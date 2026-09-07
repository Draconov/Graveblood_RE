# Butano feasibility notes for a clean Graveblood reconstruction

These notes are **implementation guidance only**. They do not use Butano as evidence for what the original Graveblood binary does; original-game claims in this workspace come from the canonical ROM and, where explicitly stated, alpha differential evidence.

## Reviewed upstream snapshot

Repository: `GValiente/butano`

Reviewed branch: `master`

Pinned commit: `77dcbcb3d8783596a9f333c64eedbccec77b05dc`

Commit date: `2026-08-06T20:34:58Z`

Butano describes itself as a modern C++ high-level GBA engine and is distributed under the zlib license. Before implementation, pin the Graveblood reconstruction to a known Butano revision rather than silently following `master`.

## 1. Dynamic OBJ staging maps well to Butano

Recovered Graveblood behavior:

- the ROM contains a large 8bpp OBJ source bank;
- only an initial working subset is uploaded to OBJ VRAM;
- Player and NPC/interactive-entity draw code copy only the currently needed 16x8 source rows into reusable OBJ-VRAM slots;
- hardware sprites then point at those staged slots.

Relevant Butano surface:

- `butano/include/bn_sprite_tiles_ptr.h`
- `bn::sprite_tiles_ptr::allocate(...)`
- `bn::sprite_tiles_ptr::allocate_optional(...)`
- `bn::sprite_tiles_ptr::vram()`
- `bn::sprite_tiles_ptr::reload_tiles_ref()` for referenced mutable tile data

Recommended reconstruction strategy:

1. Keep canonical character graphics in ROM/source assets.
2. Reserve a small 8bpp dynamic sprite-tile working set.
3. Copy only the four 16x8 rows required by the active Graveblood frame into that set.
4. Use two 16x16 sprites for a 16x32 character, matching the recovered original layout.

Do **not** pre-allocate every one of the recovered 5,536 source tiles as live OBJ VRAM; the original game does not do that either.

## 2. World streaming maps well to dynamic regular BG maps

Recovered Graveblood behavior:

- large logical worlds exceed the physical GBA text-BG map window;
- the engine maintains streamed BG1/BG2 windows around the camera;
- source world tile IDs are translated to GBA screen entries on demand;
- BG3 is a quarter-speed parallax plane;
- BG0 is a fixed UI/text plane.

Relevant Butano example:

- `examples/dynamic_regular_bg/src/main.cpp`

The example constructs a mutable 32x32 `bn::regular_bg_map_cell` array in RAM, wraps it in `bn::regular_bg_map_item`, edits cell tile/palette/flip properties, and calls `reload_cells_ref()` after modifications.

Recommended reconstruction strategy:

- maintain two mutable 32x32 regular maps for Graveblood world layers A/B;
- update only newly exposed rows/columns as camera tile coordinates change;
- preserve Graveblood's translation-table semantics in game code;
- keep parallax as a separate regular BG and set its position to one quarter of camera position;
- render UI/text on the highest-priority regular BG.

This is an **equivalent architecture**, not a requirement to reproduce Graveblood's exact original VRAM screenblock addresses.

## 3. Background priority is directly representable

Relevant Butano API:

- `bn::regular_bg_ptr::set_priority(int)`

Recovered visual order to preserve:

1. BG0 UI/text — priority 0
2. BG1 world A — priority 1
3. BG2 world B — priority 2
4. BG3 parallax — priority 3

Butano resource allocation may choose different VRAM blocks internally; preserve the visual priority/scroll behavior rather than hardcoding the old engine's `0x0600D800/0x0600E000/...` layout.

## 4. Save support can be added cleanly with SRAM

The public demo intentionally has no save system, but a finished reconstruction will need one.

Relevant Butano API:

- `butano/include/bn_sram.h`
- `bn::sram::read` / `write`
- offset and span variants

A future save structure can serialize at minimum:

