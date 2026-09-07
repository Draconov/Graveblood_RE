#!/usr/bin/env python3
"""Export RE semantics that depend on traced code paths in Graveblood 0.0.1.1.5.2.

This intentionally reads only the canonical latest ROM. Alpha-derived comparisons
live in match_alpha_latest.py and never supply data to these exports.
"""
from __future__ import annotations
import argparse, csv, hashlib, struct
from pathlib import Path

LATEST_SHA256 = "e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b"
ROM_BASE = 0x08000000
INIT_ROM_START = 0xA8D738
INIT_RAM_START = 0x03000788
ROUTE_PTR_TABLE_ROM = 0xA8E7C8
MESSAGE_PTR_TABLE_RAM = 0x030014EC
MESSAGE_RECORD_SIZE = 0x82
WARDROBE_LABELS_ADDR = 0x080198A0
WARDROBE_LABEL_COUNT = 10
WARDROBE_LABEL_SIZE = 20
PLAYER_WARDROBE_DST_OFFSET = 0x2B4
OBJ_TILES_SOURCE = 0x08310654
OBJ_PALETTE_SOURCE = 0x08366E58
OBJ_INITIAL_COPY_BYTES = 0x8000
OBJ_TILE_BYTES_8BPP = 64
NPC_SOURCE_BIAS_RAM = 0x030007FC
NPC_DRAW_FUNCTION = 0x0800274C
NPC_DYNAMIC_UPLOAD_FUNCTION = 0x08004F04
STORY_ENTITY_OVERLAY_SLOTS = (0x0300083C, 0x03000840)
STORY_ENTITY_LIST_LOADER = 0x080010A4
STORY_ENTITY_LEVEL_GATE = 0x080043AC


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def init_ram_to_rom_off(addr: int) -> int:
    if addr < INIT_RAM_START:
        raise ValueError(hex(addr))
    return INIT_ROM_START + (addr - INIT_RAM_START)


def fixed_cstr(data: bytes, off: int, size: int) -> str:
    return data[off:off+size].split(b"\0", 1)[0].decode("ascii", errors="replace")


SPAWN_FACTORY_SPECS = (
    {
        "spawn_type": "npc",
        "literal_addr": 0x08A8C2C0,
        "registration_function": 0x0800D968,
        "factory": 0x08003A60,
        "allocation_bytes": 0xFC,
        "constructor": 0x08003998,
        "vtable": 0x08018B00,
        "object_class": "npc",
    },
    {
        "spawn_type": "grass",
        "literal_addr": 0x08A8C2C4,
        "registration_function": 0x0800D968,
        "factory": 0x08002914,
        "allocation_bytes": 0x6C,
        "constructor": None,
        "vtable": 0x08018AD8,
        "object_class": "grass/leaves",
    },
    {
        "spawn_type": "fgtile",
        "literal_addr": 0x08A8C2CC,
        "registration_function": 0x0800DBB4,
        "factory": 0x08003AEC,
        "allocation_bytes": 0x90,
        "constructor": None,
        "vtable": 0x08018E4C,
        "object_class": "foreground tile",
    },
)


def extract_spawn_factories(data: bytes) -> list[dict]:
    """Return the code-proven spawnType -> concrete runtime factory registry.

    Registration functions build the literal keys ``npc``, ``grass`` and
    ``fgtile`` and bind the Thumb factory pointers listed here.  The literal
    strings are checked against the canonical ROM so stale address labels fail
    loudly instead of producing a plausible-but-wrong CSV.
    """
    rows = []
    for spec in SPAWN_FACTORY_SPECS:
        literal_off = spec["literal_addr"] - ROM_BASE
        if literal_off < 0 or literal_off >= len(data):
            raise ValueError(f"spawn literal outside ROM: 0x{spec['literal_addr']:08X}")
        actual = data[literal_off:literal_off + len(spec["spawn_type"])].decode("ascii", errors="replace")
        if actual != spec["spawn_type"]:
            raise ValueError(
                f"spawn literal mismatch at 0x{spec['literal_addr']:08X}: "
                f"expected {spec['spawn_type']!r}, got {actual!r}"
            )
        rows.append({
            "spawn_type": spec["spawn_type"],
            "literal_rom_addr": f"0x{spec['literal_addr']:08X}",
            "registration_function": f"0x{spec['registration_function']:08X}",
            "factory": f"0x{spec['factory']:08X}",
            "allocation_bytes": f"0x{spec['allocation_bytes']:X}",
            "constructor": f"0x{spec['constructor']:08X}" if spec["constructor"] is not None else "inline in factory",
            "vtable": f"0x{spec['vtable']:08X}",
            "object_class": spec["object_class"],
            "confidence": "high",
        })
    return rows


