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

The current playable milestone boots directly into **recovered Level 7**, renders the recovered **Level 7 and Level 8** interiors, uses their recovered player spawn/collision data, drives the exact recovered 16-frame 16x32 Player walk/idle animation set through OAM, and supports the recovered Level 7 <-> Level 8 portal route. The movement runtime follows the original collision resolver semantics: **zero-valued 8-pixel cells are passable; nonzero cells block movement**.

Start here:

- `DEVELOPING_AND_BUILDING.md` — devkitPro/devkitARM/libgba setup, build, emulator/hardware testing, asset regeneration, and release tags.
- `reconstruction/` — CFA-style C runtime and checked-in generated assets.
- `.github/workflows/build-release-rom.yml` — direct devkitPro CI build artifacts plus `Graveblood_RE_v*-dev` tagged releases.

The normal reconstruction build does not require the original demo ROM. Development releases still use tags such as `Graveblood_RE_v0.0.1-dev`; GitHub Actions publishes the versioned ROM asset as `Graveblood_RE_v0.0.1.gba`.

---

## 1. What this repository contains

The workspace now includes:

- a buildable CFA-style devkitPro/libgba reconstruction under `reconstruction/`, currently covering playable Levels 7 and 8;
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
- conservative story-entity identity export (two code-backed IQ 54 overlay instances, Stas, Julia, Katya, and five collection pickups);
- decoded message/progression streams;
- five NPC routes / 30 waypoints;
- NPC state-mode semantics and exact NPC dynamic-sprite source formula;
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

`0x08004FE0` is now statically quantified. It first biases its argument by 64, then uses byte-counted copy helper `0x08010C54` for two writes:

```text
0x06000000 <- 1500 * (argument + 64) bytes
0x06010000 <-  250 * (argument + 64) bytes
```

At argument 0 those are **96,000 bytes** and **16,000 bytes**. The first copy grows by 1,500 bytes per step and exceeds the nominal 96 KiB VRAM span from `0x06000000` once the argument reaches 2. The workspace still keeps the conservative name `ending_vram_effect_candidate`: the byte equations and call sites are proven, while the intended visible frame-by-frame corruption/reveal still deserves emulator or hardware tracing. See `data/ending_vram_effect_copy_model.csv` and `disasm/ending_vram_effect_08004FE0.txt`.

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

The next Player interaction layer is now recovered as a **four-way action tree** backed by 20 fixed `0x2C`-byte records at `0x08018738`. The root page is `TALK / FLIRT / ASSAULT / SHARE`, and each root opens exactly four leaves:

```text
TALK    -> SUBJECT / Ask about / JOKE / CRITICIZE
FLIRT   -> KISS CHEEK / KISS LIPS / DIRTY JOKE / BREAKUP
ASSAULT -> SWEAR / FIGHT / unused / SCAM
SHARE   -> GIFT / ACTIVITY / A Number / ASK
```

Player `+0x1E8` stores the current four-record page base and `+0x1E4` stores the selected quadrant. In state 1, `Up / Right / Down / Left` select slots `0 / 1 / 2 / 3`. A confirmation indexes `base+choice`; record `+0x20 == 0` means submenu and copies record `+0x24` back to `+0x1E8`, while `+0x20 == 1` enters secondary state 2.

State 2 is now partly decoded instead of being treated as opaque. `Player+0x1F0` is a real vertical secondary cursor: leaf entry initializes it to `0`, fresh Up decrements it when positive, and fresh Down increments it through the mechanical range `0..8`; either move rebuilds the secondary UI through `0x080074D8` and `0x08006E00`. The builder reads leaf `+0x28` as a **secondary-topic count**. If that count is positive, leaf `+0x24` is the start index into the fixed 15-byte topic-label table at `0x080114B4`; if the count is zero, the builder exits before using `+0x24` as a topic-table index. In this demo only three leaves expose counted lists: `SUBJECT` = `sports / movies / fashion / video games / school / future / parties / last event / mysteries`; `Ask about` = `hobbies / fav. music / best places / fav. meals / dreams`; `CRITICIZE` reuses the same nine-topic list as `SUBJECT`. Do not assign a meaning to `+0x24` on the thirteen zero-count leaves yet.

