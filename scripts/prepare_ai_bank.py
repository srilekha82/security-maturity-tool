"""
Usage: .venv/bin/python ./scripts/prepare_ai_bank.py batch <areas|foundation> (--ids ID ... | --function MAP | --all)
                                                           [--missing] [--tag NAME]
       .venv/bin/python ./scripts/prepare_ai_bank.py mapping --area ID

Writes the compact file an agent reads in the AI RMF bank build, so agents never read the PDFs. Script only: it decides
nothing and records nothing (agent output goes through record_ai_bank.py).

  batch areas     -> data/ai/bank_build/batch_areas_<tag>.json   (question generator / evaluator input)
                     one item per subcategory with mapping rows (data/ai/mapping.json, which must be accepted as it is
                     now): the outcome, the Playbook suggested actions, and every AI area's row on it (why, impact, CIS
                     safeguards, folded subcategories), so rows that would get the same question can share one. The
                     areas (name, applies to, roles a question may carry, covers) and the safeguards' texts are given
                     once per batch. Definitions (roles, producer flags, impacts) come from data/ai/question_rules.json.
  batch foundation -> data/ai/bank_build/batch_foundation_<tag>.json
                     one item per foundation subcategory (GOVERN and mapping_rules.json foundation.subcategories), with
                     the same definitions and the AI areas list (for questions that name them, e.g. the inventory).
                     --missing keeps only subcategories not yet recorded in that bank.
  mapping         -> data/ai/bank_build/mapping_input_<area>.json   (mapping drafter / evaluator input)
                     one AI area (data/ai/ai_areas.json), the Playbook definition of all four AI RMF functions, the
                     mapped functions (MAP, MEASURE, MANAGE; GOVERN is foundation, not mapped per area) with every
                     subcategory's outcome and shortened suggested actions, the area's candidate CIS safeguards
                     (data/ai/mapping_rules.json area_cis) and the required checks that apply to it
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import (AI_AREA_LABELS, AI_AREAS, AI_BANKS, AI_BUILD, AI_CORE, AI_MAPPING, AI_MAPPING_RULES,  # noqa: E402
                   AI_QUESTION_RULES, AI_SAFEGUARDS, AI_SCOPE_RULES, ai_bank_path)
from ai_bank_common import (area_candidates, area_roles, area_rules, check_mapping_rules,  # noqa: E402
                            foundation_subcategories, load_inputs, load_json, rel, row_id)
from options import AI_FUNCTION_ORDER, AI_QUESTION_BANKS as QUESTION_BANKS  # noqa: E402
from ai_pilot import mapping_status  # noqa: E402

MAX_ACTIONS, ACTION_CHARS, AI_TEXT_CHARS = 6, 220, 260   # how much Playbook and CIS text the mapping drafter sees
import audit  # noqa: E402


def trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def area_items(inp: dict, chosen: list[str] | None) -> list[dict]:
    """One item per subcategory that has mapping rows, with every area's row on it (so similar rows can share a question).
    Area and safeguard texts are left out of the rows; area_context() gives them once per batch."""
    rows = {}
    for area_id, entry in load_json(AI_MAPPING, "mapping.json")["areas"].items():
        for r in entry["rows"]:
            rows.setdefault(r["subcategory"], []).append({
                "row_id": row_id(area_id, r["subcategory"]), "area": area_id, "why": r["why"], "impact": r["impact"],
                "cis_refs": r["cis_refs"],
                "folded": [{"subcategory_id": f, "outcome": inp["subs"][f]["outcome"],
                            "suggested_actions": inp["subs"][f]["suggested_actions"]} for f in r.get("folded", [])],
            })
    return [{**sub_fields(inp["subs"][sid]), "rows": rows[sid]} for sid in inp["subs"]
            if sid in rows and (chosen is None or sid in chosen)]


def area_context(inp: dict, qrules: dict, items: list[dict]) -> dict:
    """The areas and CIS safeguards the batch's rows name, each once."""
    areas = {a["id"]: a for a in load_json(AI_AREAS, "ai_areas.json")["ai_areas"]}
    scope_rules = load_json(AI_SCOPE_RULES, "scope_rules.json")
    used = {r["area"] for i in items for r in i["rows"]}
    refs = sorted({c for i in items for r in i["rows"] for c in r["cis_refs"]})
    return {
        "areas": {a: {"name": areas[a]["name"], "applies_to": areas[a]["applies_to"],
                      "roles_allowed": area_roles(areas[a], qrules, scope_rules), "covers": areas[a]["covers"]}
                  for a in areas if a in used},
        "cis_safeguards": {c: {"title": inp["safeguards"][c]["title"],
                               "ai_text": trunc(inp["safeguards"][c]["ai_applicability"], AI_TEXT_CHARS)} for c in refs},
    }


def sub_fields(s: dict) -> dict:
    return {k: s[k] for k in ("subcategory_id", "function", "outcome", "actions_preamble", "suggested_actions")}


