"""
Usage: .venv/bin/python ./scripts/record_ai_bank.py <mode> ...

The AI RMF bank build's one door for agent output. Same contract as record_judgements.py: the agent hands in a file, the
script validates the WHOLE file and rejects it if anything is wrong (exit 1, nothing stored), otherwise stores it and
writes a write-once record to data/ai/bank_build/judgement_log/ plus an audit line (actor "agent").

Script-only mode (reshapes agent output for the `questions` record; decides nothing):
  assemble --gen1 F --eval1 F [--gen2 F --eval2 F] --out F
                                             merge generator output with the evaluator's verdicts into the file
                                             `questions` records: revision (gen2) replaces the subcategories it
                                             covers; a subcategory still failing after turn 2 is needs_human_review.
                                             An evaluator file must hold a verdict on checks 1-9 for every question
                                             and a `complete` verdict per subcategory; a turn 2 file may fail a
                                             question that is unchanged and passed turn 1 only on checks 6 and 7.

Preparing the agents' input is prepare_ai_bank.py; the pilot gate is ai_pilot.py; freshness of the stages is reported by
check_freshness.py --ai-bank.

Record modes (agent output; every one needs --model, optional --session, --prompt PATH ...):
  questions <areas|foundation> <file>
                           {"MEASURE 2.8": {"status": "pass"|"needs_human_review", "turns": 1|2, "reason": "...",
                                            "questions": [question, ...]}}
                           -> data/ai/banks/question_bank_ai_rmf_<bank>.json   (entries replaced per subcategory)
                           A question: question_text, playbook_refs ["<subcategory> — suggested action N", ...],
                           cis_refs, roles (none / consumer / producer), producer_flags (data/ai/question_rules.json);
                           area bank also rows (mapping row ids "<area>|<subcategory>" it covers).
                           Rejected unless (area bank) the subcategory has rows in data/ai/mapping.json, each row is
                           asked once or twice (row_questions max) for each role its area allows (area_roles), a
                           question's roles are allowed
                           by every row it covers, its cis_refs are safeguards of those rows, and a row with folded
                           subcategories has its question cite a suggested action of each; (foundation) the subcategory
                           is foundation, it has question_rules.json foundation_questions min to max questions (plus
                           producer_only_extra asked of producers only), at least
                           one consumer and one producer question without producer flags, and no cis_refs. Both: real
                           suggested action numbers, distinct question texts, a question with producer flags has roles
                           ["producer"] only. Whether a question is practice-revealing is the evaluator's job.
                           A subcategory a person decided in the review sheet (decided_by human) is not overwritten
                           unless --replace-human.
  notes <file>             {"PR.AA-05": {"exposure": "...", "use": {"base_rag": "...", "mcp_agentic": "..."}}}
                           exposure (layer 1) is required for a new entry; `use` (layer 2) may be added later;
                           a subcategory a person decided in the review sheet is refused. A rewritten note loses
                           its review status (to be reviewed again).
                           -> data/csf/ai_impact_notes.json
  notes-review <file>      the notes evaluator's findings: [{"subcategory_id": "PR.AA-05", "note": "exposure" |
                           "base_rag" | "mcp_agentic" | "use", "reason": "..."}] ([] = all pass); every recorded
                           subcategory not decided by a person gets status pass or needs_human_review (with the
                           reasons). -> data/csf/ai_impact_notes.json
  mapping <file> [--review F]  one AI area's mapping (the drafter's file, after the evaluator's turn):
                           {"area": "mcp_tools",
                            "rows": [{"function": "MEASURE", "subcategory": "MEASURE 2.8", "cis_refs": ["MCP-8.2"],
                                      "impact": ["access"], "why": "..."}],
                            "no_question": [{"function": "MAP", "reason": "..."}]}
                           Rejected unless: the area is in ai_areas.json; each row's function is a mapped one (MAP,
                           MEASURE, MANAGE; GOVERN is foundation, asked once for the organisation, never per area); each
                           subcategory exists and belongs to the row's function; cis_refs come from the area's candidates (mapping_rules.json area_cis); impact is a
                           non-empty subset of the area's impact; a why on each row; an optional folded list (subcategories
                           this row also covers, merged by the drafter) names mapped subcategories that have no row of
                           their own and are folded once; every function has rows or a
                           no_question reason (not both); no repeated function + subcategory; every required check that applies to
                           the area is met. --review is the evaluator's last list [{"kind", "function", "subcategory",
                           "reason"}]: kind "row" (default) fails a row, stored as needs_human_review with the reason;
                           "missing" names a subcategory that should be a row, stored once in the area's `missing` list
                           (it needs human review; the area's other rows are not flagged); "note" is a remark that never
                           blocks (e.g. the area's impacts look too narrow), stored in the area's `notes`.
                           The rows a person decided (decided_by human, removed_by_human) are merged in and the result
                           is checked again before anything is stored.
                           -> data/ai/mapping.json   (the area's entry replaced; other areas kept)

Script-only modes (no agent output):
  revalidate               a change is a delta: when only the mapping rules or other AI areas changed, every recorded
                           area that is not current is checked again against the current rules (the same validator as
                           agent output). An area that passes is stamped current, its rows untouched; one that fails is
                           listed with its problems (fix them in mapping.xlsx). An area whose own row in the AI areas
                           sheet changed, or whose sources (Playbook, CIS guides) changed, must be re-drafted instead.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import (AI_AREAS, AI_BANKS, AI_BUILD, AI_CIS_CSF_XLSX, AI_MAPPING, AI_MAPPING_RULES,  # noqa: E402
                   AI_QUESTION_RULES, AI_SCOPE_RULES, CSF_CORE, CSF_IMPACT_NOTES)
from ai_bank_common import (DEFAULT_PROMPTS, area_candidates, area_roles, area_rules, check_mapping_rules,  # noqa: E402
                            foundation_subcategories, load_inputs, load_json, row_id)
from options import AI_QUESTION_BANKS  # noqa: E402
import audit  # noqa: E402

LOG_DIR = AI_BUILD / "judgement_log"
BANK_DESCRIPTION = {
    "areas": ("AI RMF area questions: every question that could be asked per mapping row (AI area x subcategory, "
              "data/ai/mapping.json), keyed by subcategory. A question lists the rows it covers (one question may stand "
              "for several areas' rows), the roles it is asked of and any producer flags; build_ai_questions.py picks a "
              "client's questions by filtering on their AI areas, role and producer flags. rows_sha is the hash of the "
              "subcategory's mapping rows the questions were written for; rows gives each row's area and impact (for the "
              "covers note and the evidence prompt). Recorded by record_ai_bank.py questions."),
    "foundation": ("AI RMF foundation questions: every question that could be asked once for the organisation (GOVERN "
                   "and the foundation subcategories of mapping_rules.json), keyed by subcategory, each with the roles "
                   "it is asked of (none, consumer, producer) and any producer flags. Recorded by record_ai_bank.py "
                   "questions."),
}
MIN_QUESTION_CHARS = 30
PLAYBOOK_REF = re.compile(r"^((?:GOVERN|MAP|MEASURE|MANAGE) \d+\.\d+) [—–-] suggested action (\d+)$")
REASON_PART = re.compile(r"(?:^|; )Q(\d+): ")    # assemble joins failures as "Q<n>: reason; Q<m>: reason"
WHOLE = "Whole subcategory: "                      # how a question_number 0 failure shows on every line of the sheet
STALE = "the mapping rows changed since these questions were written: check them against the rows, then set pass"
NOTE_MIN_CHARS = 30


# ── validators (each returns a list of problems; empty = valid) ─────────────

def question_context(inp: dict) -> dict:
    """What validate_questions checks against: the accepted mapping's rows per subcategory, the roles each area allows,
    the foundation subcategories and the question rules."""
    for p, how in ((AI_MAPPING, "record and accept the mapping first"), (AI_AREAS, "sheet_io.py import ai_areas")):
        if not p.is_file():
            sys.exit(f"[record_ai_bank] ERROR: {p} not found ({how})")
    qrules = load_json(AI_QUESTION_RULES, "question_rules.json")
    scope_rules = load_json(AI_SCOPE_RULES, "scope_rules.json")
    areas = {a["id"]: a for a in load_json(AI_AREAS, "ai_areas.json")["ai_areas"]}
    rows: dict[str, dict] = {}
    for area_id, entry in load_json(AI_MAPPING, "mapping.json")["areas"].items():
        roles = area_roles(areas[area_id], qrules, scope_rules)
        for r in entry["rows"]:
            rows.setdefault(r["subcategory"], {})[row_id(area_id, r["subcategory"])] = {
                "roles": roles, "cis_refs": r["cis_refs"], "folded": r.get("folded", []),
                "area": area_id, "impact": r["impact"], "sig": [r["why"], r["cis_refs"], r.get("folded", [])]}
    return {"rows": rows, "foundation": foundation_subcategories(load_json(AI_MAPPING_RULES, "mapping_rules.json"), inp),
            "roles": list(qrules["roles"]), "flags": list(qrules["producer_flags"]),
            "foundation_count": qrules["foundation_questions"], "row_max": qrules["row_questions"]["max"]}


def rows_sha(rows: dict) -> str:
    """Hash of a subcategory's mapping rows as the questions were written for them (a changed row makes them stale)."""
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def rows_record(ctx: dict, sid: str) -> dict:
    """What an area bank entry stores about the rows its questions were written for."""
    return {"rows_sha": rows_sha({r: v["sig"] for r, v in ctx["rows"][sid].items()}),
            "rows": {r: {"area": v["area"], "impact": v["impact"]} for r, v in ctx["rows"][sid].items()}}