- save-format version/magic;
- current level + safe spawn point;
- story progression stage;
- acquired message streams / quest flags;
- collected sketch/item flags;
- wardrobe/equipment state once fully decoded;
- relationship/friendship state once recovered;
- settings that are genuinely game state rather than presentation-only options.

Do not invent save fields before their gameplay semantics are understood; version the format from the first prototype.

## 5. Actor factory architecture should be retained

The latest ROM has a string-driven runtime registry for at least:

- `npc`
- `grass`
- `fgtile`

The `npc` runtime class is also reused for non-human interactive entities, so a rebuild should separate **runtime implementation class** from **semantic entity identity**.

Suggested shape:

```cpp
using ActorFactory = ...;

Actor* spawn_actor(const ActorRecord& record)
{
    if(record.spawn_type == "npc")     return spawn_interactive_entity(record);
    if(record.spawn_type == "grass")   return spawn_grass(record);
    if(record.spawn_type == "fgtile")  return spawn_foreground_tile(record);
    ...
}
```

The final API should use compile-time identifiers/enums where practical; the snippet only illustrates preserving the original data-driven separation.

## 5a. Rusty-key gate is forced movement, not a proven scene portal

The four level-10 `turn=4/5` Fgtile records become interactive once the collection index exceeds 3. Their post-key A-button action does **not** use `portTo=8`: it temporarily writes fixed-point values into Player `+0x390/+0x394` and calls `0x080080A4`, which applies a vertical delta and clears both fields. These Player fields are dual-purpose: construction/normal movement also uses the sentinel value `1`, so do not model them as persistent generic target coordinates.

For a parity implementation, model this as recovered movement behavior:

- `turn=4`: target `(826, 360)`;
- `turn=5`: target `(826, 410)`;
- activation: fresh A press while overlapping the post-key gate collision geometry;
- collision grid: `PX=(playerX-8)>>11`, `PY=(playerY-24)>>11`, `AX=(actorX-8)>>11`, `AY=(actorY-16)>>11`, accepting `{AX,AX+1} x {AY,AY+1}`.

The gate writes both temporary fields, but the called helper consumes only Y and clears both X/Y before returning. The X=826 value is therefore dead for this particular vertical-helper path; do not invent a horizontal movement step from it. Do not convert those four records into a level-8 scene transition merely because their serialized metadata contains `portTo=8`. The generic Fgtile `portTo -> request_scene` block is separate in the canonical code.

## 5b. NPC interaction alignment is a separate full-X/Y path

A different fresh-A NPC handler (`0x08002FCE`) copies actor `dial`, X and Y into Player `+0x388/+0x390/+0x394` and sets `0x03000610`. `Player_update` state 0 then builds a collision-resolved displacement:

```text
anchor on/right of Player: dx = anchorX - playerX - 19px
anchor left of Player:     dx = anchorX - playerX + 19px
dy = anchorY - playerY
next Player +0x1EC state = 1
```

The displacement is handed to `0x08004670`, which collision-tests movement before applying allowed X/Y components. For a Butano parity implementation, reconstruct this as **align to the NPC's Y and stand 19 px to one side**, rather than as a generic “move to pending target” service. Keep the two source cases separate from the rusty-key gate's vertical-only helper even though both temporarily reuse `+0x390/+0x394`.

## 5c. NPC interaction UI is a four-way action tree

After the state-0 alignment bootstrap, Player `+0x1E8` is a four-record page base into the 20-entry table at `0x08018738`. Each record is `0x2C` bytes: a fixed `0x1C`-byte label followed by four 32-bit fields. State 0 reads the four records at `base+0..3`, consumes each record's `+0x1C` visual selector, and enters Player interaction state 1.

The root page is exact:

```text
TALK    -> child base 4  -> SUBJECT / Ask about / JOKE / CRITICIZE
FLIRT   -> child base 8  -> KISS CHEEK / KISS LIPS / DIRTY JOKE / BREAKUP
ASSAULT -> child base 12 -> SWEAR / FIGHT / unused / SCAM
SHARE   -> child base 16 -> GIFT / ACTIVITY / A Number / ASK
```