def extract_story_entity_overlay_slots(data: bytes) -> list[dict]:
    """Decode the two initialized story-entity overlay list slots.

    load_level_record_resources (0x08005950) selects one slot using a
    scene-manager index, calls 0x080010A4 with that list, then calls the same
    loader again with the physical level actor list from LevelRecord+0x38.
    Actor policy 0x080043AC subsequently applies per-entity ``level`` gating.
    """
    rows = []
    for slot_id, ram_addr in enumerate(STORY_ENTITY_OVERLAY_SLOTS):
        init_off = init_ram_to_rom_off(ram_addr)
        ptr = struct.unpack_from("<I", data, init_off)[0]
        rows.append({
            "slot": slot_id,
            "slot_iwram": f"0x{ram_addr:08X}",
            "initializer_rom_addr": f"0x{ROM_BASE + init_off:08X}",
            "actor_list_ptr": f"0x{ptr:08X}",
            "loader_function": f"0x{STORY_ENTITY_LIST_LOADER:08X}",
            "level_record_actor_field": "+0x38",
            "level_gate_function": f"0x{STORY_ENTITY_LEVEL_GATE:08X}",
            "confidence": "high",
        })
    return rows


def extract_npc_sprite_pipeline(data: bytes) -> list[dict]:
    """Export code-backed NPC dynamic-OBJ source selection facts.

    NPC draw 0x0800274C reads an initialized source-bank base from IWRAM
    0x030007FC. Startup maps ROM offset 0xA8D738 to IWRAM 0x03000788,
    making the source initializer a directly recoverable ROM dword.
    """
    init_off = init_ram_to_rom_off(NPC_SOURCE_BIAS_RAM)
    value = struct.unpack_from("<I", data, init_off)[0]
    init_rom_addr = ROM_BASE + init_off
    return [
        {"fact":"draw", "value":f"0x{NPC_DRAW_FUNCTION:08X}",
         "evidence":"NPC vtable 0x08018B00 draw slot; stages four 16x8 rows and submits two 16x16 sprites"},
        {"fact":"source_bias_iwram", "value":f"0x{NPC_SOURCE_BIAS_RAM:08X}",
         "evidence":"literal at 0x08002910; loaded by staging loop around 0x0800286E"},
        {"fact":"source_bias_initializer_rom", "value":f"0x{init_rom_addr:08X}",
         "evidence":"startup initialized-data mapping ROM 0x08A8D738 -> IWRAM 0x03000788"},
        {"fact":"source_bias_initialized_value", "value":f"0x{value:X}",
         "evidence":"u32 initializer copied to 0x030007FC; no direct writer identified in traced references"},
        {"fact":"source_base_formula",
         "value":"sourceBias + legsColor*8 + subtype + 2*(frame-1)",
         "evidence":"0x0800286E..0x080028A0; frame is actor+0x78 and 1-based"},
        {"fact":"source_rows", "value":"base + {0,16,32,48}",
         "evidence":"staging loop increments row selector 0,8,16,24 then doubles it"},
        {"fact":"dynamic_destination_formula",
         "value":"logical rows 0x60 + 2*(24*A4 + A8 + C8) + {0,0x10,0x20,0x30}",
         "evidence":"NPC draw destination math plus 0x08004F04 halfword-offset semantics"},
        {"fact":"dynamic_obj_upload", "value":f"0x{NPC_DYNAMIC_UPLOAD_FUNCTION:08X}",
         "evidence":"shared ROM-source -> OBJ-VRAM tile staging routine"},
        {"fact":"semantic_warning", "value":"runtime npc class is not synonymous with human NPC",
         "evidence":"standalone state=4 records with subtype=6 render paper/sketch-like graphics through the same class"},
    ]