Two topic-response paths are also code-proven. `SUBJECT` uses 16 fixed 108-byte responses per topic through the pointer table at `0x030007D4`; `CRITICIZE` uses 8 per topic through `0x030007AC`. Both index the selector table at `0x0300110C` with Player `+0x388`, then *expect* a 0..4 topic class at `profile + 4*(topic_index+6)`. Value `2` uses the shared neutral line `I don't really care`; the other valid values select randomized class-specific slots in the topic bank. Topic indices 7 (`last event`) and 8 (`mysteries`) deliberately point at the same response bank in this demo. All 216 fixed SUBJECT/CRITICIZE response records are exported verbatim as structured rows in `data/player_interaction_topic_response_texts.csv`.

The initialized selector table is now recovered exactly, and it proves this social subsystem is only partly coherent in the demo. Selector `0` points to a genuine `0x3C` **Stas** social profile at `0x030010D0`, selector `1` to a genuine `0x3C` **Julia** profile at `0x03001094`, selector `2` is null, and selectors `3..8` point to six incompatible `0x30` NPC metadata/card records (`Stas / IQ 54 / Kate / Kiata / Alex / Evelina`). The two proper profiles each contain nine numeric topic classes: Stas = `3,4,0,2,1,1,3,2,2`; Julia = `1,2,2,0,1,2,4,2,3`. By contrast, applying the runtime topic-class formula to selectors `3..8` yields 54 reads of which only 23 happen to fall in `0..4`; many others are pieces of descriptor text such as `Just` or `Popu`. `0x0800948C` dereferences the selected pointer/topic directly with no null guard before that read.

The malformed entries are now also bounded by **canonical reachability** instead of being treated as equally likely runtime hazards. The only initialized `state=1` NPC records are overlay #5 at `0x08019100` (`dial=0`) and overlay #6 at `0x0801917C` (`dial=1`). NPC update sends only its state-1 proximity success through `0x08002B52 -> 0x08002FA2`; a fresh A then reaches `0x08002FCE`, which copies actor `+0x5C` into Player `+0x388`. Therefore the canonical initialized social path reaches only selectors `0` and `1`, identifying overlay **#5 as Stas** and **#6 as Julia**. NPC update itself reads but does not write actor state `+0x5A` or dial `+0x5C`; selectors `2..8` are best described as **latent prototype defects** under the recovered normal path. External mutation by another subsystem is not ruled out, so exact-parity data should still preserve the table unchanged. See `data/player_interaction_profile_selector_reachability.csv` and the selector-integrity CSV.

A selector-use inventory also closes the current question around proper-profile `+0x10`: both genuine profiles initialize it to zero, and none of the 15 recovered PC-relative loads of selector table `0x0300110C` lead to a proved `+0x10` read. Recovered social code instead uses the profile/name prefix, `+0x14`, and topic slots `+0x18..+0x38`. Use **reserved/unused in recovered interaction runtime** as the working label for `+0x10`; this is a high-confidence absence claim within the recovered selector-use sites, not a whole-program proof. See `data/player_interaction_profile_field_usage.csv`.

The later response dispatcher exposes an important demo limitation: `0x08009200` keys **only on Player `+0x1E4` (the quadrant)** and does not read the current page base `+0x1E8`. Quadrant 0 goes to the SUBJECT response-bank path, quadrant 3 goes to CRITICIZE, and quadrants 1/2 share a path that sets Player `+0x382=1`. Consequently labels on the FLIRT/ASSAULT/SHARE pages are not proof of sixteen unique implemented social effects in this build: `KISS CHEEK`, `SWEAR`, and `GIFT`, for example, reach the same quadrant-0 response code as SUBJECT at this dispatcher. Preserve the labels as recovered menu data, but reconstruct the observed runtime dispatch separately.

