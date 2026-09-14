# Graveblood_RE

Unofficial fan reverse-engineering and reconstruction project for Graveblood, developed with permission from Cojam.

This repository documents and reproducibly extracts structures from the **canonical latest public demo ROM**:

`Graveblood 0.0.1.1.5.2 demo.gba`

Expected SHA-256:

`e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b`

The older **Pre Pre Pre Alpha** build is used **only as a differential reference** to identify inherited CFA-era code and later Graveblood additions. Alpha content is not treated as canonical game content.

Alpha reference SHA-256:

`f63e1604c3887a9f018961cadca6365fe621f006b83f458702c68b079e0b0f0a`

The ROMs themselves are intentionally **not included** in this archive.

## Buildable CFA/devkitPro reconstruction

`Graveblood_RE` now uses a permanent **CFA-style devkitPro/devkitARM + libgba** runtime. The temporary high-level-engine/debug-shell path has been removed. The build follows the original game's CFA lineage: Mode 0 tile backgrounds, 8x8 world cells, hardware OAM sprites, pixel-space actors/camera, and compact C modules.

The current playable milestone now boots into the **canonical recovered Title scene** instead of jumping directly into gameplay. The title now reproduces the recovered four-layer hardware setup: BG0/screenblock 27 is the text overlay, BG1/screenblock 28 holds the exact ROM-derived 30x20 artwork, BG2/BG3 provide the recovered 64x32 backing, and the original partial BG/OBJ palettes plus 0x8000-byte OBJ bank are loaded under final `DISPCNT=0x1F00`. It cycles the two recovered tile-patch regions through four animation states on the original seven-update cadence, blinks `PRESS START...` from frame-counter bit 4, and requires fresh START. START plays code-proven **SFX 6**, queues Gameplay Level 7, and preserves the recovered **120-update transition delay**; no title music is added because no public-demo title loop-player route is code-proven. After that handoff, the streamed runtime can load **all 11 canonical level records and all 13 recovered graphics variants**, populate them with canonical actors, and execute the first clean-room story runtime. Every level has exact ROM-derived BG graphics/palette, streamed A/B source layers, translation data, fixed/parallax source, collision grid, spawn point, physical portal metadata, and level actor references checked into the reconstruction. The actor runtime contains **241 unique non-Player physical descriptors referenced 290 times across levels**, loads each level-valid member of the **16 story-overlay descriptors before the physical level list**, and follows the five recovered six-waypoint NPC routes. NPC/story rendering now carries the ROM draw cadence across **34 ROM-addressable `(legsColor, subtype)` visual families** (including the state-3 `base+8` / `base+16` directional families), with eight extracted frames per family. Actor positions use the recovered **24.8 fixed-point** storage (`0x100` = 1 pixel); state-3 routes keep their serialized waypoints as 8-pixel cells (`waypoint << 11`), resolve the previous frame's queued request through the shared collision solver, then queue the next constructor-proven `0x100` step. State 1/2/4 contacts now feed a persistent `GbStoryRuntime` that executes the recovered dialogue/social/collection state machines, the six-step sketch/key progression, consumed-overlay persistence, canonical BG0 text UI, monster transition, and the post-rusty-key Level-10 forced traversal. The four Level-10 `turn=4/5` records are explicitly kept out of generic `portTo=8` behavior; the remaining **33 normal scene-portal records** use the generic portal path, while the Level-9 `treetype=20` record preserves its stored `portTo=524` only as metadata and instead executes the recovered fresh-A **bicycle mount** across the exact Player anchor bounds x=504..519/y=464..479: it queues the Y=512 fixed8 target and stores shared ride mode `0x030005F4=2`. The final fifth-sketch sequence now reproduces the exact statically reachable argument-0 VRAM blast (96,000 + 16,000 bytes): the state-4 `-5` handler applies the first blast in that same update, and the latched terminal flag replays it at the Player slot on later updates without freezing the normal Player/object traversal. Startup zeroes the argument state, exhaustive executable alias-write closure finds no seed above 1000, and scene transitions do not reseed/reset it, so the larger latent branch is unreachable from a normal public-demo boot. Grass and Leaves foreground behavior is now reconstructed: Grass draws the exact canonical 16x16 logical tile 0x48 with turn-controlled H-flip and player-depth priority, while serialized Leaves actors remain invisible emitters that spawn the recovered four-frame 8x8 falling-leaf particles. Those Leaves now execute at their real physical slot 0 on Levels 0/6/9/10, and a newborn particle is appended to the original manager's live active vector and receives its first ±150 fixed8 velocity step later in that same traversal. Fgtile draw remains a proven no-op, but ordinary parser-default `portTo=33`, `turn=0/1` Fgtile controllers are no longer treated as inert metadata: their recovered `treetype` pair selects one of the 18 initialized patch descriptors and hot-patches descriptor-relative level graphics into BG VRAM with the original 16-pixel hysteresis and second-half one-update latch. The canonical `turn=2, treetype=1` Fgtile records are now active too: they toggle Player's desired gameplay-music selector on a recovered 2x40 contact strip, and the reserved loop follows the original 75-update fade/replacement state machine rather than being chosen solely from the level number. The exact recovered **24-frame** 16x32 Player walk/idle animation—including the level-authored alternate eight-frame idle bank—remains driven through OAM, and movement follows the original collision resolver semantics: **zero-valued 8-pixel cells are passable; nonzero cells block movement**. Fresh START during ordinary gameplay now opens the recovered **PDA**: exact ROM-derived `MESSAGES / STATUS / FRIENDS / BACKPACK` chrome, bounded shoulder tab switching with SFX11, MESSAGES primary/auxiliary stream selection with SFX4, and the six-entry FRIENDS three-row window (`Kate, Stas, IQ 54, Kiata, Alex, Evelina`) with SFX4 movement and SFX12 boundary feedback. STATUS/BACKPACK remain header-only because that is all the public-demo renderer proves. START while already in the PDA reopens/resets it rather than closing it; no ordinary B/START close action is invented because static RE proves none.

Start here:

- `DEVELOPING_AND_BUILDING.md` — devkitPro/devkitARM/libgba setup, build, emulator/hardware testing, asset regeneration, and release tags.
- `reconstruction/` — CFA-style C runtime and checked-in generated assets.
- `.github/workflows/build-release-rom.yml` — branch/PR ROM-independent test+build validation plus a minimal tagged-release path that publishes only the versioned game ROM.

The normal reconstruction build does not require the original demo ROM. Development releases still use tags such as `Graveblood_RE_v0.0.1-dev`; GitHub Actions publishes the versioned ROM asset as `Graveblood_RE_v0.0.1.gba`.

---

## 1. What this repository contains

The workspace now includes:

- a buildable CFA-style devkitPro/libgba reconstruction under `reconstruction/`, with all 11 canonical worlds / 13 graphics variants generated and loadable through the streamed renderer;
- local development/build/release instructions plus a minimal tagged-ROM GitHub release workflow;
- canonical ROM/header metadata;
- 11 corrected 0x40-byte level records;
- runtime-patched level dimensions;
- 13 graphics descriptors/variants;
- map/world-layer and collision summaries;
- 267 decoded actor records;
- 33 code-proven generic scene-transition edges, plus five code-diverted special Fgtile action records (four Level-10 turn=4/5 gates and the Level-9 treetype=20 bicycle-mount tile);
- 16 code-proven story-overlay entity records loaded alongside every physical level actor list;
- 7 dialogue scripts / 58 fixed records;
- context-sensitive normal-vs-state4 dialogue opcode semantics;
- six-step state-4 collection selector, including rusty-key and fifth-sketch transitions;
- conservative story-entity identity export (Stas, Julia, one code-backed IQ 54 overlay, Katya, five collection pickups, and role-only classifications for the still-unnamed overlays/hotspots);
- decoded message/progression streams;
- deterministic PDA extraction plus executable four-page PDA runtime/presentation, including MESSAGES stream selection and the six-entry FRIENDS window;
- five NPC routes / 30 waypoints;
- generated actor-runtime data: 241 unique non-Player physical descriptors / 290 per-level references plus all 16 story overlays, with a maximum loaded population of 65;
- exact NPC/story rendering through 34 ROM-addressable `(legsColor, subtype)` visual families with eight extracted frames each, including the state-3 `base+8` / `base+16` directional banks and the ROM draw-side frame/countdown cadence;
- state-3 NPC route following with 24.8 actor positions, 8-pixel-cell waypoints (`<< 11`), one-frame queued shared-collision motion, and the code-proven `0x100` = 1-pixel velocity;
- code-proven NPC state 1/2/4 interaction geometry (5×5 social, conditional 4×4/5×5 dialogue, 4×4 collection), fresh-A gates, and typed interaction events for the deferred dialogue/progression layer;
- Player/OBJ rendering pipeline evidence, story-entity sprite reconstruction, and executable five-sprite monster composite;
- 10 fixed wardrobe-name slots plus the recovered `Player+0x240` browse/preview selector, preview OBJ/BG tables, and code-backed no-equip boundary;
- exact-byte alpha↔latest matcher results;
- corrected 8bpp world renderer;
- raw world-layer A/B, composited world, and actor-overlay renders for all levels/graphics variants;
- ROM-side OBJ source atlas and reference character-frame renders;
- focused Thumb disassembly snapshots;
- level-10 collection-index gate activation policy tied to the rusty-key threshold;
- regression tests for corrected level/BG/OBJ/NPC/source/spawn/dialogue-context/collection/gate/wardrobe behavior.

Current canonical extraction counts:

| Item | Count |
|---|---:|
| Level records | 11 |
| Graphics variants | 13 |
| Physical actor records | 267 |
| Level-referenced unique actors | 251 |
| Story-overlay entity records | 16 |
| Physical portal tiles | 38 |
| Dialogue scripts | 7 |
| Dialogue records | 58 |
| NPC routes | 5 |
| Route waypoints | 30 |
| Code-proven NPC interaction geometry modes | 3 |
| Message streams | 3 |
| Initialized message records | 6 |
| Wardrobe label slots | 10 |
| Complete ROM-side OBJ source tiles | 5,536 |
| Exact alpha↔latest matched blocks | 109 |

---

## 2. Corrected level architecture

A v1 interpretation incorrectly treated ROM offset `0xA8D9F8` as the beginning of the level table. That address is actually **field +0x38 of level record 0**.

The true source table begins at:

`ROM offset 0x00A8D9C0` / address `0x08A8D9C0`

There are **11 records × 0x40 bytes**. Gameplay indexes the runtime copy at:

`0x03000A10 + level_id * 0x40`

The current field map is:

```text
LevelRecord (0x40 bytes)
+0x00  world width                    constructor-patched
+0x04  world height                   constructor-patched
+0x08  streamed visual world layer A
+0x0C  collision/world grid
+0x10  streamed visual world layer B
+0x14  packed/static map width         constructor-patched
+0x18  packed/static map height        constructor-patched
+0x1C  packed BG2 bootstrap + BG3 parallax source
+0x20  tile-translation index/base value
+0x24  graphics descriptor variant 0
+0x28  graphics descriptor variant 1  level 0 only
+0x2C  graphics descriptor variant 2  level 0 only
+0x30  zero in recovered records
+0x34  zero in recovered records
+0x38  actor-list pointer
+0x3C  Player alternate-idle selector copied to Player+0x1E0 on scene activation
```

The runtime dimensions patched by `0x0800DBF4` are:

| Level | World tiles | Approx. world pixels | Packed map |
|---:|---:|---:|---:|
| 0 | 256×256 | 2048×2048 | 64×32 |
| 1 | 64×64 | 512×512 | 64×32 |
| 2 | 256×200 | 2048×1600 | 64×32 |
| 3 | 256×160 | 2048×1280 | 64×32 |
| 4 | 192×160 | 1536×1280 | 64×32 |
| 5 | 320×200 | 2560×1600 | 64×32 |
| 6 | 30×20 | 240×160 | 30×20 |
| 7 | 29×24 | 232×192 | 64×32 |
| 8 | 37×43 | 296×344 | 64×32 |
| 9 | 782×128 | 6256×1024 | 64×32 |
| 10 | 168×128 | 1344×1024 | 64×32 |

Level 6 has one intentional source-data alias inside this otherwise stable layout: both `+0x0C` and `+0x10` contain `0x08655CC4`. This is **not** a field-identification ambiguity. `load_level_record_resources()` copies `+0x0C` to collision global `0x03000550` and `+0x10` to visual-B global `0x03000564`; the motion solver at `0x08004670` consumes only the former while the world streamer at `0x0800A330` consumes only the latter. The compact 30x20 source therefore legitimately serves both roles (495 zero / 105 nonzero cells). See `data/level6_collision_visual_alias.csv`.

`data/level_runtime_structs.csv`, `data/level_world_layers.csv`, `data/collision_summary.csv`, and `data/level6_collision_visual_alias.csv` expose these structures in machine-readable form.

---

