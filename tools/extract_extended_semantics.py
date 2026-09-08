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
PLAYER_WARDROBE_SELECTOR_OFFSET = 0x240
PLAYER_WARDROBE_PREVIEW_OBJ_OFFSET = 0x244
PLAYER_WARDROBE_PREVIEW_BG_OFFSET = 0x27C
WARDROBE_PREVIEW_OBJ_ROM = 0x080197B0
WARDROBE_PREVIEW_BG_ROM = 0x080197E8
WARDROBE_PREVIEW_TABLE_COUNT = 14
WARDROBE_NORMAL_CHOICE_COUNT = 7
WARDROBE_LABEL_DRAW = 0x08006430
WARDROBE_PLAYER_UPDATE_PATH = 0x08008E30
WARDROBE_TITLE_ADDR = 0x08A8C47C
WARDROBE_EXIT_PROMPT_ADDR = 0x08A8C488
PLAYER_ANIMATION_STATE_RAM = 0x03001254
PLAYER_LIVE_GRAPHICS_BANK_RAM = 0x0300103C
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
        elif index == 5:
            row.update({
                "identity": "Stas",
                "semantic_role": "social-interaction character",
                "identity_confidence": "high",
                "evidence": "overlay #5 is state=1,dial=0; the sole state-1 social bootstrap copies dial to profile selector 0, whose proper social profile name is Stas",
            })
        elif index == 6:
            row.update({
                "identity": "Julia",
                "semantic_role": "social-interaction character",
                "identity_confidence": "high",
                "evidence": "overlay #6 is state=1,dial=1; the sole state-1 social bootstrap copies dial to profile selector 1, whose proper social profile name is Julia",
            })
        elif index == 9:
            row.update({
                "identity": "IQ 54",
                "semantic_role": "story character",
                "identity_confidence": "high",
                "evidence": "overlay #9 is level=10, state=2, dial=2; dial is the proven dialogue-script index and script 2's speaking NPC is IQ 54",
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
FGTILE_GATE_A_HANDLER = 0x08003D24
FGTILE_GATE_TURN_DISPATCH = 0x08003D48
FGTILE_GATE_TURN4_HANDLER = 0x080042AE
FGTILE_GATE_TURN5_HANDLER = 0x080042C4
FGTILE_GENERIC_PORTAL_HANDOFF = 0x08004258
PLAYER_APPLY_VERTICAL_TARGET = 0x080080A4
PLAYER_TARGET_X_OFFSET = 0x390
PLAYER_TARGET_Y_OFFSET = 0x394
PLAYER_VERTICAL_DELTA_OFFSET = 0x1C
KEYS_CURRENT_LITERAL_ROM = 0x08003EE0
KEYS_PREVIOUS_LITERAL_ROM = 0x08003EE4
KEYS_CURRENT_RAM = 0x030006BC
KEYS_PREVIOUS_RAM = 0x030006C0
GATE_TARGET_X_LITERAL_ROM = 0x0800432C

PLAYER_INTERACTION_ACTIVE_RAM = 0x03000610
PLAYER_INTERACTION_SOURCE = 0x08002FCE
PLAYER_INTERACTION_DISPATCH = 0x08008BC8
PLAYER_INTERACTION_ALIGN_ENTRY = 0x0800921A
PLAYER_INTERACTION_ALIGN_RIGHT_BRANCH = 0x08009220
PLAYER_INTERACTION_ALIGN_LEFT_BRANCH = 0x08009552
PLAYER_INTERACTION_STATE_OFFSET = 0x1EC
PLAYER_DIALOGUE_INDEX_OFFSET = 0x388
PLAYER_MOTION_SOLVER = 0x08004670
PLAYER_NORMAL_ANCHOR_RESET = 0x0800842A
PLAYER_HORIZONTAL_DELTA_OFFSET = 0x18
PLAYER_INTERACTION_SEPARATION_FIXED = 0x1300
PLAYER_INTERACTION_ACTION_TABLE = 0x08018738
PLAYER_INTERACTION_ACTION_RECORD_SIZE = 0x2C
PLAYER_INTERACTION_ACTION_LABEL_SIZE = 0x1C
PLAYER_INTERACTION_ACTION_COUNT = 20
PLAYER_INTERACTION_CHOICE_OFFSET = 0x1E4
PLAYER_INTERACTION_PAGE_BASE_OFFSET = 0x1E8
PLAYER_INTERACTION_STATE0_TO_1 = 0x080092C0
PLAYER_INTERACTION_STATE1_CONTROLS = 0x08009794
PLAYER_INTERACTION_BRANCH_COMMIT = 0x08009C3E
PLAYER_INTERACTION_STATE2_RETURN_DISPATCH = 0x08008C7C
PLAYER_INTERACTION_STATE2_RETURN = 0x08009CB6
PLAYER_INTERACTION_STATE2_ENTRY = 0x08009DDA
PLAYER_INTERACTION_STATE3_TEARDOWN = 0x0800963E
PLAYER_INTERACTION_SECONDARY_LIST_BUILDER = 0x08006E00
PLAYER_INTERACTION_SECONDARY_TOPIC_TABLE = 0x080114B4
PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE = 15
PLAYER_INTERACTION_PROFILE_TABLE_RAM = 0x0300110C
PLAYER_INTERACTION_SUBJECT_RESPONSE_PTR_TABLE_RAM = 0x030007D4
PLAYER_INTERACTION_CRITICIZE_RESPONSE_PTR_TABLE_RAM = 0x030007AC
PLAYER_INTERACTION_RESPONSE_STRIDE = 108
PLAYER_INTERACTION_NEUTRAL_RESPONSE = 0x08A8C494
PLAYER_INTERACTION_STATE2_CURSOR_OFFSET = 0x1F0
PLAYER_INTERACTION_SECONDARY_FLAG_OFFSET = 0x382
PLAYER_INTERACTION_DEPTH_OFFSET = 0x38C
PLAYER_INTERACTION_RESPONSE_DISPATCH = 0x08009200
PLAYER_INTERACTION_STATE2_FRESH_A_GATE = 0x0800960E
PLAYER_INTERACTION_SOCIAL_PROFILE_RECORD_SIZE = 0x3C
PLAYER_INTERACTION_NPC_METADATA_RECORD_SIZE = 0x30
PLAYER_INTERACTION_PROFILE_NAME_SIZE = 0x10
PLAYER_INTERACTION_PROFILE_FIELD10 = 0x10
PLAYER_INTERACTION_PROFILE_FIELD14 = 0x14
PLAYER_INTERACTION_PROFILE_TOPIC_BASE = 0x18
PLAYER_INTERACTION_PROFILE_SCORE_UPDATE = 0x08009504
NPC_ACTOR_TYPE_KEY = 0x08A8C2E0
NPC_UPDATE_FUNCTION = 0x0800298C
NPC_STATE1_ENTRY = 0x08002ACA
NPC_STATE1_SOCIAL_HANDOFF = 0x08002B52
NPC_SOCIAL_PRELUDE = 0x08002FA2
NPC_SOCIAL_BOOTSTRAP = 0x08002FCE

ENDING_VRAM_EFFECT = 0x08004FE0
ENDING_VRAM_LITERALS = 0x08005038
COPY_BYTES_HELPER = 0x08010C54


def _unpack_halfwords(data: bytes, addr: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f"<{count}H", data, addr - ROM_BASE)


def _rom_cstr(data: bytes, addr: int, max_len: int = 128) -> str | None:
    if not (ROM_BASE <= addr < ROM_BASE + len(data)):
        return None
    off = addr - ROM_BASE
    end = data.find(b"\0", off, min(len(data), off + max_len))
    if end < 0:
        return None
    raw = data[off:end]
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def _parse_serialized_actor(data: bytes, off: int) -> tuple[dict[str, str], int] | None:
    if off < 0 or off + 8 > len(data) or struct.unpack_from("<I", data, off)[0] != NPC_ACTOR_TYPE_KEY:
        return None
    props: dict[str, str] = {}
    p = off
    for _ in range(64):
        if p + 4 > len(data):
            return None
        key_addr = struct.unpack_from("<I", data, p)[0]
        if key_addr == 0:
            return props, p + 4
        if p + 8 > len(data):
            return None
        value_addr = struct.unpack_from("<I", data, p + 4)[0]
        key = _rom_cstr(data, key_addr)
        value = _rom_cstr(data, value_addr)
        if key is None or value is None:
            return None
        props.setdefault(key, value)
        p += 8
    return None


def _scan_serialized_actors(data: bytes) -> list[tuple[int, dict[str, str]]]:
    needle = struct.pack("<I", NPC_ACTOR_TYPE_KEY)
    out: dict[int, dict[str, str]] = {}
    start = 0
    while True:
        off = data.find(needle, start)
        if off < 0:
            break
        if off % 4 == 0:
            parsed = _parse_serialized_actor(data, off)
            if parsed is not None:
                out[off] = parsed[0]
        start = off + 1
    return sorted(out.items())


def _thumb_unconditional_b_target(addr: int, halfword: int) -> int | None:
    if halfword & 0xF800 != 0xE000:
        return None
    imm11 = halfword & 0x07FF
    if imm11 & 0x0400:
        imm11 -= 0x0800
    return addr + 4 + (imm11 << 1)


def _thumb_literal_refs_to(data: bytes, literal_value: int, start_addr: int = 0x08000000,
                           end_addr: int = 0x08018000) -> list[int]:
    refs = []
    start = max(start_addr, ROM_BASE)
    end = min(end_addr, ROM_BASE + len(data))
    for addr in range(start, end, 2):
        hw = struct.unpack_from("<H", data, addr - ROM_BASE)[0]
        if hw & 0xF800 != 0x4800:
            continue
        literal_addr = ((addr + 4) & ~3) + ((hw & 0xFF) << 2)
        if literal_addr + 4 > ROM_BASE + len(data):
            continue
        value = struct.unpack_from("<I", data, literal_addr - ROM_BASE)[0]
        if value == literal_value:
            refs.append(addr)
    return refs


def extract_level10_collection_gate_policy(data: bytes) -> list[dict]:
    """Export the code-proven collection-index gate behavior for level 10.

    Four level-10 Fgtile records form a 2x2 cluster at x=808/824, y=352/384,
    carry turn=4/5 and portTo=8. Fgtile update reads the same state-4
    collection counter at 0x03000620. Values <=3 take the pre-key branch;
    values >3 enter the post-key collision path. The post-key turn=4/5 action
    is now traced separately: on a fresh A press it applies a vertical target
    delta through 0x080080A4. It does not read the actor's portTo field.
    """
    literal = struct.unpack_from("<I", data, FGTILE_COLLECTION_PROGRESS_LITERAL_ROM - ROM_BASE)[0]
    if literal != STATE4_PROGRESS_SELECTOR_RAM:
        raise ValueError(f"fgtile collection selector literal drifted: 0x{literal:08X}")

    # ldr r3,[pc,#0x2f8]; ldr r3,[r3]; cmp r3,#3; ble pre; b post
    expected = (0x4BBE, 0x681B, 0x2B03, 0xDD00, 0xE231)
    actual = _unpack_halfwords(data, FGTILE_COLLECTION_BRANCH_ROM, len(expected))
    if actual != expected:
        raise ValueError("fgtile collection-index branch no longer matches canonical code")

    # Keep the stronger post-key trace tied to the same canonical bytes.
    extract_level10_gate_forced_motion(data)

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
         "proven_behavior": "turn=4/5 gate tiles enter collision/interaction geometry after progress 3->4; a fresh A press dispatches forced vertical target movement, and this active branch does not read portTo or request a scene"},
    ]


def extract_level10_gate_collision_geometry(data: bytes) -> dict:
    """Decode the exact post-key turn=4/5 gate overlap geometry.

    Positions are 24.8 fixed point. Shifting by 11 therefore converts the
    biased coordinates to an 8-pixel grid. The branch accepts the actor grid
    cell and the adjacent +1 cell on each axis, producing a 2x2 contact area.
    """
    literal_expect = {
        0x080042F4: 0xFFFFF000,  # actor Y bias: -16 px
        0x080042F8: 0xFFFFF800,  # actor/player X bias: -8 px
        0x08004300: 0xFFFFE800,  # player Y bias: -24 px
    }
    for addr, expected in literal_expect.items():
        actual = struct.unpack_from("<I", data, addr - ROM_BASE)[0]
        if actual != expected:
            raise ValueError(f"gate collision literal drifted at 0x{addr:08X}: 0x{actual:08X}")

    # actorY-16px; actorX-8px; playerX-8px, each later shifted by 11.
    xy_bias = (0x68E5, 0x68C2, 0x4445, 0x50E2, 0x002F, 0x68A3,
               0x4DA4, 0x4443, 0x46A8, 0x4441, 0x12CD)
    if _unpack_halfwords(data, 0x08004058, len(xy_bias)) != xy_bias:
        raise ValueError("post-key gate X/actor-Y collision bias path drifted")

    # Load -24px, apply it to player Y, and shift by 11.
    py_bias = (0x49A3, 0x4688, 0x4442, 0x12D2)
    if _unpack_halfwords(data, 0x08004072, len(py_bias)) != py_bias:
        raise ValueError("post-key gate player-Y collision bias path drifted")

    # X accepts AX or AX+1.
    x_compare = (0x429D, 0xD100, 0xE0B4, 0x2600, 0x46B0, 0x46B1,
                 0x3301, 0x429D, 0xD100, 0xE0C5)
    if _unpack_halfwords(data, 0x0800409C, len(x_compare)) != x_compare:
        raise ValueError("post-key gate X overlap test drifted")

    # Y accepts AY or AY+1 on the X==AX branch. The X==AX+1 branch mirrors
    # the same two-cell Y policy through the sibling state path.
    y_compare = (0x45BB, 0xD05D, 0x1C7E, 0x45B3, 0xD047)
    if _unpack_halfwords(data, 0x0800420C, len(y_compare)) != y_compare:
        raise ValueError("post-key gate Y overlap test drifted")

    # Collision state == 1 enters 0x3D24 with r3 still equal to 1. The handler
    # stores it to Fgtile +0x8C/+0x8D and Player +0x1C0.
    contact_entry = (0x6813, 0x2B01, 0xD100, 0xE62C)
    if _unpack_halfwords(data, 0x080040C2, len(contact_entry)) != contact_entry:
        raise ValueError("post-key gate contact entry drifted")
    contact_flags = (0x228C, 0x54A3, 0x3201, 0x54A3, 0x3234, 0x32FF, 0x5483)
    if _unpack_halfwords(data, FGTILE_GATE_A_HANDLER, len(contact_flags)) != contact_flags:
        raise ValueError("post-key gate contact flags drifted")

    return {
        "entry": f"0x{FGTILE_POST_KEY_ENTRY:08X}",
        "player_x_grid": "(playerX-8px)>>11",
        "player_y_grid": "(playerY-24px)>>11",
        "actor_x_grid": "(actorX-8px)>>11",
        "actor_y_grid": "(actorY-16px)>>11",
        "contact_condition": "PX in {AX,AX+1} and PY in {AY,AY+1}",
        "grid_cell_px": 8,
        "player_contact_flag": "+0x1C0=1",
        "fgtile_contact_flags": "+0x8C=1; +0x8D=1",
        "confidence": "high",
    }


