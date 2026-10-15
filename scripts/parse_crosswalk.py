"""
parse_csf2.py
-------------
Reads the official NIST CSF 2.0 Reference Tool XLSX export and produces:

  olir_iso27001.json   — ISO/IEC 27001:2022 → CSF 2.0 crosswalk
  olir_pcidss.json     — PCI DSS v4.0.1 → CSF 2.0 crosswalk
  csf2_core.json       — Full CSF 2.0 core with implementation examples

and records the refresh in <output>/metadata.json (last_refreshed = today, is_placeholder = false, record_count) for
these three files, which is what check_freshness.py reads.

Source file:
  csf2.xlsx downloaded from:
  https://www.nist.gov/cyberframework/csf-20-informative-references
  Button: "Download English (xlsx)"

Usage:
  .venv/bin/python ./scripts/parse_crosswalk.py --input csf2.xlsx --output ./data

Requirements:
  pip install openpyxl
"""

import json
import re
import sys
import argparse
from datetime import date
from pathlib import Path
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).parent))
from paths import CSF_SOURCE, crosswalk_path  # noqa: E402
import audit  # noqa: E402


# ---------------------------------------------------------------------------
# Frameworks to extract — ISO 27001 and PCI DSS only.
# SOC 2 / AICPA TSC is not present in the NIST CPRT export.
# ---------------------------------------------------------------------------
FRAMEWORK_PREFIXES = {
    "iso27001": [
        "ISO/IEC 27001:2022:",
    ],
    "pcidss": [
        "PCI DSS:",
    ],
}

