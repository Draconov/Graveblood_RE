# Developing, Building, and Releasing Graveblood_RE

This guide covers the **clean-room reconstruction** under `reconstruction/`.
The original `Graveblood 0.0.1.1.5.2 demo.gba` is useful for the separate
reverse-engineering tools, but it is **not required and must not be linked or
copied into the reconstruction build**.

## 1. Toolchain

The reconstruction uses **Butano + devkitARM**.

Pinned versions used by this workspace:

- Butano commit: `77dcbcb3d8783596a9f333c64eedbccec77b05dc`
- GitHub Actions devkitARM image: `devkitpro/devkitarm:20260610`

Butano's official getting-started guide is:

`https://gvaliente.github.io/butano/getting_started.html`

Install the devkitPro **GBA Development** component. If the installer asks
which packages from `gba-dev` to install, install all of them. Also install
Git and Python and keep a GBA emulator such as **mGBA** available for testing.

Typical devkitPro locations are:

- Windows: `C:\devkitPro`
- macOS/Linux: `/opt/devkitpro`

Butano recommends building from the normal system terminal rather than the
MSYS2 terminal on Windows.

## 2. Get the pinned Butano dependency

From the root of this workspace/repository:

```sh
mkdir -p vendor
git clone https://github.com/GValiente/butano.git vendor/butano
git -C vendor/butano checkout 77dcbcb3d8783596a9f333c64eedbccec77b05dc
```

You can verify the pin with:

```sh
git -C vendor/butano rev-parse HEAD
```

It must print:

```text
77dcbcb3d8783596a9f333c64eedbccec77b05dc
```

`vendor/` is ignored by Git so the third-party engine is not accidentally
committed into this project.

## 3. Build the ROM

From the workspace root:

```sh
make -C reconstruction LIBBUTANO=../vendor/butano/butano -j4
```

Use a larger `-j` value if your CPU has more cores.

Expected output:

```text
reconstruction/Graveblood_RE.gba
```

The current development shell should display a dark green screen. Press **A**
to toggle the backdrop color. That tiny interaction is intentional: it proves
that initialization, rendering, keypad input, VBlank/update timing, linking,
and ROM generation are all alive before real reconstructed gameplay is added.

## 4. Clean and rebuild

After changing the Makefile, changing Butano versions, or when linker errors
look suspicious, do a clean build:

```sh
make -C reconstruction LIBBUTANO=../vendor/butano/butano clean
make -C reconstruction LIBBUTANO=../vendor/butano/butano -j4
```

The one-line clean command is:

```sh
make -C reconstruction LIBBUTANO=../vendor/butano/butano clean
```

## 5. Windows notes

1. Install devkitPro and select **GBA Development**.
2. Install Python and make sure `python` works from the system console.
3. Open PowerShell, Command Prompt, or another normal system terminal.
4. In PowerShell, clone the pinned Butano revision with Windows-native commands:

```powershell
New-Item -ItemType Directory -Force vendor | Out-Null
git clone https://github.com/GValiente/butano.git vendor/butano
git -C vendor/butano checkout 77dcbcb3d8783596a9f333c64eedbccec77b05dc
```

5. Build with:

```powershell
make -C reconstruction LIBBUTANO=../vendor/butano/butano -j4
```

If environment variables are not already configured by the installer, set:

```powershell
$env:DEVKITPRO = 'C:\devkitPro'
$env:DEVKITARM = 'C:\devkitPro\devkitARM'
```

## 6. macOS/Linux notes

After devkitPro installation, these are the usual environment values:

```sh
export DEVKITPRO=/opt/devkitpro
export DEVKITARM=/opt/devkitpro/devkitARM
```

If your distribution only provides `python3`, either make `python` resolve to
Python 3 or override Butano's Python variable when needed.

## 7. Test in an emulator

Open:

```text
reconstruction/Graveblood_RE.gba
```

in **mGBA**, NanoBoyAdvance, Mesen, No$gba, or another accurate GBA emulator.
For development, mGBA is a particularly convenient default because its debug
build/logging tools are useful when the reconstruction grows.

For source-level debugging with No$gba, keep the generated `.elf` locally as
well; do not commit generated binaries.

## 8. Test on real hardware

After emulator testing, copy the generated `.gba` to a compatible GBA flash
cartridge or other legal development hardware and test on real GBA/GBA SP/
Game Boy Player hardware. Keep emulator and hardware tests in the loop once
we start reproducing timing-sensitive rendering such as the world streamer,
dynamic OBJ staging, and the final-sketch effect.

## 9. Reverse-engineering tests vs. reconstruction build

These are intentionally separate workflows:

- `tools/test_*.py` verifies what we have recovered from the canonical demo ROM.
- `reconstruction/` builds new clean-room source code.

The reconstruction should consume **documented structures and reimplemented
assets/code**, not the original ROM file itself.

## 10. GitHub Actions build artifacts

The workflow at:

```text
.github/workflows/build-release-rom.yml
```

runs on pushes, pull requests, and manual dispatches. It checks out the pinned
Butano commit, builds the reconstruction in the official devkitPro container,
then uploads an artifact named:

```text
Graveblood_RE-rom
```

containing:

```text
Graveblood_RE.gba
Graveblood_RE.gba.sha256
```

This means contributors do not need to publish a release just to download a
CI-built test ROM.

## 11. Create a GitHub release ROM

The workflow publishes development releases only for tags matching `Graveblood_RE_vMAJOR.MINOR.PATCH-dev`.

Example:

```sh
git tag Graveblood_RE_v0.0.1-dev
git push origin Graveblood_RE_v0.0.1-dev
```

The build job runs first. If it succeeds, the release job uses the tag itself as
the GitHub Release title and strips the `-dev` suffix from the ROM asset name.
For `Graveblood_RE_v0.0.1-dev`, it uploads:

```text
Graveblood_RE_v0.0.1.gba
Graveblood_RE_v0.0.1.gba.sha256
```

If the same tag/release is rerun, the workflow uses `--clobber` so the assets
are replaced by the newly verified build.

Until the reconstructed game reaches an intentional public milestone, use
clear development tags such as `Graveblood_RE_v0.0.1-dev`. The workflow marks these releases as GitHub prereleases.

## 12. Where to add reconstructed game code

Keep new code under `reconstruction/src/` and split it by recovered subsystem
as it grows, for example:

```text
reconstruction/src/
├── main.cpp
├── world/
├── actors/
├── story/
├── graphics/
└── save/
```

The RE workspace already documents likely subsystem boundaries in
`BUTANO_REBUILD_NOTES.md`. Implement parity in small, testable slices: world
streaming first, then actor factories, player/NPC rendering, dialogue/state,
and only then new or speculative completion content.
