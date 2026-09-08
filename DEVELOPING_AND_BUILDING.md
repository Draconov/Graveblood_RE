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

- Mode 0 8bpp tile rendering;
- recovered Level 7 and Level 8 maps;
- recovered player spawn points;
- recovered u16 8-pixel collision grids (`0 = walkable`, nonzero = blocked);
- hardware OAM player sprite with the recovered 16-frame walk/idle animation set, retained horizontal facing, and right-facing H-flip;
- scrolling camera in Level 8;
- supported Level 7 <-> Level 8 recovered portals on fresh A.

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
└── maps/          # Tiled-compatible Level 7/8 maps + generated tilesheets
```

The runtime stays intentionally small and CFA-like. Add behavior to the smallest owning module instead of building a general-purpose engine first.

## 5. Regenerate Level 7/8 reconstruction assets

Normal builds do not require this step.

Asset regeneration uses the checked-in RE renders/actor metadata and the canonical demo ROM for collision grids plus the exact recovered Player animation source frames:

```sh
python3 tools/generate_cfa_assets.py \
  --rom "/path/to/Graveblood 0.0.1.1.5.2 demo.gba" \
  --out reconstruction
```

The generator recreates:

- `reconstruction/data/level07_assets.c`
- `reconstruction/data/level08_assets.c`
- `reconstruction/data/player_sprite.c`
- `reconstruction/include/graveblood/assets.h`
- `reconstruction/maps/level07.tmx`
- `reconstruction/maps/level08.tmx`
- `reconstruction/maps/generated/*.png`

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
