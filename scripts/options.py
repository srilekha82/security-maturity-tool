"""Shared facts, read once from the data files. Scripts import these names; none keeps its own copy.

Domains, certifications, the intake menus and the question types come from data/common/intake_options.json. The function
order of each framework comes from that track's scope_rules.json, the AI bank names from the AI scope_rules.json.
Nothing here is decided in code: change a fact by editing the JSON."""

import json
from pathlib import Path

from paths import AI_QUESTION_RULES, AI_SCOPE_RULES, INTAKE_OPTIONS, SCOPE_RULES

_common = json.loads(INTAKE_OPTIONS.read_text())

DOMAINS = [d["value"] for d in _common["domains"]]
DOMAIN_LABELS = {d["value"]: d["label"] for d in _common["domains"]}
WEIGHT_KEY = {d["value"]: d["weight_key"] for d in _common["domains"]}     # key of the domain in domain_weights.json
CERTS = [c["value"] for c in _common["certs"] if c["value"] != "none"]     # certifications with a crosswalk
CERT_LABELS = {c["value"]: c["label"] for c in _common["certs"] if c["value"] != "none"}
CERT_FILES = {c["value"]: c["file"] for c in _common["certs"] if c["value"] != "none"}
SEVERITY_ORDER = _common["severity_order"]       # question types, least to most demanding
QUESTION_TYPES = set(SEVERITY_ORDER)
_menus = {"domains": _common["domains"], "certs": _common["certs"]}
INTAKE_QUESTIONS = [{**q, "options": _menus[q["options"]] if isinstance(q["options"], str) else q["options"]}
                    for q in _common["questions"]]     # menus with their options spelled out


def load_intake(run_dir) -> dict:
    """<run_dir>/intake.json (written by intake.py): org, date, domain, certs. Exits with a pointer if it is missing."""
    path = Path(run_dir) / "intake.json"
    if not path.is_file():
        raise SystemExit(f"ERROR: {path} not found. Run scripts/intake.py first (it records org, domain and certifications).")
    return json.loads(path.read_text())


def _rank(order: list) -> dict:
    return {f: i for i, f in enumerate(order)}


CSF_FUNCTION_ORDER = _rank(json.loads(SCOPE_RULES.read_text())["function_order"])          # GV, ID, ...
_ai_rules = json.loads(AI_SCOPE_RULES.read_text())
AI_FUNCTION_ORDER = _rank(_ai_rules["function_order"])        # GOVERN, MAP, ...
AI_QUESTION_BANKS = tuple(json.loads(AI_QUESTION_RULES.read_text())["banks"])   # foundation, areas
