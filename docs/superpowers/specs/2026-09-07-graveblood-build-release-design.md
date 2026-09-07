# Graveblood Reconstruction Build & Release Design

## Goal

Add a real, buildable clean-room Game Boy Advance reconstruction skeleton to the existing Graveblood reverse-engineering workspace, document how to develop and build it locally, and provide GitHub Actions automation that builds the ROM on pushes/pull requests and publishes the ROM on version tags.

## Scope

This design does **not** claim the game reconstruction is complete. The first buildable ROM is a development shell that proves the toolchain, repository layout, CI path, and release path. Future RE-backed gameplay code will replace/extend this shell while keeping the same build contract.

The canonical reverse-engineering data remains separate from implementation code. Original ROM files are never bundled or required by the reconstruction build.

## Architecture

- `reconstruction/` is an independent Butano project based on the official Butano template layout.
- Butano is an external dependency pinned to commit `77dcbcb3d8783596a9f333c64eedbccec77b05dc` (2026-08-06) for reproducible development and CI.
- `reconstruction/Makefile` accepts an overridable `LIBBUTANO` path and builds `Graveblood_RE.gba`.
- The initial `main.cpp` boots Butano, paints a visible development-screen color, responds to a simple input toggle, and continuously updates. This intentionally proves the ROM runs without pretending to implement unrecovered gameplay.
- `DEVELOPING_AND_BUILDING.md` documents devkitARM, Butano checkout, local build, clean/rebuild, emulator testing, hardware testing, and tagged releases.
- `.github/workflows/build-release-rom.yml` builds in the official `devkitpro/devkitarm:20260610` container, checks out the pinned Butano commit, uploads ROM artifacts for normal CI, and uses a separate Ubuntu release job to attach `.gba` + SHA-256 files to `v*` GitHub releases.

## Build Contract

Local project root layout:

```text
workspace/
├── reconstruction/
├── vendor/
│   └── butano/      # clone of GValiente/butano, pinned commit
└── ... RE workspace files ...
```

Build command:

```sh
make -C reconstruction LIBBUTANO=../vendor/butano/butano -j4
```

Expected output:

```text
reconstruction/Graveblood_RE.gba
```

## CI / Release Contract

- `push`, `pull_request`, and `workflow_dispatch` all run the ROM build.
- CI uploads an artifact named `Graveblood_RE-rom` containing:
  - `Graveblood_RE.gba`
  - `Graveblood_RE.gba.sha256`
- A pushed tag matching `v*` also runs a release job.
- The release job creates the GitHub release if it does not already exist and uploads the two generated files.
- Workflow permissions are read-only by default; only the release job receives `contents: write`.

## Development Safety

- Do not include or derive build inputs from the original `.gba` files.
- Keep RE evidence and reconstruction code in separate directories.
- New gameplay features should be implemented from documented/recovered behavior, not by copying original binaries into the build.
- Clearly label the output as a reconstruction/development build until the project is intentionally renamed/released otherwise.

## Verification

The workspace test suite will gain static tests that verify:

- expected reconstruction files exist;
- Makefile points to Butano through an overridable `LIBBUTANO` variable;
- ROM title/code and output target are explicit;
- initial source calls `bn::core::init()` and `bn::core::update()`;
- workflow pins Butano to the approved commit;
- workflow pins devkitPro image `20260610`;
- workflow uploads build artifacts and gates release publication to `v*` tags;
- documentation contains exact local checkout/build/release commands.

Because devkitARM is not installed in the packaging environment, final local verification here is structural/static plus the existing ROM-RE tests. GitHub Actions is the intended authoritative compile environment for the Butano ROM build.
