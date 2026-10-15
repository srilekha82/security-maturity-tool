"""
Usage: .venv/bin/python ./scripts/compute_scope.py <run_dir>

  run_dir   — run folder, e.g. runs/Acme_2026-07-28; its intake.json (intake.py) gives the domain and certifications

Assigns each active CSF 2.0 subcategory a question_type (full_discovery / gap / confirmatory /
skip) and writes <run_dir>/csf_scope.json. This script decides nothing. For each subcategory it works
out a STATE (a fact), then looks the state up in data/csf/scope_rules.json (the policy):

  govern / no_cert / no_mapping / no_soa / not_in_soa      from the subcategory, the certs, the OLIR map
  implemented / applicable_not_implemented /
  implementation_unknown                                   from the SoA (soa_parsed.json)
  covered_elsewhere / not_relevant / unclear               the AGENT's reading of an exclusion reason,
                                                           from <run_dir>/soa_judgements.json

With several certs or several mapped controls the most demanding type wins (severity_order in
data/common/intake_options.json). The domain weights in data/csf/domain_weights.json then bump the type up
domain_bump_steps levels. Withdrawn subcategories are left out.

Agent step: if an ISO control mapped to a CSF subcategory is excluded in the SoA, or its
applicability was unrecognised, and soa_judgements.json has no entry for it, the script writes
<run_dir>/soa_pending.json and exits 2 without writing csf_scope.json. The agent fills
soa_judgements.json (prompts/soa_exclusion_judge.md) and the script is run again:

  {"Annex A Controls: 5.1": {"applicable": false,            # only needed if applicability was unrecognised
                             "exclusion_class": "covered_elsewhere" | "not_relevant" | "unclear",
                             "reason": "one sentence"}}
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import CSF_CORE, CROSSWALK_DIRS, DOMAIN_WEIGHTS, SCOPE_RULES  # noqa: E402
from options import CERT_FILES, CSF_FUNCTION_ORDER, SEVERITY_ORDER, WEIGHT_KEY, load_intake  # noqa: E402
import audit  # noqa: E402


def normalize_soa_id(control_id: str) -> str:
    """Unify ID styles: 'A.5.1' (old soa_parsed.json) and 'Control 5.1' (some OLIR rows) -> 'Annex A Controls: 5.1'."""
    m = re.match(r"^(?:A\.|Control\s+)(\d+\.\d+)$", control_id.strip())
    return f"Annex A Controls: {m.group(1)}" if m else control_id.strip()


def load_rules() -> dict:
    rules = json.loads(SCOPE_RULES.read_text())
    order, states = SEVERITY_ORDER, rules["states"]
    bad = [n for n, s in states.items() if s["type"] not in order]
    bad += [c for c in rules["exclusion_classes"] if c not in states]
    bad += [s for s in rules["function_states"].values() if s not in states]
    if bad:
        sys.exit(f"[compute_scope] ERROR: {SCOPE_RULES.name} refers to unknown types/states: {bad}")
    return rules


def needs_judgement(row: dict) -> bool:
    """An SoA row the agent has to read: excluded, or applicability not recognised."""
    return row["applicable"] is not True


def soa_control_state(row: dict, judgement: dict | None, rules: dict) -> str | None:
    """State of one SoA control, or None while a judgement is still missing."""
    applicable = row["applicable"]
    if applicable is None:
        applicable = (judgement or {}).get("applicable")
        if not isinstance(applicable, bool):
            return None
    if applicable:
        impl = row.get("implemented")
        return ("implemented" if impl is True
                else "applicable_not_implemented" if impl is False else "implementation_unknown")
    cls = (judgement or {}).get("exclusion_class")
    return cls if cls in rules["exclusion_classes"] else None


def validate_judgements(judgements: dict, soa: dict, rules: dict) -> list[str]:
    errors = []
    for cid, j in judgements.items():
        if cid not in soa:
            errors.append(f"{cid}: not a control in soa_parsed.json")
            continue
        if not isinstance(j, dict):
            errors.append(f"{cid}: entry must be an object")
            continue
        if "applicable" in j and not isinstance(j["applicable"], bool):
            errors.append(f"{cid}: applicable must be true or false")
        if "exclusion_class" in j and j["exclusion_class"] not in rules["exclusion_classes"]:
            errors.append(f"{cid}: exclusion_class must be one of {rules['exclusion_classes']}")
        if not str(j.get("reason", "")).strip():
            errors.append(f"{cid}: a reason is required")
    return errors


def cert_state(cert: str, sid: str, olir: dict, soa: dict | None, judgements: dict,
               rules: dict, rank) -> tuple[str, str, list]:
    """(state, deciding_control, mapped_controls) for one cert and one subcategory."""
    controls = olir.get("csf_to_controls", {}).get(sid, {}).get("controls", [])
    if not controls:
        return "no_mapping", "", []
    if cert == "iso27001" and soa is not None:
        # Only Annex A controls appear in an SoA; mandatory clauses never do.
        in_soa = [n for n in (normalize_soa_id(c) for c in controls) if n in soa]
        if not in_soa:
            return "not_in_soa", "", controls
        per = [(soa_control_state(soa[c], judgements.get(c), rules), c) for c in in_soa]
        state, ctl = max(per, key=lambda r: rank(r[0]))
        return state, ctl, controls
    return "no_soa", "", controls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    intake = load_intake(run_dir)
    domain, certs = intake["domain"], intake["certs"]
    ev = audit.begin(audit.run_log(run_dir), "compute_scope", {"domain": domain, "certs": certs})
    ev_inputs = [run_dir / "intake.json", CSF_CORE, SCOPE_RULES, DOMAIN_WEIGHTS]

    rules = load_rules()
    order = SEVERITY_ORDER
    rank = lambda state: order.index(rules["states"][state]["type"])  # noqa: E731

    csf_core = json.loads(CSF_CORE.read_text())
    weights = json.loads(DOMAIN_WEIGHTS.read_text()).get(WEIGHT_KEY[domain], {})
    olirs = {c: json.loads((CROSSWALK_DIRS[CERT_FILES[c]] / CERT_FILES[c]).read_text()) for c in certs}

    # ── SoA and the agent's reading of its exclusions ────────────────────────
    soa, judgements = None, {}
    soa_path = run_dir / "soa_parsed.json"
    if "iso27001" in certs and soa_path.exists():
        soa = {normalize_soa_id(r["control_id"]): r for r in json.loads(soa_path.read_text())}
        print(f"[compute_scope] Using SoA: {len(soa)} controls", file=sys.stderr)
        ev_inputs += [soa_path, run_dir / "soa_judgements.json"]
        jpath = run_dir / "soa_judgements.json"
        judgements = {normalize_soa_id(k): v for k, v in
                      (json.loads(jpath.read_text()) if jpath.exists() else {}).items()}
        errors = validate_judgements(judgements, soa, rules)
        if errors:
            ev.reject(errors, "soa_judgements.json", ev_inputs)

        # only controls that map to an active CSF subcategory need reading
        mapped = {normalize_soa_id(c) for sid, info in olirs["iso27001"].get("csf_to_controls", {}).items()
                  for c in info.get("controls", [])}
        pending = [c for c in sorted(mapped & soa.keys())
                   if needs_judgement(soa[c]) and soa_control_state(soa[c], judgements.get(c), rules) is None]
        if pending:
            pending_path = run_dir / "soa_pending.json"
            pending_path.write_text(json.dumps({
                "count": len(pending),
                "items": [{"control_id": c, "applicable_raw": soa[c]["applicable_raw"],
                           "applicable_recognised": soa[c]["applicable"] is not None,
                           "exclusion_reason": soa[c]["exclusion_reason"]} for c in pending],
            }, indent=2, ensure_ascii=False))
            print(f"[compute_scope] {len(pending)} SoA controls need a judgement → {pending_path}")
            ev.pending(f"{len(pending)} SoA controls need an agent reading", ev_inputs, [pending_path])
        (run_dir / "soa_pending.json").unlink(missing_ok=True)
    elif "iso27001" in certs:
        print("[compute_scope] No soa_parsed.json — ISO-mapped subcategories become confirmatory (LOW)",
              file=sys.stderr)

    # ── per subcategory: state -> policy ─────────────────────────────────────
    scope = []
    for sub in csf_core["subcategories"]:
        sid = sub["subcategory_id"]
        if sub["subcategory_text"].startswith("[Withdrawn"):
            continue

        cert_controls = sorted({c for cert in certs
                                for c in olirs[cert].get("csf_to_controls", {}).get(sid, {}).get("controls", [])})
        fixed = rules["function_states"].get(sid[:2])
        if fixed:
            state, cert, ctl, controls = fixed, "", "", cert_controls
        elif not certs:
            state, cert, ctl, controls = "no_cert", "", "", []
        else:
            results = [(cert_state(c, sid, olirs[c], soa, judgements, rules, rank), c) for c in certs]
            (state, ctl, _), cert = max(results, key=lambda r: rank(r[0][0]))
            controls = sorted({x for (_, _, ctrls), _c in results for x in ctrls})

        policy = rules["states"][state]
        qtype, conf = policy["type"], policy["confidence"]
        reason = policy["reason"].format(cert=cert, control=ctl)

        if weights.get(sid, 0) > 0:
            bumped = order[min(order.index(qtype) + rules["domain_bump_steps"], len(order) - 1)]
            if bumped != qtype:
                qtype, reason = bumped, reason + " [domain bump applied]"

        scope.append({"subcategory_id": sid, "question_type": qtype, "state": state, "reason": reason,
                      "confidence": conf, "mapped_controls": controls})

    scope.sort(key=lambda e: (CSF_FUNCTION_ORDER.get(e["subcategory_id"][:2], 99), e["subcategory_id"]))
    out = run_dir / "csf_scope.json"
    out.write_text(json.dumps(scope, indent=2, ensure_ascii=False))

    counts = Counter(e["question_type"] for e in scope)
    print(f"[compute_scope] {len(scope)} subcategories → {out}", file=sys.stderr)
    summary = " | ".join(f"{t}: {counts.get(t, 0)}" for t in order if t != "skip" or counts.get(t))
    print("[compute_scope] " + summary, file=sys.stderr)
    ev.finish(inputs=ev_inputs, outputs=[out], detail=summary, soa_used=soa is not None)


if __name__ == "__main__":
    main()
