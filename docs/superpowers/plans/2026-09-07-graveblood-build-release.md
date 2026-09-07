# Graveblood Reconstruction Build & Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a buildable Butano reconstruction shell, local build/development instructions, and GitHub Actions ROM build/release automation to the Graveblood RE workspace.

**Architecture:** Keep the reconstruction as an independent Butano project under `reconstruction/` and retain all reverse-engineering evidence outside it. Pin Butano and the devkitPro CI image, expose a stable `make` build contract, and separate build CI from tagged release publication.

**Tech Stack:** C++/Butano, GNU Make, devkitARM, GitHub Actions, Python `unittest` for workspace regression tests.

**Spec:** `docs/superpowers/specs/2026-09-07-graveblood-build-release-design.md`

## Global Constraints

- Canonical RE ROM remains `Graveblood 0.0.1.1.5.2 demo.gba`; it is not a reconstruction build dependency.
- Butano is pinned to commit `77dcbcb3d8783596a9f333c64eedbccec77b05dc`.
- CI devkitARM image is pinned to `devkitpro/devkitarm:20260610`.
- Reconstruction output is `reconstruction/Graveblood_RE.gba`.
- GitHub release publication happens only for `v*` tags.
- Existing reverse-engineering tests must continue to pass.
- This packaged workspace is not a Git checkout, so commit steps are represented by verified workspace checkpoints rather than git commits.

---

### Task 1: Guard the Reconstruction Build Contract

**Files:**
- Create: `tools/test_reconstruction_build.py`

**Interfaces:**
- Consumes: approved spec paths and constants.
- Produces: regression tests that define the required scaffold, documentation, and workflow behavior.

- [ ] **Step 1: Write failing scaffold tests**

Create tests asserting the future files exist and contain the pinned Butano commit, devkitPro image tag, output name, Butano initialization/update loop, build command, artifact upload, and `v*` release gate.

- [ ] **Step 2: Run only the new test file**

