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
from ai_bank_common import DEFAULT_PROMPTS, core_subcategories  # noqa: E402
from paths import AI_AREAS, AI_CORE, AI_MAPPING, AI_SAFEGUARDS, REPO_ROOT  # noqa: E402


class ParsedSources(unittest.TestCase):
    def test_playbook(self):
        core = json.loads(AI_CORE.read_text())
        fns = core["functions"]
        self.assertEqual([f["id"] for f in fns], ["GOVERN", "MAP", "MEASURE", "MANAGE"])
        self.assertTrue(all(len(f["description"]) > 20 for f in fns))
        self.assertIn("Policies, processes, procedures and practices", fns[0]["description"])
        self.assertTrue(all(s["function"] == f["id"] for f in fns for s in f["subcategories"]))
        self.assertEqual(len(fns[0]["subcategories"]), 19)
        subs = core_subcategories(core)
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
        R.CSF_IMPACT_NOTES = self.tmp / "ai_impact_notes.json"
        R.AI_BANKS, R.AI_BUILD, R.LOG_DIR = self.tmp / "banks", self.tmp / "build", self.tmp / "build" / "log"
        R.AI_MAPPING = AI_MAPPING                   # the accepted mapping, read only (other classes redirect it)
        P.AI_BANKS, P.AI_BUILD, PL.AI_BANKS = R.AI_BANKS, R.AI_BUILD, R.AI_BANKS
        self.addCleanup(setattr, P, "mapping_status", P.mapping_status)   # tests stub the accept gate
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

    def question(self, sid, n=1, **over):
        q = {"question_text": f"For your highest-criticality AI systems, how is the outcome of {sid} handled (variant {n}), "
                              "and who owns it?",
             "playbook_refs": [f"{sid} — suggested action 1"], "cis_refs": [], "roles": ["consumer", "producer"],
             "producer_flags": []}
        q.update(over)
        return q

    def area_questions(self, sid):
        """Questions that cover every row of sid once per allowed role: one question per distinct set of roles."""
        rows = R.question_context(self.inp)["rows"][sid]
        groups = {}
        for rid, r in rows.items():
            groups.setdefault(tuple(r["roles"]), []).append(rid)
        qs = []
        for n, (roles, rids) in enumerate(groups.items(), 1):
            folds = sorted({f for rid in rids for f in rows[rid]["folded"]})
            qs.append(self.question(sid, n, rows=rids, roles=list(roles),
                                    playbook_refs=[f"{x} — suggested action 1" for x in [sid] + folds]))
        return qs

    def test_questions_areas(self):
        ctx = R.question_context(self.inp)
        sid = "MEASURE 2.8"                                          # 14 areas, incl. invisible_usage (none) and model
        qs = self.area_questions(sid)
        good = {sid: {"status": "pass", "turns": 1, "questions": qs}}
        model_row = "model|MEASURE 2.8"
        q_model = next(q for q in qs if model_row in q["rows"])
        some_row = next(r for r in ctx["rows"][sid] if ctx["rows"][sid][r]["cis_refs"])
        bad = lambda **k: {sid: dict(good[sid], questions=[dict(qs[0], **k)] + qs[1:])}   # noqa: E731
        cases = {
            "row asked three times": {sid: dict(good[sid], questions=qs + [
                self.question(sid, n, rows=[model_row], roles=["producer"]) for n in (8, 9)])},
            "row not asked": {sid: dict(good[sid], questions=[dict(q_model, rows=[model_row])] +
                                        [q for q in qs if q is not q_model])},
            "role the area does not allow": {sid: dict(good[sid], questions=[dict(q_model, roles=["consumer", "producer"])]
                                                       + [q for q in qs if q is not q_model])},
            "unknown row": bad(rows=qs[0]["rows"] + ["agent|MAP 1.1"]),
            "cis ref not of the rows": bad(cis_refs=["LLM-77.7"]),
            "no such suggested action": bad(playbook_refs=[f"{sid} — suggested action 99"]),
            "playbook ref of another subcategory": bad(playbook_refs=["GOVERN 1.1 — suggested action 1"]),
            "flag on a consumer question": bad(producer_flags=["given_to_others"]),
            "unknown flag": {sid: dict(good[sid], questions=[dict(q_model, producer_flags=["open_weights"])]
                                       + [q for q in qs if q is not q_model])},
            "missing field": bad(rows=None),
            "foundation subcategory": {"GOVERN 1.1": good[sid]},
            "review without reason": {sid: dict(good[sid], status="needs_human_review", turns=2)},
        }
        cases["missing field"][sid]["questions"][0].pop("rows")
        for name, data in cases.items():
            self.assertEqual(self.run_mode("questions", data, "areas"), 1, name)
        self.assertEqual(self.run_mode("questions", good, "areas"), 0)
        bank = json.loads((R.AI_BANKS / "question_bank_ai_rmf_areas.json").read_text())
        self.assertEqual(bank["summary"], {"subcategories": 1, "passed": 1, "needs_human_review": 0, "questions": len(qs)})
        self.assertTrue(bank["subcategories"][sid]["rows_sha"])
        cited = [dict(q, cis_refs=ctx["rows"][sid][some_row]["cis_refs"][:1]) if some_row in q["rows"] else q for q in qs]
        self.assertEqual(self.run_mode("questions", {sid: dict(good[sid], questions=cited)}, "areas"), 0)
        split = qs + [self.question(sid, 9, rows=[model_row], roles=["producer"])]   # a row split in two questions
        self.assertEqual(self.run_mode("questions", {sid: dict(good[sid], questions=split)}, "areas"), 0)
        flagged = [dict(q_model, producer_flags=["built_on_existing_model"])] + [q for q in qs if q is not q_model]
        self.assertEqual(self.run_mode("questions", {sid: dict(good[sid], questions=flagged)}, "areas"), 0)

    def test_questions_area_folds(self):
        sid = "MAP 3.2"                                              # internal_process folds MAP 5.1 into it
        qs = self.area_questions(sid)
        self.assertEqual(self.run_mode("questions", {sid: {"status": "pass", "turns": 1, "questions": qs}}, "areas"), 0)
        unfolded = [dict(q, playbook_refs=[f"{sid} — suggested action 1"]) for q in qs]
        self.assertEqual(self.run_mode("questions", {sid: {"status": "pass", "turns": 1, "questions": unfolded}}, "areas"), 1)
        folding = next(q for q in qs if len(q["playbook_refs"]) > 1)   # a split row: one of its two questions cites it
        second = self.question(sid, 9, rows=folding["rows"], roles=folding["roles"])
        self.assertEqual(self.run_mode("questions", {sid: {"status": "pass", "turns": 1, "questions": qs + [second]}},
                                       "areas"), 0)

    def test_questions_foundation(self):
        sid = "GOVERN 1.1"
        both = self.question(sid, 1, roles=["none", "consumer", "producer"])
        prod = self.question(sid, 2, roles=["producer"])
        good = {sid: {"status": "pass", "turns": 1, "questions": [both, prod]}}
        cases = {
            "no consumer question": [prod],
            "producer only with a flag": [self.question(sid, 1, roles=["consumer"]),
                                          self.question(sid, 2, roles=["producer"], producer_flags=["given_to_others"])],
            "too many": [self.question(sid, n) for n in range(1, 6)],
            "five shared": [self.question(sid, n) for n in range(1, 5)] + [self.question(sid, 5, roles=["consumer"])],
            "six": [self.question(sid, n) for n in range(1, 5)] + [self.question(sid, n, roles=["producer"])
                                                                   for n in (5, 6)],
            "cis ref": [dict(both, cis_refs=["LLM-3.1"])],
            "unknown role": [dict(both, roles=["vendor"])],
            "rows on a foundation question": [dict(both, rows=[])],
            "same text twice": [both, dict(both)],
        }
        for name, qs in cases.items():
            self.assertEqual(self.run_mode("questions", {sid: dict(good[sid], questions=qs)}, "foundation"), 1, name)
        self.assertEqual(self.run_mode("questions", {"MEASURE 2.8": good[sid]}, "foundation"), 1)   # an area subcategory
        extra = [self.question(sid, n) for n in range(1, 5)] + [self.question(sid, 5, roles=["producer"])]
        self.assertEqual(self.run_mode("questions", {sid: dict(good[sid], questions=extra)}, "foundation"), 0)
        self.assertEqual(self.run_mode("questions", good, "foundation"), 0)
        self.assertEqual(self.run_mode("questions", {"MANAGE 1.2": {"status": "pass", "turns": 1, "questions": [
            self.question("MANAGE 1.2")]}}, "foundation"), 0)          # a foundation subcategory outside GOVERN
        bank = json.loads((R.AI_BANKS / "question_bank_ai_rmf_foundation.json").read_text())
        self.assertEqual(list(bank["subcategories"]), ["GOVERN 1.1", "MANAGE 1.2"])

    def test_bank_freshness(self):
        sid = "MAP 3.2"
        self.assertEqual(self.run_mode("questions", {sid: {"status": "pass", "turns": 1,
                                                           "questions": self.area_questions(sid)}}, "areas"), 0)
        doc = json.loads((R.AI_BANKS / "question_bank_ai_rmf_areas.json").read_text())
        ok, text = R.bank_freshness("areas", doc, self.inp)
        self.assertFalse(ok)
        self.assertIn("40 of 41 subcategories missing", text)
        ctx = R.question_context(self.inp)
        for other in ctx["rows"]:                                    # as if every subcategory were recorded
            doc["subcategories"].setdefault(other, dict(doc["subcategories"][sid], rows_sha=R.rows_sha(
                {r: v["sig"] for r, v in ctx["rows"][other].items()})))
        self.assertTrue(R.bank_freshness("areas", doc, self.inp)[0])
        doc["subcategories"][sid]["rows_sha"] = "changed"           # a mapping row changed after the questions
        ok, text = R.bank_freshness("areas", doc, self.inp)
        self.assertFalse(ok)
        self.assertIn(f"mapping rows changed since written: {sid}", text)

    def test_evidence_prompts_are_added_to_bank_questions_once_checked(self):
        sid = "MEASURE 2.8"                                           # two questions (roles differ by area)
        good = {sid: {"status": "pass", "turns": 1, "questions": self.area_questions(sid)}}
        self.assertEqual(self.run_mode("questions", good, "areas"), 0)
        path = R.AI_BANKS / "question_bank_ai_rmf_areas.json"
        n = len(good[sid]["questions"])
        text = "The intended-use record for one AI system, who owns it, and the list of AI systems it covers."

        def go(data, review):
            f, rv = self.tmp / "evidence.json", self.tmp / "evidence_review.json"
            f.write_text(json.dumps(data))
            rv.write_text(json.dumps(review))
            a = argparse.Namespace(file=str(f), bank="areas", review=str(rv), model="m", session=None, prompt=None)
            try:
                R.record("evidence", a)
                return 0
            except SystemExit as e:
                return e.code
        ok = [{"subcategory_id": sid, "question_number": 1, "verdict": "pass", "reason": ""}]
        for name, data, review in (("unknown question", {sid: {"99": text}}, ok),
                                   ("too short", {sid: {"1": "Records."}}, ok),
                                   ("no verdict", {sid: {"1": text}}, []),
                                   ("fail without reason", {sid: {"1": text}}, [dict(ok[0], verdict="fail")])):
            self.assertEqual(go(data, review), 1, name)
        data = {sid: {str(k): text for k in range(1, n + 1)}}
        review = [dict(ok[0], question_number=k) for k in range(1, n + 1)]
        self.assertGreater(n, 1)
        review[-1] = dict(review[-1], verdict="fail", reason="Check 2: generic.")
        self.assertEqual(go(data, review), 0)
        qs = json.loads(path.read_text())["subcategories"][sid]["questions"]
        self.assertEqual(qs[0]["evidence_prompt"], text)                  # a passing prompt is stored
        self.assertNotIn("evidence_prompt", qs[-1])                       # a failing one is not
        self.assertEqual(go({sid: {"1": text + " Again."}}, ok), 1)       # never overwrites an evidence prompt
        P.AI_BANKS = R.AI_BANKS
        doc = json.loads(P.prepare_evidence(self.inp, "areas").read_text())
        self.assertEqual([q["number"] for q in doc["items"].get(sid, {}).get("questions", [])],
                         [n])                                             # only questions still without one

    def test_notes(self):
        long = "x" * 40
        self.assertEqual(self.run_mode("notes", {"NOT.AA-99": {"exposure": long}}), 1)
        self.assertEqual(self.run_mode("notes", {"DE.CM-01": {"use": {"base_rag": long, "mcp_agentic": long}}}), 0)
        self.assertNotIn("exposure", json.loads(R.CSF_IMPACT_NOTES.read_text())["notes"]["DE.CM-01"])  # exposure optional
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"exposure": long}}), 0)
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"use": {"base_rag": long, "mcp_agentic": long}}}), 0)
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"use": {"base_rag": long}}}), 1)
        n = json.loads(R.CSF_IMPACT_NOTES.read_text())["notes"]["PR.AA-05"]
        self.assertEqual(set(n), {"exposure", "use"})
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"exposure": None}}), 0)      # exposure: null removes it
        self.assertEqual(set(json.loads(R.CSF_IMPACT_NOTES.read_text())["notes"]["PR.AA-05"]), {"use"})
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"use": None}}), 0)          # no note left: dropped
        self.assertNotIn("PR.AA-05", json.loads(R.CSF_IMPACT_NOTES.read_text())["notes"])
        self.assertEqual(self.run_mode("notes-review", [{"subcategory_id": "DE.CM-01", "note": "exposure",
                                                         "reason": "x"}]), 1)   # it has no exposure note

    def test_notes_review(self):
        long = "x" * 40
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"exposure": long},
                                                 "DE.CM-01": {"exposure": long}}), 0)
        notes = lambda: json.loads(R.CSF_IMPACT_NOTES.read_text())["notes"]   # noqa: E731
        bad = {
            "unknown subcategory": [{"subcategory_id": "PR.AA-01", "note": "exposure", "reason": "x"}],
            "use note without a use layer": [{"subcategory_id": "PR.AA-05", "note": "base_rag", "reason": "x"}],
            "unknown note": [{"subcategory_id": "PR.AA-05", "note": "title", "reason": "x"}],
            "no reason": [{"subcategory_id": "PR.AA-05", "note": "exposure", "reason": " "}],
            "not a list": {"PR.AA-05": "x"},
        }
        for name, data in bad.items():
            self.assertEqual(self.run_mode("notes-review", data), 1, name)
        self.assertEqual(self.run_mode("notes-review", [{"subcategory_id": "PR.AA-05", "note": "use",
                                                         "reason": "Check 5: use layer missing."}]), 0)
        self.assertEqual((notes()["PR.AA-05"]["status"], notes()["DE.CM-01"]["status"]), ("needs_human_review", "pass"))
        self.assertEqual(notes()["PR.AA-05"]["review_reason"], "use: Check 5: use layer missing.")
        self.assertEqual(self.run_mode("notes-review", [{"subcategory_id": "DE.CM-01", "note": "exposure",
                                                         "reason": "x"}]), 1)   # reviewed and unchanged: keeps its pass
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"exposure": long + " rewritten",
                                                              "use": {"base_rag": long, "mcp_agentic": long}}}), 0)
        self.assertNotIn("status", notes()["PR.AA-05"])                 # rewritten: to be reviewed again
        self.assertEqual(self.run_mode("notes-review", []), 0)          # round 2 judges only the rewritten note
        self.assertEqual((notes()["PR.AA-05"]["status"], notes()["DE.CM-01"]["status"]), ("pass", "pass"))
        self.assertEqual(self.run_mode("notes", {"PR.AA-05": {"exposure": long, "use": None}}), 0)
        self.assertNotIn("use", notes()["PR.AA-05"])                    # use: null removes the use layer
        doc = json.loads(R.CSF_IMPACT_NOTES.read_text())
        doc["notes"]["DE.CM-01"]["decided_by"] = "human"
        R.CSF_IMPACT_NOTES.write_text(json.dumps(doc))
        self.assertEqual(self.run_mode("notes", {"DE.CM-01": {"exposure": long + " overwritten"}}), 1)
        self.assertEqual(self.run_mode("notes-review", [{"subcategory_id": "DE.CM-01", "note": "exposure",
                                                         "reason": "x"}]), 1)


    def test_prepare_batch_areas(self):
        P.mapping_status = lambda: (True, "accepted")
        out = P.prepare_batch(self.inp, "areas", [], None, True, "t")
        doc = json.loads(out.read_text())
        mapping = json.loads(P.AI_MAPPING.read_text())["areas"]
        want = sorted(f"{a}|{r['subcategory']}" for a, e in mapping.items() for r in e["rows"])
        got = sorted(r["row_id"] for i in doc["items"] for r in i["rows"])
        self.assertEqual(got, want)                                   # every mapping row once, grouped by subcategory
        self.assertTrue(all(r["row_id"].endswith(i["subcategory_id"]) for i in doc["items"] for r in i["rows"]))
        self.assertEqual(set(doc["areas"]), set(mapping))
        self.assertEqual(set(doc["cis_safeguards"]), {c for e in mapping.values() for r in e["rows"] for c in r["cis_refs"]})
        self.assertEqual(doc["areas"]["invisible_usage"]["roles_allowed"], ["none", "consumer", "producer"])
        self.assertEqual(doc["areas"]["model"]["roles_allowed"], ["producer"])
        folds = [f for i in doc["items"] for r in i["rows"] for f in r["folded"]]
        self.assertTrue(folds and all(f["suggested_actions"] for f in folds))   # so a fold's action can be cited
        found = json.loads(P.AI_MAPPING_RULES.read_text())["foundation"]
        self.assertFalse({i["subcategory_id"] for i in doc["items"]} & set(found["subcategories"]))

    def test_prepare_batch_refuses_a_mapping_not_accepted(self):
        P.mapping_status = lambda: (False, "changed since accepted")
        with self.assertRaises(SystemExit):
            P.prepare_batch(self.inp, "areas", [], None, True, "t")

    def test_prepare_batch_foundation_missing_only(self):
        P.mapping_status = lambda: (True, "accepted")
        R.AI_BANKS.mkdir(parents=True, exist_ok=True)
        (R.AI_BANKS / "question_bank_ai_rmf_foundation.json").write_text(json.dumps({"subcategories": {"GOVERN 1.1": {}}}))
        out = P.prepare_batch(self.inp, "foundation", [], "GOVERN", False, "t", missing_only=True)
        ids = [i["subcategory_id"] for i in json.loads(out.read_text())["items"]]
        self.assertEqual(len(ids), 18)                               # 19 GOVERN subcategories, one recorded
        self.assertNotIn("GOVERN 1.1", ids)
        out = P.prepare_batch(self.inp, "foundation", [], None, True, "all")
        self.assertEqual(len(json.loads(out.read_text())["items"]), 31)   # GOVERN + the 12 foundation subcategories
        with self.assertRaises(SystemExit):
            P.prepare_batch(self.inp, "foundation", ["MAP 1.1"], None, False, "t")   # an area subcategory

    def test_accept_pilot(self):
        PL.AI_PILOT = self.tmp / "pilot_accepted.json"
        with self.assertRaises(SystemExit):
            PL.accept_pilot("too early")             # no bank has anything recorded yet
        self.assertFalse(PL.AI_PILOT.exists())
        self.assertEqual(self.run_mode("questions", {"GOVERN 1.1": {"status": "pass", "turns": 1, "questions": [
            self.question("GOVERN 1.1")]}}, "foundation"), 0)
        self.assertEqual(self.run_mode("questions", {"MAP 3.2": {"status": "pass", "turns": 1,
                                                                 "questions": self.area_questions("MAP 3.2")}}, "areas"), 0)
        PL.accept_pilot("looks good")
        doc = json.loads(PL.AI_PILOT.read_text())
        self.assertEqual(doc["recorded"], {"areas": 1, "foundation": 1})
        self.assertEqual(set(doc["prompts"]), set(DEFAULT_PROMPTS["questions"]))
        self.assertTrue(all(doc["prompts"].values()))

    def test_assemble_turns(self):
        def cands(n):
            return [self.question("X", i) for i in range(n)]
        def w(name, obj):
            (self.tmp / name).write_text(json.dumps(obj))
            return self.tmp / name
        def verdicts(gen, fails):
            """A verdict for every question and subcategory of gen; fails = {(sid, n): {check: reason}}."""
            out = []
            for sid, v in gen.items():
                for n in range(len(v["questions"]) + 1):
                    keys = ["complete"] if n == 0 else [str(c) for c in range(1, 10)]
                    f = fails.get((sid, n), {})
                    out.append({"subcategory_id": sid, "question_number": n, "reasons": f,
                                "checks": {k: "fail" if k in f else "pass" for k in keys},
                                **({"starts_with": v["questions"][n - 1]["question_text"]} if n else {})})
            return out
        g1 = {"A": {"questions": cands(3)}, "B": {"questions": cands(4)}, "C": {"questions": cands(3)}}
        g2 = {"B": {"questions": cands(4)}, "C": {"questions": [self.question("X", 9)] + cands(3)[1:]}}
        gen1, gen2 = w("g1.json", g1), w("g2.json", g2)
        eval1 = w("e1.json", verdicts(g1, {("B", 2): {"1": "yes/no"}, ("C", 1): {"4": "vague"}}))
        eval2 = w("e2.json", verdicts(g2, {("C", 1): {"4": "still vague"}, ("C", 0): {"complete": "row not asked"}}))
        out = self.tmp / "assembled.json"
        R.assemble(gen1, eval1, gen2, eval2, out)
        r = json.loads(out.read_text())
        self.assertEqual((r["A"]["status"], r["A"]["turns"]), ("pass", 1))
        self.assertEqual((r["B"]["status"], r["B"]["turns"]), ("pass", 2))
        self.assertEqual((r["C"]["status"], r["C"]["turns"]), ("needs_human_review", 2))
        self.assertEqual(r["C"]["reason"], "Q0: row not asked; Q1: check 4: still vague")
        R.assemble(gen1, w("e0.json", verdicts(g1, {})), None, None, out)   # nothing failed on turn 1: all pass
        self.assertTrue(all(v["status"] == "pass" and v["turns"] == 1 for v in json.loads(out.read_text()).values()))
        bad = {
            "unknown subcategory": verdicts(g1, {}) + [{"subcategory_id": "Z", "question_number": 1, "checks": {},
                                                        "reasons": {}}],
            "a question without a verdict": verdicts(g1, {})[1:],
            "a check missing": [dict(v, checks={k: c for k, c in v["checks"].items() if k != "9"})
                                if v["question_number"] == 1 else v for v in verdicts(g1, {})],
            "a fail without a reason": verdicts(g1, {("A", 1): {"3": ""}}),
            "the old failures-only format": [{"subcategory_id": "A", "question_number": 1, "check": 3, "reason": "x"}],
            "a verdict on the wrong question": [dict(v, starts_with="Where is your AI policy kept")
                                                if (v["subcategory_id"], v["question_number"]) == ("A", 2) else v
                                                for v in verdicts(g1, {})],
            "a quote that fits several questions": [dict(v, starts_with="For your highest-criticality AI systems")
                                                    if (v["subcategory_id"], v["question_number"]) == ("A", 2) else v
                                                    for v in verdicts(g1, {})],
        }
        for name, v in bad.items():
            with self.assertRaises(SystemExit, msg=name):
                R.assemble(gen1, w("bad.json", v), None, None, out)
        # turn 2 may not fail a question that is unchanged and passed turn 1, except on checks 6 and 7
        with self.assertRaises(SystemExit):
            R.assemble(gen1, eval1, gen2, w("e3.json", verdicts(g2, {("C", 2): {"3": "chained after all"}})), out)
        R.assemble(gen1, eval1, gen2, w("e4.json", verdicts(g2, {("C", 2): {"7": "duplicates the new Q1"}})), out)
        self.assertEqual(json.loads(out.read_text())["C"]["status"], "needs_human_review")