## 3. Background graphics pipeline

The latest demo configures four **8bpp / 256-color text backgrounds** at `0x0800A208`:

| BG | CNT | Priority | Screenblock | Proven runtime role |
|---|---:|---:|---:|---|
| BG0 | `0x1B80` | 0 | 27 | fixed screen-space text/UI plane |
| BG1 | `0x1C81` | 1 | 28 | streamed world layer B (foreground) |
| BG2 | `0x1D82` | 2 | 29 | streamed world layer A (room/backdrop) |
| BG3 | `0x1E83` | 3 | 30 | quarter-speed parallax |

Gameplay update `0x08004B74` applies:

```text
BG0 scroll = (0, 0)
BG1 scroll = (cameraX, cameraY)
BG2 scroll = (cameraX, cameraY)
BG3 scroll = (cameraX / 4, cameraY / 4)
```

The gameplay stream call at `0x08004B74` passes screenblock 29 (`0x0600E800`, BG2) as destination 1 and screenblock 28 (`0x0600E000`, BG1) as destination 2. `0x0800A330` writes visual layer A to destination 1 and layer B to destination 2, proving **A -> BG2 / B -> BG1**. The same routine updates an inclusive **31x21** rectangle (`+30/+20`) inside the 32x32 hardware ring buffer. Its source address is linear rather than independently X/Y-clamped, so Level 7's recovered signed camera maximum of `-8` legitimately publishes stream X `-1` and aliases the previous-row tail at the left edge. The BG-state audit now closes the other side of that unchecked behavior too: `0x0800A400` can request the guard cells immediately before/after a layer, and `0x0800A330` performs both the layer read and `translation[source_id]` lookup without bounds checks. The old clean-room streamer returned zero for those camera-reachable overreads; generated level assets now carry compact already-translated guard tables for exactly cell `-1` and cells `N..N+width`, preserving the canonical ROM-adjacent results without C undefined behavior. `data/bg_state_parity.csv` verifies 13 initial graphics states, 22 layer-guard states, and 56 reachable ordinary-Fgtile patch outcomes with zero byte mismatches. This matters beyond an off-screen border: high 8bpp tile IDs can alias BG screenblock memory (the known Level-2 case), so guard-map writes can feed visible tile pixels.

The follow-up visible-frame audit closes the next layer of that chain. `tools/audit_visible_bg_frames.py` reconstructs the four Mode-0 gameplay BGs in one 64 KiB BG-VRAM image so 8bpp tile IDs 864..1023 naturally alias screenblocks 27..31, applies 32x32 wrapping, H/V flips, priority and palette-index-0 transparency, then resolves the final 240x160 image through the recovered BG palette to BGR555 pixels. `data/visible_bg_frame_parity.csv` covers **121 deterministic gameplay checkpoints** across all 11 levels: spawn/camera boundaries, ordinary Fgtile base/alternate mutations, and the Level-0/2 screenblock-alias regions. Canonical-ROM reconstruction and independently parsed checked-in C assets currently produce **0 mismatched visible pixels in all 121 states**. The audit includes adversarial tests that deliberately corrupt a checked-in tile or palette entry and require visible mismatches, so the zero result is not a shared-generator tautology. Its cold-boot model intentionally starts BG VRAM at zero: the GBA BIOS zeroes VRAM before cartridge execution, while the public-demo level setup subsequently uploads character data through `0x0600D7FF` and writes map screenblocks 27..30; screenblock 31 is otherwise left at its BIOS-zero value before the ending effect. No production renderer change was required by this checkpoint.

The matching OBJ/OAM audit now closes the sprite-source side of the visible frame. `tools/audit_visible_oam_frames.py` reconstructs 8bpp tiled OBJ pieces, signed hardware screen wrapping/clipping, H-flip, palette-index-0 transparency, priority and equal-priority OAM-index tie-breaking, then resolves them through the canonical gameplay OBJ source palette to BGR555. `data/visible_oam_frame_parity.csv` covers **88 deterministic sprite checkpoints**: 25 Player cases, 43 NPC cases spanning all 34 recovered visual families plus an eight-frame sweep, 3 Grass cases, all 4 Leaf frames, all 6 riding-bicycle frames, both Level-9/10 parked bicycles, and 5 monster states. After one ROM-proven production fix, all **88/88 checkpoints have zero pixel mismatches**. The fixed bug was specific but visible: original `Player_draw` checks the fifth-sketch monster branch before the Level-9/10 parked-bicycle branches, so monster rendering is exclusive; the RE had incorrectly appended the parked bicycle after the five monster cells. Adversarial tests mutate checked-in sprite bytes and OBJ colors and require visible mismatches, while the time-of-day OBJ-palette transformation remains independently covered by the ROM-backed gameplay-lighting tests rather than being duplicated inside this source-palette compositor.

Camera tracking is now ROM-backed rather than continuously centered. `0x08006550` computes the Player body center from fixed8 fields and keeps it inside **X=96..144 / Y=67..93 pixels** relative to the camera; only crossing a dead-zone edge moves the camera. `0x0800A2D4` then clamps X/Y to the **30x20-tile (240x160)** viewport bounds and publishes `(cameraX>>3,cameraY>>3)` as the streamed-world origin. Gameplay-scene activation loads the new level first, then calls that tracker and clamp without resetting `0x03000570/0x0300056C`, so camera position persists across level transitions instead of snapping to `(0,0)`. Active gameplay also follows the recovered frame phases rather than the earlier update-then-draw approximation: `GameplayScene_update` publishes/clamps and streams the previously tracked camera, begins OAM, traverses every object's **draw slot `+0x10`**, ends OAM, and only then traverses the **update slot `+0x0C`**. Player update calls `0x08006550` in that later phase, so a camera move becomes visible/streamed on the next active gameplay frame. Fresh START PDA entry and hidden B+SELECT Wardrobe entry are likewise handled after the current gameplay draw because both gates live inside `Player_update`. Step 15 establishes the global draw-before-update frame contract; Step 17 closes the physical-NPC slice, and Step 18 closes the remaining overlay/portal placement around Player: the story-overlay list is loaded before the physical level list, while the 33 generic portal Fgtiles split into **6 pre-Player** and **27 post-Player** updates. See `data/camera_runtime_semantics.csv`, `data/gameplay_frame_order.csv`, `data/story_overlay_update_order.csv`, `data/player_npc_update_order.csv`, and `data/player_portal_update_order.csv`.

Step 16 closes the proven **Player -> special Fgtile** ordering slice. In the canonical physical actor streams, Level 9 places Player at index **2** and the `treetype=20` bicycle controller at index **11** (`0x08386FF0`), while Level 10 places Player at index **1** and its four `turn=4/5` traversal controllers at indices **13..16** (`0x08367380..0x08367464`). Because the original generic updater walks objects in serialized order, these controllers see the Player's position *after that frame's Player update*. The clean-room loop therefore evaluates those recovered Level-9/10 special Fgtile actions after `gb_player_update()`, so any vertical target they queue resolves on the next Player update. See `data/player_fgtile_update_order.csv`.

Step 17 closes the canonical **Player -> physical NPC** ordering slice across all 11 levels: all **92 physical-NPC level references** are post-Player. Step 18 closes the two ordering questions left around that result. First, `load_level_record_resources` submits the selected 16-record story-overlay list to `0x080010A4` at `0x08005996` and only later submits `LevelRecord+0x38` physical actors at `0x080059AE`, proving overlays are inserted before Player and validating the clean-room pre-Player overlay phase. Second, the **33 generic portals** are not all post-Player: Level 1 portal indices 0/1 and all four Level 8 portals are pre-Player, while the other **27** are post-Player. The runtime now goes beyond the old coarse pre/post buckets and resumes the original serialized physical-object traversal one ordinal at a time after Player. This matters in Levels 0/1/2/5/6/9, where post-Player portal Fgtiles and NPCs are interleaved (for example Level 1 is `Player(2) -> portal(3) -> NPC(4) -> portals(5..7) -> NPCs(8..15)`). NPC motion/proximity/SFX, the Level-9 bicycle controller, Level-10 gate records, and generic portal activation therefore execute at their recovered object slots, and a queued scene request no longer aborts later object updates in the same frame. Generated `GbPortal.physical_index` values come directly from canonical actor-table order, including target-Level-0 portals. See `data/player_npc_update_order.csv`, `data/story_overlay_update_order.csv`, and `data/player_portal_update_order.csv`.

Step 19 extends that same insertion-order proof into **draw/OAM ordering**. The original common OBJ submit helper at `0x0800A8F0` allocates from one monotonically increasing OAM counter, so equal-priority sprite tie-breaking follows object draw traversal. The clean-room actor array now stores level-valid story overlays before the physical list, the generator exports Player's physical-list index for every level (`8,2,0,0,0,0,8,0,4,2,1`), and production gameplay uses one unified OAM pass: overlay/physical objects before Player, then Player, then objects after Player, followed by dynamic Leaves. This replaces the old blanket reservation where Player always occupied OAM 0..8. Ordinary physical NPCs are still post-Player and therefore remain behind Player when both use priority 2; pre-Player story overlays can correctly own lower OAM indices. See `data/gameplay_oam_insertion_order.csv`.

The current controller-parity work restores the remaining active ordinary Fgtile/foreground behavior that was still outside that traversal. `Fgtile_update` reaches `0x08005C6C` for parser-default `portTo=33` turn-0/1 strips: the clean-room runtime preserves `treetype`, reproduces the recovered 2x90 / 90x2 scan, the ±16-pixel hysteresis shift, and the original second-half pending latch, then copies through the exact 18-entry `(destination, source, count)` patch table into literal BG VRAM. The three serialized `turn=2, treetype=1` descriptors are a separate **music-zone controller**: a 2x40 contact strip toggles Player desired music selector `+0x1CC` between 0 and 1, and Player update then follows the recovered 75-update fade table before replacing the reserved loop and copying desired to applied `+0x1D0`. Their physical ordinals are Level 0/6 index 3 (before Player index 8) and Level 2/5 index 4 (after Player index 0), preserving the original same-frame-versus-next-frame fade timing. The separate full-graphics selector is intentionally not invented as gameplay: it requires `turn==3`, and the canonical public-demo physical tables serialize no such Fgtile. All public-demo Leaves records are physical slot 0 before Player; `Leaves_update` appends a fresh `LeafParticle` to manager vector `+0x14`, and the manager reloads vector end after each update, so the newborn is updated later in the **same frame** instead of starting one frame late. Player-owned PDA/Wardrobe entry checks remain at the Player slot after overlays and those pre-Player objects; the recovered music fade itself runs after the hidden B+SELECT Wardrobe gate but before fresh START/PDA, exactly matching the Player-update order around `0x08008318`, `0x08008328`, and `0x0800849E`.

The alpha build initializes only three inherited backgrounds. The latest build adds the top-priority BG0 while retaining the inherited world-stream routine. Latest `0x0800A330` and alpha `0x0800406C` match byte-for-byte over the recovered function body.

### Graphics descriptors

Each 0x24-byte graphics descriptor supplies the resources loaded by `0x0800575C`, including:

- BG tile source;
- tile-translation table;
- BG palette source/length;
- OBJ tile source;
- OBJ palette source/length.

The loader copies:

- `0xD800` bytes of BG tile graphics to `0x06000000`;
- `0x8000` bytes of initial OBJ tile graphics to `0x06010000`.

There are **13 descriptors/variants** total: one primary variant for every level plus two additional variants for level 0.

All three level-0 variants reuse the same OBJ set while replacing BG tiles, translation data, and BG palette. They are real gameplay-selectable variants through `0x08005BEC` / `0x08005C54`; this workspace deliberately does not invent narrative names such as “day/night” until the triggering semantics are completely proven.

### Tile translation

World cells are rendered as:

```text
u16 source tile id
        ↓
translation[source_id]
        ↓
GBA text-BG screen entry
  bits 0..9  tile index
  bit 10     H flip
  bit 11     V flip
        ↓
8bpp 8×8 BG tile + 256-color BGR555 palette
```

The engine's `0x0800A330` does **not** impose an artificial 2048-entry bound on the translation lookup. Level 2 contains source IDs above 2047, and the routine simply reads `translation[source_id]` as a raw halfword with no bounds check. The old "unresolved/dynamic" map cells are now fully classified rather than treated as missing data: the 0xD800-byte character upload provides exactly 864 8bpp tiles, so translated tile indices 864..1023 read from VRAM screenblocks 27..31. Across all 13 graphics variants there are **1,689 runtime VRAM-alias cells grouped into 81 distinct alias classes**. Of those, 1,531 are in-table Level-0 aliases and 158 are Level-2 unchecked lookup overruns into the adjacent BG palette. The former four ambiguous Level-2 layer-A cells are all source ID 2260 at world cells `(109,85)`, `(119,85)`, `(109,96)`, and `(119,96)`: ID 2260 lands on BG palette entry 210 at `0x085E2B3C`, reads `0x7F9D`, selects tile 925, and therefore fetches its 64 pixel bytes from `0x0600E740` — BG1/screenblock 28 offset `0x740`. Their exact pixels depend on the current streamed BG1 map row, so the offline world renderer intentionally leaves runtime aliases transparent; this is a known hardware self-alias, not unresolved ROM content. `renders/maps/runtime_alias_summary.csv` records the complete classification.

