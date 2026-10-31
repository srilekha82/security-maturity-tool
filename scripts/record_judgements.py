"""
Usage: .venv/bin/python ./scripts/record_judgements.py <verdicts.json> [--pending PATH] [--model ID] [--session REF] [--cache-dir DIR]
       .venv/bin/python ./scripts/record_judgements.py log <run_dir> --step NAME --output FILE --model ID
                  [--prompt PATH] [--inputs FILE ...] [--base FILE --patch FILE [--check FILE
                  [--prev-patch FILE --prev-check FILE]]] [--session REF]

The second form (log) is the audit trail for agent steps inside an engagement run (SoA exclusion
reading, assessor). It goes through audit.record_agent_output, like every other agent step: it writes
runs/<Org>_<date>/judgement_log/<timestamp>_<step>.json with the model, prompt and input hashes and a snapshot of
the output. Write-once. See log_run_step().
With --base and --patch (the assessor) the agent returns only the entries it changed; the patch is
validated against the base (same fields, no added or removed entries, a new assessor_note on each),
merged, and the merged list is written to --output. Exits 1, writing nothing, if the patch is invalid.
With --check (the rewrite checker's verdicts, prompts/assessor_rewrite_checker.md, logged as its own step first) there
must be exactly one verdict per patch entry; an entry it fails keeps the rewrite but gets data/common/assessor_check.json
`flag` as confidence_flag and the reason appended to its assessor_note. With --prev-patch and --prev-check (round 2),
an entry identical to the earlier patch that passed then must pass now.

The first form, below, is for the question bank build.

Validates agent verdicts for the question bank and merges them into data/csf/bank_build/cset_judgements.json.
This is the only way verdicts get into the store, so a malformed agent answer fails here, loudly,
instead of silently changing a bank.

verdicts.json:
{
  "<qid>": {
    "domains": ["finance", "other"],          # any of the six domains, or ["all"]  (optional)
    "rewrite": "Question text ..." | null,    # for statement-only practices; null = cannot be asked  (optional)
    "fit": {"GV.SC-04": {"verdict": "accept"|"reject", "reason": "..."}},          # (optional)
    "reason": "one sentence"
  }
}

Every recording run is also appended to judgement_log/ (next to the store) as a write-once record:
timestamp, CSET commit, hashes of the judge prompt, the pending file the agent was shown and the verdicts file,
the verdicts exactly as submitted, and the --model / --session the caller supplies. The store is the
current-state lookup; the log is the audit trail and is never edited.

Each stored verdict records a hash of the question text it was based on (see build_question_bank.py),
so it is ignored automatically if CSET later changes that question. Exit code 1 if anything is invalid;
nothing is written in that case.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_question_bank import REWRITE_FLAGS, text_hash  # noqa: E402
from options import DOMAINS, QUESTION_TYPES  # noqa: E402
from paths import ASSESSOR_CHECK, BANK_BUILD, CSF_CORE, REPO_ROOT  # noqa: E402
import audit  # noqa: E402
from audit import sha, run_log  # noqa: E402

JUDGE_PROMPT = REPO_ROOT / "prompts" / "question_bank_judge.md"


VALID_DOMAINS = set(DOMAINS) | {"all"}


def validate(verdicts: dict, candidates: dict, valid_subs: set[str]) -> list[str]:
    errors = []
    mapped = {}
    for m in candidates["mappings"]:
        mapped.setdefault(str(m["qid"]), set()).add(m["subcategory_id"])

    for qid, v in verdicts.items():
        q = candidates["questions"].get(qid)
        if q is None:
            errors.append(f"{qid}: unknown question id")
            continue
        if not isinstance(v, dict) or not (v.keys() & {"domains", "rewrite", "fit"}):
            errors.append(f"{qid}: needs at least one of domains / rewrite / fit")
            continue
        if "domains" in v:
            d = v["domains"]
            if not isinstance(d, list) or not d or not set(d) <= VALID_DOMAINS:
                errors.append(f"{qid}: domains must be a non-empty list from {sorted(VALID_DOMAINS)}")
        if "rewrite" in v and v["rewrite"] is not None:
            if not isinstance(v["rewrite"], str) or len(v["rewrite"].strip()) < 20:
                errors.append(f"{qid}: rewrite must be a question of at least 20 characters, or null")
            elif not (REWRITE_FLAGS & set(q["flags"])):
                errors.append(f"{qid}: rewrite given but the question is neither statement-only nor truncated")
        for sub, fv in v.get("fit", {}).items():
            if sub not in mapped.get(qid, set()) or sub not in valid_subs:
                errors.append(f"{qid}: {sub} is not an active subcategory this question maps to")
            if not isinstance(fv, dict) or fv.get("verdict") not in ("accept", "reject"):
                errors.append(f"{qid}/{sub}: verdict must be accept or reject")
            elif not str(fv.get("reason", "")).strip():
                errors.append(f"{qid}/{sub}: a reason is required")
        if not str(v.get("reason", "")).strip() and "domains" in v:
            errors.append(f"{qid}: a reason is required with domains")
    return errors


def validate_patch(base: list, patch: list) -> list[str]:
    """Check an agent's list of changed entries against the full list it reviewed."""
    if not isinstance(base, list) or not isinstance(patch, list):
        return ["base and patch must both be JSON lists of entries"]
    by_id = {e["subcategory_id"]: e for e in base}
    errors, seen = [], set()
    for e in patch:
        sid = e.get("subcategory_id") if isinstance(e, dict) else None
        if sid not in by_id:
            errors.append(f"{sid!r}: not an entry in the reviewed list (entries cannot be added)")
            continue
        if sid in seen:
            errors.append(f"{sid}: appears twice in the patch")
        seen.add(sid)
        old = by_id[sid]
        if set(e) != set(old):
            errors.append(f"{sid}: must be the complete entry with the same fields (diff: {sorted(set(e) ^ set(old))})")
            continue
        for k in ("function", "outcome"):
            if e[k] != old[k]:
                errors.append(f"{sid}: {k} must not change")
        if e["question_type"] not in QUESTION_TYPES:
            errors.append(f"{sid}: question_type must be one of {sorted(QUESTION_TYPES)}")
        if not isinstance(e["questions"], list) or not e["questions"] or not all(
                isinstance(q, dict) and str(q.get("question_text", "")).strip() for q in e["questions"]):
            errors.append(f"{sid}: questions must be a non-empty list of non-blank questions")
        note = e.get("assessor_note")
        if not isinstance(note, str) or not note.strip() or note == old.get("assessor_note"):
            errors.append(f"{sid}: a changed entry needs a new assessor_note saying what changed")
        elif old.get("assessor_note") and not note.startswith(old["assessor_note"]):
            errors.append(f"{sid}: the existing assessor_note must be kept; append yours after ' | '")
        if e == old:
            errors.append(f"{sid}: identical to the reviewed entry; leave unchanged entries out of the patch")
    return errors