import build_ai_questions as BQ  # noqa: E402
import check_freshness as CF  # noqa: E402


class Scope(unittest.TestCase):
    """build_ai_questions.py on synthetic banks (the real banks do not exist until the build)."""

    def q(self, text, roles, rows=None, flags=()):
        q = {"question_text": f"For your highest-criticality AI systems, how is {text} handled, and who owns it?",
             "playbook_refs": ["MAP 1.1 — suggested action 1"], "cis_refs": [], "roles": roles,
             "producer_flags": list(flags)}
        if rows is not None:
            q["rows"] = rows
        return q

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        m28 = lambda a: f"{a}|MEASURE 2.8"   # noqa: E731
        foundation = {"subcategories": {
            "GOVERN 1.1": {"status": "pass", "turns": 1, "questions": [
                self.q("the AI policy", ["none", "consumer", "producer"]), self.q("model law", ["producer"])]},
            "GOVERN 6.1": {"status": "pass", "turns": 1, "questions": [
                self.q("vendor AI risk", ["consumer"]),
                self.q("base model risk", ["producer"], flags=["built_on_existing_model"])]}}}
        areas = {"subcategories": {
            "MEASURE 2.8": {"status": "pass", "turns": 1, "rows_sha": "x",
                            "rows": {m28("agent"): {"area": "agent", "impact": ["access", "process"]},
                                     m28("mcp_tools"): {"area": "mcp_tools", "impact": ["access"]},
                                     m28("model"): {"area": "model", "impact": ["assets"]},
                                     m28("invisible_usage"): {"area": "invisible_usage", "impact": ["data"]}},
                            "questions": [self.q("action logging", ["consumer", "producer"], [m28("agent"), m28("mcp_tools")]),
                                          self.q("weights access logging", ["producer"], [m28("model")]),
                                          self.q("shadow AI logging", ["none", "consumer", "producer"],
                                                 [m28("invisible_usage")])]},
            "MANAGE 2.4": {"status": "needs_human_review", "turns": 2, "review_reason": "Q1: vague", "rows_sha": "y",
                           "rows": {"model_building|MANAGE 2.4": {"area": "model_building", "impact": ["assets"]}},
                           "questions": [self.q("withdrawing a release", ["producer"], ["model_building|MANAGE 2.4"],
                                                flags=["given_to_others"])]}}}
        self.banks = {}
        for name, doc in (("foundation", foundation), ("areas", areas)):
            self.banks[name] = self.tmp / f"bank_{name}.json"
            self.banks[name].write_text(json.dumps(doc))
        real = BQ.ai_bank_path
        BQ.ai_bank_path = lambda b: self.banks[b]
        self.addCleanup(setattr, BQ, "ai_bank_path", real)
        self.run = self.tmp / "run"
        self.run.mkdir()
        self.names = json.loads(BQ.AI_AREA_LABELS.read_text())["labels"]

    def profile(self, **over):
        p = {"ai_in_use": "some", "role": "consumer", "producer": None,
             "ai_areas": ["invisible_usage", "input", "output", "mcp_tools", "agent"],
             "engagement_flags": {"csf_assessment_done": True, "iso27001_held": False, "iso42001_held": False},
             "captured_on": "2026-10-14"}
        p.update(over)
        return p

    def producer(self, built=True, given=False, **over):
        p = {"role": "producer", "producer": {"built_on_existing_model": built, "given_to_others": given},
             "ai_areas": ["invisible_usage", "input", "output", "model_building", "model", "test_tuning_data"]}
        return self.profile(**{**p, **over})

    def go(self, profile):
        (self.run / "ai_usage.json").write_text(json.dumps(profile))
        sys.argv = ["x", str(self.run)]
        try:
            BQ.main()
        except SystemExit as e:
            return e.code
        return 0

    def asked(self, bank):
        """{subcategory: [question text fragment]} of the draft."""
        d = json.loads((self.run / f"ai_questions_draft_{bank}.json").read_text())
        return {e["subcategory_id"]: [q["question_text"].split(" how is ")[1].split(" handled")[0] for q in e["questions"]]
                for e in d}

    def test_consumer_gets_its_roles_and_areas_with_a_covers_note(self):
        self.assertEqual(self.go(self.profile()), 0)
        self.assertEqual(self.asked("foundation"), {"GOVERN 1.1": ["the AI policy"], "GOVERN 6.1": ["vendor AI risk"]})
        self.assertEqual(self.asked("areas"), {"MEASURE 2.8": ["action logging", "shadow AI logging"]})
        e = json.loads((self.run / "ai_questions_draft_areas.json").read_text())[0]
        shared, single = e["questions"]
        self.assertEqual(shared["applies_to"], f"This question covers: {self.names['mcp_tools']}; {self.names['agent']}"
                         if shared["rows"][0].startswith("mcp") else
                         f"This question covers: {self.names['agent']}; {self.names['mcp_tools']}")
        self.assertEqual(single["applies_to"], self.names["invisible_usage"])
        ev = json.loads(BQ.AI_EVIDENCE_PROMPTS.read_text())
        self.assertEqual(shared["evidence_prompt"], " ".join([ev["by_impact"]["access"], ev["by_impact"]["process"]]))
        self.assertEqual(e["question_type"], "full_discovery")
        f = json.loads((self.run / "ai_questions_draft_foundation.json").read_text())
        self.assertTrue(all(q["applies_to"] == "Whole organisation" for x in f for q in x["questions"]))
        self.assertEqual({q["criticality_frame"] for x in f for q in x["questions"]}, {"none"})
        self.assertEqual((shared["criticality_frame"], single["criticality_frame"]), ("required", "optional"))

    def test_a_bank_evidence_prompt_replaces_the_generic_line(self):
        doc = json.loads(self.banks["areas"].read_text())
        doc["subcategories"]["MEASURE 2.8"]["questions"][0]["evidence_prompt"] = "An extract of the agent action log."
        self.banks["areas"].write_text(json.dumps(doc))
        self.assertEqual(self.go(self.profile()), 0)
        e = json.loads((self.run / "ai_questions_draft_areas.json").read_text())[0]
        self.assertEqual(e["questions"][0]["evidence_prompt"], "An extract of the agent action log.")

    def test_a_shared_question_names_only_the_clients_areas(self):
        self.assertEqual(self.go(self.profile(ai_areas=["invisible_usage", "input", "output", "agent"])), 0)
        e = json.loads((self.run / "ai_questions_draft_areas.json").read_text())[0]
        self.assertEqual(e["questions"][0]["applies_to"], f"This question covers: {self.names['agent']}")
        self.assertEqual(e["questions"][0]["rows"], ["agent|MEASURE 2.8"])

    def test_producer_flags_pick_the_flagged_questions(self):
        self.assertEqual(self.go(self.producer(built=True, given=False)), 0)
        self.assertEqual(self.asked("foundation"), {"GOVERN 1.1": ["the AI policy", "model law"],
                                                    "GOVERN 6.1": ["base model risk"]})
        self.assertEqual(self.asked("areas"), {"MEASURE 2.8": ["weights access logging", "shadow AI logging"]})
        self.assertEqual(self.go(self.producer(built=False, given=True)), 0)
        self.assertEqual(self.asked("foundation"), {"GOVERN 1.1": ["the AI policy", "model law"]})
        d = {e["subcategory_id"]: e for e in json.loads((self.run / "ai_questions_draft_areas.json").read_text())}
        self.assertIn("MANAGE 2.4", d)
        self.assertTrue(d["MANAGE 2.4"]["confidence_flag"].startswith("LOW"))

    def test_both_gets_consumer_and_producer_questions(self):
        p = self.producer(built=True, given=False, role="both")
        p["ai_areas"] += ["agent", "mcp_tools"]
        self.assertEqual(self.go(p), 0)
        self.assertEqual(self.asked("foundation")["GOVERN 6.1"], ["vendor AI risk", "base model risk"])
        self.assertEqual(self.asked("areas")["MEASURE 2.8"], ["action logging", "weights access logging", "shadow AI logging"])

    def test_every_area_has_a_client_label(self):
        ids = [a["id"] for a in json.loads(AI_AREAS.read_text())["ai_areas"]]
        labels = json.loads(BQ.AI_AREA_LABELS.read_text())["labels"]
        self.assertEqual(sorted(labels), sorted(ids))
        self.assertTrue(all(str(v).strip() for v in labels.values()))

    def test_none_and_unsure(self):
        self.assertEqual(self.go(self.profile(ai_in_use="none", role=None, ai_areas=["invisible_usage"])), 0)
        self.assertEqual(self.asked("foundation"), {"GOVERN 1.1": ["the AI policy"]})
        self.assertEqual(self.asked("areas"), {"MEASURE 2.8": ["shadow AI logging"]})
        self.assertEqual(self.go(self.profile(ai_in_use="unsure", role=None,
                                              ai_areas=["invisible_usage", "input", "output"])), 0)
        self.assertEqual(self.asked("foundation"), {"GOVERN 1.1": ["the AI policy"], "GOVERN 6.1": ["vendor AI risk"]})
        scope = json.loads((self.run / "ai_scope.json").read_text())
        self.assertEqual(scope["roles_asked_as"], ["none", "consumer"])

    def test_ai_draft_goes_through_the_existing_assessor_patch_merge(self):
        import record_judgements as RJ
        self.assertEqual(self.go(self.profile()), 0)
        draft = json.loads((self.run / "ai_questions_draft_areas.json").read_text())
        changed = json.loads(json.dumps(draft[0]))
        changed["questions"][0]["question_text"] += " Who signs off?"
        changed["assessor_note"] = "Added an ownership prompt."
        (self.run / "patch.json").write_text(json.dumps([changed]))
        RJ.log_run_step([str(self.run), "--step", "ai_assessor_areas", "--base", "ai_questions_draft_areas.json",
                         "--patch", "patch.json", "--output", "ai_questions_assessed_areas.json", "--model", "test"])
        merged = json.loads((self.run / "ai_questions_assessed_areas.json").read_text())
        self.assertEqual(len(merged), len(draft))
        self.assertEqual(merged[0]["assessor_note"], "Added an ownership prompt.")
        self.assertTrue(list((self.run / "judgement_log").glob("*ai_assessor_areas.json")))
        # one workbook for the client: the CSF sheet first, then one AI sheet holding both banks with an Area column
        import openpyxl
        import write_questionnaire as WQ
        csf = [{"subcategory_id": "GV.RM-01", "function": "GV", "outcome": "o", "question_type": "full_discovery",
                "questions": [{"question_text": "How is risk managed?", "source_reference": "CSET: 1"}],
                "evidence_prompt": "ep", "confidence_flag": ""}]
        (self.run / "csf_final.json").write_text(json.dumps(csf))
        out = self.run / "questionnaire.xlsx"
        finals = [str(self.run / f"ai_questions_draft_{b}.json") for b in ("areas", "foundation")]
        for argv in (["x", str(self.run / "csf_final.json"), str(out)],
                     ["x", *finals, str(out), "--framework", "ai"],
                     ["x", *finals, str(out), "--framework", "ai"]):   # the last call replaces the AI sheet
            sys.argv = argv
            WQ.main()
        wb = openpyxl.load_workbook(out)
        self.assertEqual(wb.sheetnames, ["CSF Questionnaire", "AI RMF Questionnaire"])
        ws = wb["AI RMF Questionnaire"]
        header = [c.value for c in ws[1]]
        area = [row[header.index("Area")].value for row in ws.iter_rows(min_row=2)]
        self.assertEqual(area[0], "Whole organisation")                   # GOVERN (foundation) first
        self.assertTrue(any(a.startswith("This question covers:") for a in area))
        self.assertNotIn("Rung", header)
        sys.argv = ["x", str(self.run / "csf_final.json"), finals[0], str(out)]
        with self.assertRaises(SystemExit):   # csf mode takes exactly one question file
            WQ.main()

    def test_engagement_flags_change_nothing(self):
        # the questions are about AI, so a CSF assessment or ISO 27001 neither drops nor rewords any of them
        drafts = []
        for flags in ((False, False, False), (True, True, True)):
            ef = dict(zip(("csf_assessment_done", "iso27001_held", "iso42001_held"), flags))
            self.assertEqual(self.go(self.profile(engagement_flags=ef)), 0)
            drafts.append([json.loads((self.run / f"ai_questions_draft_{b}.json").read_text())
                           for b in ("foundation", "areas")])
        self.assertEqual(drafts[0], drafts[1])
        self.assertTrue(all(e["question_type"] == "full_discovery" for bank in drafts[1] for e in bank))

    def test_missing_bank_fails(self):
        self.banks["areas"].unlink()
        self.assertEqual(self.go(self.profile()) != 0, True)
        self.assertFalse((self.run / "ai_scope.json").exists())

    def test_invalid_profiles_are_rejected_and_write_nothing(self):
        for bad in (self.profile(ai_in_use="maybe"), self.profile(role=None), self.profile(role="vendor"),
                    self.profile(ai_areas=["mobile"]), self.profile(producer={"built_on_existing_model": True}),
                    self.producer(producer=None), self.profile(ai_in_use="none", role="consumer"),
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
            self.row("MAP", "MAP 4.1", ["MCP-2.1", "MCP-2.3"]),
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
        self.assertEqual(list(doc["subcategories"]), ["MAP", "MEASURE", "MANAGE"])   # GOVERN is foundation
        self.assertEqual(sum(len(v) for v in doc["subcategories"].values()), 72 - 19 - 12)   # and 12 foundation subs
        self.assertEqual(set(doc["function_definitions"]), {"GOVERN", "MAP", "MEASURE", "MANAGE"})
        others = {a["id"]: a for a in doc["other_areas"]}                   # the rest of the AI areas sheet
        self.assertEqual(len(others), 13)
        self.assertNotIn("mcp_tools", others)
        self.assertEqual(set(others["model_building"]), {"id", "name", "applies_to", "covers"})
        self.assertEqual(doc["foundation"], ["GOVERN"] + ["MAP 1.3", "MAP 1.5", "MAP 3.4", "MEASURE 1.1", "MEASURE 1.2", "MEASURE 3.1", "MEASURE 3.2", "MEASURE 4.1", "MANAGE 1.2", "MANAGE 1.3", "MANAGE 1.4", "MANAGE 2.1"])
        self.assertIn("audit trail", [c["name"] for c in doc["rules"]["required_checks"]])

    def test_mapping_rules_match_the_cis_guides(self):
        from ai_bank_common import check_mapping_rules
        rules = json.loads(R.AI_MAPPING_RULES.read_text())
        self.assertEqual(check_mapping_rules(rules, self.inp), [])
        bad = json.loads(json.dumps(rules))
        bad["always_cis_controls"]["controls"]["8"] = "Data Protection"      # wrong name for control 8
        bad["always_cis_controls"]["controls"]["19"] = "No such control"     # CIS v8.1 has 18 controls
        bad["area_cis"]["mcp_tools"]["controls"].append(42)
        bad["functions"].append("GOVERN")                                    # both mapped and foundation
        problems = check_mapping_rules(bad, self.inp)
        self.assertTrue(any("8" in p and "Audit Log Management" in p for p in problems), problems)
        self.assertTrue(any("19" in p for p in problems) and any("mcp_tools" in p and "42" in p for p in problems))
        self.assertTrue(any("split the AI RMF functions" in p for p in problems), problems)
        govern_check = json.loads(json.dumps(rules))                         # a required check on a foundation function
        govern_check["required_checks"].append({"name": "inventory", "areas": "all", "any_of": ["GOVERN 1.6"]})
        self.assertEqual(check_mapping_rules(govern_check, self.inp),
                         ["required check 'inventory': ['GOVERN 1.6'] are not subcategories of a mapped function"])

    def test_foundation_subcategories_are_asked_once_not_per_area(self):
        from ai_bank_common import check_mapping_rules
        rules = json.loads(R.AI_MAPPING_RULES.read_text())
        self.assertEqual(rules["foundation"]["subcategories"], ["MAP 1.3", "MAP 1.5", "MAP 3.4", "MEASURE 1.1", "MEASURE 1.2", "MEASURE 3.1", "MEASURE 3.2", "MEASURE 4.1", "MANAGE 1.2", "MANAGE 1.3", "MANAGE 1.4", "MANAGE 2.1"])
        self.assertEqual(check_mapping_rules(rules, self.inp), [])
        for extra, words in ((["MAP 9.9"], "foundation subcategories"), (["GOVERN 1.6"], "foundation subcategories")):
            bad = json.loads(json.dumps(rules))
            bad["foundation"]["subcategories"] = extra
            self.assertTrue(any(words in p for p in check_mapping_rules(bad, self.inp)), extra)
        bad = json.loads(json.dumps(rules))                                  # a required check may not name one
        bad["foundation"]["subcategories"] = ["MEASURE 2.8"]
        self.assertTrue(any("audit trail" in p for p in check_mapping_rules(bad, self.inp)))

        doc = json.loads(P.prepare_mapping(self.inp, "mcp_tools").read_text())
        offered = [s["id"] for subs in doc["subcategories"].values() for s in subs]
        self.assertFalse(set(rules["foundation"]["subcategories"]) & set(offered))
        g = self.good()
        for sub in rules["foundation"]["subcategories"]:
            self.assertEqual(self.go(dict(g, rows=g["rows"] + [self.row(sub.split()[0], sub)])), 1, sub)
            self.assertFalse(R.AI_MAPPING.exists(), sub)
        self.assertEqual(self.go(g), 0)
        reached, _ = R.mapping_coverage(json.loads(R.AI_MAPPING.read_text()), self.inp, rules)
        self.assertTrue(set(rules["foundation"]["subcategories"]) <= reached)

    def test_bad_drafts_are_rejected_and_nothing_is_stored(self):
        g = self.good()
        rows = g["rows"]
        cases = {
            "unknown subcategory": [self.row("MAP", "MAP 9.9")] + rows,
            "subcategory of another function": [self.row("MAP", "GOVERN 2.1")] + rows,
            "safeguard not a candidate": [self.row("MAP", "MAP 3.5", ["LLM-3.1"])] + rows,
            "impact the area does not have": [self.row("MAP", "MAP 3.5", impact=["assets"])] + rows,
            "repeated row": rows + [rows[0]],
            "short why": [self.row("MAP", "MAP 3.5", why="tools")] + rows,
            "missing function": [r for r in rows if r["function"] != "MANAGE"],
            "missing audit trail": [r for r in rows if r["subcategory"] != "MEASURE 2.8"],
            "audit row without a control 8 safeguard": [dict(r, cis_refs=["MCP-6.8"]) if r["subcategory"] == "MEASURE 2.8"
                                                        else r for r in rows],
            "GOVERN row (foundation, never per area)": [self.row("GOVERN", "GOVERN 1.6", ["MCP-2.1"])] + rows,
            "folded subcategory that is also a row": [dict(rows[0], folded=["MAP 2.2"])] + rows[1:],
            "folded foundation subcategory": [dict(rows[0], folded=["MANAGE 1.2"])] + rows[1:],
            "folded GOVERN subcategory": [dict(rows[0], folded=["GOVERN 1.6"])] + rows[1:],
            "folded into two rows": [dict(rows[0], folded=["MAP 1.6"]), dict(rows[1], folded=["MAP 1.6"])] + rows[2:],
            "unknown field": [dict(rows[0], note="x")] + rows[1:],
        }
        for name, rs in cases.items():
            self.assertEqual(self.go(dict(g, rows=rs)), 1, name)
            self.assertFalse(R.AI_MAPPING.exists(), name)
        self.assertEqual(self.go(dict(g, area="no_such_area")), 1)
        self.assertEqual(self.go(dict(g, rows=[dict(rows[0], folded=["MAP 1.6"])] + rows[1:])), 0)   # a valid fold
        R.AI_MAPPING.unlink()
        self.assertEqual(self.go(g, review=[{"function": "MAP", "subcategory": "MAP 9.9", "reason": "x"}]), 1)
        self.assertEqual(self.go(dict(g, rows=[r for r in rows if r["function"] != "MAP"],
                                      no_question=[{"function": "MAP", "reason": "Nothing about the tools' context here."}])), 0)

    def test_missing_rows_and_notes_are_recorded_once_without_flagging_good_rows(self):
        g = self.good()
        bad_reviews = [[{"function": "MANAGE", "subcategory": None, "reason": "Missing MANAGE 4.1."}],      # name it
                       [{"kind": "missing", "function": "MANAGE", "subcategory": "MANAGE 2.4", "reason": "x"}],  # a row
                       [{"kind": "missing", "function": "MANAGE", "subcategory": "MANAGE 2.1", "reason": "x"}],  # foundation
                       [{"kind": "guess", "function": "MAP", "subcategory": "MAP 2.2", "reason": "x"}]]
        for rv in bad_reviews:
            self.assertEqual(self.go(g, review=rv), 1, rv)
            self.assertFalse(R.AI_MAPPING.exists(), rv)
        review = [{"kind": "missing", "function": "MANAGE", "subcategory": "MANAGE 4.1",
                   "reason": "Nothing checks that a tool's actions can be overridden and rolled back."},
                  {"kind": "note", "function": "MEASURE", "subcategory": "MEASURE 2.7",
                   "reason": "Protects processes too; the area's impacts may be too narrow."}]
        self.assertEqual(self.go(g, review=review), 0)
        entry = json.loads(R.AI_MAPPING.read_text())["areas"]["mcp_tools"]
        self.assertEqual([x["subcategory"] for x in entry["missing"]], ["MANAGE 4.1"])
        self.assertEqual([x["subcategory"] for x in entry["notes"]], ["MEASURE 2.7"])
        self.assertTrue(all(r["status"] == "pass" for r in entry["rows"]))     # no MANAGE row is flagged

    def test_a_fold_counts_as_reached(self):
        g = self.good()
        self.assertEqual(self.go(dict(g, rows=[dict(g["rows"][0], folded=["MAP 1.6"])] + g["rows"][1:])), 0)
        reached, unreached = R.mapping_coverage(json.loads(R.AI_MAPPING.read_text()), self.inp,
                                                json.loads(R.AI_MAPPING_RULES.read_text()))
        self.assertIn("MAP 1.6", reached)

    def test_a_redraft_that_breaks_the_rules_with_the_persons_decisions_is_rejected(self):
        self.assertEqual(self.go(self.good()), 0)
        doc = json.loads(R.AI_MAPPING.read_text())                       # as if the person removed the audit row
        doc["areas"]["mcp_tools"]["removed_by_human"] = ["MEASURE 2.8"]   # under rules that allowed it
        R.AI_MAPPING.write_text(json.dumps(doc))
        before = R.AI_MAPPING.read_text()
        self.assertEqual(self.go(self.good()), 1)
        self.assertEqual(R.AI_MAPPING.read_text(), before)

    def test_a_change_is_a_delta(self):
        self.assertEqual(self.go(self.good()), 0)
        entry = lambda: json.loads(R.AI_MAPPING.read_text())["areas"]["mcp_tools"]   # noqa: E731
        self.assertEqual(R.mapping_freshness(entry(), "mcp_tools", self.inp), "current")
        real_rules, real_areas = R.AI_MAPPING_RULES, R.AI_AREAS
        rules = json.loads(real_rules.read_text())
        tmp_rules, tmp_areas = self.tmp / "rules.json", self.tmp / "areas.json"
        try:
            R.AI_MAPPING_RULES = tmp_rules                               # a subcategory no row uses becomes foundation
            tmp_rules.write_text(json.dumps(dict(rules, foundation=dict(rules["foundation"], subcategories=
                                 rules["foundation"]["subcategories"] + ["MAP 1.4"]))))
            self.assertEqual(R.mapping_freshness(entry(), "mcp_tools", self.inp), "recheck")
            _, lines, cleared = R.revalidate(self.inp, R.mapping_inputs(self.inp))
            self.assertEqual((lines, cleared), ([], 1))
            self.assertEqual(R.mapping_freshness(entry(), "mcp_tools", self.inp), "current")
            before = entry()["rows"]                                     # a subcategory a row uses becomes foundation
            tmp_rules.write_text(json.dumps(dict(rules, foundation=dict(rules["foundation"], subcategories=
                                 rules["foundation"]["subcategories"] + ["MAP 2.2"]))))
            _, lines, cleared = R.revalidate(self.inp, R.mapping_inputs(self.inp))
            self.assertEqual(cleared, 0)
            self.assertTrue(any("MAP 2.2 is foundation" in ln for ln in lines), lines)
            self.assertEqual((entry()["rows"], R.mapping_freshness(entry(), "mcp_tools", self.inp)), (before, "recheck"))
            R.AI_MAPPING_RULES = real_rules
            areas = json.loads(real_areas.read_text())                   # another area's row changes: recheck
            for a in areas["ai_areas"]:
                if a["id"] == "agent":
                    a["covers"] += " Changed."
            tmp_areas.write_text(json.dumps(areas))
            R.AI_AREAS = tmp_areas
            self.assertEqual(R.mapping_freshness(entry(), "mcp_tools", self.inp), "recheck")
            for a in areas["ai_areas"]:                                  # its own row changes: re-draft
                if a["id"] == "mcp_tools":
                    a["covers"] += " Changed."
            tmp_areas.write_text(json.dumps(areas))
            self.assertEqual(R.mapping_freshness(entry(), "mcp_tools", self.inp), "redraft")
            _, lines, cleared = R.revalidate(self.inp, R.mapping_inputs(self.inp))
            self.assertEqual(cleared, 0)
            self.assertIn("re-draft", lines[0])
        finally:
            R.AI_MAPPING_RULES, R.AI_AREAS = real_rules, real_areas

    def test_recorded_with_review_and_coverage(self):
        review = [{"function": "MEASURE", "subcategory": "MEASURE 2.7", "reason": "Too generic for tool credentials."}]
        self.assertEqual(self.go(self.good(), review=review), 0)
        doc = json.loads(R.AI_MAPPING.read_text())
        rows = {r["subcategory"]: r for r in doc["areas"]["mcp_tools"]["rows"]}
        self.assertEqual(rows["MEASURE 2.7"]["status"], "needs_human_review")
        self.assertEqual(rows["MAP 4.1"]["status"], "pass")
        self.assertEqual(doc["areas"]["mcp_tools"]["inputs"]["ai_areas"], R.audit.sha(R.AI_AREAS))
        rules = json.loads(R.AI_MAPPING_RULES.read_text())
        reached, unreached = R.mapping_coverage(doc, self.inp, rules)
        self.assertIn("GOVERN 4.1", reached)            # foundation
        self.assertIn("GOVERN 1.6", reached)
        self.assertIn("MEASURE 2.11", unreached)
        self.assertIn("MANAGE 1.2", reached)            # foundation subcategory, asked once for the organisation
        self.assertIn("MANAGE 1.1", unreached)          # not foundation: an area must reach it
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
        self.want = 2                             # subcategories a complete bank must hold (stubbed)
        real_completeness = CF.bank_completeness
        CF.bank_completeness = lambda bank, doc: ((len(doc["subcategories"]) >= self.want),
                                                  f"{len(doc['subcategories'])} of {self.want}")
        self.addCleanup(setattr, CF, "bank_completeness", real_completeness)
        CF.AI_BANKS, CF.CSF_IMPACT_NOTES = self.tmp / "banks", self.tmp / "notes.json"
        CF.AI_PILOT = self.tmp / "pilot.json"
        real_mapping_status = CF.mapping_status   # the mapping gate has its own test (test_sheet_io.py)
        self.mapping_ok = False                   # build_everything() accepts it
        CF.mapping_status = lambda: (self.mapping_ok, "accepted (test)" if self.mapping_ok else "missing (test)")
        self.addCleanup(setattr, CF, "mapping_status", real_mapping_status)
        CF.AI_AREAS, CF.AI_AREAS_XLSX = self.tmp / "ai_areas.json", self.tmp / "ai_areas.xlsx"
        real_sheets = CF.AI_QUESTIONS_XLSX
        CF.AI_QUESTIONS_XLSX = {b: (self.tmp / f"questions_{b}.xlsx", n) for b, (_, n) in real_sheets.items()}
        self.addCleanup(setattr, CF, "AI_QUESTIONS_XLSX", real_sheets)
        self.addCleanup(setattr, CF, "AI_IMPACT_NOTES_XLSX", CF.AI_IMPACT_NOTES_XLSX)
        CF.AI_IMPACT_NOTES_XLSX = self.tmp / "impact_notes.xlsx"
        CF.AI_BANKS.mkdir()

    def sha(self, name):
        return self.audit.sha(self.src / name)

    def accept_pilot(self):
        CF.AI_PILOT.write_text(json.dumps({"accepted_on": "2026-10-14", "prompts": {
            p: self.audit.sha(REPO_ROOT / p) for p in DEFAULT_PROMPTS["questions"]}}))

    def build_everything(self, applicable=2, recorded=2):
        self.mapping_ok = True
        pb = self.sha(self.files["playbook"])
        g = {k: self.sha(self.files[k]) for k in ("LLM", "MCP", "AGENT")}
        CF.AI_CORE.write_text(json.dumps({"source_sha256_16": pb}))
        CF.AI_SAFEGUARDS.write_text(json.dumps({"sources": {k: {"sha256_16": v} for k, v in g.items()}}))
        self.want = applicable
        for bank in ("foundation", "areas"):
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
        self.assertFalse(s["bank areas"][0])
        self.assertIn("2 of 3", s["bank areas"][1])

    def test_a_changed_guide_makes_only_its_dependents_stale(self):
        self.build_everything()
        (self.src / self.files["LLM"]).write_text("changed")
        s = self.states()
        self.assertFalse(s["parse"] or s["bank foundation"] or s["bank areas"])
        self.assertTrue(s["notes"])   # notes use only the MCP and agents guides

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

    def test_a_review_sheet_edited_but_not_imported(self):
        self.build_everything()
        sheet = CF.AI_QUESTIONS_XLSX["areas"][0]
        sheet.write_text("edited")
        stages = {s: (ok, text) for s, ok, text in CF.ai_stages()}
        self.assertFalse(stages["bank areas"][0])
        self.assertIn("sheet_io.py import area_questions", stages["bank areas"][1])
        doc = json.loads((CF.AI_BANKS / "question_bank_ai_rmf_areas.json").read_text())
        doc["source_sha"] = self.audit.sha(sheet)                         # imported
        (CF.AI_BANKS / "question_bank_ai_rmf_areas.json").write_text(json.dumps(doc))
        self.assertTrue(self.states()["bank areas"])

    def test_pilot_stage(self):
        self.build_everything()
        self.assertTrue(self.states()["pilot"])
        CF.AI_PILOT.unlink()
        self.assertFalse(self.states()["pilot"])
        self.accept_pilot()
        doc = json.loads(CF.AI_PILOT.read_text())
        doc["prompts"][DEFAULT_PROMPTS["questions"][0]] = "0" * 16   # the generator prompt was edited after acceptance
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
