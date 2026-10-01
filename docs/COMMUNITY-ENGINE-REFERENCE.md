# Ratchet & Clank: Going Commando (RaC2) Reverse-Engineering Intelligence

Synthesized from the `#rac-ps2-reverse-engineering` community research archive (2018–2026), Aug 8 2002 prototype datamining, and cross-game engine analysis.

---

## 1. Versions & Target Executable

| Build | Serial / Info | Significance & Notes |
|---|---|---|
| **NTSC-U v2.00 (Greatest Hits)** | `SCUS_972.68` (`4124a79c1...`) | Primary target executable. Entry point `0x00131AE8`, GP base `0x001AEFF0`. |
| NTSC-U v1.01 (Black Label) | `SCUS_972.68` | First retail press; minor differences from GH. |
| JP / KR / Greatest Hits | Various | According to @foas (2020), **UYA's multiplayer engine was branched from the RaC2 JP/KR/GH codebase**. Symbols and shared structures in UYA (`ratchet-uya-decomp`) map closely to this target. |
| Aug 8 2002 Prototype | Debug build | Core ELF is larger (`.lit` at `0x001af780` vs retail `0x001a8300`). Certain level overlays were compiled against a different internal build, causing broken overlay links. Rich in assert strings, symbols, and author initials. |
| PS3 HD Port (Idol Minds) | EBOOT.BIN | Contains level-stacking artifacts; EBOOT retains ~8 never-called duplicates of the hero movement code. |
| Vita Port (Mass Media) | `boot.cpp` leak | Path leak: `C:\projects\RCVita\RC_Vita\rc2\code\game\boot.cpp`. Exposes a centralized `switch(LevelId)` function-pointer dispatch and an 8,192-entry global Moby update table. |

---

## 2. Toolchain & Runtime Environment

- **Compiler**: SN Systems ProDG GCC 2.95.3 (`ee-gcc2953.exe` / `ee-gcc`)
- **PS2 SDK**: Sony Computer Entertainment PS2 SDK **2.5.5**
- **Gamepad Subsystem**: `libpad2` / `scePad2` (`PsIIlibpad2 2500` detected in `core.data`). RaC3/DL moved to `scePad`.
- **Audio Subsystem**: 989snd v2 (migrated to SCREAM in Vita/PS3 ports). Disc I/O runs through 989snd IOP RPC.
- **Global Pointer (`$gp`)**: `0x001AEFF0` (Elf32_RegInfo `ri_gp_value`)
- **Entry Point**: `0x00131AE8` (`crt0` startup in `core.text`)

---

## 3. Binary & Dynamic Overlay Layout

The game uses dynamic level overlays loaded over the high memory region:

```
[0x00100080 - 0x00115200]  .vutext       (VU0/VU1 microcode)
[0x00115200 - 0x00133B80]  core.text     (Engine core, OS/IOP interface, ParseBin)
[0x00133B80 - 0x0013A200]  core.data     (Core globals, libpad2, 989snd descriptors)
[0x0013A200 - 0x0013C080]  core.rdata    (Core string literals & tables)
[0x0013C080 - 0x001A7480]  core.bss      (Zero-initialized core memory)
[0x001A7480 - 0x001A7C80]  core.lit      (Small core constants in $gp window)
----------------------------------------------------------------------------------
[0x001A7C80 - 0x001B1300]  .lit          (Level/Game constants in $gp window)
[0x001B1300 - 0x00238C00]  .bss          (Gameplay dynamic zero-initialized heap)
[0x00238C00 - 0x0026E880]  .data         (Gameplay initialized state)
[0x0026E880 - 0x0026E88C]  lvl.vtbl      (Level vtable descriptor)
[0x0026E900 - 0x0026E914]  lvl.camvtbl   (Level camera vtable descriptor)
[0x0026E980 - 0x0026E988]  lvl.sndvtbl   (Level sound vtable descriptor)
[0x0026EA00 - 0x00352D08]  .text         (Main gameplay, player, and actor logic)
[0x01800000 - 0x01815570]  extra         (Legal screens & memory card assets)
```

- **Frontend Overlays**: Boot/frontend UI is managed via `.DVP.ovlytab` overlay tables inside the main ELF.
- **Level Overlays**: Level switching swaps `.lit`, `.bss`, `.data`, the three `lvl.*vtbl` structures, and `.text`.
- **Level Headers**: Stored in `RC2.HDR` and duplicated inside the disc Table of Contents (ToC).

---

## 4. Reverse-Engineered Core Subsystems