STATE4_PROGRESS_SELECTOR_RAM = 0x03000620
STATE4_MONSTER_RENDER_FLAG_RAM = 0x0300061C
NORMAL_STORY_STAGE_RAM = 0x030006AC
STATE4_SELECTOR_LITERAL_ROM = 0x08002D18
STATE4_MONSTER_FLAG_LITERAL_ROM = 0x08003388
NORMAL_STORY_STAGE_LITERAL_ROM = 0x08003398


def extract_state4_collection_selector(data: bytes) -> list[dict]:
    """Export the state==4 interaction-progress -> dialogue-script mapping.

    NPC update 0x0800298C constructs six s32 selector values on its stack at
    0x080029D6..0x080029EA: {4,-1,-1,5,6,0}.  The state-4 branch at
    0x08002C24 loads [0x03000620] and indexes that six-entry table.  Pickup
    completion handlers later increment the same global.
    """
    literal_off = STATE4_SELECTOR_LITERAL_ROM - ROM_BASE
    literal = struct.unpack_from("<I", data, literal_off)[0]
    if literal != STATE4_PROGRESS_SELECTOR_RAM:
        raise ValueError(f"state4 selector literal drifted: 0x{literal:08X}")

    # Verify the compact constant-building instruction sequence before exposing
    # the derived selector table.  These are exact Thumb halfwords from the
    # canonical ROM, not a guessed narrative ordering.
    code_off = 0x29D6
    expected_halfwords = (0x2204, 0x2000, 0x920C, 0x3A05, 0x920D, 0x920E,
                          0x3206, 0x920F, 0x3201, 0x9011, 0x9210)
    actual = struct.unpack_from(f"<{len(expected_halfwords)}H", data, code_off)
    if actual != expected_halfwords:
        raise ValueError("state4 selector construction no longer matches canonical code")

    scripts = (4, -1, -1, 5, 6, 0)
    roles = (
        "first collection dialogue",
        "silent collection",
        "silent collection",
        "rusty key dialogue",
        "final sketch / monster transition",
        "post-completion fallback",
    )
    return [
        {
            "progress_index": index,
            "dialogue_script": script,
            "script_role": roles[index],
            "selector_global": f"0x{STATE4_PROGRESS_SELECTOR_RAM:08X}",
            "selector_dispatch": "0x08002C24",
            "completion_behavior": (
                "completed state-4 interaction increments selector; most completion paths also move entity y to -100"
                if index < 5 else
                "fallback state after the five recovered state-4 overlay entities have been consumed"
            ),
            "confidence": "high",
        }
        for index, script in enumerate(scripts)
    ]


def extract_story_entity_identities() -> list[dict]:
    """Conservative semantic labels for the 16 code-proven story-overlay records.

    Only names supported by both dialogue selection and overlay metadata are
    promoted to character identities.  Records 11..15 are deliberately labeled
    by role rather than as people: their state-4 path and shared paper/sketch
    graphics prove they are collection interactables implemented with the npc
    runtime class.
    """
    rows = []
    for index in range(16):
        row = {
            "index": index,
            "identity": "unidentified",
            "semantic_role": "story-controlled entity",
            "identity_confidence": "unknown",
            "evidence": "no narrative identity assigned without dialogue+metadata proof",
        }
        if index == 4:
            row.update({
                "identity": "IQ 54",
                "semantic_role": "walking story character",
                "identity_confidence": "high",
                "evidence": "overlay #4 has dial=2, state=3, route=0; script 2 is spoken by IQ 54 and asks Vika to find five sketches",
            })
        elif index == 10:
            row.update({
                "identity": "Katya",
                "semantic_role": "story character",
                "identity_confidence": "high",
                "evidence": "overlay #10 has dial=3; script 3 is Katya's sister/bicycle conversation",
            })
        elif 11 <= index <= 15:
            row.update({
                "semantic_role": "collection pickup",
                "identity_confidence": "high",
                "evidence": "five overlay records share state=4 and the paper/sketch source family; IQ script 2 explicitly asks for five sketches",
            })
        rows.append(row)
    return rows


