"""Helpers shared by the AI RMF bank scripts (prepare_ai_bank.py, record_ai_bank.py, ai_pilot.py, build_ai_questions.py).
Not a script."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import AI_CORE, AI_SAFEGUARDS, REPO_ROOT  # noqa: E402

# The prompts each agent step follows. `questions` (generator and evaluator) is also what the pilot acceptance is tied to.
DEFAULT_PROMPTS = {
    "questions": ["prompts/ai_rmf_question_generator.md", "prompts/ai_rmf_question_evaluator.md"],
    "evidence": ["prompts/ai_rmf_evidence_writer.md", "prompts/ai_rmf_evidence_evaluator.md"],
    "notes": ["prompts/ai_impact_notes_writer.md"],
    "notes-review": ["prompts/ai_impact_notes_evaluator.md"],
    "mapping": ["prompts/ai_rmf_mapping_drafter.md", "prompts/ai_rmf_mapping_evaluator.md"],
}


def load_json(path: Path, what: str):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"[ai_bank] ERROR: cannot read {what} ({path}): {e}")


def row_id(area: str, subcategory: str) -> str:
    """The id of one mapping row (AI area x subcategory) in the area question bank."""
    return f"{area}|{subcategory}"


def area_roles(area: dict, qrules: dict, scope_rules: dict) -> list[str]:
    """Roles an area question may carry: the area's applies_to, plus `none` for areas every client gets."""
    roles = list(qrules["area_roles"]["applies_to"][area["applies_to"]])
    return (["none"] if area["id"] in scope_rules["ai_area_rules"]["always"] else []) + roles


def core_subcategories(core: dict) -> list[dict]:
    """Every subcategory of ai_rmf_core.json, flattened from its functions (GOVERN, MAP, MEASURE, MANAGE order)."""
    return [s for f in core["functions"] for s in f["subcategories"]]


def load_inputs() -> dict:
    """Reference data every validator and every prepare mode needs. Fails early with a pointer to the step that creates it."""
    for p, step in ((AI_CORE, "parse_ai_rmf_sources.py"), (AI_SAFEGUARDS, "parse_ai_rmf_sources.py")):
        if not p.is_file():
            sys.exit(f"[ai_bank] ERROR: {p} not found. Run {step} first.")
    core = load_json(AI_CORE, "ai_rmf_core.json")
    sg = load_json(AI_SAFEGUARDS, "cis_ai_safeguards.json")
    return {
        "core": core, "subs": {s["subcategory_id"]: s for s in core_subcategories(core)},
        "safeguards": {r["id"]: r for r in sg["safeguards"]}, "sg_doc": sg,
    }


def always_controls(rules: dict) -> list[int]:
    return sorted(int(n) for n in rules["always_cis_controls"]["controls"])


def check_mapping_rules(rules: dict, inp: dict) -> list[str]:
    """Problems in mapping_rules.json against the parsed CIS guides: every control number of an area (its own and the
    always ones) must exist in each guide the area uses; the always controls' names must match the guides' titles; a
    required check's cis_control must be an always control (so every area can cite it); every AI RMF function is either
    mapped per area (functions) or foundation, never both; a required check names subcategories of mapped functions;
    a foundation subcategory is a real subcategory of a mapped function and no required check names it."""
    controls = inp["sg_doc"]["controls"]   # keyed "<guide>-<number>"
    errors = []
    mapped, foundation = rules["functions"], rules["foundation"]["functions"]
    core_fns = [f["id"] for f in inp["core"]["functions"]]
    if set(mapped) & set(foundation) or sorted(mapped + foundation) != sorted(core_fns):
        errors.append(f"functions {mapped} and foundation {foundation} must split the AI RMF functions {core_fns} between them")
    extra = rules["foundation"]["subcategories"]
    bad = [s for s in extra if s not in inp["subs"] or inp["subs"][s]["function"] not in mapped]
    if bad:
        errors.append(f"foundation subcategories {bad}: must be subcategories of a mapped function ({mapped})")
    for check in rules["required_checks"]:
        bad = [s for s in check["any_of"] if s not in inp["subs"] or inp["subs"][s]["function"] not in mapped]
        if bad:
            errors.append(f"required check {check['name']!r}: {bad} are not subcategories of a mapped function")
        if set(check["any_of"]) & set(extra):
            errors.append(f"required check {check['name']!r}: names foundation subcategories {sorted(set(check['any_of']) & set(extra))}")
    for n, name in rules["always_cis_controls"]["controls"].items():
        for g in {g for k, v in rules["area_cis"].items() if k != "description" for g in v["guides"]}:
            c = controls.get(f"{g}-{n}")
            if c is None:
                errors.append(f"always_cis_controls {n}: no control {n} in the {g} guide")
            elif c["title"].strip().lower() != name.strip().lower():
                errors.append(f"always_cis_controls {n}: named {name!r}, but the {g} guide calls it {c['title']!r}")
    for area, v in rules["area_cis"].items():
        if area == "description":
            continue
        for g in v["guides"]:
            missing = [n for n in v["controls"] if f"{g}-{n}" not in controls]
            if missing:
                errors.append(f"area_cis {area}: controls {missing} are not in the {g} guide")
    for check in rules["required_checks"]:
        if "cis_control" in check and check["cis_control"] not in always_controls(rules):
            errors.append(f"required check {check['name']!r}: cis_control {check['cis_control']} is not an always control")
    return errors


def foundation_subcategories(rules: dict, inp: dict) -> list[str]:
    """Subcategories asked once for the organisation, never mapped to an AI area: all of the foundation functions, plus
    the single subcategories listed in foundation.subcategories."""
    extra = set(rules["foundation"]["subcategories"])
    return [sid for sid, s in inp["subs"].items() if s["function"] in rules["foundation"]["functions"] or sid in extra]


def area_rules(rules: dict, area_id: str) -> dict:
    """The mapping_rules.json entries that apply to one AI area: its candidate CIS controls and guides, its required checks."""
    cis = rules["area_cis"].get(area_id)
    if cis is None:
        sys.exit(f"[ai_bank] ERROR: AI area {area_id!r} has no entry in mapping_rules.json area_cis")
    return {"controls": sorted(set(cis["controls"]) | set(always_controls(rules))), "guides": cis["guides"],
            "required_checks": [c for c in rules["required_checks"] if c["areas"] == "all" or area_id in c["areas"]]}


def area_candidates(inp: dict, rules: dict, area_id: str) -> list[dict]:
    """The CIS safeguards a mapping row of this AI area may cite: its controls (plus the always ones) in its guides."""
    r = area_rules(rules, area_id)
    return [s for s in inp["sg_doc"]["safeguards"] if s["guide"] in r["guides"] and s["control"] in r["controls"]]


def rel(path: Path) -> str:
    """Path relative to the repo root when inside it (always the case outside tests)."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
