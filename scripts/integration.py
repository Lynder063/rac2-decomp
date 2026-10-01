"""Replace reviewed assembly bodies with genuine compiler-produced C sections."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from check_candidates import compare_function, file_hash, run, linker_script
from elf_tools import assert_fresh


ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION = re.compile(r"/\*\s+[0-9A-Fa-f]+\s+([0-9A-Fa-f]{8})\s+[0-9A-Fa-f]{8}\s*\*/")
HEADER = '.set noat\n.set noreorder\n.section .text, "ax"\n'


def split_assembly(content: str, functions: list[dict]) -> list[dict]:
    lines = content.splitlines(keepends=True)
    selected = sorted(functions, key=lambda function: function["address"])
    if len({function["address"] for function in selected}) != len(selected):
        raise ValueError("Duplicate integration address")
    edits = []
    previous_end = 0
    for function in selected:
        address, size = function["address"], function["size"]
        if size <= 0 or size % 4 or address % 4 or address < previous_end:
            raise ValueError("Invalid or overlapping integration boundary")
        if function["symbol"] != f"FUN_{address:08X}":
            raise ValueError("Integration symbol does not identify its address")
        previous_end = address + size
        original_symbol = f"func_{address:08X}"
        starts = [index for index, line in enumerate(lines) if line.strip() == f".globl {original_symbol}"]
        if len(starts) != 1:
            raise ValueError(f"Expected one original assembly definition: {original_symbol}")
        start = starts[0]
        if start + 1 >= len(lines) or lines[start + 1].strip() != original_symbol + ":":
            raise ValueError("Assembly function label is not contiguous")
        observed = []
        end = start + 2
        while end < len(lines):
            match = INSTRUCTION.search(lines[end])
            if not match:
                raise ValueError("Unexpected directive or label within promoted body")
            instruction_address = int(match.group(1), 16)
            expected_address = address + 4 * len(observed)
            if instruction_address != expected_address:
                raise ValueError("Disassembly addresses disagree with reviewed body")
            observed.append(instruction_address)
            end += 1
            if len(observed) * 4 == size:
                break
        if len(observed) * 4 != size:
            raise ValueError("Incomplete assembly body")
        edits.append((start, end, function))
    pieces = []
    cursor = 0
    for start, end, function in sorted(edits):
        fragment = "".join(lines[cursor:start])
        if INSTRUCTION.search(fragment):
            pieces.append({"kind": "asm", "content": HEADER + fragment})
        pieces.append({"kind": "c", "function": function})
        cursor = end
    remaining = "".join(lines[cursor:])
    if INSTRUCTION.search(remaining):
        pieces.append({"kind": "asm", "content": HEADER + remaining})
    return pieces


def compile_c(reference: Path, directory: Path, toolchain: Path) -> tuple[dict, Path, dict]:
    catalog = json.loads((ROOT / "config" / "candidate-catalog.json").read_text(encoding="utf-8"))
    candidates = json.loads((ROOT / "progress" / "candidates.json").read_text(encoding="utf-8"))
    source = ROOT / "candidates" / "boot.c"
    if file_hash(reference) != catalog["reference_sha256"] or file_hash(source) != candidates["source_sha256"]:
        raise ValueError("Integration inputs changed since candidate review")
    if file_hash(ROOT / "config" / "candidate-catalog.json") != candidates["catalog_sha256"]:
        raise ValueError("Integration catalogue changed since review")
    expected = {(entry["symbol"], entry["address"], entry["size"]) for entry in catalog["functions"]}
    actual = {(entry["symbol"], entry.get("address"), entry.get("size")) for entry in candidates["functions"]
              if entry["matched"]}
    if actual != expected or len(candidates["functions"]) != len(expected):
        raise ValueError("Every integrated function requires a complete candidate match")
    instrument_paths = {"ee-gcc2953.exe": toolchain / "bin" / "ee-gcc2953.exe",
                        "ee-as.exe": toolchain / "bin" / "ee-as.exe",
                        "ld.exe": toolchain / "ee" / "bin" / "ld.exe",
                        "cc1.exe": toolchain / "lib" / "gcc-lib" / "ee" / "2.95.3" / "cc1.exe",
                        "cpp.exe": toolchain / "lib" / "gcc-lib" / "ee" / "2.95.3" / "cpp.exe"}
    hashes = {name: file_hash(path) for name, path in instrument_paths.items()}
    if hashes != candidates["tools"]:
        raise ValueError("C integration instruments differ from the qualified candidate run")
    c_directory = directory / "build" / "c"
    c_directory.mkdir(parents=True)
    snapshot = c_directory / "boot.c"
    snapshot.write_bytes(source.read_bytes())
    if file_hash(snapshot) != candidates["source_sha256"]:
        raise ValueError("C source changed while creating the integration snapshot")
    catalog["compiled_source_sha256"] = candidates["source_sha256"]
    object_path = c_directory / "boot.c.o"
    run([str(instrument_paths["ee-gcc2953.exe"]), "-c", *catalog["flags"], str(snapshot), "-o", str(object_path)],
        directory / "compile-c.log")
    assert_fresh(object_path, [snapshot])
    qualification_script = c_directory / "qualification.ld"
    qualification_script.write_text(linker_script(catalog), encoding="ascii")
    qualified = c_directory / "qualification.elf"
    run([str(instrument_paths["ld.exe"]), "-T", str(qualification_script), "-o", str(qualified), str(object_path)],
        directory / "qualify-c-object.log")
    assert_fresh(qualified, [object_path, snapshot, qualification_script])
    results = [compare_function(reference, qualified, function["symbol"], function["address"], function["size"])
               for function in catalog["functions"]]
    if not all(result["matched"] for result in results):
        raise ValueError("The exact C object used for integration failed its independent candidate gate")
    object_proof = {"target": catalog["target"], "reference_sha256": file_hash(reference),
                    "source_sha256": file_hash(snapshot), "object_sha256": file_hash(object_path),
                    "candidate_elf_sha256": file_hash(qualified),
                    "catalog_sha256": file_hash(ROOT / "config" / "candidate-catalog.json"),
                    "checker_sha256": file_hash(ROOT / "scripts" / "check_candidates.py"),
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "tools": hashes, "flags": catalog["flags"], "functions": results,
                    "integrated_functions": 0,
                    "profile_scope": "Independent qualification of the exact object subsequently used in the full boot"}
    (directory / "object-qualification.json").write_text(json.dumps(object_proof, indent=2) + "\n", encoding="utf-8")
    return catalog, object_path, hashes


def replace_inputs(directory: Path, sources: list[Path], catalog: dict, c_object: Path) -> tuple[list[Path], dict]:
    script = directory / "config" / "rac2.ld"
    content = script.read_text(encoding="ascii")
    replacements = {}
    unchanged = []
    found = set()
    for source in sources:
        original = source.read_text(encoding="ascii")
        functions = [function for function in catalog["functions"]
                     if re.search(r"^\s*\.globl\s+func_" + f"{function['address']:08X}" + r"\s*$", original, re.MULTILINE)]
        if not functions:
            unchanged.append(source)
            continue
        declarations = re.findall(r"^\s*\.section\s+([^,\s]+)", original, re.MULTILINE)
        if any(name != ".text" for name in declarations):
            raise ValueError("Integration supports a pure text assembly input only")
        relative = source.relative_to(directory / "asm_pp")
        old_object = "build/asm/" + relative.as_posix() + ".o"
        old_text = old_object + "(.text);"
        if content.count(old_text) != 1:
            raise ValueError("Cannot identify one linked original text input")
        new_inputs = []
        pieces = split_assembly(original, functions)
        for index, piece in enumerate(pieces):
            if piece["kind"] == "c":
                function = piece["function"]
                found.add(function["symbol"])
                new_inputs.append(c_object.relative_to(directory).as_posix() + f"(.text.{function['symbol']});")
            else:
                fragment = directory / "asm_pp" / "integrated" / f"{source.stem}_{index}.s"
                fragment.parent.mkdir(exist_ok=True)
                fragment.write_text(piece["content"], encoding="ascii")
                unchanged.append(fragment)
                fragment_object = "build/asm/" + fragment.relative_to(directory / "asm_pp").as_posix() + ".o"
                new_inputs.append(fragment_object + "(.text);")
        content = content.replace(old_text, "\n        ".join(new_inputs))
        content = re.sub(re.escape(old_object) + r"\(\.(?:data|rodata|bss)\);", "", content)
        replacements[relative.as_posix()] = [function["symbol"] for function in functions]
    if found != {function["symbol"] for function in catalog["functions"]}:
        raise ValueError("Not all reviewed C bodies replaced original assembly inputs")
    script.write_text(content, encoding="ascii")
    return unchanged, replacements


def add_definitions(directory: Path, catalog: dict) -> None:
    path = directory / "config" / "undefined_symbols.ld"
    content = path.read_text(encoding="ascii")
    for function in catalog["functions"]:
        original = f"func_{function['address']:08X}"
        content = re.sub(r"^" + re.escape(original) + r"\s*=.*?;\s*$", "", content, flags=re.MULTILINE)
        content += f"{original} = {function['symbol']};\n"
    for name, address in catalog["externals"].items():
        content = re.sub(r"^" + re.escape(name) + r"\s*=.*?;\s*$", "", content, flags=re.MULTILINE)
        content += f"{name} = 0x{address:08X};\n"
    content += f"_gp = 0x{catalog['gp']:08X};\n"
    path.write_text(content, encoding="ascii")


def validate_integrated(reference: Path, candidate: Path, catalog: dict, source: Path) -> list[dict]:
    if file_hash(source) != catalog["compiled_source_sha256"]:
        raise ValueError("Public C source changed after the compiled integration snapshot")
    results = [compare_function(reference, candidate, function["symbol"], function["address"], function["size"])
               for function in catalog["functions"]]
    if not all(result["matched"] for result in results):
        raise ValueError("An integrated C body failed the complete post-link comparison")
    for result in results:
        result.update({"integrated": True, "program": "boot"})
        result["state"] = "integrated"
    return results
