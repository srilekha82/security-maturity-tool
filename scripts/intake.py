"""
Usage: .venv/bin/python ./scripts/intake.py menu [KEY]
       .venv/bin/python ./scripts/intake.py write --org NAME --domain N --certs "N N" --ai-in-use N
              [--ai-usage "N N" --ai-components "N N"] --csf-assessment-done N --iso42001-held N
              [--date YYYY-MM-DD] [--runs-dir DIR] [--replace]

The engagement intake, as numbered choices (the menus live in data/common/intake_options.json).

  menu   prints the numbered menus, or one of them. Ask the user one question at a time and take the number(s) typed.
  write  turns the typed numbers into values (a lookup, nothing is interpreted), checks them, and writes in a new
         run folder <runs>/<Org>_<date>/:
           intake.json     org, date, domain, certs     read by compute_scope, build_questions and check_freshness
           ai_usage.json   the AI usage profile (no org)  read by build_ai_questions
         iso27001_held is derived from the certifications, so the two cannot disagree.
         "How do you use AI?" (ai_usage) and "What does your AI include?" (ai_components) list AI area ids from
         data/ai/ai_areas.json; they are asked only when AI in use is "some" (option 2), may be left blank, and giving
         them otherwise is rejected. ai_areas() turns the answers into the client's AI areas, adding the automatic ones
         from scope_rules.json ai_area_rules. Until question selection works on AI areas, the old profile fields (role,
         rung, usage contexts, hosts_model) are also written, worked out from the areas (scope_rules.json legacy_profile).
         Exit 1 with the problems listed, writing nothing, if a number is not on its menu, a single-choice question gets
         several, "None" is combined with a certification, the profile breaks a rule of
         build_ai_questions.validate_profile, or the run folder already has an intake.json (same org and date):
         --replace overwrites it, and the later files in that folder (scope, drafts) are then stale.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import AI_AREAS, AI_CATEGORIES, AI_SCOPE_RULES, RUNS  # noqa: E402
from options import INTAKE_QUESTIONS  # noqa: E402
from build_ai_questions import validate_profile  # noqa: E402
import audit  # noqa: E402

BY_KEY = {q["key"]: q for q in INTAKE_QUESTIONS}


def applies(q: dict, values: dict) -> bool:
    """A question is asked unless its ask_if names an answer the user did not give."""
    return all(values.get(k) == v for k, v in q.get("ask_if", {}).items())


def print_menu(q: dict) -> None:
    note = "".join(f"  (ask only if {k} is option {[o['value'] for o in BY_KEY[k]['options']].index(v) + 1})"
                   for k, v in q.get("ask_if", {}).items())
    print(f"{q['key']}: {q['prompt']}{note}")
    for i, o in enumerate(q["options"], 1):
        print(f"  {i}. {o['label']}")


def pick(q: dict, text: str) -> tuple[list, list[str]]:
    """(values chosen, problems) for the numbers typed against one menu."""
    tokens = [t for t in re.split(r"[\s,]+", (text or "").strip()) if t]
    if not tokens and q.get("optional"):
        return [], []
    if not tokens:
        return [], [f"{q['key']}: no answer given"]
    errors, chosen = [], []
    for t in tokens:
        if not t.isdigit() or not 1 <= int(t) <= len(q["options"]):
            errors.append(f"{q['key']}: {t!r} is not a number on the menu (1 to {len(q['options'])})")
        elif q["options"][int(t) - 1]["value"] not in chosen:
            chosen.append(q["options"][int(t) - 1]["value"])
    if not q["multi"] and len(chosen) > 1:
        errors.append(f"{q['key']}: pick one option")
    if q["key"] == "certs" and "none" in chosen and len(chosen) > 1:
        errors.append("certs: 'None' cannot be combined with a certification")
    return chosen, errors


def run_folder_name(org: str, day: str) -> str:
    return f"{re.sub(r'[^A-Za-z0-9._-]+', '_', org.strip()).strip('_')}_{day}"


def ai_areas(gate: str, usage: list, components: list, rules: dict, order: list) -> list[str]:
    """The client's AI areas, in ai_areas.json order: the ones ticked, plus the automatic ones (ai_area_rules)."""
    r = rules["ai_area_rules"]
    got = set(r["always"])
    if gate != "none":
        got |= set(r["any_ai"]) | set(usage) | set(components)
        for area, adds in r["with"].items():
            if area in got:
                got |= set(adds)
    return [a for a in order if a in got]


