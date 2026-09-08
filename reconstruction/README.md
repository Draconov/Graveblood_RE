# Graveblood_RE reconstruction

This directory is the permanent **CFA-style devkitPro/libgba** reconstruction runtime.
It deliberately follows the original game's historical toolchain/architecture lineage instead of wrapping the project in a modern high-level GBA engine.

## Current playable slice

The ROM boots directly into reconstructed **Level 7** using checked-in assets generated from the verified RE workspace.

Controls:

- **D-pad** — move the recovered 16x32 player sprite;
- the player now uses the recovered 6-frame regular walk, 6-frame up/back walk, mirrored 8-phase idle, retained horizontal facing, and right-facing H-flip behavior;
- movement uses the recovered **8x8 u16 collision grid** (`0 = walkable`, nonzero = blocked);
- **A** while standing on a supported recovered `fgtile` portal — change level;
- the Level 7 -> Level 8 and Level 8 -> Level 7 routes are implemented;
- portals whose destination level has not yet been reconstructed remain inert.

Level 8 uses a scrolling 64x64 Mode 0 text background, so this milestone also proves the CFA-style camera/world path rather than a framebuffer test screen.

## Runtime architecture

- devkitARM `gba_rules` build;
- libgba hardware definitions;
- Mode 0 / 8bpp text background;
- 8x8 world cells;
- hardware OAM player sprite;
- 16 losslessly packed recovered player animation frames in one 4bpp OBJ palette;
- pixel-space player/camera coordinates;
- small C modules under `source/engine` and `source/game`;
- generated C assets under `data/`;
- Tiled-compatible `.tmx` copies under `maps/`.

The normal build does **not** require an original Graveblood ROM or Python. Asset regeneration does require the canonical demo ROM for the collision grids and exact Player animation source frames; generated assets are checked into the repository.

See [`../DEVELOPING_AND_BUILDING.md`](../DEVELOPING_AND_BUILDING.md).
