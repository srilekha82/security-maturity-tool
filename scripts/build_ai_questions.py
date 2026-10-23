"""
Usage: .venv/bin/python ./scripts/build_ai_questions.py <run_dir>

Turns the AI usage profile into the AI RMF question drafts for one engagement. This script decides nothing: it reads
<run_dir>/ai_usage.json, looks the profile up in data/ai/scope_rules.json (the policy) and picks candidates from the bank(s)
under data/ai/banks/. Writes, per bank the profile selects:

  <run_dir>/ai_scope.json                     question type per subcategory and bank, with the reason (inspectable)
  <run_dir>/ai_questions_draft_<bank>.json    entries in the same shape as csf_questions_draft.json, so the assessor
                                              patch merge (record_judgements.py log --base --patch) works unchanged
  <run_dir>/ai_question_bank_used_<bank>.json snapshot of the bank used, so the run stays reproducible

ai_usage.json:
{
  "ai_in_use": "none" | "some" | "unsure",
  "ai_areas": ["invisible_usage", "input", ...],             # the client's AI areas (intake.ai_areas); not read here
                                                              # until TODO step 4. rung, usage_contexts, modifiers and
                                                              # hosts_model are derived from them.
  "producer": {"built_on_existing_model": bool, "given_to_others": bool} | null,   # asked; not read here until step 4
  "role": "producer" | "consumer" | "both" | null,           # asked; needed for "some"
  "rung": "base" | "rag" | "mcp" | "agentic" | null,          # highest technology rung reached; needed for "some"
  "usage_contexts": ["internal", "code_generation", "customer_facing", "third_party_embedded"],
  "modifiers": ["poc", "self_hosted", "builds_on_base_model", "unsanctioned_use"],
  "hosts_model": true | false,                                # optional (default false); true adds self_hosted
  "engagement_flags": {"csf_assessment_done": true, "iso27001_held": false, "iso42001_held": false},
  "captured_on": "YYYY-MM-DD"
}
  some     scoped by role, rung, usage contexts and modifiers
  unsure   scoped as `some` with the rules' fixed profile (consumer, base, no tags); inventory and MAP questions forced to
           full_discovery; the real profile comes from the answers (run again with an updated file)
  none     only the live shadow-AI check is asked; everything else is skip

Question type (topic level): with csf_assessment_done or iso27001_held, a subcategory whose topics are gap topics
(data_model, infra, ai_access) is `gap`; other topics stay full_discovery; with several topics the most demanding wins.

Candidate filter (the effective profile is recorded in ai_scope.json):
  capability   the candidate's rung must be at or below the org's highest rung
  scope_tags   empty = applies to all; otherwise at least one must be in the org's usage contexts
  modifiers    a candidate tagged with a modifier is kept only if the org has it; scope_rules.always_modifiers
               (unsanctioned_use) count as held by every org
  none gate    only candidates tagged with the gate's live modifier are kept
Ranking (weights in scope_rules.json): tag and modifier matches first, with a boost for poc orgs on data_model, ai_access and
inventory questions; ties keep bank order. The top N per type (max_questions) are taken. A subcategory with no candidate left
is dropped and listed in the summary; there is no generic fallback question. gap entries are reworded with
scope_rules.gap_frame; entries whose bank record is needs_human_review carry the rules' review_flag as confidence_flag.

Errors (bad profile, missing bank, a bank category that is not in question_categories.json) exit 1 and write nothing.
Requires the bank(s) built by /build-ai-bank.
"""

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import AI_CATEGORIES, AI_CORE, AI_EVIDENCE_PROMPTS, AI_SCOPE_RULES, ai_bank_path  # noqa: E402
from options import AI_BANK_NAMES, AI_FUNCTION_ORDER, SEVERITY_ORDER  # noqa: E402
from ai_bank_common import core_subcategories  # noqa: E402
import audit  # noqa: E402


# ── the profile ─────────────────────────────────────────────────────────────

def validate_profile(p: dict, enums: dict, rules: dict) -> list[str]:
    if not isinstance(p, dict):
        return ["ai_usage.json must be a JSON object"]
    if p.get("ai_in_use") not in ("none", "some", "unsure"):
        return ["ai_in_use must be none, some or unsure"]
    errors = []
    if p["ai_in_use"] == "some":
        if p.get("role") not in (*AI_BANK_NAMES, "both"):
            errors.append("role must be producer, consumer or both when AI is in use")
        if p.get("rung") not in rules["rung_order"]:
            errors.append(f"rung must be one of {rules['rung_order']}")
    for key, allowed in (("usage_contexts", enums["scope_tags"]), ("modifiers", enums["modifiers"])):
        v = p.get(key, [])
        if not isinstance(v, list) or not set(v) <= set(allowed):
            errors.append(f"{key} must be a list from {allowed}")
    if "builds_on_base_model" in p.get("modifiers", []) and p.get("role") not in ("producer", "both"):
        errors.append("builds_on_base_model applies to producers only")
    if not isinstance(p.get("hosts_model", False), bool):
        errors.append("hosts_model must be true or false")
    flags = p.get("engagement_flags")
    known = set(rules["gap_flags"]) | set(rules["no_effect_flags"])
    if not isinstance(flags, dict) or set(flags) != known or not all(isinstance(x, bool) for x in flags.values()):
        errors.append(f"engagement_flags must be an object of booleans with exactly {sorted(known)}")
    return errors


