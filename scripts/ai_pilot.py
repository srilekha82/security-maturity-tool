"""
Usage: .venv/bin/python ./scripts/ai_pilot.py accept [--note TEXT]

The pilot gate of the AI RMF bank build: the one human decision that lets a missing or incomplete bank be rebuilt without
asking (like a CSF bank).

  accept   the user's decision that the pilot is good. Needs at least one recorded subcategory in each bank. Writes
           data/ai/bank_build/pilot_accepted.json with the hashes of the generator and evaluator prompts. Editing either
           prompt makes the acceptance stale: a new pilot is needed before the next rebuild.

pilot_status() is what check_freshness.py reads to report the `pilot` stage.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import AI_BANKS, AI_BUILD, AI_PILOT, REPO_ROOT  # noqa: E402
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    pk = sub.add_parser("accept")
    pk.add_argument("--note")
    args = ap.parse_args()

    ev = audit.begin(AI_BUILD / "audit.jsonl", "accept_pilot", {"note": args.note}, actor="human")
    line = accept_pilot(args.note)
    print(f"[ai_pilot] {line}")
    ev.finish(inputs=[REPO_ROOT / p for p in DEFAULT_PROMPTS["candidates"]], outputs=[AI_PILOT], detail=line)


if __name__ == "__main__":
    main()