### Packed `+0x1C` source

The common 64×32 source at level `+0x1C` is not one spatial 64-tile-wide room. `0x080057DC` splits it:

- source columns 0..31 → BG2 / screenblock 29 bootstrap;
- source columns 32..63 → BG3 / screenblock 30 parallax.

The renderer keeps BG1/A above BG2/B because hardware priority 1 wins over priority 2.

---

## 4. Actor ABI and alpha differential

The alpha build gives a clean baseline.

Alpha actor parser around `0x0800296C` understands:

`x, y, turn, subtype, treetype, legsColor, num, portTo`

Latest parser `0x080043F8` retains those and adds:

`level, setglobal, state, dial, route`

The homologous alpha actor-policy slot `0x08002950` is literally `bx lr`, while latest `0x080043AC` implements `level`/`setglobal` behavior. This is strong direct evidence that these policy fields were added later.

### Runtime actor fields

| Property | Object offset | Proven interpretation |
|---|---:|---|
| `x` | `+0x08` | 24.8 fixed-point X (`value << 8`) |
| `y` | `+0x0C` | 24.8 fixed-point Y (`value << 8`) |
| `subtype` | `+0x28` | actor-specific subtype |
| `turn` | `+0x4C` | orientation/state value |
| `legsColor` | `+0x4E` | actor visual parameter |
| `num` | `+0x50` | actor-specific numeric parameter |
| `portTo` | `+0x52` | destination level in normal portal path |
| `treetype` | `+0x54` | actor/graphics-state parameter |
| `level` | `+0x56` | level filter |
| `setglobal` | `+0x58` | inherited culling-policy control |
| `state` | `+0x5A` | NPC behavior/interaction enum |
| `dial` | `+0x5C` | dialogue script index |
| `route` | `+0x64` | route index |

`setglobal` retains its literal property name because its polarity is counterintuitive: **value 0 sets inherited object byte +0x31 to 1**, which bypasses normal spatial/camera culling. The machine behavior is high-confidence; a friendly boolean rename is not.

---

## 5. NPC state and route system

`0x0800298C` dispatches the recovered NPC states:

| State | Working interpretation |
|---:|---|
| 0 | default/no special branch |
| 1 | interaction/proximity mode 1 |
| 2 | interaction/proximity mode 2 |
| 3 | **route following** |
| 4 | interaction/proximity mode 4 |

States 1, 2, and 4 use different spatial checks and can enter dialogue on an A-button rising edge; their original design labels remain unknown.

For state 3:

```text
actor.route (+0x64)
       ↓
0x03001818[route]
       ↓
six signed (x,y) waypoints
       ↓
actor+0xF8 = current waypoint
       ↓
steer → reach → index++ → wrap after 5
```

Five routes / 30 waypoints are exported to `data/npc_routes.csv`.

Route 0:

```text
(112,61) → (210,61) → (216,105) → (129,107)
         → (111,91) → (111,61) → repeat
```

Only route 0 is explicitly referenced by currently decoded actor metadata. No claim is made that routes 1–4 are reachable.

---

## 6. Portals and physical level graph

The normal portal path loads `actor+0x52` (`portTo`) and passes it directly to `request_scene()` as the destination Gameplay level.

Recovered normal edges:

```text
0  → 1,2,6,8
1  → 0,2,3,4,5
2  → 0
3  → none recovered
4  → none recovered
5  → 0,4
6  → 1,2,6,8
7  → 6,8
8  → 7,9
9  → 1,6,8
10 → none on the generic scene-transition path
```

After per-level expansion there are **33 code-proven generic scene-transition edges**. Five Fgtile records that carry `portTo` metadata are deliberately excluded from that graph because their control flow diverts before `0x08004258`: the four Level-10 `turn=4/5` rusty-key gates and the Level-9 `treetype=20` tile. The latter still stores `portTo=524`, but fresh-A contact in the recovered 2x2 contact grid (integer Player anchor x=504..519, y=464..479) enters `0x0800417C`, writes a 512-pixel vertical target to Player `+0x394`, calls `0x080080A4`, and stores ride mode **2** to `0x030005F4`; **524 is not used as a scene destination**.

---

## 7. Dialogue VM, Messages, and collection progression

There are **7 dialogue scripts / 58 records**. Each record is exactly `0x90` bytes:

```text
+0x00  27 bytes  speaker
+0x1B 109 bytes  text
+0x88   4 bytes  signed opcode
+0x8C   4 bytes  signed argument
```

### Context-sensitive opcode dispatch

v4 corrects an important v3 overgeneralization: the `0x90`-byte record format is shared, but **opcode semantics depend on the interaction context**.

Normal NPC dialogue uses the dispatcher around `0x08002F76`:

| Opcode | Normal-dialogue behavior |
|---:|---|
| `0` | generic dialogue/content record |
| `-1` | write argument to actor dialogue step `+0x70` |
| `-2` | set primary message-stream selector `0x03001814` |
| `-3` | place stream id in first free auxiliary selector |
| `-4` | write argument to story/message stage `0x030006AC` |
| `-5` | latent OBJ graphics-bank load via `0x08005720(argument)`; dormant from canonical state-2 dialogue |

State-4 collection interactions use a separate dispatcher. In that context:

| Opcode | State-4 pickup behavior |
|---:|---|
| `-1` | set dialogue step, consume interaction, increment collection progress |
| `-2` | set primary message stream, consume interaction, increment progress |
| `-3` | add auxiliary message stream, consume interaction, increment progress |
| `-4` | set monster-render flag `0x0300061C = 1`; **does not** write the record argument to `0x030006AC` |
| `-5` | run final-sketch handler `0x080037F6`, consume pickup, increment progress |

`data/dialogue_context_semantics.csv` is the authoritative context × opcode export. `data/dialogue_opcode_semantics.csv` is retained as a normal-context compatibility view. `dialogue_scripts.csv` also labels `-4/-5` explicitly as **normal-context** interpretations instead of universal meanings.

The normal-context `-5` branch is original but dormant in the canonical public demo. The only `-5` record is **script 6, step 4, argument 6** at `0x080117D8`, while every canonical state-2 dialogue actor selects only scripts **0–3**. Script 6 is reached instead through state-4 collection progress index 4, whose dedicated `0x080037F6` handler intercepts `-5` for the final-sketch sequence. If the generic branch were reached, `0x08005720` would select a ROM OBJ graphics bank with a `0x1800` stride, copy `0x1200` bytes to `0x06010000`, then copy `0x200` bytes from bank offset `+0x1400` to `0x06011400`. The reconstruction deliberately does **not** invent a trigger for that latent bank swap. See `data/normal_dialogue_minus5_reachability.csv`.

### Dialogue page-audio latch

The interaction byte at `0x0300062C` is now closed as the dialogue/presentation latch rather than an unexplained mode flag. Player construction clears it to 0. An accepted state-2/state-4 fresh-A activation whose **immediate target record is text** plays SFX3 at volume 80 when the latch is 0, or SFX8 at volume 80 when it is already 1; both text-page paths then store 1. Negative/control records bypass the SFX3/SFX8 page sound. Normal-context opcodes `-1..-4` each play SFX7 and clear the latch, including chained control records in the same update; because the original `0x08001B74` one-shot routine owns eight independent slots, two consecutive controls really can allocate two SFX7 instances in one frame. State-4 selector `-1` is deliberately silent and clears the latch, state-4 terminal `-1/-2/-3` use SFX7 and clear it, `-4` advances without a page sound or latch clear, and terminal `-5` uses SFX13. The clean-room story runtime therefore keeps an eight-entry FIFO of pending one-shots and drains all queued story sounds each frame instead of collapsing same-frame calls to the last ID. See `data/dialogue_audio_latch_semantics.csv`.

### Messages

Message selector slots initialize to `-1`:

```text
0x03001814 primary
0x03001810 auxiliary 1
0x0300180C auxiliary 2
0x03001808 auxiliary 3
```

The Messages UI resolves:

```text
record = message_stream[selected_stream] + story_stage * 0x82
```

Each `0x82`-byte message record contains 15 bytes title, 15 sender, and 100 body.

Recovered primary stream progression includes:

- stage 0: **Go meet IQ** / Katya;
- stage 1: **Find sketches** / IQ 54.

Only two initialized records are recovered per stream. The local index computation does not visibly clamp later story stages, so a clean-room implementation should define safe behavior rather than copying an unsafe pointer walk blindly.

### State-4 collection selector

`state == 4` does not use the actor's literal `dial=3` directly. The update routine reads collection/progression index:

`0x03000620`

and indexes a six-entry selector built in the function itself:

```text
progress 0 -> script 4   first collection dialogue
progress 1 -> -1         silent collection
progress 2 -> -1         silent collection
progress 3 -> script 5   rusty-key dialogue
progress 4 -> script 6   final sketch / monster transition
progress 5 -> script 0   post-completion fallback
```

Every completed state-4 collection path advances the same index. With exactly five paper/sketch-like story-overlay entities, values 0–4 are the five collection steps and completion leaves the counter at 5. This means the **fourth collected paper triggers the rusty-key dialogue and the fifth triggers the cliffhanger**, independent of which physical paper record is collected first.

Machine-readable exports:

- `data/dialogue_context_semantics.csv`
- `data/state4_collection_progression.csv`
- `data/message_streams.csv`
- `data/message_selectors.csv`

---

## 8. Fifth-sketch monster sequence and rusty-key gate activation

Dialogue script 6 contains:

```text
Vika: "Ok this is the last one"
opcode -4, 6
Vika: "..."
Vika: "What in the world is this?"
opcode -5, 6
```

In the **state-4 pickup context**, the first opcode does not set story stage 6. Instead, the `-4` handler sets:

`0x0300061C = 1`

`Player_draw` (`0x080065FC`) checks that flag immediately. When it is 1, normal Vika rendering is bypassed and execution enters the special branch at `0x080068BC`. That branch submits five 16×16 OBJ sprites with logical tile arguments:

```text
0x159
0x178  0x17A
0x198  0x19A
```

The packaged renderer emulates those exact OAM submissions and produces `renders/sprites/state4_monster_composite.png`: a directly reconstructed dark creature composite, not a manually selected atlas crop.

The sequence now reconstructs as:

```text
fifth collection
   -> selector progress 4 chooses script 6
   -> state4 -4 sets 0x0300061C = 1
   -> Player_draw replaces Vika with five-sprite creature composite
   -> dialogue continues: "..." / "What in the world is this?"
   -> state4 -5 enters 0x080037F6
       -> call 0x08004FE0
       -> play SFX 13
       -> set 0x03000678 = 1
       -> increment collection index to 5
       -> move collection entity Y to -100
       -> clear dialogue state
   -> Player_update gates repeated 0x08004FE0 calls with 0x03000678
      -> if 0x03000674 <= 1000, it resets 0x03000674 to 0 before the call
      -> if 0x03000674 > 1000, it adds 20 before the call
      -> after the effect call it rejoins the ordinary Player_update continuation
```

This corrects an older RE label: `0x03000674` is **not a progress counter on any statically reachable public-demo path**. Startup zero-fills `0x03000000..0x03000788`, so both the argument state at `0x03000674` and event flag at `0x03000678` begin at zero. The opcode `-5` handler calls `0x08004FE0(0)` first and then sets `0x03000678=1`. On subsequent `Player_update` frames, values `<=1000` are explicitly replaced with zero; only a value already above 1000 is incremented by 20. When the flag is set, both branches call `0x08004FE0` at `0x080088B6` and then branch back to `0x080081DA`, so the effect is a Player-entry side effect rather than a terminal gameplay loop. The direct Player-update writer inventory is closed at `0x080081D0` (`>1000 -> +20`) and `0x080088AA` (`<=1000 -> 0`), and an exhaustive Thumb immediate-store alias scan across every executable literal-load root that can address either global finds **no additional argument writer and no post-boot flag reset**. Starting from boot value 0, the low branch therefore writes 0 forever and the high branch can never bootstrap itself. The flag remains latched across gameplay scene transitions and is cleared only by reboot/startup zero-fill. This is a high-confidence static closure for the public-demo executable; only arbitrary hardware/external corruption lies outside that scope. See `data/ending_effect_alias_write_closure.csv`, `data/ending_effect_boot_lifetime.csv`, `data/ending_vram_effect_runtime.csv`, `data/ending_effect_argument_writes.csv`, `data/ending_event_flag_runtime.csv`, and `data/ending_effect_static_reachability.csv`.

