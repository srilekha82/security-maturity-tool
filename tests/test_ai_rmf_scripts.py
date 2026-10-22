"""Run: .venv/bin/python -m unittest discover -s tests -v

Checks the AI RMF scripts against the real parsed data (read-only) with every store redirected to a temp dir,
so a test run never touches data/ai or data/csf."""

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ai_pilot as PL  # noqa: E402
import prepare_ai_bank as P  # noqa: E402
import record_ai_bank as R  # noqa: E402
from ai_bank_common import DEFAULT_PROMPTS  # noqa: E402
from paths import AI_CORE, AI_SAFEGUARDS, REPO_ROOT  # noqa: E402


class ParsedSources(unittest.TestCase):
    def test_playbook(self):
        subs = json.loads(AI_CORE.read_text())["subcategories"]
        self.assertEqual(len(subs), 72)
        self.assertEqual(len({s["subcategory_id"] for s in subs}), 72)
        self.assertTrue(all(s["suggested_actions"] and len(s["outcome"]) > 20 for s in subs))
        self.assertEqual({s["function"] for s in subs}, {"GOVERN", "MAP", "MEASURE", "MANAGE"})

    def test_safeguards(self):
        doc = json.loads(AI_SAFEGUARDS.read_text())
        ids = [r["id"] for r in doc["safeguards"]]
        self.assertEqual(len(ids), 459)
        self.assertEqual(len(set(ids)), 459)
        for g in ("LLM", "MCP", "AGENT"):
            self.assertEqual(sum(1 for i in ids if i.startswith(g + "-")), 153)
            for tenth in ("4.10", "8.10", "16.10"):  # the numeric-collapse gotcha
                self.assertIn(f"{g}-{tenth}", ids)
        self.assertTrue(all(r["title"] and r["base_text"] for r in doc["safeguards"]))
        self.assertIn("LLM-1.1", {r["id"] for r in doc["safeguards"] if r["has_ai_guidance"]})