def bank_freshness(bank: str, doc: dict, inp: dict) -> tuple[bool, str]:
    """(complete?, text) for a question bank against what it must hold now: area bank, every subcategory with mapping rows,
    each written for the rows as they are now (rows_sha); foundation bank, every foundation subcategory."""
    ctx = question_context(inp)
    want = list(ctx["rows"]) if bank == "areas" else ctx["foundation"]
    have = doc["subcategories"]
    missing = [s for s in want if s not in have]
    extra = [s for s in have if s not in want]
    changed = [s for s in want if s in have and bank == "areas"
               and have[s].get("rows_sha") != rows_sha({r: v["sig"] for r, v in ctx["rows"][s].items()})]
    review = sum(1 for e in have.values() if e["status"] == "needs_human_review")
    if missing or extra or changed:
        parts = ([f"{len(missing)} of {len(want)} subcategories missing"] if missing else []) + \
                ([f"no longer in the bank's scope: {', '.join(extra)}"] if extra else []) + \
                ([f"mapping rows changed since written: {', '.join(changed)}"] if changed else [])
        return False, "incomplete (" + "; ".join(parts) + ")"
    return True, f"current ({len(have)} subcategories, {review} need human review)"


def check_question(tag: str, sid: str, q, bank: str, inp: dict, ctx: dict) -> list[str]:
    """Problems of one question (fields, refs, roles, flags; area bank: the rows it covers)."""
    need = {"question_text", "playbook_refs", "cis_refs", "roles", "producer_flags"} | ({"rows"} if bank == "areas" else set())
    if not isinstance(q, dict) or set(q) != need:
        return [f"{tag}: fields must be exactly {sorted(need)}"
                + (f"; diff {sorted(set(q) ^ need)}" if isinstance(q, dict) else "")]
    if not all(isinstance(q[k], list) for k in need - {"question_text"}):
        return [f"{tag}: {sorted(need - {'question_text'})} must be lists"]
    errors = []
    if len(str(q["question_text"]).strip()) < MIN_QUESTION_CHARS:
        errors.append(f"{tag}: question_text shorter than {MIN_QUESTION_CHARS} characters")
    rows = ctx["rows"].get(sid, {})
    covered = [rows[r] for r in q.get("rows", []) if r in rows]
    if bank == "areas":
        bad = [r for r in q["rows"] if r not in rows]
        if not q["rows"] or bad or len(set(q["rows"])) != len(q["rows"]):
            errors.append(f"{tag}: rows must be distinct mapping rows of {sid} (unknown: {bad})")
    allowed_subs = {sid} | {f for r in covered for f in r["folded"]}
    if not q["playbook_refs"]:
        errors.append(f"{tag}: playbook_refs must name at least one suggested action")
    for ref in q["playbook_refs"]:
        m = PLAYBOOK_REF.match(str(ref))
        if not m or m.group(1) not in allowed_subs:
            errors.append(f"{tag}: playbook_ref {ref!r} must be '<subcategory> — suggested action N' for "
                          f"{sorted(allowed_subs)}")
        elif not 1 <= int(m.group(2)) <= len(inp["subs"][m.group(1)]["suggested_actions"]):
            errors.append(f"{tag}: {m.group(1)} has no suggested action {m.group(2)}")
    allowed_cis = {c for r in covered for c in r["cis_refs"]}
    if set(q["cis_refs"]) - allowed_cis:
        errors.append(f"{tag}: cis_refs {sorted(set(q['cis_refs']) - allowed_cis)} are not safeguards of the rows it "
                      f"covers" + (" (foundation questions cite none)" if bank == "foundation" else ""))
    roles = q["roles"]
    allowed_roles = (set.intersection(*(set(r["roles"]) for r in covered)) if covered else set()) \
        if bank == "areas" else set(ctx["roles"])
    if not roles or len(set(roles)) != len(roles) or set(roles) - allowed_roles:
        errors.append(f"{tag}: roles {roles} must be distinct and from {sorted(allowed_roles)}"
                      + (" (the roles every covered row's area allows)" if bank == "areas" else ""))
    flags = q["producer_flags"]
    if set(flags) - set(ctx["flags"]) or len(set(flags)) != len(flags):
        errors.append(f"{tag}: producer_flags must be distinct and from {ctx['flags']}")
    elif flags and roles != ["producer"]:
        errors.append(f"{tag}: a question with producer flags is asked of producers only (roles ['producer'])")
    return errors