FRAMEWORK_META = {
    "iso27001": {
        "framework":      "ISO/IEC 27001:2022",
        "focal_document": "NIST CSF 2.0",
        "author":         "NIST (CPRT export)",
        "source_url":     "https://www.nist.gov/cyberframework/csf-20-informative-references",
        "notes": (
            "Extracted from the NIST CSF 2.0 Reference Tool informative references column. "
            "Includes both Mandatory Clauses and Annex A Controls. "
            "Relationship type (Subset/Superset/Equal/Intersect) is not carried — "
            "this file lists coverage only. "
            "SOC 2 / AICPA TSC is not included — no official NIST mapping exists; "
            "use AICPA published TSC → SP 800-53 mapping as a manual bridge."
        ),
    },
    "pcidss": {
        "framework":      "PCI DSS v4.0.1",
        "focal_document": "NIST CSF 2.0",
        "author":         "NIST (CPRT export)",
        "source_url":     "https://www.nist.gov/cyberframework/csf-20-informative-references",
        "notes": (
            "Extracted from the NIST CSF 2.0 Reference Tool informative references column. "
            "PCI DSS requirement IDs only — relationship type not carried. "
            "For the owner-authority OLIR submission from PCI SSC see: "
            "csrc.nist.gov/projects/olir/informative-reference-catalog/details?referenceId=183"
        ),
    },
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def clean_control_id(raw: str, prefix: str) -> str:
    """
    Strip the framework prefix and clean up whitespace/punctuation.

    "ISO/IEC 27001:2022: Mandatory Clause:  4.1"  → "Mandatory Clause: 4.1"
    "PCI DSS: 12.1.1"                             → "12.1.1"
    """
    control = raw[len(prefix):].strip().rstrip(",").strip()
    control = re.sub(r" {2,}", " ", control)  # collapse double spaces
    return control


def parse_references(refs_text: str) -> dict:
    """
    Parse the Informative References cell (newline-separated lines) and
    return a dict keyed by framework with sorted, deduplicated control IDs.

    Returns: { "iso27001": [...], "pcidss": [...] }
    """
    result = {key: [] for key in FRAMEWORK_PREFIXES}

    if not refs_text:
        return result

    for line in refs_text.splitlines():
        line = line.strip()
        if not line:
            continue
        for framework, prefixes in FRAMEWORK_PREFIXES.items():
            for prefix in prefixes:
                if line.startswith(prefix):
                    control_id = clean_control_id(line, prefix)
                    # Skip bare prefix with nothing after
                    # e.g. "ISO/IEC 27001:2022: Annex A Controls:"
                    if (control_id
                            and not control_id.endswith(":")
                            and len(control_id) > 1
                            and control_id not in result[framework]):
                        result[framework].append(control_id)
                    break  # matched — skip remaining prefixes for this line

    for key in result:
        result[key].sort()

    return result


def parse_examples(examples_text: str) -> list:
    """
    Split implementation examples text into a list.
    Each example begins with Ex1:, Ex2:, etc.
    """
    if not examples_text:
        return []
    parts = re.split(r"(?=Ex\d+:)", examples_text.strip())
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# XLSX reader
# ---------------------------------------------------------------------------

def parse_xlsx(input_path: str) -> list:
    """
    Read the CSF 2.0 sheet and return a flat list of subcategory records.

    Each record:
    {
        "function_id":             "GV",
        "function_text":           "GOVERN (GV): ...",
        "category_id":             "GV.OC",
        "category_text":           "Organizational Context (GV.OC): ...",
        "subcategory_id":          "GV.OC-01",
        "subcategory_text":        "The organizational mission...",
        "implementation_examples": ["Ex1: ...", ...],
        "mappings": {
            "iso27001": ["Mandatory Clause: 4.1", ...],
            "pcidss":   ["12.1.1", ...]
        }
    }
    """
    wb = load_workbook(input_path, read_only=True)
    ws = wb["CSF 2.0"]

    records = []
    current_function_id   = None
    current_function_text = None
    current_category_id   = None
    current_category_text = None

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i <= 1:  # skip title + header rows
            continue

        col_fn  = row[0]  # Function
        col_cat = row[1]  # Category
        col_sub = row[2]  # Subcategory
        col_ex  = row[3]  # Implementation Examples
        col_ref = row[4]  # Informative References

        # Function row — col A filled, B and C empty
        if col_fn and not col_cat and not col_sub:
            text = str(col_fn).strip()
            m = re.search(r"\((\w+)\)", text)
            current_function_id   = m.group(1) if m else text[:2]
            current_function_text = text
            current_category_id   = None
            current_category_text = None
            continue

        # Category row — col B filled, C empty
        if col_cat and not col_sub:
            text = str(col_cat).strip()
            m = re.search(r"\((\w+\.\w+)\)", text)
            current_category_id   = m.group(1) if m else None
            current_category_text = text
            continue

        # Subcategory row — col C filled
        if col_sub:
            text = str(col_sub).strip()
            m = re.match(r"^(\w+\.\w+-\d+):", text)
            subcategory_id   = m.group(1) if m else None
            subcategory_text = text[m.end():].strip() if m else text

            records.append({
                "function_id":             current_function_id,
                "function_text":           current_function_text,
                "category_id":             current_category_id,
                "category_text":           current_category_text,
                "subcategory_id":          subcategory_id,
                "subcategory_text":        subcategory_text,
                "implementation_examples": parse_examples(str(col_ex) if col_ex else ""),
                "mappings":                parse_references(str(col_ref) if col_ref else ""),
            })

    return records


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------

def build_csf_to_controls(records: list, framework: str,
                           control_filter: set = None) -> dict:
    """
    Forward index: CSF subcategory → controls.
    "Given GV.OC-01 — which ISO controls cover it?"
    If control_filter is provided, only include controls in that set.
    """
    index = {}
    for rec in records:
        sid = rec["subcategory_id"]
        if not sid:
            continue
        controls = rec["mappings"].get(framework, [])
        if control_filter is not None:
            controls = [c for c in controls if c in control_filter]
        index[sid] = {
            "subcategory_text":        rec["subcategory_text"],
            "function_id":             rec["function_id"],
            "category_id":             rec["category_id"],
            "implementation_examples": rec["implementation_examples"],
            "controls":                controls,
            "has_mapping":             len(controls) > 0,
        }
    return index


def build_control_to_csf(records: list, framework: str,
                          control_filter: set = None) -> dict:
    """
    Reverse index: control → CSF subcategories.
    "Given ISO control 5.1 — which CSF subcategories does it satisfy?"
    If control_filter is provided, only include controls in that set.
    """
    index = {}
    for rec in records:
        for control in rec["mappings"].get(framework, []):
            if control_filter is not None and control not in control_filter:
                continue
            if control not in index:
                index[control] = []
            index[control].append({
                "subcategory_id":   rec["subcategory_id"],
                "subcategory_text": rec["subcategory_text"],
                "function_id":      rec["function_id"],
                "category_id":      rec["category_id"],
            })
    return index


def build_framework_json(records: list, framework: str, source_file: str,
                          control_filter: set = None) -> dict:
    """Assemble the complete JSON for one framework output file."""
    def effective_controls(rec):
        c = rec["mappings"].get(framework, [])
        return [x for x in c if control_filter is None or x in control_filter]

    mapped   = [r for r in records if effective_controls(r)]
    unmapped = [r for r in records if not effective_controls(r)]
    unique   = set(c for r in records for c in effective_controls(r))

    meta = dict(FRAMEWORK_META[framework])
    meta["source_file"] = source_file

    return {
        "meta": meta,
        "summary": {
            "total_subcategories":             len(records),
            "subcategories_with_mapping":      len(mapped),
            "subcategories_without_mapping":   len(unmapped),
            "unique_controls_mapped":          len(unique),
            "unmapped_subcategory_ids": sorted(
                r["subcategory_id"] for r in unmapped if r["subcategory_id"]
            ),
        },
        "csf_to_controls": build_csf_to_controls(records, framework, control_filter),
        "control_to_csf":  build_control_to_csf(records, framework, control_filter),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def record_refresh(metadata_path: Path, counts: dict) -> str:
    """Mark the files just parsed as refreshed today in metadata.json. counts: {filename: record_count}."""
    if not metadata_path.is_file():
        return f"{metadata_path} not found: refresh not recorded"
    metadata = json.loads(metadata_path.read_text())
    for name, count in counts.items():
        metadata.setdefault(name, {}).update(
            {"last_refreshed": date.today().isoformat(), "is_placeholder": False, "record_count": count})
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    return f"refresh recorded in {metadata_path.name} for {', '.join(counts)}"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Parse NIST CSF 2.0 Reference Tool XLSX into ISO 27001 and "
            "PCI DSS crosswalk JSON files."
        )
    )
    parser.add_argument(
        "--input",
        default=str(CSF_SOURCE),
        help="Path to csf2.xlsx (default: data/csf/source/csf2.xlsx)"
    )
    parser.add_argument(
        "--output",
        default="./data",
        help="Data root (default: ./data). Files go to csf/ and csf/crosswalks/ under it."
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    ev = audit.begin(output_dir / "audit.jsonl", "parse_crosswalk", {"input": str(input_path), "output": str(output_dir)})
    written, counts = [], {}
    csf_dir = output_dir / "csf"
    csf_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {input_path}")
    records = parse_xlsx(str(input_path))
    print(f"Parsed {len(records)} subcategory records\n")

    for framework, filename, control_filter in [
        ("iso27001",  "olir_iso27001.json",  None),
        ("pcidss",    "olir_pcidss.json",    None),
    ]:
        data = build_framework_json(records, framework, input_path.name,
                                    control_filter=control_filter)
        out_path = crosswalk_path(filename, base=output_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
        written.append(out_path)

        s = data["summary"]
        counts[filename] = s["subcategories_with_mapping"]
        print(f"Written: {out_path}")
        print(f"  Subcategories with mapping:    {s['subcategories_with_mapping']} / {s['total_subcategories']}")
        print(f"  Subcategories without mapping: {s['subcategories_without_mapping']}")
        print(f"  Unique controls mapped:        {s['unique_controls_mapped']}\n")

    # CSF core — subcategories + implementation examples only (no mappings)
    core_path = csf_dir / "csf2_core.json"
    core = {
        "meta": {
            "source_file": input_path.name,
            "source_url":  "https://www.nist.gov/cyberframework/csf-20-informative-references",
            "author":      "NIST (CPRT export)",
            "description": "CSF 2.0 subcategories and implementation examples.",
        },
        "subcategories": [
            {
                "function_id":             r["function_id"],
                "function_text":           r["function_text"],
                "category_id":             r["category_id"],
                "category_text":           r["category_text"],
                "subcategory_id":          r["subcategory_id"],
                "subcategory_text":        r["subcategory_text"],
                "implementation_examples": r["implementation_examples"],
            }
            for r in records
        ],
    }
    with open(core_path, "w") as f:
        json.dump(core, f, indent=2)
    print(f"Written: {core_path}")
    print(f"  Total subcategories: {len(core['subcategories'])}")
    counts["csf2_core.json"] = sum(1 for r in core["subcategories"] if not r["subcategory_text"].startswith("[Withdrawn"))  # active only
    metadata_path = output_dir / "metadata.json"
    print(record_refresh(metadata_path, counts))
    ev.finish(inputs=[input_path], outputs=written + [core_path] + ([metadata_path] if metadata_path.is_file() else []),
              detail=f"{len(records)} subcategory records parsed")
    print("\nDone.")
    print("\nNote: SOC 2 / AICPA TSC is not in NIST CPRT data.")
    print("      Use AICPA TSC → SP 800-53 mapping as a manual bridge.")


if __name__ == "__main__":
    main()