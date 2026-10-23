"""
Usage: .venv/bin/python ./scripts/parse_ai_rmf_sources.py [--source-dir DIR] [--output-dir DIR]

Parses the AI RMF sources into compact JSON. Script only, no judgement.

  AI_RMF_Playbook.pdf          -> data/ai/ai_rmf_core.json
      functions[]: id (GOVERN ...), name, description (the Playbook's statement under the function heading),
      subcategories[]: subcategory_id, function, category, outcome, actions_preamble, suggested_actions[]
  3 CIS v8.1 companion guides  -> data/ai/cis_ai_safeguards.json
      controls:   one per guide and CIS Control (applicability intro, hosting notes, additional considerations)
      safeguards: one row per safeguard (id with guide prefix e.g. LLM-15.4, title, base text, IG levels, AI text)

It does NOT extract an AI RMF -> CIS link (the guides carry none; see the crosswalk step).

CIS safeguard IDs: the guides' tables lose the ID in about half the rows, so IDs are rebuilt from the control number
(taken from each page's footer) and row order, and checked against any ID the table does show. Expected counts live
in data/ai/parse_config.json; any mismatch fails the parse and nothing is written.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).parent))
from paths import AI, AI_BUILD, AI_CORE, AI_PARSE_CONFIG, AI_SAFEGUARDS, AI_SOURCE  # noqa: E402
import audit  # noqa: E402

SUB_RE = re.compile(r"^((GOVERN|MAP|MEASURE|MANAGE) (\d+)\.(\d+))\s*$")
FUNCTION_RE = re.compile(r"^(Govern|Map|Measure|Manage)\s*$")   # function heading, followed by its one-line statement
PAGE_NO_RE = re.compile(r"^\d+ of \d+$")
FOOTER_RE = re.compile(r"^Control (\d+): (.+?) \d+$")
HOSTING_RE = re.compile(r"^Model Hosting and Deployment Considerations\s*$", re.M)
ADDITIONAL_RE = re.compile(r"^Additional .+ Considerations\s*$", re.M)
BULLET_RE = re.compile(r"^[•▪◦·]\s*")
SECTIONS = ("About", "Suggested Actions", "Transparency & Documentation")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("­", "")).strip()


# ── Playbook ────────────────────────────────────────────────────────────────

def parse_playbook(pdf_path: Path) -> list[dict]:
    """Functions (in Playbook page order), each with its description and its subcategories."""
    with pdfplumber.open(pdf_path) as pdf:
        lines = [l for p in pdf.pages for l in (p.extract_text() or "").split("\n")]
    lines = [l for l in lines if not PAGE_NO_RE.match(l.strip())]

    starts = [(i, SUB_RE.match(l.strip())) for i, l in enumerate(lines)]
    starts = [(i, m) for i, m in starts if m]
    # A function heading counts only when the next subcategory after it belongs to that function (skips stray words).
    headings = []
    for i, l in enumerate(lines):
        fm = FUNCTION_RE.match(l.strip())
        nxt = next((m for j, m in starts if j > i), None)
        if fm and nxt and nxt.group(2) == fm.group(1).upper():
            headings.append((i, fm.group(1)))
    functions = {}
    for i, name in headings:
        first = next(j for j, _ in starts if j > i)
        functions[name.upper()] = {"id": name.upper(), "name": name, "description": clean(" ".join(lines[i + 1:first])),
                                   "subcategories": []}
    breaks = sorted([i for i, _ in starts] + [i for i, _ in headings])
    for i, m in starts:
        end = next((b for b in breaks if b > i), len(lines))
        block = lines[i + 1:end]
        idx = {name: block.index(name) for name in SECTIONS if name in block}
        if len(idx) < len(SECTIONS):
            raise ValueError(f"{m.group(1)}: missing section(s) {sorted(set(SECTIONS) - set(idx))}")
        outcome = clean(" ".join(block[:idx["About"]]))
        preamble, actions = [], []
        for l in block[idx["Suggested Actions"] + 1:idx["Transparency & Documentation"]]:
            if BULLET_RE.match(l):
                actions.append(BULLET_RE.sub("", l))
            elif actions:
                actions[-1] += " " + l.strip()
            else:
                preamble.append(l.strip())
        if m.group(2) not in functions:
            raise ValueError(f"{m.group(1)}: no '{m.group(2).title()}' function heading before it")
        functions[m.group(2)]["subcategories"].append({
            "subcategory_id": m.group(1),
            "function": m.group(2),
            "category": f"{m.group(2)} {m.group(3)}",
            "outcome": outcome,
            "actions_preamble": clean(" ".join(preamble)),
            "suggested_actions": [clean(a) for a in actions if clean(a)],
        })
    return list(functions.values())


# ── CIS companion guides ────────────────────────────────────────────────────

def table_rows(page, table) -> list[list[str]]:
    """Body rows of a safeguard table as 7 cell texts. Every second row has no outer cells in pdfplumber's model
    (the ID and AI text columns come back as None), so each cell is read by cropping the row's band at the
    header's column bounds instead of trusting the table's own cells."""
    header_cells = table.rows[0].cells
    xs = [(c[0], c[2]) for c in header_cells]
    rows = []
    for row in table.rows[1:]:
        top, bottom = row.bbox[1], row.bbox[3]
        rows.append([(page.crop((x0, top, x1, bottom)).extract_text() or "") for x0, x1 in xs])
    return rows


def parse_guide(pdf_path: Path, prefix: str, app_header: str) -> tuple[list[dict], dict]:
    """(safeguard rows, controls) for one guide."""
    per_control_text: dict[str, list[str]] = {}
    rows_by_control: dict[str, list[list]] = {}
    titles: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            last = text.strip().split("\n")[-1].strip() if text.strip() else ""
            fm = FOOTER_RE.match(last)
            if not fm:
                continue  # front matter, appendices, conclusion
            control = fm.group(1)
            titles.setdefault(control, fm.group(2))
            per_control_text.setdefault(control, []).append(text)
            for table in page.find_tables():
                header = table.extract()[0]
                if header and header[0] == "Safeguard":
                    if header[-1].strip() != app_header:
                        raise ValueError(f"{prefix} control {control}: unexpected table header {header}")
                    rows_by_control.setdefault(control, []).extend(table_rows(page, table))

    safeguards, controls = [], {}
    for control, rows in rows_by_control.items():
        for n, row in enumerate(rows, 1):
            sid = f"{control}.{n}"
            shown = clean(row[0])
            if shown and shown != sid:
                raise ValueError(f"{prefix}: table shows safeguard {shown} where row order gives {sid}")
            safeguards.append({
                "id": f"{prefix}-{sid}",
                "cis_id": sid,
                "guide": prefix,
                "control": int(control),
                "title": clean(row[1]),
                "base_text": clean(row[2]),
                "ig": [lvl for lvl, cell in zip(("IG1", "IG2", "IG3"), row[3:6]) if cell and cell.strip()],
                "ai_applicability": clean(row[6]),
                "has_ai_guidance": bool(clean(row[6])) and not clean(row[6]).startswith("No Additional"),
            })

    for control, pages in per_control_text.items():
        text = "\n".join(l for p in pages for l in p.split("\n") if not FOOTER_RE.match(l.strip()))
        intro = ""
        im = re.search(r"^" + re.escape(app_header) + r"\s*$", text, re.M)
        sm = re.search(r"^Safeguards\s*$", text, re.M)
        if im and sm and im.end() < sm.start():
            intro = clean(text[im.end():sm.start()])
        hosting = additional = ""
        hm = HOSTING_RE.search(text)
        if hm:
            rest = text[hm.end():]
            am = ADDITIONAL_RE.search(rest)
            hosting = clean(rest[:am.start()] if am else rest)
            additional = clean(rest[am.end():]) if am else ""
        else:
            am = ADDITIONAL_RE.search(text)
            additional = clean(text[am.end():]) if am else ""
        controls[f"{prefix}-{control}"] = {
            "guide": prefix, "control": int(control), "title": titles[control],
            "applicability_intro": intro, "hosting_notes": hosting, "additional_considerations": additional,
        }
    safeguards.sort(key=lambda r: (r["control"], int(r["cis_id"].split(".")[1])))
    return safeguards, controls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=str(AI_SOURCE))
    parser.add_argument("--output-dir", default=str(AI))
    args = parser.parse_args()

    src, out = Path(args.source_dir), Path(args.output_dir)
    cfg = json.loads(AI_PARSE_CONFIG.read_text())
    ev = audit.begin(AI_BUILD / "audit.jsonl", "parse_ai_rmf_sources", {"source_dir": str(src), "output_dir": str(out)})

    playbook = src / cfg["playbook"]["file"]
    guide_files = {g: src / c["file"] for g, c in cfg["guides"].items()}
    missing = [str(p) for p in [playbook, *guide_files.values()] if not p.is_file()]
    if missing:
        ev.fail(f"[parse_ai_rmf_sources] ERROR: source file(s) missing (see data/ai/source/README.md): {missing}")
    inputs = [playbook, *guide_files.values()]

    errors = []
    try:
        functions = parse_playbook(playbook)
    except ValueError as e:
        ev.fail(f"[parse_ai_rmf_sources] ERROR: Playbook: {e}", inputs)
    order = cfg["playbook"]["functions"]
    if sorted(f["id"] for f in functions) != sorted(order):
        errors.append(f"Playbook: found functions {[f['id'] for f in functions]}, expected {order}")
    functions.sort(key=lambda f: order.index(f["id"]) if f["id"] in order else len(order))   # AI RMF order, not page order
    subs = [s for f in functions for s in f["subcategories"]]
    errors += [f"Playbook {f['id']}: no function description" for f in functions if len(f["description"]) < 20]
    if len(subs) != cfg["playbook"]["subcategories"]:
        errors.append(f"Playbook: found {len(subs)} subcategories, expected {cfg['playbook']['subcategories']}")
    ids = [s["subcategory_id"] for s in subs]
    if len(set(ids)) != len(ids):
        errors.append("Playbook: duplicate subcategory ids")
    errors += [f"Playbook {s['subcategory_id']}: no outcome text" for s in subs if len(s["outcome"]) < 20]
    errors += [f"Playbook {s['subcategory_id']}: no suggested actions" for s in subs if not s["suggested_actions"]]

    safeguards, controls = [], {}
    expected = cfg["cis_v81_safeguards_per_control"]
    for g, path in guide_files.items():
        try:
            rows, ctl = parse_guide(path, g, cfg["guides"][g]["applicability_header"])
        except ValueError as e:
            errors.append(str(e))
            continue
        counts: dict[str, int] = {}
        for r in rows:
            counts[str(r["control"])] = counts.get(str(r["control"]), 0) + 1
        bad = {c: (counts.get(c, 0), n) for c, n in expected.items() if counts.get(c, 0) != n}
        if bad:
            errors.append(f"{g}: safeguards per control differ from expected (found, expected): {bad}")
        safeguards += rows
        controls.update(ctl)

    if errors:
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        ev.fail(f"[parse_ai_rmf_sources] {len(errors)} problems, nothing written: {errors[:2]}", inputs)

    out.mkdir(parents=True, exist_ok=True)
    core_path, sg_path = out / AI_CORE.name, out / AI_SAFEGUARDS.name
    core_path.write_text(json.dumps({"source": playbook.name, "source_sha256_16": audit.sha(playbook),
                                     "functions": functions}, indent=2, ensure_ascii=False))
    sg_path.write_text(json.dumps({
        "sources": {g: {"file": p.name, "sha256_16": audit.sha(p)} for g, p in guide_files.items()},
        "controls": controls, "safeguards": safeguards}, indent=2, ensure_ascii=False))

    with_ai = sum(1 for r in safeguards if r["has_ai_guidance"])
    per_guide = ", ".join(f"{g} {sum(1 for r in safeguards if r['guide'] == g)}" for g in guide_files)
    print(f"[parse_ai_rmf_sources] {len(functions)} functions, {len(subs)} subcategories → {core_path.name}; "
          f"{len(safeguards)} safeguards ({per_guide}; {with_ai} with AI text) → {sg_path.name}")
    ev.finish(inputs=inputs, outputs=[core_path, sg_path],
              detail=f"{len(subs)} subcategories, {len(safeguards)} safeguards ({per_guide}), {with_ai} with AI text")


if __name__ == "__main__":
    main()
