# Developing, Building, and Releasing Graveblood_RE

`reconstruction/` is a CFA-style Game Boy Advance project built directly with **devkitPro / devkitARM / libgba**. There is no external engine checkout.

The original `Graveblood 0.0.1.1.5.2 demo.gba` remains reverse-engineering evidence. It is **not a normal reconstruction build input**.

## 1. Install the GBA toolchain

Install devkitPro and the **GBA Development** component (`gba-dev`). This supplies devkitARM, `gba_rules`, libgba, gbafix, and the normal GBA build utilities.

Typical installations:

- Windows: `C:\devkitPro`
- macOS/Linux: `/opt/devkitpro`

If needed, set:

```sh
export DEVKITPRO=/opt/devkitpro
export DEVKITARM=/opt/devkitpro/devkitARM
```

PowerShell equivalent:

```powershell
$env:DEVKITPRO = 'C:\devkitPro'
$env:DEVKITARM = 'C:\devkitPro\devkitARM'
```

The project intentionally uses the same `$(DEVKITARM)/gba_rules` + `-lgba` pattern as current official devkitPro GBA examples.

## 2. Build

From the repository root:

```sh
make -C reconstruction -j4
```

Expected ROM:

```text
reconstruction/Graveblood_RE.gba
```

Clean:

```sh
make -C reconstruction clean
```

Then rebuild normally.

## 3. Current ROM milestone

The current build is no longer a framebuffer/color smoke test. It boots into the recovered canonical **Title scene**, where fresh START plays SFX 6 and enters Level 7 after the original 120-update pending delay. The title uses the exact recovered Mode-0 setup (`DISPCNT=0x1F00`): BG0 text on screenblock 27, BG1 30x20 artwork on screenblock 28, BG2/BG3 64x32 backing, 223-entry BG palette, 0x8000-byte OBJ bank, 91-entry OBJ palette plus the 32-color high OBJ patch, canonical hidden OAM, original animation/prompt timing, and intentionally no music because the exhaustive loop-player scan contains no Title call. Gameplay then provides:

- recovered four-background Mode 0 layout (BG0 UI, streamed BG1/BG2 world, quarter-speed BG3 parallax);
- exact original BG graphics/palettes plus raw streamed world layers and translation tables for all **11 levels / 13 graphics variants**;
- recovered player spawn points for every level;
- recovered u16 8-pixel collision grids (`0 = walkable`, nonzero = blocked); Level 6 intentionally reuses ROM array `0x08655CC4` for both LevelRecord `+0x0C` collision and `+0x10` visual-B source data, but the loader copies those fields to distinct globals (`0x03000550` / `0x03000564`) and the collision solver / BG streamer consume them independently;
- hardware OAM Player sprite with the recovered 24-frame walk/idle animation set (including the level-authored alternate idle bank), retained horizontal facing, and right-facing H-flip;
- ROM-accurate persistent camera globals with the Player body center held inside the recovered X=96..144 / Y=67..93 pixel dead-zone; camera state survives level loads, then clamps to the 30x20-tile viewport and drives the 32x32 ring-buffer stream with incremental row/column updates; the streamer preserves the original unchecked inclusive 31x21 guard behavior using generated already-translated values for cell `-1` and cells `N..N+width` rather than zeroing those ROM-adjacent reads; this is covered by `data/bg_state_parity.csv` and `tools/test_bg_state_parity.py`, including the screenblock-as-tile alias consequence; active gameplay keeps tracking and publication as separate phases so the frame starts with camera publish/stream + object draw and only then runs object updates, with Player tracking becoming visible on the next frame; the global phase proof is in `data/gameplay_frame_order.csv`; `data/story_overlay_update_order.csv` proves overlay insertion before the physical list, `data/player_portal_update_order.csv` splits generic portals into 6 pre-Player / 27 post-Player controllers, and `data/player_fgtile_update_order.csv` records the special post-Player Fgtile ordinals; the independent `tools/audit_visible_bg_frames.py` compositor now verifies the resulting 240x160 four-BG image at 121 deterministic checkpoints, including screenblock-as-tile aliases and final BGR555 palette resolution, with zero canonical-ROM vs checked-in-asset pixel mismatches; adversarial tile/palette mutations prove the audit fails on real visual drift;
- independent visible OBJ/OAM parity auditing through `tools/audit_visible_oam_frames.py` / `data/visible_oam_frame_parity.csv`: **88 deterministic sprite checkpoints** cover all recovered Player/NPC visual source families plus Grass, Leaves, riding/parked bicycles and the fifth-sketch monster, with 8bpp tiled decode, clipping/wrap, H-flip, transparency, priority/OAM-index ties and source-palette BGR555 comparison; all 88 currently match the canonical-ROM model, and adversarial sprite/palette mutations are required to fail; this pass also fixes the old Level-9/10 monster overlap by honoring the original monster-first `Player_draw` branch, which suppresses the parked bicycle while the monster composite is active; gameplay time-of-day OBJ lighting remains verified by its separate ROM-backed runtime suite;
- 33 generic scene-transition edges loadable on fresh A; the four Level-10 turn-4/5 records are handled separately by the rusty-key story gate, while the Level-9 treetype-20 record preserves `portTo=524` only as metadata and executes its recovered fresh-A **bicycle mount** over Player anchor bounds x=504..519/y=464..479, queues the Y=512 fixed8 target, and stores shared ride mode `0x030005F4=2` instead of requesting scene 524; these special Fgtile controllers are evaluated **after Player update** because their canonical physical ordinals are post-Player (Level 9 Player index 2 -> treetype-20 index 11; Level 10 Player index 1 -> turn4/5 indices 13..16), so they observe same-frame Player movement and any queued vertical target resolves on the next Player update; Step 17 proves all 92 physical-NPC level references are post-Player and runs canonical physical-NPC motion/proximity after Player; Step 18 proves story overlays are loaded before the physical list and splits generic portal activation around Player according to the six pre-Player / 27 post-Player ROM ordinals; production now additionally preserves the exact post-Player serialized interleaving instead of bucket-updating all NPCs before all portals, with generated portal `physical_index` metadata driving per-record dispatch;
- shared Player state `0x030005F4` has dormant original-ROM value-1 draw/update consumers, but public-demo writer closure proves normal boot reaches only values 0 and 2: startup seeds 0, treetype-20 writes 2, scene entry preserves exactly 2 and clears every other value, and the Level-10 mode-5->6 handoff clears it; therefore the clean-room runtime intentionally does not invent a mode-1 entry path;
- standalone fresh SELECT is code-proven to decrement private `Player+0x1BC` from constructor value 11 down to the guard floor 3 (eight accepted presses), then internally transfer back to the common Player-update continuation; it does not fall through into the neighboring state-12/vector block, and no separate consumer of that counter is proven, so the clean-room runtime intentionally leaves standalone SELECT inert;
- generated canonical story content: 7 dialogue scripts / 58 records, six message records, Stas/Julia social tables, the original CFA proportional font, and five monster sprites;
- ROM-proven object ordering around Player: the selected 16-record story-overlay list is loaded before the physical level list, all **92** canonical physical-NPC references are post-Player, and the **33** generic portals split into **6 pre-Player / 27 post-Player** controllers; production draw now follows that same insertion order through the shared monotonic OAM allocator, using generated Player physical indices `[8,2,0,0,0,0,8,0,4,2,1]`, while update dispatch now also walks physical ordinals one-by-one so interleaved NPC/Fgtile records retain their original relative timing; generated portal records carry their canonical `physical_index`; guarded by `data/story_overlay_update_order.csv`, `data/player_npc_update_order.csv`, `data/player_portal_update_order.csv`, and `data/gameplay_oam_insertion_order.csv`;
- active ordinary Fgtile control behavior is restored: parser-default `portTo=33` + turn 0/1 records retain `treetype`, reproduce the recovered vertical/horizontal strip scan and 16px hysteresis latch, and apply the exact 18-entry descriptor-relative graphics patch table to BG VRAM; the three canonical turn-2/treetype-1 records are music-zone controllers whose 2x40 contact strip toggles Player's desired selector `0↔1`, with physical indices Level 0 #3 / Level 6 #3 before Player #8 and Level 2 #4 / Level 5 #4 after Player #0; the separate full-graphics branch is left dormant because it requires `turn==3` and no canonical public-demo Fgtile serializes that value;
- Leaves update at physical slot 0 before Player on Levels 0/6/9/10; their constructor registers newborn `LeafParticle` objects on the manager live update vector and the manager reloads vector end after every object, so fresh particles take their first `(-150,+150)` fixed8 step in the same traversal. Modal B+SELECT/START checks are kept at the Player slot after overlays/pre-Player objects rather than short-circuiting those controllers early;
- ROM-proven NPC pre-UI alignment: state-1 social interactions collision-resolve to NPC Y with the exact ±19-pixel side offset, while state-2 dialogue interactions with `legsColor != 1` use the vertical-target helper before dialogue UI opens;
- a persistent clean-room story runtime that consumes state 1/2/4 interaction events, executes the six-step collection/key progression, persists consumed story pickups across level reloads, renders dialogue/social UI on BG0, keeps social D-pad selection separate from fresh-A confirmation, preserves zero-count leaf entry into state 2 plus the SFX7 fresh-B root return, reproduces the exact recovered shared SUBJECT/CRITICIZE response RNG and pre-dispatch score-mirror ordering, reproduces the `0x0300062C` dialogue-page latch (first text page SFX3, later text page SFX8, control-record SFX7/13 routing, silent state-4 selector `-1`), preserves multiple same-frame one-shots through an eight-entry FIFO, and reproduces the exact reachable argument-0 final VRAM blast (96,000 + 16,000 bytes), including the state-4 `-5` same-update first blast and later latched Player-slot replays that rejoin normal Player/object traversal, while refusing unproved/out-of-range larger arguments. The normal-context opcode `-5` OBJ-bank loader at `0x08005720` is intentionally not exposed: the sole `-5` record is script 6 / step 4, canonical state-2 actors select only scripts 0–3, and state-4 progress 4 intercepts that record through the dedicated final-sketch handler.
- the original 14-entry signed 8-bit PCM bank, played by an eight-channel 16,384 Hz FIFO-A/DMA1 mixer; gameplay entry seeds desired/applied selector 0 on Levels 0–9 and selector 1 on Level 10, canonical turn-2 Fgtile zones can toggle desired selector 0↔1, music ID 2 is code-proven unreachable/orphaned in the public demo, and the recovered loop lifecycle uses mode 2, volume `0x90`, a reserved channel, and the exact 75-update fade/replacement path (including retained partial fade count when desired temporarily returns to applied). High-confidence SFX routing now distinguishes first dialogue text pages (3), subsequent dialogue text pages (8), normal/state4 control records (7/13), actual secondary social-topic cursor movement (4), generic scene portals (5), and the title START transition (6).

