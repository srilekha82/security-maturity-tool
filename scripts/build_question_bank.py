"""
Usage: .venv/bin/python ./scripts/build_question_bank.py --domain <domain|all> [--fanout-threshold N]
                                                 [--allow-pending] [--output-dir DIR] [--cache-dir DIR]

  --domain            healthcare|finance|manufacturing_ot|saas_cloud|consulting|other|all
  --fanout-threshold  a question mapped to >= N subcategories gets a per-subcategory fit check (default 4)
  --allow-pending     write the bank even if some candidates still need a judgement (they are left out)
  --output-dir        where the bank is written (default: data/csf/banks/)
  --cache-dir         where cset_candidates.json, cset_judgements.json and the pending files live
                      (default: data/csf/bank_build/)

Builds data/csf/banks/question_bank_<domain>.json from data/csf/bank_build/cset_candidates.json (see
extract_cset_candidates.py). Each (question, subcategory) pair is routed:

  reject   not_answerable / empty_text questions; a question already judged unfit or out of domain
  accept   decided from the schema, no agent needed:
             - the question's source model is sector-specific and matches the target domain
               (ACET -> finance), and it does not fan out across many subcategories
             - or an earlier agent judgement (bank_build/cset_judgements.json) covers it
  pending  needs an agent: unknown domain (generic source model), a statement-only practice or a
           truncated question that must be (re)written, or a question fanning out over many subcategories

If anything is pending the script writes pending_judgements_<domain>.json (in the bank_build folder) and exits with
code 2 without writing the bank. An agent fills the pending items (prompts/question_bank_judge.md),
record_judgements.py saves the verdicts, and this script is run again. Verdicts are stored per
question with a hash of its text, so they are only redone when CSET changes the question.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import BANK_BUILD, CSF_BANKS, CSF_CORE, CROSSWALK_DIRS, bank_path  # noqa: E402
from options import CSF_FUNCTION_ORDER, DOMAINS  # noqa: E402
import audit  # noqa: E402

REJECT_FLAGS = {"not_answerable", "empty_text"}
# Questions whose text must be (re)written by the agent: a practice statement with no question,
# or a question CSET left cut off mid-sentence.
REWRITE_FLAGS = {"statement_only", "truncated"}

# Source models that are specific to one sector. Everything else is treated as generic.
SECTOR_BY_MODEL = {"ACET": "finance", "SSG Chemical": "manufacturing_ot",
                   "CYOTE": "manufacturing_ot", "HYDRO": "manufacturing_ot"}


def text_hash(q: dict) -> str:
    """Hash of what a judgement was based on; a judgement is stale if CSET changes it."""
    basis = json.dumps([q["question_text"], q.get("practice", {})], sort_keys=True)
    return hashlib.sha1(basis.encode()).hexdigest()[:10]


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def load_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def route_pairs(domain: str, candidates: dict, judgements: dict, active: dict[str, dict],
                fanout_threshold: int) -> tuple[list[dict], dict[str, dict]]:
    """
    Route every (question, active subcategory) pair for one domain.
    Returns (routed_pairs, pending_by_qid).
    """
    questions = candidates["questions"]
    subs_of: dict[str, list[str]] = {}
    for m in candidates["mappings"]:
        if m["subcategory_id"] in active:
            subs_of.setdefault(str(m["qid"]), []).append(m["subcategory_id"])

    routed, pending = [], {}

    def need(qid: str, kind: str, sub: str | None = None):
        item = pending.setdefault(qid, {"needs": [], "fit_subcategories": []})
        if kind not in item["needs"]:
            item["needs"].append(kind)
        if sub and sub not in item["fit_subcategories"]:
            item["fit_subcategories"].append(sub)

    for qid, subs in subs_of.items():
        q = questions.get(qid)
        if q is None:
            continue
        j = judgements.get("questions", {}).get(qid)
        if j and j.get("text_hash") != text_hash(q):
            j = None  # CSET changed this question since it was judged

        def emit(sub, status, decided_by, reason, text=None):
            routed.append({"qid": qid, "subcategory_id": sub, "status": status,
                           "decided_by": decided_by, "reason": reason, "text": text})

        if REJECT_FLAGS & set(q["flags"]):
            for s in subs:
                emit(s, "reject", "schema", f"flags: {sorted(REJECT_FLAGS & set(q['flags']))}")
            continue

        # domain
        sector = SECTOR_BY_MODEL.get(q.get("model_name"))
        domain_by = "schema" if sector == domain else None
        if domain_by is None and j and "domains" in j:
            if domain not in j["domains"] and "all" not in j["domains"]:
                for s in subs:
                    emit(s, "reject", "agent", f"not suited to {domain}: {j.get('reason', '')}")
                continue
            domain_by = "agent"

        # Collect everything this question needs in one go, so the agent is asked once.
        fanout = len(subs)
        needs_rewrite = bool(REWRITE_FLAGS & set(q["flags"])) and not (j and "rewrite" in j)
        fit_missing = [s for s in subs if fanout >= fanout_threshold
                       and (j or {}).get("fit", {}).get(s) is None]
        if domain_by is None:
            need(qid, "domains")
        if needs_rewrite:
            need(qid, "rewrite")
        for s in fit_missing:
            need(qid, "fit", s)
        if qid in pending:
            for s in subs:
                emit(s, "pending", None, "needs judgement")
            continue

        text = q["question_text"]
        if REWRITE_FLAGS & set(q["flags"]):
            if not j["rewrite"]:
                for s in subs:
                    emit(s, "reject", "agent", "agent: cannot be asked as a question")
                continue
            text = j["rewrite"]

        for s in subs:
            if fanout >= fanout_threshold:
                verdict = j["fit"][s]
                if verdict["verdict"] == "reject":
                    emit(s, "reject", "agent", f"does not fit {s}: {verdict.get('reason', '')}")
                else:
                    emit(s, "accept", "agent", "fit confirmed", text)
            else:
                emit(s, "accept", domain_by, "domain match" if domain_by == "schema" else "agent domain verdict", text)
    return routed, pending


def build_pending_file(domain: str, pending: dict, candidates: dict, active: dict[str, dict]) -> dict:
    items = []
    for qid, p in sorted(pending.items(), key=lambda kv: int(kv[0])):
        q = candidates["questions"][qid]
        mapped = [m["subcategory_id"] for m in candidates["mappings"]
                  if str(m["qid"]) == qid and m["subcategory_id"] in active]
        items.append({
            "qid": qid,
            "needs": p["needs"],
            "model_name": q.get("model_name"),
            "category": q.get("category"),
            "sub_category": q.get("sub_category"),
            "question_text": q["question_text"],
            "practice": q.get("practice", {}),
            "mapped_subcategories": [{"id": s, "outcome": active[s]["subcategory_text"]} for s in sorted(mapped)],
            "check_fit_for": sorted(p["fit_subcategories"]),
        })
    return {"domain": domain, "cset_commit": candidates["cset_commit"], "count": len(items), "items": items}


def build_bank(domain: str, routed: list[dict], candidates: dict, active: dict[str, dict],
               iso_lookup: dict, pending_count: int) -> dict:
    by_sub: dict[str, list[dict]] = {}
    seen: dict[str, set[str]] = {}
    for r in sorted(routed, key=lambda r: int(r["qid"])):
        if r["status"] != "accept":
            continue
        text = r["text"]
        key = norm(text)
        if key in seen.setdefault(r["subcategory_id"], set()):
            continue  # same wording already offered for this subcategory
        seen[r["subcategory_id"]].add(key)
        q = candidates["questions"][r["qid"]]
        by_sub.setdefault(r["subcategory_id"], []).append({
            "cset_question_id": int(r["qid"]),
            "question_text": text,
            "category": q.get("category"),
            "sub_category": q.get("sub_category"),
            "model_name": q.get("model_name"),
            "decided_by": r["decided_by"],
            "reworded": text != q["question_text"],
        })

    ordered = sorted(active, key=lambda s: (CSF_FUNCTION_ORDER.get(s[:2], 9), s))
    questions = {
        sid: {
            "subcategory_text": active[sid]["subcategory_text"],
            "iso_mapping": iso_lookup.get(sid, []),
            "candidates": by_sub.get(sid, []),
        }
        for sid in ordered
    }
    with_candidates = sum(1 for v in questions.values() if v["candidates"])
    return {
        "domain": domain,
        "cset_commit": candidates["cset_commit"],
        "built_on": date.today().isoformat(),
        "total_subcategories": len(questions),
        "with_candidates": with_candidates,
        "empty": len(questions) - with_candidates,
        "pending_judgements": pending_count,
        "questions": questions,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, choices=DOMAINS + ["all"])
    parser.add_argument("--fanout-threshold", type=int, default=4)
    parser.add_argument("--allow-pending", action="store_true")
    parser.add_argument("--output-dir", default=str(CSF_BANKS))
    parser.add_argument("--cache-dir", default=str(BANK_BUILD))
    args = parser.parse_args()

    cache, out_dir = Path(args.cache_dir), Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_log = cache / "audit.jsonl"
    candidates = load_json(cache / "cset_candidates.json")
    if candidates is None:
        audit.begin(audit_log, "build_question_bank", {"domain": args.domain}).fail(
            "[build_question_bank] ERROR: cset_candidates.json not found. "
            "Run scripts/extract_cset_candidates.py first.")
    judgements = load_json(cache / "cset_judgements.json", {"questions": {}})

    csf_core = load_json(CSF_CORE)
    active = {s["subcategory_id"]: s for s in csf_core["subcategories"]
              if not s["subcategory_text"].startswith("[Withdrawn")}
    olir_iso = load_json(CROSSWALK_DIRS["olir_iso27001.json"] / "olir_iso27001.json")
    iso_lookup = {k: v.get("controls", []) for k, v in olir_iso.get("csf_to_controls", {}).items()}

    any_pending = False
    build_inputs = [cache / "cset_candidates.json", cache / "cset_judgements.json", CSF_CORE]
    for domain in (DOMAINS if args.domain == "all" else [args.domain]):
        ev = audit.begin(audit_log, "build_question_bank", {"domain": domain, "fanout_threshold": args.fanout_threshold,
                                                             "allow_pending": args.allow_pending})
        routed, pending = route_pairs(domain, candidates, judgements, active, args.fanout_threshold)
        n_pending = sum(1 for r in routed if r["status"] == "pending")
        pending_path = cache / f"pending_judgements_{domain}.json"
        if not pending:
            pending_path.unlink(missing_ok=True)
        if pending:
            pending_path.write_text(json.dumps(build_pending_file(domain, pending, candidates, active),
                                               indent=2, ensure_ascii=False))
            print(f"[{domain}] {len(pending)} questions need a judgement → {pending_path}")
            if not args.allow_pending:
                any_pending = True
                ev.finish("pending", build_inputs, [pending_path], detail=f"{len(pending)} questions need an agent judgement",
                          cset_commit=candidates["cset_commit"])
                continue
        bank = build_bank(domain, routed, candidates, active, iso_lookup, n_pending)
        path = bank_path(domain, out_dir)
        path.write_text(json.dumps(bank, indent=2, ensure_ascii=False))
        by = {}
        for r in routed:
            by[(r["status"], r["decided_by"])] = by.get((r["status"], r["decided_by"]), 0) + 1
        print(f"Built: {path}\nCSET commit: {bank['cset_commit']}\nSubcategories: {bank['total_subcategories']}\n"
              f"  With candidates: {bank['with_candidates']}\n  Empty (fallback at engagement time): {bank['empty']}\n"
              f"  Routing: " + ", ".join(f"{s}/{d or '-'}: {n}" for (s, d), n in sorted(by.items(), key=str)))
        ev.finish(inputs=build_inputs, outputs=[path],
                  detail=f"{bank['with_candidates']} of {bank['total_subcategories']} subcategories with candidates; routing "
                         + ", ".join(f"{s}/{d or '-'}: {n}" for (s, d), n in sorted(by.items(), key=str)),
                  cset_commit=bank["cset_commit"])
    if any_pending:
        sys.exit(2)


if __name__ == "__main__":
    main()