def prepare_batch(inp: dict, bank: str, ids: list[str], function: str | None, everything: bool, tag: str | None,
                  missing_only: bool = False) -> Path:
    """The generator / evaluator input for the area bank (mapping rows by subcategory) or the foundation bank."""
    ok, status = mapping_status()
    if not ok:
        sys.exit(f"[prepare_ai_bank] ERROR: the mapping is not accepted as it is now: {status}")
    qrules = load_json(AI_QUESTION_RULES, "question_rules.json")
    foundation = foundation_subcategories(load_json(AI_MAPPING_RULES, "mapping_rules.json"), inp)
    if bank == "foundation":
        pool = foundation
    else:
        items = area_items(inp, None)
        pool = [i["subcategory_id"] for i in items]
    if ids:
        bad = [i for i in ids if i not in pool]
        if bad:
            sys.exit(f"[prepare_ai_bank] ERROR: not subcategories of the {bank} bank: {bad}")
        chosen = ids
    elif function:
        chosen = [s for s in pool if inp["subs"][s]["function"] == function]
    elif everything:
        chosen = pool
    else:
        sys.exit("[prepare_ai_bank] ERROR: give --ids, --function or --all")
    if missing_only:
        bank_path = ai_bank_path(bank, AI_BANKS)
        done = set(load_json(bank_path, bank_path.name)["subcategories"]) if bank_path.is_file() else set()
        chosen = [s for s in chosen if s not in done]
    if not chosen:
        sys.exit("[prepare_ai_bank] ERROR: no subcategories selected" + (" (all already recorded)" if missing_only else ""))
    definitions = {k: qrules[k] for k in ("roles", "roles_note", "producer_flags", "impacts", "criticality_frame",
                                          "criticality_frame_optional")}
    if bank == "foundation":
        doc = {"bank": bank, "definitions": definitions, "questions_per_subcategory": qrules["foundation_questions"],
               "ai_system_inventory": {k: qrules["ai_system_inventory"][k] for k in ("subcategory", "sheet")},
               "ai_areas": [{**{k: a[k] for k in ("id", "name", "applies_to")},
                             "client_label": load_json(AI_AREA_LABELS, "area_client_labels.json")["labels"][a["id"]]}
                            for a in load_json(AI_AREAS, "ai_areas.json")["ai_areas"]],
               "items": [sub_fields(inp["subs"][s]) for s in chosen]}
    else:
        items = [i for i in items if i["subcategory_id"] in chosen]
        doc = {"bank": bank, "definitions": definitions, "area_question_rule": qrules["area_question_rule"],
               **area_context(inp, qrules, items), "items": items}
    name = tag or (function if function else "ids" if ids else "all")
    out = AI_BUILD / f"batch_{bank}_{name}.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
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
    for s in inp["subs"].values():
        if s["function"] in subs and s["subcategory_id"] not in rules["foundation"]["subcategories"]:
            subs[s["function"]].append({"id": s["subcategory_id"], "outcome": s["outcome"],
                                        "actions": [trunc(a, ACTION_CHARS) for a in s["suggested_actions"][:MAX_ACTIONS]]})
    out = AI_BUILD / f"mapping_input_{area_id}.json"
    out.write_text(json.dumps({
        "area": areas[area_id],
        "other_areas": [{k: a[k] for k in ("id", "name", "applies_to", "covers")}
                        for a in areas.values() if a["id"] != area_id],   # the rest of the AI areas sheet
        "functions": rules["functions"],
        "function_definitions": {f["id"]: f["description"] for f in inp["core"]["functions"]},
        "foundation": rules["foundation"]["functions"] + rules["foundation"]["subcategories"],
        "rules": {"min_why_chars": rules["min_why_chars"], "required_checks": r["required_checks"]},
        "subcategories": subs,
        "cis_candidates": [{"id": s["id"], "title": s["title"], "lowest_ig": (s["ig"] or ["-"])[0],
                            "ai_text": trunc(s["ai_applicability"], AI_TEXT_CHARS)}
                           for s in area_candidates(inp, rules, area_id)],
    }, indent=2, ensure_ascii=False))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["batch", "mapping"])
    ap.add_argument("bank", nargs="?", choices=QUESTION_BANKS)
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--function", choices=AI_FUNCTION_ORDER)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--missing", action="store_true", help="only subcategories not yet recorded in the bank")
    ap.add_argument("--tag")
    ap.add_argument("--area", help="mapping: the AI area id")
    args = ap.parse_args()

    ev = audit.begin(AI_BUILD / "audit.jsonl", f"prepare_{args.what}",
                     {"bank": args.bank, "ids": args.ids, "function": args.function, "all": args.all, "area": args.area})
    inp = load_inputs()
    if args.what == "mapping":
        if not args.area:
            ev.fail("[prepare_ai_bank] ERROR: mapping needs --area ID")
        out = prepare_mapping(inp, args.area)
        ev.finish(inputs=[AI_CORE, AI_SAFEGUARDS, AI_AREAS, AI_MAPPING_RULES], outputs=[out], detail=f"prepared {out.name}")
        print(f"[prepare_ai_bank] wrote {rel(out)} ({out.stat().st_size // 1024} KB)")
        return
    else:
        if not args.bank:
            ev.fail("[prepare_ai_bank] ERROR: batch needs a bank (areas|foundation)")
        out = prepare_batch(inp, args.bank, args.ids, args.function, args.all, args.tag, args.missing)
    print(f"[prepare_ai_bank] wrote {rel(out)} ({out.stat().st_size // 1024} KB)")
    ev.finish(inputs=[AI_CORE, AI_SAFEGUARDS, AI_MAPPING, AI_AREAS, AI_QUESTION_RULES], outputs=[out],
              detail=f"prepared {out.name}")


if __name__ == "__main__":
    main()
