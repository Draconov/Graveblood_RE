# Graveblood_RE

Unofficial fan reverse-engineering and reconstruction project for Graveblood, a game by Cojam.

This repository documents and reproducibly extracts structures from the **canonical latest public demo ROM**.

## Buildable clean-room reconstruction

`Graveblood_RE` includes a separate `reconstruction/` Butano project that builds a new GBA ROM from source without using the original ROM as a build input. The current ROM is deliberately a minimal development shell; it proves the toolchain and CI/release path before recovered gameplay is implemented.

Start here:

- `DEVELOPING_AND_BUILDING.md` — Windows/macOS/Linux setup, pinned Butano checkout, build, emulator/hardware testing, and release tags.
- `reconstruction/` — clean-room C++/Butano project.
- `.github/workflows/build-release-rom.yml` — CI build artifacts plus `Graveblood_RE_v*-dev` tagged GitHub releases.

The reconstruction currently outputs `reconstruction/Graveblood_RE.gba`. It should not be confused with the canonical demo ROM documented by the RE tools.

Development releases use tags such as `Graveblood_RE_v0.0.1-dev`; GitHub Actions publishes the versioned ROM asset as `Graveblood_RE_v0.0.1.gba`.

---

## 1. What this repository contains

The workspace includes:

- a buildable clean-room Butano reconstruction shell under `reconstruction/`;
- local development/build/release instructions plus GitHub Actions ROM artifacts/releases;
- canonical ROM/header metadata;
- 11 corrected 0x40-byte level records;
- runtime-patched level dimensions;
- 13 graphics descriptors/variants;
- map/world-layer and collision summaries;
- 267 decoded actor records;
- 38 physical portal records;
- 16 code-proven story-overlay entity records loaded alongside every physical level actor list;
- 7 dialogue scripts / 58 fixed records;
- context-sensitive normal-vs-state4 dialogue opcode semantics;
- six-step state-4 collection selector, including rusty-key and fifth-sketch transitions;
- conservative story-entity identity export (IQ 54, Katya, and five collection pickups);
- decoded message/progression streams;
- five NPC routes / 30 waypoints;
- NPC state-mode semantics and exact NPC dynamic-sprite source formula;
- Player/OBJ rendering pipeline evidence, story-entity sprite reconstruction, and executable five-sprite monster composite;
- 10 fixed wardrobe-name slots copied by the Player constructor;
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
+0x3C  unknown flag
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

`data/level_runtime_structs.csv`, `data/level_world_layers.csv`, and `data/collision_summary.csv` expose these structures in machine-readable form.

---

## 3. Background graphics pipeline

The latest demo configures four **8bpp / 256-color text backgrounds** at `0x0800A208`:

| BG | CNT | Priority | Screenblock | Proven runtime role |
|---|---:|---:|---:|---|
| BG0 | `0x1B80` | 0 | 27 | fixed screen-space text/UI plane |
| BG1 | `0x1C81` | 1 | 28 | streamed world layer A |
| BG2 | `0x1D82` | 2 | 29 | streamed world layer B |
| BG3 | `0x1E83` | 3 | 30 | quarter-speed parallax |

Gameplay update `0x08004B74` applies:

```text
BG0 scroll = (0, 0)
BG1 scroll = (cameraX, cameraY)
BG2 scroll = (cameraX, cameraY)
BG3 scroll = (cameraX / 4, cameraY / 4)
```

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

The engine's `0x0800A330` does **not** impose an artificial 2048-entry bound on the translation lookup. Level 2 contains source IDs above 2047. Mirroring the machine's raw halfword address arithmetic reduces exporter failures from 51,164 cells to four genuinely unresolved/dynamic cells in level-2 layer A.

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
9  → 1,6,8 plus anomalous 524
10 → 8
```

There are 38 physical portal actor tiles because some transitions use adjacent records. Value `524` is preserved as **special/out-of-range**, not force-fit into a level number.

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
| `-5` | generic record-action fallback; calls `0x08005720(argument)` |

State-4 collection interactions use a separate dispatcher. In that context:

| Opcode | State-4 pickup behavior |
|---:|---|
| `-1` | set dialogue step, consume interaction, increment collection progress |
| `-2` | set primary message stream, consume interaction, increment progress |
| `-3` | add auxiliary message stream, consume interaction, increment progress |
| `-4` | set monster-render flag `0x0300061C = 1`; **does not** write the record argument to `0x030006AC` |
| `-5` | run final-sketch handler `0x080037F6`, consume pickup, increment progress |

`data/dialogue_context_semantics.csv` is the authoritative context × opcode export. `data/dialogue_opcode_semantics.csv` is retained as a normal-context compatibility view. `dialogue_scripts.csv` also labels `-4/-5` explicitly as **normal-context** interpretations instead of universal meanings.

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
   -> gameplay repeatedly advances 0x03000674 and feeds it to 0x08004FE0
```