Validate the built cartridge header before launching it:

```sh
python3 tools/validate_gba_rom.py reconstruction/Graveblood_RE.gba
```

Then open `reconstruction/Graveblood_RE.gba` in **mGBA** or another accurate emulator. A bounded boot smoke is available when mGBA is installed:

```sh
python3 tools/run_mgba_smoke.py reconstruction/Graveblood_RE.gba --seconds 5
```

On a headless Linux host, run that command under Xvfb (and use dummy SDL audio), matching CI:

```sh
xvfb-run -a env SDL_AUDIODRIVER=dummy \
  python3 tools/run_mgba_smoke.py reconstruction/Graveblood_RE.gba --seconds 5
```

The smoke gate treats an emulator that exits before the window as a failure; reaching the timeout means the Title loop remained alive. For deeper machine-readable emulator validation, build the compile-time self-test cartridge separately:

```sh
make -C reconstruction \
  TARGET=Graveblood_RE_selftest \
  BUILD=build-selftest \
  EXTRA_CFLAGS=-DGB_EMULATOR_SELFTEST \
  -j"$(nproc)"
python3 tools/validate_gba_rom.py reconstruction/Graveblood_RE_selftest.gba
```

With mGBA installed, the GDB-backed runner boots that cartridge, lets the ARM7TDMI execute, interrupts it through mGBA's remote debugger, and reads a fixed 96-byte report from EWRAM:

```sh
xvfb-run -a env SDL_AUDIODRIVER=dummy \
  python3 tools/run_mgba_selftest.py reconstruction/Graveblood_RE_selftest.gba \
    --seconds 2 --ppu-screenshot dist/mgba-selftest-ppu.png
```

The self-test ROM uses production Graveblood code to check seven emulator-side contracts: equal-priority Player/physical-post-Player-NPC OAM ordering and priority bits, two-phase VBlank timing, the Level-9 boundary plus delayed Level-10 scene handoff, the complete Level-10 scripted entrance on the real collision map, far-right Level-9 leaf emission, the ending-effect VRAM payload/bounds, and Timer1 audio cadence. The ending check deliberately validates the real GBA VRAM bus result rather than ordinary-RAM byte semantics: the original unaligned first copy uses byte stores, which mirror the odd source byte across each BG-VRAM halfword below `0x06010000` but are ignored once the destination enters OBJ VRAM. The aligned second copy starts at `0x06010000` and remains byte-exact through legal wide stores. The self-test seeds its OBJ-VRAM guards with 16-bit stores so the guards themselves are hardware-valid. The audio check counts interrupts across 60 real VBlanks and requires 63–66 Timer1 IRQs, matching the recovered 64 Hz count-up timer. Its DMA setup probe accepts both the literal `0xB200` write and mGBA's effective FIFO-DMA `0xB640` readback; mGBA normalizes FIFO DMA to destination-fixed, 32-bit transfers, so rejecting that effective value would be a false failure.

When `--ppu-screenshot` is supplied, the cartridge then leaves a controlled production-renderer overlap fixture on screen. The runner resumes mGBA, requests mGBA's own native F12 screenshot through `xdotool`, parses the resulting 240×160 core PNG, and checks two composited pixels: the equal-priority Player must win over the deliberately post-Player physical NPC at the lower Player OAM index in that fixture, while the adjacent transparent Player pixel must reveal the NPC below. This is an eighth external PPU assertion layered on top of the seven EWRAM report bits. The normal release cartridge does not enter this path because it is compiled only when `GB_EMULATOR_SELFTEST` is defined. A flash cartridge is still recommended for analog speaker quality and device-specific timing that even an accurate emulator cannot prove.

For real-hardware/flash-cart validation, build the separate device-test cartridge:

```bash
make -C reconstruction \
  TARGET=Graveblood_RE_device_test \
  BUILD=build-device-test \
  EXTRA_CFLAGS=-DGB_DEVICE_SELFTEST \
  -j"$(nproc)"
python3 tools/validate_gba_rom.py reconstruction/Graveblood_RE_device_test.gba
```

`Graveblood_RE_device_test.gba` runs the same seven production checks without needing GDB, then switches to a simple Mode-3 status screen designed to be unambiguous on a physical GBA. The top band is green only when all seven checks passed, otherwise red. The seven bars below it are, from top to bottom: **OAM ordering/priority**, **VBlank timing**, **Level-9→10 boundary/scene handoff**, **Level-10 scripted entrance**, **far-right Level-9 Leaves**, **ending-effect VRAM payload/bounds**, and **Timer1 audio cadence**. Each bar is green for pass and red for fail. After drawing the screen, the device cartridge restarts the production Direct Sound path and plays recovered **SFX6** once; hearing it provides the final human-observable check of the DAC/speaker path that mGBA cannot prove. The device-test ROM then remains on the status screen until reset/power-off. It is a validation artifact only and is never substituted for the normal release ROM.

## 4. Source layout

```text
reconstruction/
├── Makefile
├── include/graveblood/
├── source/
│   ├── main.c
│   ├── engine/
│   └── game/
├── data/          # checked-in generated C assets
└── maps/          # Tiled-compatible Level 7/8 inspection maps + generated tilesheets
```

The runtime stays intentionally small and CFA-like. Add behavior to the smallest owning module instead of building a general-purpose engine first.

## 5. Regenerate all-level reconstruction assets

Normal builds do not require this step.

