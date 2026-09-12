# Graveblood_RE reconstruction

This directory is the permanent **CFA-style devkitPro/libgba** reconstruction runtime.
It deliberately follows the original game's historical toolchain/architecture lineage instead of wrapping the project in a modern high-level GBA engine.

## Current playable milestone

The ROM now boots into the recovered **Title scene**. Its exact four-layer Mode-0 presentation is reconstructed: BG0 text overlay, BG1 30x20 artwork, BG2/BG3 64x32 backing, exact partial BG/OBJ palettes and OBJ tile bank, canonical hidden OAM, four-state tile animation, frame-counter prompt blink, fresh-START gate, **SFX 6**, and 120-update delayed transition before entering Level 7. There is deliberately no title music because the exhaustive public-demo loop-player scan contains no Title call. After START, the runtime registry contains exact checked-in streamed assets for **all 11 canonical levels and all 13 recovered graphics variants**.

Controls:

- **D-pad** — move the recovered 16x32 player sprite;
- the player uses the recovered 6-frame regular walk, 6-frame up/back walk, mirrored 8-phase idle, retained horizontal facing, and right-facing H-flip behavior;
- movement uses the recovered **8x8 u16 collision grid** (`0 = walkable`, nonzero = blocked); Level 6 intentionally aliases the same compact 30x20 ROM source into collision and visual-B record fields, while the runtime keeps their globals/consumers separate;
- **A** near a state-1/2/4 NPC/story actor — enter the recovered social, dialogue, or collection path;
- **A** on a normal recovered `fgtile` portal — change to its destination level through the generic portal path;
- after the fourth collection advances progress `3 -> 4`, **A** on the Level-10 `turn=4/5` gate uses the recovered forced vertical traversal (Y=360 or Y=410) rather than `portTo=8`;
- while normal gameplay/story UI is idle, hold exactly **B+SELECT** to enter the recovered Wardrobe browser; fresh Left/Right browse selectors 0..6 and fresh B exits to Level 7; there is no equip/A-confirm action;
- **START** during ordinary gameplay opens the recovered PDA; L/R switches `MESSAGES / STATUS / FRIENDS / BACKPACK`, MESSAGES uses Left/Right for available message-stream slots, FRIENDS uses Up/Down across its six recovered entries, and START inside the PDA reopens it rather than closing it; no ordinary close key is invented;
- 33 generic scene-portal records resolve through the runtime registry; the four Level-10 gate records remain special, and the Level-9 `treetype=20` record executes its recovered fresh-A vertical target to Y=512 instead of treating stored `portTo=524` as a level. The canonical actor streams place these special controllers after Player (Level 9: 2 -> 11; Level 10: 1 -> 13..16), so the reconstruction evaluates those actions after Player update and lets their queued target resolve on the next Player update.

All 11 levels use the recovered multi-layer world architecture rather than a flattened runtime background. BG1 and BG2 are 32x32 ring-buffer windows streamed from the original visual world layers, while BG3 uses the recovered fixed parallax map at quarter camera speed. Level 0 additionally exposes recovered graphics variants 1 and 2 through `gb_level_assets(0, variant)`; normal portal entry currently selects variant 0.


The runtime now reconstructs the public-demo **PDA** as a dedicated scene. It uses the four exact ROM-derived 30x20 page chrome maps with a non-colliding dynamic text layer, preserves the currently loaded level graphics like the original renderer, opens/reopens on fresh START after stopping reserved channels 0..2 and playing SFX6, switches bounded top-level pages with SFX11, selects available MESSAGES streams with SFX4, and renders the recovered six-entry FRIENDS list through a three-row cursor/scroll window. Successful FRIENDS movement uses SFX4; attempts beyond the first/last entry use SFX12. STATUS and BACKPACK remain header-only. The original invalid-page return helper is retained as a latent parity path with SFX7, but no B/START close action is fabricated because no ordinary close-key setter is code-proven.

The runtime also reconstructs the public-demo **Wardrobe browse/preview-only** path: exact held B+SELECT entry, selector 0 reset, seven ROM-derived Level-7 preview background pages and 16x32 8bpp outfit figures, fresh Left/Right bounds `0..6`, and fresh-B Level-7 exit. The browser never mutates the live gameplay graphics bank and does not invent an A-confirm/equip action. SFX11 is not wired because the known SFX11 calls are outside the recovered selector navigation branches.