def legacy_fields(gate: str, areas: list, rules: dict) -> dict:
    """The old profile fields the current question filter reads, worked out from the AI areas (removed in step 4)."""
    if gate != "some":
        return {"role": None, "rung": None, "usage_contexts": [], "modifiers": [], "hosts_model": False}
    lp = rules["legacy_profile"]
    others = [a for a in areas if a in lp["usage_contexts"]]
    role = ("both" if others else "producer") if "producer" in areas else "consumer"
    rung = next((rung for area, rung in lp["rung"] if area in areas), "base")
    return {"role": role, "rung": rung, "usage_contexts": [lp["usage_contexts"][a] for a in others],
            "modifiers": [], "hosts_model": "hosting" in areas}


def write(args) -> None:
    errors, values = [], {}
    if not re.search(r"[A-Za-z0-9]", args.org):
        errors.append("org: a name with at least one letter or digit is needed")
    for q in INTAKE_QUESTIONS:
        given = getattr(args, q["key"])
        if not applies(q, values):
            if given:
                errors.append(f"{q['key']}: not asked unless {q['ask_if']}; leave it out")
            continue
        chosen, errs = pick(q, given)
        errors += errs
        values[q["key"]] = chosen if q["multi"] else (chosen[0] if chosen else None)
    if errors:
        fail(errors)

    gate = values["ai_in_use"]
    certs = [c for c in values["certs"] if c != "none"]
    rules = json.loads(AI_SCOPE_RULES.read_text())
    order = [a["id"] for a in json.loads(AI_AREAS.read_text())["ai_areas"]]
    areas = ai_areas(gate, values.get("ai_usage", []), values.get("ai_components", []), rules, order)
    profile = {
        "ai_in_use": gate,
        "ai_areas": areas,
        **legacy_fields(gate, areas, rules),
        "engagement_flags": {"csf_assessment_done": values["csf_assessment_done"],
                             "iso27001_held": "iso27001" in certs, "iso42001_held": values["iso42001_held"]},
        "captured_on": args.date,
    }
    enums = json.loads(AI_CATEGORIES.read_text())["enums"]
    problems = validate_profile(profile, enums, rules)
    if problems:
        fail(problems)

    run_dir = Path(args.runs_dir) / run_folder_name(args.org, args.date)
    if (run_dir / "intake.json").is_file() and not args.replace:
        fail([f"{run_dir} already has an intake. Use --replace to overwrite it (scope and drafts already in that folder "
              "would then be out of date: re-run /csf-questionnaire and /ai-questionnaire), or use another --date."])
    ev = audit.begin(audit.run_log(run_dir), "intake", {"org": args.org, "date": args.date})
    run_dir.mkdir(parents=True, exist_ok=True)
    intake = {"org": args.org.strip(), "date": args.date, "domain": values["domain"], "certs": certs}
    outputs = []
    for name, doc in (("intake.json", intake), ("ai_usage.json", profile)):
        (run_dir / name).write_text(json.dumps(doc, indent=2, ensure_ascii=False))
        outputs.append(run_dir / name)
    detail = f"{values['domain']}; certs {', '.join(certs) or 'none'}; AI {gate}: {', '.join(areas)}"
    print(f"[intake] {run_dir}: {detail} → intake.json, ai_usage.json")
    ev.finish(outputs=outputs, detail=detail)


def fail(problems: list[str]) -> None:
    audit.report_problems("intake", problems, "the answers")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    m = sub.add_parser("menu")
    m.add_argument("key", nargs="?", choices=list(BY_KEY))
    w = sub.add_parser("write")
    w.add_argument("--org", required=True, help="organisation name (free text)")
    for q in INTAKE_QUESTIONS:
        w.add_argument(f"--{q['key'].replace('_', '-')}", dest=q["key"], help=q["prompt"])
    w.add_argument("--date", default=date.today().isoformat(), help="run date (default: today)")
    w.add_argument("--runs-dir", default=str(RUNS))
    w.add_argument("--replace", action="store_true", help="overwrite the intake of an existing run folder")
    args = parser.parse_args()

    if args.mode == "menu":
        for q in ([BY_KEY[args.key]] if args.key else INTAKE_QUESTIONS):
            print_menu(q)
    else:
        write(args)


if __name__ == "__main__":
    main()