FGTILE_COLLECTION_PROGRESS_LITERAL_ROM = 0x08003ED8
FGTILE_COLLECTION_BRANCH_ROM = 0x08003BDC
FGTILE_PRE_KEY_ENTRY = 0x08003BE6
FGTILE_POST_KEY_ENTRY = 0x0800404A


def extract_level10_collection_gate_policy(data: bytes) -> list[dict]:
    """Export the code-proven collection-index gate behavior for level 10.

    Four level-10 Fgtile records form a 2x2 cluster at x=808/824, y=352/384,
    carry turn=4/5 and portTo=8.  Fgtile update reads the same state-4
    collection counter at 0x03000620.  Values <=3 take the pre-key branch;
    values >3 jump to a separate collision/interaction branch at 0x0800404A.

    The machine code proves activation after the rusty-key collection, but this
    export intentionally does not claim that 0x0800404A itself performs the
    eventual scene transition on that exact frame.
    """
    literal = struct.unpack_from("<I", data, FGTILE_COLLECTION_PROGRESS_LITERAL_ROM - ROM_BASE)[0]
    if literal != STATE4_PROGRESS_SELECTOR_RAM:
        raise ValueError(f"fgtile collection selector literal drifted: 0x{literal:08X}")

    # ldr r3,[pc,#0x2f8]; ldr r3,[r3]; cmp r3,#3; ble pre; b post
    expected = (0x4BBE, 0x681B, 0x2B03, 0xDD00, 0xE231)
    actual = struct.unpack_from("<5H", data, FGTILE_COLLECTION_BRANCH_ROM - ROM_BASE)
    if actual != expected:
        raise ValueError("fgtile collection-index branch no longer matches canonical code")

    common = {
        "selector_global": f"0x{STATE4_PROGRESS_SELECTOR_RAM:08X}",
        "fgtile_update": "0x08003B98",
        "affected_level": "10",
        "affected_level10_tiles": "4",
        "tile_metadata": "(808,384)t4; (824,384)t4; (808,352)t5; (824,352)t5; all portTo=8",
        "confidence": "high",
    }
    return [
        {**common, "phase": "pre_key", "progress_condition": "<= 3",
         "entry": f"0x{FGTILE_PRE_KEY_ENTRY:08X}",
         "proven_behavior": "turn=4/5 gate tiles follow the pre-key path and return without entering the post-key collision/interaction machinery"},
        {**common, "phase": "post_key", "progress_condition": "> 3",
         "entry": f"0x{FGTILE_POST_KEY_ENTRY:08X}",
         "proven_behavior": "turn=4/5 gate tiles enter a distinct collision/interaction branch after the rusty-key collection advances progress 3->4; direct scene-transition timing remains unresolved"},
    ]


