"""
Usage: .venv/bin/python ./scripts/check_freshness.py --all --run runs/<Org>_<date>
       .venv/bin/python ./scripts/check_freshness.py --ai-bank

AI RMF gate (--ai-bank):
    .venv/bin/python ./scripts/check_freshness.py --ai-bank

Compares the SHA-256 of the current source files (Playbook, the three CIS companion guides, the CIS -> CSF xlsx) with the
hashes each output records about its own inputs, one line per stage: parse (ai_rmf_core.json, cis_ai_safeguards.json),
each question bank (foundation, areas), notes, and pilot. A stage is `current` only if it exists and was built from
these exact sources; a bank must also be complete (record_ai_bank.bank_freshness: the area bank has every subcategory
with mapping rows, each written for the rows as they are now; the foundation bank every foundation subcategory). `mapping` is current when every AI area
is drafted from the current sources, AI areas and rules, reviewed (no row needs_human_review, no sheet edit left
unimported) and accepted as it is now (ai_pilot.py accept-mapping); it also says how many subcategories no area reaches. `pilot` is current when the user accepted the pilot (ai_pilot.py accept) for the current
generator and evaluator prompts. `ai areas` is current when data/ai/ai_areas.json was imported from
data/ai/authoring/ai_areas.xlsx as the spreadsheet is now (sheet_io.py import ai_areas). Exit 0 = every stage current (skip the rebuild); exit 1 = something is missing, stale
or incomplete.

Everything at the start of an engagement (CSF and AI together), --all. The domain and certifications come from the run's
intake.json (--run), or are given directly with --domain and --certs when no run exists yet:
    .venv/bin/python ./scripts/check_freshness.py --all --domain finance --certs iso27001 [--cset-path PATH]

Prints the reference-data table (csf2_core.json plus the crosswalk of each certification held), the CSF question bank of the domain (missing; stale when the CSET SQL changed since the
bank was built; else current) and the AI RMF stages above, then what needs work. It runs `git fetch` in the CSET clone
to see upstream; if the fetch fails it says so and compares with the local commit instead. It only reports facts: the
calling command decides what to rebuild. Exit 0 = all current; exit 1 = something needs work.
"""
import json, sys, argparse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from options import AI_QUESTION_BANKS, CERT_FILES, DOMAINS, load_intake  # noqa: E402
from paths import (AI_BANKS, AI_CIS_CSF_XLSX, AI_CORE,  # noqa: E402
                   AI_PARSE_CONFIG, AI_PILOT, AI_SAFEGUARDS, AI_SOURCE, AI_AREAS, AI_AREAS_XLSX, CSF_IMPACT_NOTES,
                   AI_QUESTIONS_AREAS_XLSX, AI_QUESTIONS_FOUNDATION_XLSX, DATA_AUDIT, METADATA, bank_path)
import audit  # noqa: E402
from sheet_io import sheet_status  # noqa: E402
from extract_cset_candidates import DEFAULT_CSET_PATH, git, sql_changed  # noqa: E402
from ai_pilot import mapping_status, pilot_status  # noqa: E402