State 1 is the four-way selector. Fresh directional input maps `Up/Right/Down/Left` to choice slots `0/1/2/3` in Player `+0x1E4`. On A confirmation, code forms `action_index = Player+0x1E8 + Player+0x1E4` and reads the selected record. Record `+0x20` is the proven node type: `0` is a submenu node and `1` is a leaf action. A submenu copies record `+0x24` into Player `+0x1E8`, resets the interaction state to 0, and renders the next four-record page. A leaf enters state 2.

Leaf `+0x24/+0x28` are now **partially** decoded. In the state-2 builder `0x08006E00`, `+0x28` is a secondary-topic count. When that count is positive, `+0x24` is the start index into the 15-byte label table at `0x080114B4`; when the count is zero, the builder returns before consuming `+0x24` as a label index. The counted leaves are `SUBJECT` (9 topics starting at 0), `Ask about` (5 topics starting at 10), and `CRITICIZE` (9 topics starting at 0). Keep `+0x24` raw for zero-count leaves.

Player `+0x1F0` is a **state-2 vertical cursor**, not an automatic countdown: entry sets it to 0, fresh Up decrements it when positive, and fresh Down increments it while the old value is `<=7`, yielding a mechanical `0..8` range. Both directions rebuild the secondary list through `0x080074D8` and `0x08006E00`. The movement code itself uses the global 0..8 bound; a per-leaf clamp to `+0x28` has not been proved. Fresh B returns state 2 to state 0, but call that a return/back transition rather than a semantic cancel until the leaf completion flow is fully traced.

For reconstruction, `SUBJECT` and `CRITICIZE` already have recoverable response selection. Player `+0x388` selects a pointer from `0x0300110C`; the code then expects a 0..4 topic class from `profile + 4*(topic+6)`. `SUBJECT` selects from 16-response topic banks referenced at `0x030007D4`; `CRITICIZE` selects from 8-response banks at `0x030007AC`. Class 2 renders the shared neutral string `I don't really care`; the other valid classes use randomized slots documented in `data/player_interaction_topic_response_banks.csv`. Topic indices 7 and 8 share the same response pointers in this demo, and all 216 fixed response records are exported in `data/player_interaction_topic_response_texts.csv`.

Do not normalize the selector table in a faithful reconstruction. Its exact initialized entries are `0 -> Stas 0x3C social profile`, `1 -> Julia 0x3C social profile`, `2 -> null`, then `3..8 -> Stas/IQ 54/Kate/Kiata/Alex/Evelina 0x30 NPC metadata records`. Only Stas and Julia expose the expected nine numeric classes: Stas `3,4,0,2,1,1,3,2,2`; Julia `1,2,2,0,1,2,4,2,3`. Reading selectors 3..8 through the social formula produces only 23 valid-class values out of 54 reads and otherwise overlaps metadata/text. The response path at `0x0800948C` performs the selected-pointer/topic dereference without a preceding null guard. For exact demo parity preserve this defect; a later remade/fixed mode can deliberately supply coherent profiles, but that is a design extension rather than RE.

Do **not** implement each leaf label as an independent effect yet. The runtime dispatcher at `0x08009200` reads only Player `+0x1E4`: quadrant 0 uses SUBJECT response code, quadrant 3 uses CRITICIZE response code, and quadrants 1/2 set Player `+0x382=1`. It does not consult page base `+0x1E8`, so identically positioned leaves on TALK/FLIRT/ASSAULT/SHARE share these runtime paths in the canonical demo. Treat the labels as recovered menu/presentation data and the quadrant dispatcher as the currently proved behavior.