class Recording(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name, rel in (("AI_APPLICABILITY", "applicability.json"), ("CROSSWALK", "airmf_to_cis.json"),
                          ("CSF_IMPACT_NOTES", "ai_impact_notes.json")):
            setattr(R, name, self.tmp / rel)
        R.AI_BANKS, R.AI_BUILD, R.LOG_DIR = self.tmp / "banks", self.tmp / "build", self.tmp / "build" / "log"
        R.AI_CROSSWALKS = self.tmp
        P.AI_APPLICABILITY, P.AI_CROSSWALK_CIS = R.AI_APPLICABILITY, R.CROSSWALK   # prepare reads what record wrote
        P.AI_BANKS, P.AI_BUILD, PL.AI_BANKS = R.AI_BANKS, R.AI_BUILD, R.AI_BANKS
        R.AI_BUILD.mkdir(parents=True, exist_ok=True)
        self.inp = R.load_inputs()
        self.subs = list(self.inp["subs"])

    def run_mode(self, mode, data, bank=None):
        f = self.tmp / f"{mode}_in.json"
        f.write_text(json.dumps(data))
        a = argparse.Namespace(file=str(f), bank=bank, model="test-model", session=None, prompt=None)
        try:
            R.record(mode, a)
            return 0
        except SystemExit as e:
            return e.code

    def applicability(self, consumer_only=()):
        c = list(self.inp["bank_cats"]["consumer"])[0]
        p = list(self.inp["bank_cats"]["producer"])[0]
        return {s: {"producer": [] if s in consumer_only else [p], "consumer": [c], "reason": "test"} for s in self.subs}

    def test_applicability_valid_and_invalid(self):
        bad = self.applicability()
        del bad[self.subs[0]]
        bad[self.subs[1]]["consumer"] = ["no_such_category"]
        self.assertEqual(self.run_mode("applicability", bad), 1)
        self.assertFalse(R.AI_APPLICABILITY.exists(), "nothing may be stored when the file is rejected")
        self.assertEqual(self.run_mode("applicability", self.applicability(consumer_only=self.subs[:2])), 0)
        stored = json.loads(R.AI_APPLICABILITY.read_text())["subcategories"]
        self.assertEqual(stored[self.subs[0]]["producer"], [])
        self.assertEqual(len(list(R.LOG_DIR.glob("*_applicability.json"))), 1)
        lines = [json.loads(l) for l in (R.AI_BUILD / "audit.jsonl").read_text().splitlines()]
        self.assertEqual([l["status"] for l in lines], ["rejected", "ok"])

    def test_crosswalk_rejects_unknown_safeguard(self):
        data = {s: [] for s in self.subs}
        data[self.subs[0]] = ["LLM-3.1", "LLM-99.9"]
        self.assertEqual(self.run_mode("crosswalk", data), 1)
        data[self.subs[0]] = ["LLM-3.1", "MCP-3.1"]
        self.assertEqual(self.run_mode("crosswalk", data), 0)
        self.assertEqual(json.loads(R.CROSSWALK.read_text())["links"][self.subs[0]], ["LLM-3.1", "MCP-3.1"])

    def candidate(self, sid, **over):
        c = {"question_text": f"Describe how your organisation handles the outcome of {sid}, who owns it and what evidence exists.",
             "playbook_ref": f"{sid} — suggested action 1", "cis_refs": ["LLM-3.1"], "scope_tags": [],
             "capability": "base", "topic": "governance"}
        c.update(over)
        return c

    def test_candidates(self):
        self.assertEqual(self.run_mode("applicability", self.applicability(consumer_only=[self.subs[0]])), 0)
        sid, other = self.subs[1], self.subs[0]
        mk = lambda n: [self.candidate(sid, question_text=f"Describe how variant {i} of {sid} works in practice and who owns it.")
                        for i in range(n)]
        topic = self.inp["bank_cats"]["producer"][list(self.inp["bank_cats"]["producer"])[0]]["topic"]
        good = {sid: {"status": "pass", "turns": 1, "candidates": [dict(c, topic=topic) for c in mk(3)]}}
        cases = {
            "too few": {sid: dict(good[sid], candidates=good[sid]["candidates"][:2])},
            "bad capability": {sid: dict(good[sid], candidates=[dict(c, capability="llm") for c in good[sid]["candidates"]])},
            "topic not in categories": {sid: dict(good[sid], candidates=[dict(c, topic="infra") for c in good[sid]["candidates"]])},
            "unknown cis ref": {sid: dict(good[sid], candidates=[dict(c, cis_refs=["LLM-77.7"]) for c in good[sid]["candidates"]])},
            "playbook_ref of another id": {sid: dict(good[sid], candidates=[dict(c, playbook_ref="GOVERN 9.9") for c in good[sid]["candidates"]])},
            "not applicable to bank": {other: good[sid]},
            "review without reason": {sid: {"status": "needs_human_review", "turns": 2, "candidates": []}},
        }
        for name, data in cases.items():
            self.assertEqual(self.run_mode("candidates", data, "consumer" if name == "x" else "producer"), 1, name)
        self.assertEqual(self.run_mode("candidates", good, "producer"), 0)
        bank = json.loads((R.AI_BANKS / "question_bank_ai_rmf_producer.json").read_text())
        self.assertEqual(bank["summary"]["passed"], 1)
        flagged = {sid: {"status": "needs_human_review", "turns": 2, "reason": "evaluator still failed Q2",
                         "candidates": good[sid]["candidates"]}}
        self.assertEqual(self.run_mode("candidates", flagged, "producer"), 0)
        bank = json.loads((R.AI_BANKS / "question_bank_ai_rmf_producer.json").read_text())
        self.assertEqual(bank["summary"], {"subcategories": 1, "passed": 0, "needs_human_review": 1, "candidates": 3})

    def test_notes(self):
        long = "x" * 40
        self.assertEqual(self.run_mode("notes", {"NOT.AA-99": {"exposure": long}}), 1)
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"use": {"base_rag": long, "mcp_agentic": long}}}), 1)  # no exposure yet
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"exposure": long}}), 0)
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"use": {"base_rag": long, "mcp_agentic": long}}}), 0)
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"use": {"base_rag": long}}}), 1)
        n = json.loads(R.CSF_IMPACT_NOTES.read_text())["notes"]["PR.AA-05"]
        self.assertEqual(set(n), {"exposure", "use"})


    def test_prepare_batch_missing_only(self):
        self.assertEqual(self.run_mode("applicability", self.applicability()), 0)
        sid = self.subs[0]
        topic = self.inp["bank_cats"]["consumer"][list(self.inp["bank_cats"]["consumer"])[0]]["topic"]
        mk = [self.candidate(sid, question_text=f"Describe variant {i} of {sid} in practice and who owns it, with evidence.",
                             topic=topic) for i in range(3)]
        self.assertEqual(self.run_mode("candidates", {sid: {"status": "pass", "turns": 1, "candidates": mk}}, "consumer"), 0)
        out = P.prepare_batch(self.inp, "consumer", [], None, True, "t", missing_only=True)
        ids = [i["subcategory_id"] for i in json.loads(out.read_text())["items"]]
        self.assertNotIn(sid, ids)
        self.assertEqual(len(ids), len(self.subs) - 1)

    def test_accept_pilot(self):
        PL.AI_PILOT = self.tmp / "pilot_accepted.json"
        with self.assertRaises(SystemExit):
            PL.accept_pilot("too early")             # no bank has anything recorded yet
        self.assertFalse(PL.AI_PILOT.exists())
        self.assertEqual(self.run_mode("applicability", self.applicability()), 0)
        sid = self.subs[0]
        for bank in ("producer", "consumer"):
            topic = self.inp["bank_cats"][bank][list(self.inp["bank_cats"][bank])[0]]["topic"]
            cands = [self.candidate(sid, question_text=f"Describe variant {i} of {sid} in practice and who owns it, with evidence.",
                                    topic=topic) for i in range(3)]
            self.assertEqual(self.run_mode("candidates", {sid: {"status": "pass", "turns": 1, "candidates": cands}}, bank), 0)
        PL.accept_pilot("looks good")
        doc = json.loads(PL.AI_PILOT.read_text())
        self.assertEqual(doc["recorded"], {"producer": 1, "consumer": 1})
        self.assertEqual(set(doc["prompts"]), set(DEFAULT_PROMPTS["candidates"]))
        self.assertTrue(all(doc["prompts"].values()))

    def test_assemble_turns(self):
        def cands(n):
            return [self.candidate("X", question_text=f"Describe variant {i} of the practice and who owns it, with evidence.") for i in range(n)]
        def w(name, obj):
            (self.tmp / name).write_text(json.dumps(obj))
            return self.tmp / name
        gen1 = w("g1.json", {"A": {"candidates": cands(3)}, "B": {"candidates": cands(4)}, "C": {"candidates": cands(3)}})
        eval1 = w("e1.json", [{"subcategory_id": "B", "question_number": 2, "check": 1, "reason": "yes/no"},
                              {"subcategory_id": "C", "question_number": 1, "check": 4, "reason": "vague"}])
        gen2 = w("g2.json", {"B": {"candidates": cands(4)}, "C": {"candidates": cands(3)}})
        eval2 = w("e2.json", [{"subcategory_id": "C", "question_number": 1, "check": 4, "reason": "still vague"}])
        out = self.tmp / "assembled.json"
        R.assemble(gen1, eval1, gen2, eval2, out)
        r = json.loads(out.read_text())
        self.assertEqual((r["A"]["status"], r["A"]["turns"]), ("pass", 1))
        self.assertEqual((r["B"]["status"], r["B"]["turns"]), ("pass", 2))
        self.assertEqual((r["C"]["status"], r["C"]["turns"]), ("needs_human_review", 2))
        self.assertIn("still vague", r["C"]["reason"])
        R.assemble(gen1, w("e0.json", []), None, None, out)   # nothing failed on turn 1: all pass
        self.assertTrue(all(v["status"] == "pass" and v["turns"] == 1 for v in json.loads(out.read_text()).values()))
        with self.assertRaises(SystemExit):
            R.assemble(gen1, w("e9.json", [{"subcategory_id": "Z", "question_number": 1, "reason": "x"}]), None, None, out)