`0x08004FE0` performs large expanding copies into VRAM beginning at `0x06000000` and `0x06010000`. The workspace keeps the conservative name `ending_vram_effect_candidate`: the control flow is proven, while the exact intended frame-by-frame corruption/reveal still deserves emulator or hardware tracing.

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

For these `turn=4/5` gate tiles, the machine code therefore proves **gate behavior activation after the rusty-key collection**. v4 deliberately does not claim that `0x0800404A` itself performs the `portTo=8` scene transition on the same frame; the branch first manipulates collision/player state, so the eventual transition timing remains a separate proof target.

Machine-readable exports:

- `data/level10_collection_gate_policy.csv`
- `data/state4_collection_progression.csv`
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
      ↓
draw          0x080065FC
      ↓
dynamic copy  0x08004F04
      ↓
OAM submit    0x0800A8F0
```

A previous working label that called vtable `0x08018AD8` the Player class was wrong. Rendering its referenced logical tile `0x48` proves it is a small **leaves/grass actor**. v4 retains that correction.

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

The primary OBJ source begins at `0x08310654`; the OBJ palette begins at `0x08366E58`. The span contains **5,536 complete 64-byte source tiles plus a 4-byte remainder** before the palette.

Only the first `0x8000` bytes / 512 logical tiles are initially uploaded. `0x08004F04` dynamically copies later animation tiles into hardware-visible OBJ VRAM slots.

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

A second source base, `3468`, follows from initialized globals and the `0x08006B3A` draw branch **if `player+0x1E0 == 0`**. Because that field's allocator/default state has not yet been proven, the packaged image is named `player_branch_candidate_3468.png`, not “default Vika.”

---


### Spawn registry, story-overlay graphics, and evidence-backed identities

The latest ROM's string-driven spawner registry is now code-backed:

| `spawnType` | Factory | Allocation | Runtime implementation |
|---|---:|---:|---|
| `npc` | `0x08003A60` | `0xFC` | NPC / interactive entity, vtable `0x08018B00` |
| `grass` | `0x08002914` | `0x6C` | grass/leaves, vtable `0x08018AD8` |
| `fgtile` | `0x08003AEC` | `0x90` | foreground tile, vtable `0x08018E4C` |

The `npc` draw method is `0x0800274C`. Its dynamic graphics source selection is:

```text
sourceBias = [0x030007FC] = startup-initialized 0xE00
sourceBase = sourceBias + legsColor*8 + subtype + 2*(frame-1)
sourceRows = sourceBase + {0,16,32,48}
```

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

The overlay can now be labeled conservatively from combined dialogue + metadata evidence:

- **overlay #4 = IQ 54** (high confidence): `dial=2`, `state=3`, `route=0`; script 2 is IQ's sketch-quest conversation;
- **overlay #10 = Katya** (high confidence): `dial=3`; script 3 is Katya's sister/bicycle conversation;
- **overlay #11–15 = five collection pickups** (high confidence role, not person identity): all use `state=4` and the same paper/sketch graphics family, matching IQ's explicit request to find five sketches.

The remaining human-looking overlay records remain **unidentified** rather than being assigned names from appearance alone. See `data/story_entity_identities.csv`.

Machine-readable exports:

- `data/spawn_type_factories.csv`
- `data/npc_sprite_pipeline.csv`
- `data/story_entity_sprite_sources.csv`
- `renders/sprites/story_entity_contact_sheet.png`

Implementation guidance for the eventual clean-room rebuild is in `BUTANO_REBUILD_NOTES.md`. The Butano snapshot reviewed for those notes is pinned to commit `77dcbcb3d8783596a9f333c64eedbccec77b05dc` (2026-08-06); Butano is not used as evidence for original Graveblood behavior.

---

## 10. Wardrobe table — code-backed

The Player constructor copies exactly:

`0xC8 = 200 bytes`

from ROM:

`0x080198A0`

into:

`player + 0x2B4`

The copied region is exactly **10 fixed slots × 20 bytes**:

| Slot | Literal |
|---:|---|
| 0 | `Favorite Skirt` |
| 1–7 | `Not for demo` |
| 8–9 | empty |

This makes the relationship to the Player object code-proven rather than a guess based on nearby strings.

The initialized RAM block at `0x03001254` is consumed both by `Player_draw` and by the Wardrobe/menu code around `0x08008E30`, but it is a **larger shared avatar/menu state block**. v4 intentionally does not reduce the first dword to an unsupported name such as `equipped_outfit`.

Machine-readable exports:

- `data/wardrobe_labels.csv`
- `data/player_sprite_pipeline.csv`
- `data/obj_graphics_summary.csv`

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
- `render_summary.csv`.

The large raw layer-A/layer-B PNGs are **not bundled** to keep the ZIP smaller; `tools/render_maps.py` regenerates them exactly.

`renders/sprites/` contains:

- `obj_source_atlas.png` — all 5,536 complete source tiles;
- `character_source_2198.png` — known-valid character frame sample, no default-outfit claim;
- `player_branch_candidate_3468.png` — conditional initialized-branch candidate;
- `leaves_logical_tile_0x48.png` — evidence for the corrected leaves-vtable identification;
- `sprite_summary.json`.

The bright palette-zero regions visible in some map renders reflect the ROM's selected BG palette/base fill in the offline composition; the renderer does not invent replacement scenery for runtime/dynamic cells.

---

## 13. Reproducing the extraction

Requirements:

- Python 3;
- Pillow for image rendering;
- `clang` + `llvm-objdump` only if regenerating focused disassembly snapshots.

Set the canonical ROM path:

```bash
export GRAVEBLOOD_ROM="/path/to/Graveblood 0.0.1.1.5.2 demo.gba"
```

Regenerate canonical structural data:

```bash
python3 tools/extract_structure.py "$GRAVEBLOOD_ROM" --out data
python3 tools/extract_extended_semantics.py "$GRAVEBLOOD_ROM" --out data
```

Regenerate maps:

```bash
python3 tools/render_maps.py "$GRAVEBLOOD_ROM" renders/generated_maps --actors data/actors.csv
```

`render_maps.py` emits layer A, layer B, final composites, actor overlays, and a summary CSV. v4 packages all of those layer/composite/overlay renders plus contact sheets so each hardware world layer can be inspected independently.

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
- `data/actors.csv` — all 267 physical actor records.
- `data/portal_edges.csv` — code-proven physical transition records.
- `data/standalone_spawners.csv` — raw 16-record Graveblood-era story-overlay block.
- `data/npc_state_modes.csv` — recovered behavior modes.
- `data/spawn_type_factories.csv` — code-proven `npc/grass/fgtile` factory registry.
- `data/npc_sprite_pipeline.csv` — NPC source/destination dynamic-OBJ formula and evidence.
- `data/story_entity_sprite_sources.csv` — exact source rows selected for all 16 standalone records.
- `data/story_entity_overlay_slots.csv` — two startup overlay selectors, actor-list loader, and level-gate chain.
- `data/story_entity_identities.csv` — conservative evidence-backed identities/roles for the 16 overlay records.
- `data/dialogue_context_semantics.csv` — authoritative normal-vs-state4 opcode semantics.
- `data/state4_collection_progression.csv` — six-step state-4 selector (`4,-1,-1,5,6,0`).
- `data/level10_collection_gate_policy.csv` — code-proven pre-key/post-key branch threshold for the four level-10 gate tiles.
- `data/npc_routes.csv` — five six-waypoint routes.
- `data/dialogue_scripts.csv` — all 58 decoded dialogue records.
- `data/dialogue_opcode_semantics.csv` — normal-context compatibility opcode view.
- `data/message_streams.csv` / `message_selectors.csv` — inbox/progression data.
- `data/wardrobe_labels.csv` — ten fixed Player wardrobe-name slots.
- `data/obj_graphics_summary.csv` — OBJ bank/hardware summary.
- `data/player_sprite_pipeline.csv` — code-backed Player graphics anchors and caveats.
- `data/crossbuild_matches.csv` / `crossbuild_summary.json` — alpha differential.
- `data/graveblood_001152.sym` — working symbol map.

### Tools

- `tools/extract_structure.py` — canonical structural extractor.
- `tools/extract_extended_semantics.py` — routes/messages/states/wardrobe/OBJ semantics.
- `tools/match_alpha_latest.py` — alpha↔latest exact fingerprint matcher.
- `tools/render_maps.py` — corrected 8bpp world renderer.
- `tools/render_sprites.py` — OBJ/OAM dynamic Player/NPC renderer library, including story-entity contact-sheet generation.
- `tools/disasm_thumb_chunk.py` — focused Thumb disassembly helper.
- `tools/test_*.py` — current ROM-backed regression suite (count verified at package time).

---

## 15. Current reconstruction boundary / next high-value targets

This workspace is **not** a decompiled source tree yet. It is a verified structural/semantic foundation for one.

Highest-value next targets are:

1. trace the post-key `Fgtile` branch from `0x0800404A` through the exact eventual `portTo=8` handoff and Player/collision state changes;
2. identify the remaining human story-overlay records from dialogue/location/behavior evidence without assigning names from sprite appearance alone;
3. finish the Player animation-bank/wardrobe selector and prove the actual equipped-state fields;
4. fully name state 1/2/4 interaction geometry and distinguish talk triggers from collectible/contact triggers;
5. emulator/frame-trace `0x08004FE0` to reproduce the final expanding VRAM effect over time, now that the creature composite itself is reconstructed;
6. recover audio/SFX tables and identify SFX 13;
7. inspect any unused dialogue/message/wardrobe branches for content beyond the public festival path;
8. build a Butano parity prototype of the public demo using the recovered data before adding new story content.

### Confidence policy

This workspace intentionally separates:

- **proven machine behavior** — directly supported by traced code/data;
- **working names** — useful conservative labels whose original developer names are unknown;
- **candidates** — plausible interpretations that still need another proof step.