The runtime now also embeds the canonical custom-PCM sound bank: all **14 pointer/length table entries** are checked in byte-for-byte as signed 8-bit mono PCM and linked through `data/audio_samples.s`. `source/engine/audio.c` implements the recovered **8-channel**, **16,384 Hz** FIFO-A mixer using DMA1 plus 256-sample Timer1 refills. Code-proven gameplay routing starts music **ID 0** on normal Levels 0–9 and **ID 1** on Level 10; music ID 2 is preserved as canonical data but is code-proven **unreachable/orphaned in the public demo**. The loop player uses mode 2 and volume `0x90`, reserves its channel against one-shot allocation, loops by resetting its cursor at sample end, and participates in the exact recovered 75-word fade/replacement path. Static RE now closes the entire one-shot call graph at **30/30 high-confidence call sites**. The executable reconstruction wires the routes whose owning subsystems exist, including Title START, PDA open/tab/message/friends feedback, dialogue/collection activation and terminals, generic portals, and final sketch. The two technically identified latent combat/effect-object constructor sounds remain unwired because Step-3 static closure proved the public demo has no live projectile spawn root; wiring them would invent reachable gameplay rather than reconstruct it.

The same level-entry path rebuilds a fixed-capacity actor pool from generated canonical descriptors. It loads **241 unique non-Player physical descriptors through 290 level references**, then appends the **16 story-overlay descriptors** that match the current level; the maximum current population is 65 actors. NPC/story actors use 34 recovered 8bpp visual families with all eight ROM-addressable frames packed per family and a bounded OAM range after the Player. Actor positions use recovered 24.8 fixed-point storage (`0x100` = 1 pixel). State-3 route followers convert serialized 8-pixel-cell waypoints with `waypoint << 11` and move by the constructor-proven `0x100` fixed units per update toward the five recovered six-waypoint routes. Fresh-A state 1/2/4 contacts now feed `GbStoryRuntime`: all 7 scripts/58 dialogue records are generated into the build, normal-vs-state4 opcodes stay context-specific, Stas/Julia social menus use the recovered action/topic/response tables, the six collection steps persist consumed overlays, and the fourth/fifth steps trigger the rusty-key and monster/cliffhanger paths. The original normal-context opcode `-5` path is retained as RE evidence only: its `0x08005720(argument)` OBJ-bank loader is unreachable from canonical state-2 selectors, while state-4 progress 4 intercepts the sole `-5` record with the final-sketch handler. BG0 uses the recovered CFA font for dialogue/social text. State4 `-5` reproduces the exact statically reachable argument-0 VRAM blast (96,000 + 16,000 bytes) while the terminal flag remains latched; startup seeds the argument state to zero and exhaustive executable alias-write closure finds no writer capable of seeding it above 1000, so the larger branch is unreachable from a normal public-demo boot. Story overlays still start from level-only activation except for consumed-state persistence. Grass now renders its exact 16x16 canonical sprite with recovered flip/depth behavior; Leaves descriptors are invisible emitters whose shared cooldown/cycle state spawns the recovered four-frame 8x8 particles, while Fgtile rendering remains a proven no-op. Generic physical portals remain in `portal.c`, while the four Level-10 turn-4/5 records are intercepted by the separate story-gate path. Gameplay scene requests are queued with the recovered countdown semantics (generic portals and Wardrobe exit use delay 10; Title keeps delay 120), and the hidden Level-9 X>2555 Player boundary queues Level 10 while entering the recovered mode-5/mode-6 scripted entrance. Normal Player walking now uses 24.8 fixed-point ±0x100 cardinal requests through the ROM-derived 16×16 collision solver, including tile-14 status blocking and exact one-pixel corner correction instead of the old four-foot-point integer approximation.

## Runtime architecture