### 4.1 Moby Object Model (`include/moby.h`)
- All dynamic entities (Ratchet, enemies, crates, hazards, projectiles) are **Mobies**.
- **Layout Compatibility**: The first `0x28` bytes directly match Deadlocked (`MobyInstance`) and UYA:
  - `0x00`: Position `(X, Y, Z)` as 3x `f32`
  - `0x0C`: `state` (u8)
  - `0x0D`: `group` (u8, collision group)
  - `0x0E`: `mclass` (u8, class sub-type)
  - `0x0F`: `alpha` (u8, transparency/fade)
  - `0x10`: Rotation `(Pitch, Yaw, Roll)` as 3x `f32`
  - `0x1C`: `scale` (u8)
  - `0x1D`: `drawDistance` (u8)
  - `0x1E`: `modeBits` (u16) — bit `0x40` indicates **No Pre-Update** (`MOBY_MODE_NO_PRE_UPDATE`)
  - `0x20`: `pModel` (pointer to model mesh)
  - `0x24`: `pParent` (parent joint/moby pointer)
  - `0x64`: `pUpdate` — per-tick function pointer (`void (*)(Moby *)`)
  - `0x68`: `pVar` — pointer to moby-specific state structure
  - `0x6C`: `oClass` — Object Class ID (e.g. `4351` = Clank-switch debug trigger in Nebula G34)
  - `0x6E`: `UID` — Unique actor ID in loaded level
- **Dispatch**:
  - `CreateMobyChain(void)`
  - `PreUpdateMoby(Moby *moby)`
  - `PostUpdateMoby(Moby *moby)`
  - Vita port confirms global moby update table capacity of **8,192 entries**.

### 4.2 Weapon Modification System (`include/weapons.h`)
- In RaC2 (and shared with RaC3), weapon mods are stored as bitmasks per byte in a global table indexed by `weaponId`:
  - `0x01` (`1 << 0`): Lock-on mod
  - `0x02` (`1 << 1`): Shock mod
  - `0x04` (`1 << 2`): Acid mod

### 4.3 Event & Progression Flags (`include/flags.h`)
- Internal flag naming recovered from prototype datamining:
  - Format: `GLOBAL_RC2FLAG_L<level_id>_evt_<event_id>` (e.g. `GLOBAL_RC2FLAG_L01_evt_02`).
- Challenge Mode state:
  - Retail code strictly tests `challenge_mode > 0` (or `!= 0`).

### 4.4 RaC1 Save Import Gadgets (`include/gadgets.h`)
- RaC2 contains logic to detect RaC1 saves and unlock legacy weapons for free.
- The enum names in RaC2 directly mirror RaC1's internal `GADGET_*` enum (Bomb Glove, Pyrocitor, Blaster, Glove of Doom, Suck Cannon, Swingshot, RYNO, etc.).

### 4.5 Controller & Frontend Quirks
- In the RaC2 title screen, `R2` and the Right Stick do not satisfy the "Press START" condition.
- The Left Analog Stick is internally remapped to D-pad directional pulses.
- The title screen sofa animation ("Ratchet watching TV") is an IPU/FMV streaming video in RaC2/RaC3, unlike RaC1 where it was rendered in real-time engine 3D.

---

## 5. Community Ecosystem & Tools Reference

| Tool / Repository | Author | Reusable Assets & Insights |
|---|---|---|
| `codeberg.org/CreepNT/rc2_aug8_research` | @creepnt | `iso_toc_fix.py`, `iso_overlay_surgeon.py` (overlay extract/inject), PCSX2 semihosting printf patcher, `level_correlator.py` (matching mobys/funcs across levels), ImHex templates. |
| `github.com/CreepNT/MobyViewer` | @creepnt | Moby live memory inspection tool (runs against PCSX2). Useful for verifying moby struct offsets in real time. |
| `wrench` | @chaoticgd | Full parser for RaC2 Table of Contents, `RC2.HDR`, and `.WAD` level archives. |
| Archipelago Randomizer | @evilwb | Contains local Ghidra project with named symbols, moby update dispatch tables, and intro-skip patches. |
| `github.com/Metroynome/rac-cheats` / `libgc` | @agentmoose | C cheat library with known memory offsets for player state, bolts, weapons, and level variables. |
| Native ARM64/Metal Port | @protonfission | Verified level overlay mappings, confirmed function execution against PCSX2 state captures. |
| `RAC2Decomp` (AI repo) | platypet2217-star | **Caution**: Criticized by community for questionable provenance and non-clean-room C code. Avoid copying. |