The shared quadrant-1/2 flag has a proved follow-up handshake. At `0x0800852E`, while Player `+0x382` is armed, a **fresh A** clears Player `+0x382`, `+0x381`, and interaction state `+0x1EC`, then writes `1` to global `0x03000610`. The same accepted edge compares Player `+0x39C` with `10 * current_profile[+0x14]` and nudges `+0x39C` by exactly one toward that target. An independent write in the quadrant-0 topic-response path at `0x08009504` proves `profile+0x14 += 2 * (topic_class - 2)`, giving class deltas `-4,-2,0,+2,+4`; both genuine Stas/Julia profiles initialize `+0x14` to zero. A second independent path at `0x080090F8`, before the quadrant-specific response branch, directly computes and stores **`Player+0x39C = 10 * profile+0x14`**. This upgrades `+0x39C` to a **scaled relationship-like score mirror/follower** rather than an unrelated counter. No distinct rendering consumer has been proved yet, so do not call it a visible relationship meter. The previously noticed `8/16/24` values belong to incompatible `0x30` metadata records and must not be interpreted as proper social-score initial values. See `data/player_interaction_social_score_semantics.csv`, `data/player_interaction_score_mirror_semantics.csv`, and `data/player_interaction_profile_target_step.csv`.

Player `+0x38C` is also a nested interaction-depth counter: submenu confirmation increments it, leaf entry reloads then increments it through the same shared block, and the B-return path decrements it. In state 2, the fresh-A gate at `0x0800960E` reaches state 3 only when depth is positive **and page base is 4 (TALK)**. Page bases 8/12/16 take an internal Player-update exit branch at this gate without changing `+0x1EC`. Fresh B from state 2 is therefore only named a **return to state 0** here; static code still does not prove whether its game-level meaning is cancel, commit, or leaf-dependent. State 3 remains interaction teardown: it resets page/state scratch, clears `0x03000610`, restores scene graphics, and sets Player `+0x381=1`. See `data/player_interaction_action_table.csv`, `data/player_interaction_secondary_topics.csv`, `data/player_interaction_state2_cursor.csv`, `data/player_interaction_topic_response_banks.csv`, `data/player_interaction_topic_response_texts.csv`, `data/player_interaction_runtime_dispatch.csv`, `data/player_interaction_followup_handshake.csv`, `data/player_interaction_profile_target_step.csv`, `data/player_interaction_profile_selector_table.csv`, `data/player_interaction_social_profile_topics.csv`, `data/player_interaction_social_score_semantics.csv`, `data/player_interaction_profile_topic_layout_mismatch.csv`, `data/player_interaction_profile_selector_integrity.csv`, `data/player_interaction_depth_semantics.csv`, and `data/player_interaction_state_transitions.csv`.

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

### Player animation bank and frame selection

The normal avatar animation path is now recovered far enough to drive the CFA reconstruction directly. Startup initializes the shared graphics bank at `0x0300103C` to **15**, animation state `0x03001254` to **8**, frame `0x03001258` to **1**, and countdown `0x030012A8` to **5**. Player `+0x1DC` supplies the constructor-proven bank stride of **192 source tiles**.

For bank 15 the normal draw branches select exactly:

```text
states 2..6: 3456 3458 3460 3462 3464 3466   (6-frame regular walk)
state 7:     3520 3522 3524 3526 3528 3530   (6-frame up/back walk)
state 8:     3468 3470 3532 3534 3534 3532 3470 3468
```

The eight-phase idle therefore contains four unique packed poses. Across the two walking banks plus those four idle poses there are **16 unique 16×32 frames**. All 16 use the same 15 opaque RGB colors, so the reconstruction stores them losslessly in one 4bpp OBJ palette plus transparency. Right-facing rendering is the original horizontal-flip path; vertical movement keeps the existing horizontal facing instead of resetting it.

The shared frame counter is not reset when direction/state changes. `Player_update` first advances/clamps the existing frame/countdown, then commits the direction-selected animation state. Normal moving states use a reset countdown of `5`; normal state-8 idle uses `8`. This is why the reconstruction preserves timer/frame continuity rather than restarting a walk cycle on every turn.

