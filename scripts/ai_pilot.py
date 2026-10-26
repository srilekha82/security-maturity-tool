"""
Usage: .venv/bin/python ./scripts/ai_pilot.py accept [--note TEXT]
       .venv/bin/python ./scripts/ai_pilot.py accept-mapping [--note TEXT]

The human gates of the AI RMF bank build.

  accept-mapping  the user's decision that the AI RMF mapping (data/ai/mapping.json) is good, after reviewing it in
           data/ai/authoring/mapping.xlsx. Needs every AI area recorded, built from the current sources, AI areas and
           mapping rules, no row still needs_human_review and no sheet edit left unimported. Subcategories no area
           reaches are allowed and listed in the acceptance. Writes data/ai/bank_build/mapping_accepted.json with a hash
           of the mapping's content; any later change to the mapping makes the acceptance stale.

  accept   the user's decision that the pilot is good. Needs at least one recorded subcategory in each bank. Writes
           data/ai/bank_build/pilot_accepted.json with the hashes of the generator and evaluator prompts. Editing either
           prompt makes the acceptance stale: a new pilot is needed before the next rebuild.

pilot_status() and mapping_status() are what check_freshness.py reads to report the `pilot` and `mapping` stages.
"""

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import (AI_BANKS, AI_BUILD, AI_CORE, AI_MAPPING, AI_MAPPING_ACCEPTED, AI_MAPPING_XLSX, AI_PILOT,  # noqa: E402
                   AI_SAFEGUARDS, REPO_ROOT)
from ai_bank_common import BANKS, DEFAULT_PROMPTS, load_json  # noqa: E402
import audit  # noqa: E402


def pilot_status(pilot_file: Path | None = None) -> tuple[bool, str]:
    """(current?, text) for the `pilot` stage: accepted, and the generator and evaluator prompts unchanged since."""
    pilot_file = pilot_file or AI_PILOT
    pilot = json.loads(pilot_file.read_text()) if pilot_file.is_file() else None
    if pilot is None:
        return False, "missing (run /build-ai-bank and review the pilot)"
    same = pilot["prompts"] == {p: audit.sha(REPO_ROOT / p) for p in DEFAULT_PROMPTS["candidates"]}
    return same, (f"accepted {pilot['accepted_on']}" if same
                  else "stale (generator or evaluator prompt changed since the pilot was accepted)")


def accept_pilot(note: str | None) -> str:
    """Record that the user accepted the pilot. Needs at least one recorded subcategory in each bank."""
    recorded = {}
    for bank in BANKS:
        path = AI_BANKS / f"question_bank_ai_rmf_{bank}.json"
        recorded[bank] = len(load_json(path, path.name)["subcategories"]) if path.is_file() else 0
    if not all(recorded.values()):
        sys.exit(f"[ai_pilot] ERROR: run the pilot first; recorded subcategories per bank: {recorded}")
    prompts = DEFAULT_PROMPTS["candidates"]
    AI_PILOT.write_text(json.dumps({
        "accepted_on": date.today().isoformat(), "note": note, "recorded": recorded,
        "prompts": {p: audit.sha(REPO_ROOT / p) for p in prompts}}, indent=2, ensure_ascii=False))
    return f"pilot accepted ({recorded}); the generator and evaluator prompts are now locked to this acceptance"