def load(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


AI_QUESTIONS_XLSX = {"areas": (AI_QUESTIONS_AREAS_XLSX, "area_questions"),           # review sheet, sheet_io name
                     "foundation": (AI_QUESTIONS_FOUNDATION_XLSX, "foundation_questions")}


def bank_completeness(bank: str, doc: dict) -> tuple[bool, str]:
    """Whether a question bank holds what it must now (record_ai_bank.bank_freshness)."""
    import record_ai_bank as R
    return R.bank_freshness(bank, doc, R.load_inputs())


def ai_stages() -> list[tuple[str, bool, str]]:
    """(stage, current?, text) per stage of the AI RMF build; see the module docstring."""
    cfg = json.loads(AI_PARSE_CONFIG.read_text())
    guides = {g: audit.sha(AI_SOURCE / c["file"]) for g, c in cfg["guides"].items()}
    playbook, cis_csf = audit.sha(AI_SOURCE / cfg["playbook"]["file"]), audit.sha(AI_CIS_CSF_XLSX)
    missing = [name for name, v in [("Playbook", playbook), ("CIS -> CSF xlsx", cis_csf), *guides.items()] if v is None]
    if missing:
        return [("sources", False, f"missing: {', '.join(missing)} (see data/ai/source/README.md)")]

    def verdict(stage, doc, same, what="sources changed since it was built"):
        if doc is None:
            return stage, False, "missing"
        return (stage, True, "current") if same else (stage, False, f"stale ({what})")

    core, sg = load(AI_CORE), load(AI_SAFEGUARDS)
    notes = load(CSF_IMPACT_NOTES)
    recorded = lambda sources: {g: v["sha256_16"] for g, v in sources.items()}  # noqa: E731
    stages = [
        verdict("parse", core and sg, core and sg and core["source_sha256_16"] == playbook
                and recorded(sg["sources"]) == guides),
    ]
    for bank in AI_QUESTION_BANKS:
        doc = load(AI_BANKS / f"question_bank_ai_rmf_{bank}.json")
        stage, ok, text = verdict(f"bank {bank}", doc, doc and doc["playbook_sha256_16"] == playbook
                                  and doc["guide_sha256_16"] == guides)
        if ok and stages[0][1]:
            ok, text = bank_completeness(bank, doc)
            sheet, name = AI_QUESTIONS_XLSX[bank]
            if ok and sheet.is_file() and audit.sha(sheet) != doc.get("source_sha"):
                ok, text = False, f"review sheet edited but not imported (sheet_io.py import {name})"
        stages.append((stage, ok, text))
    stages.append(verdict("notes", notes, notes and notes.get("sources_sha256_16") == {
        "cis_csf": cis_csf, "MCP": guides["MCP"], "AGENT": guides["AGENT"]}))
    stages.append(("pilot", *pilot_status(AI_PILOT)))
    stages.append(("ai areas", *sheet_status("ai_areas", AI_AREAS_XLSX, AI_AREAS)))
    stages.append(("mapping", *mapping_status()))
    return stages


def check_ai_bank() -> None:
    ev = audit.begin(DATA_AUDIT, "check_freshness_ai_bank", {})
    stages = ai_stages()
    for stage, ok, text in stages:
        print(f"{stage + ':':<16}{text}")
    todo = [stage for stage, ok, _ in stages if not ok]
    if todo:
        print(f"\nNeeds work: {', '.join(todo)}")
        ev.finish("stale", detail=f"needs work: {', '.join(todo)}", stages={s: t for s, _, t in stages})
        sys.exit(1)
    print("\nAll AI RMF stages are current: nothing to rebuild.")
    ev.finish(detail="all AI RMF stages current")
    sys.exit(0)


def csf_bank_stage(domain: str, cset_path: Path) -> tuple[tuple[str, bool, str], list[str]]:
    """(stage line, notes) for the CSF question bank of a domain. Stale = the CSET SQL changed since the bank was built."""
    stage = f"CSF bank {domain}"
    bank = load(bank_path(domain))
    if bank is None:
        return (stage, False, "missing"), []
    notes = []
    try:
        git(cset_path, "fetch")
        ref = git(cset_path, "rev-parse", "@{u}")
    except (RuntimeError, OSError) as e:
        notes.append(f"could not check upstream CSET ({e}); compared with the local CSET commit instead")
        try:
            ref = git(cset_path, "rev-parse", "HEAD")
        except (RuntimeError, OSError) as e2:
            return (stage, False, f"cannot check against CSET ({e2})"), notes
    built = bank.get("cset_commit")
    if built == ref:
        return (stage, True, "current"), notes
    try:
        changed = sql_changed(cset_path, built or "", ref)
    except (RuntimeError, OSError):
        changed = True  # cannot compare (unknown commit): treat as stale
    if changed:
        return (stage, False, "stale (CSET SQL changed since the bank was built)"), notes
    return (stage, True, "current (CSET moved, no SQL changed)"), notes


def reference_table(certs: list[str]) -> tuple[list[str], list[str]]:
    """Print the age table of the reference data files relevant for these certs; (files checked, files needing attention)."""
    metadata = json.loads(METADATA.read_text())

    relevant = ["csf2_core.json"]
    relevant.extend(CERT_FILES[cert] for cert in certs if cert in CERT_FILES)

    today = date.today()
    needs_attention = []

    col_w = [22, 14, 9, 11, 45]
    sep = "─" * (sum(col_w) + len(col_w) * 3 - 1)
    header = f"{'File':<{col_w[0]}} {'Last updated':<{col_w[1]}} {'Age':<{col_w[2]}} {'Threshold':<{col_w[3]}} {'Status':<{col_w[4]}}"
    print("\nData file status for this engagement:")
    print(sep)
    print(header)
    print(sep)

    for fname in relevant:
        info = metadata.get(fname, {})
        last_refreshed = info.get("last_refreshed")
        threshold = info.get("refresh_threshold_days")
        is_placeholder = info.get("is_placeholder", False)

        if last_refreshed is None:
            age_days = 9999
            age_str = "never"
            last_str = "—"
        else:
            last_date = date.fromisoformat(last_refreshed)
            age_days = (today - last_date).days
            age_str = f"{age_days}d"
            last_str = last_refreshed

        thresh_str = f"{threshold}d" if threshold else "—"

        if is_placeholder:
            status = "seed data — replace before first real run"
            needs_attention.append(fname)
        elif threshold is None:
            status = "ok (static)"
        elif age_days > threshold:
            status = "STALE — recommend updating"
            needs_attention.append(fname)
        elif age_days > threshold * 0.75:
            status = "aging — worth checking"
        else:
            status = "ok"

        print(f"{fname:<{col_w[0]}} {last_str:<{col_w[1]}} {age_str:<{col_w[2]}} {thresh_str:<{col_w[3]}} {status}")

    print(sep)

    return relevant, needs_attention


def check_all(args) -> None:
    """CSF reference data, the CSF bank of the domain, and every AI RMF stage, in one report."""
    ev = audit.begin(DATA_AUDIT, "check_freshness_all", {"domain": args.domain, "certs": args.certs})
    _, files = reference_table(args.certs)
    csf_stage, notes = csf_bank_stage(args.domain, Path(args.cset_path).expanduser())
    stages = [csf_stage, *ai_stages()]
    print()
    for stage, ok, text in stages:
        print(f"{stage + ':':<22}{text}")
    for note in notes:
        print(f"note: {note}")
    todo = files + [stage for stage, ok, _ in stages if not ok]
    if todo:
        print(f"\nNeeds work: {', '.join(todo)}")
        ev.finish("stale", detail=f"needs work: {', '.join(todo)}", stages={s: t for s, _, t in stages}, notes=notes)
        sys.exit(1)
    print("\nEverything is current.")
    ev.finish(detail="everything current", notes=notes)
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--certs", nargs="*", default=[], choices=list(CERT_FILES), help="with --all and no --run")
    parser.add_argument("--run", help="with --all: the run folder; domain and certs come from its intake.json")
    parser.add_argument("--ai-bank", action="store_true", help="SHA-256 gate for the AI RMF build (see the docstring)")
    parser.add_argument("--all", action="store_true", help="CSF and AI freshness together (needs --run, or --domain)")
    parser.add_argument("--domain", choices=DOMAINS, help="with --all and no --run: the CSF domain of this engagement")
    parser.add_argument("--cset-path", default=DEFAULT_CSET_PATH, help="with --all: local CSET clone")
    args = parser.parse_args()

    if args.ai_bank:
        check_ai_bank()
    if not args.all:
        parser.error("give --ai-bank, or --all with --run (or --domain)")
    if args.run:
        intake = load_intake(args.run)
        args.domain, args.certs = intake["domain"], intake["certs"]
    elif not args.domain:
        parser.error("--all needs --run, or --domain")
    check_all(args)

if __name__ == "__main__":
    main()
