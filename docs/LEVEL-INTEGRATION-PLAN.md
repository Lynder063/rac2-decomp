# Level integration of the integrated C: what it takes

Measured 2026-10-01, on the same pinned image as the first two C lots.

## Why this is the next step

The level overlay programs are the same engine compiled into 28 programs: the
boot's 17 integrated C functions appear again inside each overlay - **13 of the
17 in every one of the 27 levels** (the four tiny boot-only accessors are the
exception). Their addresses differ per level, and the mapping is measured, not
assumed: byte search of each function's exact body, disambiguated for bodies
that are byte-identical to each other.

    couples (function, level) : 351 / 459        D:\RAC2\work\catalogues-niveaux.json

If the levels count the same way the boot does - one program at a time, which is
how the 48,788,176-byte total is built - the present 716 bytes become about
**18,750 bytes counted** (about 0.038 %), without writing a line of new C.

## What is missing

1. **Per-level linker scripts.** `scripts/integration.py` already places each C
   function in its own section (`.text.FUN_xxxxxxxx`) through a generated linker
   script, so the same compiled object can be re-linked at another set of
   addresses. A catalog per level (symbol, address, size) is all it needs; the
   first one is measured above.
2. **A level build that integrates.** `scripts/build.py --all-levels` rebuilds
   and verifies every overlay from assembly, but the C path (`--c-toolchain`) is
   wired for the boot only. The overlay rebuild needs the same treatment the boot
   already has: substitute the C sections, then compare all loaded bytes.
3. **A report that counts per program.** `scripts/decomp_report.py` validates the
   scope as 28 programs but takes its matched bytes from the single boot
   integration proof, so a level match currently counts for nothing. The proof
   format already carries per-program identity; the report needs a proof per
   program and a matched-bytes sum across them.

## What is explicitly not assumed

- That a function present in a level sits in an executable section there (to be
  checked per level, like `owners` does for the boot).
- That the level's copy is reachable the same way; the comparison gate decides.
- That any of this raises the reported figure until the report counts it: the
  number to watch stays `matchedCode` in `build/decomp/report.json`.

## Order of work

1. Catalog per level (done: `catalogues-niveaux.json`, 351 couples).
2. Overlay integration on one level (0_aranos_tutorial), full-gate compared.
3. The other 26, then the per-program report change.
4. Only then port more C: each additional distinct byte counts 28 times.
