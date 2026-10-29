"""
Usage: .venv/bin/python ./scripts/build_ai_questions.py <run_dir>

Picks the AI RMF questions for one engagement from the two question banks. This script decides nothing: it reads
<run_dir>/ai_usage.json and filters the banks (data/ai/banks/question_bank_ai_rmf_<foundation|areas>.json) with the
policy in data/ai/scope_rules.json. Writes, per bank:

  <run_dir>/ai_scope.json                     the profile used, and per bank and subcategory what was picked and why
  <run_dir>/ai_questions_draft_<bank>.json    entries in the same shape as csf_questions_draft.json, so the assessor
                                              patch merge (record_judgements.py log --base --patch) works unchanged
  <run_dir>/ai_question_bank_used_<bank>.json snapshot of the bank used, so the run stays reproducible

ai_usage.json (written by intake.py):
{
  "ai_in_use": "none" | "some" | "unsure",
  "role": "consumer" | "producer" | "both" | null,           # asked when AI is in use
  "producer": {"built_on_existing_model": bool, "given_to_others": bool} | null,   # for producer or both
  "ai_areas": ["invisible_usage", "input", ...],             # the client's AI areas (data/ai/ai_areas.json ids)
  "engagement_flags": {"csf_assessment_done": bool, "iso27001_held": bool, "iso42001_held": bool},
  "captured_on": "YYYY-MM-DD"
}

A question is picked when
  roles           one of its roles is a role the client is asked as (scope_rules.json client_roles: none -> none;
                  unsure -> none, consumer; otherwise the role, both = consumer and producer)
  producer_flags  every flag it carries is true in the client's producer answers
  rows            (area questions) it covers a row of one of the client's AI areas
Each picked area question carries the names of the client's areas it covers; a question shared by several areas shows
them to the client as scope_rules.json covers_note. A subcategory with no picked question is left out (it does not
apply to this client). Every question is full_discovery for every client: the questions are about AI (an AI area, or
AI in the organisation), so they never repeat the general security the CSF sheet or ISO 27001 covers, and the
engagement flags change nothing here. Entries whose bank record is needs_human_review carry
the rules' review_flag as confidence_flag.

Errors (bad profile, missing bank) exit 1 and write nothing. Requires the banks built by /build-ai-bank.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import AI_AREAS, AI_CORE, AI_EVIDENCE_PROMPTS, AI_QUESTION_RULES, AI_SCOPE_RULES, ai_bank_path  # noqa: E402
from options import AI_FUNCTION_ORDER, AI_QUESTION_BANKS  # noqa: E402
from ai_bank_common import core_subcategories  # noqa: E402
import audit  # noqa: E402


# ── the profile ─────────────────────────────────────────────────────────────

def validate_profile(p: dict, areas: list[str], qrules: dict, rules: dict) -> list[str]:
    if not isinstance(p, dict):
        return ["ai_usage.json must be a JSON object"]
    if p.get("ai_in_use") not in ("none", "some", "unsure"):
        return ["ai_in_use must be none, some or unsure"]
    errors = []
    role = p.get("role")
    if p["ai_in_use"] == "some" and role not in ("consumer", "producer", "both"):
        errors.append("role must be consumer, producer or both when AI is in use")
    if p["ai_in_use"] != "some" and role is not None:
        errors.append("role is asked only when AI is in use")
    flags = list(qrules["producer_flags"])
    prod = p.get("producer")
    if role in ("producer", "both"):
        if not isinstance(prod, dict) or set(prod) != set(flags) or not all(isinstance(v, bool) for v in prod.values()):
            errors.append(f"producer must be an object of booleans with exactly {flags} for a producer")
    elif prod is not None:
        errors.append("producer is only given for role producer or both")
    got = p.get("ai_areas")
    if not isinstance(got, list) or not set(got) <= set(areas):
        errors.append(f"ai_areas must be a list from {areas}")
    eflags = p.get("engagement_flags")
    known = set(rules["engagement_flags"]["flags"])
    if not isinstance(eflags, dict) or set(eflags) != known or not all(isinstance(x, bool) for x in eflags.values()):
        errors.append(f"engagement_flags must be an object of booleans with exactly {sorted(known)}")
    return errors


def client_roles(p: dict, rules: dict) -> list[str]:
    return rules["client_roles"][p["role"] if p["ai_in_use"] == "some" else p["ai_in_use"]]


def usage_note(p: dict, names: dict, rules: dict) -> str:
    note = rules["usage_notes"][p["ai_in_use"]]
    return note.format(role=p.get("role"), areas=", ".join(names[a] for a in p["ai_areas"]))


# ── selection ───────────────────────────────────────────────────────────────

def pick(bank: str, rec: dict, roles: list, flags: list, areas: list) -> list[tuple[dict, list[str]]]:
    """(question, the client's rows it covers) for every question of one bank entry the client gets."""
    out = []
    for q in rec["questions"]:
        if not set(q["roles"]) & set(roles) or not set(q["producer_flags"]) <= set(flags):
            continue
        rows = [r for r in q.get("rows", []) if rec["rows"][r]["area"] in areas] if bank == "areas" else []
        if bank == "areas" and not rows:
            continue
        out.append((q, rows))
    return out


def evidence_for(bank: str, rec: dict, rows: list, evidence: dict, impact_order: list) -> str:
    if bank == "foundation":
        return evidence["foundation"]
    impacts = {i for r in rows for i in rec["rows"][r]["impact"]}
    return " ".join(evidence["by_impact"][i] for i in impact_order if i in impacts) or evidence["default"]


def build_entry(bank: str, sid: str, rec: dict, picked: list, outcome: str, names: dict, rules: dict,
                evidence: dict, impact_order: list, note: str) -> dict:
    questions = []
    for q, rows in picked:
        client_areas = [names[rec["rows"][r]["area"]] for r in rows]
        questions.append({
            "question_text": q["question_text"],
            "source_reference": "AI RMF Playbook: " + "; ".join(q["playbook_refs"]),
            "cis_refs": q["cis_refs"],
            "applies_to": (rules["foundation_label"] if bank == "foundation" else
                           rules["covers_note"].format(areas="; ".join(client_areas)) if len(q["rows"]) > 1
                           else client_areas[0]),
            "rows": rows,
            "evidence_prompt": evidence_for(bank, rec, rows, evidence, impact_order),
        })
    return {
        "subcategory_id": sid, "bank": bank, "function": sid.split()[0], "outcome": outcome,
        "question_type": rules["default_type"], "questions": questions,
        "evidence_prompt": questions[0]["evidence_prompt"],
        "scope_reason": "", "usage_note": note,
        "confidence_flag": rules["review_flag"] if rec["status"] == "needs_human_review" else "",
        "assessor_note": None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    ev = audit.begin(audit.run_log(run_dir), "build_ai_questions", {})
    usage_path = run_dir / "ai_usage.json"
    inputs = [usage_path, AI_SCOPE_RULES, AI_QUESTION_RULES, AI_EVIDENCE_PROMPTS, AI_AREAS, AI_CORE]
    for p in inputs:
        if not p.is_file():
            ev.fail(f"[build_ai_questions] ERROR: {p} not found" + (
                " (capture the AI usage profile first)" if p == usage_path else
                " (run parse_ai_rmf_sources.py)" if p == AI_CORE else ""), inputs)
    rules = json.loads(AI_SCOPE_RULES.read_text())
    qrules = json.loads(AI_QUESTION_RULES.read_text())
    evidence = json.loads(AI_EVIDENCE_PROMPTS.read_text())
    names = {a["id"]: a["name"] for a in json.loads(AI_AREAS.read_text())["ai_areas"]}
    outcomes = {s["subcategory_id"]: s["outcome"] for s in core_subcategories(json.loads(AI_CORE.read_text()))}
    profile = json.loads(usage_path.read_text())

    errors = validate_profile(profile, list(names), qrules, rules)
    if errors:
        ev.reject(errors, "ai_usage.json", inputs)

    roles = client_roles(profile, rules)
    flags = [f for f, v in (profile.get("producer") or {}).items() if v]
    note = usage_note(profile, names, rules)

    scope, drafts, summary = {}, {}, []
    for bank in AI_QUESTION_BANKS:
        bank_file = ai_bank_path(bank)
        if not bank_file.is_file():
            ev.fail(f"[build_ai_questions] ERROR: {bank_file} not found. Run /build-ai-bank first.", inputs)
        inputs.append(bank_file)
        out, entries = [], []
        for sid, rec in json.loads(bank_file.read_text())["subcategories"].items():
            picked = pick(bank, rec, roles, flags, profile["ai_areas"])
            covered = sorted({rec["rows"][r]["area"] for _, rows in picked for r in rows})
            reason = rules["reason"].format(roles=", ".join(roles),
                                            areas=f"; areas {', '.join(names[a] for a in covered)}" if covered else "")
            entries.append({"subcategory_id": sid, "questions": len(picked), "reason": reason if picked else
                            "No question of this subcategory applies to the client's role, flags or AI areas"})
            if picked:
                e = build_entry(bank, sid, rec, picked, outcomes[sid], names, rules, evidence, list(qrules["impacts"]),
                                note)
                e["scope_reason"] = reason
                out.append(e)
        out.sort(key=lambda q: (AI_FUNCTION_ORDER.get(q["function"], 99), list(outcomes).index(q["subcategory_id"])))
        scope[bank], drafts[bank] = entries, (out, bank_file)
        summary.append(f"{bank}: {len(out)} subcategories, {sum(len(q['questions']) for q in out)} questions")

    outputs = [run_dir / "ai_scope.json"]
    outputs[0].write_text(json.dumps({
        "ai_in_use": profile["ai_in_use"], "role": profile.get("role"), "roles_asked_as": roles,
        "producer_flags": flags, "ai_areas": profile["ai_areas"], "usage_note": note,
        "banks": scope}, indent=2, ensure_ascii=False))
    for bank, (out, bank_file) in drafts.items():
        draft, used = run_dir / f"ai_questions_draft_{bank}.json", run_dir / f"ai_question_bank_used_{bank}.json"
        draft.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        shutil.copy2(bank_file, used)
        outputs += [draft, used]
    detail = f"ai_in_use={profile['ai_in_use']}; roles {', '.join(roles)}; " + "; ".join(summary)
    print(f"[build_ai_questions] {detail} → {run_dir}", file=sys.stderr)
    ev.finish(inputs=inputs, outputs=outputs, detail=detail)


if __name__ == "__main__":
    main()
