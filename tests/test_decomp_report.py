import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("decomp_report", ROOT / "scripts" / "decomp_report.py")
report_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_module)


class DecompReportTests(unittest.TestCase):
    def setUp(self):
        self.scope = json.loads((ROOT / "config" / "progress-scope.json").read_text())
        self.target = json.loads((ROOT / "config" / "target.json").read_text())
        self.overlays = json.loads((ROOT / "config" / "overlays.json").read_text())
        self.progress = json.loads((ROOT / "progress" / "report.json").read_text())

    def generate(self):
        return report_module.generate(self.scope, self.target, self.overlays, self.progress)

    def test_assembly_reconstruction_never_counts_as_decompilation(self):
        report = self.generate()
        self.assertTrue(self.progress["g1"]["matched"])
        self.assertEqual(len(self.progress["g3"]), 27)
        self.assertEqual(report["measures"]["matchedCode"], "0")
        self.assertEqual(report["measures"]["completeCode"], "0")
        self.assertEqual(report["measures"]["completeUnits"], 0)
        self.assertTrue(all(not unit["metadata"]["complete"] for unit in report["units"]))

    def test_scope_and_categories_cover_all_measured_programs(self):
        report = self.generate()
        expected_code = sum(section["size"] for program in self.scope["programs"]
                            for section in program["sections"] if section["flags"] & 4)
        self.assertEqual(int(report["measures"]["totalCode"]), expected_code)
        self.assertEqual(sum(int(category["measures"]["totalCode"]) for category in report["categories"]), expected_code)
        self.assertEqual({unit["metadata"]["moduleName"] for unit in report["units"]},
                         {program["name"] for program in self.scope["programs"]})
        self.assertEqual(len(report["units"]), len({unit["name"] for unit in report["units"]}))

    def test_missing_or_duplicated_overlay_is_rejected(self):
        for change in ("missing", "duplicate"):
            with self.subTest(change=change):
                scope = copy.deepcopy(self.scope)
                scope["programs"].pop()
                if change == "duplicate":
                    scope["programs"].append(copy.deepcopy(scope["programs"][-1]))
                with self.assertRaises(ValueError):
                    report_module.generate(scope, self.target, self.overlays, self.progress)

    def test_changed_program_identity_is_rejected(self):
        self.scope["programs"][-1]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.generate()

    def test_progress_beyond_baseline_requires_new_exporter(self):
        self.progress["decompiled_functions"] = 1
        with self.assertRaises(ValueError):
            self.generate()

    def test_nobits_and_nonallocated_sections_are_rejected(self):
        for field, value in (("type", 8), ("flags", 0), ("size", 0)):
            with self.subTest(field=field):
                scope = copy.deepcopy(self.scope)
                scope["programs"][0]["sections"][0][field] = value
                with self.assertRaises(ValueError):
                    report_module.generate(scope, self.target, self.overlays, self.progress)


if __name__ == "__main__":
    unittest.main()