`0x08004FE0` is statically quantified. It first biases its argument by 64, then uses byte-counted copy helper `0x08010C54` for two writes:

```text
0x06000000 <- 1500 * (argument + 64) bytes
0x06010000 <-  250 * (argument + 64) bytes
```

At argument 0 those are **96,000 bytes** and **16,000 bytes**. Because the five state-4 sketch overlays are all Level-10 entities, the active Level-10 graphics descriptor makes the two argument-0 ROM sources exact: copy 1 uses `0x085E2B60 + 0x5E801 = 0x08641361`, ending exclusively at `0x08658A61`; copy 2 uses `0x08310654 + 0x5E800 = 0x0836EE54`, ending at `0x08372CD4`. The first range therefore overlaps the first **9,157 bytes of SFX13** (`0x0865669C...`) before those bytes are blasted into VRAM. This is strong static evidence for a corruption/glitch-style effect rather than an ordinary dedicated ending-image load, but it still does not prove the intended visible frame sequence.

The first copy grows by 1,500 bytes per argument step and exceeds the nominal 96 KiB VRAM span from `0x06000000` once the argument reaches 2. Static closure proves the normal public-demo path can supply **argument 0 only**, whose two writes end at `0x06017700` and `0x06013E80` and therefore stay inside VRAM. The clean-room runtime reproduces the exact argument-0 **GBA VRAM result** while the terminal flag remains latched. The first 96,000-byte source is unaligned and the original helper therefore uses byte stores; on the GBA's 16-bit VRAM bus each byte write replicates across its halfword, so after each two-byte pair the odd source byte occupies both destination bytes. The second 16,000-byte source is aligned and follows the helper's wide-copy path, remaining byte-exact. The reconstruction writes those final bus-visible values explicitly with halfword/word stores so behavior is deterministic on hardware and accurate emulators instead of depending on C byte-store behavior. No larger-argument behavior is implemented because that branch is dormant from a normal boot. See `data/ending_vram_effect_copy_model.csv`, `data/ending_vram_effect_runtime.csv`, `data/ending_vram_effect_argument0_payloads.csv`, `data/ending_event_flag_runtime.csv`, `data/ending_vram_effect_level10_sources.csv`, and `disasm/ending_vram_effect_08004FE0.txt`.

### Rusty-key threshold and level-10 gate actors

Level 10 contains four `Fgtile` records in a 2×2 cluster:

```text
(808,384) turn=4  portTo=8
(824,384) turn=4  portTo=8
(808,352) turn=5  portTo=8
(824,352) turn=5  portTo=8
```

The fourth collection advances `0x03000620` from `3` to `4`, immediately after script 5 reports the rusty key. `Fgtile_update` (`0x08003B98`) reads that **same** collection index and branches at the exact threshold:

```text
progress <= 3  -> pre-key path at 0x08003BE6
progress >  3  -> post-key collision/interaction path at 0x0800404A
```

For these `turn=4/5` gate tiles, the machine code proves **gate behavior activation after the rusty-key collection**, and the post-key action is now traced further. While the Player overlaps the gate collision geometry, a **fresh A-button press** dispatches directly by `turn`:

```text
turn=4 -> 0x080042AE -> target X=826, target Y=360
turn=5 -> 0x080042C4 -> target X=826, target Y=410
                         -> call 0x080080A4
```

Player `+0x390/+0x394` are **dual-purpose fields**, not durable generic target slots. Scripted interaction paths temporarily place 24.8 fixed-point anchor X/Y values there, but the Player constructor initializes both to `1`, and normal `Player_update` writes both back to the sentinel value `1` at `0x0800842A`. `0x080080A4` reads only the temporary Y value, writes `anchorY-currentY` to Player `+0x1C`, then clears **both** fields. The X value written by the gate is therefore not consumed by this helper. A static Thumb-BL scan of the recovered low-ROM code finds exactly three callers of `0x080080A4`: `0x08002DD6`, `0x080041C8`, and `0x080042BE`. The first NPC/dialogue path also writes X/Y before calling the same vertical-only helper; another Fgtile path writes only Y=512. Because `0x080080A4` clears `+0x390` before returning, the gate's X=826 write is not available for a later frame through this path.

A **different NPC fresh-A path** at `0x08002FCE` explains why the same two fields sometimes really do carry both axes. It copies actor `dial` (`+0x5C`) to Player `+0x388`, actor X/Y to Player `+0x390/+0x394`, and sets `0x03000610` (`player_interaction_active_flag`) to `1`. `Player_update` (`0x080081B0`) sees that flag at `0x08008BC8`; when Player `+0x1EC == 0`, it enters the full-X/Y bootstrap at `0x0800921A`:

```text
if anchorX >= playerX:
    Player+0x18 = anchorX - playerX - 19px
    Player+0x4C = 1
else:
    Player+0x18 = anchorX - playerX + 19px
    Player+0x4C = 0

Player+0x1C = anchorY - playerY
Player+0x1EC = 1
```

The common motion routine `0x08004670` then collision-tests `+0x18/+0x1C` against the world tile grid and applies permitted components to Player `+0x08/+0x0C`. The intended NPC interaction alignment is therefore **same Y, 19 pixels to one side of the NPC**, with collision resolution still honored. This closes the old `0x08009220` “generic X/Y target mover” hypothesis: it is a specific interaction-alignment bootstrap. See `data/player_npc_interaction_alignment.csv`.

The NPC-side proximity gates feeding those interaction paths are now fully separated as well. `NPC_update` (`0x0800298C`) converts Player and actor coordinates to the same 11-bit-shifted grid, subtracts `0x1000` from actor X/Y (two interaction cells) to form the scan origin, and then uses state-specific rectangles:

```text
state 1 -> social_interaction     -> fixed 5x5 -> fresh A
state 2 -> dialogue_interaction   -> 4x4 when actor+0x4E == 1, otherwise 5x5 -> fresh A
state 4 -> collection_interaction -> fixed 4x4 -> fresh A
```

For all three states, **fresh A** is a real rising-edge test: input bit 0 must be set in `0x030006BC` (`keys_current`) and clear in `0x030006C0` (`keys_previous`). State 1 additionally requires `0x03000610 == 0`; on activation it copies actor `dial` (`+0x5C`) and X/Y into Player `+0x388/+0x390/+0x394`, marks actor `+0x4C`, and sets `0x03000610=1`. State 2 uses the serialized `actor+0x4E` field (exported as `legsColor`) as the only recovered 4×4-vs-5×5 geometry selector; when that field is not 1, the fresh-A path also copies actor X/Y into Player anchors and calls `0x080080A4` for the recovered vertical alignment handoff. State 4 sends the fresh-A contact into the `0x03000620` collection selector and its proven `4,-1,-1,5,6,0` progression. These are therefore **three different A-button proximity interactions**, not automatic collision pickups and not one generic “talk” rectangle. See `data/npc_interaction_geometry.csv`, `disasm/npc_interaction_geometry_0800298C.txt`, and `disasm/npc_interaction_activation_08002D96.txt`.

The next Player interaction layer is now recovered as a **four-way action tree** backed by 20 fixed `0x2C`-byte records at `0x08018738`. The root page is `TALK / FLIRT / ASSAULT / SHARE`, and each root opens exactly four leaves:

```text
TALK    -> SUBJECT / Ask about / JOKE / CRITICIZE
FLIRT   -> KISS CHEEK / KISS LIPS / DIRTY JOKE / BREAKUP
ASSAULT -> SWEAR / FIGHT / unused / SCAM
SHARE   -> GIFT / ACTIVITY / A Number / ASK
```

Player `+0x1E8` stores the current four-record page base and `+0x1E4` stores the selected quadrant. In state 1, fresh `Up / Right / Down / Left` **only select** slots `0 / 1 / 2 / 3`; they do not commit the action. A separate **fresh A** confirmation indexes `base+choice`. Record `+0x20 == 0` means submenu and copies record `+0x24` back to `+0x1E8`, then the state-0 selector bootstrap clears the choice back to 0 for the child page; record `+0x20 == 1` always enters secondary state 2.

State 2 is now bounded closely enough to separate shipped behavior from prototype menu data. **All 16 leaf records enter state 2 after fresh-A confirmation, including the 13 leaves whose `+0x28` count is zero.** `Player+0x1F0` is a real vertical secondary cursor: leaf entry initializes it to `0`, fresh Up decrements it when positive, and fresh Down increments it through the mechanical range `0..8`; either move rebuilds the secondary UI through `0x080074D8` and `0x08006E00`. The builder reads leaf `+0x28` as a **secondary-topic count**. If that count is positive, leaf `+0x24` is the start index into the fixed 15-byte topic-label table at `0x080114B4`; if the count is zero, the builder exits before using `+0x24` as a topic-table index. In this demo only three leaves expose counted lists: `SUBJECT` = `sports / movies / fashion / video games / school / future / parties / last event / mysteries`; `Ask about` = `hobbies / fav. music / best places / fav. meals / dreams`; `CRITICIZE` reuses the same nine-topic list as `SUBJECT`. Of the 13 zero-count leaves, **JOKE is the sole TALK leaf and still commits through the real state-3/150-update follow-up path**. The other **12 leaves under FLIRT / ASSAULT / SHARE are code-proven prototype/inert leaves on fresh A**: page bases `8/12/16` branch through the common Player-update finalizer before the state-3 store, leaving state 2 unchanged. Fresh B calls `0x08009CB6`, plays **SFX7 at volume `0x50`** from `0x08009CCA`, clears page base `+0x1E8` and interaction state `+0x1EC`, and returns through the root-page bootstrap. The unused `+0x24` values on zero-count leaves remain deliberately unnamed because the builder does not consume them as topic indices. See `data/player_interaction_leaf_commit_semantics.csv`.

Two topic-response paths are also code-proven. `SUBJECT` uses 16 fixed 108-byte responses per topic through the pointer table at `0x030007D4`; `CRITICIZE` uses 8 per topic through `0x030007AC`. Both index the selector table at `0x0300110C` with Player `+0x388`, then *expect* a 0..4 topic class at `profile + 4*(topic_index+6)`. Value `2` uses the shared neutral line `I don't really care`; the other valid values select class-specific slots in the topic bank. Their random variant selection is now exact rather than approximated: both call the same generator at `0x08010DAC`, whose initialized 64-bit state is `1` and advances as `state = state * 0x5851F42D4C957F2D + 1`; the returned value is `(state >> 32) & 0x7FFFFFFF`. SUBJECT uses `rand % 4`, CRITICIZE uses `rand % 2`, and an exhaustive low-ROM Thumb-BL scan finds exactly those two calls (`0x0800967E` and `0x08009916`). The first canonical SUBJECT draw is therefore variant `1`. Topic indices 7 (`last event`) and 8 (`mysteries`) deliberately point at the same response bank in this demo. All 216 fixed SUBJECT/CRITICIZE response records are exported verbatim as structured rows in `data/player_interaction_topic_response_texts.csv`; the RNG contract is exported in `data/player_interaction_response_rng.csv`.

The initialized selector table is now recovered exactly, and it proves this social subsystem is only partly coherent in the demo. Selector `0` points to a genuine `0x3C` **Stas** social profile at `0x030010D0`, selector `1` to a genuine `0x3C` **Julia** profile at `0x03001094`, selector `2` is null, and selectors `3..8` point to six incompatible `0x30` NPC metadata/card records (`Stas / IQ 54 / Kate / Kiata / Alex / Evelina`). The two proper profiles each contain nine numeric topic classes: Stas = `3,4,0,2,1,1,3,2,2`; Julia = `1,2,2,0,1,2,4,2,3`. By contrast, applying the runtime topic-class formula to selectors `3..8` yields 54 reads of which only 23 happen to fall in `0..4`; many others are pieces of descriptor text such as `Just` or `Popu`. `0x0800948C` dereferences the selected pointer/topic directly with no null guard before that read.

The malformed entries are now also bounded by **canonical reachability** instead of being treated as equally likely runtime hazards. The only initialized `state=1` NPC records are overlay #5 at `0x08019100` (`dial=0`) and overlay #6 at `0x0801917C` (`dial=1`). NPC update sends only its state-1 proximity success through `0x08002B52 -> 0x08002FA2`; a fresh A then reaches `0x08002FCE`, which copies actor `+0x5C` into Player `+0x388`. Therefore the canonical initialized social path reaches only selectors `0` and `1`, identifying overlay **#5 as Stas** and **#6 as Julia**. NPC update itself reads but does not write actor state `+0x5A` or dial `+0x5C`; selectors `2..8` are best described as **latent prototype defects** under the recovered normal path. External mutation by another subsystem is not ruled out, so exact-parity data should still preserve the table unchanged. See `data/player_interaction_profile_selector_reachability.csv` and the selector-integrity CSV.