def validate_questions(data, bank: str, inp: dict, ctx: dict) -> list[str]:
    """The whole file, per subcategory: status, the questions, and coverage (area bank: every row asked once, or up to
    row_questions max times, per role its area allows, folded outcomes cited; foundation: the count, a consumer and a producer question)."""
    if not isinstance(data, dict) or not data:
        return ["the file must be a non-empty JSON object keyed by subcategory id"]
    errors = []
    for sid, entry in data.items():
        if bank == "areas" and sid not in ctx["rows"]:
            errors.append(f"{sid}: not a subcategory with mapping rows (foundation subcategories go in the foundation bank)")
            continue
        if bank == "foundation" and sid not in ctx["foundation"]:
            errors.append(f"{sid}: not a foundation subcategory")
            continue
        if not isinstance(entry, dict) or entry.get("status") not in ("pass", "needs_human_review"):
            errors.append(f"{sid}: status must be 'pass' or 'needs_human_review'")
            continue
        if entry.get("turns") not in (1, 2):
            errors.append(f"{sid}: turns must be 1 or 2")
        if entry["status"] == "needs_human_review" and not str(entry.get("reason", "")).strip():
            errors.append(f"{sid}: needs_human_review requires the evaluator's reason")
        qs = entry.get("questions")
        if not isinstance(qs, list) or not qs:
            errors.append(f"{sid}: questions must be a non-empty list")
            continue
        problems = [e for n, q in enumerate(qs, 1) for e in check_question(f"{sid}#{n}", sid, q, bank, inp, ctx)]
        texts = [str(q.get("question_text", "")).strip().lower() for q in qs if isinstance(q, dict)]
        if len(set(texts)) != len(texts):
            problems.append(f"{sid}: the same question_text twice")
        errors += problems
        if problems:
            continue
        if bank == "areas":
            for rid, row in ctx["rows"][sid].items():
                for role in row["roles"]:
                    n = sum(1 for q in qs if rid in q["rows"] and role in q["roles"])
                    if not 1 <= n <= ctx["row_max"]:
                        errors.append(f"{sid}: row {rid} is asked {n} times for role {role} (1 to {ctx['row_max']})")
                for f in row["folded"]:
                    if not any(rid in q["rows"] and any(str(r).startswith(f + " ") for r in q["playbook_refs"])
                               for q in qs):
                        errors.append(f"{sid}: row {rid} folds {f}; one of its questions must cite a suggested action "
                                      f"of {f}")
        else:
            fc = ctx["foundation_count"]
            lo, hi, extra = fc["min"], fc["max"], fc["producer_only_extra"]
            shared = sum(1 for q in qs if q["roles"] != ["producer"])
            if not lo <= len(qs) <= hi + extra or shared > hi:
                errors.append(f"{sid}: {len(qs)} questions ({shared} not producer-only); a foundation subcategory has "
                              f"{lo} to {hi}, plus up to {extra} asked of producers only")
            for role in ("consumer", "producer"):
                if not any(role in q["roles"] and not q["producer_flags"] for q in qs):
                    errors.append(f"{sid}: no {role} question without producer flags (every {role} is scored on it)")
    return errors


def human_decided(data, args) -> list[str]:
    """A subcategory a person decided in the review sheet is not overwritten by agent output unless --replace-human."""
    path = AI_BANKS / f"question_bank_ai_rmf_{args.bank}.json"
    if not isinstance(data, dict) or not path.is_file() or getattr(args, "replace_human", False):
        return []
    bank = load_json(path, path.name)["subcategories"]
    return [f"{sid}: decided by a person in the review sheet; leave it out of the batch, or pass --replace-human if the "
            "person agreed to regenerate it" for sid in data if bank.get(sid, {}).get("decided_by") == "human"]


def split_reason(reason: str) -> dict[int, str]:
    """{question number: reason} from a stored review_reason (0 = the whole subcategory); {} if it has no Q<n> parts."""
    cuts = list(REASON_PART.finditer(reason or ""))
    parts: dict[int, str] = {}
    for m, nxt in zip(cuts, cuts[1:] + [None]):
        text = reason[m.end():nxt.start() if nxt else None].strip()
        parts[int(m.group(1))] = "; ".join(filter(None, [parts.get(int(m.group(1))), text]))
    return parts


def join_reason(parts: dict[int, str]) -> str:
    return "; ".join(f"Q{n}: {t}" for n, t in sorted(parts.items()))[:500]


def review_view(bank: str, entry: dict, sid: str, ctx: dict) -> dict:
    """The entry as the review sheet shows it: an area entry whose mapping rows changed since its questions were written
    is flagged for the whole subcategory (STALE) until a person sets it pass."""
    if bank != "areas" or sid not in ctx["rows"] or entry.get("rows_sha") == rows_record(ctx, sid)["rows_sha"]:
        return entry
    parts = split_reason(entry.get("review_reason", "")) if entry["status"] != "pass" else {}
    return dict(entry, status="needs_human_review", review_reason=join_reason({**parts, 0: STALE}))


def line_review(entry: dict, n: int) -> tuple[str, str]:
    """(status, reason) of question n's sheet line: only its own failure and any whole-subcategory one. A reason
    without Q<n> parts (written by hand) flags every line."""
    if entry["status"] == "pass":
        return "pass", ""
    reason = entry.get("review_reason", "")
    parts = split_reason(reason)
    if not parts:
        return "needs_human_review", reason
    own = "\n".join(filter(None, [parts.get(n), WHOLE + parts[0] if 0 in parts else ""]))
    return ("needs_human_review" if own else "pass"), own


def reason_from_lines(lines: list[dict]) -> dict[int, str]:
    """The inverse of line_review over a subcategory's lines as they are now (renumbered by position)."""
    parts: dict[int, str] = {}
    for n, ln in enumerate(lines, 1):
        if ln["status"] != "needs_human_review":
            continue
        own, _, whole = str(ln.get("review_reason") or "").partition(WHOLE)
        if whole.strip():
            parts[0] = whole.strip()
        if own.strip() or not whole.strip():
            parts[n] = own.strip() or "flagged in the review sheet"
    return parts


def question_sheet_rows(bank: str, doc: dict, inp: dict) -> list[dict]:
    """One review-sheet line per question of the bank (sheet_io.py export area_questions / foundation_questions)."""
    names = {a["id"]: a["name"] for a in load_json(AI_AREAS, "ai_areas.json")["ai_areas"]}
    ctx = question_context(inp)
    lines = []
    for sid, entry in doc["subcategories"].items():
        entry = review_view(bank, entry, sid, ctx)
        for n, q in enumerate(entry["questions"], 1):
            areas = [r.split("|")[0] for r in q.get("rows", [])]
            status, reason = line_review(entry, n)
            lines.append({
                "subcategory": sid, "outcome": inp["subs"][sid]["outcome"], "q": str(n), "areas": areas,
                "area_names": "; ".join(names.get(a, a) for a in areas), "roles": q["roles"],
                "producer_flags": q["producer_flags"], "question_text": q["question_text"],
                "playbook_refs": q["playbook_refs"], "cis_refs": q["cis_refs"], "status": status,
                "review_reason": reason, "decided_by": entry.get("decided_by", "agent")})
    return lines


