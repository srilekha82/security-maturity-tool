"""Helpers shared by the AI RMF bank scripts (prepare_ai_bank.py, record_ai_bank.py, ai_pilot.py). Not a script."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import AI_CATEGORIES, AI_CORE, AI_SAFEGUARDS, REPO_ROOT  # noqa: E402
from options import AI_BANK_NAMES as BANKS  # noqa: E402,F401  (re-exported for the three scripts)

# The prompts each agent step follows. `candidates` (generator and evaluator) is also what the pilot acceptance is tied to.
DEFAULT_PROMPTS = {
    "applicability": ["prompts/ai_rmf_applicability_judge.md"],
    "crosswalk": ["prompts/ai_rmf_cis_linker.md"],
    "candidates": ["prompts/ai_rmf_question_generator.md", "prompts/ai_rmf_question_evaluator.md"],
    "notes": ["prompts/ai_impact_notes_writer.md"],
}


def load_json(path: Path, what: str):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"[ai_bank] ERROR: cannot read {what} ({path}): {e}")


def load_inputs() -> dict:
    """Reference data every validator and every prepare mode needs. Fails early with a pointer to the step that creates it."""
    for p, step in ((AI_CORE, "parse_ai_rmf_sources.py"), (AI_SAFEGUARDS, "parse_ai_rmf_sources.py")):
        if not p.is_file():
            sys.exit(f"[ai_bank] ERROR: {p} not found. Run {step} first.")
    core = load_json(AI_CORE, "ai_rmf_core.json")
    sg = load_json(AI_SAFEGUARDS, "cis_ai_safeguards.json")
    cats = load_json(AI_CATEGORIES, "question_categories.json")
    return {
        "core": core, "subs": {s["subcategory_id"]: s for s in core["subcategories"]},
        "safeguards": {r["id"]: r for r in sg["safeguards"]}, "sg_doc": sg,
        "cats": cats, "enums": cats["enums"],
        "bank_cats": {b: {c["id"]: c for c in cats["banks"][b]["categories"]} for b in BANKS},
    }


def rel(path: Path) -> str:
    """Path relative to the repo root when inside it (always the case outside tests)."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