Asset regeneration uses the checked-in RE metadata/renders and the canonical demo ROM for the exact BG graphics, palettes, streamed source layers, translation tables, fixed/parallax sources, collision grids, physical portal records, recovered Player animation frames, canonical actor descriptors/references, story overlays, NPC routes, exact NPC/story frame-1 graphics, dialogue/message/social tables, canonical font glyphs, and monster sprites across all 11 levels / 13 graphics variants:

```sh
python3 tools/generate_cfa_assets.py \
  --rom "/path/to/Graveblood 0.0.1.1.5.2 demo.gba" \
  --out reconstruction
```

The generated C assets contain the original `0xD800` BG graphics blobs, 256-entry BGR555 palettes, raw layer-A/layer-B source IDs, translation-table prefixes, fixed map sources, collision arrays, portal records, actor descriptor/index tables, story overlays, five six-waypoint routes, and exact deduplicated NPC/story frame-1 OBJ data. The generator recreates:

- `reconstruction/data/level00_assets.c` through `level10_assets.c` (variant 0);
- `reconstruction/data/level00_v1_assets.c` and `level00_v2_assets.c`;
- `reconstruction/data/level_registry.c`;
- `reconstruction/data/player_sprite.c`;
- `reconstruction/data/actor_data.c`, `actor_routes.c`, and `actor_sprite_data.c`;
- `reconstruction/include/graveblood/assets.h`;
- the existing Level 7/8 Tiled inspection maps and generated tilesheets.

Large worlds such as Level 9 (`782x128` tiles) are **not** flattened into editor tilesheets; the GBA runtime consumes their streamed source arrays directly.

The generated results are deterministic and covered by `tools/test_cfa_assets.py`.

Canonical Title assets/evidence are regenerated separately from the streamed world assets:

```bash
python3 tools/extract_title_scene.py \
  "$GRAVEBLOOD_ROM"
```

This regenerates `reconstruction/data/title_assets.c`, `data/title_scene_semantics.csv`, and the focused Title disassembly evidence.

Canonical audio extraction is a separate ROM-backed step because the PCM files are linked directly rather than emitted as C arrays:

```sh
python3 tools/extract_audio.py \
  "/path/to/Graveblood 0.0.1.1.5.2 demo.gba" \
  --repo-root .
```

This writes `reconstruction/data/audio/sample_00.pcm` through `sample_13.pcm`, `audio_samples.s`, `audio_data.c`, and the audio evidence CSV/disassembly exports. Once checked in, ordinary `make -C reconstruction` builds do not need the reference ROM.

## 6. Reverse-engineering tests

With the canonical demo ROM available:

```sh
export GRAVEBLOOD_ROM="/path/to/Graveblood 0.0.1.1.5.2 demo.gba"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py' -v
```

RE tests and the reconstruction build remain separate: tests prove recovered behavior/data; `reconstruction/` implements it.

### Hardware-address / ARM validation gate