def extract_level10_gate_forced_motion(data: bytes) -> list[dict]:
    """Decode the rusty-key gate's post-key turn=4/5 A-button action.

    This deliberately separates the gate action from the generic Fgtile
    ``portTo`` scene handoff at 0x08004258. The turn dispatch jumps directly
    to 0x080042AE/0x080042C4, writes the dual-purpose Player fields
    +0x390/+0x394 and calls the vertical-only helper at 0x080080A4.
    """
    extract_level10_gate_collision_geometry(data)

    if struct.unpack_from("<I", data, KEYS_CURRENT_LITERAL_ROM - ROM_BASE)[0] != KEYS_CURRENT_RAM:
        raise ValueError("current-key literal drifted in Fgtile gate interaction")
    if struct.unpack_from("<I", data, KEYS_PREVIOUS_LITERAL_ROM - ROM_BASE)[0] != KEYS_PREVIOUS_RAM:
        raise ValueError("previous-key literal drifted in Fgtile gate interaction")

    # current-key test, then previous-key test. At this point r3 is the contact
    # bit (1), so this is current A set + previous A clear: a rising edge.
    key_test = (0x4A6B, 0x6812, 0x421A, 0xD012, 0x224C, 0x5EA2,
                0x4694, 0x4A68, 0x6812, 0x421A, 0xD10E)
    if _unpack_halfwords(data, 0x08003D32, len(key_test)) != key_test:
        raise ValueError("Fgtile fresh-A gate trigger no longer matches canonical code")

    # turn 4 -> 0x42AE; turn 5 -> 0x42C4.
    turn_dispatch = (0x4663, 0x2B04, 0xD100, 0xE2AE, 0x2B05, 0xD100, 0xE2B6)
    if _unpack_halfwords(data, FGTILE_GATE_TURN_DISPATCH, len(turn_dispatch)) != turn_dispatch:
        raise ValueError("Fgtile turn=4/5 gate dispatch drifted")

    turn4 = (0x23E5, 0x22B4, 0x009B, 0x0252, 0x50C2, 0x4A1C, 0x3B04, 0x50C2, 0xF003, 0xFEF1)
    turn5 = (0x23E5, 0x22CD, 0x009B, 0xE7F3)
    if _unpack_halfwords(data, FGTILE_GATE_TURN4_HANDLER, len(turn4)) != turn4:
        raise ValueError("Fgtile turn=4 forced-motion handler drifted")
    if _unpack_halfwords(data, FGTILE_GATE_TURN5_HANDLER, len(turn5)) != turn5:
        raise ValueError("Fgtile turn=5 forced-motion handler drifted")

    target_x_fixed = struct.unpack_from("<I", data, GATE_TARGET_X_LITERAL_ROM - ROM_BASE)[0]
    if target_x_fixed != 0x00033A00:
        raise ValueError(f"gate target-X literal drifted: 0x{target_x_fixed:08X}")

    helper = (0x22E5, 0x0092, 0x5883, 0x68C1, 0x1A5B, 0x21E4,
              0x61C3, 0x2300, 0x0089, 0x5043, 0x5083, 0x4770)
    if _unpack_halfwords(data, PLAYER_APPLY_VERTICAL_TARGET, len(helper)) != helper:
        raise ValueError("Player vertical-target helper drifted")

    # The generic portal path explicitly reads actor+0x52 (portTo) and calls
    # request_scene. It is a separate block from the direct gate handlers.
    portal = (0x2352, 0x2200, 0x5EE1, 0x4832, 0x230A, 0xF001, 0xFCE5)
    if _unpack_halfwords(data, FGTILE_GENERIC_PORTAL_HANDOFF, len(portal)) != portal:
        raise ValueError("generic Fgtile portTo scene handoff drifted")

    common = {
        "target_x_px": target_x_fixed // 0x100,
        "target_x_fixed": f"0x{target_x_fixed:08X}",
        "trigger": "fresh A press while overlapping post-key gate collision geometry",
        "keys_current": f"0x{KEYS_CURRENT_RAM:08X}",
        "keys_previous": f"0x{KEYS_PREVIOUS_RAM:08X}",
        "helper": f"0x{PLAYER_APPLY_VERTICAL_TARGET:08X}",
        "player_target_x_offset": f"+0x{PLAYER_TARGET_X_OFFSET:X}",
        "player_target_y_offset": f"+0x{PLAYER_TARGET_Y_OFFSET:X}",
        "player_vertical_delta_offset": f"+0x{PLAYER_VERTICAL_DELTA_OFFSET:X}",
        "helper_behavior": "writes targetY-currentY to Player+0x1C, then clears +0x390/+0x394; target X is not consumed by this helper",
        "generic_portal_handoff": f"0x{FGTILE_GENERIC_PORTAL_HANDOFF:08X}",
        "post_key_reads_portto": "no",
        "confidence": "high",
    }
    return [
        {**common, "turn": 4, "handler": f"0x{FGTILE_GATE_TURN4_HANDLER:08X}",
         "target_y_px": (0xB4 << 9) // 0x100, "target_y_fixed": f"0x{0xB4 << 9:08X}"},
        {**common, "turn": 5, "handler": f"0x{FGTILE_GATE_TURN5_HANDLER:08X}",
         "target_y_px": (0xCD << 9) // 0x100, "target_y_fixed": f"0x{0xCD << 9:08X}"},
    ]


def _thumb1_bl_target(data: bytes, off: int) -> int | None:
    """Decode an ARMv4T two-halfword Thumb BL at a ROM offset."""
    h1, h2 = struct.unpack_from("<HH", data, off)
    if h1 & 0xF800 != 0xF000 or h2 & 0xF800 != 0xF800:
        return None
    high = h1 & 0x07FF
    if high & 0x0400:
        high -= 0x0800
    delta = (high << 12) + ((h2 & 0x07FF) << 1)
    return ROM_BASE + off + 4 + delta


def extract_player_vertical_target_calls(data: bytes) -> list[dict]:
    """Export recovered static callers of Player_apply_vertical_target_delta.

    The scan is limited to the recovered low-ROM executable region. It proves
    that the helper itself never consumes Player+0x390: every call returns only
    after the helper has cleared +0x390/+0x394. A separate NPC interaction path
    consumes both fields without calling this helper.
    """
    expected_calls = (0x08002DD6, 0x080041C8, 0x080042BE)
    hits = []
    for off in range(0, min(len(data) - 2, 0x1A000), 2):
        if _thumb1_bl_target(data, off) == PLAYER_APPLY_VERTICAL_TARGET:
            hits.append(ROM_BASE + off)
    if tuple(hits) != expected_calls:
        raise ValueError(f"vertical-target helper callsites drifted: {[hex(v) for v in hits]}")

    dialogue_setup = (0x22E4, 0x4641, 0x0092, 0x508B, 0x23E5, 0x4642,
                      0x68E9, 0x009B, 0x50D1, 0x4640, 0xF005, 0xF965)
    if _unpack_halfwords(data, 0x08002DC2, len(dialogue_setup)) != dialogue_setup:
        raise ValueError("dialogue vertical-target setup drifted")

    fgtile_setup = (0x23E5, 0x2280, 0x009B, 0x0292, 0x50CA, 0x4640, 0xF003, 0xFF6C)
    if _unpack_halfwords(data, 0x080041BC, len(fgtile_setup)) != fgtile_setup:
        raise ValueError("secondary Fgtile vertical-target setup drifted")

    # Reuse the gate and helper validators for the third call and the exact
    # consume/clear semantics.
    extract_level10_gate_forced_motion(data)

    common = {
        "helper": f"0x{PLAYER_APPLY_VERTICAL_TARGET:08X}",
        "helper_consumes_target_x": "no",
        "helper_consumes_target_y": "yes",
        "helper_clears_target_x": "yes",
        "helper_clears_target_y": "yes",
        "confidence": "high",
    }
    return [
        {**common, "callsite": "0x08002DD6", "context": "NPC/dialogue interaction",
         "target_x_write": "source actor X -> Player+0x390",
         "target_y_write": "source actor Y -> Player+0x394"},
        {**common, "callsite": "0x080041C8", "context": "Fgtile interaction",
         "target_x_write": "none in this call path",
         "target_y_write": "512px -> Player+0x394"},
        {**common, "callsite": "0x080042BE", "context": "rusty-key level-10 turn=4/5 gate",
         "target_x_write": "826px -> Player+0x390",
         "target_y_write": "360px or 410px -> Player+0x394 depending on turn"},
    ]



def extract_player_interaction_action_table(data: bytes) -> list[dict]:
    """Decode the 20-entry NPC interaction action tree at 0x08018738.

    Each 0x2C-byte record starts with a 0x1C-byte fixed label followed by four
    u32 fields.  State-1 confirmation proves +0x20 is the branch/leaf type.
    For branch records (+0x20 == 0), +0x24 is copied into Player+0x1E8 and is
    therefore the base index of the next four-entry page.  The remaining leaf
    payload fields are intentionally exported raw until their action semantics
    are proved.
    """
    expected_labels = [
        "TALK", "FLIRT", "ASSAULT", "SHARE",
        "SUBJECT", "Ask about", "JOKE", "CRITICIZE",
        "KISS CHEEK", "KISS LIPS", "DIRTY JOKE", "BREAKUP",
        "SWEAR", "FIGHT", "unused", "SCAM",
        "GIFT", "ACTIVITY", "A Number", "ASK",
    ]
    rows = []
    for index in range(PLAYER_INTERACTION_ACTION_COUNT):
        addr = PLAYER_INTERACTION_ACTION_TABLE + index * PLAYER_INTERACTION_ACTION_RECORD_SIZE
        off = addr - ROM_BASE
        raw_label = data[off:off + PLAYER_INTERACTION_ACTION_LABEL_SIZE]
        label = raw_label.split(b"\0", 1)[0].decode("ascii")
        visual_selector, node_type, field_24, field_28 = struct.unpack_from("<4I", data, off + 0x1C)
        rows.append({
            "index": index,
            "source_rom_addr": f"0x{addr:08X}",
            "label": label,
            "record_size": PLAYER_INTERACTION_ACTION_RECORD_SIZE,
            "visual_selector": visual_selector,
            "node_type": node_type,
            "field_24": field_24,
            "field_28": field_28,
            "node_role": "submenu" if node_type == 0 else "leaf_action" if node_type == 1 else "unknown",
            "child_base": field_24 if node_type == 0 else "",
            "children": "",
            "confidence": "high" if node_type in (0, 1) else "low",
        })

    if [row["label"] for row in rows] != expected_labels:
        raise ValueError("interaction action-table labels drifted from canonical demo")
    if [row["node_type"] for row in rows[:4]] != [0, 0, 0, 0]:
        raise ValueError("interaction root node types no longer match canonical demo")
    if [row["child_base"] for row in rows[:4]] != [4, 8, 12, 16]:
        raise ValueError("interaction root child bases no longer match canonical demo")
    if any(row["node_type"] != 1 for row in rows[4:]):
        raise ValueError("interaction leaf node types no longer match canonical demo")

    for root in rows[:4]:
        base = root["child_base"]
        root["children"] = "|".join(rows[i]["label"] for i in range(base, base + 4))
    return rows


def extract_player_interaction_secondary_topics(data: bytes) -> list[dict]:
    """Decode the counted secondary-topic lists used by leaf interaction actions.

    The UI builder at 0x08006E00 selects the current 0x2C-byte action record,
    loads record +0x24 as a start index and +0x28 as a count, and returns
    immediately when the count is non-positive.  For positive counts it
    renders fixed 15-byte labels from 0x080114B4.  Therefore +0x24 is only
    assigned the topic-start role on records whose +0x28 count is nonzero.
    """
    # selected = Player+0x1E4 + Player+0x1E8; record size = 44 bytes; then
    # +0x24/+0x28 are loaded and count<=0 exits before any topic-table use.
    prefix = (0x58C2, 0x3304, 0x58C1, 0x3BBD, 0x0004, 0x3BFF, 0x1850, 0x0001,
              0x4359, 0x4BE8, 0x185B, 0x6A59, 0x6A9E)
    if _unpack_halfwords(data, 0x08006E10, len(prefix)) != prefix:
        raise ValueError("interaction secondary-list record selection drifted")
    if _unpack_halfwords(data, 0x08006E38, 3) != (0x2E00, 0xDC00, 0xE18B):
        raise ValueError("interaction secondary-list zero-count exit drifted")

    # r8 = field_24; multiplying by 15 and adding the literal at 0x080071D4
    # yields the first fixed-width topic string.  Keep the adjacent UI-object
    # literal distinct so the two tables cannot be accidentally conflated.
    topic_index_math = (0x4643, 0x0119, 0x1ACB, 0x4698, 0x4BD1, 0x0019,
                        0x4441, 0x4699, 0xF7FB, 0xF9C7)
    if _unpack_halfwords(data, 0x08006E86, len(topic_index_math)) != topic_index_math:
        raise ValueError("interaction secondary-topic string path drifted")
    if struct.unpack_from("<I", data, 0x080071C4 - ROM_BASE)[0] != PLAYER_INTERACTION_ACTION_TABLE:
        raise ValueError("interaction secondary-list action-table literal drifted")
    if struct.unpack_from("<I", data, 0x080071D4 - ROM_BASE)[0] != PLAYER_INTERACTION_SECONDARY_TOPIC_TABLE:
        raise ValueError("interaction secondary-topic table literal drifted")
    if struct.unpack_from("<I", data, 0x080071CC - ROM_BASE)[0] != 0x080199A0:
        raise ValueError("interaction secondary-list UI-object literal drifted")

    expected_topics = [
        "sports", "movies", "fashion", "video games", "school", "future",
        "parties", "last event", "mysteries", "//", "hobbies", "fav. music",
        "best places", "fav. meals", "dreams",
    ]
    topic_off = PLAYER_INTERACTION_SECONDARY_TOPIC_TABLE - ROM_BASE
    topics = [
        fixed_cstr(data, topic_off + i * PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE,
                   PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE)
        for i in range(len(expected_topics))
    ]
    if topics != expected_topics:
        raise ValueError("interaction secondary-topic labels drifted from canonical demo")

    action_rows = extract_player_interaction_action_table(data)
    rows = []
    for action in action_rows[4:]:
        count = action["field_28"]
        if count <= 0:
            continue
        start = action["field_24"]
        if start + count > len(topics):
            raise ValueError(f"secondary-topic range outside recovered table for {action['label']}")
        rows.append({
            "action_index": action["index"],
            "action_label": action["label"],
            "topic_start": start,
            "topic_count": count,
            "topics": "|".join(topics[start:start + count]),
            "builder": f"0x{PLAYER_INTERACTION_SECONDARY_LIST_BUILDER:08X}",
            "topic_table": f"0x{PLAYER_INTERACTION_SECONDARY_TOPIC_TABLE:08X}",
            "topic_stride": PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE,
            "field_24_role": "topic_start when field_28 > 0",
            "field_28_role": "topic_count",
            "zero_count_behavior": "builder exits before field_24 is used as a topic-table index",
            "confidence": "high",
        })
    return rows


def extract_player_interaction_topic_response_banks(data: bytes) -> list[dict]:
    """Recover the topic-indexed SUBJECT and CRITICIZE response banks.

    Player interaction code uses Player+0x388 as an NPC/profile selector,
    Player+0x1F0 as the topic index, and a per-profile value at
    ``profile + 4*(topic+6)`` as a 0..4 response class.  SUBJECT chooses one
    of four randomized variants per non-neutral class from 16-string banks;
    CRITICIZE chooses one of two from 8-string banks.  Class 2 uses the shared
    neutral literal ``I don't really care``.
    """
    # The state-0 response renderer branches on Player+0x1E4: slot 0 enters
    # SUBJECT's four-way random path and slot 3 enters CRITICIZE's two-way one.
    choice_dispatch = (0x23F2, 0x005B, 0x58E3, 0x2B00, 0xD100, 0xE238,
                       0x2B03, 0xD100, 0xE381)
    if _unpack_halfwords(data, 0x08009200, len(choice_dispatch)) != choice_dispatch:
        raise ValueError("interaction topic-response choice dispatch drifted")

    # SUBJECT: topic cursor +6 indexes the current NPC/profile's topic class.
    subject_profile = (0x23F8, 0x005B, 0x58E2, 0x4698, 0x59A3, 0x4960,
                       0x009B, 0x58C9, 0x1D93, 0x009B, 0x585B)
    if _unpack_halfwords(data, 0x0800968E, len(subject_profile)) != subject_profile:
        raise ValueError("SUBJECT topic-profile lookup drifted")
    if struct.unpack_from("<I", data, 0x0800981C - ROM_BASE)[0] != PLAYER_INTERACTION_PROFILE_TABLE_RAM:
        raise ValueError("SUBJECT profile-table literal drifted")
    if struct.unpack_from("<I", data, 0x08009838 - ROM_BASE)[0] != PLAYER_INTERACTION_SUBJECT_RESPONSE_PTR_TABLE_RAM:
        raise ValueError("SUBJECT response-pointer-table literal drifted")

    # CRITICIZE repeats the same profile lookup and uses the compact 8-string
    # response bank. Both response paths share the neutral class-2 literal.
    criticize_profile = (0x23F8, 0x59A2, 0x005B, 0x4698, 0x49B1, 0x58E3,
                          0x0092, 0x5889, 0x1D9A, 0x0092, 0x5852)
    if _unpack_halfwords(data, 0x08009924, len(criticize_profile)) != criticize_profile:
        raise ValueError("CRITICIZE topic-profile lookup drifted")
    if struct.unpack_from("<I", data, 0x08009BF4 - ROM_BASE)[0] != PLAYER_INTERACTION_PROFILE_TABLE_RAM:
        raise ValueError("CRITICIZE profile-table literal drifted")
    if struct.unpack_from("<I", data, 0x08009BF8 - ROM_BASE)[0] != PLAYER_INTERACTION_CRITICIZE_RESPONSE_PTR_TABLE_RAM:
        raise ValueError("CRITICIZE response-pointer-table literal drifted")
    if struct.unpack_from("<I", data, 0x08009C0C - ROM_BASE)[0] != PLAYER_INTERACTION_NEUTRAL_RESPONSE:
        raise ValueError("topic-response neutral literal drifted")
    if struct.unpack_from("<I", data, 0x08009E94 - ROM_BASE)[0] != PLAYER_INTERACTION_NEUTRAL_RESPONSE:
        raise ValueError("CRITICIZE neutral literal drifted")

    subject_class_dispatch = (0x2B00, 0xD100, 0xE182, 0x2B01, 0xD100, 0xE201,
                              0x2B02, 0xD100, 0xE232, 0x2B03, 0xD100, 0xE215,
                              0x2B04, 0xD000, 0xE5A7)
    if _unpack_halfwords(data, 0x080096A4, len(subject_class_dispatch)) != subject_class_dispatch:
        raise ValueError("SUBJECT topic-class dispatch drifted")
    criticize_class_dispatch = (0x2A00, 0xD100, 0xE12D, 0x2A01, 0xD100, 0xE1C7,
                                 0x2A02, 0xD100, 0xE1F8, 0x2A03, 0xD100, 0xE1DB,
                                 0x2A04, 0xD000, 0xE45C)
    if _unpack_halfwords(data, 0x0800993A, len(criticize_class_dispatch)) != criticize_class_dispatch:
        raise ValueError("CRITICIZE topic-class dispatch drifted")

    neutral = fixed_cstr(data, PLAYER_INTERACTION_NEUTRAL_RESPONSE - ROM_BASE,
                         PLAYER_INTERACTION_RESPONSE_STRIDE)
    if neutral != "I don't really care":
        raise ValueError("topic-response neutral text drifted")

    subject_ptr_off = init_ram_to_rom_off(PLAYER_INTERACTION_SUBJECT_RESPONSE_PTR_TABLE_RAM)
    criticize_ptr_off = init_ram_to_rom_off(PLAYER_INTERACTION_CRITICIZE_RESPONSE_PTR_TABLE_RAM)
    subject_ptrs = [struct.unpack_from("<I", data, subject_ptr_off + i * 4)[0] for i in range(9)]
    criticize_ptrs = [struct.unpack_from("<I", data, criticize_ptr_off + i * 4)[0] for i in range(9)]

    topics = [
        fixed_cstr(data, PLAYER_INTERACTION_SECONDARY_TOPIC_TABLE - ROM_BASE +
                   i * PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE,
                   PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE)
        for i in range(9)
    ]
    expected_topics = ["sports", "movies", "fashion", "video games", "school",
                       "future", "parties", "last event", "mysteries"]
    if topics != expected_topics:
        raise ValueError("topic-response topic labels drifted")

    # Validate that each pointer addresses the expected number of fixed-width
    # nonempty strings in the canonical ROM. Topic 7/8 deliberately reuse the
    # same response bank in both pointer tables.
    for ptrs, count, name in ((subject_ptrs, 16, "SUBJECT"), (criticize_ptrs, 8, "CRITICIZE")):
        for ptr in ptrs:
            for i in range(count):
                text = fixed_cstr(data, ptr - ROM_BASE + i * PLAYER_INTERACTION_RESPONSE_STRIDE,
                                  PLAYER_INTERACTION_RESPONSE_STRIDE)
                if not text:
                    raise ValueError(f"{name} response bank has empty entry at 0x{ptr:08X}+{i}")

    rows = []
    for i, topic in enumerate(topics):
        rows.append({
            "topic_index": i,
            "topic": topic,
            "profile_table": f"0x{PLAYER_INTERACTION_PROFILE_TABLE_RAM:08X}",
            "profile_topic_value_offset": "+4*(topic_index+6)",
            "subject_pointer_table": f"0x{PLAYER_INTERACTION_SUBJECT_RESPONSE_PTR_TABLE_RAM:08X}",
            "subject_response_base": f"0x{subject_ptrs[i]:08X}",
            "subject_variants_per_topic": 16,
            "subject_profile_value_0_slots": "0|4|8|12",
            "subject_profile_value_1_slots": "1|5|9|13",
            "subject_profile_value_2_slots": "neutral",
            "subject_profile_value_3_slots": "2|6|10|14",
            "subject_profile_value_4_slots": "3|7|11|15",
            "criticize_pointer_table": f"0x{PLAYER_INTERACTION_CRITICIZE_RESPONSE_PTR_TABLE_RAM:08X}",
            "criticize_response_base": f"0x{criticize_ptrs[i]:08X}",
            "criticize_variants_per_topic": 8,
            "criticize_profile_value_0_slots": "0|4",
            "criticize_profile_value_1_slots": "1|5",
            "criticize_profile_value_2_slots": "neutral",
            "criticize_profile_value_3_slots": "2|6",
            "criticize_profile_value_4_slots": "3|7",
            "response_stride": PLAYER_INTERACTION_RESPONSE_STRIDE,
            "neutral_response": neutral,
            "neutral_response_addr": f"0x{PLAYER_INTERACTION_NEUTRAL_RESPONSE:08X}",
            "profile_value_dispatch": "0..4 select response classes; other values fall through the generic interaction path",
            "confidence": "high",
        })
    return rows


def extract_player_interaction_topic_response_texts(data: bytes) -> list[dict]:
    """Export every fixed-width SUBJECT/CRITICIZE bank entry as usable text.

    Rating class 2 is intentionally absent from these banks because both code
    paths use the shared neutral literal instead.  The remaining four classes
    occupy the low two bits of each bank slot; higher slot groups are the RNG
    variants (four for SUBJECT and two for CRITICIZE).
    """
    bank_rows = extract_player_interaction_topic_response_banks(data)
    slot_to_rating = {0: 0, 1: 1, 2: 3, 3: 4}
    rows = []
    for bank in bank_rows:
        topic_index = bank["topic_index"]
        topic = bank["topic"]
        for action, base_key, count in (
            ("SUBJECT", "subject_response_base", 16),
            ("CRITICIZE", "criticize_response_base", 8),
        ):
            base = int(bank[base_key], 16)
            for slot in range(count):
                addr = base + slot * PLAYER_INTERACTION_RESPONSE_STRIDE
                text = fixed_cstr(data, addr - ROM_BASE, PLAYER_INTERACTION_RESPONSE_STRIDE)
                rows.append({
                    "action": action,
                    "topic_index": topic_index,
                    "topic": topic,
                    "slot": slot,
                    "profile_value_class": slot_to_rating[slot & 3],
                    "variant": slot >> 2,
                    "rom_addr": f"0x{addr:08X}",
                    "response_stride": PLAYER_INTERACTION_RESPONSE_STRIDE,
                    "text": text,
                    "confidence": "high",
                })
    return rows


def extract_player_interaction_state2_cursor(data: bytes) -> dict:
    """Export the mechanically proved cursor behavior of interaction state 2.

    Fresh A reaches leaf entry with r3 cleared by the previous-key edge test,
    so the store at 0x08009DE4 initializes Player+0x1F0 to zero.  The state-2
    dispatcher treats a fresh Up edge as the decrement path and otherwise
    routes through 0x080099F8, whose fresh Down edge increments the same field.
    Both moves rebuild the secondary UI through 0x080074D8 and 0x08006E00.
    """
    fresh_a = (0x2301, 0x420B, 0xD101, 0xF7FF, 0xFAAE, 0x4A8B, 0x6812,
               0x4013, 0xD001)
    if _unpack_halfwords(data, 0x080095F8, len(fresh_a)) != fresh_a:
        raise ValueError("interaction fresh-A edge path drifted")
    entry = (0x2E01, 0xD000, 0xE740, 0x22F8, 0x0052, 0x50A3)
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE2_ENTRY, len(entry)) != entry:
        raise ValueError("interaction state-2 cursor initialization drifted")

    # The branch structure at 0x08008BF4 makes 0x08008C16 the fresh-Up path:
    # current Up set + previous Up clear avoids both 0x080099F8 calls.
    up_dispatch = (0x3340, 0x001A, 0x400A, 0x2D01, 0xD101, 0xF000, 0xFDC9,
                   0x2A00, 0xD101, 0xF000, 0xFEF7, 0x4A74, 0x6812, 0x421A,
                   0xD001, 0xF000, 0xFEF1)
    if _unpack_halfwords(data, 0x08008BF4, len(up_dispatch)) != up_dispatch:
        raise ValueError("interaction state-2 fresh-Up dispatch drifted")
    up_move = (0x23F8, 0x005B, 0x58E2, 0x2A00, 0xDD20, 0x1E51, 0x50E1)
    if _unpack_halfwords(data, 0x08008C16, len(up_move)) != up_move:
        raise ValueError("interaction state-2 cursor decrement drifted")

    down_move = (0x2380, 0x420B, 0xD101, 0xF7FF, 0xF930, 0x4A81, 0x6812,
                 0x421A, 0xD001, 0xF7FF, 0xF92A, 0x23F8, 0x005B, 0x58E2,
                 0x2A07, 0xDD01, 0xF7FF, 0xF923, 0x1C51, 0x50E1)
    if _unpack_halfwords(data, 0x080099F8, len(down_move)) != down_move:
        raise ValueError("interaction state-2 cursor increment drifted")

    # Both movement paths converge on the same two UI rebuild calls.
    if _thumb1_bl_target(data, 0x08008C54 - ROM_BASE) != 0x080074D8:
        raise ValueError("interaction state-2 Up rebuild helper drifted")
    if _thumb1_bl_target(data, 0x08008C5A - ROM_BASE) != PLAYER_INTERACTION_SECONDARY_LIST_BUILDER:
        raise ValueError("interaction state-2 Up list-builder call drifted")

    return {
        "cursor_offset": f"+0x{PLAYER_INTERACTION_STATE2_CURSOR_OFFSET:X}",
        "entry_value": 0,
        "entry_handler": f"0x{PLAYER_INTERACTION_STATE2_ENTRY:08X}",
        "up_handler": "0x08008C16",
        "up_behavior": "fresh Up decrements cursor when cursor > 0",
        "down_handler": "0x080099F8",
        "down_behavior": "fresh Down increments cursor when cursor <= 7",
        "mechanical_range": "0..8",
        "rebuild_calls": "0x080074D8|0x08006E00",
        "per_action_count_clamp": "not proved; movement code uses global 0..8 bound",
        "confidence": "high",
    }



def extract_player_interaction_runtime_dispatch(data: bytes) -> list[dict]:
    """Map all 16 leaf labels onto the code-proven quadrant response paths.

    The response dispatcher at 0x08009200 reads Player+0x1E4 only. Choice 0
    jumps to the SUBJECT response-bank path, choice 3 to CRITICIZE, while
    choices 1 and 2 set Player+0x382 to 1 and take the shared continuation.
    It does not read Player+0x1E8, so the FLIRT/ASSAULT/SHARE leaf labels do
    not receive distinct response dispatch solely from their submenu base in
    this canonical demo.
    """
    dispatch = (0x23F2, 0x005B, 0x58E3, 0x2B00, 0xD100, 0xE238,
                0x2B03, 0xD100, 0xE381, 0x2201, 0x4B95, 0x54E2, 0xE15E)
    if _unpack_halfwords(data, PLAYER_INTERACTION_RESPONSE_DISPATCH, len(dispatch)) != dispatch:
        raise ValueError("interaction runtime response dispatcher drifted")
    if struct.unpack_from("<I", data, 0x0800946C - ROM_BASE)[0] != PLAYER_INTERACTION_SECONDARY_FLAG_OFFSET:
        raise ValueError("interaction shared quadrant flag offset drifted")

    action_rows = extract_player_interaction_action_table(data)
    paths = {
        0: "SUBJECT response bank",
        1: "set Player+0x382=1",
        2: "set Player+0x382=1",
        3: "CRITICIZE response bank",
    }
    rows = []
    for action in action_rows[4:]:
        index = action["index"]
        page_base = (index // 4) * 4
        quadrant = index - page_base
        rows.append({
            "action_index": index,
            "action_label": action["label"],
            "page_base": page_base,
            "quadrant": quadrant,
            "runtime_path": paths[quadrant],
            "dispatcher": f"0x{PLAYER_INTERACTION_RESPONSE_DISPATCH:08X}",
            "dispatch_key": "Player+0x1E4 quadrant only",
            "page_base_consulted": "no",
            "shared_flag_offset": f"+0x{PLAYER_INTERACTION_SECONDARY_FLAG_OFFSET:X}" if quadrant in (1, 2) else "",
            "reconstruction_warning": "leaf label is not proof of a unique runtime effect in this demo",
            "confidence": "high",
        })
    return rows



def extract_player_interaction_followup_handshake(data: bytes) -> dict:
    """Export the shared fresh-A handshake armed by response quadrants 1/2.

    The response dispatcher sets Player+0x382 for choices 1 and 2.  Earlier in
    Player_update, 0x0800852E tests that flag and requires a fresh A edge.  The
    accepted edge clears +0x382, +0x381 and interaction state +0x1EC, then
    writes 1 back to the global interaction-active byte at 0x03000610.
    """
    consumer_prefix = (0x4B12, 0x5CE3, 0x2B00, 0xD100, 0xE3B5, 0x4653, 0x2201)
    if _unpack_halfwords(data, 0x0800852E, len(consumer_prefix)) != consumer_prefix:
        raise ValueError("interaction shared follow-up consumer drifted")

    fresh_a_commit = (0x2300, 0x4AC8, 0x54A3, 0x4AC8, 0x54A3,
                      0x3A96, 0x3AFF, 0x50A3, 0x4AC7, 0x3301, 0x7013)
    if _unpack_halfwords(data, 0x08008596, len(fresh_a_commit)) != fresh_a_commit:
        raise ValueError("interaction shared follow-up fresh-A handshake drifted")

    literals = {
        0x080088BC: PLAYER_INTERACTION_SECONDARY_FLAG_OFFSET,
        0x080088C0: 0x381,
        0x080088C4: 0x03000610,
    }
    for address, expected in literals.items():
        actual = struct.unpack_from("<I", data, address - ROM_BASE)[0]
        if actual != expected:
            raise ValueError(
                f"interaction follow-up literal drifted at 0x{address:08X}: "
                f"0x{actual:08X} != 0x{expected:08X}"
            )

    # After clearing +0x381, r2 is decremented by 0x96 and 0xFF: 0x381 -> 0x1EC.
    if 0x381 - 0x96 - 0xFF != PLAYER_INTERACTION_STATE_OFFSET:
        raise AssertionError("follow-up state-offset arithmetic no longer matches constants")

    return {
        "armed_by": "quadrants 1 and 2 at 0x08009212",
        "flag_offset": f"+0x{PLAYER_INTERACTION_SECONDARY_FLAG_OFFSET:X}",
        "consumer": "0x0800852E",
        "trigger": "fresh A while Player+0x382 != 0",
        "clears": "Player+0x382|Player+0x381|Player+0x1EC",
        "active_global_write": "0x03000610=1",
        "result_state": 0,
        "exact_leaf_effect": "not proved; dispatcher is quadrant-only",
        "confidence": "high",
    }




def extract_player_interaction_profile_selector_table(data: bytes) -> list[dict]:
    """Recover the initialized selector table and classify its heterogeneous entries.

    The table at 0x0300110C contains two genuine 0x3C social-profile records,
    one null entry, then six pointers to a different 0x30 NPC metadata/card
    layout.  Runtime social code nevertheless indexes all non-null entries as
    if they exposed nine numeric topic classes, which is an important demo
    parity hazard rather than an extraction error.
    """
    table_off = init_ram_to_rom_off(PLAYER_INTERACTION_PROFILE_TABLE_RAM)
    expected_ptrs = [
        0x030010D0, 0x03001094, 0x00000000,
        0x03001224, 0x030011F4, 0x030011C4,
        0x03001194, 0x03001164, 0x03001134,
    ]
    expected_names = ["Stas", "Julia", "", "Stas", "IQ 54", "Kate", "Kiata", "Alex", "Evelina"]
    rows = []
    for selector_index, (expected_ptr, expected_name) in enumerate(zip(expected_ptrs, expected_names)):
        ptr = struct.unpack_from("<I", data, table_off + selector_index * 4)[0]
        if ptr != expected_ptr:
            raise ValueError(
                f"interaction profile pointer drifted at selector {selector_index}: "
                f"0x{ptr:08X} != 0x{expected_ptr:08X}"
            )
        if ptr == 0:
            rows.append({
                "selector_index": selector_index,
                "profile_ptr": "0x00000000",
                "initialized_rom_addr": "",
                "name": "",
                "record_kind": "null",
                "record_size": 0,
                "selector_source": "actor+0x5C copied to Player+0x388",
                "behavior_confidence": "high",
            })
            continue
        rec_off = init_ram_to_rom_off(ptr)
        name = fixed_cstr(data, rec_off, PLAYER_INTERACTION_PROFILE_NAME_SIZE)
        if name != expected_name:
            raise ValueError(
                f"interaction selector name drifted at selector {selector_index}: {name!r}"
            )
        if selector_index < 2:
            kind = "social_profile_0x3C"
            size = PLAYER_INTERACTION_SOCIAL_PROFILE_RECORD_SIZE
        else:
            kind = "npc_metadata_0x30_wrong_for_social_code"
            size = PLAYER_INTERACTION_NPC_METADATA_RECORD_SIZE
        rows.append({
            "selector_index": selector_index,
            "profile_ptr": f"0x{ptr:08X}",
            "initialized_rom_addr": f"0x{ROM_BASE + rec_off:08X}",
            "name": name,
            "record_kind": kind,
            "record_size": size,
            "selector_source": "actor+0x5C copied to Player+0x388",
            "behavior_confidence": "high",
        })
    return rows


def extract_player_interaction_social_profile_topics(data: bytes) -> list[dict]:
    """Export the nine valid topic classes from the two genuine social profiles."""
    selectors = extract_player_interaction_profile_selector_table(data)
    topics = [
        fixed_cstr(data, PLAYER_INTERACTION_SECONDARY_TOPIC_TABLE - ROM_BASE +
                   i * PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE,
                   PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE)
        for i in range(9)
    ]
    expected = {
        "Stas": [3, 4, 0, 2, 1, 1, 3, 2, 2],
        "Julia": [1, 2, 2, 0, 1, 2, 4, 2, 3],
    }
    rows = []
    for selector in selectors[:2]:
        ptr = int(selector["profile_ptr"], 16)
        rec_off = init_ram_to_rom_off(ptr)
        field14 = struct.unpack_from("<i", data, rec_off + PLAYER_INTERACTION_PROFILE_FIELD14)[0]
        ratings = list(struct.unpack_from("<9I", data, rec_off + PLAYER_INTERACTION_PROFILE_TOPIC_BASE))
        if ratings != expected[selector["name"]]:
            raise ValueError(f"social profile topic ratings drifted for {selector['name']}: {ratings}")
        for topic_index, (topic, rating) in enumerate(zip(topics, ratings)):
            rows.append({
                "selector_index": selector["selector_index"],
                "profile_ptr": selector["profile_ptr"],
                "name": selector["name"],
                "profile_field_14_initial": field14,
                "topic_index": topic_index,
                "topic": topic,
                "rating": rating,
                "rating_range": "0..4",
                "record_kind": selector["record_kind"],
                "behavior_confidence": "high",
            })
    return rows


def extract_player_interaction_social_score_semantics(data: bytes) -> dict:
    """Prove the centered topic-class update of profile+0x14."""
    update_path = (
        0x23F8, 0x005B, 0x58E3, 0x3306, 0x009B, 0x585B,
        0x3B02, 0x694A, 0x4694, 0x005B, 0x4463, 0x614B,
    )
    if _unpack_halfwords(data, PLAYER_INTERACTION_PROFILE_SCORE_UPDATE, len(update_path)) != update_path:
        raise ValueError("interaction profile+0x14 centered score update drifted")
    if struct.unpack_from("<I", data, 0x0800981C - ROM_BASE)[0] != PLAYER_INTERACTION_PROFILE_TABLE_RAM:
        raise ValueError("interaction score-update profile-table literal drifted")
    follower = extract_player_interaction_profile_target_step(data)
    real_profiles = extract_player_interaction_social_profile_topics(data)
    initial_by_name = {}
    for row in real_profiles:
        initial_by_name[row["name"]] = row["profile_field_14_initial"]
    return {
        "profile_field": "+0x14",
        "update_site": "0x08009504..0x0800951A",
        "topic_class_source": "profile + 4*(Player+0x1F0 + 6)",
        "update_formula": "profile+0x14 += 2 * (topic_class - 2)",
        "topic_class_deltas": "0:-4|1:-2|2:0|3:+2|4:+4",
        "player_follower_offset": follower["player_offset"],
        "player_follower_target": "10 * profile+0x14",
        "direct_player_mirror_site": "0x080090F8",
        "direct_player_mirror_formula": "Player+0x39C = 10 * profile+0x14",
        "proper_profile_initial_values": "|".join(f"{name}:{initial_by_name[name]}" for name in ("Stas", "Julia")),
        "semantic_name": "relationship-like social score",
        "name_confidence": "medium-high",
        "behavior_confidence": "high",
    }


def _ascii_le_word(raw: int) -> str:
    b = raw.to_bytes(4, "little", signed=False)
    if all(0x20 <= x <= 0x7E for x in b):
        return b.decode("ascii")
    return ""


def extract_player_interaction_profile_topic_layout_mismatch(data: bytes) -> list[dict]:
    """Prove selectors 3..8 expose incompatible 0x30 records to social reads."""
    selectors = [row for row in extract_player_interaction_profile_selector_table(data)
                 if row["record_kind"] == "npc_metadata_0x30_wrong_for_social_code"]
    topics = [
        fixed_cstr(data, PLAYER_INTERACTION_SECONDARY_TOPIC_TABLE - ROM_BASE +
                   i * PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE,
                   PLAYER_INTERACTION_SECONDARY_TOPIC_STRIDE)
        for i in range(9)
    ]
    rows = []
    for profile in selectors:
        ptr = int(profile["profile_ptr"], 16)
        rec_off = init_ram_to_rom_off(ptr)
        for topic_index, topic in enumerate(topics):
            field_offset = 4 * (topic_index + 6)
            raw = struct.unpack_from("<I", data, rec_off + field_offset)[0]
            rows.append({
                "selector_index": profile["selector_index"],
                "name": profile["name"],
                "topic_index": topic_index,
                "topic": topic,
                "profile_field_offset": f"+0x{field_offset:X}",
                "raw_value": raw,
                "raw_value_hex": f"0x{raw:08X}",
                "ascii_le": _ascii_le_word(raw),
                "valid_response_class": "yes" if 0 <= raw <= 4 else "no",
                "explicit_dispatch_range": "0..4",
                "layout_finding": "wrong-layout metadata overlaps social topic-class read",
                "behavior_confidence": "high",
            })
    return rows


def extract_player_interaction_profile_selector_reachability(data: bytes) -> list[dict]:
    """Prove canonical initialized social actors reach only selectors 0 and 1.

    NPC_update dispatches state==1 to 0x08002ACA.  Its proximity success is the
    sole unconditional branch in NPC_update to 0x08002FA2, whose fresh-A edge
    reaches 0x08002FCE and copies actor+0x5C (dial) into Player+0x388.  Scanning
    the serialized canonical actors finds exactly two initialized state-1 NPCs,
    with dials 0 and 1.  This is a canonical-initial-state reachability proof;
    mutation by code outside this recovered path is deliberately not excluded.
    """
    dispatch = (0x235A, 0x5EEB, 0x2B03, 0xD100, 0xE0CD)
    if _unpack_halfwords(data, NPC_UPDATE_FUNCTION + 0x40, len(dispatch)) != dispatch:
        raise ValueError("NPC state dispatch drifted")
    state1_test = (0x2B02, 0xD00A, 0x2B01, 0xD067)
    if _unpack_halfwords(data, 0x080029F2, len(state1_test)) != state1_test:
        raise ValueError("NPC state-1 dispatch drifted")
    handoff_hw = struct.unpack_from("<H", data, NPC_STATE1_SOCIAL_HANDOFF - ROM_BASE)[0]
    if _thumb_unconditional_b_target(NPC_STATE1_SOCIAL_HANDOFF, handoff_hw) != NPC_SOCIAL_PRELUDE:
        raise ValueError("NPC state-1 social handoff drifted")
    all_handoffs = []
    for addr in range(NPC_UPDATE_FUNCTION, 0x080037F6, 2):
        hw = struct.unpack_from("<H", data, addr - ROM_BASE)[0]
        if _thumb_unconditional_b_target(addr, hw) == NPC_SOCIAL_PRELUDE:
            all_handoffs.append(addr)
    if all_handoffs != [NPC_STATE1_SOCIAL_HANDOFF]:
        raise ValueError(f"unexpected NPC_update handoffs to social prelude: {[hex(x) for x in all_handoffs]}")
    fresh_a = (0x4B0D, 0x681B, 0x4013, 0xD000, 0xE515, 0x20E2, 0x4664, 0x6DEE)
    if _unpack_halfwords(data, 0x08002FC4, len(fresh_a)) != fresh_a:
        raise ValueError("NPC social fresh-A selector bootstrap drifted")

    actors = []
    for off, props in _scan_serialized_actors(data):
        if props.get("spawnType") != "npc":
            continue
        try:
            state = int(props.get("state", "0"), 0)
            dial = int(props.get("dial", "0"), 0)
        except ValueError:
            continue
        if state == 1:
            actors.append((off, props, dial))
    actual = [(ROM_BASE + off, dial) for off, _, dial in actors]
    expected = [(0x08019100, 0), (0x0801917C, 1)]
    if actual != expected:
        raise ValueError(f"canonical state-1 NPC set drifted: {[(hex(a), d) for a,d in actual]}")

    actor_by_dial = {dial: (off, props) for off, props, dial in actors}
    selectors = extract_player_interaction_profile_selector_table(data)
    # NPC_update has no direct word store to actor+0x5C.  Its register-offset
    # halfword stores to actor are a small, canonical set used for facing/UI
    # fields; state+0x5A is only loaded in the recovered function.
    dial_writes = []
    register_strh_sites = []
    for addr in range(NPC_UPDATE_FUNCTION, 0x080037F6, 2):
        hw = struct.unpack_from("<H", data, addr - ROM_BASE)[0]
        if (hw & 0xF800) == 0x6000:  # STR (immediate)
            base = (hw >> 3) & 7
            byte_off = ((hw >> 6) & 0x1F) * 4
            if base == 5 and byte_off == 0x5C:
                dial_writes.append(addr)
        if (hw & 0xFE00) == 0x5200 and ((hw >> 3) & 7) == 5:  # STRH register offset, base r5
            register_strh_sites.append(addr)
    expected_strh_sites = [0x08002BEE, 0x08002BF6, 0x08002BFC,
                           0x08002D46, 0x08002D64, 0x08002D82, 0x08002DEC, 0x08002FEE,
                           0x08003274, 0x08003282, 0x08003286, 0x0800329E, 0x080032A6,
                           0x080032C2, 0x080035C0]
    if dial_writes:
        raise ValueError(f"unexpected NPC_update actor+0x5C writes: {[hex(x) for x in dial_writes]}")
    if register_strh_sites != expected_strh_sites:
        raise ValueError(f"NPC_update register-offset halfword-store inventory drifted: {[hex(x) for x in register_strh_sites]}")
    state_read_signatures = {
        0x080029CC: (0x235A, 0x5EEB),
        0x08002F96: (0x235A, 0x5EEB),
        0x0800320A: (0x235A, 0x5EEB),
        0x0800363E: (0x2300, 0x465A, 0x6293, 0x335A, 0x5EEB),
    }
    for addr, sig in state_read_signatures.items():
        if _unpack_halfwords(data, addr, len(sig)) != sig:
            raise ValueError(f"NPC_update state+0x5A read signature drifted at 0x{addr:08X}")

    rows = []
    for selector in selectors:
        idx = selector["selector_index"]
        actor = actor_by_dial.get(idx)
        rows.append({
            "selector_index": idx,
            "profile_name": selector["name"],
            "profile_kind": selector["record_kind"],
            "canonical_reachability": "reachable" if actor else "not reached by initialized state-1 NPC",
            "actor_rom_addr": f"0x{ROM_BASE + actor[0]:08X}" if actor else "",
            "actor_state": 1 if actor else "",
            "actor_dial": idx if actor else "",
            "actor_level": int(actor[1].get("level", "0"), 0) if actor else "",
            "social_bootstrap": f"0x{NPC_SOCIAL_BOOTSTRAP:08X}",
            "only_npc_update_handoff": f"0x{NPC_STATE1_SOCIAL_HANDOFF:08X} -> 0x{NPC_SOCIAL_PRELUDE:08X}",
            "selector_copy": "actor+0x5C -> Player+0x388",
            "npc_update_state_write": "none in 0x0800298C..0x080037F6",
            "npc_update_dial_write": "none in 0x0800298C..0x080037F6",
            "reachability_scope": "canonical initialized actors plus NPC_update; external mutation not ruled out",
            "confidence": "high",
        })
    return rows


def extract_player_interaction_profile_field_usage(data: bytes) -> list[dict]:
    """Inventory recovered selector-derived profile-field uses, including +0x10 absence.

    Every PC-relative Thumb load of the profile-selector-table address in the
    recovered Player interaction code is inventoried.  None of those recovered
    data-flow sites reads +0x10; +0x14 is the score and +0x18..+0x38 are topic
    classes.  Absence is intentionally scoped to these recovered selector-use
    sites rather than asserted as a whole-program theorem.
    """
    refs = _thumb_literal_refs_to(data, PLAYER_INTERACTION_PROFILE_TABLE_RAM)
    expected_refs = [
        0x080085BA, 0x08008CD4, 0x080090FE, 0x080091EE, 0x08009492,
        0x08009698, 0x0800992C, 0x080099CE, 0x08009ADA, 0x08009B0E,
        0x08009B30, 0x08009BBA, 0x08009CFC, 0x08009D30, 0x08009D52,
    ]
    if refs != expected_refs:
        raise ValueError(f"profile selector-table reference inventory drifted: {[hex(x) for x in refs]}")
    profiles = extract_player_interaction_profile_selector_table(data)[:2]
    initial_field10 = []
    initial_field14 = []
    for profile in profiles:
        ptr = int(profile["profile_ptr"], 16)
        rec_off = init_ram_to_rom_off(ptr)
        initial_field10.append((profile["name"], struct.unpack_from("<i", data, rec_off + PLAYER_INTERACTION_PROFILE_FIELD10)[0]))
        initial_field14.append((profile["name"], struct.unpack_from("<i", data, rec_off + PLAYER_INTERACTION_PROFILE_FIELD14)[0]))
    if initial_field10 != [("Stas", 0), ("Julia", 0)]:
        raise ValueError(f"proper profile +0x10 initializer drifted: {initial_field10}")
    return [
        {
            "profile_field": "+0x00",
            "proper_profile_initial_values": "Stas|Julia",
            "runtime_usage": "profile/name text source",
            "evidence_sites": "0x080091EC",
            "working_name": "name/text prefix",
            "selector_literal_ref_count": len(refs),
            "confidence": "high",
        },
        {
            "profile_field": "+0x10",
            "proper_profile_initial_values": "|".join(f"{n}:{v}" for n,v in initial_field10),
            "runtime_usage": "no selector-derived read found in recovered interaction code",
            "evidence_sites": "all 15 recovered profile-table load sites inventoried",
            "working_name": "reserved/unused in recovered interaction runtime",
            "selector_literal_ref_count": len(refs),
            "confidence": "high for absence within recovered selector-use sites",
        },
        {
            "profile_field": "+0x14",
            "proper_profile_initial_values": "|".join(f"{n}:{v}" for n,v in initial_field14),
            "runtime_usage": "relationship-like score read/write",
            "evidence_sites": "0x080085AC|0x080090F8|0x08009504",
            "working_name": "relationship-like social score",
            "selector_literal_ref_count": len(refs),
            "confidence": "high behavior / medium-high semantic name",
        },
        {
            "profile_field": "+0x18..+0x38",
            "proper_profile_initial_values": "nine 0..4 topic classes per proper profile",
            "runtime_usage": "nine topic-class reads",
            "evidence_sites": "0x0800948C response dispatch and related selector-derived paths",
            "working_name": "topic preference classes",
            "selector_literal_ref_count": len(refs),
            "confidence": "high",
        },
    ]


def extract_player_interaction_profile_selector_integrity(data: bytes) -> dict:
    """Summarize the selector table's demo-parity integrity hazards.

    The response path at 0x0800948C indexes Player+0x388 directly into the
    selector table, then dereferences the selected pointer and the current
    topic slot without a null check.  The initialized table contains only two
    records with the expected nine-rating social layout.
    """
    deref_path = (
        0x23E2, 0x009B, 0x58E3, 0x4AE2, 0x009B, 0x589A,
        0x23F8, 0x005B, 0x58E3, 0x3306, 0x009B, 0x589A,
    )
    if _unpack_halfwords(data, 0x0800948C, len(deref_path)) != deref_path:
        raise ValueError("interaction profile/topic direct dereference drifted")
    if struct.unpack_from("<I", data, 0x0800981C - ROM_BASE)[0] != PLAYER_INTERACTION_PROFILE_TABLE_RAM:
        raise ValueError("interaction response profile-table literal drifted")

    selectors = extract_player_interaction_profile_selector_table(data)
    mismatch = extract_player_interaction_profile_topic_layout_mismatch(data)
    reachability = extract_player_interaction_profile_selector_reachability(data)
    reached = [str(r["selector_index"]) for r in reachability if r["canonical_reachability"] == "reachable"]
    latent = [str(r["selector_index"]) for r in reachability if r["canonical_reachability"] != "reachable"]
    return {
        "proper_social_profiles": sum(r["record_kind"] == "social_profile_0x3C" for r in selectors),
        "null_entries": sum(r["record_kind"] == "null" for r in selectors),
        "wrong_layout_entries": sum(r["record_kind"] == "npc_metadata_0x30_wrong_for_social_code" for r in selectors),
        "wrong_layout_topic_reads": len(mismatch),
        "wrong_layout_reads_in_0_4": sum(r["valid_response_class"] == "yes" for r in mismatch),
        "runtime_profile_deref": "0x0800948C",
        "selector_null_guard": "none before profile/topic dereference",
        "null_selector_index": 2,
        "actor_selector_source": "actor+0x5C -> Player+0x388",
        "canonical_reachable_selectors": "|".join(reached),
        "latent_selectors": "|".join(latent),
        "hazard_scope": "latent under canonical initialized state-1 NPC path; external mutation not ruled out",
        "parity_warning": "preserve malformed selector table for demo parity, but do not treat selectors 2..8 as normally reached",
        "behavior_confidence": "high",
    }


def extract_player_interaction_profile_target_step(data: bytes) -> dict:
    """Export the raw profile-linked target adjustment after the +0x382 handshake.

    The canonical code loads Player+0x39C and the current profile selected by
    Player+0x388, reads profile+0x14, multiplies that field by ten, and nudges
    +0x39C by one toward the result.  No social/relationship meaning is assigned
    here because the static evidence only proves the arithmetic/data flow.
    """
    compare_path = (0x21E7, 0x0089, 0x5863, 0x4698, 0x23E2, 0x009B,
                    0x58E3, 0x4AC3, 0x009B, 0x589B, 0x695A, 0x0093,
                    0x189B, 0x005B, 0x4598, 0xDB01)
    if _unpack_halfwords(data, 0x080085AC, len(compare_path)) != compare_path:
        raise ValueError("interaction profile-linked target compare drifted")
    if struct.unpack_from("<I", data, 0x080088C8 - ROM_BASE)[0] != PLAYER_INTERACTION_PROFILE_TABLE_RAM:
        raise ValueError("interaction profile table literal drifted in target-step path")

    below_path = (0x2301, 0x469C, 0x44E0, 0x4643, 0x5063)
    if _unpack_halfwords(data, 0x080085D0, len(below_path)) != below_path:
        raise ValueError("interaction below-target increment drifted")

    above_equal_path = (0x4598, 0xDC01, 0xF7FF, 0xFC09,
                        0x2301, 0x425B, 0x469C, 0x44E0, 0x4643, 0x5063)
    if _unpack_halfwords(data, 0x08008DC0, len(above_equal_path)) != above_equal_path:
        raise ValueError("interaction above/equal target branch drifted")

    return {
        "player_offset": "+0x39C",
        "profile_selector_offset": f"+0x{PLAYER_DIALOGUE_INDEX_OFFSET:X}",
        "profile_table": f"0x{PLAYER_INTERACTION_PROFILE_TABLE_RAM:08X}",
        "profile_field_offset": "+0x14",
        "target_formula": "10 * profile[+0x14]",
        "below_target": "increment Player+0x39C by 1",
        "above_target": "decrement Player+0x39C by 1",
        "at_target": "leave Player+0x39C unchanged",
        "entry_path": "after fresh-A +0x382 follow-up handshake",
        "semantic_name": "scaled relationship-like score mirror/follower",
        "confidence": "high",
    }

def extract_player_interaction_score_mirror_semantics(data: bytes) -> dict:
    """Prove Player+0x39C directly mirrors ten times profile+0x14.

    Before the quadrant-specific response branch, the canonical Player path
    selects the current profile through Player+0x388, reads profile+0x14,
    computes value*10, and stores it to Player+0x39C.  The separate follow-up
    path can then nudge the same field one unit toward that same target.
    """
    sync_path = (
        0x23E2, 0x009B, 0x58E3, 0x4AD7, 0x009B, 0x58D1,
        0x694A, 0x0093, 0x189B, 0x22E7, 0x005B, 0x0092, 0x50A3,
    )
    if _unpack_halfwords(data, 0x080090F8, len(sync_path)) != sync_path:
        raise ValueError("interaction direct social-score mirror path drifted")
    if struct.unpack_from("<I", data, 0x0800945C - ROM_BASE)[0] != PLAYER_INTERACTION_PROFILE_TABLE_RAM:
        raise ValueError("interaction direct mirror profile-table literal drifted")
    return {
        "direct_sync_site": "0x080090F8",
        "profile_selector": "Player+0x388",
        "profile_table": f"0x{PLAYER_INTERACTION_PROFILE_TABLE_RAM:08X}",
        "profile_field": "+0x14",
        "player_field": "+0x39C",
        "direct_sync_formula": "Player+0x39C = 10 * profile+0x14",
        "position": "before quadrant-specific response branch",
        "followup_behavior": "fresh-A +0x382 path nudges same field by one toward same target",
        "working_name": "scaled relationship-like score mirror/follower",
        "behavior_confidence": "high",
    }


def extract_player_interaction_depth_semantics(data: bytes) -> dict:
    """Export the nested interaction depth mechanics and state-2 A gate.

    Player+0x38C is incremented when descending from a submenu selection and
    again when entering a leaf, while the B-return path decrements it. During
    state 2 a fresh A only reaches state 3 when depth is positive and the
    current page base is 4 (the TALK page). Other nonzero submenu bases take
    the Player_update exit branch without changing +0x1EC at this gate.
    """
    branch_depth = (0x6A43, 0x5163, 0x23F6, 0x005B, 0x50E6,
                    0x23E3, 0x3201, 0x009B, 0x50E2)
    if _unpack_halfwords(data, 0x08009C58, len(branch_depth)) != branch_depth:
        raise ValueError("interaction submenu depth increment drifted")
    leaf_reload = (0x33A1, 0x33FF, 0x58E2, 0x4653, 0x6819, 0xE71E)
    if _unpack_halfwords(data, 0x08009E18, len(leaf_reload)) != leaf_reload:
        raise ValueError("interaction leaf depth reload drifted")
    b_decrement = (0x22E3, 0x0092, 0x58A3, 0x3B01, 0x50A3)
    if _unpack_halfwords(data, 0x08008C98, len(b_decrement)) != b_decrement:
        raise ValueError("interaction B depth decrement drifted")

    a_gate = (0x22E3, 0x25F4, 0x0092, 0x58A2, 0x006D, 0x5960,
              0x2A00, 0xDC00, 0xE30E, 0x2804, 0xD001)
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE2_FRESH_A_GATE, len(a_gate)) != a_gate:
        raise ValueError("interaction state-2 fresh-A page/depth gate drifted")
    if _thumb1_bl_target(data, 0x08009624 - ROM_BASE) != 0x08008B5E:
        raise ValueError("interaction non-TALK fresh-A exit branch drifted")
    if _unpack_halfwords(data, 0x0800962C, 4) != (0x23F6, 0x2203, 0x005B, 0x50E2):
        raise ValueError("interaction TALK state-3 store drifted")

    return {
        "depth_offset": f"+0x{PLAYER_INTERACTION_DEPTH_OFFSET:X}",
        "submenu_confirm": "increments depth at 0x08009C62",
        "leaf_entry": "reloads depth at 0x08009E18 then increments through 0x08009C62",
        "b_return": "decrements depth at 0x08008C98",
        "state2_fresh_a_gate": "depth > 0 and page_base == 4 -> state 3",
        "talk_page_base": 4,
        "other_page_bases": "8|12|16",
        "other_page_fresh_a": "exits Player_update path without changing interaction state",
        "state_offset": f"+0x{PLAYER_INTERACTION_STATE_OFFSET:X}",
        "page_base_offset": f"+0x{PLAYER_INTERACTION_PAGE_BASE_OFFSET:X}",
        "confidence": "high",
    }

def extract_player_interaction_state_transitions(data: bytes) -> list[dict]:
    """Export code-proven transitions in Player's +0x1EC NPC interaction state.

    State 1 is the four-way action selector.  Branch records return to state 0
    after replacing Player+0x1E8 with their +0x24 child base; leaf records enter
    state 2.  State 2's exact leaf-action semantics remain unresolved, but its B
    return/back path to state 0 is proved; cancel-versus-commit meaning is not.  State 3 is a teardown path that
    resets the interaction base/state and clears 0x03000610.
    """
    # State 0 setup ends by storing 1 to Player+0x1EC.
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE0_TO_1, 4) != (0x23F6, 0x2201, 0x005B, 0x50E2):
        raise ValueError("interaction state 0->1 store drifted")

    # The state-1 D-pad dispatcher checks Up, Right, Down, Left in that order.
    control_prefix = (0x2A00, 0xD004, 0x4A25, 0x6812, 0x4013, 0xD100, 0xE268, 0x2310)
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE1_CONTROLS, len(control_prefix)) != control_prefix:
        raise ValueError("interaction state-1 control dispatcher drifted")
    if _unpack_halfwords(data, 0x080097D8, 4) != (0x23F2, 0x2203, 0x005B, 0x50E2):
        raise ValueError("interaction left-choice store drifted")
    if _unpack_halfwords(data, 0x08009D60, 4) != (0x23F2, 0x2201, 0x005B, 0x50E2):
        raise ValueError("interaction right-choice store drifted")
    if _unpack_halfwords(data, 0x08009DA4, 4) != (0x23F2, 0x2202, 0x005B, 0x50E2):
        raise ValueError("interaction down-choice store drifted")

    # Confirmation indexes the 0x2C-byte table and branches on record+0x20.
    commit = (0x26F2, 0x272C, 0x0076, 0x59A6, 0x1980, 0x003E, 0x4346, 0x488E,
              0x1980, 0x6A06, 0x2E00, 0xD000, 0xE0C0, 0x6A43, 0x5163)
    if _unpack_halfwords(data, PLAYER_INTERACTION_BRANCH_COMMIT, len(commit)) != commit:
        raise ValueError("interaction action commit path drifted")
    if struct.unpack_from("<I", data, 0x08009E88 - ROM_BASE)[0] != PLAYER_INTERACTION_ACTION_TABLE:
        raise ValueError("interaction action-table literal drifted")

    # A node_type==1 leaf initializes secondary state and stores state 2.
    leaf_entry = (0x2E01, 0xD000, 0xE740, 0x22F8, 0x0052, 0x50A3)
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE2_ENTRY, len(leaf_entry)) != leaf_entry:
        raise ValueError("interaction leaf state entry drifted")
    if _unpack_halfwords(data, 0x08009E12, 3) != (0x23F6, 0x005B, 0x50E5):
        raise ValueError("interaction state-2 store drifted")

    # Fresh-B dispatch calls 0x08009CB6 only while state==2.  On that edge r5 is
    # zero, and 0x08009CC4 stores r5 to Player+0x1EC through r6.
    return_dispatch = (0x59A3, 0x2B02, 0xD101, 0xF001, 0xF818)
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE2_RETURN_DISPATCH, len(return_dispatch)) != return_dispatch:
        raise ValueError("interaction state-2 B return dispatch drifted")
    if _unpack_halfwords(data, 0x08009CBE, 5) != (0xF000, 0xFD99, 0x2150, 0x51A5, 0x2201):
        raise ValueError("interaction state-2 B return store drifted")

    # State 3 teardown clears state/base/scratch and the active interaction byte.
    teardown = (0xF001, 0xF8D9, 0x23E1, 0x2296, 0x009B, 0x50E2, 0x2300)
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE3_TEARDOWN, len(teardown)) != teardown:
        raise ValueError("interaction state-3 teardown drifted")
    if struct.unpack_from("<I", data, 0x08009828 - ROM_BASE)[0] != PLAYER_INTERACTION_ACTIVE_RAM:
        raise ValueError("interaction active-flag teardown literal drifted")

    common = {
        "state_offset": f"+0x{PLAYER_INTERACTION_STATE_OFFSET:X}",
        "choice_offset": f"+0x{PLAYER_INTERACTION_CHOICE_OFFSET:X}",
        "page_base_offset": f"+0x{PLAYER_INTERACTION_PAGE_BASE_OFFSET:X}",
        "action_table": f"0x{PLAYER_INTERACTION_ACTION_TABLE:08X}",
        "confidence": "high",
    }
    return [
        {**common, "transition": "alignment_to_selector", "handler": "0x0800924C", "from_state": 0, "to_state": 1,
         "input": "alignment complete", "choice": "", "condition": "state == 0",
         "proven_behavior": "renders four action records from Player+0x1E8 page base and enters the four-way selector"},
        {**common, "transition": "selector_up", "handler": "0x08009C74", "from_state": 1, "to_state": 1,
         "input": "fresh Up", "choice": 0, "condition": "state == 1",
         "proven_behavior": "stores choice 0 to Player+0x1E4 and refreshes selector visuals"},
        {**common, "transition": "selector_right", "handler": "0x08009D60", "from_state": 1, "to_state": 1,
         "input": "fresh Right", "choice": 1, "condition": "state == 1",
         "proven_behavior": "stores choice 1 to Player+0x1E4 and refreshes selector visuals"},
        {**common, "transition": "selector_down", "handler": "0x08009DA4", "from_state": 1, "to_state": 1,
         "input": "fresh Down", "choice": 2, "condition": "state == 1",
         "proven_behavior": "stores choice 2 to Player+0x1E4 and refreshes selector visuals"},
        {**common, "transition": "selector_left", "handler": "0x080097D8", "from_state": 1, "to_state": 1,
         "input": "fresh Left", "choice": 3, "condition": "state == 1",
         "proven_behavior": "stores choice 3 to Player+0x1E4 and refreshes selector visuals"},
        {**common, "transition": "selector_branch_confirm", "handler": "0x08009C3E", "from_state": 1, "to_state": 0,
         "input": "fresh A", "choice": "selected", "condition": "selected record +0x20 == 0",
         "proven_behavior": "copies selected record +0x24 child base to Player+0x1E8, then returns to state 0 to render that four-action page"},
        {**common, "transition": "selector_leaf_confirm", "handler": "0x08009DDA", "from_state": 1, "to_state": 2,
         "input": "fresh A", "choice": "selected", "condition": "selected record +0x20 == 1",
         "proven_behavior": "initializes the secondary leaf-action interaction state and stores state 2; exact leaf payload semantics remain unresolved"},
        {**common, "transition": "secondary_b_return", "handler": "0x08009CB6", "from_state": 2, "to_state": 0,
         "input": "fresh B", "choice": "", "condition": "state == 2",
         "proven_behavior": "runs UI cleanup and returns the interaction state to 0; cancel-versus-commit meaning is not statically proved"},
        {**common, "transition": "teardown", "handler": "0x0800963E", "from_state": 3, "to_state": 0,
         "input": "state dispatch", "choice": "", "condition": "state == 3",
         "proven_behavior": "resets Player+0x1E8 and interaction scratch/state, writes 0x03000610=0, restores scene graphics, and marks Player+0x381=1"},
    ]