def questions_from_sheet(bank: str, lines: list[dict], doc: dict, inp: dict) -> tuple[dict, list[str], int]:
    """(new bank, problems, subcategories changed) from the review sheet. The whole bank is checked with
    validate_questions; a subcategory whose questions, status or flagged questions differ from the bank is stored as
    decided_by human. Each line carries its own status; the subcategory is needs_human_review while any line is. An area
    subcategory whose mapping rows changed (review_view) is stored against the rows as they are now once every line is
    set pass.
    Subcategories come from generation: the sheet may not add one or drop one."""
    by_sub: dict[str, list[dict]] = {}
    problems = []
    for n, ln in enumerate(lines, 2):
        if ln["subcategory"] not in doc["subcategories"]:
            problems.append(f"row {n}: {ln['subcategory']} is not in the {bank} bank (new subcategories come from "
                            "/build-ai-bank)")
            continue
        by_sub.setdefault(ln["subcategory"], []).append(ln)
    dropped = [sid for sid in doc["subcategories"] if sid not in by_sub]
    if dropped:
        problems.append(f"every subcategory keeps at least one question; no lines left for {', '.join(dropped)}")
    if problems:
        return doc, problems, 0
    ctx = question_context(inp)
    data, changed = {}, []
    for sid, sub_lines in by_sub.items():
        old = review_view(bank, doc["subcategories"][sid], sid, ctx)
        qs = []
        for ln in sub_lines:
            q = {"question_text": ln["question_text"], "playbook_refs": ln["playbook_refs"], "cis_refs": ln["cis_refs"],
                 "roles": ln["roles"], "producer_flags": ln["producer_flags"]}
            if bank == "areas":
                q["rows"] = [row_id(a, sid) for a in ln["areas"]]
            qs.append(q)
        parts = reason_from_lines(sub_lines)
        status = "needs_human_review" if parts else "pass"
        data[sid] = {"status": status, "turns": old["turns"], "questions": qs,
                     **({"reason": join_reason(parts)} if parts else {})}
        old_parts = split_reason(old.get("review_reason", "")) if old["status"] != "pass" else {}
        if qs != old["questions"] or status != old["status"] or (old_parts and parts != old_parts):
            changed.append(sid)
    problems = validate_questions(data, bank, inp, ctx)
    if problems:
        return doc, problems, 0
    new = json.loads(json.dumps(doc))
    for sid in changed:
        e = new["subcategories"][sid]
        e.update({"status": data[sid]["status"], "questions": data[sid]["questions"], "decided_by": "human"})
        if data[sid]["status"] == "pass":
            e.pop("review_reason", None)
            if bank == "areas":
                e.update(rows_record(ctx, sid))
        else:
            e["review_reason"] = data[sid]["reason"]
    passed = sum(1 for e in new["subcategories"].values() if e["status"] == "pass")
    new["summary"] = {"subcategories": len(new["subcategories"]), "passed": passed,
                      "needs_human_review": len(new["subcategories"]) - passed,
                      "questions": sum(len(e["questions"]) for e in new["subcategories"].values())}
    return new, [], len(changed)


NOTE_KEYS = ("exposure", "base_rag", "mcp_agentic")   # the notes of one CSF subcategory; "use" = its use layer as a whole


def validate_notes_review(data) -> list[str]:
    """The notes evaluator's findings: [{subcategory_id, note (exposure, base_rag, mcp_agentic or use), reason}], on
    stored notes a person has not decided ([] = every note passes)."""
    if not isinstance(data, list):
        return ["the file must be a JSON list of findings ([] if every note passes)"]
    notes = load_json(CSF_IMPACT_NOTES, "ai_impact_notes.json")["notes"] if CSF_IMPACT_NOTES.is_file() else {}
    errors = []
    for n, f in enumerate(data, 1):
        if not isinstance(f, dict) or set(f) != {"subcategory_id", "note", "reason"}:
            errors.append(f"finding {n}: fields must be exactly subcategory_id, note, reason")
            continue
        sid = f["subcategory_id"]
        if sid not in notes:
            errors.append(f"finding {n}: {sid} has no recorded notes")
        elif f["note"] not in NOTE_KEYS + ("use",) or (f["note"] in NOTE_KEYS[1:] and "use" not in notes[sid]):
            errors.append(f"finding {n}: note must be exposure, use, or base_rag / mcp_agentic of a use layer {sid} has")
        elif notes[sid].get("decided_by") == "human":
            errors.append(f"finding {n}: {sid} was decided by a person in the review sheet")
        if not str(f.get("reason", "")).strip():
            errors.append(f"finding {n}: reason is empty")
    return errors


def notes_sheet_rows(doc: dict) -> list[dict]:
    """One review-sheet line per CSF subcategory with notes (sheet_io.py export impact_notes)."""
    outcome = {s["subcategory_id"]: s["subcategory_text"] for s in load_json(CSF_CORE, "csf2_core.json")["subcategories"]}
    return [{"subcategory": sid, "outcome": outcome.get(sid, ""), "exposure": v["exposure"],
             "base_rag": v.get("use", {}).get("base_rag", ""), "mcp_agentic": v.get("use", {}).get("mcp_agentic", ""),
             "status": v.get("status", "pass"), "review_reason": v.get("review_reason", ""),
             "decided_by": v.get("decided_by", "agent")} for sid, v in doc["notes"].items()]


def notes_from_sheet(lines: list[dict], doc: dict) -> tuple[dict, list[str], int]:
    """(new notes doc, problems, subcategories changed) from the review sheet. Notes come from the writer: the sheet may
    change them, clear or fill a use layer (both use notes or neither), and set Status, but not add or drop a
    subcategory. A changed subcategory is stored as decided_by human."""
    notes, problems, seen, changed = doc["notes"], [], set(), []
    new = json.loads(json.dumps(doc))
    for n, ln in enumerate(lines, 2):
        sid = ln["subcategory"]
        if sid not in notes or sid in seen:
            problems.append(f"row {n}: {sid} is not a recorded subcategory, or is listed twice (notes come from "
                            "/build-ai-bank, Step 7)")
            continue
        seen.add(sid)
        entry = {"exposure": str(ln["exposure"] or "").strip()}
        use = {k: str(ln[k] or "").strip() for k in NOTE_KEYS[1:]}
        if any(use.values()):
            entry["use"] = use
        bad = validate_notes({sid: entry}, from_sheet=True)
        if not all(use.values()) and any(use.values()):
            bad.append(f"{sid}: give both use notes (model / RAG and tools / agents) or neither")
        problems += [f"row {n}: {b}" for b in bad]
        old = notes[sid]
        if bad or ({k: old[k] for k in ("exposure", "use") if k in old} == entry
                   and ln["status"] == old.get("status", "pass")):
            continue
        e = new["notes"][sid]
        e.pop("use", None)
        e.update(entry, status=ln["status"], decided_by="human")
        if ln["status"] == "pass":
            e.pop("review_reason", None)
        else:
            e["review_reason"] = old.get("review_reason") or "flagged in the review sheet"
        changed.append(sid)
    if set(notes) - seen:
        problems.append(f"every subcategory keeps its notes; no line for {', '.join(sorted(set(notes) - seen))}")
    if problems:
        return doc, problems, 0
    return new, [], len(changed)


