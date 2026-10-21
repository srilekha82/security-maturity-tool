"""Run: .venv/bin/python -m unittest discover -s tests -v

sheet_io.py: spreadsheet <-> JSON for the sheets in data/common/sheet_specs.json. Everything is written to a temp dir;
the committed ai_areas.xlsx and ai_areas.json are read only."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sheet_io as S  # noqa: E402
from paths import AI_AREAS, AI_AREAS_XLSX  # noqa: E402


class AiAreasSheet(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.spec = S.load_spec("ai_areas")
        self.xlsx, self.json, self.log = self.tmp / "a.xlsx", self.tmp / "a.json", self.tmp / "audit.jsonl"
        shutil.copy(AI_AREAS_XLSX, self.xlsx)   # the committed spreadsheet is the decision
        self.assertEqual(self.do_import(), 0)

    def edit(self, row, header, value):
        wb = openpyxl.load_workbook(self.xlsx)
        ws = wb[self.spec["sheet"]]
        col = [c.value for c in ws[1]].index(header) + 1
        ws.cell(row=row, column=col, value=value)
        wb.save(self.xlsx)

    def cell(self, row, header):
        ws = openpyxl.load_workbook(self.xlsx)[self.spec["sheet"]]
        return ws.cell(row=row, column=[c.value for c in ws[1]].index(header) + 1).value

    def do_import(self):
        try:
            S.import_sheet(self.spec, self.xlsx, self.json, self.log)
            return 0
        except SystemExit as e:
            return e.code

    def test_committed_json_is_the_import_of_the_committed_spreadsheet(self):
        committed = json.loads(AI_AREAS.read_text())
        self.assertEqual(committed["source_sha"], S.audit.sha(AI_AREAS_XLSX))
        self.assertEqual(json.loads(self.json.read_text())["ai_areas"], committed["ai_areas"])
        ids = [a["id"] for a in committed["ai_areas"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_spreadsheet_only_columns_stay_out_of_the_json(self):
        first = json.loads(self.json.read_text())["ai_areas"][0]
        self.assertNotIn("example_question", first)
        self.assertEqual(sorted(first), ["applies_to", "covers", "id", "impact", "kind", "name"])

    def test_an_edit_is_stale_until_imported(self):
        self.edit(2, "AI area", "Internal business process")
        self.assertFalse(S.sheet_status("ai_areas", self.xlsx, self.json)[0])
        self.assertEqual(self.do_import(), 0)
        self.assertEqual(json.loads(self.json.read_text())["ai_areas"][0]["name"], "Internal business process")
        self.assertTrue(S.sheet_status("ai_areas", self.xlsx, self.json)[0])

    def test_bad_cells_are_rejected_and_nothing_is_written(self):
        second_id = self.cell(3, "ID")
        for header, value in (("Applies to", "everyone"), ("Kind", "asset"), ("Impact", "data, money"),
                              ("Impact", ""), ("ID", "Bad Id"), ("AI area", ""), ("ID", second_id)):
            self.setUp()
            before = self.json.read_text()
            self.edit(2, header, value)
            self.assertEqual(self.do_import(), 1, (header, value))
            self.assertEqual(self.json.read_text(), before, (header, value))

    def test_impact_is_a_list(self):
        self.edit(2, "Impact", "Access, data, access")
        self.assertEqual(self.do_import(), 0)
        self.assertEqual(json.loads(self.json.read_text())["ai_areas"][0]["impact"], ["access", "data"])

    def test_export_never_overwrites_the_decision(self):
        with self.assertRaises(SystemExit):   # in sync, but the spreadsheet holds a column the JSON does not keep
            S.export_sheet(self.spec, self.xlsx, self.json, self.log)
        self.edit(2, "AI area", "edited")
        with self.assertRaises(SystemExit):   # edited and not imported
            S.export_sheet(self.spec, self.xlsx, self.json, self.log)
        self.assertEqual(self.cell(2, "AI area"), "edited")
        self.assertTrue(self.cell(2, "Example question"))

    def test_wrong_headers_are_rejected(self):
        wb = openpyxl.load_workbook(self.xlsx)
        wb[self.spec["sheet"]].cell(row=1, column=2, value="Surface")
        wb.save(self.xlsx)
        self.assertEqual(self.do_import(), 1)


if __name__ == "__main__":
    unittest.main()
