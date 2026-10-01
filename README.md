# RAC2 - Going Commando

Preparation and byte-exact decompilation tooling for **Ratchet & Clank:
Going Commando, USA v1.01, SCUS_972.68**. This is part of project 45.

The goal is original game code running natively on PC. This repository is an
initial reconstruction workspace, not a playable PC port. Assembly reconstruction
does not count as C/C++ decompilation. See `progress/report.json` for measured status.

Verified on **2026-10-01**: the complete boot image (**2,521,763 loaded bytes,
two PT_LOAD segments**) and **all 27 level overlays** rebuild identically in loaded
memory. **81 tool tests pass**. C/C++ decompiled functions: **0**. The compiler
profile and native runtime remain to be established.

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