A selector-use inventory also closes the current question around proper-profile `+0x10`: both genuine profiles initialize it to zero, and none of the 15 recovered PC-relative loads of selector table `0x0300110C` lead to a proved `+0x10` read. Recovered social code instead uses the profile/name prefix, `+0x14`, and topic slots `+0x18..+0x38`. Use **reserved/unused in recovered interaction runtime** as the working label for `+0x10`; this is a high-confidence absence claim within the recovered selector-use sites, not a whole-program proof. See `data/player_interaction_profile_field_usage.csv`.

The later TALK response dispatcher at `0x08009200` keys **only on Player `+0x1E4` (the quadrant)**: quadrant 0 goes to SUBJECT, quadrant 3 to CRITICIZE, and quadrants 1/2 share the Ask-about/JOKE follow-up path. Crucially, the preceding state-2 fresh-A gate reaches state 3 **only when page base `+0x1E8 == 4` (TALK)**. FLIRT/ASSAULT/SHARE page bases `8/12/16` return from that gate without changing interaction state, so their recovered labels are prototype/inert menu data in the demonstrated runtime—not evidence that those leaves secretly reuse TALK effects.

TALK commitment enters state 3 teardown, clears the menu/interaction scratch, marks Player `+0x381`, and seeds Player `+0x384` with **150**. The response/score dispatcher runs only after that countdown reaches zero on a later update; topic selection itself does not mutate the relationship score or consume response RNG. Immediately before quadrant dispatch, the ROM stores **`Player+0x39C = 10 * profile+0x14`** using the pre-delta score. SUBJECT then applies `profile+0x14 += 2 * (topic_class - 2)`, while CRITICIZE applies the exact inverse `profile+0x14 += 2 * (2 - topic_class)`. Ask about/JOKE skip topic-class lookup and RNG and instead arm Player `+0x382`. An exhaustive recovered reference inventory finds eight PC-relative references to `+0x382`: five reads, constructor/follow-up clears, and **one runtime setter only**—`0x08009214`, reached by response quadrants 1 and 2. That setter has no leaf discriminator, so no distinct Ask-about versus JOKE effect is present in the recovered path. The shared follow-up at `0x0800852E` accepts fresh A, clears `+0x382`, `+0x381`, and interaction state, writes `1` to global `0x03000610`, and nudges `+0x39C` one step toward `10 * current_profile[+0x14]`. No distinct rendering consumer for `+0x39C` is proved, so it remains a **scaled relationship-like score mirror/follower**, not a named visible meter. See `data/player_interaction_social_score_semantics.csv`, `data/player_interaction_score_mirror_semantics.csv`, `data/player_interaction_followup_flag_references.csv`, `data/player_interaction_followup_handshake.csv`, and `data/player_interaction_state_transitions.csv`.

Player `+0x38C` is also a nested interaction-depth counter: submenu confirmation increments it, leaf entry reloads then increments it through the same shared block, and the B-return path decrements it. In state 2, the fresh-A gate at `0x0800960E` reaches state 3 only when depth is positive **and page base is 4 (TALK)**. Page bases 8/12/16 take an internal Player-update exit branch at this gate without changing `+0x1EC`. Fresh B from state 2 is therefore named a **return/back to state 0/root page** here; its SFX7 call and page/state reset are code-proven, while static code still does not prove whether the game-level meaning is cancel, commit, or leaf-dependent. State 3 remains interaction teardown: it resets page/state scratch, clears `0x03000610`, restores scene graphics, and sets Player `+0x381=1`. See `data/player_interaction_action_table.csv`, `data/player_interaction_secondary_topics.csv`, `data/player_interaction_state2_cursor.csv`, `data/player_interaction_leaf_commit_semantics.csv`, `data/player_interaction_topic_response_banks.csv`, `data/player_interaction_topic_response_texts.csv`, `data/player_interaction_runtime_dispatch.csv`, `data/player_interaction_followup_flag_references.csv`, `data/player_interaction_followup_handshake.csv`, `data/player_interaction_profile_target_step.csv`, `data/player_interaction_profile_selector_table.csv`, `data/player_interaction_social_profile_topics.csv`, `data/player_interaction_social_score_semantics.csv`, `data/player_interaction_profile_topic_layout_mismatch.csv`, `data/player_interaction_profile_selector_integrity.csv`, `data/player_interaction_depth_semantics.csv`, and `data/player_interaction_state_transitions.csv`.

The post-key collision geometry is now exact as well. Graveblood converts biased 24.8 coordinates to an 8-pixel grid:

```text
PX = (playerX -  8px) >> 11
PY = (playerY - 24px) >> 11
AX = (actorX  -  8px) >> 11
AY = (actorY  - 16px) >> 11

contact = PX in {AX, AX+1} and PY in {AY, AY+1}
```

On contact, the code sets Fgtile `+0x8C/+0x8D` and Player `+0x1C0`, then tests current-vs-previous A state (`0x030006BC` / `0x030006C0`) for the rising edge. The best machine-level description is therefore a **fresh-A forced vertical gate traversal/reposition**, not a scene portal.

This also resolves the old `portTo=8` ambiguity. The generic Fgtile portal block at `0x08004258` does read actor `+0x52` (`portTo`) and calls `request_scene` (`0x08005C30`), but the post-key `turn=4/5` A-button dispatch jumps straight to `0x080042AE/0x080042C4` and returns through the movement path. **That active gate branch does not read `portTo` or request a scene.** The four records still contain `portTo=8` as metadata, but current code evidence does not use it for the rusty-key crossing.

Machine-readable exports:

- `data/level10_collection_gate_policy.csv`
- `data/level10_gate_forced_motion.csv`
- `data/level10_gate_collision_geometry.csv`
- `data/player_vertical_target_calls.csv`
- `data/player_npc_interaction_alignment.csv`
- `data/state4_collection_progression.csv`
- `data/ending_vram_effect_copy_model.csv`
- `renders/sprites/state4_monster_composite.png`

---

## 9. Player / OBJ graphics pipeline

The Player chain is now anchored:

```text
"player" registration
      ↓
factory       0x08006418
      ↓
constructor   0x0800621C
      ↓
vtable        0x08019688
      ├─ update 0x080081B0
      │    └─ collision-resolved motion 0x08004670
      ↓
draw          0x080065FC
      ↓
dynamic copy  0x08004F04
      ↓
OAM submit    0x0800A8F0
```

A previous working label that called vtable `0x08018AD8` the Player class was wrong. Its vtable is now fully separated as **Grass**: update `0x08002480` is a no-op and draw `0x08002684` submits logical tile `0x48` as a 16x16 sprite. The separate `leaves` factory is `0x08005EE0`; its serialized object has a no-op draw and instead emits transient leaf particles from `Leaves_update` at `0x08005F80`.

### OBJ format

Code and hardware configuration establish:

- 8bpp OBJ graphics: 64 bytes per logical 8×8 tile;
- logical tile N becomes hardware ATTR2 tile index `N*2`;
- tile-argument bit `0x400` = H flip;
- tile-argument bit `0x800` = V flip;
- OBJ mapping is 2D (`DISPCNT` bit 6 clear);
- next 8-pixel column = logical tile +1;
- next 8-pixel row = logical tile +16.

Graveblood's four size enums resolve to:

| Enum | Hardware size |
|---:|---:|
| 0 | 8×8 |
| 1 | 8×16 |
| 2 | 16×8 |
| 3 | 16×16 |

The primary OBJ source begins at `0x08310654`; the low gameplay OBJ color source begins at `0x08366E58`. The span contains **5,536 complete 64-byte source tiles plus a 4-byte remainder** before that color source. The clean-room no longer treats the following region as a flat 256-color palette: the canonical sprite pixels use only indices **0..90**, Title initializes those 91 low colors, and level setup separately reapplies the recovered 32-color patch at OBJ indices **224..255**.

Only the first `0x8000` bytes / 512 logical tiles are initially uploaded. `0x08004F04` dynamically copies later animation tiles into hardware-visible OBJ VRAM slots. Gameplay then applies the recovered time-of-day transform to OBJ entries 0..247 at level entry and amortizes later updates four entries at a time through 248..251; entries 252..255 remain the fixed tail of the high patch.

### Player frame staging

`Player_draw` constructs a 16×32 character from four 16×8 source rows:

```text
ROM source row 0 → dynamic logical row 0x60
ROM source row 1 → dynamic logical row 0x70
ROM source row 2 → dynamic logical row 0x80
ROM source row 3 → dynamic logical row 0x90

OAM 16×16 @ 0x60
OAM 16×16 @ 0x80, Y+16
        ↓
16×32 character
```

The offline renderer independently stages the same OBJ-VRAM data and reproduces known character frames.

**Important caution:** source base `2198` is a known-valid Vika-style 16×32 sample, but v4 does **not** claim it is the constructor/default outfit.

### Player animation bank and frame selection

The normal avatar animation path is now recovered far enough to drive the CFA reconstruction directly. Startup initializes the shared graphics bank at `0x0300103C` to **15**, animation state `0x03001254` to **8**, frame `0x03001258` to **1**, and countdown `0x030012A8` to **5**. Player `+0x1DC` supplies the constructor-proven bank stride of **192 source tiles**.

For bank 15 the normal draw branches select exactly:

```text
states 2..6: 3456 3458 3460 3462 3464 3466   (6-frame regular walk)
state 7:     3520 3522 3524 3526 3528 3530   (6-frame up/back walk)
state 8, selector 0: 3468 3470 3532 3534 3534 3532 3470 3468
state 8, selector 1: 3392 3394 3396 3398 3400 3402 3404 3406
```

Selector 0 mirrors four unique idle poses across eight phases; selector 1 supplies eight additional distinct poses. Across the two six-frame walking banks, four selector-0 idle poses, and eight selector-1 idle poses there are **24 unique 16×32 frames**. The reconstruction now preserves the original **8bpp palette indices byte-for-byte** instead of repacking those pixels into a synthetic 4bpp bank. Right-facing rendering is the original horizontal-flip path; vertical movement keeps the existing horizontal facing instead of resetting it.

The gameplay OBJ palette is dynamic rather than a static shared 256-entry bank. The ROM-initialized lighting clock starts at **48,000**; a 12-slot day/night cycle plus duplicate wrap record interpolates BGR555 target/divisor/contrast parameters. Player update advances an amortized four-entry palette cursor every frame. Dialogue pauses the clock but not that cursor, fresh Player construction resets only the cursor, and Wardrobe keeps the same live lighting cadence/source instead of resetting the palette.

The shared frame counter is not reset when direction/state changes. `Player_update` first advances/clamps the existing frame/countdown, then commits the direction-selected animation state. Normal moving states use a reset countdown of `5`. State-8 idle is selector-dependent: selector 0 reloads `8`, while the level-authored selector-1 bank reloads `5`. This is why Levels 0, 2, 3, 6, 9, and 10 animate the alternate idle bank faster and why the reconstruction preserves timer/frame continuity rather than restarting a cycle on every turn.

`Player+0x1E0` is no longer treated as an unknown/stale-heap selector. Scene activation at `0x08005CFC..0x08005D06` reads the active `LevelRecord+0x3C` and stores it to `Player+0x1E0` **before the first active-scene update**. The canonical Level 0..10 values are `1,0,1,1,0,0,1,0,0,1,1`, so Levels **0, 2, 3, 6, 9, and 10** select the alternate eight-frame idle bank while the others use selector 0. The clean-room `GbLevelAssets.player_idle_selector` now carries that ROM-authored value into the Player runtime; see `data/player_level_idle_selector.csv` and `data/player_sprite_pipeline.csv`.

The hardware submission path is now parity-backed as well. Normal Player and NPC characters are emitted as **two stacked 16×16 OBJ entries** (bottom half first, then top) at `x-cameraX`, `y-cameraY-16/-32`; the previous clean-room `x-8` anchor and single 16×32 submission were approximations. Player uses OBJ priority **2**. NPCs use priority **1** when their world Y is below the Player and **2** otherwise, reproducing the ROM's top-down depth rule. Equal-priority ties now follow the recovered insertion order exactly: story overlays are registered before the physical list, Player occupies its generated per-level physical-list position, and ordinary physical NPCs are registered after Player. The unified gameplay renderer submits OAM in that order instead of globally reserving lower indices for Player, so physical post-Player NPCs remain behind Player at equal priority while pre-Player overlays can correctly appear in front. The fifth-sketch monster also uses priority 2. Levels 9 and 10 additionally draw the recovered **parked bicycle** as a fixed 32×32 four-piece composite from tiles `0x17C/0x17E/0x19C/0x19E` at world `(504,476)` and `(706,884)` respectively, again at priority 2. When shared ride mode `0x030005F4` is 2, Player_draw suppresses that parked composite and instead stages one of six ROM-derived riding frames as **five 16×16 8bpp sprites** at priority 2; the reconstruction reproduces the same composition and restores the ordinary Player OBJ bank when riding ends.

---


### Spawn registry, story-overlay graphics, and evidence-backed identities

The latest ROM's string-driven spawner registry is now code-backed:

| `spawnType` | Factory | Allocation | Runtime implementation |
|---|---:|---:|---|
| `npc` | `0x08003A60` | `0xFC` | NPC / interactive entity, vtable `0x08018B00` |
| `grass` | `0x08002914` | `0x6C` | Grass, vtable `0x08018AD8`; no-op update + 16x16 sprite draw |
| `fgtile` | `0x08003AEC` | `0x90` | interaction/control foreground tile, vtable `0x08018E4C`; draw is a no-op |
| `leaves` | `0x08005EE0` | `0x74` | invisible Leaves emitter, vtable `0x08019660`; spawns transient leaf particles |

The `npc` draw method is `0x0800274C`. Its dynamic graphics source selection is:

```text
sourceBias = [0x030007FC] = startup-initialized 0xE00
sourceBase = sourceBias + legsColor*8 + subtype + 2*(frame-1)
sourceRows = sourceBase + {0,16,32,48}
```

NPC draw also owns the animation clock. `actor+0x78` is the **1-based frame**, `actor+0x7C` is its countdown, and a zero countdown advances/wraps the frame *before* the current draw is staged, then reloads `5 * trunc(8 / actor+0x50)`. `legsColor == 1` branches to the draw epilogue before any of those fields mutate, so those actors are genuinely invisible rather than merely transparent. For state 3, the serialized/base family is preserved at `actor+0xEC`: idle restores `base` with 8 frames, horizontal/down movement selects `base+8` with 6 frames, and upward movement selects `base+16` with 6 frames. Horizontal and diagonal movement also writes the ROM-facing bit; pure vertical/idle keeps the existing facing. See `data/npc_sprite_pipeline.csv` and `data/npc_state_modes.csv`.

Physical NPCs also now follow the inherited spatial-dispatch policy. The common parser's `setglobal` default is **1**, leaving inherited byte `+0x31` clear and allowing the object manager to camera-cull them before `NPC_draw`; because the animation clock lives in draw, offscreen physical NPCs therefore do not advance. Explicit `setglobal=0` story overlays set `+0x31=1` and bypass that spatial gate. Leaves are a deliberate exception: `Leaves_factory` explicitly writes inherited `+0x31=1` even though its `+0x58` policy field is 1, keeping the weather emitter globally active. These distinctions are guarded in `data/new_actor_field_semantics.csv` and `data/npc_sprite_pipeline.csv`.

Startup maps ROM `0x08A8D738` to IWRAM `0x03000788`, so the `0x030007FC` initializer is recoverable at ROM `0x08A8D7AC`. The canonical value is `0xE00`. No direct writer to that field has been identified among the currently traced references, so the workspace calls it an initialized source base rather than claiming immutability.

The destination working rows are determined independently by per-object dynamic-slot fields:

```text
logical OBJ rows =
  0x60 + 2*(24*actor[A4] + actor[A8] + actor[C8])
       + {0x00,0x10,0x20,0x30}
```

This lets the renderer reconstruct standalone story-controlled entities directly from their metadata. It also produced an important semantic correction: the `npc` **runtime class is not synonymous with a human NPC**. Standalone records 11–15 (state 4, subtype 6) render the same paper/sketch-like graphic through that class. The workspace therefore keeps runtime class and narrative identity separate.

The lifecycle of the 16-record block is now code-proven too. `load_level_record_resources` (`0x08005950`) selects one of two startup-initialized overlay slots:

```text
0x0300083C -> 0x08018E94
0x03000840 -> 0x08018E94
```

It passes that selected list to `0x080010A4`, then passes the physical level actor list from `LevelRecord+0x38` to the **same loader**. The new actor policy at `0x080043AC` subsequently applies each overlay record's `level` field. In other words, the Graveblood-era story entities are loaded as a global overlay alongside ordinary map actors and are filtered/activated by level policy; they are not an orphan table. Both selector slots point to the same list in this public demo.

The overlay can now be labeled conservatively from combined runtime + dialogue metadata evidence. One earlier identity claim was intentionally removed: **overlay #4 is not code-proven to be IQ 54**. It is `state=3, route=0`, and the recovered route-follow path uses `actor+0x64` (route), `+0xF8` (waypoint) and `+0xEC` (base sprite family) but does **not** consult `actor+0x5C` (`dial`). Its serialized `dial=2` therefore cannot be used as an identity key. See `data/npc_state3_field_usage.csv`.

- **overlay #0 = unidentified passive visible story actor** (high-confidence role): `state=0`, drawable sprite family; there is no special state-0 interaction branch;
- **overlay #1–3 = unidentified visible dialogue entities** (high-confidence role): each uses `state=2`; their `dial` values choose dialogue scripts but do not by themselves name the underlying actor;
- **overlay #4 = unidentified route-following story actor** (high-confidence role): `state=3`, `route=0`; `dial` is unused by the recovered state-3 path;
- **overlay #5 = Stas** (high confidence): `state=1`, `dial=0`; the only state-1 social bootstrap copies that dial into profile selector 0, whose proper profile name is Stas;
- **overlay #6 = Julia** (high confidence): `state=1`, `dial=1`; the same path selects profile 1, whose proper profile name is Julia;
- **overlay #7–8 = unidentified invisible dialogue hotspots** (high-confidence role): both use `state=2` with `legsColor=1`; state 2 supplies the fresh-A dialogue interaction while NPC draw exits before staging or advancing animation;
- **overlay #9 = IQ 54** (high confidence): level 10, `state=2`, `dial=2`; in state 2 `dial` is the proven dialogue-script index and script 2's speaking NPC is IQ 54;
- **overlay #10 = Katya** (high confidence): `state=2`, `dial=3`; script 3 is Katya's sister/bicycle conversation;
- **overlay #11–15 = five collection pickups** (high-confidence role, not person identity): all use `state=4` and the same paper/sketch graphics family, matching IQ's explicit request to find five sketches.

The remaining unknown names stay **unidentified** rather than being guessed from sprite appearance, duplicate coordinates, or a `dial` field that the active state does not consume. See `data/story_entity_identities.csv`.

Machine-readable exports:

- `data/spawn_type_factories.csv`
- `data/npc_sprite_pipeline.csv`
- `data/npc_state3_field_usage.csv`
- `data/story_entity_sprite_sources.csv`
- `renders/sprites/story_entity_contact_sheet.png`

Implementation guidance for the playable rebuild now lives in `reconstruction/README.md`, `DEVELOPING_AND_BUILDING.md`, and the CFA/devkitPro migration spec under `docs/superpowers/specs/`. The reconstruction follows the original CFA/devkitPro lineage while keeping the canonical ROM RE data as the behavioral source of truth.

---

## 10. Wardrobe browser and preview state — code-backed

The Player constructor still proves the fixed wardrobe-label storage exactly: it copies `0xC8 = 200 bytes` from ROM `0x080198A0` into `Player+0x2B4`, giving **10 slots × 20 bytes**.

| Slot | Literal | Normal Left/Right reachable | Preview OBJ bank | Preview BG page |
|---:|---|:---:|---:|---:|
| 0 | `Favorite Skirt` | yes | 15 | 6 |
| 1 | `Not for demo` | yes | 13 | 2 |
| 2 | `Not for demo` | yes | 12 | 1 |
| 3 | `Not for demo` | yes | 11 | 0 |
| 4 | `Not for demo` | yes | 6 | 3 |
| 5 | `Not for demo` | yes | 4 | 4 |
| 6 | `Not for demo` | yes | 5 | 5 |
| 7 | `Not for demo` | no | — | — |
| 8–9 | empty | no | — | — |

The actual browser selector is **`Player+0x240`**, initialized to `0` by the Player constructor. The standalone helper at `0x08006430` draws the selected label using the code-proven formula `Player+0x2B4 + selector*20`. The previously labeled `0x08008E30` “Wardrobe function” is not a function entry at all: it is an internal Wardrobe presentation path inside `Player_update` (`0x080081B0`).

Normal browser input is **Left / Right / B**. Starting from constructor state, Left/Right can reach selectors `0..6`; the path at `0x080093F4` that writes `7` is a defensive clamp for an already-high value, not a seventh Right step. The hidden entry path is also code-proven: `0x08008318..0x0800831C` requires the current held-key value to equal **`0x0006` (B+SELECT)** exactly. Fresh B exits by requesting **Gameplay Level 7, variant 0**. No A-button confirmation/equip path is present in the recovered browser control flow.

The CFA reconstruction now implements this exact **browse/preview-only Wardrobe scene**. Gameplay movement, actors, story interactions, and portals are suspended while it is active; selector 0 is restored on entry; the seven canonical BG pages and seven 16x32 8bpp preview figures are loaded from checked-in ROM-derived data; and leaving the browser reloads Level 7 through the normal gameplay loader.

The constructor also copies two 14-dword preview tables:

- `Player+0x244 <- ROM 0x080197B0`: first group `15,13,12,11,6,4,5`; second group is seven zeroes. The Wardrobe preview loop consumes these as dynamic OBJ source-bank selectors.
- `Player+0x27C <- ROM 0x080197E8`: normal selector pages `6,2,1,0,3,4,5`. The selected value feeds `0x08004F6C`, which copies one `0x2000`-byte page into BG VRAM at `0x06003000`.

This also corrects an older state-label mistake. **`0x03001254` is the Player animation state/frame block**, not shared Wardrobe state. The live gameplay graphics-bank global is **`0x0300103C`**, initialized to `15`; its two direct canonical-ROM literal references are both read-only Player drawing paths. No recovered Wardrobe path writes that live bank. The public demo therefore proves a **browse/preview interface, not a gameplay equip action**.

For reconstruction parity, alternate `Not for demo` preview banks remain preview-only. The CFA runtime keeps the proven startup/default outfit and does not make those choices gameplay-selectable without new evidence. The previously provisional SFX11-navigation label is rejected: its call sites `0x0800898E` and `0x0800904E` are outside the selector Left/Right branches, so Wardrobe navigation is intentionally silent.

Machine-readable exports:

- `data/wardrobe_labels.csv` — raw 10×20-byte label slots (including ROM padding);
- `data/player_wardrobe_state_semantics.csv` — selector, navigation, preview tables, corrected global roles, and no-equip result;
- `data/player_wardrobe_slots.csv` — normalized per-slot reachability and preview mapping;
- `data/wardrobe_runtime_assets.csv` — canonical per-selector BG/OBJ source addresses, sizes, and SHA-256 hashes;
- `data/player_sprite_pipeline.csv` — Player graphics/animation anchors;
- `data/obj_graphics_summary.csv` — OBJ bank/hardware summary.

---

## 11. Alpha differential results

`tools/match_alpha_latest.py` performs exact-byte fingerprint matching over the executable regions while validating both ROM hashes.

Current result:

- **109 exact shared blocks**;
- **22,605 bytes** summed across non-exclusive matches;
- largest exact block: **1,537 bytes**.

Dominant address-shift clusters include:

- `-0x10`
- `+0x65A0`
- `+0x76A0`
- `+0x7AFC`

These clusters are useful for finding inherited functions separated by blocks of newly inserted Graveblood code. Exact matching is intentionally conservative: relocated branch/literal instructions can split otherwise homologous functions.

The alpha is never used to populate canonical latest-ROM level/actor/dialogue exports.

---

## 12. Rendered artifacts

`renders/maps/` contains:

- final corrected composite world renders for all 13 graphics variants;
- matching actor/portal overlay renders;
- `world_contact_sheet.png`;
- `actor_contact_sheet.png`;
- `render_summary.csv`;
- `runtime_alias_summary.csv` — all 81 classified runtime screenblock-alias classes (1,689 world cells), including the Level-2 palette-overrun aliases.

The large raw layer-A/layer-B PNGs are **not bundled** to keep the ZIP smaller; `tools/render_maps.py` regenerates them exactly.

`renders/sprites/` contains:

- `obj_source_atlas.png` — all 5,536 complete source tiles;
- `character_source_2198.png` — known-valid character frame sample, no default-outfit claim;
- `player_branch_candidate_3468.png` — legacy-named reference image for the proven selector-0 idle source 3468;
- `grass_logical_tile_0x48.png` — exact 16x16 Grass sprite evidence;
- `leaf_particle_frame_0x4C.png`, `0x4D`, `0x5C`, `0x5D` — the four recovered 8x8 transient leaf-particle frames;
- `sprite_summary.json`.

The bright palette-zero regions visible in some map renders reflect the ROM's selected BG palette/base fill in the offline composition; the renderer does not invent replacement scenery for runtime/dynamic cells.

---

## 13. Reproducing the extraction

Requirements:

- Python 3;
- Pillow for image rendering;
- `clang` + `llvm-objdump` for focused disassembly snapshots when available, or Python `capstone` as the fallback disassembler.

Set the canonical ROM path:

```bash
export GRAVEBLOOD_ROM="/path/to/Graveblood 0.0.1.1.5.2 demo.gba"
```

Regenerate canonical structural data:

```bash
python3 tools/extract_structure.py "$GRAVEBLOOD_ROM" --out data
python3 tools/extract_extended_semantics.py "$GRAVEBLOOD_ROM" --out data
python3 tools/extract_foreground.py "$GRAVEBLOOD_ROM" --out .
```

Regenerate maps:

```bash
python3 tools/render_maps.py "$GRAVEBLOOD_ROM" renders/generated_maps --actors data/actors.csv
```

`render_maps.py` emits layer A, layer B, final composites, actor overlays, `render_summary.csv`, and `runtime_alias_summary.csv`. The latter distinguishes runtime screenblock self-aliases from genuinely static character data instead of labeling them unresolved. v4 packages all of those layer/composite/overlay renders plus contact sheets so each hardware world layer can be inspected independently.

Run all regressions:

```bash
GRAVEBLOOD_ROM="$GRAVEBLOOD_ROM" \
python3 -m unittest discover -s tools -p 'test_*.py' -v
```

To regenerate alpha differential data separately:

```bash
python3 tools/match_alpha_latest.py \
  "$GRAVEBLOOD_ROM" \
  "/path/to/Graveblood Pre Pre Pre Alpha.gba" \
  --out data
```

Every canonical extractor rejects a ROM with the wrong SHA-256 unless the explicitly debug-only override in `extract_structure.py` is used.

---

## 14. Important files

### Data

- `data/levels.csv` — corrected level overview.
- `data/level_runtime_structs.csv` — all 0x40-byte level fields with runtime dimensions.
- `data/level_graphics_descriptors.csv` — primary graphics descriptor per level.
- `data/level_graphics_variants.csv` — all 13 variants.
- `data/level_world_layers.csv` — source pointers and layer statistics.
- `data/collision_summary.csv` — collision/world-grid summaries.
- `data/level6_collision_visual_alias.csv` — code-proven closure of Level 6's intentional `+0x0C` collision / `+0x10` visual-B source-data alias.
- `data/actors.csv` — all 267 serialized level actor records (including 10 Player descriptors).
- `data/portal_edges.csv` — code-proven physical transition records.
- `data/player_direct_scene_transitions.csv` — non-Fgtile Player-owned scene requests, including the hidden Level-9→10 boundary.
- `data/world_progression_graph.csv` — composed gameplay transition graph: 33 Fgtile edges + the direct Player boundary, with movement-only gates excluded.
- `data/standalone_spawners.csv` — raw 16-record Graveblood-era story-overlay block.
- `data/npc_state_modes.csv` — recovered behavior modes with state 1/2/4 promoted to social/dialogue/collection interactions.
- `data/npc_fixed_point_runtime.csv` — 24.8 actor-position storage, 8-pixel route/interaction grid conversions, and the shared special-NPC timer contract.
- `data/npc_special_movers.csv` — the unique `legsColor=40` mover plus all 22 `legsColor=112` proximity-latched movers, with exact timer/SFX/motion semantics.
- `data/actor_system_inventory.csv` — family counts and factory/constructor/update/draw/vtable addresses, including the 105-NPC split into 89 physical records + 16 story overlays.
- `data/npc_interaction_geometry.csv` — exact state 1/2/4 grid rectangles, fresh-A rule, actor-origin bias, and state-specific activation effects.
- `data/spawn_type_factories.csv` — code-proven `npc/grass/fgtile` factory registry.
- `data/foreground_actor_semantics.csv` — separated Grass/Fgtile/Leaves/leaf-particle vtables and code-proven draw/update behavior.
- `data/camera_runtime_semantics.csv` — exact Player body-center camera target, X/Y dead-zones, viewport clamp, stream origin, and scene-transition persistence proof.
- `data/leaves_emitter_semantics.csv` — exact shared cooldown/cycle globals, offsets, camera threshold, spawn equations, particle frames, and constructor.
- `data/leaves_level_usage.csv` — per-level Leaves presence and camera-range reachability of the X>2000 emitter gate.
- `data/npc_sprite_pipeline.csv` — NPC source/destination dynamic-OBJ formula and evidence.
- `data/story_entity_sprite_sources.csv` — exact source rows selected for all 16 standalone records.
- `data/story_entity_overlay_slots.csv` — two startup overlay selectors, actor-list loader, and level-gate chain.
- `data/story_entity_identities.csv` — conservative evidence-backed identities/roles for the 16 overlay records.
- `data/dialogue_context_semantics.csv` — authoritative normal-vs-state4 opcode semantics.
- `data/state4_collection_progression.csv` — six-step state-4 selector (`4,-1,-1,5,6,0`).
- `data/level10_collection_gate_policy.csv` — code-proven pre-key/post-key branch threshold for the four level-10 gate tiles.
- `data/level10_gate_forced_motion.csv` — exact post-key fresh-A turn 4/5 target coordinates, Player offsets, helper behavior, and separation from generic `portTo`.
- `data/level10_gate_collision_geometry.csv` — exact 8-pixel-grid overlap formulas and contact flags for the post-key gate.
- `data/player_vertical_target_calls.csv` — all three recovered static callers of `0x080080A4`, including which temporary anchor fields each caller writes and the helper's X-discard/Y-consume behavior.
- `data/player_npc_interaction_alignment.csv` — fresh-A NPC source path, interaction-active flag/state-0 dispatch, exact ±19 px X alignment equations, Y alignment, and collision-resolved motion handoff.
- `data/player_interaction_action_table.csv` — all 20 four-way interaction records, root-to-child page links, visual selectors, and conservatively raw leaf payload fields.
- `data/player_interaction_profile_selector_table.csv` — exact nine-entry social selector table: two real `0x3C` profiles, one null slot, and six incompatible `0x30` metadata/card pointers.
- `data/player_interaction_profile_selector_reachability.csv` — canonical state-1 actor/dial reachability proving selectors 0/1 are the normal initialized social path; selectors 2..8 remain latent unless externally mutated.
- `data/player_interaction_profile_field_usage.csv` — recovered selector-derived profile-field inventory, including the absence of a `+0x10` consumer in the recovered interaction runtime.
- `data/player_interaction_social_profile_topics.csv` — the nine valid 0..4 topic ratings for the genuine Stas and Julia social profiles.
- `data/player_interaction_social_score_semantics.csv` — delayed SUBJECT/CRITICIZE topic-class score updates after the 150-update post-interaction countdown, including the inverse CRITICIZE formula.
- `data/player_interaction_score_mirror_semantics.csv` — direct `Player+0x39C = 10 * profile+0x14` synchronization plus the later one-step follower behavior.
- `data/player_interaction_profile_topic_layout_mismatch.csv` — all 54 wrong-layout topic reads for selectors 3..8, including ASCII overlap and valid-class accidents.
- `data/player_interaction_profile_selector_integrity.csv` — compact parity warning/counts plus the unguarded response dereference site.
- `data/player_interaction_state_transitions.csv` — code-proven state 0→1 setup, state-1 directional choices, branch/leaf confirmation, state-2 B return/back transition, and state-3 teardown.
- `data/ending_vram_effect_copy_model.csv` — exact byte-count equations/source biases/destinations for the final `0x08004FE0` effect.
- `data/ending_vram_effect_runtime.csv` — exact opcode-entry + Player_update threshold/reset/repeat gate for `0x03000674/0x03000678`.
- `data/ending_effect_argument_writes.csv` — exact direct Player-update writes to `0x03000674`: `0x080081D0` +20 above 1000 and `0x080088AA` reset to zero at/below 1000.
- `data/ending_effect_alias_write_closure.csv` — exhaustive executable Thumb immediate-store alias inventory for the ending argument and event flag; proves no hidden >1000 seed and no post-boot flag writer besides the final-sketch setter.
- `data/ending_effect_boot_lifetime.csv` — startup zero-fill proof for both ending globals plus the absence of scene-transition calls to the boot zero helper.
- `data/ending_effect_static_reachability.csv` — high-confidence closure from boot value 0: only argument 0 is reachable, the >1000 branch is dormant, and the event flag stays latched until reboot.
- `data/ending_vram_effect_level10_sources.csv` — exact Level-10 argument-0 source addresses/ranges, including the 9,157-byte SFX13 overlap in copy 1.
- `data/npc_routes.csv` — five six-waypoint routes.
- `data/dialogue_scripts.csv` — all 58 decoded dialogue records.
- `data/dialogue_opcode_semantics.csv` — normal-context compatibility opcode view.
- `data/message_streams.csv` / `message_selectors.csv` — inbox/progression data.
- `data/wardrobe_labels.csv` — ten fixed Player wardrobe-name slots, byte-faithful to the ROM.
- `data/player_wardrobe_state_semantics.csv` — code-backed browser selector, navigation, preview tables, corrected global roles, and no-equip result.
- `data/player_wardrobe_slots.csv` — normalized per-slot reachability and preview OBJ/BG mappings.
- `data/obj_graphics_summary.csv` — OBJ bank/hardware summary.
- `data/player_sprite_pipeline.csv` — code-backed Player graphics anchors and caveats.
- `data/player_animation_semantics.csv` — startup animation values, exact bank-15 frame sources, cadence, flip behavior, and the bounded `+0x1E0` caveat.
- `data/player_motion_collision_contract.csv` — ROM-guarded fixed8 Player position/request fields, 16×16 collision body, normal ±1px D-pad requests, tile-14/status behavior, corner-slide rules, and the PDA-only solver gate.
- `data/player_controller_modes.csv` — dedicated `0x03000624` controller-mode inventory: normal mode 0 plus the Level-10 scripted entrance modes 5/6; PDA/social/Wardrobe state machines are deliberately excluded.
- `data/crossbuild_matches.csv` / `crossbuild_summary.json` — alpha differential.
- `data/audio_samples.csv` — all 14 canonical PCM table entries, exact lengths, roles, durations, and SHA-256 hashes.
- `data/audio_call_sites.csv` — exhaustive one-shot/loop/channel-control call sites. All 30 one-shot calls to `0x08001B74` now have code-bounded high-confidence semantics; there are no remaining medium-confidence one-shot rows.
- `data/audio_one_shot_closure.csv` — machine-readable closure invariant: 30/30 high-confidence one-shot calls, 0 medium, reachable one-shot IDs `3..13`.
- `data/pda_menu_pages.csv` — exact four-state PDA top-level selector (`MESSAGES / STATUS / FRIENDS / BACKPACK`) and L/R bounds used by SFX11.
- `data/pda_runtime_semantics.csv` / `pda_page_render_sources.csv` / `pda_cursor_semantics.csv` / `pda_friends_entries.csv` — exact PDA open/page/render/local-navigation evidence and the six recovered FRIENDS entries.
- `data/audio_music_routes.csv` — code-proven gameplay music-selector routes; sample 2 is code-proven unreachable/orphaned in the public demo.
- `data/title_scene_semantics.csv` — recovered title descriptor/map/animation/prompt/START-transition timing and evidence.
- `data/graveblood_001152.sym` — working symbol map.

### Focused disassembly

- `disasm/wardrobe_label_draw_08006430.txt` — selected-label helper, including `Player+0x240` × 20 addressing into `Player+0x2B4`.
- `disasm/wardrobe_player_update_path_08008DF0.txt` — internal `Player_update` Wardrobe browser path: title/prompt, preview loaders, navigation, and exit flow.
- `disasm/npc_interaction_geometry_0800298C.txt` — NPC state dispatch plus state 1/2/4 proximity rectangle construction/scan loops.
- `disasm/npc_interaction_activation_08002D96.txt` — state 2/1/4 fresh-A gates and their activation handoffs.

### Tools

- `tools/extract_structure.py` — canonical structural extractor.
- `tools/extract_extended_semantics.py` — routes/messages/states/wardrobe/OBJ semantics.
- `tools/extract_wardrobe_runtime.py` — deterministic seven-choice Wardrobe preview asset extraction.
- `tools/extract_foreground.py` — canonical Grass/Fgtile/Leaves/leaf-particle behavior and level-usage extractor.
- `tools/match_alpha_latest.py` — alpha↔latest exact fingerprint matcher.
- `tools/render_maps.py` — corrected 8bpp world renderer.
- `tools/render_sprites.py` — OBJ/OAM dynamic Player/NPC renderer library, including story-entity contact-sheet generation.
- `tools/disasm_thumb_chunk.py` — focused Thumb disassembly helper.
- `tools/extract_audio.py` — canonical 14-entry PCM extractor plus audio call-site/routing evidence exporter.
- `tools/extract_title_scene.py` — canonical Title scene map/tile/palette/animation/prompt extractor plus scene evidence exporter.
- `tools/extract_pda.py` — canonical four-page PDA map/control/content extractor plus generated runtime assets.
- `tools/test_*.py` — current ROM-backed regression suite (**244 tests** at this package checkpoint).

---

## 15. Current reconstruction boundary / next high-value targets

This workspace is **not** a decompiled source tree yet. It is a verified structural/semantic foundation for one.