def validate_notes(data, from_sheet: bool = False) -> list[str]:
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
        if not from_sheet and existing.get(sid, {}).get("decided_by") == "human" and \
                v != {k: existing[sid].get(k) for k in v}:
            errors.append(f"{sid}: decided by a person in the review sheet (sheet_io.py import impact_notes); not "
                          "overwritten")
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
        if not isinstance(r, dict) or not {"function", "subcategory", "cis_refs", "impact", "why"} <= set(r) <= \
                {"function", "subcategory", "cis_refs", "impact", "why", "folded"}:
            errors.append(f"{tag}: fields must be function, subcategory, cis_refs, impact, why (and optional folded)")
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
        elif r["subcategory"] in rules["foundation"]["subcategories"]:
            errors.append(f"{tag}: {r['subcategory']} is foundation (asked once for the organisation), not mapped to an AI area")
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
    errors += folded_problems(rows, inp, rules)
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
            folded = {sid for r in rows if isinstance(r, dict) for sid in r.get("folded") or []}
            for f in review:
                kind = f.get("kind", "row") if isinstance(f, dict) else None
                key = (f.get("function"), f.get("subcategory")) if isinstance(f, dict) else None
                sub = inp["subs"].get(key[1]) if key else None
                if key is None or kind not in REVIEW_KINDS or not str(f.get("reason", "")).strip():
                    errors.append(f"review entry {f!r}: needs kind ({', '.join(REVIEW_KINDS)}), function, subcategory "
                                  "and reason")
                elif sub is None or sub["function"] != key[0]:
                    errors.append(f"review entry {f!r}: subcategory must be a subcategory of the function")
                elif kind == "row" and key not in seen:
                    errors.append(f"review entry {f!r}: no such row in the mapping (use kind missing for a subcategory "
                                  "that should be a row)")
                elif kind == "missing" and (key in seen or key[1] in folded
                                            or key[1] in rules["foundation"]["subcategories"]):
                    errors.append(f"review entry {f!r}: missing must name a subcategory that is not a row, not folded "
                                  "and not foundation (fail the row it is folded into instead)")
    return errors


def folded_problems(rows: list, inp: dict, rules: dict) -> list[str]:
    """`folded` (optional on a row): subcategories whose content this row also covers, because the drafter merged them
    into it. Each must be a mapped-function subcategory that is not foundation, not a row of its own, folded once."""
    rows = [r for r in rows if isinstance(r, dict)]
    own, errors, where = {r.get("subcategory") for r in rows}, [], {}
    for n, r in enumerate(rows, 1):
        folded = r.get("folded", [])
        if not isinstance(folded, list):
            errors.append(f"row {n}: folded must be a list of subcategory ids")
            continue
        for sid in folded:
            sub = inp["subs"].get(sid)
            if sub is None or sub["function"] not in rules["functions"] or sid in rules["foundation"]["subcategories"]:
                errors.append(f"row {n}: folded {sid!r} is not a MAP, MEASURE or MANAGE subcategory an area can map")
            elif sid in own:
                errors.append(f"row {n}: folded {sid} is also a row of its own; keep one")
            elif sid in where:
                errors.append(f"row {n}: folded {sid} is already folded into {where[sid]}")
            else:
                where[sid] = r.get("subcategory")
    return errors


REVIEW_KINDS = ("row", "missing", "note")


def store_mapping(data, inp, m: dict, review) -> tuple[Path, str]:
    failing, missing, notes = {}, [], []
    for f in review or []:
        entry = {"function": f["function"], "subcategory": f["subcategory"], "reason": str(f["reason"]).strip()[:500]}
        kind = f.get("kind", "row")
        if kind == "row":
            failing.setdefault((f["function"], f["subcategory"]), []).append(entry["reason"])
        else:
            (missing if kind == "missing" else notes).append(entry)
    rows = []
    for r in data["rows"]:
        why = failing.get((r["function"], r["subcategory"]))
        rows.append({**r, "status": "needs_human_review" if why else "pass", "decided_by": "agent",
                     **({"review_reason": "; ".join(why)[:500]} if why else {})})
    doc = load_json(AI_MAPPING, "mapping.json") if AI_MAPPING.is_file() else {"areas": {}}
    rows, no_question, kept, removed = keep_human_decisions(rows, data.get("no_question", []),
                                                           doc["areas"].get(data["area"]), inp)
    merged = {"area": data["area"], "no_question": no_question,
              "rows": [{k: r[k] for k in ("function", "subcategory", "cis_refs", "impact", "why", "folded") if k in r}
                       for r in rows]}
    problems = validate_mapping(merged, inp, m, None) if kept else []
    if problems:   # a person's earlier decision no longer fits the current rules: they decide, not the script
        print("[record_ai_bank] ERROR: merged with the rows a person decided, the area breaks the rules; nothing "
              "stored. Fix those lines in mapping.xlsx (sheet_io.py import mapping), then record again:\n  - "
              + "\n  - ".join(problems), file=sys.stderr)
        sys.exit(1)
    own = {r["subcategory"] for r in rows}
    missing = [x for x in missing if x["subcategory"] not in own and x["subcategory"] not in removed]
    doc["description"] = ("AI RMF mapping: per AI area, rows of AI RMF function -> subcategory, CIS safeguards that prove "
                          "it, impact. Drafted and evaluated by agents (prompts/ai_rmf_mapping_*.md), recorded by "
                          "record_ai_bank.py mapping, reviewed by a person. Model: AI_RMF_Mapping_Sheet_Design.md.")
    doc["areas"][data["area"]] = {
        "recorded_on": date.today().isoformat(), "inputs": mapping_input_hashes(inp, data["area"]),
        "rows": rows, "no_question": no_question, **({"missing": missing} if missing else {}),
        **({"notes": notes} if notes else {}), **({"removed_by_human": removed} if removed else {})}
    doc["areas"] = {a: doc["areas"][a] for a in m["areas"] if a in doc["areas"]}   # ai_areas.json order
    AI_MAPPING.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    review_n = sum(1 for r in rows if r["status"] != "pass")
    reached, unreached = mapping_coverage(doc, inp, m["rules"])
    return AI_MAPPING, (f"{data['area']}: {len(rows)} rows ({review_n} need human review"
                        + (f"; {len(missing)} missing rows to decide" if missing else "")
                        + (f"; {len(notes)} evaluator notes" if notes else "")
                        + (f"; {kept} human decisions kept" if kept else "") + "); mapping has "
                        f"{len(doc['areas'])} of {len(m['areas'])} areas, {len(unreached)} subcategories not reached yet")


def keep_human_decisions(rows: list, no_question: list, prev: dict | None, inp: dict) -> tuple[list, list, int, list]:
    """A re-drafted area keeps what a person decided in the review sheet: rows decided_by human replace the agent's row
    on the same subcategory (or are added), and subcategories the person removed (removed_by_human) stay removed.
    Returns (rows, no_question, human decisions kept, removed list)."""
    if not prev:
        return rows, no_question, 0, []
    human = {r["subcategory"]: r for r in prev["rows"] if r.get("decided_by") == "human"}
    removed = [sid for sid in prev.get("removed_by_human", []) if sid not in human]
    out = [r for r in rows if r["subcategory"] not in human and r["subcategory"] not in removed] + list(human.values())
    for i, r in enumerate(out):   # a subcategory the person decided is no longer folded into an agent row
        if set(r.get("folded", [])) & set(human):
            out[i] = {k: v for k, v in r.items() if k != "folded"}
            if [f for f in r["folded"] if f not in human]:
                out[i]["folded"] = [f for f in r["folded"] if f not in human]
    out.sort(key=lambda r: list(inp["subs"]).index(r["subcategory"]))
    fns = {r["function"] for r in out}
    kept = len(human) + sum(1 for r in rows if r["subcategory"] in removed)
    return out, [q for q in no_question if q["function"] not in fns], kept, removed


def mapping_input_hashes(inp: dict, area_id: str) -> dict:
    """What a recorded area was built from: its own row of the AI areas sheet (`area`), the whole sheet and the rules
    (both reach the drafter: other areas' covers, candidates, foundation), and the sources."""
    row = next((a for a in load_json(AI_AREAS, "ai_areas.json")["ai_areas"] if a["id"] == area_id), None)
    return {"area": hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16],
            "ai_areas": audit.sha(AI_AREAS), "rules": audit.sha(AI_MAPPING_RULES),
            "playbook": inp["core"]["source_sha256_16"],
            "guides": {g: s["sha256_16"] for g, s in inp["sg_doc"]["sources"].items()}}