A ROM-independent hardware-facing gate is also checked in:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tools.test_hardware_address_runtime -v
```

On Linux, its host harnesses map the literal GBA regions used by production code (`0x04000000` MMIO, `0x05000000` palette RAM, `0x06000000` VRAM, and `0x07000000` OAM) into isolated test processes. The tests execute the real `input.c`, `audio.c`, `video.c`, `actors.c`, and ending-effect code against those addresses and verify active-low input, FIFO-A/DMA1/timer programming, Mode-0/OAM/OBJ uploads, Player/NPC/Grass/leaf submissions, the two-phase VBlank wait, and the argument-0 VRAM boundary/result model. `ending.c` now expresses the GBA byte-store result explicitly, so the host harness can verify the BG-VRAM replication and OBJ-VRAM no-op portions deterministically; mGBA/real hardware remain the authority for the complete bus/PPU/audio behavior.

The same gate cross-compiles every checked-in reconstruction C unit plus both `.incbin` assembly units for **ARM7TDMI Thumb** and performs a relocatable ARM link. It uses `clang --target=arm-none-eabi` when available, otherwise `arm-none-eabi-gcc`. This is deliberately **not** presented as a substitute for the final devkitARM/libgba ROM link or an emulator/device run: mGBA/flash-cart validation remains the authority for actual PPU/audio/timing behavior.

## 7. GitHub Actions

`.github/workflows/build-release-rom.yml` validates ordinary development pushes and keeps the resulting game ROM available. A normal branch push or pull request runs the ROM-independent CI regression gate, builds the normal game cartridge with the pinned devkitARM image, validates the resulting ROM header, and uploads that validated `Graveblood_RE.gba` as the `Graveblood_RE-rom` Actions artifact for 7 days. Branch/PR CI remains read-only and cannot write GitHub Releases. The deeper ROM-backed parity suites still require the canonical reference demo via `GRAVEBLOOD_ROM` and therefore remain a local/reference-ROM gate rather than a clean-runner dependency.

Development-release tags matching:

```text
Graveblood_RE_v*-dev
```

use that same build job, then a second publish job downloads the exact validated `Graveblood_RE-rom` artifact and publishes that cartridge to the GitHub Release. The release job does not rebuild the game, so the released bytes are the bytes that passed validation. The workflow uses the pinned builder:

```text
devkitpro/devkitarm:20260610
```

The common verification commands are:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tools.test_reconstruction_build \
  tools.test_gba_rom_validation \
  tools.test_device_selftest \
  tools.test_hardware_address_runtime \
  tools.test_mgba_selftest \
  tools.test_mgba_smoke -v
make -C reconstruction -j"$(nproc)"
python3 tools/validate_gba_rom.py reconstruction/Graveblood_RE.gba
```

The only Actions artifact is the normal validated game ROM (`Graveblood_RE-rom`); no checksum artifact, self-test cartridge, device-test cartridge, mGBA screenshot, or other diagnostic artifact is uploaded. GitHub Releases still contain exactly one asset: the versioned normal `.gba`. The diagnostic self-test/device-test build paths remain in the repository for manual/local validation. Only the tag publish job receives `contents: write`; branch/PR build/validation stays read-only.

## 8. Development release tags

Use tags such as:

```sh
git tag Graveblood_RE_v0.0.1-dev
git push origin Graveblood_RE_v0.0.1-dev
```

The release workflow publishes exactly one release asset:

```text
Graveblood_RE_v0.0.1.gba
```

and marks the GitHub release as a prerelease. Re-running the same tag replaces that ROM with `--clobber`.

## 9. Reconstruction rule

When CFA-era conventions, current libgba conventions, and our guesses disagree, the priority is:

1. verified behavior/data from the canonical Graveblood demo;
2. confirmed CFA/Contra Force Advance architecture where available;
3. current devkitPro/libgba hardware behavior;
4. new design choices only when the original behavior is genuinely absent or intentionally being extended.

Canonical Wardrobe preview assets are also regenerated separately because the browser uses seven selector-specific Level-7 BG pages and dynamic OBJ source-bank slices:

```sh
python3 tools/extract_wardrobe_runtime.py \
  "/path/to/Graveblood 0.0.1.1.5.2 demo.gba" \
  --root .
```

This writes `reconstruction/data/wardrobe_assets.c` and `data/wardrobe_runtime_assets.csv`. Ordinary ROM builds use the checked-in C data and do not need the reference ROM. The reconstructed browser is browse/preview-only: exact B+SELECT entry, selectors 0..6, fresh-B Level-7 exit, no A-confirm/equip action, and no guessed SFX11 route.


## Interactive runtime parity regression gate

When changing gameplay interaction or presentation, include `tools/test_interactive_runtime_parity.py` in the focused gate.  It checks four regressions that were visible in playable-ROM comparison but were previously underrepresented by static asset audits:

1. START closes an already-open PDA through the gameplay-return path.
2. Normal dialogue uses the recovered 20x6 window / 18x4 interior and original border tile IDs 3/4/5.
3. Gameplay lighting preserves OBJ pair 4/5 and pairs above 199 instead of overwriting them.
4. A serialized physical state-2 NPC emits its dialogue event on fresh A while held-A alone does not retrigger it.

Use the exact reference ROM through `GRAVEBLOOD_ROM` for ROM-backed suites.  The visual BG/OAM audits remain useful, but passing them does not substitute for interaction tests or playable-ROM comparison.
