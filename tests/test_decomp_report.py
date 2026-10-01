import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch


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
        self.progress["decompiled_functions"] = 0
        self.progress["integrated_functions"] = 0
        self.catalog = json.loads((ROOT / "config" / "candidate-catalog.json").read_text())
        self.source = (ROOT / "candidates" / "boot.c").read_bytes()
        self.object_proof = json.loads((ROOT / "progress" / "candidates.json").read_text())

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

    def test_progress_beyond_baseline_requires_integration_proof(self):
        for field in ("decompiled_functions", "integrated_functions"):
            with self.subTest(field=field):
                self.progress[field] = 1
                with self.assertRaises(ValueError):
                    self.generate()
                self.progress[field] = 0

    def test_nobits_and_nonallocated_sections_are_rejected(self):
        for field, value in (("type", 8), ("flags", 0), ("size", 0)):
            with self.subTest(field=field):
                scope = copy.deepcopy(self.scope)
                scope["programs"][0]["sections"][0][field] = value
                with self.assertRaises(ValueError):
                    report_module.generate(scope, self.target, self.overlays, self.progress)

    def integration(self):
        functions = [{"symbol": function["symbol"], "address": function["address"],
                      "size": function["size"], "matched": True, "integrated": True, "program": "boot"}
                     for function in self.catalog["functions"]]
        self.progress["decompiled_functions"] = len(functions)
        self.progress["integrated_functions"] = len(functions)
        return {"target": self.target["serial"], "reference_sha256": self.target["boot"]["sha256"],
                "source_sha256": hashlib.sha256(self.source).hexdigest(),
                "catalog_sha256": hashlib.sha256(self.catalog_bytes()).hexdigest(),
                "candidate_source": "candidates/boot.c", "functions": functions,
                "full_boot_gate": {"matched": True, "bytes_compared": 2521763, "segments": 2},
                "state": "integrated", "tools": copy.deepcopy(self.object_proof["tools"]),
                "matched_code_bytes": sum(function["size"] for function in functions)}

    def catalog_bytes(self):
        return json.dumps(self.catalog).encode("utf-8")

    def generate_integrated(self, integration):
        with patch.object(Path, "read_bytes", side_effect=[self.source, self.catalog_bytes()]):
            return report_module.generate(self.scope, self.target, self.overlays, self.progress, integration)

    def update_catalog_function(self, integration, index, **changes):
        self.catalog["functions"][index].update(changes)
        integration["functions"][index].update(changes)
        integration["catalog_sha256"] = hashlib.sha256(self.catalog_bytes()).hexdigest()

    def test_fuzzy_percent_weights_code_and_data_while_code_percent_uses_only_code(self):
        measures = report_module.measures(80, 120, 1, 40)
        self.assertEqual(measures["matchedCodePercent"], 50)
        self.assertEqual(measures["completeCodePercent"], 50)
        self.assertEqual(measures["fuzzyMatchPercent"], 20)
        self.assertEqual(report_module.measures(0, 120, 1)["fuzzyMatchPercent"], 0)
        self.assertEqual(report_module.measures(0, 0, 0)["fuzzyMatchPercent"], 0)

    def test_seventeen_complete_c_units_preserve_totals_and_categories(self):
        baseline = self.generate()
        integration = self.integration()
        report = self.generate_integrated(integration)
        measures = report["measures"]
        self.assertEqual(measures["totalCode"], "48788176")
        self.assertEqual(measures["totalData"], baseline["measures"]["totalData"])
        self.assertEqual(measures["completeCode"], "716")
        self.assertEqual(measures["matchedCode"], "716")
        self.assertEqual(measures["completeUnits"], 17)
        self.assertEqual(measures["totalUnits"], 193)
        self.assertEqual(measures["matchedCodePercent"], 716 / 48788176 * 100)
        self.assertEqual(measures["completeCodePercent"], 716 / 48788176 * 100)
        for aggregate in [measures, *(category["measures"] for category in report["categories"])]:
            self.assertEqual(aggregate["fuzzyMatchPercent"], int(aggregate["matchedCode"])
                             / (int(aggregate["totalCode"]) + int(aggregate["totalData"])) * 100)
        for field in ("totalCode", "totalData", "completeCode", "matchedCode", "totalUnits", "completeUnits"):
            with self.subTest(field=field):
                self.assertEqual(sum(int(unit["measures"][field]) for unit in report["units"]), int(measures[field]))
                self.assertEqual(sum(int(category["measures"][field]) for category in report["categories"]),
                                 int(measures[field]))
        completed = [unit for unit in report["units"] if unit["metadata"]["complete"]]
        self.assertEqual({unit["functions"][0]["name"] for unit in completed},
                         {function["symbol"] for function in integration["functions"]})
        for unit in completed:
            self.assertEqual(unit["metadata"]["sourcePath"], "candidates/boot.c")
            self.assertFalse(unit["metadata"]["autoGenerated"])
            self.assertEqual(unit["measures"]["matchedCodePercent"], 100)
        for category in report["categories"]:
            self.assertEqual(category["measures"]["matchedCode"], "716" if category["id"] == "boot" else "0")
        original_units = {unit["name"]: unit for unit in baseline["units"]}
        for unit in report["units"]:
            if unit["metadata"]["complete"]:
                continue
            original = original_units[unit["name"]]
            promoted_bytes = sum(function["size"] for function in integration["functions"]
                                 if unit["metadata"]["moduleName"] == "boot"
                                 and int(original["sections"][0]["metadata"]["virtualAddress"]) <= function["address"]
                                 < int(original["sections"][0]["metadata"]["virtualAddress"])
                                 + int(original["sections"][0]["size"]))
            self.assertEqual(int(unit["sections"][0]["size"]),
                             int(original["sections"][0]["size"]) - promoted_bytes)
            self.assertEqual(unit["measures"]["matchedCode"], "0")
        exported = json.dumps(report)
        for private_field in ("sha256", "full_boot_gate", "tools", "state", "meaning", "xrefs"):
            self.assertNotIn(private_field, exported)

    def test_fully_promoted_section_omits_empty_parent(self):
        integration = self.integration()
        section = next(section for section in self.scope["programs"][0]["sections"]
                       if section["address"] == integration["functions"][0]["address"])
        section["size"] = integration["functions"][0]["size"]
        integration["functions"] = integration["functions"][:1]
        integration["matched_code_bytes"] = section["size"]
        self.progress["decompiled_functions"] = self.progress["integrated_functions"] = 1
        report = self.generate_integrated(integration)
        parent_name = f"boot/{section['name']}@{section['address']:08X}"
        self.assertNotIn(parent_name, {unit["name"] for unit in report["units"]})
        self.assertEqual(report["measures"]["totalUnits"], 176)
        self.assertTrue(all(int(unit["sections"][0]["size"]) > 0 for unit in report["units"]))

    def test_integration_identity_source_and_hashes_are_required(self):
        original = self.integration()
        for field, value in (("target", "SCUS_971.99"), ("reference_sha256", "0" * 64),
                             ("source_sha256", "0" * 64), ("catalog_sha256", "0" * 64),
                             ("candidate_source", "candidates/other.c"),
                             ("candidate_source", "../candidates/boot.c"), ("state", "matched_unintegrated"),
                             ("source_sha256", "not-a-hash"), ("tools", {}), ("tools", {"cc": "bad"})):
            with self.subTest(field=field, value=value):
                integration = copy.deepcopy(original)
                integration[field] = value
                with self.assertRaises(ValueError):
                    self.generate_integrated(integration)
        for field in original:
            with self.subTest(missing=field):
                integration = copy.deepcopy(original)
                del integration[field]
                with self.assertRaises(ValueError):
                    self.generate_integrated(integration)

    def test_changed_source_and_catalog_identity_are_rejected(self):
        integration = self.integration()
        self.source += b"\n"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.generate_integrated(integration)
        integration["source_sha256"] = hashlib.sha256(self.source).hexdigest()
        for field, value in (("target", "SCUS_971.99"), ("reference_sha256", "0" * 64)):
            with self.subTest(field=field):
                original = self.catalog[field]
                self.catalog[field] = value
                integration["catalog_sha256"] = hashlib.sha256(self.catalog_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError, "catalog identity"):
                    self.generate_integrated(integration)
                self.catalog[field] = original

    def test_partial_mismatch_duplicate_and_unknown_functions_are_rejected(self):
        original = self.integration()
        for field, value in (("matched", False), ("matched", 1), ("integrated", False),
                             ("integrated", 1), ("program", "levels/0_aranos_tutorial"),
                             ("size", 8), ("symbol", "unknown"), ("different_bytes", 1)):
            with self.subTest(field=field, value=value):
                integration = copy.deepcopy(original)
                integration["functions"][0][field] = value
                with self.assertRaises(ValueError):
                    self.generate_integrated(integration)
        integration = copy.deepcopy(original)
        integration["functions"].append(copy.deepcopy(integration["functions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.generate_integrated(integration)
        integration = copy.deepcopy(original)
        integration["functions"].pop()
        with self.assertRaises(ValueError):
            self.generate_integrated(integration)

    def test_overlapping_functions_are_rejected_even_with_consistent_catalog(self):
        integration = self.integration()
        self.update_catalog_function(integration, 1, address=integration["functions"][0]["address"] + 4)
        with self.assertRaisesRegex(ValueError, "Overlapping integrated"):
            self.generate_integrated(integration)

    def test_out_of_bounds_and_nonexecutable_functions_are_rejected(self):
        for address in (0x80000000, 1260416, 1135104 - 4, 1135104 + 125264 - 4):
            with self.subTest(address=address):
                integration = self.integration()
                self.update_catalog_function(integration, 0, address=address)
                with self.assertRaises(ValueError):
                    self.generate_integrated(integration)

    def test_invalid_instruction_boundaries_are_rejected(self):
        for field, value in (("address", 1135105), ("address", True), ("size", 0),
                             ("size", -4), ("size", 10), ("size", True)):
            with self.subTest(field=field, value=value):
                integration = self.integration()
                self.update_catalog_function(integration, 0, **{field: value})
                with self.assertRaises(ValueError):
                    self.generate_integrated(integration)

    def test_full_boot_gate_cannot_be_failed_partial_or_from_another_reference(self):
        original = self.integration()
        for field, value in (("matched", False), ("matched", 1), ("bytes_compared", 72),
                             ("bytes_compared", "2521763"), ("segments", 1),
                             ("reference_sha256", "0" * 64), ("candidate_sha256", "0" * 64)):
            with self.subTest(field=field, value=value):
                integration = copy.deepcopy(original)
                integration["full_boot_gate"][field] = value
                with self.assertRaises(ValueError):
                    self.generate_integrated(integration)
        for field, value in (("matched", False), ("bytes_compared", 72), ("reference_sha256", "0" * 64)):
            with self.subTest(progress_field=field):
                before = self.progress["g1"][field]
                self.progress["g1"][field] = value
                with self.assertRaises(ValueError):
                    self.generate_integrated(original)
                self.progress["g1"][field] = before

    def test_progress_and_byte_counts_must_agree_exactly(self):
        integration = self.integration()
        for field in ("integrated_functions", "decompiled_functions"):
            for value in (0, 6, 8, True, "7"):
                with self.subTest(field=field, value=value):
                    self.progress[field] = value
                    with self.assertRaises(ValueError):
                        self.generate_integrated(integration)
            self.progress[field] = 7
        for value in (0, 68, 76, "72", True):
            with self.subTest(bytes=value):
                integration["matched_code_bytes"] = value
                with self.assertRaises(ValueError):
                    self.generate_integrated(integration)

    def test_contradictory_optional_function_hashes_are_rejected(self):
        integration = self.integration()
        integration["functions"][0].update(reference_sha256="1" * 64, candidate_sha256="2" * 64)
        with self.assertRaisesRegex(ValueError, "hashes differ"):
            self.generate_integrated(integration)

    def test_raw_assembly_cannot_be_promoted_even_with_updated_source_hash(self):
        integration = self.integration()
        self.source += b'asm(".word 0");'
        integration["source_sha256"] = hashlib.sha256(self.source).hexdigest()
        with self.assertRaisesRegex(ValueError, "embed assembly"):
            self.generate_integrated(integration)

    def test_duplicate_catalog_and_overlapping_sections_are_rejected(self):
        integration = self.integration()
        self.catalog["functions"].append(copy.deepcopy(self.catalog["functions"][0]))
        integration["catalog_sha256"] = hashlib.sha256(self.catalog_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "Duplicate catalog"):
            self.generate_integrated(integration)
        self.progress["integrated_functions"] = self.progress["decompiled_functions"] = 0
        self.scope["programs"][0]["sections"].append(copy.deepcopy(self.scope["programs"][0]["sections"][0]))
        with self.assertRaisesRegex(ValueError, "Overlapping progress"):
            self.generate()

    def run_main(self, integration, proof=None):
        fixtures = {"config/progress-scope.json": self.scope, "config/target.json": self.target,
                    "config/overlays.json": self.overlays, "progress/report.json": self.progress,
                    "progress/integration.json": integration,
                    "progress/candidates.json": proof if proof is not None else self.object_proof}
        def read_text(path, **kwargs):
            return json.dumps(fixtures[path.relative_to(ROOT).as_posix()])
        with patch("sys.argv", ["decomp_report.py", "--output", str(ROOT / "unwritten-report.json")]), \
                patch.object(Path, "exists", return_value=integration is not None), \
                patch.object(Path, "read_text", autospec=True, side_effect=read_text), \
                patch.object(Path, "read_bytes", side_effect=[self.source, self.catalog_bytes()]), \
                patch.object(Path, "mkdir") as mkdir, patch.object(Path, "write_text") as write, \
                patch("sys.stdout", new_callable=io.StringIO) as stdout:
            try:
                status = report_module.main()
            except (ValueError, KeyError):
                mkdir.assert_not_called()
                write.assert_not_called()
                raise
            return status, write, stdout.getvalue()

    def test_main_reads_integration_and_validates_candidate_object_proof_before_writing(self):
        integration = self.integration()
        self.object_proof["catalog_sha256"] = integration["catalog_sha256"]
        status, write, stdout = self.run_main(integration)
        self.assertEqual(status, 0)
        report = json.loads(write.call_args.args[0])
        self.assertEqual(report["measures"]["matchedCode"], "716")
        self.assertEqual(json.loads(stdout)["matched_code"], "716")

    def test_main_baseline_without_integration_is_unchanged(self):
        status, write, stdout = self.run_main(None)
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(write.call_args.args[0]), self.generate())
        self.assertEqual(json.loads(stdout)["matched_code"], "0")

    def test_generation_preserves_inputs_and_does_not_depend_on_function_order(self):
        integration = self.integration()
        originals = copy.deepcopy((self.scope, self.target, self.overlays, self.progress, integration))
        report = self.generate_integrated(integration)
        self.assertEqual((self.scope, self.target, self.overlays, self.progress, integration), originals)
        integration["functions"].reverse()
        self.assertEqual(self.generate_integrated(integration), report)

    def test_main_requires_all_candidate_tools_but_allows_additional_boot_instruments(self):
        integration = self.integration()
        self.object_proof["catalog_sha256"] = integration["catalog_sha256"]
        missing = copy.deepcopy(integration)
        missing["tools"].pop("ee-gcc2953.exe")
        with self.assertRaisesRegex(ValueError, "instrument mismatch"):
            self.run_main(missing)
        integration["tools"]["Ps2EeAs.exe"] = "1" * 64
        status, write, stdout = self.run_main(integration)
        self.assertEqual(status, 0)

    def test_main_refuses_stale_optional_object_hash_and_malformed_object_proof(self):
        integration = self.integration()
        self.object_proof["catalog_sha256"] = integration["catalog_sha256"]
        integration["object_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "object proof hash mismatch"):
            self.run_main(integration)
        del integration["object_sha256"]
        for proof in ([], {**self.object_proof, "functions": [None]}):
            with self.subTest(proof=proof):
                with self.assertRaises(ValueError):
                    self.run_main(integration, proof)

    def test_full_boot_elf_is_distinct_from_candidate_elf_but_c_object_is_identical(self):
        integration = self.integration()
        self.object_proof["catalog_sha256"] = integration["catalog_sha256"]
        integration["candidate_elf_sha256"] = "2" * 64
        integration["c_object_sha256"] = self.object_proof["object_sha256"]
        status, write, stdout = self.run_main(integration)
        self.assertEqual(status, 0)
        integration["c_object_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "C object proof hash mismatch"):
            self.run_main(integration)

    def test_forged_integration_is_rejected_when_object_proof_is_invalid(self):
        integration = self.integration()
        self.object_proof["catalog_sha256"] = integration["catalog_sha256"]
        for field, value in (("object_sha256", "bad"), ("source_sha256", "0" * 64),
                             ("catalog_sha256", "0" * 64), ("target", "SCUS_971.99"),
                             ("tools", {"ee-gcc2953.exe": "0" * 64})):
            with self.subTest(field=field):
                proof = copy.deepcopy(self.object_proof)
                proof[field] = value
                with self.assertRaises(ValueError):
                    self.run_main(integration, proof)
        for field, value in (("matched", False), ("size", 8), ("different_bytes", 1),
                             ("candidate_sha256", "0" * 64)):
            with self.subTest(function_field=field):
                proof = copy.deepcopy(self.object_proof)
                proof["functions"][0][field] = value
                with self.assertRaises(ValueError):
                    self.run_main(integration, proof)
        proof = copy.deepcopy(self.object_proof)
        proof["functions"].pop(0)
        with self.assertRaises(ValueError):
            self.run_main(integration, proof)
        proof = copy.deepcopy(self.object_proof)
        proof["functions"].append(copy.deepcopy(proof["functions"][0]))
        with self.assertRaises(ValueError):
            self.run_main(integration, proof)
        integration["functions"][0].update(reference_sha256="1" * 64, candidate_sha256="1" * 64)
        with self.assertRaisesRegex(ValueError, "function hashes disagree"):
            self.run_main(integration)


if __name__ == "__main__":
    unittest.main()