def effective_profile(p: dict, rules: dict) -> dict:
    """The profile the scope is computed from (the rules' fixed profile for `unsure` and `none`)."""
    gate = p["ai_in_use"]
    if gate == "some":
        e = {"role": p["role"], "rung": p["rung"], "usage_contexts": list(p["usage_contexts"]),
             "modifiers": list(p["modifiers"])}
        if p.get("hosts_model") and "self_hosted" not in e["modifiers"]:
            e["modifiers"].append("self_hosted")   # the intake asks "hosts a model?"; bank candidates are tagged self_hosted
    elif gate == "unsure":
        e = dict(rules["gate"]["unsure"]["profile"])
    else:
        e = {"role": "consumer", "rung": "base", "usage_contexts": [], "modifiers": []}
    e["banks"] = rules["gate"]["none"]["banks"] if gate == "none" else (list(AI_BANK_NAMES) if e["role"] == "both" else [e["role"]])
    return e


def usage_note(p: dict, eff: dict) -> str:
    if p["ai_in_use"] == "none":
        return "No AI use declared; only the unsanctioned-use check is asked"
    if p["ai_in_use"] == "unsure":
        return "AI use unconfirmed: discover what AI is in use before assuming any"
    parts = [f"role {p['role']}", f"highest rung {eff['rung']}"]
    if eff["usage_contexts"]:
        parts.append("usage " + ", ".join(eff["usage_contexts"]))
    if eff["modifiers"]:
        parts.append("modifiers " + ", ".join(eff["modifiers"]))
    return "; ".join(parts)


# ── scope: a question type per subcategory ──────────────────────────────────

def scope_entry(sid: str, categories: list, topics: list, gate: str, flags: list, rules: dict) -> tuple[str, str, str]:
    """(question_type, state, reason) for one subcategory, from the rules."""
    fn = sid.split()[0]
    none, unsure = rules["gate"]["none"], rules["gate"]["unsure"]
    if gate == "none":
        if set(categories) & set(none["live_categories"]):
            return none["live_type"], "none_live", none["live_reason"]
        return "skip", "none_skip", none["skip_reason"]
    if gate == "unsure" and (set(categories) & set(unsure["force_full_discovery"]["categories"])
                             or fn in unsure["force_full_discovery"]["functions"]):
        return rules["default_type"], "forced", rules["reasons"]["forced"]
    per = []
    for t in topics:
        if flags and t in rules["gap_topics"]:
            per.append((rules["gap_type"], "gap", rules["reasons"]["gap"].format(flags=" and ".join(flags), topic=t)))
        elif t in rules["gap_topics"]:
            per.append((rules["default_type"], "no_flag", rules["reasons"]["default"].format(topic=t)))
        else:
            per.append((rules["default_type"], "ungapped_topic", rules["reasons"]["ungapped_topic"].format(topic=t)))
    return max(per, key=lambda r: SEVERITY_ORDER.index(r[0]))


# ── selection: candidates per subcategory ───────────────────────────────────

def keep(c: dict, eff: dict, rules: dict, gate: str) -> bool:
    rung = rules["rung_order"]
    if rung.index(c["capability"]) > rung.index(eff["rung"]):
        return False
    if c["scope_tags"] and not set(c["scope_tags"]) & set(eff["usage_contexts"]):
        return False
    if not set(c.get("modifiers", [])) <= set(eff["modifiers"]) | set(rules["always_modifiers"]):
        return False
    return gate != "none" or rules["gate"]["none"]["live_modifier"] in c.get("modifiers", [])


def rank(c: dict, categories: list, eff: dict, rules: dict) -> int:
    w = rules["ranking"]
    score = w["tag_match"] * len(set(c["scope_tags"]) & set(eff["usage_contexts"]))
    score += w["modifier_match"] * len(set(c.get("modifiers", [])) & set(eff["modifiers"]))
    if "poc" in eff["modifiers"] and (c["topic"] in w["poc_boost_topics"] or set(categories) & set(w["poc_boost_categories"])):
        score += w["poc_boost"]
    return score