def validate_check(patch: list, check, prev: tuple[list, list] | None = None) -> list[str]:
    """The checker's verdicts on a patch: one per patch entry, pass or fail (a fail with a reason); in round 2 an entry
    identical to the earlier patch that passed then must pass now."""
    if not isinstance(check, list) or not all(isinstance(v, dict) for v in check):
        return ["the check file must be a JSON list of verdicts"]
    ids = [e.get("subcategory_id") for e in patch if isinstance(e, dict)]
    got = [v.get("subcategory_id") for v in check]
    errors = [] if sorted(got) == sorted(ids) else [f"the check needs exactly one verdict per patch entry "
                                                     f"(missing {sorted(set(ids) - set(got))}, extra or repeated "
                                                     f"{sorted({g for g in got if g not in ids or got.count(g) > 1})})"]
    for v in check:
        if v.get("verdict") not in ("pass", "fail") or (v["verdict"] == "fail" and not str(v.get("reason", "")).strip()):
            errors.append(f"{v.get('subcategory_id')}: verdict must be pass or fail, and a fail needs a reason")
    if prev:
        old = {e["subcategory_id"]: e for e in prev[0]}
        passed = {v["subcategory_id"] for v in prev[1] if v.get("verdict") == "pass"}
        now = {e["subcategory_id"]: e for e in patch if isinstance(e, dict)}
        flipped = [v["subcategory_id"] for v in check if v.get("verdict") == "fail" and v["subcategory_id"] in passed
                   and now.get(v["subcategory_id"]) == old.get(v["subcategory_id"])]
        if flipped:
            errors.append(f"round 2 fails entries that are unchanged and passed round 1: {', '.join(flipped)}")
    return errors