def extract_dialogue_context_semantics() -> list[dict]:
    """Return opcode semantics separated by interpreter context.

    Normal state-1/2 dialogue dispatch around 0x08002F76 and state-4 pickup
    dispatch around 0x080031D0 share record layout but *not* all opcode
    meanings.  Keeping context explicit prevents the old v3 mistake of
    universalizing state-4 -5 as a global dialogue opcode.
    """
    rows = [
        {"context":"normal", "opcode":-1, "semantic":"set dialogue step",
         "target":"actor+0x70", "proven_behavior":"writes record argument to actor+0x70", "handler":"0x08003510", "confidence":"high"},
        {"context":"normal", "opcode":-2, "semantic":"set primary message stream",
         "target":"0x03001814", "proven_behavior":"writes record argument to primary message selector", "handler":"0x0800345C", "confidence":"high"},
        {"context":"normal", "opcode":-3, "semantic":"add auxiliary message stream",
         "target":"0x03001810/0C/08", "proven_behavior":"writes record argument to first free auxiliary message-selector slot", "handler":"0x0800339C", "confidence":"high"},
        {"context":"normal", "opcode":-4, "semantic":"set story/progression stage",
         "target":f"0x{NORMAL_STORY_STAGE_RAM:08X}", "proven_behavior":"writes record argument to story stage consumed by Messages indexing", "handler":"0x080032C8", "confidence":"high"},
        {"context":"normal", "opcode":-5, "semantic":"generic record action fallback",
         "target":"0x08005720", "proven_behavior":"not specially dispatched; falls through generic path which calls 0x08005720 with the record argument", "handler":"0x08002F88", "confidence":"high"},
        {"context":"state4_pickup", "opcode":-1, "semantic":"set dialogue step and consume interaction",
         "target":"actor+0x70", "proven_behavior":"writes record argument to actor+0x70, increments 0x03000620 and moves entity y to -100", "handler":"0x08003742", "confidence":"high"},
        {"context":"state4_pickup", "opcode":-2, "semantic":"set primary message stream and consume interaction",
         "target":"0x03001814", "proven_behavior":"writes record argument to primary selector, increments 0x03000620 and moves entity y to -100", "handler":"0x08003688", "confidence":"high"},
        {"context":"state4_pickup", "opcode":-3, "semantic":"add auxiliary message stream and consume interaction",
         "target":"0x03001810/0C/08", "proven_behavior":"uses first-free auxiliary selector policy, increments 0x03000620 and moves entity y to -100", "handler":"0x08003894", "confidence":"high"},
        {"context":"state4_pickup", "opcode":-4, "semantic":"enable monster render mode",
         "target":f"0x{STATE4_MONSTER_RENDER_FLAG_RAM:08X}", "proven_behavior":"sets 1 (derived as opcode+5) and advances to the next dialogue record; does not write the record argument", "handler":"0x080031E6", "confidence":"high"},
        {"context":"state4_pickup", "opcode":-5, "semantic":"trigger final-sketch monster/effect sequence",
         "target":"0x080037F6", "proven_behavior":"calls 0x08004FE0, plays SFX 13, sets 0x03000678=1, increments 0x03000620, moves entity y to -100 and clears dialogue", "handler":"0x080037F6", "confidence":"high"},
    ]
    return rows