def mapping_freshness(entry: dict, area_id: str, inp: dict) -> str:
    """current, recheck (only the rules or other areas changed: `revalidate` can clear it without an agent) or redraft
    (the area's own row or the sources changed). An entry recorded before the area hash existed can only be rechecked
    if the whole AI areas sheet is unchanged."""
    rec, now = entry.get("inputs") or {}, mapping_input_hashes(inp, area_id)
    if rec == now:
        return "current"
    if rec.get("playbook") != now["playbook"] or rec.get("guides") != now["guides"]:
        return "redraft"
    if rec.get("area", None if rec.get("ai_areas") == now["ai_areas"] else "unknown") not in (None, now["area"]):
        return "redraft"
    return "recheck"


def revalidate(inp: dict, m: dict) -> tuple[dict, list[str], int]:
    """(the mapping, one line per area that is not current, areas stamped current). Checks only; decides nothing: the
    recorded rows are kept as they are, and an area that breaks the current rules stays stale."""
    doc = load_json(AI_MAPPING, "mapping.json") if AI_MAPPING.is_file() else {"areas": {}}
    lines, cleared = [], 0
    foundation = set(m["rules"]["foundation"]["subcategories"])
    for area_id, entry in doc["areas"].items():
        state = mapping_freshness(entry, area_id, inp)
        if state == "current":
            continue
        if state == "redraft":
            lines.append(f"{area_id}: its own row in the AI areas sheet or the sources changed; re-draft it")
            continue
        draft = {"area": area_id, "no_question": entry.get("no_question", []),
                 "rows": [{k: r[k] for k in ("function", "subcategory", "cis_refs", "impact", "why", "folded") if k in r}
                          for r in entry["rows"]]}
        problems = validate_mapping(draft, inp, m, None)
        if problems:
            lines += [f"{area_id}: {p}" for p in problems]
            continue
        if entry.get("missing"):   # a missing finding on a subcategory that is now foundation no longer applies
            entry["missing"] = [x for x in entry["missing"] if x["subcategory"] not in foundation]
            if not entry["missing"]:
                del entry["missing"]
        entry["inputs"] = mapping_input_hashes(inp, area_id)
        cleared += 1
    if cleared:
        AI_MAPPING.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    return doc, lines, cleared


def mapping_coverage(doc: dict, inp: dict, rules: dict) -> tuple[set, list]:
    """(subcategories reached by an area row, a fold or the foundation, the ones not reached, in AI RMF order). A folded
    subcategory is reached: it is asked and scored through the row it is folded into."""
    reached = {s for a in doc.get("areas", {}).values() for r in a["rows"] for s in [r["subcategory"], *r.get("folded", [])]}
    reached |= set(foundation_subcategories(rules, inp))
    return reached, [s for s in inp["subs"] if s not in reached]


# ── the review sheet (sheet_io.py export / import mapping) ──────────────────

ROW_FIELDS = ("cis_refs", "impact", "why", "status", "folded")   # what a person can change on a row in the sheet


def mapping_sheet_rows(doc: dict, inp: dict, m: dict) -> tuple[list[dict], list[list[str]]]:
    """(one line per recorded area x mapped-function subcategory, the Coverage sheet as rows of cells). Script only:
    the outcome and safeguard titles are looked up, nothing is decided."""
    mapped_subs = [s for s in inp["subs"].values() if s["function"] in m["rules"]["functions"]
                   and s["subcategory_id"] not in m["rules"]["foundation"]["subcategories"]]
    lines = []
    for area_id, entry in doc.get("areas", {}).items():
        by_sub = {r["subcategory"]: r for r in entry["rows"]}
        into = {f: r["subcategory"] for r in entry["rows"] for f in r.get("folded", [])}
        missing = {x["subcategory"]: x["reason"] for x in entry.get("missing", [])}
        notes = {}
        for x in entry.get("notes", []):
            notes.setdefault(x["subcategory"], []).append(x["reason"])
        for s in mapped_subs:
            r = by_sub.get(s["subcategory_id"])
            refs = r["cis_refs"] if r else []
            note = ("Also covers " + ", ".join(r["folded"]) + " (folded into this row by the drafter)."
                    if r and r.get("folded") else
                    f"Folded into {into[s['subcategory_id']]}: that row covers this subcategory's content."
                    if s["subcategory_id"] in into else "")
            lines.append({
                **({"_comments": {"why": note}} if note else {}),
                "area": area_id, "area_name": m["areas"].get(area_id, {}).get("name", ""), "function": s["function"],
                "subcategory": s["subcategory_id"], "outcome": s["outcome"], "mapped": bool(r),
                "why": r["why"] if r else "", "cis_refs": refs,
                "cis_titles": "; ".join(f"{g}: {inp['safeguards'][g]['title']}" for g in refs if g in inp["safeguards"]),
                "impact": r["impact"] if r else [],
                "status": r["status"] if r else "needs_human_review" if s["subcategory_id"] in missing else "",
                "review_reason": " ".join(filter(None, [
                    r.get("review_reason", "") if r else "",
                    f"Missing: {missing[s['subcategory_id']]}" if s["subcategory_id"] in missing else "",
                    *[f"Note: {t}" for t in notes.get(s["subcategory_id"], [])]])),
                "decided_by": r["decided_by"] if r else "", "folded": r.get("folded", []) if r else [],
            })
    drafted = doc.get("areas", {})
    reach = {(a, r["subcategory"]) for a in drafted for r in drafted[a]["rows"]}
    folds = {(a, f): r["subcategory"] for a in drafted for r in drafted[a]["rows"] for f in r.get("folded", [])}
    foundation = set(foundation_subcategories(m["rules"], inp))
    coverage = [["Function", "Subcategory", "What it means (Playbook outcome)", "Areas reaching it",
                 *[a if a in drafted else f"{a} (not drafted)" for a in m["areas"]]]]
    for s in inp["subs"].values():   # all 72, in AI RMF order; every AI area as a column
        if s["subcategory_id"] in foundation:
            coverage.append([s["function"], s["subcategory_id"], s["outcome"], "foundation (asked once, by role)",
                             *["" for _ in m["areas"]]])
            continue
        cells = ["yes" if (a, s["subcategory_id"]) in reach else f"folded into {folds[(a, s['subcategory_id'])]}"
                 if (a, s["subcategory_id"]) in folds else "" for a in m["areas"]]
        coverage.append([s["function"], s["subcategory_id"], s["outcome"], sum(1 for c in cells if c), *cells])
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
        elif ln["subcategory"] in m["rules"]["foundation"]["subcategories"]:
            problems.append(f"row {n}: {ln['subcategory']} is foundation (asked once for the organisation), not per area")
        elif ln["subcategory"] in sheet.setdefault(ln["area"], {}):
            problems.append(f"row {n}: {ln['area']} / {ln['subcategory']} appears twice")
        else:
            sheet[ln["area"]][ln["subcategory"]] = dict(ln, function=sub["function"], line=n)
    new_doc = json.loads(json.dumps(doc))
    for area_id, subs in sheet.items():
        recorded = {r["subcategory"]: r for r in areas[area_id]["rows"]}
        problems += [f"{area_id} / {sid}: the line is missing from the sheet; set Mapped to no instead of deleting it"
                     for sid in recorded if sid not in subs]
        rows, removed = [], set(areas[area_id].get("removed_by_human", []))
        missing = {x["subcategory"]: x for x in areas[area_id].get("missing", [])}
        for sid, ln in subs.items():
            if not ln["mapped"]:
                if sid in recorded:
                    changed += 1
                    removed.add(sid)
                    if ln["folded"]:
                        problems.append(f"{area_id}: sheet row {ln['line']} ({sid}): {', '.join(ln['folded'])} "
                                        "folded into it would be lost; clear 'Folded into this row' (or map them on their "
                                        "own lines) before setting Mapped to no")
                elif sid in missing and ln["status"] != "needs_human_review":
                    changed += 1   # the person decided the evaluator's missing row is not needed
                    missing.pop(sid)
                continue
            if missing.pop(sid, None):
                changed += 1
            removed.discard(sid)
            new = {"function": ln["function"], "subcategory": sid, "cis_refs": ln["cis_refs"], "impact": ln["impact"],
                   "why": ln["why"], "status": ln["status"] or "pass"}
            if ln["folded"]:
                new["folded"] = ln["folded"]
            old = recorded.get(sid)
            if old and all(new.get(k, []) == (str(old[k]).strip() if k == "why" else old.get(k, [])) for k in ROW_FIELDS):
                rows.append(old)
            else:
                changed += 1
                rows.append({**new, "decided_by": "human"})
        rows.sort(key=lambda r: list(inp["subs"]).index(r["subcategory"]))
        own = {r["subcategory"] for r in rows}
        for i, r in enumerate(rows):   # a subcategory the person maps on its own is no longer folded into another row
            if set(r.get("folded", [])) & own:
                rows[i] = {k: v for k, v in r.items() if k != "folded"}
                if [f for f in r["folded"] if f not in own]:
                    rows[i]["folded"] = [f for f in r["folded"] if f not in own]
        with_rows = {r["function"] for r in rows}
        draft = {"area": area_id, "rows": [{k: r[k] for k in ("function", "subcategory", "cis_refs", "impact", "why",
                                                              "folded") if k in r} for r in rows],
                 "no_question": [q for q in areas[area_id].get("no_question", []) if q["function"] not in with_rows]}
        at = {f"row {k}:": f"sheet row {subs[r['subcategory']]['line']} ({r['subcategory']}):"
              for k, r in enumerate(rows, 1)}
        problems += [f"{area_id}: " + next((e.replace(a, b, 1) for a, b in at.items() if e.startswith(a + " ")), e)
                     for e in validate_mapping(draft, inp, m, None)]
        new_doc["areas"][area_id].update(rows=rows, no_question=draft["no_question"])
        new_doc["areas"][area_id].pop("missing", None)
        if missing:
            new_doc["areas"][area_id]["missing"] = list(missing.values())
        new_doc["areas"][area_id].pop("removed_by_human", None)
        if removed:
            new_doc["areas"][area_id]["removed_by_human"] = sorted(removed, key=list(inp["subs"]).index)
    return new_doc, problems, changed


