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

The original demo's opcode `-5` path performs deliberately extreme expanding VRAM copies. A Butano rebuild should **not blindly reproduce raw out-of-range VRAM writes** merely because the binary does them.

First frame-trace the canonical ROM in mGBA/hardware and determine the intended visible effect. Then reproduce that visual result safely with managed BG/sprite data or a narrowly isolated low-level routine if direct hardware behavior is actually required.

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
