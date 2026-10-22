"""
Usage: .venv/bin/python ./scripts/prepare_ai_bank.py applicability
       .venv/bin/python ./scripts/prepare_ai_bank.py crosswalk
       .venv/bin/python ./scripts/prepare_ai_bank.py batch <producer|consumer> (--ids ID ... | --category "GOVERN 1" | --all)
                                                           [--missing] [--tag NAME]
       .venv/bin/python ./scripts/prepare_ai_bank.py mapping --area ID

Writes the compact file an agent reads in the AI RMF bank build, so agents never read the PDFs. Script only: it decides
nothing and records nothing (agent output goes through record_ai_bank.py).

  applicability   -> data/ai/bank_build/applicability_pending.json
  crosswalk       -> data/ai/bank_build/crosswalk_pending.json
  batch           -> data/ai/bank_build/batch_<bank>_<tag>.json   (generator / evaluator input)
                     --missing keeps only subcategories not yet recorded in that bank
  mapping         -> data/ai/bank_build/mapping_input_<area>.json   (mapping drafter / evaluator input)
                     one AI area (data/ai/ai_areas.json), the four AI RMF functions with every subcategory's outcome and
                     shortened suggested actions, the area's candidate CIS safeguards (data/ai/mapping_rules.json
                     area_cis) and the required checks that apply to it
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import (AI_APPLICABILITY, AI_AREAS, AI_BANKS, AI_BUILD, AI_CATEGORIES, AI_CORE, AI_CROSSWALK_CIS,  # noqa: E402
                   AI_MAPPING_RULES, AI_SAFEGUARDS)
from ai_bank_common import (BANKS, area_candidates, area_rules, check_mapping_rules, load_inputs, load_json,  # noqa: E402
                            rel)

MAX_ACTIONS, ACTION_CHARS, AI_TEXT_CHARS = 6, 220, 260   # how much Playbook and CIS text the mapping drafter sees
import audit  # noqa: E402


def trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def category_view(inp: dict, bank: str) -> list[dict]:
    return [{"id": c["id"], "name": c["name"], "topic": c["topic"], "covers": c["covers"]}
            for c in inp["bank_cats"][bank].values()]


def prepare_applicability(inp: dict) -> Path:
    out = AI_BUILD / "applicability_pending.json"
    out.write_text(json.dumps({
        "definitions": inp["cats"]["definitions"]["roles"],
        "categories": {b: category_view(inp, b) for b in BANKS},
        "items": [{"subcategory_id": s["subcategory_id"], "outcome": s["outcome"],
                   "suggested_actions": [trunc(a, 160) for a in s["suggested_actions"]]}
                  for s in inp["core"]["subcategories"]],
    }, indent=2, ensure_ascii=False))
    return out


def prepare_crosswalk(inp: dict) -> Path:
    out = AI_BUILD / "crosswalk_pending.json"
    out.write_text(json.dumps({
        "items": [{"subcategory_id": s["subcategory_id"], "outcome": s["outcome"]} for s in inp["core"]["subcategories"]],
        "safeguards": [{"id": r["id"], "title": r["title"]} for r in inp["sg_doc"]["safeguards"] if r["has_ai_guidance"]],
    }, indent=2, ensure_ascii=False))
    return out


def prepare_batch(inp: dict, bank: str, ids: list[str], category: str | None, everything: bool, tag: str | None,
                  missing_only: bool = False) -> Path:
    if not AI_APPLICABILITY.is_file():
        sys.exit("[prepare_ai_bank] ERROR: data/ai/applicability.json not found. Run the applicability pass first.")
    app = load_json(AI_APPLICABILITY, "applicability.json")["subcategories"]
    applicable = [sid for sid in inp["subs"] if app[sid][bank]]
    if ids:
        unknown = [i for i in ids if i not in inp["subs"]]
        notapp = [i for i in ids if i in inp["subs"] and i not in applicable]
        if unknown or notapp:
            sys.exit(f"[prepare_ai_bank] ERROR: unknown ids {unknown}; not applicable to the {bank} bank: {notapp}")
        chosen = ids
    elif category:
        chosen = [s for s in applicable if inp["subs"][s]["category"] == category]
    elif everything:
        chosen = applicable
    else:
        sys.exit("[prepare_ai_bank] ERROR: give --ids, --category or --all")
    if missing_only:
        bank_path = AI_BANKS / f"question_bank_ai_rmf_{bank}.json"
        done = set(load_json(bank_path, bank_path.name)["subcategories"]) if bank_path.is_file() else set()
        chosen = [s for s in chosen if s not in done]
    if not chosen:
        sys.exit("[prepare_ai_bank] ERROR: no applicable subcategories selected" + (" (all already recorded)" if missing_only else ""))
    xw = load_json(AI_CROSSWALK_CIS, "airmf_to_cis.json")["links"] if AI_CROSSWALK_CIS.is_file() else {}
    items = []
    for sid in chosen:
        s = inp["subs"][sid]
        items.append({
            "subcategory_id": sid, "outcome": s["outcome"], "actions_preamble": s["actions_preamble"],
            "suggested_actions": s["suggested_actions"],
            "categories": [{"id": c, "topic": inp["bank_cats"][bank][c]["topic"],
                            "covers": inp["bank_cats"][bank][c]["covers"]} for c in app[sid][bank]],
            "cis_safeguards": [{"id": g, "title": inp["safeguards"][g]["title"],
                                "ai_applicability": trunc(inp["safeguards"][g]["ai_applicability"], 500)}
                               for g in xw.get(sid, []) if g in inp["safeguards"]],
        })
    name = tag or (category.replace(" ", "_") if category else "ids" if ids else "all")
    out = AI_BUILD / f"batch_{bank}_{name}.json"
    out.write_text(json.dumps({"bank": bank, "enums": inp["enums"], "definitions": inp["cats"]["definitions"],
                               "items": items}, indent=2, ensure_ascii=False))
    return out


def prepare_mapping(inp: dict, area_id: str) -> Path:
    areas = {a["id"]: a for a in load_json(AI_AREAS, "ai_areas.json")["ai_areas"]}
    if area_id not in areas:
        sys.exit(f"[prepare_ai_bank] ERROR: unknown AI area {area_id!r} (known: {sorted(areas)})")
    rules = load_json(AI_MAPPING_RULES, "mapping_rules.json")
    problems = check_mapping_rules(rules, inp)
    if problems:
        sys.exit("[prepare_ai_bank] ERROR: mapping_rules.json does not match the CIS guides:\n  - " + "\n  - ".join(problems))
    r = area_rules(rules, area_id)
    subs = {f: [] for f in rules["functions"]}
    for s in inp["core"]["subcategories"]:
        subs[s["function"]].append({"id": s["subcategory_id"], "outcome": s["outcome"],
                                    "actions": [trunc(a, ACTION_CHARS) for a in s["suggested_actions"][:MAX_ACTIONS]]})
    out = AI_BUILD / f"mapping_input_{area_id}.json"
    out.write_text(json.dumps({
        "area": areas[area_id],
        "functions": rules["functions"],
        "rules": {"max_rows": rules["max_rows_per_area"], "min_why_chars": rules["min_why_chars"],
                  "required_checks": r["required_checks"], "org_wide": rules["org_wide"]["subcategories"]},
        "subcategories": subs,
        "cis_candidates": [{"id": s["id"], "title": s["title"], "lowest_ig": (s["ig"] or ["-"])[0],
                            "ai_text": trunc(s["ai_applicability"], AI_TEXT_CHARS)}
                           for s in area_candidates(inp, rules, area_id)],
    }, indent=2, ensure_ascii=False))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["applicability", "crosswalk", "batch", "mapping"])
    ap.add_argument("bank", nargs="?", choices=BANKS)
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--category")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--missing", action="store_true", help="only subcategories not yet recorded in the bank")
    ap.add_argument("--tag")
    ap.add_argument("--area", help="mapping: the AI area id")
    args = ap.parse_args()

    ev = audit.begin(AI_BUILD / "audit.jsonl", f"prepare_{args.what}",
                     {"bank": args.bank, "ids": args.ids, "category": args.category, "all": args.all, "area": args.area})
    inp = load_inputs()
    if args.what == "applicability":
        out = prepare_applicability(inp)
    elif args.what == "crosswalk":
        out = prepare_crosswalk(inp)
    elif args.what == "mapping":
        if not args.area:
            ev.fail("[prepare_ai_bank] ERROR: mapping needs --area ID")
        out = prepare_mapping(inp, args.area)
        ev.finish(inputs=[AI_CORE, AI_SAFEGUARDS, AI_AREAS, AI_MAPPING_RULES], outputs=[out], detail=f"prepared {out.name}")
        print(f"[prepare_ai_bank] wrote {rel(out)} ({out.stat().st_size // 1024} KB)")
        return
    else:
        if not args.bank:
            ev.fail("[prepare_ai_bank] ERROR: batch needs a bank (producer|consumer)")
        out = prepare_batch(inp, args.bank, args.ids, args.category, args.all, args.tag, args.missing)
    print(f"[prepare_ai_bank] wrote {rel(out)} ({out.stat().st_size // 1024} KB)")
    ev.finish(inputs=[AI_CORE, AI_SAFEGUARDS, AI_CATEGORIES], outputs=[out], detail=f"prepared {out.name}")


if __name__ == "__main__":
    main()