def apply_check(entry: dict, verdict: dict, rule: dict) -> dict:
    """A rewrite the checker failed: kept, flagged for the consultant, with the checker's reason on its note."""
    if verdict["verdict"] == "pass":
        return entry
    note = f"{rule['note_prefix']}{verdict['reason'].strip()}"
    return dict(entry, confidence_flag=rule["flag"],
                assessor_note=f"{entry['assessor_note']} | {note}" if entry.get("assessor_note") else note)


def load_list(path: Path) -> list:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"[record_judgements] ERROR: cannot read {path} as JSON: {e}")


def log_run_step(argv: list[str]) -> None:
    """Record an agent step inside an engagement run (SoA reading, assessor ...) through the shared recording contract."""
    parser = argparse.ArgumentParser(prog="record_judgements.py log")
    parser.add_argument("run_dir")
    parser.add_argument("--step", required=True, help="e.g. soa_exclusions, assessor")
    parser.add_argument("--output", required=True,
                        help="the file the agent wrote (relative to run_dir); with --patch, the merged file to write")
    parser.add_argument("--model", required=True, help="model id of the agent that made the judgements")
    parser.add_argument("--prompt", help="prompt file the agent followed, relative to the repo root")
    parser.add_argument("--inputs", nargs="*", default=[], help="files the agent was shown (relative to run_dir)")
    parser.add_argument("--base", help="with --patch: the full list of entries the agent reviewed")
    parser.add_argument("--patch", help="the agent's list of changed entries only; validated and merged into "
                                        "--base, written to --output")
    parser.add_argument("--check", help="with --patch: the rewrite checker's verdicts (one per patch entry)")
    parser.add_argument("--prev-patch", help="with --check, round 2: the reviewer's earlier patch")
    parser.add_argument("--prev-check", help="with --check, round 2: the checker's earlier verdicts")
    parser.add_argument("--session", help="session / run reference of the agent")
    a = parser.parse_args(argv)

    run_dir = Path(a.run_dir)
    if not run_dir.is_dir():
        sys.exit(f"[record_judgements] ERROR: run folder not found: {run_dir}")

    def rp(p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else run_dir / q

    out = rp(a.output)
    extra_inputs = [rp(p) for p in a.inputs]
    extra_record = {"inputs": [{"path": p, "sha": sha(rp(p))} for p in a.inputs], "output": {"path": a.output}}
    if a.patch:
        if not a.base:
            sys.exit("[record_judgements] ERROR: --patch needs --base")
        try:
            base = json.loads(rp(a.base).read_text())
        except (OSError, ValueError) as e:
            sys.exit(f"[record_judgements] ERROR: cannot read {rp(a.base)} as JSON: {e}")
        extra_inputs.insert(0, rp(a.base))
        extra_record["base"] = {"path": a.base, "sha": sha(rp(a.base))}
        check, prev = None, None
        if a.check:
            check = load_list(rp(a.check))
            if bool(a.prev_patch) != bool(a.prev_check):
                sys.exit("[record_judgements] ERROR: --prev-patch and --prev-check go together")
            prev = (load_list(rp(a.prev_patch)), load_list(rp(a.prev_check))) if a.prev_patch else None
            extra_inputs.append(rp(a.check))
            extra_record["check"] = {"path": a.check, "sha": sha(rp(a.check))}
        rule = json.loads(ASSESSOR_CHECK.read_text())

        def store(patch):  # the patch is the agent's whole answer; the merge is mechanical
            verdicts = {v["subcategory_id"]: v for v in check or []}
            changed = {e["subcategory_id"]: apply_check(e, verdicts[e["subcategory_id"]], rule) if check else e
                       for e in patch}
            out.write_text(json.dumps([changed.get(e["subcategory_id"], e) for e in base], indent=2, ensure_ascii=False))
            failed = sum(1 for v in verdicts.values() if v["verdict"] == "fail")
            return out, (f"logged step '{a.step}', {len(changed)} entries changed"
                         + (f", {failed} not confirmed by the checker (flagged)" if check else ""))

        def validate(patch):
            errors = validate_patch(base, patch)
            return errors or (validate_check(patch, check, prev) if check is not None else [])

        file = rp(a.patch)
    else:  # an output another script validates on its next run (soa_judgements.json): recorded as submitted
        file, validate = out, lambda data: []
        store = lambda data: (out, f"logged step '{a.step}'")  # noqa: E731

    audit.record_agent_output(
        log_path=run_log(run_dir), log_dir=run_dir / "judgement_log", step=a.step, args={"prompt": a.prompt},
        file=file, validate=validate, store=store, model=a.model, session=a.session,
        prompts=[a.prompt] if a.prompt else [], extra_inputs=extra_inputs, extra_record=extra_record)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "log":
        return log_run_step(sys.argv[2:])
    parser = argparse.ArgumentParser()
    parser.add_argument("verdicts")
    parser.add_argument("--pending", help="the pending_judgements file the agent was shown")
    parser.add_argument("--model", help="model id of the agent that made the verdicts")
    parser.add_argument("--session", help="session / run reference of the agent")
    parser.add_argument("--cache-dir", default=str(BANK_BUILD))
    args = parser.parse_args()

    cache = Path(args.cache_dir)
    candidates = json.loads((cache / "cset_candidates.json").read_text())
    csf_core = json.loads(CSF_CORE.read_text())
    valid_subs = {s["subcategory_id"] for s in csf_core["subcategories"]
                  if not s["subcategory_text"].startswith("[Withdrawn")}
    store_path = cache / "cset_judgements.json"

    def store(verdicts):
        store = json.loads(store_path.read_text()) if store_path.exists() else {"questions": {}}
        for qid, v in verdicts.items():
            entry = store["questions"].setdefault(qid, {})
            if entry.get("text_hash") != text_hash(candidates["questions"][qid]):
                entry.clear()  # stale verdicts for a changed question are dropped
            entry.update({k: val for k, val in v.items() if k in ("domains", "rewrite", "reason")})
            if "fit" in v:
                entry.setdefault("fit", {}).update(v["fit"])
            entry.update({"text_hash": text_hash(candidates["questions"][qid]),
                          "judged_on": date.today().isoformat(), "decided_by": "agent"})
        store_path.write_text(json.dumps(store, indent=2, ensure_ascii=False))
        return store_path, f"recorded {len(verdicts)} questions ({len(store['questions'])} judged in total)"

    audit.record_agent_output(
        log_path=cache / "audit.jsonl", log_dir=cache / "judgement_log", step="record_judgements",
        args={"verdicts": args.verdicts}, file=args.verdicts,
        validate=lambda verdicts: validate(verdicts, candidates, valid_subs), store=store,
        model=args.model, session=args.session, prompts=[str(JUDGE_PROMPT.relative_to(REPO_ROOT))],
        log_name=lambda verdicts: f"{len(verdicts)}q",
        extra_inputs=[args.pending] if args.pending else [],
        extra_record={"cset_commit": candidates["cset_commit"], "pending_file": args.pending,
                      "pending_sha": sha(Path(args.pending)) if args.pending else None},
        snapshot_key="verdicts")


if __name__ == "__main__":
    main()