def words_match(quote, text: str) -> bool:
    """True if quote is the start of text (at least three words, ignoring case and punctuation)."""
    norm = lambda s: re.findall(r"[a-z0-9]+", str(s).lower())   # noqa: E731
    q = norm(quote or "")
    return len(q) >= 3 and norm(text)[:len(q)] == q


QUESTION_CHECKS = [str(n) for n in range(1, 10)]   # prompts/ai_rmf_question_evaluator.md, checks 1-9
TURN_TWO_RECHECKS = {"6", "7"}   # an unchanged question that passed turn 1 may newly fail only these (a rewrite clashes)


def verdict_failures(gen: dict, verdicts, name: str) -> dict[tuple[str, int], list[tuple[str, str]]]:
    """{(subcategory, question number): [(check, reason), ...]} of the failures in an evaluator verdict file, which must
    hold a verdict on every check for every question of `gen`, quoting the start of that question and of no other
    (`starts_with`), and a
    `complete` verdict per subcategory (number 0)."""
    if not isinstance(verdicts, list):
        sys.exit(f"[record_ai_bank] ERROR: {name} must be a JSON list of verdicts")
    want = {(sid, n) for sid, v in gen.items() for n in range(len(v["questions"]) + 1)}
    got, problems = {}, []
    for v in verdicts:
        key = (v.get("subcategory_id"), v.get("question_number")) if isinstance(v, dict) else None
        if key not in want or key in got:
            problems.append(f"unexpected or repeated verdict {key}")
            continue
        keys = ["complete"] if key[1] == 0 else QUESTION_CHECKS
        checks, reasons = v.get("checks"), v.get("reasons") or {}
        starts = [n for n, q in enumerate(gen[key[0]]["questions"], 1)
                  if words_match(v.get("starts_with"), q["question_text"])]
        if key[1] and starts != [key[1]]:
            problems.append(f"{key}: starts_with {v.get('starts_with')!r} must be the start of question {key[1]} and of no "
                            f"other (matches {starts})")
            continue
        if not isinstance(checks, dict) or sorted(checks) != sorted(keys) or \
                not set(checks.values()) <= {"pass", "fail", "n/a"}:
            problems.append(f"{key}: checks must be exactly {keys}, each pass, fail or n/a")
            continue
        fails = [c for c in keys if checks[c] == "fail"]
        if not all(str(reasons.get(c, "")).strip() for c in fails):
            problems.append(f"{key}: every failed check needs a reason")
            continue
        got[key] = [(c, str(reasons[c]).strip()) for c in fails]
    problems += [f"no verdict for {k}" for k in sorted(want - set(got), key=str)]
    if problems:
        sys.exit(f"[record_ai_bank] ERROR: {name}:\n  - " + "\n  - ".join(problems))
    return {k: f for k, f in got.items() if f}