The canonical audio subsystem is now reconstructed as well: all **14 original PCM resources** are byte-exact checked-in assets, the runtime has the recovered **8-channel 16,384 Hz** signed-PCM mixer with FIFO A/DMA1/Timer0/Timer1 double buffering, normal Levels 0–9 route to music ID 0, and Level 10 routes to music ID 1. The static one-shot call graph is now **closed**: an exhaustive full-ROM Thumb BL scan finds **30 calls to `0x08001B74`, all 30 high-confidence and zero medium-confidence**. SFX3 covers the first accepted state-2/state-4 text page when dialogue latch `0x0300062C` is zero plus the now-bounded **hit/death burst** constructor; SFX4 covers successful PDA FRIENDS movement, PDA `MESSAGES` cursor movement, and the now-bounded **latent projectile** constructor; SFX5 covers generic Fgtile/scene-portal activation; SFX6 covers both Title START and fresh-START PDA opening; SFX7 covers normal dialogue opcodes `-1..-4`, state4 terminal opcodes `-1/-2/-3`, the PDA return-to-gameplay transition, and the fresh-B state-2 interaction return/back path. SFX8 is the subsequent state-2/state-4 text-page sound while dialogue latch `0x0300062C` is already nonzero; SFX9 is the `legsColor==0x70` NPC proximity-latch activation; SFX10 is the fresh-R **bicycle-mode** action at volume `0x1E`, reachable only while shared ride state `0x030005F4 == 2`; SFX11 is strictly PDA top-level tab switching across `MESSAGES / STATUS / FRIENDS / BACKPACK`; SFX12 is PDA FRIENDS top/bottom boundary feedback; SFX13 is the final-sketch state4 `-5` transition. The two formerly opaque effect-object classes are now behaviorally closed under deliberately technical names: the SFX4 class is a 1x1 fixed8 **latent projectile** with velocity, a `0x5000` max-axis travel budget, map/object collision, a slot-`+0x1C` hit dispatch carrying argument 60, and an 8x16 priority-1 active/terminal sprite (`0x126`/`0x124`); the SFX3 class is a 32x32 **hit/death burst** with four eight-update visual phases (`0x127/0x128/0x12A/0x12C`) and optional hit propagation. Static reachability closes the subsystem as dormant in the public demo: the projectile constructor has no direct Thumb branch/call or literal pointer root, the burst is directly constructed only by Player/NPC hit callbacks, both live burst calls pass propagation argument 0, and the only recovered slot-`+0x1C` dispatch roots are that unrooted projectile plus the disabled optional burst propagation. Their original developer/narrative names remain unknown, so the clean-room runtime intentionally does not invent a projectile spawn path. Music ID 2 is preserved as canonical data but is code-proven **unreachable/orphaned in the public demo**: the exhaustive ROM scan finds only three loop-player calls, reachable selector values are 0/1, and no direct one-shot or loop call targets ID 2. The one-shot entry point consumes only `(sound_id, volume)`, while the looping entry point consumes `(sound_id, mode, volume)`; gameplay music uses mode 2 and volume `0x90`. The exact 75-word fade table is relocated from ROM `0x08A8E370` to runtime `0x030013C0`, including the original counter-75 one-word-overrun lookup immediately before channel replacement.

The public-demo Wardrobe selector/preview path is now executable as the hidden B+SELECT browse-only scene, and the state 1/2/4 NPC interaction rectangles, dialogue contexts, collection selector, and rusty-key gate are executable in the clean-room runtime. The recovered `0x080080A4` vertical-target helper is no longer represented as a teleport: Level-10 turn=4/5 gates, the Level-9 `treetype=20` action, and aligned state-2 dialogue interactions queue `targetY-currentY` into the fixed8 collision request and use the dual-purpose Player `+0x390/+0x394` reset latches so the request survives exactly one normal motion resolution. State-1 social activation also collision-resolves the code-proven full-X/Y bootstrap before opening the selector, ending on the NPC's Y exactly 19 pixels to the appropriate side. Scene changes now use the recovered queued handoff instead of immediate swaps: generic gameplay portals and Wardrobe→Level7 use delay 10, while Title START keeps its exact 120-update delay. The composed gameplay graph contains **34 transitions** (33 Fgtile edges plus the hidden Player-owned Level9→10 boundary), and every Level 0–10 is reachable from Title's Level7 destination. The Level9 boundary sets scripted Player mode 5; after Level10 loads, the recovered entrance drives +370 fixed8 X until the >700/>350 handoff, snaps Y to 870, then mode 6 climbs at -256 fixed8 until Y reaches 780 before normal control resumes. The CFA reconstruction uses the recovered **BG0/BG1/BG2/BG3** layout across **all 11 levels / 13 graphics variants**, loads 241 unique non-Player physical descriptors / 290 level references plus 16 story overlays, renders the recovered NPC/story animation banks with ROM cadence and state-3 directional family switching, follows state-3 routes through queued shared-collision motion, and consumes typed state 1/2/4 interaction events through `GbStoryRuntime`. The runtime now executes all **7 dialogue scripts / 58 records** with context-specific opcode handling, the two canonical Stas/Julia social profiles and recovered response tables, the six-step sketch/key sequence, primary/auxiliary message selectors, persistent consumed story pickups, canonical CFA-font BG0 dialogue/social presentation, the five-sprite monster transition, and the special Level-10 post-key traversal to Y=360/410. The state4 `-5` effect executes the exact statically reachable argument-0 VRAM blast while `final_effect_pending` remains latched. Step-4 closure proves startup seeds the argument to 0, exhaustive executable alias-write analysis finds no writer capable of seeding it above 1000, and scene transitions neither reset nor reseed the state; therefore the larger branch is dormant from a normal public-demo boot rather than merely unsupported by convention. The Level-9 `treetype=20` Fgtile is also executable as its recovered fresh-A bicycle mount: exact 2x2 contact geometry, queued Y=512 alignment, shared ride mode 2, six-frame/five-sprite riding render, parked-bicycle suppression, and fresh-R SFX10 at volume 30 are all reproduced; ride mode survives the Level9→10 boundary and is cleared at the recovered Level10 mode-5→6 handoff. It is no longer misclassified as scene destination 524. A separate static closure now resolves the same ROM word `0x030005F4` beyond the bicycle path: original value-1 draw/update code still exists at `0x08006818/0x08006A66/0x08008A5C`, but boot initializes the word to 0 and the only resolved executable writers produce 2 or 0, so value 1 is dormant from a normal public-demo boot and no clean-room entry path is invented. Normal Player mode now uses the ROM-proven 24.8 fixed-point position/request fields and direct cardinal ±0x100 requests rather than the older integer-step approximation. Standalone fresh **SELECT** is also now closed rather than guessed: Player construction seeds `Player+0x1BC=11`, each accepted fresh SELECT while the value is above 3 decrements it once, and the post-decrement `BL 0x0800851C` is an internal long transfer into the common Player-update continuation. It does **not** return to the adjacent `0x080090C4` state-12/vector block; that block has its own incoming transfer from `0x08008708`. Exact access closure finds no render/audio/motion/interaction consumer of `Player+0x1BC` beyond this guard/decrement path, so the clean-room runtime intentionally leaves standalone SELECT visually/gameplay-inert instead of inventing a dash or movement action. See `data/player_select_counter_closure.csv`. The clean-room `0x08004670` collision model uses the constructor-proven 16×16 body, 8-pixel collision cells, tile-14 horizontal status 7/11 blocking, vertical center status `0x31/0x51`, exact ±1px axis-only corner correction, diagonal carry-through, double-corner restore, and pre-motion side-probe rows. The solver's `0x03000618` gate is documented but intentionally omitted from normal physics because it is the PDA invalid-page return-pending byte and ordinary gameplay does not set it. Story-overlay startup policy is now closed: both overlay slots point to the same 16-record list, and initial visibility is level-or-wildcard gated rather than progression-swapped; persistent consumption still applies afterwards. The clean-room runtime now implements the public-demo PDA: exact four-page chrome, START open/reopen, bounded L/R tabs, MESSAGES primary/auxiliary stream selection, the six-entry FRIENDS three-row window, STATUS/BACKPACK header-only behavior, and the latent invalid-page return helper. No ordinary close key is bound because the ROM does not prove one. Grass/Leaves foreground rendering is now executable: Grass uses the exact canonical 16x16 sprite with original H-flip/depth rules; Leaves uses the recovered persistent cooldown/cycle globals and emits exact four-frame 8x8 transient particles, effectively visible only in the far-right portion of Level 9 where camera X can exceed 2000. Leaves emission now runs at serialized physical slot 0 and newborn particles receive their first velocity update in the same manager traversal. Fgtile remains intentionally non-rendering because its draw method is literally a no-op, while its ordinary turn-0/1 control path now performs the recovered descriptor-driven BG-VRAM graphics hot-patches. The first hardware-validation layer is now automated. `tools/test_hardware_address_runtime.py` maps the literal GBA MMIO/palette/VRAM/OAM regions into isolated Linux host processes and executes the production input, audio, video, actor/foreground, VBlank, and ending-effect paths against those real addresses; it also cross-compiles all 43 C units plus both `.incbin` assembly units for ARM7TDMI Thumb and reloc-links them as ARM. This has validated literal register widths/addresses, active-low input, FIFO-A/DMA1/timer setup, Mode-0/OAM/OBJ placement, Player/NPC/Grass/leaf dynamic OBJ submission, and the argument-0 VRAM boundary without finding a new production mismatch. The existing ROM-backed runtime suites continue to cover fixed8 collision/corner behavior, Level9→10 scripted entrance, Title/PDA/Wardrobe state timing, and foreground state machines. The repository retains three validation layers without coupling them to publication: `tools/validate_gba_rom.py` checks cartridge identity/header checksum, `tools/run_mgba_smoke.py` can perform a bounded normal-ROM boot test, and the optional `Graveblood_RE_selftest.gba` / `Graveblood_RE_device_test.gba` builds exercise seven scenario-level hardware contracts. The ending-effect check now matches actual GBA VRAM semantics: the original unaligned byte-copy mirrors bytes only in BG VRAM and its byte stores are ignored in OBJ VRAM, while the aligned second copy remains byte-exact. The self-test also writes its PPU probe pixels and OBJ-VRAM guard values with legal 16-bit stores. These diagnostic cartridges and screenshots are no longer published by GitHub CI. `.github/workflows/build-release-rom.yml` runs the ROM-independent CI regression gate and normal cartridge build/validation on ordinary branch pushes and pull requests, then uploads only the validated normal `Graveblood_RE.gba` as the short-lived `Graveblood_RE-rom` Actions artifact. `Graveblood_RE_v*-dev` tags use a second job that downloads that exact validated artifact and publishes exactly one versioned `.gba` GitHub Release asset without rebuilding it. ROM-backed parity tests remain available locally when the canonical demo is supplied via `GRAVEBLOOD_ROM`.

### Confidence policy

This workspace intentionally separates:

- **proven machine behavior** — directly supported by traced code/data;
- **working names** — useful conservative labels whose original developer names are unknown;
- **candidates** — plausible interpretations that still need another proof step.

That distinction matters if this work later becomes the basis for a finished Graveblood reconstruction: recovered facts should not quietly turn into invented “original” design.

## Interactive runtime parity checkpoint (2026-09-14)

A direct comparison of the playable reconstruction against the public-demo ROM exposed several interaction/presentation gaps that isolated BG/OAM asset audits did not catch.  This checkpoint therefore treats the uploaded playable ROM and the canonical `0.0.1.1.5.2` demo as the acceptance target for the interactive shell.

The runtime now restores four ROM-backed behaviors together:

- **PDA START return:** pressing START while the PDA is already open exits back to gameplay through the existing return path and SFX 7 instead of reopening/resetting the PDA.
- **Normal dialogue window:** normal dialogue uses the recovered `(1,13)` 20x6-tile window, with an 18x4-tile text interior and the original BG border tiles 3/4/5 plus hardware flip bits.  Speaker text occupies its own line before body text.
- **Gameplay OBJ lighting skip ranges:** the palette-lighting pass leaves OBJ pair 4/5 and every pair starting above 199 untouched.  The reference branches around the OBJ write for these ranges; treating the level BG palette as a substitute OBJ source incorrectly recolored Player pixels.
- **Physical NPC fresh-A interaction:** state 1/2/4 interaction emission is performed by the NPC at its serialized physical update slot.  The earlier physical-order refactor had preserved NPC motion but accidentally left interaction scanning in the obsolete bulk updater, so many normal NPCs could animate but never talk/socialize/collect.

The Player sheet itself is not replaced in this checkpoint: the packed 24-frame sheet, initial bank-15 selection and initial source frame are already reference-derived.  The proven live Player presentation correction here is the OBJ-lighting skip behavior above.  Further appearance differences should be diagnosed from actual runtime state rather than by swapping artwork blindly.