Run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tools/test_reconstruction_build.py -v
```

Expected: FAIL because reconstruction/docs/workflow files do not exist yet.

- [ ] **Step 3: Preserve the failing output as the TDD red checkpoint**

No source files are added before the test demonstrates the missing behavior.

---

### Task 2: Add the Minimal Butano Reconstruction Project

**Files:**
- Create: `reconstruction/Makefile`
- Create: `reconstruction/src/main.cpp`
- Create: `reconstruction/README.md`
- Create: `.gitignore`

**Interfaces:**
- Consumes: external Butano library directory through Make variable `LIBBUTANO`.
- Produces: `reconstruction/Graveblood_RE.gba` when built with devkitARM + pinned Butano.

- [ ] **Step 1: Implement the Makefile**

Use Butano template semantics with:

```make
TARGET := Graveblood_RE
LIBBUTANO ?= ../vendor/butano/butano
SOURCES := src
INCLUDES := include
GRAPHICS :=
AUDIO :=
AUDIOBACKEND := null
DMGAUDIO :=
DMGAUDIOBACKEND := null
ROMTITLE := GRAVEBLOOD
ROMCODE := GBR0
```

and include `$(LIBBUTANOABS)/butano.mak`.

- [ ] **Step 2: Implement a visible development ROM shell**

`main.cpp` initializes Butano, sets a dark backdrop color, toggles to a second backdrop color when A is pressed, and calls `bn::core::update()` every frame.

- [ ] **Step 3: Document the reconstruction subproject boundary**

`reconstruction/README.md` states that this is a clean-room development shell and does not include original ROM bytes.

- [ ] **Step 4: Ignore generated build products**

Add `reconstruction/build/`, `.elf`, `.gba`, `.map`, and intermediate Butano outputs to `.gitignore` without ignoring RE evidence.

- [ ] **Step 5: Run the scaffold test**

Expected: project-related assertions pass; docs/workflow assertions still fail.

---

### Task 3: Add Local Development and Build Instructions

**Files:**
- Create: `DEVELOPING_AND_BUILDING.md`
- Modify: `README.md`
- Modify: `BUTANO_REBUILD_NOTES.md`

**Interfaces:**
- Consumes: reconstruction build contract from Task 2.
- Produces: exact developer instructions for Windows, macOS, Linux, emulators, hardware, clean builds, and version tags.

- [ ] **Step 1: Document prerequisite installation**

Describe devkitARM `GBA Development`/`gba-dev`, Python, Git, Make, and an emulator such as mGBA; link to Butano's official getting-started guide.

- [ ] **Step 2: Document pinned Butano checkout**

Use exactly:

```sh
mkdir -p vendor
git clone https://github.com/GValiente/butano.git vendor/butano
git -C vendor/butano checkout 77dcbcb3d8783596a9f333c64eedbccec77b05dc
```

- [ ] **Step 3: Document build and clean commands**

Use exactly:

```sh
make -C reconstruction LIBBUTANO=../vendor/butano/butano -j4
make -C reconstruction LIBBUTANO=../vendor/butano/butano clean
```

- [ ] **Step 4: Document testing and release tagging**

Explain loading `.gba` in mGBA and pushing `v*` tags to trigger release publication.

- [ ] **Step 5: Cross-link the docs from workspace README and Butano notes**

Keep the distinction between reverse-engineering evidence and implementation explicit.

---

### Task 4: Add GitHub Actions Build and Tagged Release

**Files:**
- Create: `.github/workflows/build-release-rom.yml`

**Interfaces:**
- Consumes: `reconstruction/Makefile` and pinned Butano commit.
- Produces: CI artifact `Graveblood_RE-rom` and tagged GitHub release assets named `Graveblood_RE_vMAJOR.MINOR.PATCH.gba`.

- [ ] **Step 1: Add build job**

Use `ubuntu-latest` with container `devkitpro/devkitarm:20260610`, checkout the current repo and Butano commit into `vendor/butano`, build the ROM, generate `.sha256`, and upload both files via `actions/upload-artifact@v4`.

- [ ] **Step 2: Add release job**

On `refs/tags/Graveblood_RE_v*-dev`, use `actions/download-artifact@v4` on a normal `ubuntu-latest` runner, then use the preinstalled GitHub CLI with `GH_TOKEN` to create or update the release assets.

- [ ] **Step 3: Validate workflow syntax**

Parse YAML with Python/PyYAML and assert expected top-level jobs and pinned values.

- [ ] **Step 4: Run the scaffold regression**

Expected: all reconstruction build tests pass.

---

### Task 5: Full Workspace Verification and Repository Package

**Files:**
- Modify: `WORKSPACE_MANIFEST.txt`
- Package: `/mnt/data/Graveblood_0.0.1.1.5.2_RE_workspace_v5.zip`

**Interfaces:**
- Consumes: completed repository workspace.
- Produces: verified downloadable repository archive.

- [ ] **Step 1: Run the complete Python regression suite**

```sh
PYTHONDONTWRITEBYTECODE=1 GRAVEBLOOD_ROM='/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba' GRAVEBLOOD_ALPHA_ROM='/mnt/data/Graveblood Pre Pre Pre Alpha.gba' python3 -m unittest discover -s tools -p 'test_*.py' -v
```

Expected: all previous 39 tests plus the new reconstruction tests pass.

- [ ] **Step 2: Compile all Python tools without polluting workspace**

Use `PYTHONPYCACHEPREFIX` outside the workspace and run `py_compile` over `tools/*.py`.

- [ ] **Step 3: Validate workflow YAML and build references**

Ensure pinned commit/image and expected ROM path are internally consistent.

- [ ] **Step 4: Regenerate workspace manifest and scan contamination**

Confirm no original `.gba`, `.rom`, `.bin`, `.pyc`, or `__pycache__` files are present.

- [ ] **Step 5: Build ZIP and verify archive integrity**

Run `unzip -t` and re-verify manifest after extracting the archive.

- [ ] **Step 6: Record archive SHA-256**

Publish the hash with the download link.
