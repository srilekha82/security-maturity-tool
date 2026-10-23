"""
Usage: .venv/bin/python ./scripts/record_ai_bank.py <mode> ...

The AI RMF bank build's one door for agent output. Same contract as record_judgements.py: the agent hands in a file, the
script validates the WHOLE file and rejects it if anything is wrong (exit 1, nothing stored), otherwise stores it and
writes a write-once record to data/ai/bank_build/judgement_log/ plus an audit line (actor "agent").

Script-only mode (reshapes agent output for the `candidates` record; decides nothing):
  assemble --gen1 F --eval1 F [--gen2 F --eval2 F] --out F
                                             merge generator output with the evaluator's failures into the file
                                             `candidates` records: revision (gen2) replaces the subcategories it
                                             covers; a subcategory still failing after turn 2 is needs_human_review

Preparing the agents' input is prepare_ai_bank.py; the pilot gate is ai_pilot.py; freshness of the stages is reported by
check_freshness.py --ai-bank.

Record modes (agent output; every one needs --model, optional --session, --prompt PATH ...):
  candidates <bank> <file> {"GOVERN 1.1": {"status": "pass"|"needs_human_review", "turns": 1|2, "reason": "...",
                                           "candidates": [candidate, ...]}}
                           -> data/ai/banks/question_bank_ai_rmf_<bank>.json   (entries replaced per subcategory)
                           Still checks against the old applicability.json, which was removed; TODO step 4 rewires
                           candidates to mapping rows, so it cannot run until then.
  notes <file>             {"PR.AA-05": {"exposure": "...", "use": {"base_rag": "...", "mcp_agentic": "..."}}}
                           exposure (layer 1) is required for a new entry; `use` (layer 2) may be added later
                           -> data/csf/ai_impact_notes.json
  mapping <file> [--review F]  one AI area's mapping (the drafter's file, after the evaluator's turn):
                           {"area": "mcp_tools",
                            "rows": [{"function": "MEASURE", "subcategory": "MEASURE 2.8", "cis_refs": ["MCP-8.2"],
                                      "impact": ["access"], "why": "..."}],
                            "no_question": [{"function": "MAP", "reason": "..."}]}
                           Rejected unless: the area is in ai_areas.json; each row's function is a mapped one (MAP,
                           MEASURE, MANAGE; GOVERN is foundation, asked once for the organisation, never per area); each
                           subcategory exists and belongs to the row's function; cis_refs come from the area's candidates (mapping_rules.json area_cis); impact is a
                           non-empty subset of the area's impact; a why on each row; every function has rows or a
                           no_question reason (not both); no repeated function + subcategory; every required check that applies to
                           the area is met. --review is the evaluator's last list of failures [{"function", "subcategory" (or null for the whole function), "reason"}]:
                           those rows (or functions) are stored as needs_human_review with the reason.
                           -> data/ai/mapping.json   (the area's entry replaced; other areas kept)

Candidate schema: subcategory_id is the key; each candidate has question_text, playbook_ref, cis_refs[],
scope_tags[] (empty = all usage contexts), capability, topic, optional modifiers[]. Enums and their definitions live in
data/ai/question_categories.json. This script checks structure only: whether a question is practice-revealing is the
evaluator's job.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import (AI_APPLICABILITY, AI_AREAS, AI_BANKS, AI_BUILD, AI_CIS_CSF_XLSX, AI_MAPPING,  # noqa: E402
                   AI_MAPPING_RULES, CSF_CORE, CSF_IMPACT_NOTES)
from ai_bank_common import (BANKS, DEFAULT_PROMPTS, area_candidates, area_rules, check_mapping_rules,  # noqa: E402
                            foundation_subcategories, load_inputs, load_json)
import audit  # noqa: E402

LOG_DIR = AI_BUILD / "judgement_log"
MIN_CANDIDATES, MAX_CANDIDATES = 3, 5
MIN_QUESTION_CHARS = 30
NOTE_MIN_CHARS = 30


# ── validators (each returns a list of problems; empty = valid) ─────────────

def validate_candidates(data, bank, inp) -> list[str]:
    errors = []
    if not isinstance(data, dict) or not data:
        return ["the file must be a non-empty JSON object keyed by subcategory id"]
    if not AI_APPLICABILITY.is_file():
        return ["data/ai/applicability.json not found: run the applicability pass first"]
    app = load_json(AI_APPLICABILITY, "applicability.json")["subcategories"]
    e = inp["enums"]
    for sid, entry in data.items():
        if sid not in inp["subs"]:
            errors.append(f"{sid}: unknown subcategory id")
            continue
        if not app[sid][bank]:
            errors.append(f"{sid}: not applicable to the {bank} bank (applicability.json)")
            continue
        if not isinstance(entry, dict) or entry.get("status") not in ("pass", "needs_human_review"):
            errors.append(f"{sid}: status must be 'pass' or 'needs_human_review'")
            continue
        if entry.get("turns") not in (1, 2):
            errors.append(f"{sid}: turns must be 1 or 2")
        cands = entry.get("candidates")
        if not isinstance(cands, list):
            errors.append(f"{sid}: candidates must be a list")
            continue
        if entry["status"] == "pass" and not MIN_CANDIDATES <= len(cands) <= MAX_CANDIDATES:
            errors.append(f"{sid}: a passing entry needs {MIN_CANDIDATES}-{MAX_CANDIDATES} candidates, got {len(cands)}")
        if entry["status"] == "needs_human_review":
            if not str(entry.get("reason", "")).strip():
                errors.append(f"{sid}: needs_human_review requires the evaluator's reason")
            if len(cands) > MAX_CANDIDATES:
                errors.append(f"{sid}: at most {MAX_CANDIDATES} candidates")
        topics_allowed = {inp["bank_cats"][bank][c]["topic"] for c in app[sid][bank]}
        seen = set()
        for n, c in enumerate(cands, 1):
            tag = f"{sid}#{n}"
            if not isinstance(c, dict):
                errors.append(f"{tag}: must be an object")
                continue
            need = {"question_text", "playbook_ref", "cis_refs", "scope_tags", "capability", "topic"}
            if not need <= set(c) or set(c) - need - {"modifiers"}:
                errors.append(f"{tag}: fields must be {sorted(need)} (+ optional modifiers); diff {sorted(set(c) ^ need)}")
                continue
            q = str(c["question_text"]).strip()
            if len(q) < MIN_QUESTION_CHARS:
                errors.append(f"{tag}: question_text shorter than {MIN_QUESTION_CHARS} characters")
            if q.lower() in seen:
                errors.append(f"{tag}: duplicate question within {sid}")
            seen.add(q.lower())
            if not str(c["playbook_ref"]).startswith(sid):
                errors.append(f"{tag}: playbook_ref must start with the subcategory id (e.g. '{sid} — suggested action 3')")
            if not isinstance(c["cis_refs"], list) or [g for g in c["cis_refs"] if g not in inp["safeguards"]]:
                errors.append(f"{tag}: cis_refs must be a list of ids from the companion guides")
            if not isinstance(c["scope_tags"], list) or not set(c["scope_tags"]) <= set(e["scope_tags"]):
                errors.append(f"{tag}: scope_tags must be a list from {e['scope_tags']} (empty = all)")
            if c["capability"] not in e["capability"]:
                errors.append(f"{tag}: capability must be one of {e['capability']}")
            if c["topic"] not in topics_allowed:
                errors.append(f"{tag}: topic {c['topic']!r} is not a topic of this subcategory's {bank} categories {sorted(topics_allowed)}")
            if "modifiers" in c and (not isinstance(c["modifiers"], list) or not set(c["modifiers"]) <= set(e["modifiers"])):
                errors.append(f"{tag}: modifiers must be a list from {e['modifiers']}")
    return errors


def validate_notes(data) -> list[str]:
    errors = []
    if not isinstance(data, dict) or not data:
        return ["the file must be a non-empty JSON object keyed by CSF subcategory id"]
    csf = load_json(CSF_CORE, "csf2_core.json")["subcategories"]
    valid = {s["subcategory_id"] for s in csf if not s["subcategory_text"].startswith("[Withdrawn")}
    existing = load_json(CSF_IMPACT_NOTES, "ai_impact_notes.json")["notes"] if CSF_IMPACT_NOTES.is_file() else {}
    pending_path = AI_BUILD / "impact_pending.json"
    mapped = None
    if pending_path.is_file():
        mapped = {i["subcategory_id"] for i in load_json(pending_path, "impact_pending.json")["items"]}
    for sid, v in data.items():
        if sid not in valid:
            errors.append(f"{sid}: not an active CSF 2.0 subcategory")
            continue
        if mapped is not None and sid not in mapped:
            errors.append(f"{sid}: not in impact_pending.json (no mapped AI safeguard); notes are not invented for unmapped subcategories")
        if not isinstance(v, dict) or not set(v) <= {"exposure", "use"}:
            errors.append(f"{sid}: fields must be exposure and/or use")
            continue
        if "exposure" in v:
            if not isinstance(v["exposure"], str) or len(v["exposure"].strip()) < NOTE_MIN_CHARS:
                errors.append(f"{sid}: exposure must be a note of at least {NOTE_MIN_CHARS} characters")
        elif sid not in existing:
            errors.append(f"{sid}: a new entry needs an exposure note (layer 1) first")
        if "use" in v:
            u = v["use"]
            if not isinstance(u, dict) or set(u) != {"base_rag", "mcp_agentic"} or any(
                    not isinstance(t, str) or len(t.strip()) < NOTE_MIN_CHARS for t in u.values()):
                errors.append(f"{sid}: use must have base_rag and mcp_agentic notes of at least {NOTE_MIN_CHARS} characters")
    return errors



def mapping_inputs(inp: dict) -> dict:
    """The AI areas and the mapping rules, for the mapping validator and store."""
    for p, how in ((AI_AREAS, "sheet_io.py import ai_areas"), (AI_MAPPING_RULES, "data/ai/mapping_rules.json")):
        if not p.is_file():
            sys.exit(f"[record_ai_bank] ERROR: {p} not found ({how})")
    rules = load_json(AI_MAPPING_RULES, "mapping_rules.json")
    problems = check_mapping_rules(rules, inp)
    if problems:
        sys.exit("[record_ai_bank] ERROR: mapping_rules.json does not match the CIS guides:\n  - " + "\n  - ".join(problems))
    return {"areas": {a["id"]: a for a in load_json(AI_AREAS, "ai_areas.json")["ai_areas"]}, "rules": rules}


def validate_mapping(data, inp, m: dict, review) -> list[str]:
    if not isinstance(data, dict) or set(data) - {"area", "rows", "no_question"} or "area" not in data:
        return ["the file must be an object with area, rows and no_question"]
    area_id = data["area"]
    if area_id not in m["areas"]:
        return [f"unknown AI area {area_id!r} (not in ai_areas.json)"]
    rules, area = m["rules"], m["areas"][area_id]
    rows, skips = data.get("rows", []), data.get("no_question", [])
    if not isinstance(rows, list) or not isinstance(skips, list):
        return ["rows and no_question must be lists"]
    allowed = {s["id"] for s in area_candidates(inp, rules, area_id)}
    errors, seen = [], set()
    for n, r in enumerate(rows, 1):
        tag = f"row {n}"
        if not isinstance(r, dict) or set(r) != {"function", "subcategory", "cis_refs", "impact", "why"}:
            errors.append(f"{tag}: fields must be function, subcategory, cis_refs, impact, why")
            continue
        sub = inp["subs"].get(r["subcategory"])
        if r["function"] in rules["foundation"]["functions"]:
            errors.append(f"{tag}: {r['function']} is foundation (asked once for the organisation), not mapped to an AI area")
        elif r["function"] not in rules["functions"]:
            errors.append(f"{tag}: function must be one of {rules['functions']}")
        elif sub is None:
            errors.append(f"{tag}: {r['subcategory']!r} is not an AI RMF subcategory")
        elif sub["function"] != r["function"]:
            errors.append(f"{tag}: {r['subcategory']} belongs to {sub['function']}, not {r['function']}")
        if (r["function"], r["subcategory"]) in seen:
            errors.append(f"{tag}: {r['function']} / {r['subcategory']} appears twice")
        seen.add((r["function"], r["subcategory"]))
        if not isinstance(r["cis_refs"], list) or [g for g in r["cis_refs"] if g not in allowed]:
            errors.append(f"{tag}: cis_refs must come from this area's candidates; not allowed: "
                          f"{[g for g in r['cis_refs'] if g not in allowed] if isinstance(r['cis_refs'], list) else r['cis_refs']}")
        if not isinstance(r["impact"], list) or not r["impact"] or not set(r["impact"]) <= set(area["impact"]):
            errors.append(f"{tag}: impact must be one or more of the area's impacts {area['impact']}")
        if len(str(r["why"]).strip()) < rules["min_why_chars"]:
            errors.append(f"{tag}: why must say in a sentence why this subcategory checks this area")
    with_rows = {r.get("function") for r in rows if isinstance(r, dict)}
    for s in skips:
        if not isinstance(s, dict) or s.get("function") not in rules["functions"] or \
                len(str(s.get("reason", "")).strip()) < rules["min_why_chars"]:
            errors.append(f"no_question {s!r}: needs a function and a reason")
        elif s["function"] in with_rows:
            errors.append(f"{s['function']}: has rows and a no_question entry; keep one")
    missing = [f for f in rules["functions"] if f not in with_rows and f not in {s.get("function") for s in skips
                                                                                if isinstance(s, dict)}]
    if missing:
        errors.append(f"functions with neither rows nor a no_question reason: {missing}")
    for check in area_rules(rules, area_id)["required_checks"]:
        hits = [r for r in rows if isinstance(r, dict) and r.get("subcategory") in check["any_of"]]
        if "cis_control" in check:
            hits = [r for r in hits if any(g in inp["safeguards"] and inp["safeguards"][g]["control"] == check["cis_control"]
                                           for g in r.get("cis_refs") or [])]
        if not hits:
            extra = f" citing a CIS control {check['cis_control']} safeguard" if "cis_control" in check else ""
            errors.append(f"required check '{check['name']}' missing: needs a row on {' or '.join(check['any_of'])}{extra}")
    if review is not None:
        if not isinstance(review, list):
            errors.append("the review file must be a list of failures")
        else:
            for f in review:
                key = (f.get("function"), f.get("subcategory")) if isinstance(f, dict) else None
                if key is None or not str(f.get("reason", "")).strip():
                    errors.append(f"review entry {f!r}: needs function, subcategory (or null) and reason")
                elif key[1] is None and key[0] not in rules["functions"]:
                    errors.append(f"review entry {f!r}: unknown function")
                elif key[1] is not None and key not in seen:
                    errors.append(f"review entry {f!r}: no such row in the mapping")
    return errors


def store_mapping(data, inp, m: dict, review) -> tuple[Path, str]:
    failing = {}
    for f in review or []:
        failing.setdefault((f["function"], f["subcategory"]), []).append(str(f["reason"]).strip())
    rows = []
    for r in data["rows"]:
        why = failing.get((r["function"], r["subcategory"])) or failing.get((r["function"], None))
        rows.append({**r, "status": "needs_human_review" if why else "pass", "decided_by": "agent",
                     **({"review_reason": "; ".join(why)[:500]} if why else {})})
    doc = load_json(AI_MAPPING, "mapping.json") if AI_MAPPING.is_file() else {"areas": {}}
    doc["description"] = ("AI RMF mapping: per AI area, rows of AI RMF function -> subcategory, CIS safeguards that prove "
                          "it, impact. Drafted and evaluated by agents (prompts/ai_rmf_mapping_*.md), recorded by "
                          "record_ai_bank.py mapping, reviewed by a person. Model: AI_RMF_Mapping_Sheet_Design.md.")
    doc["areas"][data["area"]] = {
        "recorded_on": date.today().isoformat(), "inputs": mapping_input_hashes(inp),
        "rows": rows, "no_question": data.get("no_question", [])}
    doc["areas"] = {a: doc["areas"][a] for a in m["areas"] if a in doc["areas"]}   # ai_areas.json order
    AI_MAPPING.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    review_n = sum(1 for r in rows if r["status"] != "pass")
    reached, unreached = mapping_coverage(doc, inp, m["rules"])
    return AI_MAPPING, (f"{data['area']}: {len(rows)} rows ({review_n} need human review); mapping has "
                        f"{len(doc['areas'])} of {len(m['areas'])} areas, {len(unreached)} subcategories not reached yet")


def mapping_input_hashes(inp: dict) -> dict:
    """What a recorded area was built from; check_freshness.py compares these with the current files."""
    return {"ai_areas": audit.sha(AI_AREAS), "rules": audit.sha(AI_MAPPING_RULES),
            "playbook": inp["core"]["source_sha256_16"],
            "guides": {g: s["sha256_16"] for g, s in inp["sg_doc"]["sources"].items()}}


def mapping_coverage(doc: dict, inp: dict, rules: dict) -> tuple[set, list]:
    """(subcategories reached by an area row or by a foundation function, the ones not reached, in AI RMF order)."""
    reached = {r["subcategory"] for a in doc.get("areas", {}).values() for r in a["rows"]}
    reached |= set(foundation_subcategories(rules, inp))
    return reached, [s for s in inp["subs"] if s not in reached]


# ── the review sheet (sheet_io.py export / import mapping) ──────────────────

ROW_FIELDS = ("cis_refs", "impact", "why", "status")   # what a person can change on a row in the sheet


def mapping_sheet_rows(doc: dict, inp: dict, m: dict) -> tuple[list[dict], list[list[str]]]:
    """(one line per recorded area x mapped-function subcategory, the Coverage sheet as rows of cells). Script only:
    the outcome and safeguard titles are looked up, nothing is decided."""
    mapped_subs = [s for s in inp["subs"].values() if s["function"] in m["rules"]["functions"]]
    lines = []
    for area_id, entry in doc.get("areas", {}).items():
        by_sub = {r["subcategory"]: r for r in entry["rows"]}
        for s in mapped_subs:
            r = by_sub.get(s["subcategory_id"])
            refs = r["cis_refs"] if r else []
            lines.append({
                "area": area_id, "area_name": m["areas"].get(area_id, {}).get("name", ""), "function": s["function"],
                "subcategory": s["subcategory_id"], "outcome": s["outcome"], "mapped": bool(r),
                "why": r["why"] if r else "", "cis_refs": refs,
                "cis_titles": "; ".join(f"{g}: {inp['safeguards'][g]['title']}" for g in refs if g in inp["safeguards"]),
                "impact": r["impact"] if r else [], "status": r["status"] if r else "",
                "review_reason": r.get("review_reason", "") if r else "", "decided_by": r["decided_by"] if r else "",
            })
    drafted = doc.get("areas", {})
    reach = {(a, r["subcategory"]) for a in drafted for r in drafted[a]["rows"]}
    foundation = set(foundation_subcategories(m["rules"], inp))
    coverage = [["Function", "Subcategory", "What it means (Playbook outcome)", "Areas reaching it",
                 *[a if a in drafted else f"{a} (not drafted)" for a in m["areas"]]]]
    for s in inp["subs"].values():   # all 72, in AI RMF order; every AI area as a column
        if s["subcategory_id"] in foundation:
            coverage.append([s["function"], s["subcategory_id"], s["outcome"], "foundation (asked once, by role)",
                             *["" for _ in m["areas"]]])
            continue
        hits = [a for a in m["areas"] if (a, s["subcategory_id"]) in reach]
        coverage.append([s["function"], s["subcategory_id"], s["outcome"], len(hits),
                         *["yes" if a in hits else "" for a in m["areas"]]])
    return lines, coverage


def mapping_from_sheet(lines: list[dict], doc: dict, inp: dict, m: dict) -> tuple[dict, list[str], int]:
    """(the mapping with the person's edits, problems, rows changed). Every edited area is checked with the same
    validator as agent output; a changed or new row is decided_by human, an unchanged one keeps what was recorded."""
    problems, changed = [], 0
    areas = doc.get("areas", {})
    sheet: dict[str, dict[str, dict]] = {}
    for n, ln in enumerate(lines, 2):
        sub = inp["subs"].get(ln["subcategory"])
        if ln["area"] not in areas:
            problems.append(f"row {n}: AI area {ln['area']!r} has no recorded mapping (draft it first)")
        elif sub is None or sub["function"] not in m["rules"]["functions"]:
            problems.append(f"row {n}: {ln['subcategory']!r} is not a MAP, MEASURE or MANAGE subcategory")
        elif ln["subcategory"] in sheet.setdefault(ln["area"], {}):
            problems.append(f"row {n}: {ln['area']} / {ln['subcategory']} appears twice")
        else:
            sheet[ln["area"]][ln["subcategory"]] = dict(ln, function=sub["function"], line=n)
    new_doc = json.loads(json.dumps(doc))
    for area_id, subs in sheet.items():
        recorded = {r["subcategory"]: r for r in areas[area_id]["rows"]}
        problems += [f"{area_id} / {sid}: the line is missing from the sheet; set Mapped to no instead of deleting it"
                     for sid in recorded if sid not in subs]
        rows = []
        for sid, ln in subs.items():
            if not ln["mapped"]:
                changed += sid in recorded
                continue
            new = {"function": ln["function"], "subcategory": sid, "cis_refs": ln["cis_refs"], "impact": ln["impact"],
                   "why": ln["why"], "status": ln["status"] or "pass"}
            old = recorded.get(sid)
            if old and all(new[k] == (str(old[k]).strip() if k == "why" else old[k]) for k in ROW_FIELDS):
                rows.append(old)
            else:
                changed += 1
                rows.append({**new, "decided_by": "human"})
        rows.sort(key=lambda r: list(inp["subs"]).index(r["subcategory"]))
        with_rows = {r["function"] for r in rows}
        draft = {"area": area_id, "rows": [{k: r[k] for k in ("function", "subcategory", "cis_refs", "impact", "why")}
                                           for r in rows],
                 "no_question": [q for q in areas[area_id].get("no_question", []) if q["function"] not in with_rows]}
        at = {f"row {k}:": f"sheet row {subs[r['subcategory']]['line']} ({r['subcategory']}):"
              for k, r in enumerate(rows, 1)}
        problems += [f"{area_id}: " + next((e.replace(a, b, 1) for a, b in at.items() if e.startswith(a + " ")), e)
                     for e in validate_mapping(draft, inp, m, None)]
        new_doc["areas"][area_id].update(rows=rows, no_question=draft["no_question"])
    return new_doc, problems, changed


def assemble(gen1: Path, eval1: Path, gen2: Path | None, eval2: Path | None, out: Path) -> str:
    """Candidates file for `candidates` from generator output and evaluator failures. No judgement: a subcategory
    passes iff the last evaluation lists no failure for it."""
    g1, f1 = load_json(gen1, "generator output"), load_json(eval1, "evaluator failures")
    for name, v in (("generator output", g1), ("evaluator failures", f1)):
        if (name == "generator output") != isinstance(v, dict):
            sys.exit(f"[record_ai_bank] ERROR: {name} has the wrong JSON type")
    if bool(gen2) != bool(eval2):
        sys.exit("[record_ai_bank] ERROR: --gen2 and --eval2 go together")
    final, last_fail, turns = {sid: v["candidates"] for sid, v in g1.items()}, f1, {sid: 1 for sid in g1}
    if gen2:
        g2, f2 = load_json(gen2, "revision output"), load_json(eval2, "second evaluation")
        for sid, v in g2.items():
            if sid not in final:
                sys.exit(f"[record_ai_bank] ERROR: revision covers {sid}, which turn 1 did not")
            final[sid], turns[sid] = v["candidates"], 2
        last_fail = [f for f in f1 if f["subcategory_id"] not in g2] + f2
    failing: dict[str, list[str]] = {}
    for f in last_fail:
        if f.get("subcategory_id") not in final:
            sys.exit(f"[record_ai_bank] ERROR: failure for unknown subcategory {f.get('subcategory_id')!r}")
        failing.setdefault(f["subcategory_id"], []).append(
            f"Q{f.get('question_number')}: {str(f.get('reason', '')).strip()}")
    result = {}
    for sid in final:
        entry = {"status": "needs_human_review" if sid in failing else "pass", "turns": turns[sid], "candidates": final[sid]}
        if sid in failing:
            entry["reason"] = "; ".join(failing[sid])[:500]
        result[sid] = entry
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return f"{len(result)} subcategories: {len(result) - len(failing)} pass, {len(failing)} need human review → {out.name}"

# ── storing ─────────────────────────────────────────────────────────────────

def store(mode: str, data: dict, args, inp: dict) -> tuple[Path, str]:
    """Write the validated data to its store; returns (store path, one-line summary)."""
    today = date.today().isoformat()
    if mode == "candidates":
        path = AI_BANKS / f"question_bank_ai_rmf_{args.bank}.json"
        AI_BANKS.mkdir(parents=True, exist_ok=True)
        bank = load_json(path, path.name) if path.is_file() else {"bank": args.bank, "subcategories": {}}
        app = load_json(AI_APPLICABILITY, "applicability.json")["subcategories"]
        for sid, entry in data.items():
            bank["subcategories"][sid] = {
                "categories": app[sid][args.bank], "status": entry["status"], "turns": entry["turns"],
                **({"review_reason": entry["reason"]} if entry.get("reason") else {}),
                "candidates": entry["candidates"]}
        bank["subcategories"] = {sid: bank["subcategories"][sid] for sid in inp["subs"] if sid in bank["subcategories"]}
        bank.update({"built_on": today, "playbook_sha256_16": inp["core"]["source_sha256_16"],
                     "guide_sha256_16": {g: s["sha256_16"] for g, s in inp["sg_doc"]["sources"].items()}})
        passed = sum(1 for e in bank["subcategories"].values() if e["status"] == "pass")
        review = len(bank["subcategories"]) - passed
        bank["summary"] = {"subcategories": len(bank["subcategories"]), "passed": passed, "needs_human_review": review,
                           "candidates": sum(len(e["candidates"]) for e in bank["subcategories"].values())}
        path.write_text(json.dumps(bank, indent=2, ensure_ascii=False))
        return path, f"{args.bank} bank: recorded {len(data)} subcategories; bank has {passed} passed, {review} needing human review"
    if mode == "notes":
        store_doc = load_json(CSF_IMPACT_NOTES, "ai_impact_notes.json") if CSF_IMPACT_NOTES.is_file() else {"notes": {}}
        for sid, v in data.items():
            store_doc["notes"].setdefault(sid, {}).update(v)
        store_doc["notes"] = dict(sorted(store_doc["notes"].items()))
        store_doc.update({
            "description": ("AI-world notes per CSF 2.0 subcategory. `exposure` is shown to every org; `use` only when AI is "
                            "in use (base_rag for the base/rag rungs, mcp_agentic for the mcp/agentic rungs). Written by an "
                            "agent from the CIS MCP and agents companion guides joined to CSF via the official CIS v8.1 -> CSF "
                            "2.0 mapping, then reviewed. The Stage 2 XLS writer selects from the intake (AI in use, highest rung)."),
            "judged_on": today,
            "sources_sha256_16": {"cis_csf": audit.sha(AI_CIS_CSF_XLSX),
                                  **{g: inp["sg_doc"]["sources"][g]["sha256_16"] for g in ("MCP", "AGENT")}}})
        CSF_IMPACT_NOTES.write_text(json.dumps(store_doc, indent=2, ensure_ascii=False))
        with_use = sum(1 for v in store_doc["notes"].values() if "use" in v)
        return CSF_IMPACT_NOTES, f"{len(store_doc['notes'])} subcategories with notes, {with_use} with a use layer"
    raise AssertionError(mode)


def record(mode: str, args) -> None:
    inp = load_inputs()
    if mode == "mapping":
        m = mapping_inputs(inp)
        review = load_json(Path(args.review), "review file") if getattr(args, "review", None) else None
        validate = lambda d: validate_mapping(d, inp, m, review)                # noqa: E731
        store_fn = lambda d: store_mapping(d, inp, m, review)                    # noqa: E731
        extra = {"review_file": args.review, "review": review}
        log_name = lambda d: f"mapping_{d.get('area', 'unknown')}" if isinstance(d, dict) else "mapping"  # noqa: E731
    else:
        validate = {"candidates": lambda d: validate_candidates(d, args.bank, inp),
                    "notes": validate_notes}[mode]
        store_fn, extra = (lambda d: store(mode, d, args, inp)), None
        log_name = f"{mode}_{args.bank}" if mode == "candidates" else mode
    audit.record_agent_output(
        log_path=AI_BUILD / "audit.jsonl", log_dir=LOG_DIR, step=f"record_ai_bank_{mode}",
        args={"file": args.file, "bank": getattr(args, "bank", None)}, file=args.file,
        validate=validate, store=store_fn,
        model=args.model, session=args.session, prompts=args.prompt or DEFAULT_PROMPTS[mode],
        log_name=log_name, extra_record=extra)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    pa = sub.add_parser("assemble")
    for name in ("gen1", "eval1", "gen2", "eval2"):
        pa.add_argument(f"--{name}", required=name in ("gen1", "eval1"))
    pa.add_argument("--out", required=True)

    for m in ("candidates", "notes", "mapping"):
        p = sub.add_parser(m)
        if m == "candidates":
            p.add_argument("bank", choices=BANKS)
        p.add_argument("file")
        if m == "mapping":
            p.add_argument("--review", help="the evaluator's last list of failures (rows stored as needs_human_review)")
        p.add_argument("--model", required=True, help="model id of the agent that produced the file")
        p.add_argument("--session")
        p.add_argument("--prompt", nargs="*", help="prompt file(s) the agent followed, relative to the repo root")
    args = ap.parse_args()

    if args.mode == "assemble":
        ev = audit.begin(AI_BUILD / "audit.jsonl", "assemble_candidates", {"gen1": args.gen1, "gen2": args.gen2})
        ins = [Path(p) for p in (args.gen1, args.eval1, args.gen2, args.eval2) if p]
        line = assemble(Path(args.gen1), Path(args.eval1), Path(args.gen2) if args.gen2 else None,
                        Path(args.eval2) if args.eval2 else None, Path(args.out))
        print(f"[record_ai_bank] {line}")
        ev.finish(inputs=ins, outputs=[Path(args.out)], detail=line)
        return
    record(args.mode, args)


if __name__ == "__main__":
    main()