`Player+0x1E0` is now bounded more precisely rather than silently assumed to be zero. The Player constructor initializes nearby `+0x1C0` but **skips `+0x1E0`**, while both draw/update read `+0x1E0`. The factory allocates the `0x3A0`-byte Player through the normal malloc/new path, not a zero-filling allocator, and the recovered Player path has no pre-use store to `+0x1E0`. Static RE therefore cannot honestly claim a deterministic original value at first use. The CFA reconstruction explicitly initializes the corresponding clean-room behavior to the normal selector-0 branch instead of reproducing dependence on stale heap contents. The old `player_branch_candidate_3468.png` remains an evidence artifact, but the runtime no longer depends on that single candidate image.

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
- **overlay #5 = Stas** (high confidence): `state=1`, `dial=0`; the only state-1 social bootstrap copies that dial into profile selector 0, whose proper profile name is Stas;
- **overlay #6 = Julia** (high confidence): `state=1`, `dial=1`; the same path selects profile 1, whose proper profile name is Julia;
- **overlay #9 = IQ 54** (high confidence): level 10, `state=2`, `dial=2`; `dial` is the proven script index and script 2's speaking NPC is IQ 54, so this is a second level-specific instance of the same character rather than a new identity;
- **overlay #10 = Katya** (high confidence): `dial=3`; script 3 is Katya's sister/bicycle conversation;
- **overlay #11–15 = five collection pickups** (high confidence role, not person identity): all use `state=4` and the same paper/sketch graphics family, matching IQ's explicit request to find five sketches.