def extract_player_npc_interaction_alignment(data: bytes) -> list[dict]:
    """Export the full-X/Y bootstrap used by the NPC interaction path.

    This is deliberately separate from ``Player_apply_vertical_target_delta``.
    An NPC fresh-A handler copies its dialogue index and world position into
    Player fields, sets 0x03000610, and Player_update state 0 converts the X/Y
    anchors into one collision-resolved motion request. The intended endpoint
    is the NPC's Y and a 19-pixel horizontal separation on the appropriate side.

    +0x390/+0x394 are therefore not persistent generic target coordinates:
    Player construction and normal update paths also write the sentinel value 1
    to both fields.
    """
    # The source path is reached with r2 == 1 (A-button mask) from 0x08002B4C.
    source_dispatch = (0x6992, 0x2A01, 0xD100, 0xE226)
    if _unpack_halfwords(data, 0x08002B4C, len(source_dispatch)) != source_dispatch:
        raise ValueError("NPC interaction source dispatch drifted")

    if struct.unpack_from("<I", data, 0x08002FF8 - ROM_BASE)[0] != KEYS_CURRENT_RAM:
        raise ValueError("NPC interaction current-key literal drifted")
    if struct.unpack_from("<I", data, 0x08002FFC - ROM_BASE)[0] != KEYS_PREVIOUS_RAM:
        raise ValueError("NPC interaction previous-key literal drifted")
    if struct.unpack_from("<I", data, 0x08003018 - ROM_BASE)[0] != PLAYER_INTERACTION_ACTIVE_RAM:
        raise ValueError("NPC interaction-active literal drifted")

    # Reject if an interaction is already active, require current A set and
    # previous A clear, then copy dial/X/Y to Player and set the active flag.
    source = (0x4919, 0x780B, 0x2B00, 0xD000, 0xE51F,
              0x4B0F, 0x681B, 0x4213, 0xD100, 0xE51A,
              0x4B0D, 0x681B, 0x4013, 0xD000, 0xE515,
              0x20E2, 0x4664, 0x6DEE, 0x0080, 0x5026,
              0x68AE, 0x3008, 0x5026, 0x68EE, 0x3004, 0x5026)
    if _unpack_halfwords(data, 0x08002FB0, len(source)) != source:
        raise ValueError("NPC full-X/Y interaction source drifted")
    active_set = (0x2301, 0x700B)
    if _unpack_halfwords(data, 0x08002FF0, len(active_set)) != active_set:
        raise ValueError("NPC interaction-active flag set drifted")

    # Player_update gates its interaction state machine on 0x03000610; state 0
    # jumps to the full-X/Y bootstrap at 0x0800921A.
    dispatch = (0x4B83, 0x781B, 0x2B00, 0xD0C4,
                0x26F6, 0x0076, 0x59A5, 0x2D00, 0xD100, 0xE31E)
    if _unpack_halfwords(data, PLAYER_INTERACTION_DISPATCH, len(dispatch)) != dispatch:
        raise ValueError("Player interaction state-0 dispatch drifted")

    right_branch = (0x23E4, 0x009B, 0x58E3, 0x68A2, 0x4293, 0xDA00, 0xE191,
                    0x1A9B, 0x4A8F, 0x4694, 0x4463, 0x61A3,
                    0x2201, 0x234C, 0x52E2,
                    0x23E5, 0x009B, 0x58E3, 0x68E2, 0x1A9B, 0x22E3, 0x61E3)
    if _unpack_halfwords(data, PLAYER_INTERACTION_ALIGN_RIGHT_BRANCH, len(right_branch)) != right_branch:
        raise ValueError("Player NPC alignment anchor-at/right branch drifted")
    if struct.unpack_from("<I", data, 0x08009470 - ROM_BASE)[0] != 0xFFFFED00:
        raise ValueError("Player NPC -19px alignment literal drifted")

    left_branch = (0x1A9B, 0x2298, 0x0152, 0x4694, 0x4463, 0x61A3, 0x234C, 0x52E5, 0xE66C)
    if _unpack_halfwords(data, PLAYER_INTERACTION_ALIGN_LEFT_BRANCH, len(left_branch)) != left_branch:
        raise ValueError("Player NPC alignment anchor-left branch drifted")

    state_advance = (0x23F6, 0x2201, 0x005B, 0x50E2)
    if _unpack_halfwords(data, 0x080092C0, len(state_advance)) != state_advance:
        raise ValueError("Player NPC alignment state advance drifted")

    # Normal update writes 1 to both anchor fields, matching constructor
    # initialization and proving they are dual-purpose rather than durable XY.
    normal_reset = (0x21E4, 0x2201, 0x0089, 0x5062, 0x3104, 0x5062)
    if _unpack_halfwords(data, PLAYER_NORMAL_ANCHOR_RESET, len(normal_reset)) != normal_reset:
        raise ValueError("Player normal-path +0x390/+0x394 sentinel reset drifted")
    constructor_reset = (0x3304, 0x50E7, 0x3304, 0x50E7)
    if _unpack_halfwords(data, 0x0800638C, len(constructor_reset)) != constructor_reset:
        raise ValueError("Player constructor +0x390/+0x394 sentinel initialization drifted")

    # The common Player tail calls this collision resolver. Its entry reads
    # +0x18/+0x1C, and its accepted-motion paths add them to +0x08/+0x0C.
    motion_head = (0x234A, 0x2200, 0xB5F0, 0x46D6, 0x464F, 0x4646,
                   0x52C2, 0x6983, 0xB5C0, 0x69C2)
    if _unpack_halfwords(data, PLAYER_MOTION_SOLVER, len(motion_head)) != motion_head:
        raise ValueError("actor collision-motion solver entry drifted")
    x_apply = (0x6881, 0x468C, 0x6983, 0x4463, 0x6083)
    if _unpack_halfwords(data, 0x08004722, len(x_apply)) != x_apply:
        raise ValueError("actor collision-motion X application drifted")
    y_apply = (0x69C2, 0x4694, 0x68C3, 0x4463, 0x60C3)
    if _unpack_halfwords(data, 0x080047D0, len(y_apply)) != y_apply:
        raise ValueError("actor collision-motion Y application drifted")

    common = {
        "source_handler": f"0x{PLAYER_INTERACTION_SOURCE:08X}",
        "trigger": "fresh A press while interaction-active flag is clear",
        "dialogue_index_write": f"actor+0x5C -> Player+0x{PLAYER_DIALOGUE_INDEX_OFFSET:X}",
        "anchor_x_write": f"actor+0x08 -> Player+0x{PLAYER_TARGET_X_OFFSET:X}",
        "anchor_y_write": f"actor+0x0C -> Player+0x{PLAYER_TARGET_Y_OFFSET:X}",
        "interaction_active_global": f"0x{PLAYER_INTERACTION_ACTIVE_RAM:08X}=1",
        "player_update_dispatch": f"0x{PLAYER_INTERACTION_DISPATCH:08X}",
        "interaction_state_offset": f"+0x{PLAYER_INTERACTION_STATE_OFFSET:X}",
        "required_state": 0,
        "alignment_entry": f"0x{PLAYER_INTERACTION_ALIGN_ENTRY:08X}",
        "vertical_formula": f"Player+0x{PLAYER_VERTICAL_DELTA_OFFSET:X}=anchorY-currentY",
        "collision_motion_solver": f"0x{PLAYER_MOTION_SOLVER:08X}",
        "next_state": 1,
        "normal_path_anchor_reset": f"Player+0x{PLAYER_TARGET_X_OFFSET:X}=1; Player+0x{PLAYER_TARGET_Y_OFFSET:X}=1 at 0x{PLAYER_NORMAL_ANCHOR_RESET:08X}",
        "constructor_anchor_init": f"Player+0x{PLAYER_TARGET_X_OFFSET:X}=1; Player+0x{PLAYER_TARGET_Y_OFFSET:X}=1",
        "confidence": "high",
    }
    return [
        {**common,
         "side": "anchor_at_or_right",
         "alignment_handler": f"0x{PLAYER_INTERACTION_ALIGN_RIGHT_BRANCH:08X}",
         "horizontal_formula": f"Player+0x{PLAYER_HORIZONTAL_DELTA_OFFSET:X}=anchorX-currentX-0x{PLAYER_INTERACTION_SEPARATION_FIXED:X}",
         "intended_horizontal_separation_px": -(PLAYER_INTERACTION_SEPARATION_FIXED // 0x100),
         "facing_value": 1},
        {**common,
         "side": "anchor_left",
         "alignment_handler": f"0x{PLAYER_INTERACTION_ALIGN_LEFT_BRANCH:08X}",
         "horizontal_formula": f"Player+0x{PLAYER_HORIZONTAL_DELTA_OFFSET:X}=anchorX-currentX+0x{PLAYER_INTERACTION_SEPARATION_FIXED:X}",
         "intended_horizontal_separation_px": PLAYER_INTERACTION_SEPARATION_FIXED // 0x100,
         "facing_value": 0},
    ]

def extract_ending_vram_effect_copy_model(data: bytes) -> list[dict]:
    """Export the exact two copy-length equations used by 0x08004FE0.

    0x08010C54 is a byte-counted memcpy-like helper (it uses byte loads/stores
    for the tail), so r2 is a byte count, not a word count. The visual meaning
    over successive frames is still intentionally left for emulator/hardware
    tracing.
    """
    prologue = (0x3040, 0xB570, 0x0005, 0x4C14, 0x4A14, 0x0016, 0x436E)
    if _unpack_halfwords(data, ENDING_VRAM_EFFECT, len(prologue)) != prologue:
        raise ValueError("ending VRAM effect prologue drifted")
    literals = struct.unpack_from("<4I", data, ENDING_VRAM_LITERALS - ROM_BASE)
    scene_manager, first_scale, first_source_bias, second_destination = literals
    if literals != (0x030005BC, 1500, 0x0005E801, 0x06010000):
        raise ValueError(f"ending VRAM effect literals drifted: {[hex(v) for v in literals]}")

    second_math = (0x23FA, 0x3418, 0x001A, 0x436A)
    if _unpack_halfwords(data, 0x0800500E, len(second_math)) != second_math:
        raise ValueError("ending VRAM second-copy multiplier drifted")
    second_bias_math = (0x23BD, 0x02DB)
    if _unpack_halfwords(data, 0x08005022, len(second_bias_math)) != second_bias_math:
        raise ValueError("ending VRAM second-copy source bias drifted")

    # memcpy-like helper begins by treating r2 as a byte count and its tail
    # path uses ldrb/strb, proving the count unit.
    helper_head = (0xB5F0, 0x2A0F, 0xD939)
    if _unpack_halfwords(data, COPY_BYTES_HELPER, len(helper_head)) != helper_head:
        raise ValueError("copy helper entry drifted")
    if _unpack_halfwords(data, 0x08010CBE, 2) != (0x5CCC, 0x54EC):
        raise ValueError("copy helper byte-tail path drifted")

    common = {
        "function": f"0x{ENDING_VRAM_EFFECT:08X}",
        "argument_bias": 64,
        "copy_helper": f"0x{COPY_BYTES_HELPER:08X}",
        "scene_manager": f"0x{scene_manager:08X}",
        "confidence": "high",
    }
    return [
        {**common, "copy": 1, "destination": "0x06000000",
         "source_bias": f"0x{first_source_bias:08X}", "bytes_per_step": first_scale,
         "size_formula": f"{first_scale}*(argument+64)",
         "size_at_argument_0": first_scale * 64},
        {**common, "copy": 2, "destination": f"0x{second_destination:08X}",
         "source_bias": "0x0005E800", "bytes_per_step": 250,
         "size_formula": "250*(argument+64)",
         "size_at_argument_0": 250 * 64},
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


def _find_u32_literals(data: bytes, value: int) -> list[int]:
    """Return ROM addresses containing an exact little-endian u32 value."""
    needle = struct.pack("<I", value)
    rows = []
    start = 0
    while True:
        off = data.find(needle, start)
        if off < 0:
            break
        rows.append(ROM_BASE + off)
        start = off + 1
    return rows


def extract_player_wardrobe_state_semantics(data: bytes) -> list[dict]:
    """Export the code-backed Player wardrobe browser state.

    The older workspace label treated 0x03001254 as a shared wardrobe/avatar
    block because one literal reference occurs late in Player_update.  Full
    xref tracing shows that address is the Player animation state/frame block;
    the actual wardrobe selector is Player+0x240 and the wardrobe presentation
    lives inside Player_update rather than at a standalone function entry.

    The demo exposes preview/navigation behavior but no recovered confirm/equip
    action.  In particular, the live Player graphics-bank global remains a
    read-only input along the recovered wardrobe path.
    """
    # Constructor 0x0800621C: zero Player+0x23C and then Player+0x240 before
    # copying the two 14-dword preview tables.
    ctor_signature = (0x238F, 0x4E32, 0x0031, 0x009B, 0x50E5, 0x3304, 0x50E5)
    if _unpack_halfwords(data, 0x08006332, len(ctor_signature)) != ctor_signature:
        raise ValueError("Player wardrobe selector initializer drifted")
    if struct.unpack_from("<I", data, 0x08006400 - ROM_BASE)[0] != 0x08019780:
        raise ValueError("Player wardrobe preview-table base literal drifted")
    if struct.unpack_from("<I", data, 0x08006404 - ROM_BASE)[0] != WARDROBE_LABELS_ADDR:
        raise ValueError("Player wardrobe label-table literal drifted")

    obj_values = struct.unpack_from(
        f"<{WARDROBE_PREVIEW_TABLE_COUNT}I",
        data,
        WARDROBE_PREVIEW_OBJ_ROM - ROM_BASE,
    )
    bg_values = struct.unpack_from(
        f"<{WARDROBE_PREVIEW_TABLE_COUNT}I",
        data,
        WARDROBE_PREVIEW_BG_ROM - ROM_BASE,
    )

    # 0x0800650A..0x08006524 computes Player+0x2B4 + selector*20 and
    # forwards it to the text renderer.
    label_signature = (
        0x2390, 0x9A03, 0x009B, 0x58D3, 0x0099, 0x18C9,
        0x23AD, 0x009B, 0x469C, 0x0089, 0x4461, 0x4694, 0x4461,
    )
    if _unpack_halfwords(data, 0x0800650A, len(label_signature)) != label_signature:
        raise ValueError("Wardrobe label selector formula drifted")

    # Wardrobe heading and prompt are drawn from inside Player_update.
    if fixed_cstr(data, WARDROBE_TITLE_ADDR - ROM_BASE, 32) != "Wardrobe":
        raise ValueError("Wardrobe title literal drifted")
    if fixed_cstr(data, WARDROBE_EXIT_PROMPT_ADDR - ROM_BASE, 32) != "(B) to exit":
        raise ValueError("Wardrobe exit prompt literal drifted")

    # Selected preview page: Player+0x27C + selector*4 -> 0x08004F6C.
    preview_select_signature = (
        0x2390, 0x009B, 0x58E3, 0x339E, 0x009B, 0x18E3, 0x6858,
    )
    if _unpack_halfwords(data, 0x08008E6C, len(preview_select_signature)) != preview_select_signature:
        raise ValueError("Wardrobe selected-preview page formula drifted")

    # Normal browser input checks are Left (0x20), Right (0x10), then B (0x02).
    # Right increments only from 0..5, producing the normal 0..6 range;
    # Left decrements only when >0.  0x080093F4 is a defensive high-value
    # clamp to 7, not a value reached from constructor state by normal arrows.
    left_signature = (0x2220, 0x4B49, 0x469A, 0x681B, 0x421A)
    right_signature = (0x2210, 0x421A)
    b_signature = (0x4652, 0x2302, 0x6812, 0x421A)
    if _unpack_halfwords(data, 0x08008FB8, len(left_signature)) != left_signature:
        raise ValueError("Wardrobe Left-key path drifted")
    if _unpack_halfwords(data, 0x08008FD2, len(right_signature)) != right_signature:
        raise ValueError("Wardrobe Right-key path drifted")
    if _unpack_halfwords(data, 0x08008FE8, len(b_signature)) != b_signature:
        raise ValueError("Wardrobe B-key path drifted")
    if _unpack_halfwords(data, 0x0800951E, 2) != (0x2805, 0xDD00):
        raise ValueError("Wardrobe selector upper-bound path drifted")
    if _unpack_halfwords(data, 0x08009588, 4) != (0x2690, 0x1E43, 0x00B6, 0x51A3):
        raise ValueError("Wardrobe selector decrement path drifted")

    live_bank_init_off = init_ram_to_rom_off(PLAYER_LIVE_GRAPHICS_BANK_RAM)
    live_bank_start = struct.unpack_from("<I", data, live_bank_init_off)[0]
    if live_bank_start != 15:
        raise ValueError(f"Player startup graphics bank drifted: {live_bank_start}")
    live_bank_literals = _find_u32_literals(data, PLAYER_LIVE_GRAPHICS_BANK_RAM)
    if live_bank_literals != [0x08006978, 0x08006CF8]:
        raise ValueError(
            "unexpected direct Player graphics-bank literal set: "
            + ",".join(f"0x{x:08X}" for x in live_bank_literals)
        )

    return [
        {"fact":"selector_field", "value":"player+0x240",
         "evidence":"Player constructor zeros +0x240; Wardrobe text/highlight/navigation code reads and writes this field",
         "confidence":"high"},
        {"fact":"selector_initial_value", "value":"0",
         "evidence":"0x0800633C writes constructor zero register to Player+0x240",
         "confidence":"high"},
        {"fact":"normal_navigation_range", "value":"0..6",
         "evidence":"Left decrements only above 0; Right path 0x0800951E increments only when selector<=5; 0x080093F4 is defensive clamp-to-7 for an already-high value",
         "confidence":"high"},
        {"fact":"normal_navigation_inputs", "value":"Left;Right;B",
         "evidence":"fresh-key checks at 0x08008FBE/0x08008FD2/0x08008FE8 use GBA masks 0x20/0x10/0x02",
         "confidence":"high"},
        {"fact":"confirm_input", "value":"none recovered",
         "evidence":"Wardrobe browser input path exposes Left/Right navigation and '(B) to exit'; no A-confirm/equip branch is present in the recovered browser path",
         "confidence":"high"},
        {"fact":"wardrobe_title", "value":"Wardrobe",
         "evidence":"literal 0x08A8C47C drawn at Player_update internal path 0x08008E30",
         "confidence":"high"},
        {"fact":"wardrobe_exit_prompt", "value":"(B) to exit",
         "evidence":"literal 0x08A8C488 drawn at 0x08008E60",
         "confidence":"high"},
        {"fact":"label_draw_function", "value":f"0x{WARDROBE_LABEL_DRAW:08X}",
         "evidence":"called from Player_update at 0x08008E68 and after selector changes at 0x08009406/0x0800953A",
         "confidence":"high"},
        {"fact":"label_formula", "value":"player+0x2B4 + selector*20",
         "evidence":"0x0800650A..0x08006524 computes selector*5*4 then adds Player+0x2B4 before text draw",
         "confidence":"high"},
        {"fact":"preview_obj_bank_table", "value":"player+0x244 <- 0x080197B0",
         "evidence":"constructor copies 0x38 bytes; Wardrobe preview loop 0x08008EC6 consumes 14 dwords and multiplies each by Player+0x1DC (192) before dynamic OBJ upload",
         "confidence":"high"},
        {"fact":"preview_obj_bank_values_first_group", "value":";".join(str(x) for x in obj_values[:7]),
         "evidence":"first seven dwords of canonical ROM table 0x080197B0; seven normal browser choices use the matching preview row",
         "confidence":"high"},
        {"fact":"preview_obj_bank_values_second_group", "value":";".join(str(x) for x in obj_values[7:]),
         "evidence":"second seven dwords of canonical ROM table 0x080197CC; all are zero in the public demo",
         "confidence":"high"},
        {"fact":"preview_bg_page_table", "value":"player+0x27C <- 0x080197E8",
         "evidence":"constructor copies 0x38 bytes; selector-indexed load at 0x08008E6C/0x0800952C/0x08009590 feeds 0x08004F6C",
         "confidence":"high"},
        {"fact":"preview_bg_page_values_normal_range", "value":";".join(str(x) for x in bg_values[:7]),
         "evidence":"selector 0..6 directly indexes the first seven dwords copied to Player+0x27C",
         "confidence":"high"},
        {"fact":"preview_bg_loader", "value":"0x08004F6C",
         "evidence":"copies 0x2000 bytes for selected page into BG VRAM 0x06003000; page contributes source offset page*0x2000",
         "confidence":"high"},
        {"fact":"live_player_graphics_bank", "value":"0x0300103C = 15 at startup",
         "evidence":"initialized-data source 0x08A8DFEC contains 15; Player_draw uses this as the live graphics-bank multiplier",
         "confidence":"high"},
        {"fact":"live_bank_wardrobe_mutation", "value":"none recovered",
         "evidence":"canonical ROM contains only two direct 0x0300103C literals (0x08006978,0x08006CF8), both used read-only by Player draw paths; wardrobe navigation writes only Player+0x240 and preview loaders",
         "confidence":"high"},
        {"fact":"animation_state_block", "value":"0x03001254",
         "evidence":"direct literal xrefs are in Player_draw and Player_update animation/frame logic (state at +0, frame at +4); Wardrobe selector is object field Player+0x240 instead",
         "confidence":"high"},
        {"fact":"old_wardrobe_state_label", "value":"rejected",
         "evidence":"0x08008E30 is inside Player_update (entry 0x080081B0), not a standalone Wardrobe function; its later 0x03001254 reference belongs to animation logic after the Wardrobe browser block",
         "confidence":"high"},
        {"fact":"reconstruction_policy", "value":"keep proven default outfit only",
         "evidence":"the demo proves browse/preview data but no equip action or live-bank mutation; alternate wardrobe graphics must not be made gameplay-selectable without new evidence",
         "confidence":"high"},
    ]


def extract_player_wardrobe_slots(data: bytes) -> list[dict]:
    """Combine labels with the seven normally navigable preview choices."""
    labels = extract_wardrobe_labels(data)
    obj_values = struct.unpack_from(
        f"<{WARDROBE_PREVIEW_TABLE_COUNT}I",
        data,
        WARDROBE_PREVIEW_OBJ_ROM - ROM_BASE,
    )
    bg_values = struct.unpack_from(
        f"<{WARDROBE_PREVIEW_TABLE_COUNT}I",
        data,
        WARDROBE_PREVIEW_BG_ROM - ROM_BASE,
    )
    live_bank = struct.unpack_from("<I", data, init_ram_to_rom_off(PLAYER_LIVE_GRAPHICS_BANK_RAM))[0]
    rows = []
    for slot, label_row in enumerate(labels):
        normal = slot < WARDROBE_NORMAL_CHOICE_COUNT
        rows.append({
            "slot": slot,
            "label": label_row["label"].strip(),
            "normal_navigation_reachable": "yes" if normal else "no",
            "preview_obj_bank": obj_values[slot] if normal else "",
            "preview_bg_page": bg_values[slot] if normal else "",
            "matches_startup_live_bank": "yes" if normal and obj_values[slot] == live_bank else "no",
            "equippable_in_demo": "no proven equip action",
            "evidence": (
                "normal selector range 0..6; first preview group and selector-indexed BG-page table"
                if normal else
                "outside normal 0..6 Left/Right selector range"
            ),
            "confidence": "high",
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

    wardrobe_state_rows = extract_player_wardrobe_state_semantics(data)
    write_csv(args.out / "player_wardrobe_state_semantics.csv",
              ["fact","value","evidence","confidence"],
              wardrobe_state_rows)

    wardrobe_slot_rows = extract_player_wardrobe_slots(data)
    write_csv(args.out / "player_wardrobe_slots.csv",
              ["slot","label","normal_navigation_reachable","preview_obj_bank","preview_bg_page",
               "matches_startup_live_bank","equippable_in_demo","evidence","confidence"],
              wardrobe_slot_rows)

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
        {"fact":"wardrobe_selector", "value":"player+0x240", "evidence":"constructor initializes 0; Wardrobe label/highlight/navigation paths read/write this field; normal arrow range 0..6"},
        {"fact":"animation_state_block", "value":"0x03001254", "evidence":"Player_draw/Player_update state+frame block; old shared wardrobe/avatar label rejected by full xref trace"},
        {"fact":"live_graphics_bank", "value":"0x0300103C = 15 at startup", "evidence":"Player_draw source-bank multiplier; recovered Wardrobe path previews alternatives but does not mutate this live bank"},
        {"fact":"known_character_source_sample", "value":"source base 2198", "evidence":"valid 16x32 Vika-style frame reconstruction; not claimed as constructor/default outfit"},
        {"fact":"normal_idle_branch", "value":"source base 3468 at bank 15 / idle phase 1", "evidence":"draw branch when player+0x1E0 == 0; reconstruction explicitly chooses selector-0 behavior"},
        {"fact":"player_plus_1e0", "value":"constructor leaves field uninitialized", "evidence":"constructor skips +0x1E0 and malloc/new allocator is not zero-filling; draw/update read it"},
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

    gate_geometry_row = extract_level10_gate_collision_geometry(data)
    write_csv(args.out / "level10_gate_collision_geometry.csv", list(gate_geometry_row), [gate_geometry_row])

    gate_motion_rows = extract_level10_gate_forced_motion(data)
    write_csv(args.out / "level10_gate_forced_motion.csv",
              ["turn","handler","target_x_px","target_y_px","target_x_fixed","target_y_fixed",
               "trigger","keys_current","keys_previous","helper","player_target_x_offset",
               "player_target_y_offset","player_vertical_delta_offset","helper_behavior",
               "generic_portal_handoff","post_key_reads_portto","confidence"], gate_motion_rows)

    vertical_target_call_rows = extract_player_vertical_target_calls(data)
    write_csv(args.out / "player_vertical_target_calls.csv",
              ["callsite","context","target_x_write","target_y_write","helper",
               "helper_consumes_target_x","helper_consumes_target_y",
               "helper_clears_target_x","helper_clears_target_y","confidence"],
              vertical_target_call_rows)

    interaction_action_rows = extract_player_interaction_action_table(data)
    write_csv(args.out / "player_interaction_action_table.csv",
              ["index","source_rom_addr","label","record_size","visual_selector","node_type",
               "field_24","field_28","node_role","child_base","children","confidence"],
              interaction_action_rows)

    interaction_secondary_topic_rows = extract_player_interaction_secondary_topics(data)
    write_csv(args.out / "player_interaction_secondary_topics.csv",
              ["action_index","action_label","topic_start","topic_count","topics","builder",
               "topic_table","topic_stride","field_24_role","field_28_role",
               "zero_count_behavior","confidence"],
              interaction_secondary_topic_rows)

    interaction_topic_response_rows = extract_player_interaction_topic_response_banks(data)
    write_csv(args.out / "player_interaction_topic_response_banks.csv",
              ["topic_index","topic","profile_table","profile_topic_value_offset",
               "subject_pointer_table","subject_response_base","subject_variants_per_topic",
               "subject_profile_value_0_slots","subject_profile_value_1_slots","subject_profile_value_2_slots",
               "subject_profile_value_3_slots","subject_profile_value_4_slots","criticize_pointer_table",
               "criticize_response_base","criticize_variants_per_topic",
               "criticize_profile_value_0_slots","criticize_profile_value_1_slots","criticize_profile_value_2_slots",
               "criticize_profile_value_3_slots","criticize_profile_value_4_slots","response_stride",
               "neutral_response","neutral_response_addr","profile_value_dispatch","confidence"],
              interaction_topic_response_rows)

    interaction_topic_response_text_rows = extract_player_interaction_topic_response_texts(data)
    write_csv(args.out / "player_interaction_topic_response_texts.csv",
              ["action","topic_index","topic","slot","profile_value_class","variant","rom_addr",
               "response_stride","text","confidence"],
              interaction_topic_response_text_rows)

    interaction_state2_cursor_row = extract_player_interaction_state2_cursor(data)
    write_csv(args.out / "player_interaction_state2_cursor.csv", list(interaction_state2_cursor_row),
              [interaction_state2_cursor_row])

    interaction_runtime_dispatch_rows = extract_player_interaction_runtime_dispatch(data)
    write_csv(args.out / "player_interaction_runtime_dispatch.csv",
              ["action_index","action_label","page_base","quadrant","runtime_path","dispatcher",
               "dispatch_key","page_base_consulted","shared_flag_offset","reconstruction_warning","confidence"],
              interaction_runtime_dispatch_rows)

    interaction_followup_row = extract_player_interaction_followup_handshake(data)
    write_csv(args.out / "player_interaction_followup_handshake.csv", list(interaction_followup_row),
              [interaction_followup_row])

    interaction_profile_target_row = extract_player_interaction_profile_target_step(data)
    write_csv(args.out / "player_interaction_profile_target_step.csv", list(interaction_profile_target_row),
              [interaction_profile_target_row])

    interaction_score_mirror_row = extract_player_interaction_score_mirror_semantics(data)
    write_csv(args.out / "player_interaction_score_mirror_semantics.csv",
              list(interaction_score_mirror_row), [interaction_score_mirror_row])

    interaction_profile_selector_rows = extract_player_interaction_profile_selector_table(data)
    write_csv(args.out / "player_interaction_profile_selector_table.csv",
              ["selector_index","profile_ptr","initialized_rom_addr","name","record_kind","record_size",
               "selector_source","behavior_confidence"],
              interaction_profile_selector_rows)

    interaction_profile_reachability_rows = extract_player_interaction_profile_selector_reachability(data)
    write_csv(args.out / "player_interaction_profile_selector_reachability.csv",
              ["selector_index","profile_name","profile_kind","canonical_reachability","actor_rom_addr",
               "actor_state","actor_dial","actor_level","social_bootstrap","only_npc_update_handoff",
               "selector_copy","npc_update_state_write","npc_update_dial_write","reachability_scope","confidence"],
              interaction_profile_reachability_rows)

    interaction_profile_field_usage_rows = extract_player_interaction_profile_field_usage(data)
    write_csv(args.out / "player_interaction_profile_field_usage.csv",
              ["profile_field","proper_profile_initial_values","runtime_usage","evidence_sites","working_name",
               "selector_literal_ref_count","confidence"], interaction_profile_field_usage_rows)

    interaction_social_profile_topic_rows = extract_player_interaction_social_profile_topics(data)
    write_csv(args.out / "player_interaction_social_profile_topics.csv",
              ["selector_index","profile_ptr","name","profile_field_14_initial","topic_index","topic",
               "rating","rating_range","record_kind","behavior_confidence"],
              interaction_social_profile_topic_rows)

    interaction_social_score_row = extract_player_interaction_social_score_semantics(data)
    write_csv(args.out / "player_interaction_social_score_semantics.csv", list(interaction_social_score_row),
              [interaction_social_score_row])

    interaction_profile_topic_layout_rows = extract_player_interaction_profile_topic_layout_mismatch(data)
    write_csv(args.out / "player_interaction_profile_topic_layout_mismatch.csv",
              ["selector_index","name","topic_index","topic","profile_field_offset","raw_value",
               "raw_value_hex","ascii_le","valid_response_class","explicit_dispatch_range",
               "layout_finding","behavior_confidence"],
              interaction_profile_topic_layout_rows)

    interaction_profile_integrity_row = extract_player_interaction_profile_selector_integrity(data)
    write_csv(args.out / "player_interaction_profile_selector_integrity.csv",
              list(interaction_profile_integrity_row), [interaction_profile_integrity_row])

    interaction_depth_row = extract_player_interaction_depth_semantics(data)
    write_csv(args.out / "player_interaction_depth_semantics.csv", list(interaction_depth_row),
              [interaction_depth_row])

    interaction_transition_rows = extract_player_interaction_state_transitions(data)
    write_csv(args.out / "player_interaction_state_transitions.csv",
              ["transition","handler","from_state","to_state","input","choice","condition","proven_behavior",
               "state_offset","choice_offset","page_base_offset","action_table","confidence"],
              interaction_transition_rows)

    interaction_alignment_rows = extract_player_npc_interaction_alignment(data)
    write_csv(args.out / "player_npc_interaction_alignment.csv",
              ["side","source_handler","trigger","dialogue_index_write","anchor_x_write","anchor_y_write",
               "interaction_active_global","player_update_dispatch","interaction_state_offset","required_state",
               "alignment_entry","alignment_handler","horizontal_formula","intended_horizontal_separation_px",
               "vertical_formula","facing_value","collision_motion_solver","next_state","normal_path_anchor_reset",
               "constructor_anchor_init","confidence"], interaction_alignment_rows)

    ending_copy_rows = extract_ending_vram_effect_copy_model(data)
    write_csv(args.out / "ending_vram_effect_copy_model.csv",
              ["copy","function","destination","source_bias","bytes_per_step","argument_bias",
               "size_formula","size_at_argument_0","copy_helper","scene_manager","confidence"],
              ending_copy_rows)

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

    print(f"exported {len(route_rows)} route waypoints, {len(message_rows)} message records, {len(state_rows)} NPC state modes, {len(wardrobe_rows)} wardrobe labels, {len(wardrobe_slot_rows)} wardrobe slots, {len(spawn_factory_rows)} spawn factories")

if __name__ == "__main__":
    main()
