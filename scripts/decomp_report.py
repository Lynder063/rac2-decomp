"""Export RAC2 section totals and proven C integrations in objdiff report v2 format."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOT_LOAD_BYTES = 2521763
BOOT_LOAD_SEGMENTS = 2


def measures(code_size: int, data_size: int, units: int,
             complete_code: int = 0, complete_units: int = 0) -> dict:
    percent = complete_code / code_size * 100 if code_size else 0
    fuzzy_percent = complete_code / (code_size + data_size) * 100 if code_size + data_size else 0
    return {"totalCode": str(code_size), "matchedCode": str(complete_code), "matchedCodePercent": percent,
            "totalData": str(data_size), "matchedData": "0", "matchedDataPercent": 0,
            "completeCode": str(complete_code), "completeCodePercent": percent, "completeData": "0",
            "completeDataPercent": 0, "fuzzyMatchPercent": fuzzy_percent,
            "totalUnits": units, "completeUnits": complete_units}


def require_hash(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Proof requires SHA-256 hashes")


def require_tools(value: object) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError("Proof requires instrument hashes")
    for name, digest in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Invalid proof instrument")
        require_hash(digest)


def validate_integration(integration: dict, target: dict, progress: dict) -> list[dict]:
    if not isinstance(integration, dict):
        raise ValueError("Invalid integration proof")
    if (integration.get("target") != target["serial"]
            or progress.get("target") != target["serial"]
            or integration.get("reference_sha256") != target["boot"]["sha256"]
            or integration.get("state") != "integrated"
            or integration.get("candidate_source") != "candidates/boot.c"):
        raise ValueError("Integration identity, source or state mismatch")
    for field in ("reference_sha256", "source_sha256", "catalog_sha256"):
        require_hash(integration.get(field))
    require_tools(integration.get("tools"))
    source = (ROOT / "candidates/boot.c").read_bytes()
    catalog_bytes = (ROOT / "config/candidate-catalog.json").read_bytes()
    if (hashlib.sha256(source).hexdigest() != integration["source_sha256"]
            or hashlib.sha256(catalog_bytes).hexdigest() != integration["catalog_sha256"]):
        raise ValueError("Integration source or catalog hash mismatch")
    if re.search(rb"\b(?:asm|__asm__|__asm|INCLUDE_ASM)\b|\.byte|\.word", source):
        raise ValueError("Integrated C must not embed assembly or retail bytes")
    catalog = json.loads(catalog_bytes)
    if (catalog["target"] != target["serial"]
            or catalog["reference_sha256"] != target["boot"]["sha256"]):
        raise ValueError("Candidate catalog identity mismatch")
    known = {function["symbol"]: function for function in catalog["functions"]}
    if len(known) != len(catalog["functions"]):
        raise ValueError("Duplicate catalog function")
    gate = integration.get("full_boot_gate")
    if (not isinstance(gate, dict) or gate.get("matched") is not True
            or type(gate.get("bytes_compared")) is not int
            or gate["bytes_compared"] != BOOT_LOAD_BYTES
            or type(gate.get("segments")) is not int or gate["segments"] != BOOT_LOAD_SEGMENTS):
        raise ValueError("Integration requires the complete boot gate")
    boot_gate = progress.get("g1", {})
    if (boot_gate.get("matched") is not True
            or boot_gate.get("reference_sha256") != target["boot"]["sha256"]
            or type(boot_gate.get("bytes_compared")) is not int
            or boot_gate["bytes_compared"] != BOOT_LOAD_BYTES):
        raise ValueError("Progress boot gate contradicts integration")
    for field in ("reference_sha256", "candidate_sha256"):
        if field in gate and gate[field] != boot_gate.get(field):
            raise ValueError("Integration boot gate identity mismatch")
    for field in ("object_sha256", "c_object_sha256", "candidate_elf_sha256", "checker_sha256"):
        if field in integration:
            require_hash(integration[field])
    functions = integration.get("functions")
    if not isinstance(functions, list) or not functions:
        raise ValueError("Integration requires complete C functions")
    seen = set()
    for function in functions:
        if not isinstance(function, dict):
            raise ValueError("Invalid integrated function")
        symbol = function.get("symbol")
        address, size = function.get("address"), function.get("size")
        if not isinstance(symbol, str) or symbol not in known or symbol in seen:
            raise ValueError("Unknown or duplicate integrated function")
        seen.add(symbol)
        if (function.get("matched") is not True or function.get("integrated") is not True
                or function.get("program") != "boot"
                or type(address) is not int or address < 0 or address % 4
                or type(size) is not int or size <= 0 or size % 4
                or address != known[symbol]["address"] or size != known[symbol]["size"]):
            raise ValueError("Integration requires the complete catalogued boot function")
        if "different_bytes" in function and function["different_bytes"] != 0:
            raise ValueError("Integrated function has mismatched bytes")
        if "reference_sha256" in function or "candidate_sha256" in function:
            require_hash(function.get("reference_sha256"))
            require_hash(function.get("candidate_sha256"))
            if function["reference_sha256"] != function["candidate_sha256"]:
                raise ValueError("Integrated function byte hashes differ")
    functions = sorted(functions, key=lambda function: function["address"])
    for previous, current in zip(functions, functions[1:]):
        if previous["address"] + previous["size"] > current["address"]:
            raise ValueError("Overlapping integrated functions")
    for field in ("integrated_functions", "decompiled_functions"):
        if type(progress.get(field)) is not int or progress[field] != len(functions):
            raise ValueError("Progress function count contradicts integration")
    if (type(integration.get("matched_code_bytes")) is not int
            or integration["matched_code_bytes"] != sum(function["size"] for function in functions)):
        raise ValueError("Integration byte count mismatch")
    return functions


def validate_object_proof(integration: dict, proof: dict) -> None:
    if not isinstance(proof, dict):
        raise ValueError("Invalid candidate object proof")
    for field in ("target", "reference_sha256", "source_sha256", "catalog_sha256"):
        if proof.get(field) != integration.get(field):
            raise ValueError("Candidate object proof identity mismatch")
    for field in ("object_sha256", "candidate_elf_sha256", "checker_sha256"):
        require_hash(proof.get(field))
        if field != "candidate_elf_sha256" and field in integration and integration[field] != proof[field]:
            raise ValueError("Candidate object proof hash mismatch")
    if "c_object_sha256" in integration and integration["c_object_sha256"] != proof["object_sha256"]:
        raise ValueError("Integrated C object proof hash mismatch")
    require_tools(proof.get("tools"))
    if any(integration["tools"].get(name) != digest for name, digest in proof["tools"].items()):
        raise ValueError("Candidate object proof instrument mismatch")
    results = proof.get("functions")
    if not isinstance(results, list) or any(not isinstance(result, dict) for result in results):
        raise ValueError("Invalid candidate object function proof")
    known = {result["symbol"]: result for result in results}
    if len(known) != len(results):
        raise ValueError("Duplicate candidate object function proof")
    for function in integration["functions"]:
        result = known.get(function["symbol"], {})
        if (result.get("matched") is not True or result.get("different_bytes") != 0
                or type(result.get("address")) is not int or result["address"] != function["address"]
                or type(result.get("size")) is not int or result["size"] != function["size"]):
            raise ValueError("Invalid complete candidate object function proof")
        require_hash(result.get("reference_sha256"))
        require_hash(result.get("candidate_sha256"))
        if result["reference_sha256"] != result["candidate_sha256"]:
            raise ValueError("Candidate object function bytes differ")
        for field in ("reference_sha256", "candidate_sha256"):
            if field in function and function[field] != result[field]:
                raise ValueError("Integration and candidate object function hashes disagree")


def generate(scope: dict, target: dict, overlays: dict, progress: dict,
             integration: dict | None = None) -> dict:
    if scope["target"] != target["serial"] or overlays["target"] != target["serial"]:
        raise ValueError("Progress scope belongs to another target")
    for field in ("decompiled_functions", "integrated_functions"):
        count = progress.get(field, 0)
        if type(count) is not int or count < 0:
            raise ValueError("Invalid progress function count")
        if count and integration is None:
            raise ValueError("C/C++ progress requires a valid integration proof")
    expected = {"boot": target["boot"]["sha256"],
                **{"levels/" + entry["level"]: entry["sha256"] for entry in overlays["levels"]}}
    programs = scope["programs"]
    actual = {program["name"]: program["sha256"] for program in programs}
    if len(programs) != 28 or len(actual) != len(programs) or actual != expected:
        raise ValueError("Progress scope must cover the pinned boot and all 27 overlays")
    functions = [] if integration is None else validate_integration(integration, target, progress)
    owners = {}
    for program in programs:
        occupied = []
        for section in program["sections"]:
            size, address = section["size"], section["address"]
            if (type(size) is not int or size <= 0 or type(address) is not int or address < 0
                    or type(section["flags"]) is not int or not section["flags"] & 2
                    or section["type"] != 1):
                raise ValueError("Progress scope requires positive, allocated PROGBITS sections")
            if any(address < ending and starting < address + size for starting, ending in occupied):
                raise ValueError("Overlapping progress sections")
            occupied.append((address, address + size))
            if program["name"] == "boot" and section["flags"] & 4:
                for function in functions:
                    if address <= function["address"] and function["address"] + function["size"] <= address + size:
                        owners[function["symbol"]] = section
    if len(owners) != len(functions):
        raise ValueError("Integrated function is outside an executable boot section")
    units = []
    total_code = 0
    total_data = 0
    seen_names = set()
    for program in programs:
        for section in program["sections"]:
            size = section["size"]
            name = f"{program['name']}/{section['name']}@{section['address']:08X}"
            if name in seen_names:
                raise ValueError("Duplicate progress unit")
            seen_names.add(name)
            is_code = bool(section["flags"] & 4)
            code_size = size if is_code else 0
            data_size = 0 if is_code else size
            total_code += code_size
            total_data += data_size
            category = "boot" if program["name"] == "boot" else "levels"
            promoted = [function for function in functions if owners[function["symbol"]] is section]
            remaining = size - sum(function["size"] for function in promoted)
            for function in promoted:
                units.append({"name": f"boot/candidates/boot.c/{function['symbol']}",
                              "measures": measures(function["size"], 0, 1, function["size"], 1),
                              "sections": [{"name": section["name"], "size": str(function["size"]),
                                            "fuzzyMatchPercent": 100,
                                            "metadata": {"virtualAddress": str(function["address"])}}],
                              "functions": [{"name": function["symbol"], "size": str(function["size"]),
                                             "fuzzyMatchPercent": 100,
                                             "metadata": {"virtualAddress": str(function["address"])}}],
                              "metadata": {"complete": True, "autoGenerated": False,
                                           "sourcePath": "candidates/boot.c", "moduleName": "boot",
                                           "progressCategories": ["boot"]}})
            if not remaining:
                continue
            code_size = remaining if is_code else 0
            data_size = 0 if is_code else remaining
            units.append({"name": name, "measures": measures(code_size, data_size, 1),
                          "sections": [{"name": section["name"], "size": str(remaining),
                                        "fuzzyMatchPercent": 0,
                                        "metadata": {"virtualAddress": str(section["address"])}}],
                          "metadata": {"complete": False, "autoGenerated": True,
                                       "moduleName": program["name"], "progressCategories": [category]}})
    if not total_code:
        raise ValueError("Empty executable progress scope")
    categories = []
    for category, title in (("boot", "Boot ELF"), ("levels", "27 level overlays")):
        subset = [unit for unit in units if category in unit["metadata"]["progressCategories"]]
        categories.append({"id": category, "name": title,
                           "measures": measures(sum(int(unit["measures"]["totalCode"]) for unit in subset),
                                                sum(int(unit["measures"]["totalData"]) for unit in subset),
                                                len(subset),
                                                sum(int(unit["measures"]["completeCode"]) for unit in subset),
                                                sum(unit["measures"]["completeUnits"] for unit in subset))})
    return {"version": 2, "measures": measures(total_code, total_data, len(units),
                                               sum(function["size"] for function in functions), len(functions)),
            "units": units, "categories": categories}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export RAC2 C/C++ progress with integration evidence")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    def read(relative: str) -> dict:
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))
    integration = read("progress/integration.json") if (ROOT / "progress/integration.json").exists() else None
    report = generate(read("config/progress-scope.json"), read("config/target.json"),
                      read("config/overlays.json"), read("progress/report.json"), integration)
    if integration is not None:
        validate_object_proof(integration, read("progress/candidates.json"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "units": len(report["units"]),
                      "total_code": report["measures"]["totalCode"],
                      "matched_code": report["measures"]["matchedCode"]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"Report export failed: {error}")
        raise SystemExit(2)