def extract_wardrobe_labels(data: bytes) -> list[dict]:
    """Decode the ten fixed-width labels copied by Player ctor 0x0800621C.

    The constructor copies 0xC8 bytes from 0x080198A0 to player+0x2B4,
    therefore the table is exactly ten 20-byte slots. Semantic availability
    beyond the literal labels is deliberately not inferred here.
    """
    source_off = WARDROBE_LABELS_ADDR - ROM_BASE
    rows = []
    for slot in range(WARDROBE_LABEL_COUNT):
        off = source_off + slot * WARDROBE_LABEL_SIZE
        label = fixed_cstr(data, off, WARDROBE_LABEL_SIZE)
        rows.append({
            "slot": slot,
            "source_rom_addr": f"0x{ROM_BASE + off:08X}",
            "source_rom_offset": f"0x{off:08X}",
            "player_object_offset": f"+0x{PLAYER_WARDROBE_DST_OFFSET + slot * WARDROBE_LABEL_SIZE:X}",
            "label": label,
            "literal_status": (
                "named" if label and label.strip() != "Not for demo"
                else "not_for_demo_literal" if label.strip() == "Not for demo"
                else "empty"
            ),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data"))
    args = ap.parse_args()
    data = args.rom.read_bytes()
    got = sha256(data)
    if got != LATEST_SHA256:
        raise SystemExit(f"Latest ROM hash mismatch: {got}")
    args.out.mkdir(parents=True, exist_ok=True)

    wardrobe_rows = extract_wardrobe_labels(data)
    write_csv(args.out / "wardrobe_labels.csv",
              ["slot","source_rom_addr","source_rom_offset","player_object_offset","label","literal_status"],
              wardrobe_rows)

    spawn_factory_rows = extract_spawn_factories(data)
    write_csv(args.out / "spawn_type_factories.csv",
              ["spawn_type","literal_rom_addr","registration_function","factory","allocation_bytes",
               "constructor","vtable","object_class","confidence"],
              spawn_factory_rows)

    npc_sprite_rows = extract_npc_sprite_pipeline(data)
    write_csv(args.out / "npc_sprite_pipeline.csv", ["fact","value","evidence"], npc_sprite_rows)

    story_overlay_rows = extract_story_entity_overlay_slots(data)
    write_csv(args.out / "story_entity_overlay_slots.csv",
              ["slot","slot_iwram","initializer_rom_addr","actor_list_ptr","loader_function",
               "level_record_actor_field","level_gate_function","confidence"],
              story_overlay_rows)

    obj_source_bytes = OBJ_PALETTE_SOURCE - OBJ_TILES_SOURCE
    obj_rows = [{
        "obj_tiles_source": f"0x{OBJ_TILES_SOURCE:08X}",
        "obj_palette_source": f"0x{OBJ_PALETTE_SOURCE:08X}",
        "initial_obj_upload_bytes": f"0x{OBJ_INITIAL_COPY_BYTES:X}",
        "logical_8bpp_tile_bytes": OBJ_TILE_BYTES_8BPP,
        "initial_logical_tiles": OBJ_INITIAL_COPY_BYTES // OBJ_TILE_BYTES_8BPP,
        "complete_source_tiles_before_palette": obj_source_bytes // OBJ_TILE_BYTES_8BPP,
        "source_bytes_remainder_before_palette": obj_source_bytes % OBJ_TILE_BYTES_8BPP,
        "obj_mapping": "2D (DISPCNT bit 6 clear)",
        "oam_submit_function": "0x0800A8F0",
        "dynamic_upload_function": "0x08004F04",
    }]
    write_csv(args.out / "obj_graphics_summary.csv", list(obj_rows[0]), obj_rows)

    player_rows = [
        {"fact":"factory", "value":"0x08006418", "evidence":"player actor registration/factory chain"},
        {"fact":"constructor", "value":"0x0800621C", "evidence":"factory target initializes Player object"},
        {"fact":"vtable", "value":"0x08019688", "evidence":"Player object vtable used by draw dispatch"},
        {"fact":"draw", "value":"0x080065FC", "evidence":"stages dynamic OBJ rows then submits player sprites"},
        {"fact":"dynamic_obj_upload", "value":"0x08004F04", "evidence":"ROM OBJ source -> OBJ VRAM tile copy"},
        {"fact":"oam_submit", "value":"0x0800A8F0", "evidence":"constructs 8-byte OAM entries"},
        {"fact":"graphics_stride_field", "value":"player+0x1DC = 192", "evidence":"constructor writes 0xC0; player draw multiplies animation/bank selection by field"},
        {"fact":"wardrobe_labels", "value":"10 slots x 20 bytes @ 0x080198A0 -> player+0x2B4", "evidence":"constructor copies 0xC8 bytes"},
        {"fact":"shared_avatar_menu_state", "value":"0x03001254", "evidence":"Player_draw reads first fields; Wardrobe UI consumes later/shared fields; semantics not reduced to outfit index"},
        {"fact":"known_character_source_sample", "value":"source base 2198", "evidence":"valid 16x32 Vika-style frame reconstruction; not claimed as constructor/default outfit"},
        {"fact":"initialized_branch_candidate", "value":"source base 3468 if player+0x1E0 == 0", "evidence":"derived from initialized globals and 0x08006B3A branch; allocator/default for +0x1E0 not yet proven"},
    ]
    write_csv(args.out / "player_sprite_pipeline.csv", ["fact","value","evidence"], player_rows)

    # Five pointer slots; state==3 uses route id, actor+0xF8 waypoint index,
    # and wraps after six (x,y) s32 pairs.
    route_rows = []
    route_ptrs = [struct.unpack_from("<I", data, ROUTE_PTR_TABLE_ROM + i*4)[0] for i in range(5)]
    assert struct.unpack_from("<I", data, ROUTE_PTR_TABLE_ROM + 20)[0] == 0
    for route_id, ptr in enumerate(route_ptrs):
        assert ROM_BASE <= ptr < ROM_BASE + len(data), hex(ptr)
        off = ptr - ROM_BASE
        for waypoint in range(6):
            x, y = struct.unpack_from("<ii", data, off + waypoint*8)
            route_rows.append({
                "route_id": route_id, "route_ptr": f"0x{ptr:08X}",
                "route_rom_offset": f"0x{off:08X}", "waypoint_index": waypoint,
                "x": x, "y": y,
            })
    write_csv(args.out / "npc_routes.csv",
              ["route_id","route_ptr","route_rom_offset","waypoint_index","x","y"], route_rows)

    state_rows = [
        {"state":0,"dispatch_address":"default/return","working_name":"default","proven_behavior":"no special state branch in 0x0800298C dispatch","confidence":"high"},
        {"state":1,"dispatch_address":"0x08002ACA","working_name":"interaction_mode_1","proven_behavior":"player proximity query; A-button rising-edge can start dialogue","confidence":"medium"},
        {"state":2,"dispatch_address":"0x08002A0C","working_name":"interaction_mode_2","proven_behavior":"spatial/proximity interaction variant; A-button rising-edge can start dialogue","confidence":"medium"},
        {"state":3,"dispatch_address":"0x08002B72","working_name":"route_follow","proven_behavior":"uses actor.route (+0x64), actor waypoint index (+0xF8), six (x,y) waypoints; loops index after 5","confidence":"high"},
        {"state":4,"dispatch_address":"0x08002C0C","working_name":"interaction_mode_4","proven_behavior":"third spatial/proximity interaction variant; can enter dialogue","confidence":"medium"},
    ]
    write_csv(args.out / "npc_state_modes.csv",
              ["state","dispatch_address","working_name","proven_behavior","confidence"], state_rows)

    field_rows = [
        {"property":"level","actor_offset":"+0x56","semantic":"level filter","proven_behavior":"if value != -1 and != current level (0x03000808), virtual method at vtable+0x18 is invoked","confidence":"high"},
        {"property":"setglobal","actor_offset":"+0x58","semantic":"inherited culling-policy control","proven_behavior":"if value == 0, byte actor+0x31 is set to 1; inherited object manager skips normal spatial/camera-cull path when +0x31 != 0","confidence":"high for machine behavior; original naming polarity unresolved"},
        {"property":"state","actor_offset":"+0x5A","semantic":"NPC behavior/interaction mode enum","proven_behavior":"dispatches states 1,2,3,4 inside 0x0800298C; state 3 is route following","confidence":"high"},
        {"property":"dial","actor_offset":"+0x5C","semantic":"dialogue script index","proven_behavior":"indexes pointer table at 0x0300078C","confidence":"high"},
        {"property":"route","actor_offset":"+0x64","semantic":"NPC route index","proven_behavior":"state 3 indexes route pointer table at 0x03001818 and follows six waypoints","confidence":"high"},
    ]
    write_csv(args.out / "new_actor_field_semantics.csv",
              ["property","actor_offset","semantic","proven_behavior","confidence"], field_rows)

    # v4: opcode meaning is interpreter-context dependent.  Keep the old
    # filename as a normal-context compatibility view and add the explicit
    # context matrix as the authoritative export.
    context_rows = extract_dialogue_context_semantics()
    normal_by_opcode = {row["opcode"]: row for row in context_rows if row["context"] == "normal"}
    opcode_rows = [{"opcode":0,"semantic":"normal dialogue/content record",
                    "proven_behavior":"generic content/action path", "confidence":"high"}]
    for opcode in (-1, -2, -3, -4, -5):
        row = normal_by_opcode[opcode]
        opcode_rows.append({"opcode":opcode, "semantic":row["semantic"],
                            "proven_behavior":row["proven_behavior"], "confidence":row["confidence"]})
    write_csv(args.out / "dialogue_opcode_semantics.csv",
              ["opcode","semantic","proven_behavior","confidence"], opcode_rows)
    write_csv(args.out / "dialogue_context_semantics.csv",
              ["context","opcode","semantic","target","proven_behavior","handler","confidence"], context_rows)

    state4_rows = extract_state4_collection_selector(data)
    write_csv(args.out / "state4_collection_progression.csv",
              ["progress_index","dialogue_script","script_role","selector_global","selector_dispatch",
               "completion_behavior","confidence"], state4_rows)

    identity_rows = extract_story_entity_identities()
    write_csv(args.out / "story_entity_identities.csv",
              ["index","identity","semantic_role","identity_confidence","evidence"], identity_rows)

    gate_rows = extract_level10_collection_gate_policy(data)
    write_csv(args.out / "level10_collection_gate_policy.csv",
              ["phase","progress_condition","entry","selector_global","fgtile_update","affected_level",
               "affected_level10_tiles","tile_metadata","proven_behavior","confidence"], gate_rows)

    # Message selectors and the stream pointer table are initialized in the ROM->IWRAM block.
    ptr_off = init_ram_to_rom_off(MESSAGE_PTR_TABLE_RAM)
    stream_ptrs = [struct.unpack_from("<I", data, ptr_off + i*4)[0] for i in range(3)]
    assert struct.unpack_from("<I", data, ptr_off + 12)[0] == 0
    message_rows = []
    for stream_id, ram_ptr in enumerate(stream_ptrs):
        source_off = init_ram_to_rom_off(ram_ptr)
        for stage in range(2):
            off = source_off + stage*MESSAGE_RECORD_SIZE
            message_rows.append({
                "stream_id": stream_id, "stream_ram_ptr": f"0x{ram_ptr:08X}",
                "source_rom_offset": f"0x{off:08X}", "story_stage": stage,
                "title": fixed_cstr(data, off, 15),
                "sender": fixed_cstr(data, off+15, 15),
                "body": fixed_cstr(data, off+30, 100),
            })
    write_csv(args.out / "message_streams.csv",
              ["stream_id","stream_ram_ptr","source_rom_offset","story_stage","title","sender","body"], message_rows)

    selector_rows = [
        {"address":"0x03001814","role":"primary","initial_value":-1,"writer":"dialogue opcode -2"},
        {"address":"0x03001810","role":"auxiliary #1","initial_value":-1,"writer":"dialogue opcode -3 first-free policy"},
        {"address":"0x0300180C","role":"auxiliary #2","initial_value":-1,"writer":"dialogue opcode -3 first-free policy"},
        {"address":"0x03001808","role":"auxiliary #3","initial_value":-1,"writer":"dialogue opcode -3 first-free policy"},
    ]
    for r in selector_rows:
        off = init_ram_to_rom_off(int(r["address"],16))
        assert struct.unpack_from("<i", data, off)[0] == -1
    write_csv(args.out / "message_selectors.csv",
              ["address","role","initial_value","writer"], selector_rows)

    print(f"exported {len(route_rows)} route waypoints, {len(message_rows)} message records, {len(state_rows)} NPC state modes, {len(wardrobe_rows)} wardrobe labels, {len(spawn_factory_rows)} spawn factories")

if __name__ == "__main__":
    main()
