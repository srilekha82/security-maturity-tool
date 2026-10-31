"""
Usage: .venv/bin/python ./scripts/build_questions.py <run_dir>

  run_dir  — path to run folder containing csf_scope.json and intake.json (the domain picks the bank; the certifications
             word the gap/confirmatory questions)

Reads question_bank_{domain}.json and csf_scope.json. Picks N candidates per subcategory
based on question_type, frames each question, and writes csf_questions_draft.json.

Inputs:
  <run_dir>/csf_scope.json, <run_dir>/intake.json
  data/csf/banks/question_bank_{domain}.json
  data/csf/csf2_core.json

Output:
  <run_dir>/csf_questions_draft.json
  <run_dir>/csf_question_bank_used.json   snapshot of the bank used, so the run stays reproducible
                                      after the shared bank is rebuilt
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import CSF_CORE, EVIDENCE_PROMPTS, SCOPE_RULES, bank_path  # noqa: E402
from options import CERT_LABELS, CSF_FUNCTION_ORDER, DOMAIN_LABELS, load_intake  # noqa: E402
import audit  # noqa: E402

RULES = json.loads(SCOPE_RULES.read_text())  # policy and wording live in scope_rules.json
MAX_QUESTIONS, FRAMES = RULES["max_questions"], RULES["frames"]
EVIDENCE = json.loads(EVIDENCE_PROMPTS.read_text())  # content lives in evidence_prompts.json



def cert_phrase(certs: list) -> str:
    """'ISO 27001 certification', 'PCI DSS certification', 'ISO 27001 and PCI DSS certifications'."""
    labels = [CERT_LABELS[c] for c in certs if c in CERT_LABELS]
    if not labels:
        return "certification"
    return " and ".join(labels) + (" certifications" if len(labels) > 1 else " certification")


def frame_question(base_text: str, question_type: str, mapped_controls: list, certs: list = ()) -> str:
    """The bank question, worded for the certifications held (the wording is in scope_rules.json `frames`)."""
    frame = FRAMES.get(question_type)
    if frame is None:
        return base_text
    controls = (", ".join(c.replace("Annex A Controls: ", "") for c in mapped_controls)
                if mapped_controls else FRAMES["no_controls"])
    return frame.format(cert=f"Your {cert_phrase(list(certs))}", controls=controls, text=base_text)


def evidence_prompt(subcategory_id: str) -> str:
    category = subcategory_id.rsplit("-", 1)[0]
    return EVIDENCE["by_category"].get(category, EVIDENCE["default"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", help="Path to run folder containing csf_scope.json and intake.json")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    intake = load_intake(run_dir)
    domain, certs = intake["domain"], intake["certs"]
    client = (f"Sector: {DOMAIN_LABELS.get(domain, domain)}. Certifications held: "
              f"{', '.join(CERT_LABELS.get(c, c) for c in certs if c in CERT_LABELS) or 'none'}.")  # for the reviewer
    ev = audit.begin(audit.run_log(run_dir), "build_questions", {"domain": domain, "certs": certs})
    bank_file = bank_path(domain)
    core_path = CSF_CORE

    if not bank_file.exists():
        ev.fail(f"[build_questions] ERROR: {bank_file} not found. Run /build-csf-bank first.")

    bank = json.loads(bank_file.read_text())
    scope = json.loads((run_dir / "csf_scope.json").read_text())
    csf_core = json.loads(core_path.read_text())

    sub_text = {s["subcategory_id"]: s["subcategory_text"] for s in csf_core["subcategories"]}

    output = []
    skipped = []
    no_bank_match = []

    for entry in scope:
        sid = entry["subcategory_id"]
        qtype = entry["question_type"]
        fn = sid.split(".")[0]

        if qtype == "skip":
            skipped.append(sid)
            continue

        bank_entry = bank["questions"].get(sid, {})
        candidates = bank_entry.get("candidates", [])
        n = MAX_QUESTIONS[qtype]
        selected = candidates[:n]

        if not selected:
            no_bank_match.append(sid)
            selected = [{
                "question_text": FRAMES["fallback_question"].format(outcome=sub_text.get(sid, sid)),
                "cset_question_id": None,
                "source": "csf2_core_fallback",
            }]

        framed = []
        for candidate in selected:
            framed.append({
                "question_text": frame_question(
                    candidate["question_text"], qtype, entry.get("mapped_controls", []), certs
                ),
                "source_reference": (
                    f"CSET: {candidate['cset_question_id']}"
                    if candidate.get("cset_question_id") else "NIST CSF 2.0"
                ),
                "cset_question_id": candidate.get("cset_question_id"),
            })

        confidence_flag = (
            "LOW — assessor verification required"
            if str(entry.get("confidence", "")).lower() == "low" or qtype == "confirmatory"
            else ""
        )

        output.append({
            "subcategory_id": sid,
            "function": fn,
            "outcome": sub_text.get(sid, ""),
            "question_type": qtype,
            "questions": framed,
            "evidence_prompt": evidence_prompt(sid),
            "scope_reason": entry.get("reason", ""),
            "client": client,
            "confidence_flag": confidence_flag,
            "assessor_note": None,
        })

    output.sort(key=lambda q: (CSF_FUNCTION_ORDER.get(q["function"], 99), q["subcategory_id"]))

    shutil.copy2(bank_file, run_dir / "csf_question_bank_used.json")
    out_path = run_dir / "csf_questions_draft.json"
    out_path.write_text(json.dumps(output, indent=2))

    by_type = {}
    for q in output:
        by_type[q["question_type"]] = by_type.get(q["question_type"], 0) + 1

    total_q = sum(len(e["questions"]) for e in output)
    print(f"[build_questions] {len(output)} subcategories, {total_q} questions → {out_path}", file=sys.stderr)
    print(f"[build_questions] Skipped: {len(skipped)} | No bank match (fallback used): {len(no_bank_match)}", file=sys.stderr)
    print(f"[build_questions] By type: {by_type}", file=sys.stderr)
    ev.finish(inputs=[bank_file, run_dir / "csf_scope.json", core_path, SCOPE_RULES, EVIDENCE_PROMPTS],
              outputs=[out_path, run_dir / "csf_question_bank_used.json"],
              detail=f"{len(output)} subcategories, {total_q} questions, fallback for {len(no_bank_match)}; by type {by_type}",
              bank_cset_commit=bank.get("cset_commit"), bank_built_on=bank.get("built_on"))


if __name__ == "__main__":
    main()
