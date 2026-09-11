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
- recovered u16 8-pixel collision grids (`0 = walkable`, nonzero = blocked);
- hardware OAM player sprite with the recovered 16-frame walk/idle animation set, retained horizontal facing, and right-facing H-flip;
- 32x32 ring-buffer world streaming with incremental row/column updates as the camera crosses tile boundaries;
- 33 generic scene-transition edges loadable on fresh A; the four Level-10 turn-4/5 records are handled separately by the rusty-key story gate, while the Level-9 treetype-20 record preserves `portTo=524` only as metadata and executes its recovered fresh-A vertical-target action to Y=512 instead of requesting scene 524; these vertical-target actions queue fixed8 motion through the collision solver rather than teleporting;
- generated canonical story content: 7 dialogue scripts / 58 records, six message records, Stas/Julia social tables, the original CFA proportional font, and five monster sprites;
- ROM-proven NPC pre-UI alignment: state-1 social interactions collision-resolve to NPC Y with the exact ±19-pixel side offset, while state-2 dialogue interactions with `legsColor != 1` use the vertical-target helper before dialogue UI opens;
- a persistent clean-room story runtime that consumes state 1/2/4 interaction events, executes the six-step collection/key progression, persists consumed story pickups across level reloads, renders dialogue/social UI on BG0, keeps social D-pad selection separate from fresh-A confirmation, preserves zero-count leaf entry into state 2 plus the SFX7 fresh-B root return, reproduces the exact recovered shared SUBJECT/CRITICIZE response RNG and pre-dispatch score-mirror ordering, and reproduces the exact reachable argument-0 final VRAM blast (96,000 + 16,000 bytes) while refusing unproved/out-of-range larger arguments.
- the original 14-entry signed 8-bit PCM bank, played by an eight-channel 16,384 Hz FIFO-A/DMA1 mixer; normal Levels 0–9 use code-proven music ID 0, Level 10 uses music ID 1, music ID 2 is code-proven unreachable/orphaned in the public demo, and the recovered loop lifecycle uses mode 2, volume `0x90`, a reserved channel, and the exact 75-word fade table. High-confidence SFX routing covers accepted state-2/state-4 interactions (3), actual secondary social-topic cursor movement (4), generic scene portals (5), the title START transition (6), state4 terminal dialogue branches (7), and the final-sketch boundary (13).

Open `reconstruction/Graveblood_RE.gba` in **mGBA** or another accurate emulator. Real-hardware testing on a flash cartridge is recommended as the renderer grows.

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

## 7. GitHub Actions

`.github/workflows/build-release-rom.yml` builds in:

```text
devkitpro/devkitarm:20260610
```

CI checks out only this repository, runs:

```sh
make -C reconstruction -j"$(nproc)"
```

and uploads `Graveblood_RE.gba` plus its SHA-256 as the `Graveblood_RE-rom` artifact.

## 8. Development release tags

Use tags such as:

```sh
git tag Graveblood_RE_v0.0.1-dev
git push origin Graveblood_RE_v0.0.1-dev
```

The release workflow publishes:

```text
Graveblood_RE_v0.0.1.gba
Graveblood_RE_v0.0.1.gba.sha256
```

and marks the GitHub release as a prerelease. Re-running the same release replaces the assets with `--clobber`.

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