def mapping_hash(doc: dict) -> str:
    """Hash of what the mapping decides (rows, no_question, removals per area); not the sheet hash or dates."""
    keep = {a: {k: e.get(k) for k in ("rows", "no_question", "removed_by_human")} for a, e in doc["areas"].items()}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def mapping_problems(doc: dict | None) -> tuple[list[str], list[str]]:
    """(what stops the mapping from being accepted, subcategories no area reaches)."""
    if doc is None:
        return ["missing (draft the areas: /build-ai-bank, Mapping)"], []
    if not (AI_CORE.is_file() and AI_SAFEGUARDS.is_file()):
        return ["cannot check (run parse_ai_rmf_sources.py first)"], []
    import record_ai_bank as R
    from sheet_io import sheet_status
    inp = R.load_inputs()
    m = R.mapping_inputs(inp)
    problems = []
    missing = [a for a in m["areas"] if a not in doc["areas"]]
    if missing:
        problems.append(f"incomplete ({len(doc['areas'])} of {len(m['areas'])} AI areas; missing: {', '.join(missing)})")
    now = R.mapping_input_hashes(inp)
    stale = [a for a, e in doc["areas"].items() if e.get("inputs") != now]
    if stale:
        problems.append(f"stale (sources, AI areas or mapping rules changed since drafted: {', '.join(stale)})")
    review = sum(1 for e in doc["areas"].values() for r in e["rows"] if r.get("status") != "pass")
    if review:
        problems.append(f"{review} rows need human review (Status in {AI_MAPPING_XLSX.name})")
    missing = sum(len(e.get("missing", [])) for e in doc["areas"].values())
    if missing:
        problems.append(f"{missing} missing rows to decide (Mapped = no lines with Status needs_human_review in "
                        f"{AI_MAPPING_XLSX.name}: map them, or set Status to pass)")
    if AI_MAPPING_XLSX.is_file() and not sheet_status("mapping", AI_MAPPING_XLSX, AI_MAPPING)[0]:
        problems.append(f"{AI_MAPPING_XLSX.name} edited but not imported (sheet_io.py import mapping)")
    return problems, R.mapping_coverage(doc, inp, m["rules"])[1]


def mapping_status(mapping_file: Path | None = None, accepted_file: Path | None = None) -> tuple[bool, str]:
    """(current?, text) for the `mapping` stage: complete, current, reviewed and accepted as it is now."""
    mapping_file, accepted_file = mapping_file or AI_MAPPING, accepted_file or AI_MAPPING_ACCEPTED
    doc = json.loads(mapping_file.read_text()) if mapping_file.is_file() else None
    problems, unreached = mapping_problems(doc)
    tail = f"; {len(unreached)} subcategories reached by no area" if doc else ""
    if problems:
        return False, "; ".join(problems) + tail
    accepted = json.loads(accepted_file.read_text()) if accepted_file.is_file() else None
    if accepted is None:
        return False, f"not accepted (review {AI_MAPPING_XLSX.name}, then ai_pilot.py accept-mapping){tail}"
    if accepted["mapping_sha"] != mapping_hash(doc):
        return False, f"changed since accepted on {accepted['accepted_on']} (accept again){tail}"
    return True, f"accepted {accepted['accepted_on']} ({len(doc['areas'])} areas{tail})"


def accept_mapping(note: str | None) -> str:
    """Record that the user accepted the mapping as it is now."""
    doc = json.loads(AI_MAPPING.read_text()) if AI_MAPPING.is_file() else None
    problems, unreached = mapping_problems(doc)
    if problems:
        sys.exit("[ai_pilot] ERROR: the mapping cannot be accepted yet:\n  - " + "\n  - ".join(problems))
    rows = sum(len(e["rows"]) for e in doc["areas"].values())
    AI_MAPPING_ACCEPTED.write_text(json.dumps({
        "accepted_on": date.today().isoformat(), "note": note, "areas": len(doc["areas"]), "rows": rows,
        "unreached": unreached, "mapping_sha": mapping_hash(doc)}, indent=2, ensure_ascii=False))
    return (f"mapping accepted ({len(doc['areas'])} areas, {rows} rows"
            + (f"; reached by no area: {', '.join(unreached)}" if unreached else "") + ")")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    pk = sub.add_parser("accept")
    pk.add_argument("--note")
    mk = sub.add_parser("accept-mapping")
    mk.add_argument("--note")
    args = ap.parse_args()

    if args.mode == "accept-mapping":
        ev = audit.begin(AI_BUILD / "audit.jsonl", "accept_mapping", {"note": args.note}, actor="human")
        line = accept_mapping(args.note)
        print(f"[ai_pilot] {line}")
        ev.finish(inputs=[AI_MAPPING], outputs=[AI_MAPPING_ACCEPTED], detail=line)
        return
    ev = audit.begin(AI_BUILD / "audit.jsonl", "accept_pilot", {"note": args.note}, actor="human")
    line = accept_pilot(args.note)
    print(f"[ai_pilot] {line}")
    ev.finish(inputs=[REPO_ROOT / p for p in DEFAULT_PROMPTS["candidates"]], outputs=[AI_PILOT], detail=line)


if __name__ == "__main__":
    main()
