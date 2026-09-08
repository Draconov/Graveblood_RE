# Graveblood_RE reconstruction

This directory is the permanent **CFA-style devkitPro/libgba** reconstruction runtime.
It deliberately follows the original game's historical toolchain/architecture lineage instead of wrapping the project in a modern high-level GBA engine.

## Current playable milestone

The ROM boots directly into reconstructed **Level 7**, but the runtime registry now contains exact checked-in streamed assets for **all 11 canonical levels and all 13 recovered graphics variants**.

Controls:

- **D-pad** — move the recovered 16x32 player sprite;
- the player uses the recovered 6-frame regular walk, 6-frame up/back walk, mirrored 8-phase idle, retained horizontal facing, and right-facing H-flip behavior;
- movement uses the recovered **8x8 u16 collision grid** (`0 = walkable`, nonzero = blocked);
- **A** while standing on a recovered physical `fgtile` portal — change to its normal destination level;
- all 37 normal physical portal destinations (levels 0..10) resolve through the runtime registry;
- the one Level-9 special/out-of-range destination `524` is preserved as a 16-bit target and remains inert until its non-level semantics are recovered.

All 11 levels use the recovered multi-layer world architecture rather than a flattened runtime background. BG1 and BG2 are 32x32 ring-buffer windows streamed from the original visual world layers, while BG3 uses the recovered fixed parallax map at quarter camera speed. Level 0 additionally exposes recovered graphics variants 1 and 2 through `gb_level_assets(0, variant)`; normal portal entry currently selects variant 0.


The same level-entry path now rebuilds a fixed-capacity actor pool from generated canonical descriptors. It loads **241 unique non-Player physical descriptors through 290 level references**, then appends the **16 story-overlay descriptors** that match the current level; the maximum current population is 65 actors. NPC/story actors use 32 deduplicated exact frame-1 8bpp visual combinations and a bounded 56-slot OAM range after the Player. State-3 route followers keep 21.11 fixed-point positions and move by the constructor-proven `0x100` fixed units (1/8 pixel) per update toward the five recovered six-waypoint routes. Fresh-A state 1/2/4 contacts emit typed `social`, `dialogue`, or `collection` events, but this milestone deliberately does not execute dialogue, social menus, collection progression, or story scripting. State-1's original interaction-active global gate therefore belongs to the next downstream interaction-state phase. Grass/leaves/foreground descriptors are populated and ordered but remain non-rendering until their visual behavior is proved; physical portals continue to be handled only by `portal.c`.

## Runtime architecture

- devkitARM `gba_rules` build;
- libgba hardware definitions;
- Mode 0 with four 8bpp text backgrounds sharing character base 0;
- **BG0 / screenblock 27 / priority 0** — reserved fixed UI/text plane;
- **BG1 / screenblock 28 / priority 1** — streamed world layer A;
- **BG2 / screenblock 29 / priority 2** — streamed world layer B;
- **BG3 / screenblock 30 / priority 3** — quarter-speed parallax;
- exact original `0xD800`-byte BG graphics blobs, BGR555 palettes, source layers, translation tables, and fixed-map sources checked into generated C assets for all 13 variants;
- initial 32x32 stream fill followed by row/column updates when the camera crosses tile boundaries;
- 8x8 world cells;
- hardware OAM Player plus bounded NPC/story actor sprites;
- 16 losslessly packed recovered Player animation frames in OBJ palette bank 15, coexisting with the exact 8bpp actor palette/frames;
- generated actor descriptors, per-level reference spans, story overlays, route tables, and exact NPC/story frame-1 assets;
- pixel-space player/camera coordinates;
- small C modules under `source/engine` and `source/game`;
- generated C assets under `data/`;
- Tiled-compatible flattened inspection copies under `maps/`.

The normal build does **not** require an original Graveblood ROM or Python. Asset regeneration does require the canonical demo ROM because the runtime assets preserve the original BG graphics, palettes, streamed source layers, translation data, fixed/parallax sources, collision grids, physical portals, and exact Player animation frames for all canonical levels/variants. Generated assets are checked into the repository.

See [`../DEVELOPING_AND_BUILDING.md`](../DEVELOPING_AND_BUILDING.md).
