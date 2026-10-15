"""
Usage: .venv/bin/python ./scripts/build_ai_impact_inputs.py [--xlsx PATH] [--output PATH]

Input feed for the AI impact notes (agent steps in prompts/ai_impact_notes_writer.md). Script only, no judgement.

Joins the official CIS Controls v8.1 -> NIST CSF 2.0 mapping (xlsx) to the AI-specific text of the MCP and AI Agents
companion-guide safeguards (data/ai/cis_ai_safeguards.json), by safeguard id, giving per CSF 2.0 subcategory the AI
text of every mapped safeguard that has any. Writes data/ai/bank_build/impact_pending.json:

  items:    one per CSF subcategory with at least one mapped safeguard that has AI-specific text
            {subcategory_id, subcategory_text, safeguards: [{id, cis_id, title, relationship, ai_text}]}
  unmapped: CSF subcategories with no note source, each with a reason (never guessed):
            no_cis_mapping (no CIS safeguard maps to it) or no_ai_text (mapped, but the guides add nothing)

CIS safeguard ids: the xlsx stores them as numbers, so 4.10, 8.10 and 16.10 collapse into 4.1, 8.1 and 16.1. Ids are
rebuilt from the control number and row order (a new safeguard starts when the safeguard cell or title changes), and
checked: the title must equal the companion guide's title for that id, safeguards per control must match
data/ai/parse_config.json, and the CSF subcategories the workbook lists as unmapped must equal the ones found here.
Any mismatch fails and nothing is written.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent))
from paths import AI_BUILD, AI_CIS_CSF_XLSX, AI_PARSE_CONFIG, AI_SAFEGUARDS, CSF_CORE  # noqa: E402
import audit  # noqa: E402

SHEET, UNMAPPED_SHEET = "All CIS Controls & Safeguards", "Unmapped CSF"
NOTE_GUIDES = ("MCP", "AGENT")  # the guides whose AI text feeds the notes
CSF_ID_RE = re.compile(r"^[A-Z]{2}\.[A-Z]{2}-\d{2}$")
MAX_AI_TEXT = 700


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower().replace(" ", " ")).strip()


def read_mapping(xlsx: Path, expected_per_control: dict) -> tuple[list[dict], set[str]]:
    """(rows, CSF ids the workbook lists as unmapped). Row: cis_id, title, relationship, csf_id."""
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    rows, control, n, last_key = [], None, 0, None
    seen_titles: dict[str, str] = {}
    for r in wb[SHEET].iter_rows(min_row=2, values_only=True):
        ctl_cell, sg_cell, title = r[1], r[2], r[5]
        if sg_cell is None:
            continue  # control heading or description row
        ctl = str(ctl_cell).strip().replace(" ", "")
        if ctl != control:
            control, n, last_key = ctl, 0, None
        key = (str(sg_cell).strip(), norm_title(str(title)))
        if key != last_key:
            n += 1
            last_key = key
        cis_id = f"{control}.{n}"
        # the cell may show the collapsed number (4.1 for 4.10); anything else must equal the rebuilt id
        shown = str(sg_cell).strip()
        if shown != cis_id and not (cis_id.endswith("0") and shown == cis_id[:-1]):
            raise ValueError(f"row for {title!r}: workbook shows safeguard {shown}, order gives {cis_id}")
        csf = (r[11] or "").strip() if isinstance(r[11], str) else None
        rows.append({"cis_id": cis_id, "title": str(title).strip(), "relationship": r[10], "csf_id": csf})
    per_control: dict[str, set] = {}
    for x in rows:
        per_control.setdefault(x["cis_id"].split(".")[0], set()).add(x["cis_id"])
    bad = {c: (len(per_control.get(c, ())), n_) for c, n_ in expected_per_control.items()
           if len(per_control.get(c, ())) != n_}
    if bad:
        raise ValueError(f"safeguards per control differ from expected (found, expected): {bad}")
    unmapped = {str(r[0]).strip() for r in wb[UNMAPPED_SHEET].iter_rows(min_row=2, values_only=True)
                if r[0] and CSF_ID_RE.match(str(r[0]).strip())}
    return rows, unmapped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", default=str(AI_CIS_CSF_XLSX))
    parser.add_argument("--output", default=str(AI_BUILD / "impact_pending.json"))
    args = parser.parse_args()

    ev = audit.begin(AI_BUILD / "audit.jsonl", "build_ai_impact_inputs", {"xlsx": args.xlsx, "output": args.output})
    inputs = [Path(args.xlsx), AI_SAFEGUARDS, CSF_CORE, AI_PARSE_CONFIG]
    for p in inputs:
        if not p.is_file():
            ev.fail(f"[build_ai_impact_inputs] ERROR: {p} not found (see data/ai/source/README.md; "
                    f"run parse_ai_rmf_sources.py for {AI_SAFEGUARDS.name})", inputs)

    cfg = json.loads(AI_PARSE_CONFIG.read_text())
    guides = json.loads(AI_SAFEGUARDS.read_text())["safeguards"]
    csf = {s["subcategory_id"]: s["subcategory_text"] for s in json.loads(CSF_CORE.read_text())["subcategories"]
           if not s["subcategory_text"].startswith("[Withdrawn")}
    try:
        rows, sheet_unmapped = read_mapping(Path(args.xlsx), cfg["cis_v81_safeguards_per_control"])
    except ValueError as e:
        ev.fail(f"[build_ai_impact_inputs] ERROR: {e}", inputs)

    errors = []
    by_guide: dict[str, dict[str, dict]] = {g: {} for g in NOTE_GUIDES}
    base_titles: dict[str, str] = {}
    for r in guides:
        if r["guide"] in by_guide:
            by_guide[r["guide"]][r["cis_id"]] = r
        base_titles.setdefault(r["cis_id"], r["title"])
    for x in rows:
        guide_title = base_titles.get(x["cis_id"])
        if guide_title is None or norm_title(guide_title) != norm_title(x["title"]):
            errors.append(f"safeguard {x['cis_id']}: workbook title {x['title']!r} differs from the guide title {guide_title!r}")
    unknown = sorted({x["csf_id"] for x in rows if x["csf_id"] and x["csf_id"] not in csf})
    if unknown:
        errors.append(f"CSF ids in the workbook that are not active subcategories in csf2_core.json: {unknown}")
    if errors:
        for e in sorted(set(errors))[:20]:
            print(f"  - {e}", file=sys.stderr)
        ev.fail(f"[build_ai_impact_inputs] {len(set(errors))} problems, nothing written: {sorted(set(errors))[:2]}", inputs)

    mapped_rows: dict[str, list[dict]] = {}
    for x in rows:
        if x["csf_id"]:
            mapped_rows.setdefault(x["csf_id"], []).append(x)
    found_unmapped = set(csf) - set(mapped_rows)
    if found_unmapped != sheet_unmapped:
        ev.fail("[build_ai_impact_inputs] ERROR: CSF subcategories without a mapping differ from the workbook's own "
                f"'Unmapped CSF' sheet: only here {sorted(found_unmapped - sheet_unmapped)}, "
                f"only in the sheet {sorted(sheet_unmapped - found_unmapped)}", inputs)

    items, unmapped = [], [{"subcategory_id": s, "reason": "no_cis_mapping"} for s in sorted(found_unmapped)]
    for sid in sorted(mapped_rows):
        sgs, seen = [], set()
        for x in mapped_rows[sid]:
            for g in NOTE_GUIDES:
                row = by_guide[g].get(x["cis_id"])
                if row and row["has_ai_guidance"] and row["id"] not in seen:
                    seen.add(row["id"])
                    t = row["ai_applicability"]
                    sgs.append({"id": row["id"], "cis_id": x["cis_id"], "title": row["title"],
                                "relationship": x["relationship"],
                                "ai_text": t if len(t) <= MAX_AI_TEXT else t[:MAX_AI_TEXT - 1].rstrip() + "…"})
        if sgs:
            items.append({"subcategory_id": sid, "subcategory_text": csf[sid], "safeguards": sgs})
        else:
            unmapped.append({"subcategory_id": sid, "reason": "no_ai_text"})
    unmapped.sort(key=lambda u: u["subcategory_id"])

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"guides": list(NOTE_GUIDES), "items": items, "unmapped": unmapped},
                              indent=2, ensure_ascii=False))
    n_no_map = sum(1 for u in unmapped if u["reason"] == "no_cis_mapping")
    print(f"[build_ai_impact_inputs] {len(items)} CSF subcategories with AI safeguard text → {out.name}; "
          f"unmapped: {n_no_map} no CIS mapping, {len(unmapped) - n_no_map} mapped but no AI text")
    ev.finish(inputs=inputs, outputs=[out],
              detail=f"{len(items)} items, {len(unmapped)} unmapped ({n_no_map} no CIS mapping)")


if __name__ == "__main__":
    main()