def build_draft(bank: str, e: dict, rec: dict, outcome: str, eff: dict, rules: dict, gate: str, flag_text: str,
                evidence: dict) -> dict | None:
    """The draft entry for one in-scope subcategory, or None when no bank candidate fits the profile."""
    ranked = sorted(((-rank(c, e["categories"], eff, rules), i, c) for i, c in enumerate(rec["candidates"])
                     if keep(c, eff, rules, gate)), key=lambda t: (t[0], t[1]))
    selected = [c for _, _, c in ranked][:rules["max_questions"][e["question_type"]]]
    if not selected:
        return None
    gap = e["question_type"] == rules["gap_type"]
    return {
        "subcategory_id": e["subcategory_id"], "bank": bank, "function": e["function"], "outcome": outcome,
        "question_type": e["question_type"],
        "questions": [{"question_text": rules["gap_frame"].format(flags=flag_text, text=c["question_text"]) if gap
                       else c["question_text"],
                       "source_reference": f"AI RMF Playbook: {c['playbook_ref']}", "cis_refs": c["cis_refs"],
                       "capability": c["capability"], "topic": c["topic"]} for c in selected],
        "evidence_prompt": evidence["by_topic"].get(selected[0]["topic"], evidence["default"]),
        "scope_reason": e["reason"], "usage_note": e["usage_note"],
        "confidence_flag": rules["review_flag"] if rec["status"] == "needs_human_review" else "",
        "assessor_note": None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    ev = audit.begin(audit.run_log(run_dir), "build_ai_questions", {})
    usage_path = run_dir / "ai_usage.json"
    inputs = [usage_path, AI_SCOPE_RULES, AI_CATEGORIES, AI_EVIDENCE_PROMPTS, AI_CORE]
    for p in inputs:
        if not p.is_file():
            ev.fail(f"[build_ai_questions] ERROR: {p} not found" + (
                " (capture the AI usage profile first)" if p == usage_path else
                " (run parse_ai_rmf_sources.py)" if p == AI_CORE else ""), inputs)
    rules = json.loads(AI_SCOPE_RULES.read_text())
    cats = json.loads(AI_CATEGORIES.read_text())
    evidence = json.loads(AI_EVIDENCE_PROMPTS.read_text())
    outcomes = {s["subcategory_id"]: s["outcome"] for s in core_subcategories(json.loads(AI_CORE.read_text()))}
    profile = json.loads(usage_path.read_text())

    errors = validate_profile(profile, cats["enums"], rules)
    if errors:
        ev.reject(errors, "ai_usage.json", inputs)

    gate, eff = profile["ai_in_use"], effective_profile(profile, rules)
    flags = [label for k, label in rules["gap_flags"].items() if profile["engagement_flags"][k]]
    note = usage_note(profile, eff)

    scope, drafts, summary = {}, {}, []
    for bank in eff["banks"]:
        bank_file = ai_bank_path(bank)
        if not bank_file.is_file():
            ev.fail(f"[build_ai_questions] ERROR: {bank_file} not found. Run /build-ai-bank first.", inputs)
        inputs.append(bank_file)
        bank_cats = {c["id"]: c for c in cats["banks"][bank]["categories"]}
        bank_doc = json.loads(bank_file.read_text())["subcategories"]
        entries, out, dropped = [], [], []
        for sid, rec in bank_doc.items():
            unknown = [c for c in rec["categories"] if c not in bank_cats]
            if unknown or not rec["categories"]:
                ev.fail(f"[build_ai_questions] ERROR: {bank} bank entry {sid} has categories {rec['categories']} that are not "
                        f"in question_categories.json ({unknown}). The categories changed after the bank was built: "
                        "rebuild the bank.", inputs)
            topics = sorted({bank_cats[c]["topic"] for c in rec["categories"]})
            qtype, state, reason = scope_entry(sid, rec["categories"], topics, gate, flags, rules)
            e = {"subcategory_id": sid, "function": sid.split()[0], "question_type": qtype, "state": state,
                 "reason": reason, "topics": topics, "categories": rec["categories"], "usage_note": note}
            entries.append(e)
            if qtype != "skip":
                draft = build_draft(bank, e, rec, outcomes[sid], eff, rules, gate, " and ".join(flags), evidence)
                (out if draft else dropped).append(draft or sid)
        out.sort(key=lambda q: (AI_FUNCTION_ORDER.get(q["function"], 99), q["subcategory_id"]))
        scope[bank], drafts[bank] = entries, (out, dropped, bank_file)
        by_type = Counter(q["question_type"] for q in out)
        summary.append(f"{bank}: {len(out)} subcategories, {sum(len(q['questions']) for q in out)} questions, "
                       f"by type {dict(by_type)}; skipped {sum(1 for e in entries if e['question_type'] == 'skip')}, "
                       f"no candidate left {len(dropped)}")

    outputs = [run_dir / "ai_scope.json"]
    outputs[0].write_text(json.dumps({"ai_in_use": gate, "effective_profile": eff, "gap_flags_used": flags,
                                      "usage_note": note, "banks": scope}, indent=2, ensure_ascii=False))
    for bank, (out, dropped, bank_file) in drafts.items():
        draft, used = run_dir / f"ai_questions_draft_{bank}.json", run_dir / f"ai_question_bank_used_{bank}.json"
        draft.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        shutil.copy2(bank_file, used)
        outputs += [draft, used]
        if dropped:
            print(f"[build_ai_questions] {bank}: no candidate fits the profile: {', '.join(dropped)}", file=sys.stderr)
    for k, label in rules["no_effect_flags"].items():
        if profile["engagement_flags"].get(k):
            print(f"[build_ai_questions] {label}", file=sys.stderr)
    detail = f"ai_in_use={gate}; " + "; ".join(summary)
    print(f"[build_ai_questions] {detail} → {run_dir}", file=sys.stderr)
    ev.finish(inputs=inputs, outputs=outputs, detail=detail)


if __name__ == "__main__":
    main()