def assemble(gen1: Path, eval1: Path, gen2: Path | None, eval2: Path | None, out: Path) -> str:
    """The file `questions` records, from generator output and evaluator verdicts. No judgement: a subcategory
    passes iff the last evaluation fails nothing in it."""
    g1 = load_json(gen1, "generator output")
    if not isinstance(g1, dict):
        sys.exit("[record_ai_bank] ERROR: generator output has the wrong JSON type")
    if bool(gen2) != bool(eval2):
        sys.exit("[record_ai_bank] ERROR: --gen2 and --eval2 go together")
    f1 = verdict_failures(g1, load_json(eval1, "evaluator verdicts"), "turn 1 verdicts")
    final, last_fail, turns = {sid: v["questions"] for sid, v in g1.items()}, f1, {sid: 1 for sid in g1}
    if gen2:
        g2 = load_json(gen2, "revision output")
        if not isinstance(g2, dict) or set(g2) - set(final):
            sys.exit("[record_ai_bank] ERROR: revision output must be an object of turn 1 subcategories")
        f2 = verdict_failures(g2, load_json(eval2, "second evaluation"), "turn 2 verdicts")
        flipped = [f"{sid} Q{n} check {c}" for (sid, n), fails in f2.items() if n
                   and g2[sid]["questions"][n - 1] in g1[sid]["questions"]
                   and (sid, g1[sid]["questions"].index(g2[sid]["questions"][n - 1]) + 1) not in f1
                   for c, _ in fails if c not in TURN_TWO_RECHECKS]
        if flipped:
            sys.exit("[record_ai_bank] ERROR: turn 2 verdicts fail questions that are unchanged and passed turn 1 (only "
                     f"checks {sorted(TURN_TWO_RECHECKS)} may change): {', '.join(flipped)}")
        for sid, v in g2.items():
            final[sid], turns[sid] = v["questions"], 2
        last_fail = {k: f for k, f in f1.items() if k[0] not in g2} | f2
    failing: dict[str, list[str]] = {}
    for (sid, n), fails in sorted(last_fail.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        failing.setdefault(sid, []).append(
            f"Q{n}: " + "; ".join(r if c == "complete" else f"check {c}: {r}" for c, r in fails))
    result = {}
    for sid in final:
        entry = {"status": "needs_human_review" if sid in failing else "pass", "turns": turns[sid], "questions": final[sid]}
        if sid in failing:
            entry["reason"] = "; ".join(failing[sid])[:500]
        result[sid] = entry
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return f"{len(result)} subcategories: {len(result) - len(failing)} pass, {len(failing)} need human review → {out.name}"

# ── storing ─────────────────────────────────────────────────────────────────

def store(mode: str, data: dict, args, inp: dict) -> tuple[Path, str]:
    """Write the validated data to its store; returns (store path, one-line summary)."""
    today = date.today().isoformat()
    if mode == "questions":
        path = AI_BANKS / f"question_bank_ai_rmf_{args.bank}.json"
        AI_BANKS.mkdir(parents=True, exist_ok=True)
        bank = load_json(path, path.name) if path.is_file() else {"bank": args.bank, "subcategories": {}}
        ctx = question_context(inp)
        for sid, entry in data.items():
            bank["subcategories"][sid] = {
                "status": entry["status"], "turns": entry["turns"],
                **({"review_reason": entry["reason"]} if entry.get("reason") else {}),
                **(rows_record(ctx, sid) if args.bank == "areas" else {}),
                "questions": entry["questions"]}
        bank["subcategories"] = {sid: bank["subcategories"][sid] for sid in inp["subs"] if sid in bank["subcategories"]}
        bank.update({"description": BANK_DESCRIPTION[args.bank], "built_on": today,
                     "playbook_sha256_16": inp["core"]["source_sha256_16"],
                     "guide_sha256_16": {g: s["sha256_16"] for g, s in inp["sg_doc"]["sources"].items()}})
        passed = sum(1 for e in bank["subcategories"].values() if e["status"] == "pass")
        review = len(bank["subcategories"]) - passed
        bank["summary"] = {"subcategories": len(bank["subcategories"]), "passed": passed, "needs_human_review": review,
                           "questions": sum(len(e["questions"]) for e in bank["subcategories"].values())}
        path.write_text(json.dumps(bank, indent=2, ensure_ascii=False))
        return path, (f"{args.bank} bank: recorded {len(data)} subcategories; bank has {passed} passed, {review} needing "
                      f"human review, {bank['summary']['questions']} questions")
    if mode == "notes-review":
        store_doc = load_json(CSF_IMPACT_NOTES, "ai_impact_notes.json")
        flagged: dict[str, list[str]] = {}
        for f in data:
            flagged.setdefault(f["subcategory_id"], []).append(f"{f['note']}: {str(f['reason']).strip()}")
        for sid, v in store_doc["notes"].items():
            if v.get("decided_by") == "human":
                continue
            v["status"] = "needs_human_review" if sid in flagged else "pass"
            v.pop("review_reason", None)
            if sid in flagged:
                v["review_reason"] = "; ".join(flagged[sid])[:500]
        CSF_IMPACT_NOTES.write_text(json.dumps(store_doc, indent=2, ensure_ascii=False))
        return CSF_IMPACT_NOTES, (f"notes reviewed: {len(flagged)} of {len(store_doc['notes'])} subcategories need human "
                                  "review")
    if mode == "notes":
        store_doc = load_json(CSF_IMPACT_NOTES, "ai_impact_notes.json") if CSF_IMPACT_NOTES.is_file() else {"notes": {}}
        for sid, v in data.items():
            e = store_doc["notes"].setdefault(sid, {})
            e.update(v)
            for k in ("status", "review_reason", "decided_by"):   # rewritten by an agent: to be reviewed again
                e.pop(k, None)
        store_doc["notes"] = dict(sorted(store_doc["notes"].items()))
        store_doc.update({
            "description": ("AI-world notes per CSF 2.0 subcategory. `exposure` is shown to every org; `use` only when AI is "
                            "in use (mcp_agentic when the client's AI areas include MCP / tools or agents, else base_rag). "
                            "Written by an agent from the CIS MCP and agents companion guides joined to CSF via the official "
                            "CIS v8.1 -> CSF 2.0 mapping, then reviewed. The Stage 2 XLS writer selects from the intake (AI in "
                            "use, AI areas)."),
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
        validate = {"questions": lambda d: (validate_questions(d, args.bank, inp, question_context(inp))
                                            + human_decided(d, args)),
                    "notes": validate_notes, "notes-review": validate_notes_review}[mode]
        store_fn, extra = (lambda d: store(mode, d, args, inp)), None
        log_name = f"{mode}_{args.bank}" if mode == "questions" else mode
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
    sub.add_parser("revalidate")

    for m in ("questions", "notes", "notes-review", "mapping"):
        p = sub.add_parser(m)
        if m == "questions":
            p.add_argument("bank", choices=AI_QUESTION_BANKS)
            p.add_argument("--replace-human", action="store_true",
                           help="overwrite subcategories a person decided in the review sheet (only when they agreed)")
        p.add_argument("file")
        if m == "mapping":
            p.add_argument("--review", help="the evaluator's last list of failures (rows stored as needs_human_review)")
        p.add_argument("--model", required=True, help="model id of the agent that produced the file")
        p.add_argument("--session")
        p.add_argument("--prompt", nargs="*", help="prompt file(s) the agent followed, relative to the repo root")
    args = ap.parse_args()

    if args.mode == "revalidate":
        inp = load_inputs()
        m = mapping_inputs(inp)
        ev = audit.begin(AI_BUILD / "audit.jsonl", "revalidate_mapping", {})
        _, lines, cleared = revalidate(inp, m)
        for ln in lines:
            print(f"[record_ai_bank] {ln}")
        line = f"revalidate: {cleared} areas checked against the current rules and stamped current; {len(lines)} problems"
        print(f"[record_ai_bank] {line}")
        ev.finish(inputs=[AI_AREAS, AI_MAPPING_RULES], outputs=[AI_MAPPING] if cleared else [], detail=line)
        sys.exit(1 if lines else 0)
    if args.mode == "assemble":
        ev = audit.begin(AI_BUILD / "audit.jsonl", "assemble_questions", {"gen1": args.gen1, "gen2": args.gen2})
        ins = [Path(p) for p in (args.gen1, args.eval1, args.gen2, args.eval2) if p]
        line = assemble(Path(args.gen1), Path(args.eval1), Path(args.gen2) if args.gen2 else None,
                        Path(args.eval2) if args.eval2 else None, Path(args.out))
        print(f"[record_ai_bank] {line}")
        ev.finish(inputs=ins, outputs=[Path(args.out)], detail=line)
        return
    record(args.mode, args)


if __name__ == "__main__":
    main()