import build_ai_questions as BQ  # noqa: E402
import check_freshness as CF  # noqa: E402


class Scope(unittest.TestCase):
    """build_ai_questions.py on a synthetic bank (the real bank does not exist until the build)."""

    A, B, C, D, E = "GOVERN 1.1", "MEASURE 2.7", "MANAGE 2.3", "GOVERN 1.6", "MAP 1.1"

    def cand(self, sid, text, **over):
        c = {"question_text": f"Describe how your organisation handles {text} for {sid}, who owns it and what evidence exists.",
             "playbook_ref": f"{sid} — suggested action 1", "cis_refs": [], "scope_tags": [], "capability": "base",
             "topic": "governance"}
        c.update(over)
        return c

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        A, B, C, D, E = self.A, self.B, self.C, self.D, self.E
        bank = {"subcategories": {
            A: {"categories": ["gov_accountability"], "status": "pass", "turns": 1,
                "candidates": [self.cand(A, f"topic {i}") for i in range(3)]},
            B: {"categories": ["data_exposure"], "status": "pass", "turns": 1,
                "candidates": [self.cand(B, "data flows", topic="data_model"),
                               self.cand(B, "retention", topic="data_model", scope_tags=["customer_facing"]),
                               self.cand(B, "weights", topic="data_model", modifiers=["self_hosted"])]},
            C: {"categories": ["ai_access_identity"], "status": "needs_human_review", "turns": 2,
                "candidates": [self.cand(C, "tool permissions", topic="ai_access", capability="mcp"),
                               self.cand(C, "agent approvals", topic="ai_access", capability="agentic")]},
            D: {"categories": ["inventory_shadow_ai"], "status": "pass", "turns": 1,
                "candidates": [self.cand(D, "shadow tools", modifiers=["unsanctioned_use"]), self.cand(D, "inventory")]},
            E: {"categories": ["use_context_impact"], "status": "pass", "turns": 1,
                "candidates": [self.cand(E, "intended use")]}}}
        producer_cat = {"data_exposure": "model_assets_ip", "ai_access_identity": "ai_access_tools",
                        "inventory_shadow_ai": "upstream_models", "use_context_impact": "intended_use_impact"}
        self.banks = {}
        for b in ("consumer", "producer"):
            p = self.tmp / f"bank_{b}.json"
            doc = json.loads(json.dumps(bank))
            if b == "producer":
                for sub in doc["subcategories"].values():
                    sub["categories"] = [producer_cat.get(c, c) for c in sub["categories"]]
            p.write_text(json.dumps(doc))
            self.banks[b] = p
        BQ.ai_bank_path = lambda b: self.banks[b]
        self.run = self.tmp / "run"
        self.run.mkdir()

    def profile(self, **over):
        p = {"ai_in_use": "some", "role": "consumer", "rung": "base", "usage_contexts": ["internal"],
             "modifiers": [], "engagement_flags": {"csf_assessment_done": True, "iso27001_held": False, "iso42001_held": False},
             "captured_on": "2026-10-14"}
        p.update(over)
        return p

    def go(self, profile):
        (self.run / "ai_usage.json").write_text(json.dumps(profile))
        sys.argv = ["x", str(self.run)]
        try:
            BQ.main()
        except SystemExit as e:
            return e.code
        return 0

    def scope(self, bank="consumer"):
        return {e["subcategory_id"]: e for e in json.loads((self.run / "ai_scope.json").read_text())["banks"][bank]}

    def draft(self, bank="consumer"):
        return {e["subcategory_id"]: e for e in json.loads((self.run / f"ai_questions_draft_{bank}.json").read_text())}

    def test_gap_at_topic_level_and_filters(self):
        self.assertEqual(self.go(self.profile()), 0)
        s, d = self.scope(), self.draft()
        self.assertEqual(s[self.A]["question_type"], "full_discovery")   # governance topic
        self.assertEqual(s[self.B]["question_type"], "gap")              # CSF done, data_model
        self.assertTrue(d[self.B]["questions"][0]["question_text"].startswith("General security controls (CSF assessment)"))
        texts = " ".join(q["question_text"] for q in d[self.B]["questions"])
        self.assertNotIn("retention", texts)   # customer_facing candidate dropped for an internal-only org
        self.assertNotIn("weights", texts)     # self_hosted candidate dropped: modifier not held
        self.assertNotIn(self.C, d)            # mcp/agentic candidates dropped at the base rung: no fallback invented
        self.assertEqual(len(d[self.A]["questions"]), 3)

    def test_rung_modifiers_and_review_flag(self):
        self.assertEqual(self.go(self.profile(rung="agentic", usage_contexts=["customer_facing"], modifiers=["self_hosted"])), 0)
        d = self.draft()
        self.assertEqual(len(d[self.C]["questions"]), 2)
        self.assertTrue(d[self.C]["confidence_flag"].startswith("LOW"))
        self.assertEqual(d[self.B]["questions"][0]["question_text"].count("retention"), 1)  # tag match ranks first
        self.assertEqual(len(d[self.B]["questions"]), 3)

    def test_no_flags_means_full_discovery(self):
        flags = {"csf_assessment_done": False, "iso27001_held": False, "iso42001_held": True}
        self.assertEqual(self.go(self.profile(engagement_flags=flags)), 0)
        self.assertEqual(self.scope()[self.B]["question_type"], "full_discovery")  # 42001 does not relax anything

    def test_none_keeps_only_the_shadow_ai_check(self):
        self.assertEqual(self.go(self.profile(ai_in_use="none", role=None, rung=None, usage_contexts=[])), 0)
        s, d = self.scope(), self.draft()
        self.assertEqual({k for k, v in s.items() if v["question_type"] != "skip"}, {self.D})
        self.assertEqual(list(d), [self.D])
        self.assertEqual(len(d[self.D]["questions"]), 1)   # only the unsanctioned_use candidate
        self.assertIn("No AI use declared", d[self.D]["usage_note"])

    def test_unsure_discovers_first(self):
        self.assertEqual(self.go(self.profile(ai_in_use="unsure", role=None, rung=None, usage_contexts=[])), 0)
        s = self.scope()
        self.assertEqual(s[self.D]["question_type"], "full_discovery")
        self.assertEqual(s[self.E]["state"], "forced")       # MAP function forced
        self.assertEqual(s[self.B]["question_type"], "gap")   # topic policy still applies
        self.assertEqual(self.scope()[self.A]["usage_note"], "AI use unconfirmed: discover what AI is in use before assuming any")

    def test_role_both_writes_both_banks(self):
        self.assertEqual(self.go(self.profile(role="both", modifiers=["builds_on_base_model"])), 0)
        self.assertTrue((self.run / "ai_questions_draft_producer.json").is_file())
        self.assertTrue((self.run / "ai_questions_draft_consumer.json").is_file())

    def test_ai_draft_goes_through_the_existing_assessor_patch_merge(self):
        import record_judgements as RJ
        self.assertEqual(self.go(self.profile()), 0)
        draft = json.loads((self.run / "ai_questions_draft_consumer.json").read_text())
        changed = json.loads(json.dumps(draft[0]))
        changed["questions"][0]["question_text"] += " Who signs off?"
        changed["assessor_note"] = "Added an ownership prompt."
        (self.run / "patch.json").write_text(json.dumps([changed]))
        RJ.log_run_step([str(self.run), "--step", "ai_assessor_consumer", "--base", "ai_questions_draft_consumer.json",
                         "--patch", "patch.json", "--output", "ai_questions_assessed_consumer.json", "--model", "test"])
        merged = json.loads((self.run / "ai_questions_assessed_consumer.json").read_text())
        self.assertEqual(len(merged), len(draft))
        self.assertEqual(merged[0]["assessor_note"], "Added an ownership prompt.")
        self.assertTrue(list((self.run / "judgement_log").glob("*ai_assessor_consumer.json")))
        # one workbook for the client: the CSF sheet first, then one AI sheet holding both banks with a Role column
        import openpyxl
        import write_questionnaire as WQ
        csf = [{"subcategory_id": "GV.RM-01", "function": "GV", "outcome": "o", "question_type": "full_discovery",
                "questions": [{"question_text": "How is risk managed?", "source_reference": "CSET: 1"}],
                "evidence_prompt": "ep", "confidence_flag": ""}]
        (self.run / "csf_final.json").write_text(json.dumps(csf))
        out = self.run / "questionnaire.xlsx"
        self.assertEqual(self.go(self.profile(role="both", modifiers=["builds_on_base_model"])), 0)
        finals = []
        for bank in ("consumer", "producer"):
            entries = json.loads((self.run / f"ai_questions_draft_{bank}.json").read_text())
            self.assertTrue(all(e["bank"] == bank for e in entries))
            f = self.run / f"ai_final_{bank}.json"
            f.write_text(json.dumps(entries))
            finals.append(str(f))
        for argv in (["x", str(self.run / "csf_final.json"), str(out)],
                     ["x", *finals, str(out), "--framework", "ai"],
                     ["x", *finals, str(out), "--framework", "ai"]):   # the last call replaces the AI sheet
            sys.argv = argv
            WQ.main()
        wb = openpyxl.load_workbook(out)
        self.assertEqual(wb.sheetnames, ["CSF Questionnaire", "AI RMF Questionnaire"])
        ws = wb["AI RMF Questionnaire"]
        header = [c.value for c in ws[1]]
        roles = {row[header.index("Role")].value for row in ws.iter_rows(min_row=2)}
        self.assertEqual(roles, {"producer", "consumer"})
        rows = [(r[1].value, r[2].value) for r in ws.iter_rows(min_row=2)]
        self.assertEqual(rows, sorted(rows, key=lambda t: (t[0], t[1] != "producer")))   # sorted, producer before consumer
        sys.argv = ["x", str(self.run / "csf_final.json"), finals[0], str(out)]
        with self.assertRaises(SystemExit):   # csf mode takes exactly one question file
            WQ.main()

    def test_bank_with_unknown_category_fails_loudly(self):
        doc = json.loads(self.banks["consumer"].read_text())
        doc["subcategories"][self.A]["categories"] = ["removed_category"]
        self.banks["consumer"].write_text(json.dumps(doc))
        self.assertIn("rebuild the bank", str(self.go(self.profile())))
        self.assertFalse((self.run / "ai_scope.json").exists())

    def test_invalid_profiles_are_rejected_and_write_nothing(self):
        for bad in (self.profile(ai_in_use="maybe"), self.profile(rung="llm"), self.profile(role=None),
                    self.profile(usage_contexts=["mobile"]), self.profile(modifiers=["builds_on_base_model"]),
                    self.profile(engagement_flags={"csf_assessment_done": True})):
            self.assertEqual(self.go(bad), 1, bad)
            self.assertFalse((self.run / "ai_scope.json").exists())