The remaining human-looking overlay records (#0–3, #7–8) remain **unidentified** rather than being assigned names from appearance alone. See `data/story_entity_identities.csv`.

Machine-readable exports:

- `data/spawn_type_factories.csv`
- `data/npc_sprite_pipeline.csv`
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

Normal browser input is **Left / Right / B**. Starting from constructor state, Left/Right can reach selectors `0..6`; the path at `0x080093F4` that writes `7` is a defensive clamp for an already-high value, not a seventh Right step. The browser displays `(B) to exit`. No A-button confirmation/equip path is present in the recovered browser control flow.

The constructor also copies two 14-dword preview tables:

- `Player+0x244 <- ROM 0x080197B0`: first group `15,13,12,11,6,4,5`; second group is seven zeroes. The Wardrobe preview loop consumes these as dynamic OBJ source-bank selectors.
- `Player+0x27C <- ROM 0x080197E8`: normal selector pages `6,2,1,0,3,4,5`. The selected value feeds `0x08004F6C`, which copies one `0x2000`-byte page into BG VRAM at `0x06003000`.

This also corrects an older state-label mistake. **`0x03001254` is the Player animation state/frame block**, not shared Wardrobe state. The live gameplay graphics-bank global is **`0x0300103C`**, initialized to `15`; its two direct canonical-ROM literal references are both read-only Player drawing paths. No recovered Wardrobe path writes that live bank. The public demo therefore proves a **browse/preview interface, not a gameplay equip action**.

For reconstruction parity, alternate `Not for demo` preview banks remain evidence data only. The CFA runtime keeps the proven startup/default outfit and does not make those preview choices gameplay-selectable without new evidence.

Machine-readable exports:

- `data/wardrobe_labels.csv` — raw 10×20-byte label slots (including ROM padding);
- `data/player_wardrobe_state_semantics.csv` — selector, navigation, preview tables, corrected global roles, and no-equip result;
- `data/player_wardrobe_slots.csv` — normalized per-slot reachability and preview mapping;
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
- `clang` + `llvm-objdump` for focused disassembly snapshots when available, or Python `capstone` as the fallback disassembler.

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
- `data/level10_gate_forced_motion.csv` — exact post-key fresh-A turn 4/5 target coordinates, Player offsets, helper behavior, and separation from generic `portTo`.
- `data/level10_gate_collision_geometry.csv` — exact 8-pixel-grid overlap formulas and contact flags for the post-key gate.
- `data/player_vertical_target_calls.csv` — all three recovered static callers of `0x080080A4`, including which temporary anchor fields each caller writes and the helper's X-discard/Y-consume behavior.
- `data/player_npc_interaction_alignment.csv` — fresh-A NPC source path, interaction-active flag/state-0 dispatch, exact ±19 px X alignment equations, Y alignment, and collision-resolved motion handoff.
- `data/player_interaction_action_table.csv` — all 20 four-way interaction records, root-to-child page links, visual selectors, and conservatively raw leaf payload fields.
- `data/player_interaction_profile_selector_table.csv` — exact nine-entry social selector table: two real `0x3C` profiles, one null slot, and six incompatible `0x30` metadata/card pointers.
- `data/player_interaction_profile_selector_reachability.csv` — canonical state-1 actor/dial reachability proving selectors 0/1 are the normal initialized social path; selectors 2..8 remain latent unless externally mutated.
- `data/player_interaction_profile_field_usage.csv` — recovered selector-derived profile-field inventory, including the absence of a `+0x10` consumer in the recovered interaction runtime.
- `data/player_interaction_social_profile_topics.csv` — the nine valid 0..4 topic ratings for the genuine Stas and Julia social profiles.
- `data/player_interaction_social_score_semantics.csv` — centered topic-class update of profile `+0x14` and its relationship-like working interpretation.
- `data/player_interaction_score_mirror_semantics.csv` — direct `Player+0x39C = 10 * profile+0x14` synchronization plus the later one-step follower behavior.
- `data/player_interaction_profile_topic_layout_mismatch.csv` — all 54 wrong-layout topic reads for selectors 3..8, including ASCII overlap and valid-class accidents.
- `data/player_interaction_profile_selector_integrity.csv` — compact parity warning/counts plus the unguarded response dereference site.
- `data/player_interaction_state_transitions.csv` — code-proven state 0→1 setup, state-1 directional choices, branch/leaf confirmation, state-2 B return/back transition, and state-3 teardown.
- `data/ending_vram_effect_copy_model.csv` — exact byte-count equations/source biases/destinations for the final `0x08004FE0` effect.
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
- `data/crossbuild_matches.csv` / `crossbuild_summary.json` — alpha differential.
- `data/graveblood_001152.sym` — working symbol map.

### Focused disassembly

- `disasm/wardrobe_label_draw_08006430.txt` — selected-label helper, including `Player+0x240` × 20 addressing into `Player+0x2B4`.
- `disasm/wardrobe_player_update_path_08008DF0.txt` — internal `Player_update` Wardrobe browser path: title/prompt, preview loaders, navigation, and exit flow.

### Tools

- `tools/extract_structure.py` — canonical structural extractor.
- `tools/extract_extended_semantics.py` — routes/messages/states/wardrobe/OBJ semantics.
- `tools/match_alpha_latest.py` — alpha↔latest exact fingerprint matcher.
- `tools/render_maps.py` — corrected 8bpp world renderer.
- `tools/render_sprites.py` — OBJ/OAM dynamic Player/NPC renderer library, including story-entity contact-sheet generation.
- `tools/disasm_thumb_chunk.py` — focused Thumb disassembly helper.
- `tools/test_*.py` — current ROM-backed regression suite (**93 tests** at this package checkpoint).

---

## 15. Current reconstruction boundary / next high-value targets

This workspace is **not** a decompiled source tree yet. It is a verified structural/semantic foundation for one.

The public-demo Wardrobe selector/preview path is now statically bounded: selectors `0..6` browse preview data, but no confirm/equip action or live graphics-bank mutation is recovered. With that target closed, the highest-value next targets are:

1. fully name state 1/2/4 interaction geometry and distinguish talk triggers from collectible/contact triggers;
2. identify the remaining story-overlay records from dialogue/location/behavior evidence without assigning names from sprite appearance alone;
3. continue past the now-recovered state-2 topic cursor and response banks: identify `Ask about` handling and the zero-count `JOKE / FLIRT / ASSAULT / SHARE` leaf effects without inventing semantics for their still-unused raw metadata;
4. emulator/frame-trace `0x08004FE0` to reproduce the final expanding VRAM effect over time now that its exact copy-size equations are known;
5. recover audio/SFX tables and identify SFX 13;
6. inspect unused dialogue/message/Wardrobe branches for content beyond the public festival path, while keeping browse-only preview data separate from any unproven equip mechanic;
7. expand the CFA-style devkitPro parity runtime from the current Level 7/8 slice toward the complete public demo before adding new story content.

### Confidence policy

This workspace intentionally separates:

- **proven machine behavior** — directly supported by traced code/data;
- **working names** — useful conservative labels whose original developer names are unknown;
- **candidates** — plausible interpretations that still need another proof step.

That distinction matters if this work later becomes the basis for a finished Graveblood reconstruction: recovered facts should not quietly turn into invented “original” design.
