# RAC2 - Going Commando

Preparation and byte-exact decompilation tooling for **Ratchet & Clank:
Going Commando, USA v1.01, SCUS_972.68**. This is part of project 45.

The goal is original game code running natively on PC. This repository is an
initial reconstruction workspace, not a playable PC port. Assembly reconstruction
does not count as C/C++ decompilation. See `progress/report.json` for measured status.

Verified on **2026-10-01**: the complete boot image (**2,521,763 loaded bytes,
two PT_LOAD segments**) and **all 27 level overlays** rebuild identically in loaded
memory. **99 tool tests pass**. **Seven initial C candidates (72 bytes) match
completely after compilation and link, and await integration.** Integrated C/C++
functions: **0**. The general compiler profile and native runtime remain to be established.

## Requirements

- Python 3.12 and the pinned dependencies in `requirements.txt`.
- A local image of your own matching game disc (or a local archive of that image).
- Wrench `wrenchbuild` for unpacking level executables.
- Windows and a locally supplied **SN ProDG 2.0** EE toolchain containing `ee/bin/Ps2EeAs.exe`
  and `ee/bin/ld.exe`. No SDK is supplied or downloaded by these scripts.

The target's size and disc hashes are pinned in `config/target.json` against
[Redump disc 13103](https://redump.info/disc/13103). Boot identity is measured
locally. Greatest Hits v2.00 and other regions are different targets.

## Prepare locally

Use a short runtime directory **outside** this repository. Each preparation and
build creates a new directory, preserving prior evidence and avoiding stale output.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/setup.py --iso <disc.iso> --runtime D:\RAC2\runtime --wrench <wrenchbuild.exe>
```

For an archive, replace `--iso` with `--archive <archive.7z> --sevenzip <7z.exe>`.
The entire extracted ISO is verified before any analysis or unpacking. The setup
reads ISO9660 directly to extract and verify `SYSTEM.CNF` and the boot executable;
it derives the GP register from `.reginfo`, not from a RAC1 address.
`config/boot-sections.json` records the measured section/segment inventory;
`config/overlays.json` pins the 27 extracted level executables. Neither is a
reviewed function-boundary catalogue.

`<runtime>/latest.json` points to the successful preparation manifest. Use that
manifest explicitly to reconstruct and compare the boot and all 27 overlays:

```powershell
.venv\Scripts\python.exe scripts/build.py --manifest <manifest.json> --toolchain <EE-gcc-directory> --all-levels
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Lessons carried forward from RAC1

- Verify the exact edition, SHA-256, program, virtual address and size together.
  Identical addresses in different overlays do not identify the same function.
- Keep generated assembly, assets, runtime outputs, SDKs and private manifests
  local. Only source tools and sanitized measurements belong in this repository.
- Keep ELF section order and explicit virtual addresses. Derive splat's duplicate
  object names from each ELF; do not reuse RAC1 offsets. GC has two PT_LOAD
  segments and repeated section names, so compare **both** segments and give
  repeated names distinct generated identifiers.
- Require successful subprocess exit codes, newly generated output, exact lengths,
  entry point, segment flags and memory sizes. Never count a matching prefix,
  zero-sized alias, copied oracle, ELF magic, or stale build as a reconstruction.
- VU operand ordering, negative zero and linker padding fixes inherited from RAC1
  remain subject to the RAC2 byte gate; they are not assumptions of correctness.
- Wrench produces 27 level executables. Internal level identifiers are not
  contiguous. The boot's `map level` strings cover fewer levels than the disc.
- Compiler choice, optimization, GP-relative access, stack frames, relocations,
  function boundaries and delay slots must be measured on RAC2 independently.
  The RAC1 `-O2 -G2` profile is deliberately **not** declared valid for RAC2.
- Native runtime work must execute original code; HLE replacements and movie
  playback are not evidence of a functioning native game.

## Initial C candidate lot

`candidates/boot.c` contains seven project-authored leaf functions. Their initial
neutral address-based names are retained; engine-purpose names are not inferred.
Ghidra's saved GC programme was reopened read-only with its SHA-256 and R5900
language verified. All seven contiguous bodies, callers and return delay slots
were reviewed. `config/candidate-catalog.json` records their individual boundaries.

```powershell
.venv\Scripts\python.exe scripts/check_candidates.py --reference <boot.elf> --toolchain <SN-ProDG-3.01-EE-gcc-directory> --runtime D:\RAC2\runtime
```

This lot uses `ee-gcc2953.exe`, its GNU `ee-as.exe`, and `ld.exe`, with
`-O2 -G0 -ffunction-sections`. Those settings are measured for these seven small
functions only. They are not a qualified profile for the remaining SDK or game
functions. In particular, a 64-bit zero-return declaration emitted `por`, while
the 32-bit declaration emitted the required `daddu`; the failed attempt is not
counted. The original API widths beyond the observed accesses remain to be studied.

The gate requires a fresh compile/link, a defined global STT_FUNC symbol, its
exact address and **full symbol size**, and all its bytes. Absolute aliases,
zero-size symbols, unlinked objects and identical prefixes with extra code are
refused. A deliberately wrong pointer-return candidate was compiled and rejected.
`progress/candidates.json` records reproducible source, tool and byte hashes.

These candidates are **not integrated** into the whole-game reconstruction.
The reconstruction and decomp.dev reports therefore retain zero integrated
C/C++ progress. The next milestone is a separately validated integration gate
that replaces only these reviewed assembly bodies and rechecks the full boot.

## decomp.dev reporting

The CI uploads `SCUS_972.68_report` in objdiff report v2 format. It records
**0% C/C++ decompilation**, independently of the successful assembly reconstruction
gates in `progress/report.json`. The measured scope includes the boot and all 27
overlays, with executable and initialized-data section sizes, including VU code.
Function counts are omitted until boundaries have been reviewed. Generated section
units are placeholders for that future catalogue, not completed translation units.

`python scripts/decomp_report.py --output build/decomp/report.json` regenerates
the baseline using metadata only; it requires no game assets or proprietary SDK
in GitHub Actions. Once C/C++ matches exist, it refuses to export the old zero
baseline and must be replaced with verified objdiff object-level measurements.

## Next milestones

1. Keep the established boot and 27-overlay reconstruction gates passing.
2. Build a RAC2-specific function catalogue with reviewed boundaries and stable
   `(ELF SHA-256, level, address, size)` identities; labels alone are not proof.
3. Qualify the compiler/assembler combinations against real SDK and game functions.
4. Decompile and validate C/C++ units independently before any integration.
5. Develop and validate the native runtime against the matching PS2 edition.

No game assets, proprietary SDK, reconstructed executable, or copied retail
assembly is distributed. Third-party dependencies are installed separately; this
repository currently includes only project-45-authored tools and measurements.
