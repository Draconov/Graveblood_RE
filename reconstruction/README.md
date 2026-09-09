# Graveblood_RE reconstruction

This directory is the permanent **CFA-style devkitPro/libgba** reconstruction runtime.
It deliberately follows the original game's historical toolchain/architecture lineage instead of wrapping the project in a modern high-level GBA engine.

## Current playable milestone

The ROM now boots into the recovered **Title scene**. Its exact four-layer Mode-0 presentation is reconstructed: BG0 text overlay, BG1 30x20 artwork, BG2/BG3 64x32 backing, exact partial BG/OBJ palettes and OBJ tile bank, canonical hidden OAM, four-state tile animation, frame-counter prompt blink, fresh-START gate, **SFX 6**, and 120-update delayed transition before entering Level 7. There is deliberately no title music because the exhaustive public-demo loop-player scan contains no Title call. After START, the runtime registry contains exact checked-in streamed assets for **all 11 canonical levels and all 13 recovered graphics variants**.

Controls:

- **D-pad** — move the recovered 16x32 player sprite;
- the player uses the recovered 6-frame regular walk, 6-frame up/back walk, mirrored 8-phase idle, retained horizontal facing, and right-facing H-flip behavior;
- movement uses the recovered **8x8 u16 collision grid** (`0 = walkable`, nonzero = blocked);
- **A** near a state-1/2/4 NPC/story actor — enter the recovered social, dialogue, or collection path;
- **A** on a normal recovered `fgtile` portal — change to its destination level through the generic portal path;
- after the fourth collection advances progress `3 -> 4`, **A** on the Level-10 `turn=4/5` gate uses the recovered forced vertical traversal (Y=360 or Y=410) rather than `portTo=8`;
- while normal gameplay/story UI is idle, hold exactly **B+SELECT** to enter the recovered Wardrobe browser; fresh Left/Right browse selectors 0..6 and fresh B exits to Level 7; there is no equip/A-confirm action;
- 33 generic scene-portal records resolve through the runtime registry; the four Level-10 gate records remain special, and the one Level-9 destination `524` remains inert until its non-level semantics are recovered.

All 11 levels use the recovered multi-layer world architecture rather than a flattened runtime background. BG1 and BG2 are 32x32 ring-buffer windows streamed from the original visual world layers, while BG3 uses the recovered fixed parallax map at quarter camera speed. Level 0 additionally exposes recovered graphics variants 1 and 2 through `gb_level_assets(0, variant)`; normal portal entry currently selects variant 0.


The runtime also reconstructs the public-demo **Wardrobe browse/preview-only** path: exact held B+SELECT entry, selector 0 reset, seven ROM-derived Level-7 preview background pages and 16x32 8bpp outfit figures, fresh Left/Right bounds `0..6`, and fresh-B Level-7 exit. The browser never mutates the live gameplay graphics bank and does not invent an A-confirm/equip action. SFX11 is not wired because the known SFX11 calls are outside the recovered selector navigation branches.

The runtime now also embeds the canonical custom-PCM sound bank: all **14 pointer/length table entries** are checked in byte-for-byte as signed 8-bit mono PCM and linked through `data/audio_samples.s`. `source/engine/audio.c` implements the recovered **8-channel**, **16,384 Hz** FIFO-A mixer using DMA1 plus 256-sample Timer1 refills. Code-proven gameplay routing starts music **ID 0** on normal Levels 0–9 and **ID 1** on Level 10; music ID 2 is preserved as canonical data but is code-proven **unreachable/orphaned in the public demo**. The loop player uses mode 2 and volume `0x90`, reserves its channel against one-shot allocation, loops by resetting its cursor at sample end, and participates in the exact recovered 75-word fade/replacement path. High-confidence SFX routes now reproduce **SFX 6** on the title START transition, **SFX 3** on accepted state-2 dialogue/state-4 collection activation, **SFX 4** when the secondary social-topic cursor actually moves, **SFX 5** on a normal generic scene portal activation, **SFX 7** on the code-proven state4 dialogue terminal opcodes `-1/-2/-3`, and **SFX 13 exactly once** on the state4 final-sketch `-5` transition before the safe `final_effect_pending` boundary. Remaining medium-confidence call sites stay unwired rather than being assigned guessed actions.

The same level-entry path rebuilds a fixed-capacity actor pool from generated canonical descriptors. It loads **241 unique non-Player physical descriptors through 290 level references**, then appends the **16 story-overlay descriptors** that match the current level; the maximum current population is 65 actors. NPC/story actors use 32 deduplicated exact frame-1 8bpp visual combinations and a bounded OAM range after the Player. State-3 route followers keep 21.11 fixed-point positions and move by the constructor-proven `0x100` fixed units (1/8 pixel) per update toward the five recovered six-waypoint routes. Fresh-A state 1/2/4 contacts now feed `GbStoryRuntime`: all 7 scripts/58 dialogue records are generated into the build, normal-vs-state4 opcodes stay context-specific, Stas/Julia social menus use the recovered action/topic/response tables, the six collection steps persist consumed overlays, and the fourth/fifth steps trigger the rusty-key and monster/cliffhanger paths. BG0 uses the recovered CFA font for dialogue/social text. State4 `-5` intentionally stops at `final_effect_pending` and holds the presentation rather than issuing the unsafe original expanding-VRAM writes. Story overlays still start from level-only activation except for consumed-state persistence; grass/leaves/foreground descriptors remain non-rendering until their visual behavior is proved. Generic physical portals remain in `portal.c`, while the four Level-10 turn-4/5 records are intercepted by the separate story-gate path.

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
- generated canonical story assets: 7 dialogue scripts / 58 records, six message records, two reachable social profiles, action/topic/response tables, CFA font glyphs, and five monster sprites;
- persistent `GbStoryRuntime` with context-sensitive dialogue opcodes, collection/consumption state, social menus, safe message lookups, special Level-10 gate handling, and a safe `final_effect_pending` terminal boundary;
- canonical custom PCM runtime with 14 embedded original payloads, eight software-mixed channels, exact 16,384 Hz FIFO-A output, DMA1, 256-sample double buffering, and code-proven music/SFX routing;
- pixel-space player/camera coordinates;
- small C modules under `source/engine` and `source/game`;
- generated C assets under `data/`;
- Tiled-compatible flattened inspection copies under `maps/`.

The normal build does **not** require an original Graveblood ROM or Python. The original audio payloads are already checked into `data/audio/` and linked by `data/audio_samples.s`; they are not converted, resampled, normalized, or trimmed. Asset regeneration does require the canonical demo ROM because the runtime assets preserve the original BG graphics, palettes, streamed source layers, translation data, fixed/parallax sources, collision grids, physical portals, and exact Player animation frames for all canonical levels/variants. Generated assets are checked into the repository.

See [`../DEVELOPING_AND_BUILDING.md`](../DEVELOPING_AND_BUILDING.md).