The `+0x382` path is real, not dead metadata. `0x0800852E` consumes it on a fresh A edge, clears Player `+0x382`, `+0x381`, and `+0x1EC`, reasserts `0x03000610=1`, and then nudges Player `+0x39C` one step toward `10 * current_profile[+0x14]`. The independent topic-response write at `0x08009504` updates that profile field as `profile+0x14 += 2 * (topic_class - 2)`, i.e. class `0/1/2/3/4 -> -4/-2/0/+2/+4`; both proper Stas/Julia profiles initialize it to zero. At `0x080090F8` the response path also synchronizes `Player+0x39C = 10 * profile+0x14` directly before the quadrant branch. Use **relationship-like social score** for profile `+0x14` and **scaled relationship-like score mirror/follower** for Player `+0x39C` (high-confidence arithmetic/data flow; no proved UI-meter consumer yet). See `data/player_interaction_followup_handshake.csv`, `data/player_interaction_profile_target_step.csv`, `data/player_interaction_social_score_semantics.csv`, `data/player_interaction_score_mirror_semantics.csv`, and the selector/profile CSVs.

Player `+0x38C` is a nested interaction-depth counter. Submenu confirmation increments it; leaf entry reloads then increments it through the same block; B-return decrements it. In state 2, a fresh A reaches state 3 at `0x0800962C` only when depth is positive and current page base is 4 (TALK). Bases 8/12/16 exit the Player-update path at this gate without changing interaction state. State 3 is high-confidence **interaction teardown**: `0x0800963E` resets the page/scratch/state fields, clears `0x03000610`, performs the scene-graphics restore path, and sets Player `+0x381=1`. Reconstruct this state machine from `data/player_interaction_runtime_dispatch.csv`, `data/player_interaction_depth_semantics.csv`, and `data/player_interaction_state_transitions.csv` rather than flattening the menu into a single action list.

## 6. Systems that should remain custom Graveblood code

Butano should supply GBA primitives, not replace recovered game semantics. Keep these as Graveblood-owned code/data:

- 0x40-byte logical LevelRecord equivalent;
- source-tile translation and streaming policy;
- collision/world grids;
- portal graph;
- actor field semantics;
- NPC route following;
- dialogue VM and opcodes;
- Messages/story-stage system;
- story-controlled entity population;
- wardrobe and relationship systems as they are recovered.

## 7. Fifth-sketch effect caution

The original demo's opcode `-5` path performs deliberately extreme expanding VRAM copies. Static RE now proves the exact byte-count model:

```text
0x06000000 <- 1500 * (argument + 64) bytes
0x06010000 <-  250 * (argument + 64) bytes
```

The first call therefore writes 96,000 bytes from `0x06000000`, grows by 1,500 bytes per argument step, and crosses the nominal 96 KiB VRAM span at argument 2. A Butano rebuild should **not blindly reproduce raw out-of-range VRAM writes** merely because the binary does them.

First frame-trace the canonical ROM in mGBA/hardware and determine the intended visible effect. Then reproduce that visual result safely with managed BG/sprite data or a narrowly isolated low-level routine if direct hardware behavior is actually required. The static source of truth is `data/ending_vram_effect_copy_model.csv`.

## 8. Proposed first clean-room milestone

Before adding new story content, build a Butano ROM that reproduces the public demo from recovered data:

1. boot/title → Start launches level 7;
2. load the recovered level/world data;
3. reproduce BG streaming/parallax;
4. spawn actors through the recovered registry;
5. reproduce player/NPC dynamic sprites;
6. reproduce portals and collisions;
7. run the recovered dialogue VM and Messages progression;
8. reproduce the fifth-sketch cliffhanger visually;
9. verify on mGBA and real hardware/flash cart;
10. only then begin new/restored content beyond the demo.

That parity milestone keeps reverse engineering and new game design cleanly separated.

## Graveblood_RE build implementation

The workspace now contains a real buildable Butano shell under `reconstruction/`. Local setup/build/release instructions live in `DEVELOPING_AND_BUILDING.md`. The project keeps Butano pinned to `77dcbcb3d8783596a9f333c64eedbccec77b05dc` and keeps original Graveblood ROM bytes out of the reconstruction build.

The initial shell is intentionally minimal; the architectural mappings below remain the roadmap for replacing it with RE-backed parity code.