class Mapping(unittest.TestCase):
    """prepare_ai_bank.py mapping and record_ai_bank.py mapping, on the real AI areas and mapping rules (read only)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        R.AI_MAPPING, R.AI_BUILD, R.LOG_DIR = self.tmp / "mapping.json", self.tmp / "build", self.tmp / "build" / "log"
        P.AI_BUILD = R.AI_BUILD
        R.AI_BUILD.mkdir(parents=True, exist_ok=True)
        self.inp = R.load_inputs()

    def row(self, function, sub, cis=(), impact=("access",), why=None):
        return {"function": function, "subcategory": sub, "cis_refs": list(cis), "impact": list(impact),
                "why": why or f"{sub} checks how the org handles MCP servers and tool credentials."}

    def good(self):
        return {"area": "mcp_tools", "rows": [
            self.row("GOVERN", "GOVERN 1.6", ["MCP-2.1", "MCP-2.3"]),
            self.row("MAP", "MAP 2.2"),
            self.row("MEASURE", "MEASURE 2.7", ["MCP-6.8"]),
            self.row("MEASURE", "MEASURE 2.8", ["MCP-8.2"]),
            self.row("MANAGE", "MANAGE 2.4", ["MCP-6.2"]),
            self.row("MANAGE", "MANAGE 4.3"),
        ], "no_question": []}

    def go(self, data, review=None):
        f = self.tmp / "draft.json"
        f.write_text(json.dumps(data))
        rv = None
        if review is not None:
            rv = self.tmp / "review.json"
            rv.write_text(json.dumps(review))
        a = argparse.Namespace(file=str(f), review=str(rv) if rv else None, model="test-model", session=None, prompt=None)
        try:
            R.record("mapping", a)
            return 0
        except SystemExit as e:
            return e.code

    def test_prepare_gives_only_the_areas_candidates(self):
        out = P.prepare_mapping(self.inp, "mcp_tools")
        doc = json.loads(out.read_text())
        rules = json.loads(R.AI_MAPPING_RULES.read_text())
        allowed = set(rules["area_cis"]["mcp_tools"]["controls"]) | {int(n) for n in rules["always_cis_controls"]["controls"]}
        cand = doc["cis_candidates"]
        self.assertTrue(cand and all(c["id"].startswith("MCP-") for c in cand))
        self.assertTrue(all(int(c["id"].split("-")[1].split(".")[0]) in allowed for c in cand))
        self.assertEqual(sum(len(v) for v in doc["subcategories"].values()), 72)
        self.assertIn("audit trail", [c["name"] for c in doc["rules"]["required_checks"]])

    def test_mapping_rules_match_the_cis_guides(self):
        from ai_bank_common import check_mapping_rules
        rules = json.loads(R.AI_MAPPING_RULES.read_text())
        self.assertEqual(check_mapping_rules(rules, self.inp), [])
        bad = json.loads(json.dumps(rules))
        bad["always_cis_controls"]["controls"]["8"] = "Data Protection"      # wrong name for control 8
        bad["always_cis_controls"]["controls"]["19"] = "No such control"     # CIS v8.1 has 18 controls
        bad["area_cis"]["mcp_tools"]["controls"].append(42)
        problems = check_mapping_rules(bad, self.inp)
        self.assertTrue(any("8" in p and "Audit Log Management" in p for p in problems), problems)
        self.assertTrue(any("19" in p for p in problems) and any("mcp_tools" in p and "42" in p for p in problems))

    def test_bad_drafts_are_rejected_and_nothing_is_stored(self):
        g = self.good()
        rows = g["rows"]
        cases = {
            "unknown subcategory": [self.row("MAP", "MAP 9.9")] + rows,
            "subcategory of another function": [self.row("MAP", "GOVERN 2.1")] + rows,
            "safeguard not a candidate": [self.row("MAP", "MAP 3.5", ["LLM-3.1"])] + rows,
            "impact the area does not have": [self.row("MAP", "MAP 3.5", impact=["data"])] + rows,
            "repeated row": rows + [rows[0]],
            "short why": [self.row("MAP", "MAP 3.5", why="tools")] + rows,
            "missing function": [r for r in rows if r["function"] != "MANAGE"],
            "missing audit trail": [r for r in rows if r["subcategory"] != "MEASURE 2.8"],
            "audit row without a control 8 safeguard": [dict(r, cis_refs=["MCP-6.8"]) if r["subcategory"] == "MEASURE 2.8"
                                                        else r for r in rows],
            "missing inventory": [r for r in rows if r["subcategory"] != "GOVERN 1.6"],
            "too many rows": rows + [self.row("MEASURE", f"MEASURE 2.{i}") for i in range(1, 8)],
        }
        for name, rs in cases.items():
            self.assertEqual(self.go(dict(g, rows=rs)), 1, name)
            self.assertFalse(R.AI_MAPPING.exists(), name)
        self.assertEqual(self.go(dict(g, area="no_such_area")), 1)
        self.assertEqual(self.go(g, review=[{"function": "MAP", "subcategory": "MAP 9.9", "reason": "x"}]), 1)
        self.assertEqual(self.go(dict(g, rows=[r for r in rows if r["function"] != "MAP"],
                                      no_question=[{"function": "MAP", "reason": "Nothing about the tools' context here."}])), 0)

    def test_recorded_with_review_and_coverage(self):
        review = [{"function": "MEASURE", "subcategory": "MEASURE 2.7", "reason": "Too generic for tool credentials."}]
        self.assertEqual(self.go(self.good(), review=review), 0)
        doc = json.loads(R.AI_MAPPING.read_text())
        rows = {r["subcategory"]: r for r in doc["areas"]["mcp_tools"]["rows"]}
        self.assertEqual(rows["MEASURE 2.7"]["status"], "needs_human_review")
        self.assertEqual(rows["GOVERN 1.6"]["status"], "pass")
        self.assertEqual(doc["areas"]["mcp_tools"]["inputs"]["ai_areas"], R.audit.sha(R.AI_AREAS))
        rules = json.loads(R.AI_MAPPING_RULES.read_text())
        reached, unreached = R.mapping_coverage(doc, self.inp, rules)
        self.assertIn("GOVERN 4.1", reached)            # org-wide
        self.assertIn("MEASURE 2.11", unreached)
        self.assertEqual(len(reached) + len(unreached), 72)
        self.assertEqual(len(list(R.LOG_DIR.glob("*_mapping_mcp_tools.json"))), 1)


class FreshnessGate(unittest.TestCase):
    """check_freshness.py --ai-bank compares source hashes with what each output recorded about its inputs."""

    def setUp(self):
        import audit
        self.audit = audit
        self.tmp = Path(tempfile.mkdtemp())
        cfg = json.loads(CF.AI_PARSE_CONFIG.read_text())
        self.src = self.tmp / "source"
        self.src.mkdir()
        self.files = {"playbook": cfg["playbook"]["file"], **{g: c["file"] for g, c in cfg["guides"].items()}}
        for name in list(self.files.values()) + ["mapping.xlsx"]:
            (self.src / name).write_text(f"content of {name}")
        CF.AI_SOURCE, CF.AI_CIS_CSF_XLSX = self.src, self.src / "mapping.xlsx"
        CF.AI_CORE, CF.AI_SAFEGUARDS = self.tmp / "core.json", self.tmp / "sg.json"
        CF.AI_APPLICABILITY, CF.AI_CROSSWALK_CIS = self.tmp / "app.json", self.tmp / "xw.json"
        CF.AI_BANKS, CF.CSF_IMPACT_NOTES = self.tmp / "banks", self.tmp / "notes.json"
        CF.AI_PILOT = self.tmp / "pilot.json"
        CF.AI_AREAS, CF.AI_AREAS_XLSX = self.tmp / "ai_areas.json", self.tmp / "ai_areas.xlsx"
        CF.AI_BANKS.mkdir()

    def sha(self, name):
        return self.audit.sha(self.src / name)

    def accept_pilot(self):
        CF.AI_PILOT.write_text(json.dumps({"accepted_on": "2026-10-14", "prompts": {
            p: self.audit.sha(REPO_ROOT / p) for p in DEFAULT_PROMPTS["candidates"]}}))

    def build_everything(self, applicable=2, recorded=2):
        pb = self.sha(self.files["playbook"])
        g = {k: self.sha(self.files[k]) for k in ("LLM", "MCP", "AGENT")}
        CF.AI_CORE.write_text(json.dumps({"source_sha256_16": pb}))
        CF.AI_SAFEGUARDS.write_text(json.dumps({"sources": {k: {"sha256_16": v} for k, v in g.items()}}))
        subs = {f"S{i}": {"producer": ["c"], "consumer": ["c"]} for i in range(applicable)}
        CF.AI_APPLICABILITY.write_text(json.dumps({"source_sha256_16": pb, "categories_sha": self.audit.sha(CF.AI_CATEGORIES),
                                                   "subcategories": subs}))
        CF.AI_CROSSWALK_CIS.write_text(json.dumps({"guide_sha256_16": g}))
        for bank in ("producer", "consumer"):
            (CF.AI_BANKS / f"question_bank_ai_rmf_{bank}.json").write_text(json.dumps({
                "playbook_sha256_16": pb, "guide_sha256_16": g, "subcategories": {f"S{i}": {} for i in range(recorded)},
                "summary": {"needs_human_review": 1}}))
        CF.CSF_IMPACT_NOTES.write_text(json.dumps({"sources_sha256_16": {"cis_csf": self.sha("mapping.xlsx"),
                                                                         "MCP": g["MCP"], "AGENT": g["AGENT"]}}))
        self.accept_pilot()
        CF.AI_AREAS_XLSX.write_text("a spreadsheet")
        CF.AI_AREAS.write_text(json.dumps({"source_sha": self.audit.sha(CF.AI_AREAS_XLSX)}))

    def states(self):
        return {stage: ok for stage, ok, _ in CF.ai_stages()}

    def test_nothing_built_is_not_current_even_though_sources_exist(self):
        s = self.states()
        self.assertTrue(s["parse"] is False and not any(s.values()))

    def test_everything_current(self):
        self.build_everything()
        self.assertTrue(all(self.states().values()), CF.ai_stages())

    def test_incomplete_bank(self):
        self.build_everything(applicable=3, recorded=2)
        s = {stage: (ok, text) for stage, ok, text in CF.ai_stages()}
        self.assertFalse(s["bank consumer"][0])
        self.assertIn("2 of 3", s["bank consumer"][1])
        self.assertTrue(s["crosswalk"][0])

    def test_a_changed_guide_makes_only_its_dependents_stale(self):
        self.build_everything()
        (self.src / self.files["LLM"]).write_text("changed")
        s = self.states()
        self.assertFalse(s["parse"] or s["crosswalk"] or s["bank producer"] or s["bank consumer"])
        self.assertTrue(s["applicability"] and s["notes"])   # notes use only the MCP and agents guides

    def test_changed_categories_make_applicability_stale(self):
        self.build_everything()
        a = json.loads(CF.AI_APPLICABILITY.read_text())
        a["categories_sha"] = "0" * 16
        CF.AI_APPLICABILITY.write_text(json.dumps(a))
        self.assertFalse(self.states()["applicability"])

    def test_missing_source_stops_everything(self):
        self.build_everything()
        (self.src / self.files["MCP"]).unlink()
        stages = CF.ai_stages()
        self.assertEqual([s[0] for s in stages], ["sources"])
        self.assertIn("MCP", stages[0][2])

    def test_ai_areas_stage(self):
        self.build_everything()
        self.assertTrue(self.states()["ai areas"])
        CF.AI_AREAS_XLSX.write_text("edited, not imported")
        stages = {s: (ok, text) for s, ok, text in CF.ai_stages()}
        self.assertFalse(stages["ai areas"][0])
        self.assertIn("sheet_io.py import ai_areas", stages["ai areas"][1])

    def test_pilot_stage(self):
        self.build_everything()
        self.assertTrue(self.states()["pilot"])
        CF.AI_PILOT.unlink()
        self.assertFalse(self.states()["pilot"])
        self.accept_pilot()
        doc = json.loads(CF.AI_PILOT.read_text())
        doc["prompts"][DEFAULT_PROMPTS["candidates"][0]] = "0" * 16   # the generator prompt was edited after acceptance
        CF.AI_PILOT.write_text(json.dumps(doc))
        stages = {s: (ok, text) for s, ok, text in CF.ai_stages()}
        self.assertFalse(stages["pilot"][0])
        self.assertIn("prompt changed", stages["pilot"][1])


class CsfBankStage(unittest.TestCase):
    """check_freshness.csf_bank_stage against throwaway git repos standing in for the CSET clone and its remote."""

    def git(self, cwd, *args):
        import subprocess
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
               "PATH": "/usr/bin:/bin:/opt/homebrew/bin", "HOME": str(self.tmp)}
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def commit(self, repo, rel, text):
        f = Path(repo) / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "c")
        return self.git(repo, "rev-parse", "HEAD")

    def setUp(self):
        import extract_cset_candidates as EX
        self.EX = EX
        self.tmp = Path(tempfile.mkdtemp())
        self.origin, self.clone = self.tmp / "origin", self.tmp / "clone"
        self.origin.mkdir()
        self.git(self.origin, "init", "-q", "-b", "main")
        self.base = self.commit(self.origin, f"{EX.SQL_SUBPATH}/1_data.sql", "-- v1")
        self.git(self.tmp, "clone", "-q", str(self.origin), str(self.clone))
        self.bank = self.tmp / "bank.json"
        CF.bank_path = lambda domain: self.bank

    def write_bank(self, commit):
        self.bank.write_text(json.dumps({"cset_commit": commit}))

    def stage(self):
        (stage, ok, text), notes = CF.csf_bank_stage("finance", self.clone)
        return ok, text, notes

    def test_missing_current_and_stale(self):
        self.assertEqual(self.stage()[:2], (False, "missing"))
        self.write_bank(self.base)
        self.assertEqual(self.stage()[:2], (True, "current"))
        self.commit(self.origin, "docs/readme.md", "x")                    # upstream moved, no migration SQL changed
        ok, text, notes = self.stage()
        self.assertTrue(ok and "no SQL changed" in text and not notes)
        self.commit(self.origin, f"{self.EX.SQL_SUBPATH}/2_data.sql", "-- v2")   # a migration changed
        ok, text, _ = self.stage()
        self.assertFalse(ok)
        self.assertIn("SQL changed", text)

    def test_unrelated_sql_elsewhere_does_not_make_the_bank_stale(self):
        self.write_bank(self.base)
        self.commit(self.origin, "DatabaseScripts/Clean-out.sql", "-- maintenance")
        self.assertTrue(self.stage()[0])

    def test_fetch_failure_is_reported_not_fatal(self):
        import shutil
        self.write_bank(self.base)
        shutil.rmtree(self.origin)
        ok, text, notes = self.stage()
        self.assertTrue(ok)                       # compared with the local commit instead
        self.assertTrue(notes and "could not check upstream" in notes[0])


class CsfBankRecording(unittest.TestCase):
    """Characterisation of record_judgements.py bank mode (it shares its recording skeleton with record_ai_bank.py)."""

    def setUp(self):
        import record_judgements as RJ
        self.RJ = RJ
        self.cache = Path(tempfile.mkdtemp())
        q = lambda text, flags: {"question_text": text, "title": "t", "category": "c", "sub_category": "s", "model_id": "1",
                                 "model_name": "ACET", "is_answerable": None, "practice": {}, "flags": flags}
        (self.cache / "cset_candidates.json").write_text(json.dumps({
            "cset_commit": "abc123", "questions": {"1": q("Management is accountable for risk", ["statement_only"]),
                                                   "2": q("Is risk reviewed annually?", [])},
            "mappings": [{"qid": 1, "subcategory_id": "GV.RM-01"}, {"qid": 2, "subcategory_id": "GV.RM-01"}]}))

    def run_main(self, verdicts):
        f = self.cache / "verdicts.json"
        f.write_text(json.dumps(verdicts))
        sys.argv = ["x", str(f), "--cache-dir", str(self.cache), "--model", "test-model", "--session", "s1"]
        try:
            self.RJ.main()
            return 0
        except SystemExit as e:
            return e.code

    def test_reject_then_record(self):
        bad = {"1": {"rewrite": "too short"}, "9": {"domains": ["finance"], "reason": "x"},
               "2": {"fit": {"GV.RM-01": {"verdict": "maybe"}}}}
        self.assertEqual(self.run_main(bad), 1)
        self.assertFalse((self.cache / "cset_judgements.json").exists())
        good = {"1": {"rewrite": "Is management accountable for cybersecurity risk, and how is that shown?",
                      "domains": ["finance", "other"], "reason": "ACET statement"},
                "2": {"fit": {"GV.RM-01": {"verdict": "accept", "reason": "tests the outcome"}}}}
        self.assertEqual(self.run_main(good), 0)
        store = json.loads((self.cache / "cset_judgements.json").read_text())["questions"]
        self.assertEqual(store["1"]["domains"], ["finance", "other"])
        self.assertEqual(store["2"]["fit"]["GV.RM-01"]["verdict"], "accept")
        self.assertTrue(store["1"]["text_hash"] and store["1"]["judged_on"] and store["1"]["decided_by"] == "agent")
        logs = list((self.cache / "judgement_log").glob("*_2q.json"))
        self.assertEqual(len(logs), 1)
        rec = json.loads(logs[0].read_text())
        for key in ("cset_commit", "decided_by", "model", "session", "prompts", "input_file", "store", "verdicts"):
            self.assertIn(key, rec)
        self.assertEqual(rec["verdicts"], good)
        lines = [json.loads(l) for l in (self.cache / "audit.jsonl").read_text().splitlines()]
        self.assertEqual([l["status"] for l in lines], ["rejected", "ok"])
        self.assertEqual({l["actor"] for l in lines}, {"agent"})


if __name__ == "__main__":
    unittest.main()
