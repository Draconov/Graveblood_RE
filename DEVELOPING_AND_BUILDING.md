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

The current build is no longer a framebuffer/color smoke test. It boots directly into recovered Level 7 and provides:

- recovered four-background Mode 0 layout (BG0 UI, streamed BG1/BG2 world, quarter-speed BG3 parallax);
- exact original BG graphics/palettes plus raw streamed world layers and translation tables for all **11 levels / 13 graphics variants**;
- recovered player spawn points for every level;
- recovered u16 8-pixel collision grids (`0 = walkable`, nonzero = blocked);
- hardware OAM player sprite with the recovered 16-frame walk/idle animation set, retained horizontal facing, and right-facing H-flip;
- 32x32 ring-buffer world streaming with incremental row/column updates as the camera crosses tile boundaries;
- 33 generic scene-portal records loadable on fresh A; the four Level-10 turn-4/5 records are handled separately by the rusty-key story gate, and the special Level-9 target `524` is preserved but intentionally not treated as a level;
- generated canonical story content: 7 dialogue scripts / 58 records, six message records, Stas/Julia social tables, the original CFA proportional font, and five monster sprites;
- a persistent clean-room story runtime that consumes state 1/2/4 interaction events, executes the six-step collection/key progression, persists consumed story pickups across level reloads, renders dialogue/social UI on BG0, and holds safely at `final_effect_pending` instead of reproducing the unsafe final VRAM-copy effect.

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