- devkitARM `gba_rules` build;
- libgba hardware definitions;
- Mode 0 with four 8bpp text backgrounds sharing character base 0;
- **BG0 / screenblock 27 / priority 0** — reserved fixed UI/text plane;
- **BG1 / screenblock 28 / priority 1** — streamed world layer A;
- **BG2 / screenblock 29 / priority 2** — streamed world layer B;
- **BG3 / screenblock 30 / priority 3** — quarter-speed parallax;
- exact original `0xD800`-byte BG graphics blobs, BGR555 palettes, source layers, translation tables, and fixed-map sources checked into generated C assets for all 13 variants;
- persistent ROM-style camera tracking: Player center is allowed to move inside the X=96..144 / Y=67..93 dead-zone, the camera survives scene/level loads, and active gameplay separates tracking from publication: the previously tracked camera is clamped/streamed and used for the current object draw traversal before object updates run; Player tracking during the later update traversal becomes visible on the next frame;
- recovered post-Player ordering for the Level-9 bicycle and Level-10 turn4/5 Fgtile controllers, guarded by `data/player_fgtile_update_order.csv`;
- recovered object ordering around Player: the story-overlay list is inserted before the physical level list, all 92 canonical physical-NPC references are post-Player, and the 33 generic portal Fgtiles split into 6 pre-Player / 27 post-Player controllers; draw submission now follows the same insertion order through one monotonic gameplay OAM pass, using the generated per-level Player physical index; guarded by `data/story_overlay_update_order.csv`, `data/player_npc_update_order.csv`, `data/player_portal_update_order.csv`, and `data/gameplay_oam_insertion_order.csv`;
- 8x8 world cells;
- insertion-ordered hardware OAM traversal for Player plus bounded NPC/story/Grass/leaf-particle sprites;
- 24 losslessly packed recovered Player animation frames in OBJ palette bank 15, coexisting with the exact 8bpp actor palette/frames;
- generated actor descriptors, per-level reference spans, story overlays, route tables, exact NPC/story frame-1 assets, exact Grass sprite pixels, and four exact leaf-particle frames;
- generated canonical story assets: 7 dialogue scripts / 58 records, six message records, two reachable social profiles, action/topic/response tables, CFA font glyphs, and five monster sprites;
- persistent `GbStoryRuntime` with context-sensitive dialogue opcodes, collection/consumption state, social menus with separate D-pad selection/fresh-A confirmation, zero-count state-2 leaves, the code-proven SFX7 B-return path, the exact recovered shared SUBJECT/CRITICIZE response RNG, safe message lookups, special Level-10 gate handling, and the bounded reachable final-effect runtime;
- dedicated hardware-free `GbPdaRuntime` plus exact generated PDA chrome, recovered MESSAGES/FRIENDS content routing, and PDA audio/scene integration;
- canonical custom PCM runtime with 14 embedded original payloads, eight software-mixed channels, exact 16,384 Hz FIFO-A output, DMA1, 256-sample double buffering, and code-proven music/SFX routing;
- pixel-space player/camera coordinates;
- small C modules under `source/engine` and `source/game`;
- generated C assets under `data/`;
- Tiled-compatible flattened inspection copies under `maps/`.

The normal build does **not** require an original Graveblood ROM or Python. The original audio payloads are already checked into `data/audio/` and linked by `data/audio_samples.s`; they are not converted, resampled, normalized, or trimmed. Asset regeneration does require the canonical demo ROM because the runtime assets preserve the original BG graphics, palettes, streamed source layers, translation data, fixed/parallax sources, collision grids, physical portals, and exact Player animation frames for all canonical levels/variants. Generated assets are checked into the repository.


## Validation cartridges

The normal target remains `Graveblood_RE.gba`. Two compile-time-only validation targets share the same production runtime without changing normal boot behavior:

- `Graveblood_RE_selftest.gba` (`GB_EMULATOR_SELFTEST`) is the mGBA/GDB cartridge used by CI for seven EWRAM checks plus the native PPU screenshot probe.
- `Graveblood_RE_device_test.gba` (`GB_DEVICE_SELFTEST`) is the flash-cart cartridge. It shows an overall green/red Mode-3 result, seven per-check bars in the canonical check order, and plays recovered SFX6 once after the checks so real speaker output can be confirmed by ear.

See [`../DEVELOPING_AND_BUILDING.md`](../DEVELOPING_AND_BUILDING.md) for exact build commands and the device-bar legend.
