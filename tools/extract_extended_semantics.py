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
LEVEL_RECORD_SOURCE_ROM = 0x08A8D9C0
LEVEL_RECORD_COUNT = 11
LEVEL_RECORD_SIZE = 0x40
PLAYER_IDLE_SELECTOR_LOAD_ADDR = 0x08005CFC
PLAYER_IDLE_SELECTOR_STORE_ADDR = 0x08005D06


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
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


def extract_story_overlay_update_order(data: bytes) -> list[dict]:
    """Prove story overlays are inserted before the physical level actor list.

    ``load_level_record_resources`` calls the same actor-list loader twice.  The
    selected story-overlay list is submitted first at 0x08005996; only after
    the fixed-map/stream setup does it load LevelRecord+0x38 and submit the
    physical actor list at 0x080059AE.  The generic GameplayScene object
    manager preserves insertion order, so overlay NPC updates precede every
    physical-list object, including Player.
    """
    expected = (
        0x6B2B, 0x009A, 0x4B22, 0x4E23, 0x189B, 0x6B59, 0x0030,
        0xF7FB, 0xFB85,
        0x69A8, 0xF7FF, 0xFF1E, 0x2201, 0x491F, 0x481F,
        0xF004, 0xFD2B,
        0x6BA1, 0x0030, 0xF7FB, 0xFB79,
    )
    if _unpack_halfwords(data, 0x08005988, len(expected)) != expected:
        raise ValueError('story-overlay/physical actor-list load order drifted')
    first_target = _thumb1_bl_target(data, 0x08005996 - ROM_BASE)
    second_target = _thumb1_bl_target(data, 0x080059AE - ROM_BASE)
    if first_target != STORY_ENTITY_LIST_LOADER or second_target != STORY_ENTITY_LIST_LOADER:
        raise ValueError(
            f'actor-list loader calls drifted: first={first_target!r}, second={second_target!r}'
        )
    slots = extract_story_entity_overlay_slots(data)
    if len(slots) != 2 or slots[0]['actor_list_ptr'] != slots[1]['actor_list_ptr']:
        raise ValueError('public-demo story-overlay slot identity drifted')

    return [
        {
            'phase': 'story_overlay_list',
            'call_site': '0x08005996',
            'loader': f'0x{STORY_ENTITY_LIST_LOADER:08X}',
            'list_source': 'selected 0x0300083C + sceneSelector*4 slot',
            'relative_order': 'first',
            'runtime_consequence': 'all loaded story-overlay objects are inserted before the physical level actor list',
            'confidence': 'high',
        },
        {
            'phase': 'physical_level_actor_list',
            'call_site': '0x080059AE',
            'loader': f'0x{STORY_ENTITY_LIST_LOADER:08X}',
            'list_source': 'LevelRecord+0x38',
            'relative_order': 'second',
            'runtime_consequence': 'Player and all other physical level objects update after story overlays',
            'confidence': 'high',
        },
        {
            'phase': 'clean_room_overlay_phase',
            'call_site': 'n/a',
            'loader': 'n/a',
            'list_source': 'ROM insertion-order consequence',
            'relative_order': 'before Player',
            'runtime_consequence': 'gb_actor_system_update_overlays must remain before gb_player_update',
            'confidence': 'high',
        },
    ]


def extract_story_overlay_activation_policy(data: bytes) -> dict:
    """Prove the public-demo initial story-overlay list/level gate policy.

    load_level_record_resources reads the scene selector from 0x030005BC+0x30,
    indexes the current-level global block rooted at 0x03000808, and loads the
    overlay-list pointer from +0x34 + selector*4. The two initialized slots
    both point at the same 16-record list, so that selector does not swap
    story populations in the public demo. Actor policy 0x080043AC then keeps
    entities whose signed level field is -1 or equals the current level.
    """
    slots = extract_story_entity_overlay_slots(data)
    if len(slots) != 2:
        raise ValueError('story overlay slot count drifted')

    if struct.unpack_from('<I', data, 0x08005A14 - ROM_BASE)[0] != 0x030005BC:
        raise ValueError('story overlay scene-manager base literal drifted')
    if struct.unpack_from('<I', data, 0x08005A18 - ROM_BASE)[0] != 0x03000808:
        raise ValueError('story overlay current-level block literal drifted')
    selector_seq = (0x6B2B, 0x009A, 0x4B22, 0x4E23, 0x189B, 0x6B59)
    if _unpack_halfwords(data, 0x08005988, len(selector_seq)) != selector_seq:
        raise ValueError('story overlay selector sequence drifted')

    if struct.unpack_from('<I', data, 0x080043DC - ROM_BASE)[0] != 0x03000808:
        raise ValueError('story overlay current-level gate literal drifted')
    gate_seq = (0x2356, 0x5EC3, 0xB510, 0x0004, 0x1C5A, 0xD007,
                0x4A08, 0x6812, 0x4293, 0xD003)
    if _unpack_halfwords(data, 0x080043AC, len(gate_seq)) != gate_seq:
        raise ValueError('story overlay level-gate sequence drifted')

    slot0 = slots[0]['actor_list_ptr']
    slot1 = slots[1]['actor_list_ptr']
    return {
        'current_level_global': '0x03000808',
        'scene_selector_global': '0x030005EC',
        'overlay_slot_base': '0x0300083C',
        'slot0_list': slot0,
        'slot1_list': slot1,
        'slot_lists_identical': 'yes' if slot0 == slot1 else 'no',
        'level_gate_function': '0x080043AC',
        'entity_level_field': 'actor+0x56',
        'level_rule': '-1 wildcard or entity level == current level',
        'initial_population_conclusion': 'selector does not change story overlay list in public demo; initial visibility is level-gated',
        'scope_caveat': 'initial population policy does not replace per-entity runtime/progression behavior or persistent consumption',
        'confidence': 'high',
    }


def extract_npc_sprite_pipeline(data: bytes) -> list[dict]:
    """Export code-backed NPC dynamic-OBJ source selection facts.

    NPC draw 0x0800274C reads an initialized source-bank base from IWRAM
    0x030007FC. Startup maps ROM offset 0xA8D738 to IWRAM 0x03000788,
    making the source initializer a directly recoverable ROM dword.
    """
    init_off = init_ram_to_rom_off(NPC_SOURCE_BIAS_RAM)
    value = struct.unpack_from("<I", data, init_off)[0]
    init_rom_addr = ROM_BASE + init_off

    # Guard the draw-side animation facts with exact canonical instructions.
    invisible_gate = (0x234E, 0xB5E0, 0x5EC5, 0xB085, 0x0004, 0x2D01, 0xD06B)
    if _unpack_halfwords(data, 0x08002756, len(invisible_gate)) != invisible_gate:
        raise ValueError("NPC draw invisibility gate drifted")
    frame_counter = (0x2350, 0x5EE2, 0x6FA3, 0x0011, 0x4293, 0xDD01,
                     0x2301, 0x67A3, 0x6FE3, 0x2B00, 0xDD6C)
    if _unpack_halfwords(data, 0x08002770, len(frame_counter)) != frame_counter:
        raise ValueError("NPC draw frame/countdown sequence drifted")
    cadence_reload = (0x2350, 0x5EE1, 0x234E, 0x5EE5, 0x2008)
    if _unpack_halfwords(data, 0x080028EE, len(cadence_reload)) != cadence_reload:
        raise ValueError("NPC draw cadence reload sequence drifted")

    # Draw geometry/depth contract.  NPC_draw compares actor Y against the
    # current Player Y, stores priority 1 for actors below the Player and 2
    # otherwise, then submits bottom/top 16x16 cells at exact actor X and
    # Y-16/Y-32 respectively.  No historical -8 X bias exists in the ROM.
    depth_select = (0x68E3, 0x1219, 0x4B5D, 0x6A5B, 0x68DB, 0x121B,
                    0x4299, 0xDD5C, 0x2384, 0x2201, 0x50E2, 0x3B83,
                    0x9302)
    if _unpack_halfwords(data, 0x0800278A, len(depth_select)) != depth_select:
        raise ValueError("NPC draw depth-priority selection drifted")
    depth_else = (0x2384, 0x2202, 0x50E2, 0x3B82, 0x9302)
    if _unpack_halfwords(data, 0x08002854, len(depth_else)) != depth_else:
        raise ValueError("NPC draw priority-2 fallback drifted")
    bottom_submit = (0x68A3, 0x1218, 0x4B54, 0x46B1, 0x681B, 0x59A6,
                     0x1AC0, 0x46B0, 0x4B52, 0x264C, 0x681B, 0x3910,
                     0x1AC9)
    if _unpack_halfwords(data, 0x080027B0, len(bottom_submit)) != bottom_submit:
        raise ValueError("NPC bottom-sprite screen anchor drifted")
    top_submit = (0x68E3, 0x1219, 0x4B3B, 0x681B, 0x3920, 0x1AC9,
                  0x68A3, 0x1218, 0x4B37, 0x681B, 0x1AC0, 0x2384,
                  0x58E3, 0x9300, 0x2303)
    if _unpack_halfwords(data, 0x0800281A, len(top_submit)) != top_submit:
        raise ValueError("NPC top-sprite screen anchor drifted")

    # NPC constructor initializes inherited setglobal to 1.  The common
    # level/global policy only writes inherited +0x31 when setglobal == 0;
    # therefore ordinary NPCs retain +0x31 clear and take the engine's normal
    # spatial-dispatch/camera-cull path before NPC_draw is reached.
    npc_setglobal_default = (0x4B23, 0x2201, 0x6543, 0x2331, 0x64C5,
                             0x6505, 0x65C5, 0x6605, 0x6645, 0x6582,
                             0x54C5)
    if _unpack_halfwords(data, 0x080039CA, len(npc_setglobal_default)) != npc_setglobal_default:
        raise ValueError("NPC inherited setglobal default drifted")
    global_policy = (0x2358, 0x5EE3, 0x2B00, 0xD102, 0x2201, 0x3331, 0x54E2)
    if _unpack_halfwords(data, 0x080043C8, len(global_policy)) != global_policy:
        raise ValueError("actor setglobal/+0x31 policy drifted")

    # State 3 rewrites actor+0x4E from its constructor-copied base at +0xEC.
    # The shared 0x08002BF2 tail commits base+8/6 frames; upward branches add
    # another 8 before entering the same tail, yielding base+16/6.  Idle at
    # 0x0800327A restores base/8.
    moving_family = (0x3308, 0x224E, 0x52AB, 0x2350, 0x3A48, 0x52EA)
    if _unpack_halfwords(data, 0x08002BF2, len(moving_family)) != moving_family:
        raise ValueError("NPC state-3 moving-family sequence drifted")
    idle_family = (0x2208, 0x21F4, 0x506A, 0x39A6, 0x526B, 0x2350, 0x52EA)
    if _unpack_halfwords(data, 0x0800327A, len(idle_family)) != idle_family:
        raise ValueError("NPC state-3 idle-family sequence drifted")

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
        {"fact":"invisible_legs_color", "value":"1",
         "evidence":"0x08002756..0x08002762 branches to draw epilogue before frame/countdown mutation"},
        {"fact":"frame_field", "value":"actor+0x78 (1-based)",
         "evidence":"0x08002770..0x0800277E clamps to 1..actor+0x50; 0x08002860 advances before staging when countdown expires"},
        {"fact":"countdown_field", "value":"actor+0x7C",
         "evidence":"0x08002780..0x08002788 decrements positive countdown; zero/negative enters the advance/reload path"},
        {"fact":"countdown_reload", "value":"5 * trunc(8 / actor+0x50)",
         "evidence":"0x080028EE..0x08002900 loads frame count, divides 8 by it, then multiplies quotient by 5"},
        {"fact":"normal_oam_geometry", "value":"two stacked 16x16 sprites; bottom then top",
         "evidence":"0x080027B0..0x08002838 submits Y-16 first and Y-32 second through 0x0800A8F0"},
        {"fact":"normal_screen_anchor", "value":"x=actorX-cameraX; y=actorY-cameraY-16/-32",
         "evidence":"0x080027B0..0x080027C8 and 0x0800281A..0x0800282E; no -8 X bias"},
        {"fact":"depth_priority", "value":"1 when actorY > PlayerY; otherwise 2",
         "evidence":"0x0800278A..0x080027A2 selects 1; 0x08002854..0x0800285E selects 2; actor+0x84 feeds both OAM submits"},
        {"fact":"spatial_dispatch", "value":"setglobal default 1 => inherited +0x31 clear => camera-culled before NPC_draw",
         "evidence":"NPC constructor 0x080039CA..0x080039DE sets +0x58=1/+0x31=0; common policy 0x080043C8..0x080043D4 only sets +0x31 when +0x58==0"},
        {"fact":"state3_base_family_field", "value":"actor+0xEC",
         "evidence":"NPC constructor copies serialized legsColor into the state-3 base-family field before route updates"},
        {"fact":"state3_directional_families", "value":"base / base+8 / base+16",
         "evidence":"8 / 6 / 6 frames: idle 0x0800327A restores base/8; horizontal/down 0x08002BF2 selects base+8/6; upward branches 0x08002D38..0x08002D94 select base+16/6"},
        {"fact":"state3_movement_codes", "value":"down=0; down-right=1; right=2; up-right=3; up=4; up-left=5; left=6; down-left=7; idle=8",
         "evidence":"actor+0xF4 writes across 0x08002BE4..0x08002D94 and 0x08003268..0x080032BE"},
        {"fact":"semantic_warning", "value":"runtime npc class is not synonymous with human NPC",
         "evidence":"standalone state=4 records with subtype=6 render paper/sketch-like graphics through the same class"},
    ]


def extract_player_sprite_pipeline(data: bytes) -> list[dict]:
    """Export ROM-guarded Player draw/animation visual contracts."""
    # Normal avatar draw: exact actor X, bottom Y-16 then top Y-32, both
    # 16x16 OAM shape 3 at priority 2.
    bottom_submit = (0x68A3, 0x1218, 0x683B, 0x6962, 0x1AC0, 0x68E3,
                     0x1A99, 0x464B, 0x3101, 0x681B, 0x1209, 0x1AC9,
                     0x2E02, 0xD100, 0xE15D, 0x264C, 0x2502, 0x5FA2,
                     0x2380, 0x0292, 0x405A, 0x9500, 0x3B7D,
                     0xF004, 0xF904)
    if _unpack_halfwords(data, 0x080066B6, len(bottom_submit)) != bottom_submit:
        raise ValueError("Player bottom OAM submit contract drifted")
    top_submit = (0x5FA2, 0x2360, 0x0292, 0x405A, 0x6961, 0x68E3,
                  0x1A59, 0x464B, 0x3101, 0x681B, 0x1209, 0x3910,
                  0x1AC9, 0x68A3, 0x1218, 0x683B, 0x9500, 0x1AC0,
                  0x2303, 0xF004, 0xF8EF)
    if _unpack_halfwords(data, 0x080066E8, len(top_submit)) != top_submit:
        raise ValueError("Player top OAM submit contract drifted")

    # Player_update normally keeps the state-derived reset (8 for idle), but
    # any non-zero +0x1E0 selector overwrites that reset with 5.
    alt_idle_cadence = (0x20F0, 0x0040, 0x5820, 0x2800, 0xD101,
                        0x2A08, 0xD000, 0x2205, 0x66EA)
    if _unpack_halfwords(data, 0x08008382, len(alt_idle_cadence)) != alt_idle_cadence:
        raise ValueError("Player alternate-idle countdown override drifted")

    # Fifth-sketch monster branch seeds priority 2 and reuses it for all five
    # OAM submits.
    monster_priority = (0x2502, 0x225A, 0x4F23, 0x68A3, 0x1218, 0x683B,
                        0x3914, 0x1AC0, 0x9500, 0x2303, 0x32FF,
                        0xF004, 0xF806)
    if _unpack_halfwords(data, 0x080068CA, len(monster_priority)) != monster_priority:
        raise ValueError("Player monster priority/OAM sequence drifted")

    # Levels 9/10 branch to four fixed initial-OBJ cells before returning to
    # the normal Player path.  The tile arguments 0x17C/0x17E/0x19C/0x19E
    # are encoded as 0xBE/0xBF/0xCE/0xCF << 1, all with priority 2.
    level_gate = (0x4BD0, 0x681B, 0x2B09, 0xD100, 0xE2F5,
                  0x2B0A, 0xD100, 0xE29B)
    if _unpack_halfwords(data, 0x08006622, len(level_gate)) != level_gate:
        raise ValueError("Player Level-9/10 fixed-composite dispatch drifted")
    level10_head = (0x25DD, 0x4B63, 0x4699, 0x681B, 0x00AD, 0x1AE9,
                    0x683A, 0x4B61, 0x1A98, 0x469B, 0x22BE, 0x2302,
                    0x0052, 0x469A, 0x9300, 0x3301, 0xF003, 0xFEB1,
                    0x464B, 0x681B, 0x1AE9, 0x683B, 0x4D5B, 0x22BF,
                    0x1AE8, 0x4653, 0x0052, 0x9300, 0x26E1, 0x3301,
                    0xF003, 0xFEA3)
    if _unpack_halfwords(data, 0x08006B6A, len(level10_head)) != level10_head:
        raise ValueError("Player Level-10 fixed-composite head drifted")
    shared_tail = (0x00B6, 0x464B, 0x681B, 0x1AF1, 0x465B, 0x683A,
                   0x1A98, 0x4653, 0x22CE, 0x9300, 0x0052, 0x3301,
                   0xF003, 0xFE95, 0x464B, 0x681B, 0x1AF1, 0x683B,
                   0x22CF, 0x1AE8, 0x4653, 0x0052, 0x9300, 0x3301,
                   0xF003, 0xFE89)
    if _unpack_halfwords(data, 0x08006BAA, len(shared_tail)) != shared_tail:
        raise ValueError("Player Level-9/10 fixed-composite lower-row tail drifted")
    level9_head = (0x25EE, 0x4B38, 0x4699, 0x681B, 0x006D, 0x1AE9,
                   0x23FC, 0x683A, 0x005B, 0x1A98, 0x22BE, 0x469B,
                   0x3BF7, 0x3BFF, 0x469A, 0x9300, 0x0052, 0x3301,
                   0xF003, 0xFE58, 0x464B, 0x681B, 0x1AE9, 0x683B,
                   0x352C, 0x1AE8, 0x22BF, 0x4653, 0x26F6, 0x9300,
                   0x0052, 0x3301, 0xF003, 0xFE4A)
    if _unpack_halfwords(data, 0x08006C18, len(level9_head)) != level9_head:
        raise ValueError("Player Level-9 parked-bicycle composite head drifted")

    # Shared ride-state gate: Player_draw suppresses the parked Level-9/10
    # composite when 0x030005F4 == 2 and enters the five-sprite riding path.
    bicycle_mode_global = struct.unpack_from('<I', data, 0x08006960 - ROM_BASE)[0]
    if bicycle_mode_global != 0x030005F4:
        raise ValueError("Player bicycle-mode global literal drifted")
    bicycle_gate = (0x681B, 0x2B02, 0xD007)
    if _unpack_halfwords(data, 0x0800661C, len(bicycle_gate)) != bicycle_gate:
        raise ValueError("Player bicycle-mode draw gate drifted")
    bicycle_frame_offsets = struct.unpack_from('<6I', data, 0x08019968 - ROM_BASE)
    if bicycle_frame_offsets != (0, 4, 8, 0x50, 0x54, 0x58):
        raise ValueError(f"Player bicycle frame offsets drifted: {bicycle_frame_offsets!r}")

    return [
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
        {"fact":"normal_idle_selector0", "value":"mirrored sources 3468,3470,3532,3534,3534,3532,3470,3468", "evidence":"Player_draw state-8 branch when Player+0x1E0 != 1"},
        {"fact":"normal_idle_selector1", "value":"contiguous sources 3392,3394,3396,3398,3400,3402,3404,3406", "evidence":"Player_draw state-8 branch at 0x08006C06 when Player+0x1E0 == 1"},
        {"fact":"player_plus_1e0", "value":"current LevelRecord+0x3C copied during scene activation", "evidence":"0x08005CFC loads record+0x3C; 0x08005D06 stores to Player+0x1E0"},
        {"fact":"normal_oam_geometry", "value":"two stacked 16x16 sprites; bottom then top", "evidence":"0x080066B6..0x08006710 submits bottom then top via 0x0800A8F0"},
        {"fact":"normal_screen_anchor", "value":"x=PlayerX-cameraX; y=PlayerY-cameraY-16/-32", "evidence":"0x080066B6..0x0800670E; no -8 X bias"},
        {"fact":"normal_priority", "value":"2", "evidence":"0x080066D6 loads 2 and stores it to OAM priority argument for both normal Player cells"},
        {"fact":"alternate_idle_countdown_reset", "value":"5", "evidence":"0x08008382..0x08008392 overwrites state-8 reset with 5 when Player+0x1E0 != 0"},
        {"fact":"monster_priority", "value":"2", "evidence":"0x080068CA seeds priority 2 before the fifth-sketch monster OAM sequence"},
        {"fact":"bicycle_mode_global", "value":"0x030005F4; riding mode == 2", "evidence":"Player_draw 0x0800661C reads literal 0x08006960 and compares value to 2"},
        {"fact":"bicycle_frame_offsets", "value":"0,4,8,0x50,0x54,0x58", "evidence":"six-word frame-offset table at 0x08019968 consumed by Player_draw riding path"},
        {"fact":"bicycle_riding_composite", "value":"six frames; five 16x16 8bpp sprites; priority 2", "evidence":"Player_draw riding path 0x08006736 onward performs five dynamic OBJ uploads/submits after the mode-2 gate"},
        {"fact":"level9_parked_bicycle_composite", "value":"32x32 at world (504,476); tiles 0x17C,0x17E,0x19C,0x19E; priority 2; hidden while bicycle mode == 2", "evidence":"mode-2 gate at 0x0800661C skips Level-9 branch 0x08006C18; shared lower-row tail 0x08006BAA"},
        {"fact":"level10_parked_bicycle_composite", "value":"32x32 at world (706,884); tiles 0x17C,0x17E,0x19C,0x19E; priority 2; hidden while bicycle mode == 2", "evidence":"mode-2 gate at 0x0800661C skips Level-10 branch 0x08006B6A..0x08006BDA"},
    ]


def extract_new_actor_field_semantics(data: bytes) -> list[dict]:
    """Export guarded semantics for the Graveblood-era common actor fields."""
    # The property parser supplies default=1 specifically for setglobal before
    # storing its result to actor+0x58.
    setglobal_parse = (0x4669, 0x7453, 0x0030, 0x2201, 0xF7FB, 0xFEEC,
                       0x2358, 0x52E8)
    if _unpack_halfwords(data, 0x080045A0, len(setglobal_parse)) != setglobal_parse:
        raise ValueError("setglobal parser default/store sequence drifted")
    global_policy = (0x2358, 0x5EE3, 0x2B00, 0xD102, 0x2201, 0x3331, 0x54E2)
    if _unpack_halfwords(data, 0x080043C8, len(global_policy)) != global_policy:
        raise ValueError("setglobal inherited +0x31 policy drifted")
    leaves_override = (0x2101, 0x2268, 0x64C3, 0x6503, 0x65C3, 0x6603,
                       0x6643, 0x6581, 0x5483, 0x3A69, 0x66C2, 0x6703,
                       0x3331, 0x54C1)
    if _unpack_halfwords(data, 0x08005F2C, len(leaves_override)) != leaves_override:
        raise ValueError("Leaves inherited global-active override drifted")

    return [
        {"property":"level","actor_offset":"+0x56","semantic":"level filter","proven_behavior":"if value != -1 and != current level (0x03000808), virtual method at vtable+0x18 is invoked","confidence":"high"},
        {"property":"setglobal","actor_offset":"+0x58","semantic":"inherited culling-policy control","proven_behavior":"parser default is 1; if value == 0, byte actor+0x31 is set to 1; inherited object manager skips normal spatial/camera-cull path when +0x31 != 0","confidence":"high for machine behavior; original naming polarity unresolved"},
        {"property":"leaves_global_override","actor_offset":"+0x31","semantic":"Leaves_factory forces inherited global-active/culling-bypass byte","proven_behavior":"Leaves_factory 0x08005EE0 constructor tail 0x08005F44 writes actor+0x31 = 1 even though actor+0x58 is initialized to 1","confidence":"high"},
        {"property":"state","actor_offset":"+0x5A","semantic":"NPC behavior/interaction mode enum","proven_behavior":"dispatches states 1,2,3,4 inside 0x0800298C; state 3 is route following","confidence":"high"},
        {"property":"dial","actor_offset":"+0x5C","semantic":"dialogue script index","proven_behavior":"indexes pointer table at 0x0300078C","confidence":"high"},
        {"property":"route","actor_offset":"+0x64","semantic":"NPC route index","proven_behavior":"state 3 indexes route pointer table at 0x03001818 and follows six waypoints","confidence":"high"},
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


def extract_npc_state3_field_usage(data: bytes) -> dict:
    """Prove the recovered state-3 route follower does not consume actor.dial.

    State 3 enters at 0x08002B72.  Its route core loads actor+0x64, its
    waypoint cursor from actor+0xF8 and the serialized/base sprite family from
    actor+0xEC.  The direction-family continuation at 0x08003262 returns to
    the route core or directly to the NPC_update epilogue.  The compiler uses
    an immediate word LDR for actor+0x5C everywhere NPC_update consumes dial
    (encoding 0x6DE8..0x6DEF); no such read occurs in the state-3 blocks.
    """
    entry = (0x4B65, 0x6A59, 0x688B, 0x4A64, 0x12DB, 0x6013, 0x68CB, 0x12DB,
             0x6053, 0x68AB, 0x12DC, 0x6E6B, 0x4A62, 0x009B, 0x589F, 0x23F8,
             0x58EE)
    if _unpack_halfwords(data, 0x08002B72, len(entry)) != entry:
        raise ValueError("NPC state-3 route/waypoint entry drifted")

    base_family = (0x23EC, 0x69AA, 0x58EB)
    if _unpack_halfwords(data, 0x08002BCE, len(base_family)) != base_family:
        raise ValueError("NPC state-3 base-family load drifted")

    state_exit = (0x2350, 0x3A48, 0x52EA, 0x330A, 0x5EEB, 0xE6E8)
    if _unpack_halfwords(data, 0x08002BF8, len(state_exit)) != state_exit:
        raise ValueError("NPC state-3 family/state exit drifted")

    idle_family = (0x2A00, 0xDB28, 0xD008, 0x22F4, 0x2102)
    if _unpack_halfwords(data, 0x08003262, len(idle_family)) != idle_family:
        raise ValueError("NPC state-3 directional-family continuation drifted")

    # actor+0x5C is a word-aligned field and is compiled as LDR [r5,#0x5C],
    # whose possible destination-register encodings are 0x6DE8..0x6DEF.
    # Scan every recovered state-3 block, including its out-of-line direction
    # family continuation.  This is deliberately path-scoped, not a claim
    # that NPC_update as a whole never reads dial (states 1/2 do).
    state3_ranges = (
        (0x08002B72, 0x08002C04),
        (0x08002CC4, 0x08002D96),
        (0x08003262, 0x080032C8),
    )
    dial_reads = []
    for start, end in state3_ranges:
        for addr in range(start, end, 2):
            hw = struct.unpack_from("<H", data, addr - ROM_BASE)[0]
            if 0x6DE8 <= hw <= 0x6DEF:
                dial_reads.append(addr)
    if dial_reads:
        raise ValueError(
            "unexpected actor+0x5C read in state-3 route path: "
            + ", ".join(f"0x{x:08X}" for x in dial_reads)
        )

    return {
        "state": 3,
        "entry": "0x08002B72",
        "route_field": "actor+0x64",
        "waypoint_field": "actor+0xF8",
        "base_sprite_family_field": "actor+0xEC",
        "dialogue_field": "actor+0x5C",
        "dialogue_field_use": "not consulted by recovered state-3 route-follow path",
        "identity_consequence": "state-3 dial metadata cannot prove narrative identity",
        "evidence": "0x08002B72..0x08002D94 + out-of-line 0x08003262..0x080032C6; no LDR [r5,#0x5C] on recovered state-3 path",
        "confidence": "high",
    }


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
            "role_confidence": "unknown",
            "evidence": "no narrative identity assigned without dialogue+metadata proof",
        }
        if index == 0:
            row.update({
                "semantic_role": "passive visible story actor",
                "role_confidence": "high",
                "evidence": "overlay #0 is level=0,state=0,legsColor=56; NPC_update has no special state-0 interaction branch and legsColor!=1 remains drawable",
            })
        elif index == 1:
            row.update({
                "semantic_role": "visible dialogue entity",
                "role_confidence": "high",
                "evidence": "overlay #1 is level=0,state=2,dial=0,legsColor=56; state 2 is the fresh-A dialogue path and legsColor!=1 remains drawable",
            })
        elif index == 2:
            row.update({
                "semantic_role": "visible dialogue entity",
                "role_confidence": "high",
                "evidence": "overlay #2 is level=5,state=2,dial=1,legsColor=16; state 2 is the fresh-A dialogue path and legsColor!=1 remains drawable",
            })
        elif index == 3:
            row.update({
                "semantic_role": "visible dialogue entity",
                "role_confidence": "high",
                "evidence": "overlay #3 is level=0,state=2,dial=1,legsColor=56; state 2 is the fresh-A dialogue path and legsColor!=1 remains drawable",
            })
        elif index == 4:
            row.update({
                "semantic_role": "route-following story actor",
                "role_confidence": "high",
                "evidence": "overlay #4 is state=3,route=0; recovered state-3 route-follow uses actor+0x64/+0xF8/+0xEC and actor+0x5C (dial) is not consulted, so dial=2 cannot prove identity",
            })
        elif index == 5:
            row.update({
                "identity": "Stas",
                "semantic_role": "social-interaction character",
                "identity_confidence": "high",
                "role_confidence": "high",
                "evidence": "overlay #5 is state=1,dial=0; the sole state-1 social bootstrap copies dial to profile selector 0, whose proper social profile name is Stas",
            })
        elif index == 6:
            row.update({
                "identity": "Julia",
                "semantic_role": "social-interaction character",
                "identity_confidence": "high",
                "role_confidence": "high",
                "evidence": "overlay #6 is state=1,dial=1; the sole state-1 social bootstrap copies dial to profile selector 1, whose proper social profile name is Julia",
            })
        elif index == 7:
            row.update({
                "semantic_role": "invisible dialogue hotspot",
                "role_confidence": "high",
                "evidence": "overlay #7 is level=7,state=2,dial=0,legsColor=1; state 2 supplies the fresh-A dialogue interaction while NPC_draw branches to its draw epilogue for legsColor=1",
            })
        elif index == 8:
            row.update({
                "semantic_role": "invisible dialogue hotspot",
                "role_confidence": "high",
                "evidence": "overlay #8 is level=7,state=2,dial=1,legsColor=1; state 2 supplies the fresh-A dialogue interaction while NPC_draw branches to its draw epilogue for legsColor=1",
            })
        elif index == 9:
            row.update({
                "identity": "IQ 54",
                "semantic_role": "story character",
                "identity_confidence": "high",
                "role_confidence": "high",
                "evidence": "overlay #9 is level=10, state=2, dial=2; dial is the proven dialogue-script index and script 2's speaking NPC is IQ 54",
            })
        elif index == 10:
            row.update({
                "identity": "Katya",
                "semantic_role": "story character",
                "identity_confidence": "high",
                "role_confidence": "high",
                "evidence": "overlay #10 has dial=3; script 3 is Katya's sister/bicycle conversation",
            })
        elif 11 <= index <= 15:
            row.update({
                "semantic_role": "collection pickup",
                "role_confidence": "high",
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
PLAYER_COLLISION_STATUS_OFFSET = 0x4A
PLAYER_COLLISION_WIDTH_OFFSET = 0x10
PLAYER_COLLISION_HEIGHT_OFFSET = 0x14
PLAYER_NORMAL_NEGATIVE_ONE_LITERAL = 0x08008580
PLAYER_PDA_SOLVER_GATE_RAM = 0x03000618
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
PLAYER_INTERACTION_RESPONSE_RNG = 0x08010DAC
PLAYER_INTERACTION_RESPONSE_RNG_STATE_PTR_GLOBAL = 0x03001F90
PLAYER_INTERACTION_RESPONSE_RNG_STATE_OFFSET = 0xA8
PLAYER_INTERACTION_RESPONSE_RNG_MULTIPLIER = 0x5851F42D4C957F2D
PLAYER_INTERACTION_RESPONSE_RNG_INCREMENT = 1
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
NPC_STATE2_ENTRY = 0x08002A0C
NPC_STATE4_ENTRY = 0x08002C0C
NPC_STATE2_ACTIVATION = 0x08002D96
NPC_STATE4_ACTIVATION = 0x0800301C
NPC_INTERACTION_SCRATCH = 0x03000574
NPC_INTERACTION_ACTOR_BIAS = -0x1000
NPC_INPUT_CURRENT = 0x030006BC
NPC_INPUT_PREVIOUS = 0x030006C0
NPC_COLLECTION_SELECTOR = 0x03000620
NPC_SPECIAL_TIMER = 0x03000800
NPC_SPECIAL_TIMER_INIT_ROM = INIT_ROM_START + (NPC_SPECIAL_TIMER - INIT_RAM_START)
NPC_SPECIAL_LEGSCOLOR_40 = 40
NPC_SPECIAL_LEGSCOLOR_112 = 112

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


def extract_player_interaction_response_rng(data: bytes) -> dict:
    """Recover the exact RNG used by SUBJECT/CRITICIZE response variants.

    The canonical demo calls the same libc-style generator at 0x08010DAC only
    from the two response-bank entries. The generator advances a 64-bit LCG
    state with the PCG multiplier, adds one, and returns the upper 31 bits.
    SUBJECT reduces that value modulo 4; CRITICIZE reduces it modulo 2.
    """
    subject_call = 0x0800967E
    criticize_call = 0x08009916
    if _thumb1_bl_target(data, subject_call - ROM_BASE) != PLAYER_INTERACTION_RESPONSE_RNG:
        raise ValueError("SUBJECT response RNG call drifted")
    if _thumb1_bl_target(data, criticize_call - ROM_BASE) != PLAYER_INTERACTION_RESPONSE_RNG:
        raise ValueError("CRITICIZE response RNG call drifted")

    subject_mod = (0x2703, 0x17C3, 0x0F9B, 0x18C0, 0x4007, 0x1AFF)
    if _unpack_halfwords(data, 0x08009682, len(subject_mod)) != subject_mod:
        raise ValueError("SUBJECT response RNG modulo-4 path drifted")
    criticize_mod = (0x2701, 0x0FC3, 0x18C0, 0x4007, 0x1AFF)
    if _unpack_halfwords(data, 0x0800991A, len(criticize_mod)) != criticize_mod:
        raise ValueError("CRITICIZE response RNG modulo-2 path drifted")

    generator_prefix = (0xB510, 0xF000, 0xFA9F, 0x30A8, 0x0004, 0x4A08, 0x6841, 0x6800, 0x4B07)
    if _unpack_halfwords(data, PLAYER_INTERACTION_RESPONSE_RNG, len(generator_prefix)) != generator_prefix:
        raise ValueError("interaction response RNG generator drifted")
    lo = struct.unpack_from("<I", data, 0x08010DD8 - ROM_BASE)[0]
    hi = struct.unpack_from("<I", data, 0x08010DDC - ROM_BASE)[0]
    multiplier = (hi << 32) | lo
    if multiplier != PLAYER_INTERACTION_RESPONSE_RNG_MULTIPLIER:
        raise ValueError("interaction response RNG multiplier drifted")

    state_ptr_global_literal = struct.unpack_from("<I", data, 0x08011310 - ROM_BASE)[0]
    if state_ptr_global_literal != PLAYER_INTERACTION_RESPONSE_RNG_STATE_PTR_GLOBAL:
        raise ValueError("interaction response RNG state-pointer global drifted")
    state_ptr = struct.unpack_from("<I", data, init_ram_to_rom_off(state_ptr_global_literal))[0]
    state_addr = state_ptr + PLAYER_INTERACTION_RESPONSE_RNG_STATE_OFFSET
    state_initial = struct.unpack_from("<Q", data, init_ram_to_rom_off(state_addr))[0]
    if state_initial != 1:
        raise ValueError("interaction response RNG initial state drifted")

    all_calls = []
    for off in range(0, min(len(data) - 3, 0x20000), 2):
        if _thumb1_bl_target(data, off) == PLAYER_INTERACTION_RESPONSE_RNG:
            all_calls.append(ROM_BASE + off)
    if all_calls != [subject_call, criticize_call]:
        raise ValueError(f"unexpected interaction response RNG call sites: {all_calls!r}")

    state1 = (state_initial * multiplier + PLAYER_INTERACTION_RESPONSE_RNG_INCREMENT) & 0xFFFFFFFFFFFFFFFF
    first_rand = (state1 >> 32) & 0x7FFFFFFF
    return {
        "generator": f"0x{PLAYER_INTERACTION_RESPONSE_RNG:08X}",
        "subject_call": f"0x{subject_call:08X}",
        "criticize_call": f"0x{criticize_call:08X}",
        "all_generator_calls": "|".join(f"0x{addr:08X}" for addr in all_calls),
        "state_ptr_global": f"0x{state_ptr_global_literal:08X}",
        "state_ptr_initial": f"0x{state_ptr:08X}",
        "state_offset": f"+0x{PLAYER_INTERACTION_RESPONSE_RNG_STATE_OFFSET:X}",
        "state_initial": f"0x{state_initial:016X}",
        "multiplier": f"0x{multiplier:016X}",
        "increment": PLAYER_INTERACTION_RESPONSE_RNG_INCREMENT,
        "output": "(state >> 32) & 0x7FFFFFFF",
        "subject_variant": "rand % 4",
        "criticize_variant": "rand % 2",
        "first_rand": f"0x{first_rand:08X}",
        "first_subject_variant": first_rand % 4,
        "confidence": "high",
    }


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


def extract_player_interaction_leaf_commit_semantics(data: bytes) -> list[dict]:
    """Separate code-reachable TALK leaf commits from inert prototype pages.

    All sixteen leaf records can enter interaction state 2.  The later fresh-A
    gate does *not* treat them equally: after requiring positive interaction
    depth it compares Player+0x1E8 to page base 4.  Only that TALK page falls
    through to the state-3 store.  Page bases 8/12/16 call the common
    Player-update finalizer at 0x08008B5E, whose local epilogue returns from
    Player_update before the state-3 store can execute.  Thus the twelve
    FLIRT/ASSAULT/SHARE leaves are selectable prototype data but inert on A in
    the canonical demo, while TALK/JOKE is the one zero-count leaf that still
    commits and reaches the quadrant-2 shared follow-up.
    """
    gate = (0x22E3, 0x25F4, 0x0092, 0x58A2, 0x006D, 0x5960,
            0x2A00, 0xDC00, 0xE30E, 0x2804, 0xD001)
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE2_FRESH_A_GATE, len(gate)) != gate:
        raise ValueError("interaction leaf fresh-A gate drifted")
    if _thumb1_bl_target(data, 0x08009624 - ROM_BASE) != 0x08008B5E:
        raise ValueError("interaction non-TALK Player-update finalizer target drifted")
    if _unpack_halfwords(data, 0x0800962C, 4) != (0x23F6, 0x2203, 0x005B, 0x50E2):
        raise ValueError("interaction TALK state-3 store drifted")

    finalizer_prefix = (0x2501, 0x4029, 0x000A, 0x0020)
    if _unpack_halfwords(data, 0x08008B5E, len(finalizer_prefix)) != finalizer_prefix:
        raise ValueError("interaction common Player-update finalizer entry drifted")
    finalizer_epilogue = (0xB00F, 0xBC3C, 0x4690, 0x4699, 0x46A2, 0x46AB,
                          0xBCF0, 0xBC01, 0x4700)
    if _unpack_halfwords(data, 0x08008B7E, len(finalizer_epilogue)) != finalizer_epilogue:
        raise ValueError("interaction common Player-update finalizer epilogue drifted")

    action_rows = extract_player_interaction_action_table(data)[4:]
    rows = []
    response_paths = {
        0: "SUBJECT response bank",
        1: "quadrant 1 shared +0x382 follow-up",
        2: "quadrant 2 shared +0x382 follow-up",
        3: "CRITICIZE response bank",
    }
    for action in action_rows:
        index = action["index"]
        page_base = (index // 4) * 4
        quadrant = index - page_base
        talk_commit = page_base == 4
        rows.append({
            "action_index": index,
            "action_label": action["label"],
            "page_base": page_base,
            "quadrant": quadrant,
            "topic_count": action["field_28"],
            "fresh_a_gate": f"0x{PLAYER_INTERACTION_STATE2_FRESH_A_GATE:08X}",
            "fresh_a_outcome": (
                "commit to interaction state 3" if talk_commit
                else "exit Player_update; remain in state 2"
            ),
            "post_countdown_path": (
                response_paths[quadrant] if talk_commit
                else "unreachable from canonical state-2 fresh-A gate"
            ),
            "runtime_class": (
                "TALK leaf with code-proven commit" if talk_commit
                else "prototype/inert leaf in canonical demo"
            ),
            "b_return": "state 0/root page + SFX7",
            "evidence": (
                "page_base==4 falls through to 0x0800962C state-3 store"
                if talk_commit else
                "page_base!=4 calls 0x08008B5E common finalizer, whose 0x08008B7E..0x08008B8E epilogue returns from Player_update before state-3 store"
            ),
            "confidence": "high",
        })
    return rows



def extract_player_interaction_followup_flag_references(data: bytes) -> list[dict]:
    """Inventory every recovered PC-relative reference to Player+0x382.

    The shared response flag has eight literal references in the canonical ROM.
    Five are reads, two are zeroing stores (constructor and accepted follow-up),
    and exactly one writes 1: the quadrant-1/2 dispatcher at 0x08009214.
    This proves the recovered Ask-about/JOKE follow-up has one shared runtime
    arm point and no leaf discriminator at that setter.
    """
    refs = _thumb_literal_refs_to(data, PLAYER_INTERACTION_SECONDARY_FLAG_OFFSET)
    expected = [
        0x0800637A, 0x080083CE, 0x0800843A, 0x0800852E,
        0x08008598, 0x080087AC, 0x08008B50, 0x08009214,
    ]
    if refs != expected:
        raise ValueError(
            "Player+0x382 literal-reference inventory drifted: "
            + str([f"0x{x:08X}" for x in refs])
        )

    next_halfword = {
        0x0800637A: 0x54E5,
        0x080083CE: 0x5CA2,
        0x0800843A: 0x5CA2,
        0x0800852E: 0x5CE3,
        0x08008598: 0x54A3,
        0x080087AC: 0x5CA2,
        0x08008B50: 0x5CE3,
        0x08009214: 0x54E2,
    }
    for addr, expected_hw in next_halfword.items():
        actual = struct.unpack_from("<H", data, addr + 2 - ROM_BASE)[0]
        if actual != expected_hw:
            raise ValueError(f"Player+0x382 access drifted at 0x{addr:08X}")
    if struct.unpack_from("<H", data, 0x08006220 - ROM_BASE)[0] != 0x2500:
        raise ValueError("Player constructor zero-register setup drifted")
    if struct.unpack_from("<H", data, 0x08008596 - ROM_BASE)[0] != 0x2300:
        raise ValueError("Player+0x382 follow-up clear value drifted")
    if struct.unpack_from("<H", data, 0x08009212 - ROM_BASE)[0] != 0x2201:
        raise ValueError("Player+0x382 response-arm value drifted")

    semantics = {
        0x0800637A: ("clear 0", "Player constructor initialization"),
        0x080083CE: ("read", "normal Player-update interaction guard"),
        0x0800843A: ("read", "normal Player-update input guard"),
        0x0800852E: ("read", "shared fresh-A follow-up consumer"),
        0x08008598: ("clear 0", "accepted shared follow-up teardown"),
        0x080087AC: ("read", "Player-update interaction guard"),
        0x08008B50: ("read", "Player-update finalizer/solver guard"),
        0x08009214: ("set 1", "quadrant 1/2 response dispatcher"),
    }
    rows = []
    for addr in refs:
        access, source = semantics[addr]
        rows.append({
            "address": f"0x{addr:08X}",
            "field": "Player+0x382",
            "access": access,
            "source": source,
            "leaf_discriminator": (
                "none; dispatch key is quadrant only"
                if addr == 0x08009214 else "not applicable"
            ),
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
        "exact_leaf_effect": "no distinct Ask-about/JOKE effect recovered; the sole runtime setter is the shared quadrant-1/2 dispatcher",
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
    """Prove delayed SUBJECT/CRITICIZE relationship-score semantics."""
    subject_path = (
        0x23F8, 0x005B, 0x58E3, 0x3306, 0x009B, 0x585B,
        0x3B02, 0x694A, 0x4694, 0x005B, 0x4463, 0x614B,
    )
    if _unpack_halfwords(data, PLAYER_INTERACTION_PROFILE_SCORE_UPDATE, len(subject_path)) != subject_path:
        raise ValueError("interaction SUBJECT profile+0x14 score update drifted")
    criticize_setup = (0x23F8, 0x005B, 0x58E3, 0x3306, 0x009B, 0x585A, 0x2302, 0x1A9B)
    if _unpack_halfwords(data, 0x080098A8, len(criticize_setup)) != criticize_setup:
        raise ValueError("interaction CRITICIZE inverse-score setup drifted")
    # E62B branches from the inverse setup back into the SUBJECT shared write
    # tail beginning at 0x08009512.  Keep the two address ranges explicit.
    branch_hw = struct.unpack_from("<H", data, 0x080098B8 - ROM_BASE)[0]
    if _thumb_unconditional_b_target(0x080098B8, branch_hw) != 0x08009512:
        raise ValueError("interaction CRITICIZE shared score-write tail branch drifted")

    countdown_path = (0x4B4E, 0x5CE3, 0x2B00, 0xD08D, 0x22E1, 0x21F2,
                      0x0092, 0x58A3, 0x0049, 0x5866, 0x2B00, 0xDC00,
                      0xE21C, 0x3B01, 0x50A3)
    if _unpack_halfwords(data, 0x08008CA4, len(countdown_path)) != countdown_path:
        raise ValueError("interaction 150-update post-teardown countdown drifted")
    teardown_seed = (0xF001, 0xF8D9, 0x23E1, 0x2296, 0x009B, 0x50E2)
    if _unpack_halfwords(data, PLAYER_INTERACTION_STATE3_TEARDOWN, len(teardown_seed)) != teardown_seed:
        raise ValueError("interaction state-3 countdown seed drifted")

    if struct.unpack_from("<I", data, 0x0800981C - ROM_BASE)[0] != PLAYER_INTERACTION_PROFILE_TABLE_RAM:
        raise ValueError("interaction score-update profile-table literal drifted")
    follower = extract_player_interaction_profile_target_step(data)
    real_profiles = extract_player_interaction_social_profile_topics(data)
    initial_by_name = {row["name"]: row["profile_field_14_initial"] for row in real_profiles}
    return {
        "profile_field": "+0x14",
        "update_site": "0x08009504..0x0800951A",
        "subject_update_site": "0x08009504..0x0800951A",
        "criticize_setup_site": "0x080098A8..0x080098B8",
        "criticize_shared_tail": "0x08009512..0x0800951A",
        "topic_class_source": "profile + 4*(Player+0x1F0 + 6)",
        "update_formula": "profile+0x14 += 2 * (topic_class - 2)",
        "topic_class_deltas": "0:-4|1:-2|2:0|3:+2|4:+4",
        "criticize_update_formula": "profile+0x14 += 2 * (2 - topic_class)",
        "criticize_topic_class_deltas": "0:+4|1:+2|2:0|3:-2|4:-4",
        "timing": "after state-3 teardown and 150-update countdown expires",
        "countdown_offset": "+0x384",
        "countdown_seed": 150,
        "player_follower_offset": follower["player_offset"],
        "player_follower_target": "10 * profile+0x14",
        "direct_player_mirror_site": "0x080090F8",
        "direct_player_mirror_formula": "Player+0x39C = 10 * profile+0x14 before score delta",
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


def extract_player_level_idle_selector(data: bytes) -> list[dict]:
    rows = []
    base = LEVEL_RECORD_SOURCE_ROM - ROM_BASE
    for level in range(LEVEL_RECORD_COUNT):
        record_off = base + level * LEVEL_RECORD_SIZE
        selector = struct.unpack_from("<I", data, record_off + 0x3C)[0]
        rows.append({
            "level": level,
            "record_rom_addr": f"0x{ROM_BASE + record_off:08X}",
            "record_field": "+0x3C",
            "idle_selector": selector,
            "load_addr": f"0x{PLAYER_IDLE_SELECTOR_LOAD_ADDR:08X}",
            "player_field": "+0x1E0",
            "store_addr": f"0x{PLAYER_IDLE_SELECTOR_STORE_ADDR:08X}",
            "evidence": "Gameplay scene activation reads current LevelRecord+0x3C and stores it to Player+0x1E0",
            "confidence": "high",
        })
    return rows


def extract_player_motion_collision_contract(data: bytes) -> list[dict]:
    """Export ROM-guarded Player movement/collision facts used by clean-room runtime."""
    ctor_dims = (0x2380, 0x015B, 0x6123, 0x6163)
    if _unpack_halfwords(data, 0x080063A0, len(ctor_dims)) != ctor_dims:
        raise ValueError("Player 16x16 fixed8 collision dimensions drifted")

    if struct.unpack_from("<i", data, PLAYER_NORMAL_NEGATIVE_ONE_LITERAL - ROM_BASE)[0] != -0x100:
        raise ValueError("normal Player -0x100 motion literal drifted")
    right_write = (0x2280, 0x0052, 0x61A2)
    down_write = (0x2280, 0x0052, 0x61E2)
    if _unpack_halfwords(data, 0x08009B6C, len(right_write)) != right_write:
        raise ValueError("normal RIGHT +0x100 fixed8 write drifted")
    if _unpack_halfwords(data, 0x08009B88, len(down_write)) != down_write:
        raise ValueError("normal DOWN +0x100 fixed8 write drifted")

    right_status = (0x2300, 0x2407, 0x6183, 0x334A, 0x52C4)
    left_status = (0x2300, 0x240B, 0x6183, 0x334A)
    down_status = (0x2200, 0x214A, 0x2631, 0x61C2, 0x5A42, 0x4332, 0x5242)
    up_status = (0x244A, 0x2200, 0x2651, 0x61C2, 0x5B02, 0x4332, 0x5302)
    if _unpack_halfwords(data, 0x080046C2, len(right_status)) != right_status:
        raise ValueError("right horizontal block/status path drifted")
    if _unpack_halfwords(data, 0x08004A3A, len(left_status)) != left_status:
        raise ValueError("left horizontal block/status path drifted")
    if _unpack_halfwords(data, 0x08004772, len(down_status)) != down_status:
        raise ValueError("downward center block/status path drifted")
    if _unpack_halfwords(data, 0x08004908, len(up_status)) != up_status:
        raise ValueError("upward center block/status path drifted")

    slide_down = (0x3601, 0x36FF, 0x60C6)
    slide_up = (0x3E01, 0x681B, 0x3EFF, 0x60C6)
    diagonal_bypass = (0x2A00, 0xD000, 0xE09D)
    if _unpack_halfwords(data, 0x08004826, len(slide_down)) != slide_down:
        raise ValueError("horizontal top-corner +1px slide drifted")
    if _unpack_halfwords(data, 0x08004716, len(slide_up)) != slide_up:
        raise ValueError("horizontal bottom-corner -1px slide drifted")
    if _unpack_halfwords(data, 0x08004820, len(diagonal_bypass)) != diagonal_bypass:
        raise ValueError("diagonal corner bypass path drifted")

    if struct.unpack_from("<I", data, 0x080049A0 - ROM_BASE)[0] != PLAYER_PDA_SOLVER_GATE_RAM:
        raise ValueError("Player solver PDA gate literal drifted")

    return [
        {"fact":"position_format", "value":"24.8 fixed-point at Player+0x08/+0x0C", "evidence":"0x0800468E/0x0800469A + position commits", "confidence":"high"},
        {"fact":"requested_motion", "value":"signed fixed8 at Player+0x18/+0x1C", "evidence":"0x0800467E/0x08004682; permitted components add directly to position", "confidence":"high"},
        {"fact":"collision_dimensions", "value":"0x1000 x 0x1000 fixed8 = 16 x 16 pixels", "evidence":"Player constructor 0x080063A0..0x080063A6", "confidence":"high"},
        {"fact":"collision_grid", "value":"8-pixel cells via arithmetic >> 11", "evidence":"0x08004698/0x080046A8 and mirrored probes", "confidence":"high"},
        {"fact":"normal_left", "value":"-0x100 fixed8", "evidence":"KEY_LEFT path 0x080083F0..0x080083FA loads literal -256 from 0x08008580", "confidence":"high"},
        {"fact":"normal_right", "value":"+0x100 fixed8", "evidence":"KEY_RIGHT long-branch block 0x08009B64..0x08009B7C", "confidence":"high"},
        {"fact":"normal_up", "value":"-0x100 fixed8", "evidence":"KEY_UP path 0x08008414..0x0800841E uses same -256 literal", "confidence":"high"},
        {"fact":"normal_down", "value":"+0x100 fixed8", "evidence":"KEY_DOWN long-branch block 0x08009B80..0x08009B98", "confidence":"high"},
        {"fact":"horizontal_special_block", "value":"tile 14; status 7 right / 11 left", "evidence":"0x080047E8..0x08004812 + 0x080046C2..CA; mirror 0x08004A12..0x08004A42", "confidence":"high"},
        {"fact":"vertical_center_block", "value":"status 0x31 down / 0x51 up", "evidence":"0x08004772..0x0800477E and 0x08004908..0x08004914", "confidence":"high"},
        {"fact":"axis_corner_slide", "value":"exact 0x100 fixed8 = 1 pixel correction", "evidence":"0x08004826..0x0800482A, 0x08004716..0x0800471C, mirrored X corrections", "confidence":"high"},
        {"fact":"diagonal_corner_rule", "value":"simultaneous X+Y carries X into Y resolution; no axis-only slide", "evidence":"0x08004820..0x08004962 branch routing", "confidence":"high"},
        {"fact":"pda_solver_gate", "value":"0x03000618; PDA return-pending only, not normal gameplay physics", "evidence":"solver literal 0x080049A0 + PDA invalid-page/return reference inventory", "confidence":"high"},
    ]


def extract_npc_fixed_point_runtime(data: bytes) -> dict:
    """Prove the NPC position scale, route-cell scale and shared mover timer.

    Common actor property parsing converts parsed integer X/Y values with an
    LSL #8 before storing object+0x08/+0x0C, so world positions are 24.8 fixed.
    Interaction geometry separately ASRs fixed positions by 11, making one
    interaction-grid cell 8 pixels.  Route waypoints are likewise compared in
    that 8-pixel-cell coordinate system.  The legsColor==112 pre-dispatch uses
    the 32-bit global at 0x03000800, whose initialized image value is 15.
    """
    x_parse = (0x0030, 0x2264, 0xF7FB, 0xFFB6, 0x0200, 0x60A8)
    y_parse = (0x0030, 0x2264, 0xF7FB, 0xFFA4, 0x0200, 0x60E8)
    if _unpack_halfwords(data, 0x08004410, len(x_parse)) != x_parse:
        raise ValueError("actor X fixed8 property parse drifted")
    if _unpack_halfwords(data, 0x08004434, len(y_parse)) != y_parse:
        raise ValueError("actor Y fixed8 property parse drifted")

    # NPC route-follow begins by ASR #11 when converting fixed positions to the
    # same 8-pixel grid used by route-point coordinates.
    route_grid = (0x688B, 0x4A64, 0x12DB, 0x6013, 0x68CB, 0x12DB, 0x6053)
    if _unpack_halfwords(data, 0x08002B76, len(route_grid)) != route_grid:
        raise ValueError("NPC route 8-pixel grid conversion drifted")

    special_gate = (0x2B70, 0xD10C, 0x2452, 0x5F2B, 0x2B00, 0xD000, 0xE18A)
    if _unpack_halfwords(data, 0x080029AE, len(special_gate)) != special_gate:
        raise ValueError("legsColor 112 special pre-state gate drifted")
    timer_literal = struct.unpack_from("<I", data, 0x08002D04 - ROM_BASE)[0]
    if timer_literal + 4 != NPC_SPECIAL_TIMER:
        raise ValueError(f"NPC special timer base drifted: {timer_literal:#x}")
    timer_initial = struct.unpack_from("<I", data, NPC_SPECIAL_TIMER_INIT_ROM)[0]
    if timer_initial != 15:
        raise ValueError(f"NPC special timer initial value drifted: {timer_initial}")

    return {
        "position_fraction_bits": 8,
        "one_pixel_fixed": "0x100",
        "position_fields": "actor+0x08|actor+0x0C",
        "property_parse_sites": "0x08004414|0x08004438",
        "route_waypoint_units": "8-pixel cells",
        "route_target_shift": 11,
        "interaction_grid_shift": 11,
        "interaction_grid_cell_pixels": 8,
        "special_timer_address": f"0x{NPC_SPECIAL_TIMER:08X}",
        "special_timer_storage": "32-bit",
        "special_timer_initial": timer_initial,
        "special_timer_reload": 5,
        "confidence": "high",
    }


def _serialized_int(props: dict[str, str], key: str, default: int = 0) -> int:
    raw = props.get(key, "")
    return default if raw == "" else int(float(raw))


def extract_npc_special_movers(data: bytes) -> list[dict]:
    """Export every serialized NPC that enters the two pre-state mover paths."""
    fixed = extract_npc_fixed_point_runtime(data)
    if fixed["position_fraction_bits"] != 8:
        raise AssertionError("special-mover export requires fixed8 actor positions")

    if _unpack_halfwords(data, 0x08002C04, 3) != (0x68AB, 0x3B96, 0x60AB):
        raise ValueError("legsColor 40 X-motion path drifted")
    latched_motion = (0x234C, 0x5EEA, 0x0093, 0x189A, 0x0113, 0x1A9B,
                      0x68AA, 0x4694, 0x00DB, 0x3B2D, 0x3BFF, 0x4463,
                      0x60AB, 0x68EB, 0x3BFA, 0x60EB)
    if _unpack_halfwords(data, 0x08002CD2, len(latched_motion)) != latched_motion:
        raise ValueError("legsColor 112 latched movement path drifted")
    activation = (0x2201, 0x2150, 0x2009, 0x61BB, 0xF7FE, 0xFC6C, 0x4643, 0x532B)
    if _unpack_halfwords(data, 0x08003290, len(activation)) != activation:
        raise ValueError("legsColor 112 SFX9/latch activation path drifted")

    rows = []
    for off, props in _scan_serialized_actors(data):
        if props.get("spawnType") != "npc":
            continue
        legs = _serialized_int(props, "legsColor")
        if legs not in (NPC_SPECIAL_LEGSCOLOR_40, NPC_SPECIAL_LEGSCOLOR_112):
            continue
        row = {
            "actor_rom_addr": f"0x{ROM_BASE + off:08X}",
            "legs_color": legs,
            "x_serialized": props.get("x", ""),
            "y_serialized": props.get("y", ""),
            "x_truncated_px": _serialized_int(props, "x"),
            "y_truncated_px": _serialized_int(props, "y"),
            "turn": _serialized_int(props, "turn"),
            "port_to": _serialized_int(props, "portTo"),
            "timer_address": f"0x{NPC_SPECIAL_TIMER:08X}" if legs == 112 else "",
            "timer_initial": 15 if legs == 112 else "",
            "timer_reload": 5 if legs == 112 else "",
            "proximity_radius_pixels": 32 if legs == 112 else "",
            "activation_sfx": 9 if legs == 112 else "",
            "movement": ("x -= 150 fixed8 units each update" if legs == 40
                         else "x += 600*turn - 300; y -= 250"),
            "confidence": "high",
        }
        rows.append(row)

    if len([r for r in rows if r["legs_color"] == 40]) != 1:
        raise ValueError("canonical legsColor 40 mover count drifted")
    if len([r for r in rows if r["legs_color"] == 112]) != 22:
        raise ValueError("canonical legsColor 112 mover count drifted")
    if [r["actor_rom_addr"] for r in rows if r["legs_color"] == 40] != ["0x0841E218"]:
        raise ValueError("canonical legsColor 40 mover identity drifted")
    return rows


def extract_actor_system_inventory(data: bytes) -> list[dict]:
    """Classify every serialized actor family plus transient leaf particles."""
    counts = {"npc": 0, "grass": 0, "fgtile": 0, "leaves": 0, "player": 0}
    for _, props in _scan_serialized_actors(data):
        key = props.get("spawnType") or props.get("type") or ""
        if key in counts:
            counts[key] += 1
    expected = {"npc": 105, "grass": 94, "fgtile": 55, "leaves": 3, "player": 10}
    if counts != expected:
        raise ValueError(f"canonical actor-family inventory drifted: {counts}")

    # The story-overlay loader has sixteen canonical NPC descriptors; the
    # remaining serialized NPCs are normal physical level actors.
    story_overlay_count = len(extract_story_entity_identities())
    if story_overlay_count != 16:
        raise ValueError(f"story-overlay actor count drifted: {story_overlay_count}")
    physical_npc_count = counts["npc"] - story_overlay_count

    common = {"confidence": "high"}
    return [
        {**common, "family": "NPC", "serialized_total": counts["npc"],
         "physical_count": physical_npc_count, "story_overlay_count": story_overlay_count,
         "factory": "0x08003A60", "constructor": "0x08003998", "update": "0x0800298C",
         "draw": "0x0800274C", "vtable": "0x08018B00", "runtime_role": "interactive/moving NPC"},
        {**common, "family": "Grass", "serialized_total": counts["grass"],
         "physical_count": counts["grass"], "story_overlay_count": 0,
         "factory": "0x08002914", "constructor": "", "update": "0x08002480",
         "draw": "0x08002684", "vtable": "0x08018AD8", "runtime_role": "visible static foreground actor"},
        {**common, "family": "Fgtile", "serialized_total": counts["fgtile"],
         "physical_count": counts["fgtile"], "story_overlay_count": 0,
         "factory": "0x08003AEC", "constructor": "", "update": "0x08003B98",
         "draw": "0x08003AE8", "vtable": "0x08018E4C", "runtime_role": "invisible foreground interaction/controller"},
        {**common, "family": "Leaves", "serialized_total": counts["leaves"],
         "physical_count": counts["leaves"], "story_overlay_count": 0,
         "factory": "0x08005EE0", "constructor": "", "update": "0x08005F80",
         "draw": "0x08005EDC", "vtable": "", "runtime_role": "invisible leaf-particle emitter"},
        {**common, "family": "Player", "serialized_total": counts["player"],
         "physical_count": counts["player"], "story_overlay_count": 0,
         "factory": "0x08006418", "constructor": "0x0800621C", "update": "0x080081B0",
         "draw": "0x080065FC", "vtable": "0x08019694", "runtime_role": "player actor"},
        {**common, "family": "LeafParticle", "serialized_total": 0,
         "physical_count": 0, "story_overlay_count": 0,
         "factory": "", "constructor": "0x0800B2BC", "update": "0x0800AB60",
         "draw": "0x0800AC1C", "vtable": "", "runtime_role": "transient Leaves-emitted particle"},
    ]


def extract_npc_interaction_geometry(data: bytes) -> list[dict]:
    """Recover the state 1/2/4 proximity rectangles and fresh-A gates.

    NPC coordinates use 24.8 fixed-point storage.  The interaction code shifts
    them right by 11, converting directly to 8-pixel grid cells.  Each branch
    subtracts 0x1000 (two grid cells in fixed8 space) from actor X/Y
    before scanning its rectangle against Player X/Y.  The rectangles differ:
    state 1 is fixed 5x5, state 2 is 4x4 only when actor+0x4E == 1 and 5x5
    otherwise, and state 4 is fixed 4x4.  All three activation paths require
    input bit 0 to be set in the current input word and clear in the previous
    input word, i.e. a fresh A press.
    """
    # State dispatch and actor-origin bias are shared by all three branches.
    dispatch_sig = (0x2B04, 0xD100, 0xE10C, 0x2B02, 0xD00A, 0x2B01, 0xD067)
    if _unpack_halfwords(data, 0x080029EC, len(dispatch_sig)) != dispatch_sig:
        raise ValueError("NPC interaction state dispatch drifted")
    bias = struct.unpack_from("<i", data, 0x08002D10 - ROM_BASE)[0]
    if bias != NPC_INTERACTION_ACTOR_BIAS:
        raise ValueError(f"NPC interaction actor-origin bias drifted: {bias:#x}")

    # State 2: actor+0x4E is converted to a 0/1 delta and +4, producing
    # a 4x4 rectangle when the field equals 1 and 5x5 otherwise.
    state2_size_sig = (0x234E, 0x4CB9, 0x46A4, 0x5EE9, 0x3901, 0x1E4B, 0x4199)
    if _unpack_halfwords(data, 0x08002A26, len(state2_size_sig)) != state2_size_sig:
        raise ValueError("NPC state-2 geometry selector drifted")
    state2_loop_sig = (0x2300, 0xE002, 0x3301, 0x4299, 0xD07A, 0x4294, 0xD1FA,
                       0x19DE, 0x42B0, 0xD1F7, 0x2601, 0x46B2, 0x9608, 0x3201,
                       0x4295, 0xD1EF)
    if _unpack_halfwords(data, 0x08002A6E, len(state2_loop_sig)) != state2_loop_sig:
        raise ValueError("NPC state-2 proximity loop drifted")

    # State 1: both dimensions are explicitly bounded at 5 iterations.
    state1_loop_sig = (0x1D57, 0x2300, 0xE002, 0x3301, 0x2B05, 0xD007,
                       0x4291, 0xD1FA, 0x18E0, 0x4286, 0xD1F7, 0x2001,
                       0x4682, 0x4681, 0x3201, 0x42BA, 0xD1EF)
    if _unpack_halfwords(data, 0x08002B14, len(state1_loop_sig)) != state1_loop_sig:
        raise ValueError("NPC state-1 5x5 proximity loop drifted")

    # State 4: both dimensions are explicitly bounded at 4 iterations.
    state4_loop_sig = (0x1D17, 0x2300, 0xE002, 0x3301, 0x2B04, 0xD007,
                       0x428A, 0xD1FA, 0x1918, 0x42B0, 0xD1F7, 0x2001,
                       0x4681, 0x4680, 0x3201, 0x4297, 0xD1EF)
    if _unpack_halfwords(data, 0x08002C66, len(state4_loop_sig)) != state4_loop_sig:
        raise ValueError("NPC state-4 4x4 proximity loop drifted")

    # State 2 and state 1 share input globals 0x030006BC/0x030006C0.
    if struct.unpack_from("<I", data, 0x08002FF8 - ROM_BASE)[0] != NPC_INPUT_CURRENT:
        raise ValueError("NPC current-input global drifted")
    if struct.unpack_from("<I", data, 0x08002FFC - ROM_BASE)[0] != NPC_INPUT_PREVIOUS:
        raise ValueError("NPC previous-input global drifted")
    state2_fresh_a = (0x4A94, 0x6812, 0x421A, 0xD100, 0xE0F3,
                      0x4A93, 0x6812, 0x421A, 0xD000, 0xE0EE)
    if _unpack_halfwords(data, 0x08002DA4, len(state2_fresh_a)) != state2_fresh_a:
        raise ValueError("NPC state-2 fresh-A gate drifted")
    if struct.unpack_from("<I", data, 0x08003018 - ROM_BASE)[0] != PLAYER_INTERACTION_ACTIVE_RAM:
        raise ValueError("NPC state-1 interaction-active global drifted")
    state1_fresh_a = (0x4B0F, 0x681B, 0x4213, 0xD100, 0xE51A,
                      0x4B0D, 0x681B, 0x4013, 0xD000, 0xE515)
    if _unpack_halfwords(data, 0x08002FBA, len(state1_fresh_a)) != state1_fresh_a:
        raise ValueError("NPC state-1 fresh-A gate drifted")

    # State 4 repeats the same bit-0 rising-edge test using another literal pool.
    if struct.unpack_from("<I", data, 0x08003368 - ROM_BASE)[0] != NPC_INPUT_CURRENT:
        raise ValueError("NPC state-4 current-input global drifted")
    if struct.unpack_from("<I", data, 0x0800336C - ROM_BASE)[0] != NPC_INPUT_PREVIOUS:
        raise ValueError("NPC state-4 previous-input global drifted")
    state4_fresh_a = (0x4ACF, 0x6812, 0x421A, 0xD100, 0xE0EA,
                      0x4ACD, 0x6812, 0x4013, 0xD000, 0xE0E5)
    if _unpack_halfwords(data, 0x0800302A, len(state4_fresh_a)) != state4_fresh_a:
        raise ValueError("NPC state-4 fresh-A gate drifted")
    if struct.unpack_from("<I", data, 0x08002D18 - ROM_BASE)[0] != NPC_COLLECTION_SELECTOR:
        raise ValueError("state-4 collection selector global drifted")

    common = {
        "activation": "fresh A press",
        "input_rule": "current A set; previous A clear",
        "grid_shift": "11",
        "actor_origin_bias_fixed": "-0x1000",
        "actor_origin_bias_cells": "-2,-2",
        "scratch_state": f"0x{NPC_INTERACTION_SCRATCH:08X}",
        "confidence": "high",
    }
    return [
        {
            "state": 1,
            "dispatch_address": f"0x{NPC_STATE1_ENTRY:08X}",
            "working_name": "social_interaction",
            "proximity_cells": "5x5",
            "geometry_condition": "fixed",
            "activation_effect": (
                "actor+0x5C -> Player+0x388; actor+0x08 -> Player+0x390; "
                "actor+0x0C -> Player+0x394; requires 0x03000610==0; "
                "actor+0x4C=1; 0x03000610=1"
            ),
            "evidence": "0x08002B14..0x08002B34 geometry; 0x08002FBA..0x08002FF2 fresh-A/bootstrap",
            **common,
        },
        {
            "state": 2,
            "dispatch_address": f"0x{NPC_STATE2_ENTRY:08X}",
            "working_name": "dialogue_interaction",
            "proximity_cells": "4x4 if actor+0x4E == 1; otherwise 5x5",
            "geometry_condition": "actor+0x4E (legsColor export)",
            "activation_effect": (
                "fresh A enters dialogue path; when actor+0x4E != 1, actor X/Y are copied "
                "to Player+0x390/+0x394 and 0x080080A4 queues Player alignment"
            ),
            "evidence": "0x08002A26..0x08002A8C geometry; 0x08002D96..0x08002DD8 fresh-A/alignment",
            **common,
        },
        {
            "state": 4,
            "dispatch_address": f"0x{NPC_STATE4_ENTRY:08X}",
            "working_name": "collection_interaction",
            "proximity_cells": "4x4",
            "geometry_condition": "fixed",
            "activation_effect": (
                "fresh A dispatches 0x03000620 collection selector through "
                "4;-1;-1;5;6;0 progression"
            ),
            "evidence": "0x08002C66..0x08002C86 geometry; 0x0800301C..0x0800305E fresh-A/selector dispatch",
            **common,
        },
    ]


def extract_npc_state_modes(data: bytes) -> list[dict]:
    """Return the recovered NPC state dispatch with promoted interaction names."""
    geometry = {row["state"]: row for row in extract_npc_interaction_geometry(data)}
    return [
        {"state":0,"dispatch_address":"default/return","working_name":"default",
         "proven_behavior":"no special state branch in 0x0800298C dispatch","confidence":"high"},
        {"state":1,"dispatch_address":"0x08002ACA","working_name":"social_interaction",
         "proven_behavior":"5x5 proximity; fresh-A social interaction bootstrap and Player/NPC alignment anchors",
         "confidence":geometry[1]["confidence"]},
        {"state":2,"dispatch_address":"0x08002A0C","working_name":"dialogue_interaction",
         "proven_behavior":"4x4 when actor+0x4E == 1, otherwise 5x5; fresh-A dialogue path with conditional Player alignment",
         "confidence":geometry[2]["confidence"]},
        {"state":3,"dispatch_address":"0x08002B72","working_name":"route_follow",
         "proven_behavior":"resolves prior queued fixed8 request through the shared collision solver before queuing the next +/-0x100 route step; uses six (x,y) waypoints via actor.route (+0x64)/index (+0xF8); direction selects base/base+8/base+16 sprite families with 8/6/6 frames","confidence":"high"},
        {"state":4,"dispatch_address":"0x08002C0C","working_name":"collection_interaction",
         "proven_behavior":"fixed 4x4 proximity; fresh-A collection selector dispatch via 0x03000620","confidence":geometry[4]["confidence"]},
    ]


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
    state 2.  State-2 fresh-A handling is page-gated: TALK page base 4 can
    commit through state 3, while FLIRT/ASSAULT/SHARE page bases 8/12/16 take
    the Player-update exit path and remain in state 2.  Fresh B returns to the
    root page/state 0.  State 3 is a teardown path that resets the interaction
    base/state and clears 0x03000610.
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
    if _unpack_halfwords(data, 0x08009CC6, 2) != (0x2201, 0x2007):
        raise ValueError("interaction state-2 B return SFX7 arguments drifted")
    if _thumb1_bl_target(data, 0x08009CCA - ROM_BASE) != 0x08001B74:
        raise ValueError("interaction state-2 B return SFX7 call drifted")
    if _unpack_halfwords(data, 0x08008C94, 2) != (0x50E5, 0x51A5):
        raise ValueError("interaction state-2 B caller page/state reset drifted")

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
         "proven_behavior": "initializes the secondary leaf-action interaction state and stores state 2 regardless of +0x28 topic count; later fresh-A handling is page-gated (TALK page base 4 can commit, FLIRT/ASSAULT/SHARE page bases 8/12/16 remain state 2)"},
        {**common, "transition": "secondary_b_return", "handler": "0x08009CB6", "from_state": 2, "to_state": 0,
         "input": "fresh B", "choice": "", "condition": "state == 2",
         "proven_behavior": "runs UI cleanup, plays SFX7 volume 0x50, clears Player+0x1E8 page base and Player+0x1EC state to 0"},
        {**common, "transition": "secondary_talk_a_commit", "handler": "0x0800960E", "from_state": 2, "to_state": 3,
         "input": "fresh A", "choice": "selected TALK leaf", "condition": "depth > 0 and page_base == 4",
         "proven_behavior": "only TALK page base 4 stores state 3; page bases 8/12/16 take the Player_update exit path without changing interaction state"},
        {**common, "transition": "teardown", "handler": "0x0800963E", "from_state": 3, "to_state": 0,
         "input": "state dispatch", "choice": "", "condition": "state == 3",
         "proven_behavior": "cleans UI, seeds Player+0x384=150, clears page/scratch/state, writes 0x03000610=0, restores scene graphics, and marks Player+0x381=1 before the delayed response dispatcher"},
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


def extract_ending_vram_effect_level10_sources(data: bytes) -> list[dict]:
    """Resolve the opcode -5 argument-0 copy sources for canonical Level 10.

    All five state-4 sketch overlays are level-gated to Level 10, whose active
    graphics descriptor is the initialized-IWRAM record at 0x03000E80.
    0x08004FE0 reads descriptor +0x00 and +0x14, then adds its recovered
    source biases before issuing the two byte-counted copies.
    """
    desc_ram = 0x03000E80
    desc_off = init_ram_to_rom_off(desc_ram)
    bg_tiles_source = struct.unpack_from('<I', data, desc_off + 0x00)[0]
    obj_tiles_source = struct.unpack_from('<I', data, desc_off + 0x14)[0]
    if bg_tiles_source != 0x085E2B60 or obj_tiles_source != 0x08310654:
        raise ValueError(
            f"Level 10 ending descriptor drifted: bg=0x{bg_tiles_source:08X} obj=0x{obj_tiles_source:08X}"
        )

    first_source = bg_tiles_source + 0x0005E801
    second_source = obj_tiles_source + 0x0005E800
    first_bytes = 1500 * 64
    second_bytes = 250 * 64

    sound_table_off = 0x65662C
    sfx13_source, _ = struct.unpack_from('<II', data, sound_table_off + 13 * 8)
    first_end = first_source + first_bytes
    sfx13_overlap = max(0, first_end - max(first_source, sfx13_source)) if sfx13_source < first_end else 0

    common = {
        "level": 10,
        "descriptor_iwram": f"0x{desc_ram:08X}",
        "confidence": "high",
    }
    return [
        {**common, "copy": 1, "descriptor_field": "+0x00 bg_tiles_source",
         "descriptor_value": f"0x{bg_tiles_source:08X}", "source_bias": "0x0005E801",
         "effective_source_argument_0": f"0x{first_source:08X}",
         "argument_0_bytes": first_bytes, "argument_0_end_exclusive": f"0x{first_end:08X}",
         "sfx13_overlap_bytes": sfx13_overlap},
        {**common, "copy": 2, "descriptor_field": "+0x14 obj_tiles_source",
         "descriptor_value": f"0x{obj_tiles_source:08X}", "source_bias": "0x0005E800",
         "effective_source_argument_0": f"0x{second_source:08X}",
         "argument_0_bytes": second_bytes, "argument_0_end_exclusive": f"0x{second_source + second_bytes:08X}",
         "sfx13_overlap_bytes": 0},
    ]


def extract_ending_vram_effect_argument0_payloads(data: bytes) -> list[dict]:
    """Export the exact statically reachable argument-0 payloads and VRAM bounds."""
    import hashlib

    sources = extract_ending_vram_effect_level10_sources(data)
    destinations = {1: 0x06000000, 2: 0x06010000}
    vram_limit = 0x06018000
    rows = []
    for source_row in sources:
        copy = source_row['copy']
        source = int(source_row['effective_source_argument_0'], 16)
        length = source_row['argument_0_bytes']
        destination = destinations[copy]
        start = source - ROM_BASE
        payload = data[start:start + length]
        if len(payload) != length:
            raise ValueError(f'ending argument-0 copy {copy} payload truncated')
        end = destination + length
        rows.append({
            'copy': copy,
            'reachable_argument': 0,
            'source': f'0x{source:08X}',
            'destination': f'0x{destination:08X}',
            'byte_length': length,
            'destination_end_exclusive': f'0x{end:08X}',
            'vram_limit_exclusive': f'0x{vram_limit:08X}',
            'within_vram': 'yes' if end <= vram_limit else 'no',
            'sha256': hashlib.sha256(payload).hexdigest(),
            'confidence': 'high',
        })
    if any(row['within_vram'] != 'yes' for row in rows):
        raise ValueError('statically reachable ending argument-0 payload exceeds VRAM')
    return rows


def extract_ending_effect_argument_writes(data: bytes) -> list[dict]:
    """Inventory direct Player-update writes to the ending-effect argument state.

    Player_update loads the shared global base 0x0300062C into r5.  The
    argument field is +0x48 (0x03000674).  Within the recovered Player-update
    code region the only direct STR [r5,#0x48] instructions are the guarded
    +20 update and the <=1000 reset.  This deliberately does not claim that
    indirect/external runtime writes are impossible.
    """
    if struct.unpack_from('<I', data, 0x0800854C - ROM_BASE)[0] != 0x0300062C:
        raise ValueError('ending writer global-base literal drifted')
    if _unpack_halfwords(data, 0x080081BE, 1) != (0x4DE3,):
        raise ValueError('ending writer Player_update base-load drifted')

    scan_start = 0x080081B0
    scan_end = 0x0800A000
    stores = []
    for addr in range(scan_start, scan_end, 2):
        hw = struct.unpack_from('<H', data, addr - ROM_BASE)[0]
        # Thumb-1 STR Rd,[Rb,#imm5*4], specialized to Rb=r5 and +0x48.
        if (hw & 0xF800) == 0x6000:
            imm5 = (hw >> 6) & 0x1F
            rb = (hw >> 3) & 7
            if rb == 5 and imm5 * 4 == 0x48:
                stores.append(addr)
    if stores != [0x080081D0, 0x080088AA]:
        raise ValueError(f'ending argument direct-writer inventory drifted: {[hex(v) for v in stores]}')

    if _unpack_halfwords(data, 0x080081C8, 5) != (0x4293, 0xDC00, 0xE36C, 0x3314, 0x64AB):
        raise ValueError('ending argument >1000 writer path drifted')
    if _unpack_halfwords(data, 0x080088A8, 2) != (0x2300, 0x64AB):
        raise ValueError('ending argument <=1000 reset writer drifted')

    common = {
        'global_base': '0x0300062C',
        'field_offset': '+0x48',
        'field_address': '0x03000674',
        'confidence': 'high',
    }
    return [
        {**common, 'store_address': '0x080081D0',
         'write': 'argument_state += 20',
         'guard': 'previous argument_state > 1000'},
        {**common, 'store_address': '0x080088AA',
         'write': 'argument_state = 0',
         'guard': 'previous argument_state <= 1000'},
    ]


def _literal_occurrence_count(data: bytes, value: int) -> int:
    needle = struct.pack('<I', value)
    count = 0
    start = 0
    while True:
        off = data.find(needle, start)
        if off < 0:
            return count
        count += 1
        start = off + 1


def _thumb_literal_immediate_word_store_aliases(data: bytes, target: int) -> tuple[int, list[int]]:
    """Audit positive Thumb-1 STR aliases rooted in nearby IWRAM literals.

    A Thumb-1 immediate word store can address at most +124 bytes from its
    base register.  Scan every aligned IWRAM literal in that window which is
    actually loaded by executable code, then follow that loaded register
    through the containing linear function body and record stores whose
    immediate resolves exactly to ``target``.  The recovered Graveblood code
    keeps these shared-state bases in the register loaded by the literal; the
    exact results below are guarded by their callers/tests.
    """
    roots: list[tuple[int, int, int]] = []
    for base in range(target - 124, target + 1, 4):
        for addr in _thumb_literal_refs_to(data, base):
            hw = struct.unpack_from('<H', data, addr - ROM_BASE)[0]
            roots.append((addr, (hw >> 8) & 7, base))

    stores: set[int] = set()
    rom_end = ROM_BASE + len(data)
    for root, reg, base in roots:
        wanted = target - base
        for addr in range(root + 2, min(root + 0x1200, rom_end), 2):
            hw = struct.unpack_from('<H', data, addr - ROM_BASE)[0]
            if hw & 0xF800 == 0x6000:
                imm = ((hw >> 6) & 0x1F) * 4
                rb = (hw >> 3) & 7
                if rb == reg and imm == wanted:
                    stores.add(addr)
            if hw == 0x4770 or hw & 0xFF00 == 0xBD00:
                break
    return len(roots), sorted(stores)



def extract_player_select_counter_closure(data: bytes) -> dict:
    """Close the reachable standalone-SELECT Player+0x1BC counter path.

    The public-demo Player constructor seeds +0x1BC to 11. Fresh SELECT tests
    that field against 3 and transfers to the decrement block at 0x080090B8.
    That block decrements the field, then BLs back into 0x0800851C. This BL is
    an internal long transfer inside Player_update, not a conventional helper
    that returns to the sequential bytes at 0x080090C4: the common continuation
    has no BX LR / POP {...,PC} return and exits through Player_update's saved-LR
    epilogue at 0x08008B7E..0x08008B8E. The state-12 block at 0x080090C4 has a
    distinct incoming BL from 0x08008708.

    Within the recovered Player constructor/update/draw code, the only exact
    +0x1BC offset-construction reads are the two SELECT guards, and the only
    exact decrement store is 0x080090BE. The original narrative/debug purpose
    of the counter is unknown, so the clean-room runtime deliberately does not
    invent a visible SELECT action.
    """
    constructor = (0x23DA, 0x220B, 0x0020, 0x4661, 0x005B, 0x50E5,
                   0x3304, 0x50E5, 0x3304, 0x50E2)
    if _unpack_halfwords(data, 0x080062E4, len(constructor)) != constructor:
        raise ValueError('Player+0x1BC constructor seed drifted')

    primary = (0x2204, 0x421A, 0xD00A, 0x4B1F, 0x681B, 0x4213,
               0xD106, 0x23DE, 0x005B, 0x58E3, 0x2B03, 0xDD01,
               0xF000, 0xFDCE)
    if _unpack_halfwords(data, 0x08008500, len(primary)) != primary:
        raise ValueError('primary fresh-SELECT gate drifted')
    if struct.unpack_from('<I', data, 0x0800856C - ROM_BASE)[0] != 0x030006BC:
        raise ValueError('current-key literal drifted')
    if struct.unpack_from('<I', data, 0x08008584 - ROM_BASE)[0] != 0x030006C0:
        raise ValueError('previous-key literal drifted')
    if _thumb1_bl_target(data, 0x08008518 - ROM_BASE) != 0x080090B8:
        raise ValueError('primary SELECT transfer target drifted')

    secondary = (0x2204, 0x421A, 0xD002, 0x420A, 0xD100, 0xE17A)
    if _unpack_halfwords(data, 0x08008DAA, len(secondary)) != secondary:
        raise ValueError('secondary fresh-SELECT gate drifted')

    guard_and_decrement = (0x23DE, 0x005B, 0x58E3, 0x2B03, 0xDC00, 0xE67E,
                           0x22DE, 0x3B01, 0x0052, 0x50A3, 0xF7FF, 0xFA2C)
    if _unpack_halfwords(data, 0x080090AC, len(guard_and_decrement)) != guard_and_decrement:
        raise ValueError('SELECT counter guard/decrement block drifted')
    if _thumb1_bl_target(data, 0x080090C0 - ROM_BASE) != 0x0800851C:
        raise ValueError('post-decrement internal transfer drifted')

    state12 = (0x230C, 0x310B, 0x60B3, 0xF7FF, 0xFB24)
    if _unpack_halfwords(data, 0x080090C4, len(state12)) != state12:
        raise ValueError('state-12 control block drifted')
    if _thumb1_bl_target(data, 0x08008708 - ROM_BASE) != 0x080090C4:
        raise ValueError('state-12 incoming transfer drifted')

    # Exact +0x1BC read construction: movs r3,#0xDE; lsls r3,#1; ldr r3,[r4,r3].
    read_pattern = struct.pack('<HHH', 0x23DE, 0x005B, 0x58E3)
    read_sites = []
    start = 0x0800621C - ROM_BASE
    end = 0x0800A000 - ROM_BASE
    pos = start
    while True:
        off = data.find(read_pattern, pos, end)
        if off < 0:
            break
        read_sites.append(ROM_BASE + off)
        pos = off + 2
    if read_sites != [0x0800850E, 0x080090AC]:
        raise ValueError(f'Player+0x1BC exact read inventory drifted: {[hex(v) for v in read_sites]}')

    decrement_pattern = struct.pack('<HHHH', 0x22DE, 0x3B01, 0x0052, 0x50A3)
    decrement_sites = []
    pos = start
    while True:
        off = data.find(decrement_pattern, pos, end)
        if off < 0:
            break
        decrement_sites.append(ROM_BASE + off + 6)  # address of STR
        pos = off + 2
    if decrement_sites != [0x080090BE]:
        raise ValueError(f'Player+0x1BC decrement inventory drifted: {[hex(v) for v in decrement_sites]}')

    # A conventional subroutine return from 0x851C would make 0x90C4 a real
    # fallthrough. None exists before the Player_update epilogue; that epilogue
    # restores the original caller address from the stack instead of using the
    # BL link register created at 0x90C0.
    common = data[0x0800851C - ROM_BASE:0x08008B90 - ROM_BASE]
    if struct.pack('<H', 0x4770) in common:
        raise ValueError('unexpected BX LR in SELECT common continuation')
    if any((hw & 0xFF00) == 0xBD00 for hw in struct.unpack('<' + 'H' * (len(common)//2), common)):
        raise ValueError('unexpected POP {...,PC} in SELECT common continuation')
    epilogue = (0xB00F, 0xBC3C, 0x4690, 0x4699, 0x46A2, 0x46AB,
                0xBCF0, 0xBC01, 0x4700)
    if _unpack_halfwords(data, 0x08008B7E, len(epilogue)) != epilogue:
        raise ValueError('Player_update saved-LR epilogue drifted')

    return {
        'field': 'Player+0x1BC',
        'constructor_seed': '0x080062F6',
        'constructor_initial_value': 11,
        'lower_bound': 3,
        'accepted_fresh_select_presses_per_spawn': 8,
        'input_gate': 'fresh SELECT (current bit 0x0004 set; previous clear)',
        'keys_current': '0x030006BC',
        'keys_previous': '0x030006C0',
        'primary_gate_transfer': '0x08008518',
        'secondary_gate': '0x08008DAA',
        'guard_read_sites': ';'.join(f'0x{v:08X}' for v in read_sites),
        'decrement_store': '0x080090BE',
        'post_decrement_transfer': '0x080090C0 -> 0x0800851C',
        'common_continuation_return': 'Player_update saved-LR epilogue 0x08008B7E..0x08008B8E',
        'state12_block_entry': '0x08008708 -> 0x080090C4',
        'select_reaches_state12_block': 'no',
        'gameplay_consumer': 'none code-proven beyond the counter guard/decrement itself',
        'observable_public_demo_effect': 'counter changes 11 down to 3; no separate render/audio/motion consumer proven',
        'original_purpose': 'unknown / likely leftover internal or debug state; do not rename as a gameplay mechanic',
        'reconstruction_policy': 'standalone SELECT remains inert in the clean-room runtime',
        'confidence': 'high static closure within recovered Player constructor/draw/update paths',
    }


def extract_player_shared_mode_reachability(data: bytes) -> dict:
    """Close the public-demo lifetime of shared Player state 0x030005F4.

    The ROM contains implemented draw/update branches for values 1 and 2, but
    reachability is a separate question.  Startup zeroes this IWRAM word.  A
    conservative nearby-literal Thumb-1 store scan is then resolved against
    the actual literal reloads at every candidate site.  The only true writes
    are the Level-9 treetype-20 mount (2), scene entry normalization (preserve
    2, otherwise 0), and the Level-10 scripted clear (0).  Therefore value 1
    is dormant in the public demo from a normal boot even though code for it
    remains present.
    """
    target = 0x030005F4

    exact_refs = _thumb_literal_refs_to(data, target)
    expected_refs = [0x080041CC, 0x08006618, 0x08008362, 0x08008452, 0x08008A5C, 0x080093A8]
    if exact_refs != expected_refs:
        raise ValueError(f'Player shared-mode exact literal refs drifted: {[hex(v) for v in exact_refs]}')

    roots, candidates = _thumb_literal_immediate_word_store_aliases(data, target)
    expected_candidates = [
        0x080041CE, 0x080041EC, 0x08004230, 0x0800424C, 0x08004276,
        0x0800428A, 0x0800429E, 0x080042D0, 0x080042DC, 0x080042E8,
        0x08005A7C, 0x08008986, 0x08009046, 0x08009094, 0x080093AA,
    ]
    if roots != 65 or candidates != expected_candidates:
        raise ValueError(
            f'Player shared-mode conservative alias scan drifted: roots={roots}, '
            f'stores={[hex(v) for v in candidates]}'
        )

    # Nine Fgtile false positives are later r3 reloads of scratch state
    # 0x03000598 after the real 0x030005F4 store.  The conservative helper is
    # intentionally register-name based and therefore reports them until this
    # second-stage literal resolution is applied.
    if struct.unpack_from('<I', data, 0x08004318 - ROM_BASE)[0] != 0x03000598:
        raise ValueError('Fgtile scratch-state literal drifted')
    fgtile_false_loads = [
        0x080041EA, 0x0800422E, 0x0800424A, 0x08004274, 0x08004288,
        0x0800429C, 0x080042CE, 0x080042DA, 0x080042E6,
    ]
    for addr in fgtile_false_loads:
        hw = struct.unpack_from('<H', data, addr - ROM_BASE)[0]
        if hw & 0xF800 != 0x4800:
            raise ValueError(f'expected Thumb literal load at 0x{addr:08X}')
        literal_addr = ((addr + 4) & ~3) + ((hw & 0xFF) << 2)
        value = struct.unpack_from('<I', data, literal_addr - ROM_BASE)[0]
        if value != 0x03000598:
            raise ValueError(f'false Fgtile alias at 0x{addr+2:08X} no longer resolves to 0x03000598')

    # Three late Player-update false positives similarly reload unrelated
    # globals before the reported store sites.
    if struct.unpack_from('<I', data, 0x08008BA4 - ROM_BASE)[0] != 0x03000614:
        raise ValueError('Player selector 0x03000614 literal #1 drifted')
    if struct.unpack_from('<I', data, 0x080090EC - ROM_BASE)[0] != 0x03000614:
        raise ValueError('Player selector 0x03000614 literal #2 drifted')
    if struct.unpack_from('<I', data, 0x080090F4 - ROM_BASE)[0] != 0x030005DC:
        raise ValueError('Player selector 0x030005DC literal drifted')
    if _unpack_halfwords(data, 0x0800897C, 6) != (0x4989, 0x680A, 0x2A00, 0xDD0B, 0x3A01, 0x600A):
        raise ValueError('0x03000614 decrement path drifted')
    if _unpack_halfwords(data, 0x0800903A, 7) != (0x492C, 0x680A, 0x2A02, 0xDD00, 0xE493, 0x3201, 0x600A):
        raise ValueError('0x03000614 increment path drifted')
    if _unpack_halfwords(data, 0x08009080, 11)[-2:] != (0x3301, 0x600B):
        raise ValueError('0x030005DC increment path drifted')

    # True writer #1: Level-9 treetype-20 always commits mode 2.
    level9 = extract_level9_treetype20_action(data)
    if level9['shared_bicycle_mode_value'] != 2:
        raise ValueError('treetype-20 no longer proves shared mode 2')

    # True writer #2: gameplay/scene entry preserves exactly 2 and clears any
    # other value.  r5 is the scene-manager base 0x030005BC; +0x38 = F4.
    if struct.unpack_from('<I', data, 0x08005BB0 - ROM_BASE)[0] != 0x030005BC:
        raise ValueError('scene-manager base literal drifted')
    scene_policy = (0x6BA9, 0x2902, 0xD001, 0x2100, 0x63A9)
    if _unpack_halfwords(data, 0x08005A74, len(scene_policy)) != scene_policy:
        raise ValueError('scene-entry shared-mode normalization drifted')

    # True writer #3: Level-10 mode 5->6 clears the word.
    if struct.unpack_from('<I', data, 0x08009480 - ROM_BASE)[0] != target:
        raise ValueError('Level-10 shared-mode clear literal drifted')
    if _unpack_halfwords(data, 0x080093A2, 5) != (0x2700, 0x4835, 0x60E0, 0x4835, 0x6007):
        raise ValueError('Level-10 shared-mode clear sequence drifted')

    # Dormant mode-1 consumers remain real code: draw staging, extra OAM, and
    # a fresh-A Player_update branch.  Proving their existence prevents
    # conflating "unreachable" with "not implemented in the original ROM".
    if _unpack_halfwords(data, 0x0800672E, 4) != (0x2E01, 0xD072, 0x2E02, 0xD1BC):
        raise ValueError('Player_draw mode-1 staging gate drifted')
    if _unpack_halfwords(data, 0x08006712, 4) != (0x4643, 0x681B, 0x2B01, 0xD100):
        raise ValueError('Player_draw mode-1 extra-OAM gate drifted')
    if _unpack_halfwords(data, 0x08008A5C, 4) != (0x4855, 0x6800, 0x2801, 0xD101):
        raise ValueError('Player_update mode-1 fresh-A branch drifted')

    boot = extract_ending_effect_boot_lifetime(data)
    zero_start = int(boot['zero_range_start'], 16)
    zero_end = int(boot['zero_range_end_exclusive'], 16)
    if not (zero_start <= target < zero_end):
        raise ValueError('Player shared-mode global no longer lies in boot-zeroed IWRAM')

    true_sites = [0x080041CE, 0x08005A7C, 0x080093AA]
    false_sites = [v for v in candidates if v not in true_sites]
    return {
        'shared_mode_global': '0x030005F4',
        'boot_initial_value': 0,
        'exact_literal_refs': ';'.join(f'0x{v:08X}' for v in exact_refs),
        'candidate_literal_load_roots': roots,
        'conservative_candidate_store_sites': ';'.join(f'0x{v:08X}' for v in candidates),
        'resolved_true_write_sites': ';'.join(f'0x{v:08X}' for v in true_sites),
        'resolved_false_alias_sites': ';'.join(f'0x{v:08X}' for v in false_sites),
        'mode2_writer': '0x080041CE',
        'scene_entry_normalizer': '0x08005A7C',
        'scene_entry_policy': 'preserve 2; otherwise write 0',
        'level10_clear_writer': '0x080093AA',
        'reachable_values_from_normal_boot': '0;2',
        'mode1_reachable_from_normal_boot': 'no',
        'mode2_reachable_from_normal_boot': 'yes',
        'dormant_mode1_code_sites': '0x08006818;0x08006A66;0x08008A5C',
        'closure_result': 'no code-proven writer of 1; mode 1 is dormant from normal public-demo boot',
        'scope_caveat': ('closure covers startup zeroing, exact literals, positive immediate Thumb word-store aliases, '
                         'and resolved candidate reloads in the public-demo executable; it does not model arbitrary '
                         'external memory corruption'),
        'confidence': 'high static closure for public-demo executable code',
    }


def extract_ending_effect_alias_write_closure(data: bytes) -> list[dict]:
    """Close nearby-literal aliases for the ending argument and event flag.

    The scan covers every code-referenced aligned IWRAM literal from
    ``target-124`` through ``target`` because +124 is the largest positive
    offset expressible by Thumb-1 ``STR Rd,[Rb,#imm]``.  This catches aliases
    such as loading 0x03000610 and storing +0x64 instead of loading the shared
    0x0300062C base and storing +0x48.
    """
    argument = 0x03000674
    flag = 0x03000678
    arg_roots, arg_stores = _thumb_literal_immediate_word_store_aliases(data, argument)
    flag_roots, flag_stores = _thumb_literal_immediate_word_store_aliases(data, flag)

    if arg_roots != 56 or arg_stores != [0x080081D0, 0x080088AA]:
        raise ValueError(
            f'ending argument alias closure drifted: roots={arg_roots}, '
            f'stores={[hex(v) for v in arg_stores]}'
        )
    if flag_roots != 57 or flag_stores != [0x0800380A]:
        raise ValueError(
            f'ending event-flag alias closure drifted: roots={flag_roots}, '
            f'stores={[hex(v) for v in flag_stores]}'
        )

    return [
        {
            'target_name': 'ending_effect_argument_state',
            'target_address': '0x03000674',
            'exact_literal_occurrences': _literal_occurrence_count(data, argument),
            'candidate_literal_load_roots': arg_roots,
            'write_sites': ';'.join(f'0x{v:08X}' for v in arg_stores),
            'non_player_update_write_sites': 'none',
            'largest_proven_written_value_from_zero_seed': 0,
            'closure_result': 'no seed above 1000 found',
            'confidence': 'high',
        },
        {
            'target_name': 'ending_event_active_flag',
            'target_address': '0x03000678',
            'exact_literal_occurrences': _literal_occurrence_count(data, flag),
            'candidate_literal_load_roots': flag_roots,
            'write_sites': ';'.join(f'0x{v:08X}' for v in flag_stores),
            'non_final_handler_write_sites': 'none',
            'closure_result': 'only final-sketch handler can set flag after boot',
            'confidence': 'high',
        },
    ]


def extract_ending_effect_boot_lifetime(data: bytes) -> dict:
    """Prove boot initialization and absence of a scene-level ending reset."""
    zero_helper = 0x08000186
    calls = []
    for off in range(0, min(len(data) - 2, 0x18000), 2):
        if _thumb1_bl_target(data, off) == zero_helper:
            calls.append(ROM_BASE + off)
    if calls != [0x0800012C, 0x08000136, 0x08000140]:
        raise ValueError(f'boot zero-helper call inventory drifted: {[hex(v) for v in calls]}')

    # 0x08000130: r0=0x03000000; 0x08000132: r1=0x03000788;
    # 0x08000134 subtracts them to form the byte count before the zero helper.
    if _unpack_halfwords(data, 0x08000130, 4) != (0x4823, 0x4924, 0x1A09, 0xF000):
        raise ValueError('boot IWRAM zero setup drifted')
    if struct.unpack_from('<I', data, 0x080001C0 - ROM_BASE)[0] != 0x03000000:
        raise ValueError('boot IWRAM zero start literal drifted')
    if struct.unpack_from('<I', data, 0x080001C4 - ROM_BASE)[0] != 0x03000788:
        raise ValueError('boot IWRAM zero end literal drifted')
    if _thumb1_bl_target(data, 0x08000136 - ROM_BASE) != zero_helper:
        raise ValueError('boot IWRAM zero call target drifted')

    # Initialized IWRAM data is copied starting exactly at the byte following
    # the zeroed BSS range, so it cannot overwrite either ending field.
    if struct.unpack_from('<I', data, 0x080001D4 - ROM_BASE)[0] != 0x03000788:
        raise ValueError('initialized IWRAM copy start drifted')

    argument = 0x03000674
    flag = 0x03000678
    if not (0x03000000 <= argument < 0x03000788 and 0x03000000 <= flag < 0x03000788):
        raise ValueError('ending globals no longer lie inside boot-zeroed IWRAM')

    return {
        'zero_helper': '0x08000186',
        'iwram_zero_call': '0x08000136',
        'zero_range_start': '0x03000000',
        'zero_range_end_exclusive': '0x03000788',
        'argument_state_initial_value': 0,
        'event_flag_initial_value': 0,
        'initialized_iwram_copy_start': '0x03000788',
        'zero_helper_call_sites': ';'.join(f'0x{v:08X}' for v in calls),
        'scene_reset_calls_to_zero_helper': 'none',
        'scene_transition_resets_ending_state': 'no',
        'confidence': 'high',
    }


def extract_ending_effect_static_reachability(data: bytes) -> dict:
    """Close the public-demo ending argument state from boot through runtime.

    Startup zeroes the field.  The exhaustive direct/immediate-alias store
    inventory leaves only the two Player_update stores: values <=1000 are
    forced back to zero, while the +20 writer is itself guarded by a value
    already above 1000.  Therefore zero is an invariant of executable code
    from a normal boot and the high branch has no code-proven entry seed.
    """
    rows = extract_ending_effect_argument_writes(data)
    aliases = {row['target_address']: row for row in extract_ending_effect_alias_write_closure(data)}
    boot = extract_ending_effect_boot_lifetime(data)
    argument_alias = aliases['0x03000674']
    flag_alias = aliases['0x03000678']

    if argument_alias['write_sites'] != ';'.join(row['store_address'] for row in rows):
        raise ValueError('ending static closure writer inventories disagree')
    return {
        'argument_state': '0x03000674',
        'boot_initial_argument': boot['argument_state_initial_value'],
        'direct_player_update_writers': ';'.join(row['store_address'] for row in rows),
        'immediate_alias_write_closure': 'no additional writers',
        'code_proven_seed_above_1000': 'none',
        'reachable_argument_values_from_boot': '0',
        'high_branch_reachable_from_boot': 'no',
        'repeat_effect_reachable_with_normal_zero_seed': 'argument 0 only',
        'event_flag_boot_value': boot['event_flag_initial_value'],
        'event_flag_setter': flag_alias['write_sites'],
        'event_flag_reset_after_boot': 'none',
        'scene_transition_resets_state': boot['scene_transition_resets_ending_state'],
        'scope_caveat': ('closure covers public-demo executable code, startup initialization, exact literals, '
                         'and positive immediate Thumb store aliases; it does not model arbitrary '
                         'hardware/external corruption'),
        'confidence': 'high static closure for public-demo executable code',
    }


def extract_ending_event_flag_runtime(data: bytes) -> dict:
    """Inventory direct accesses that keep the final-effect event flag latched.

    The final state-4 handler writes 1 through the only exact 0x03000678
    literal in the ROM.  Player_update reaches the same field through the
    shared 0x0300062C base at +0x4C and only reads it at the two argument
    branches; there is no direct STR [r5,#0x4C] in the recovered Player-update
    region.  This establishes same-scene latching while normal Player_update
    continues, but deliberately does not rule out scene reset or indirect /
    external writes elsewhere at runtime.
    """
    flag = 0x03000678
    literal = 0x08003984
    if struct.unpack_from('<I', data, literal - ROM_BASE)[0] != flag:
        raise ValueError('ending event-flag exact literal drifted')

    needle = struct.pack('<I', flag)
    occurrences = []
    start = 0
    while True:
        off = data.find(needle, start)
        if off < 0:
            break
        occurrences.append(ROM_BASE + off)
        start = off + 1
    if occurrences != [literal]:
        raise ValueError(f'ending event-flag literal inventory drifted: {[hex(v) for v in occurrences]}')

    # Setter: movs r2,#1; ldr r3,[pc,...0x08003984]; str r2,[r3].
    if _unpack_halfwords(data, 0x08003806, 3) != (0x2201, 0x4B5E, 0x601A):
        raise ValueError('ending event-flag setter drifted')

    if struct.unpack_from('<I', data, 0x0800854C - ROM_BASE)[0] != 0x0300062C:
        raise ValueError('ending event-flag Player_update base literal drifted')

    reads = []
    stores = []
    for addr in range(0x080081B0, 0x0800A000, 2):
        hw = struct.unpack_from('<H', data, addr - ROM_BASE)[0]
        imm5 = (hw >> 6) & 0x1F
        rb = (hw >> 3) & 7
        # Thumb-1 word LDR/STR with base r5 and offset +0x4C.
        if rb == 5 and imm5 * 4 == 0x4C:
            if (hw & 0xF800) == 0x6800:
                reads.append(addr)
            elif (hw & 0xF800) == 0x6000:
                stores.append(addr)
    if reads != [0x080081D2, 0x080088AC]:
        raise ValueError(f'ending event-flag Player_update read inventory drifted: {[hex(v) for v in reads]}')
    if stores:
        raise ValueError(f'ending event-flag Player_update store inventory drifted: {[hex(v) for v in stores]}')

    aliases = {row['target_address']: row for row in extract_ending_effect_alias_write_closure(data)}
    boot = extract_ending_effect_boot_lifetime(data)
    flag_alias = aliases['0x03000678']
    return {
        'event_flag': '0x03000678',
        'setter': '0x0800380A',
        'setter_value': 1,
        'exact_address_literal': '0x08003984',
        'exact_address_literal_occurrences': len(occurrences),
        'player_update_reads': ';'.join(f'0x{addr:08X}' for addr in reads),
        'player_update_direct_stores': 'none',
        'same_scene_behavior': 'latched while normal Player_update continues',
        'all_static_write_sites': flag_alias['write_sites'],
        'reset_after_boot': 'none',
        'scene_transition_behavior': ('latched across gameplay scene transitions; '
                                      'reset only by reboot/startup zero-fill'),
        'scope_caveat': ('closure covers public-demo executable code, startup initialization, exact literals, '
                         'and positive immediate Thumb store aliases; it does not model arbitrary '
                         'hardware/external corruption'),
        'confidence': 'high static closure for public-demo executable code',
    }


def extract_ending_vram_effect_runtime(data: bytes) -> list[dict]:
    """Export the exact static gate feeding the ending VRAM effect.

    This intentionally does not call 0x03000674 a progress counter: the public
    binary resets values <=1000 to zero and only increments values already
    above 1000.  Startup seeds the field to zero and the executable alias-write
    closure finds no writer capable of seeding the high branch.
    """
    final_entry = (0x2000, 0xF001, 0xFBF2, 0x2201, 0x2150, 0x200D)
    if _unpack_halfwords(data, 0x080037F6, len(final_entry)) != final_entry:
        raise ValueError("ending final-opcode entry drifted")
    if struct.unpack_from('<I', data, 0x08003984 - ROM_BASE)[0] != 0x03000678:
        raise ValueError("ending event-flag literal drifted")

    gate = (0x22FA, 0xB5E0, 0x4DE3, 0x6CAB, 0xB08F, 0x0004,
            0x0092, 0x4293, 0xDC00, 0xE36C, 0x3314, 0x64AB,
            0x6CEB, 0x2B01, 0xD100, 0xE36C)
    if _unpack_halfwords(data, 0x080081BA, len(gate)) != gate:
        raise ValueError("ending Player_update threshold gate drifted")
    if struct.unpack_from('<I', data, 0x0800854C - ROM_BASE)[0] != 0x0300062C:
        raise ValueError("ending Player_update global-base literal drifted")

    low_path = (0x2300, 0x64AB, 0x6CEB, 0x2B01, 0xD000, 0xE492,
                0x6CA8, 0xF7FC, 0xFB93)
    if _unpack_halfwords(data, 0x080088A8, len(low_path)) != low_path:
        raise ValueError("ending Player_update reset/repeat path drifted")

    closure = extract_ending_effect_static_reachability(data)
    if closure['high_branch_reachable_from_boot'] != 'no':
        raise ValueError('ending runtime reachability closure no longer excludes high branch')

    common = {
        "effect_function": "0x08004FE0",
        "argument_state": "0x03000674",
        "event_flag": "0x03000678",
        "event_flag_required": 1,
        "confidence": "high",
    }
    return [
        {**common, "phase": "final_opcode_entry", "handler": "0x080037F6",
         "condition": "state-4 opcode -5", "argument_update": "none",
         "effect_call": "0x080037F8", "argument_before_call": 0,
         "reachable_from_normal_boot": "yes", "unreachable_reason": ""},
        {**common, "phase": "player_update_le_1000", "handler": "0x080088A8",
         "condition": "argument_state <= 1000", "argument_update": "argument_state = 0",
         "effect_call": "0x080088B6 when event_flag == 1", "argument_before_call": "0",
         "reachable_from_normal_boot": "yes", "unreachable_reason": ""},
        {**common, "phase": "player_update_gt_1000", "handler": "0x080081CE",
         "condition": "argument_state > 1000", "argument_update": "argument_state += 20",
         "effect_call": "0x080088B6 when event_flag == 1", "argument_before_call": "updated argument_state",
         "reachable_from_normal_boot": "no",
         "unreachable_reason": "no executable writer can seed argument_state above 1000 from boot value 0"},
    ]


def extract_level9_treetype20_action(data: bytes) -> dict:
    """Return the code-proven special behavior of the Level-9 treetype-20 tile.

    The physical actor at 0x08386FF0 stores ``portTo=524``, but Fgtile_update
    checks actor+0x54 (treetype) before the generic portTo/request_scene block.
    treetype 20 enters 0x0800417C.  The overlap solver compares a 2x2 grid
    around the Player against the Fgtile; on fresh A, every accepted contact
    orientation writes 0x00020000 (512 pixels) to Player+0x394, invokes the
    vertical-target helper, then stores value 2 to shared ride-state global
    0x030005F4.  Therefore 524 is preserved actor metadata, not a scene
    destination: this branch is the bicycle mount action.
    """
    treetype_dispatch = (0x2354, 0x5EE0, 0x2302, 0x275A, 0x4699, 0x2814, 0xD100, 0xE25D)
    if _unpack_halfwords(data, 0x08003CB0, len(treetype_dispatch)) != treetype_dispatch:
        raise ValueError("Fgtile treetype-20 dispatch drifted")

    target_write = (0x23E5, 0x2280, 0x009B, 0x0292, 0x50CA, 0x4640, 0xF003, 0xFF6C)
    if _unpack_halfwords(data, 0x080041BC, len(target_write)) != target_write:
        raise ValueError("Level-9 treetype-20 vertical-target branch drifted")

    bicycle_mode_store = (0x4B55, 0x601D)
    if _unpack_halfwords(data, 0x080041CC, len(bicycle_mode_store)) != bicycle_mode_store:
        raise ValueError("Level-9 treetype-20 bicycle-mode store drifted")
    if struct.unpack_from('<I', data, 0x08004324 - ROM_BASE)[0] != 0x030005F4:
        raise ValueError("Level-9 treetype-20 bicycle-mode global literal drifted")

    generic_handoff = (0x2352, 0x2200, 0x5EE1, 0x4832, 0x230A)
    if _unpack_halfwords(data, 0x08004258, len(generic_handoff)) != generic_handoff:
        raise ValueError("generic Fgtile scene handoff drifted")

    return {
        "level": 9,
        "actor_rom_addr": "0x08386FF0",
        "treetype": 20,
        "stored_portTo": 524,
        "generic_scene_handoff_reached": "no",
        "special_entry": "0x0800417C",
        "trigger": "fresh A while overlapping treetype-20 Fgtile",
        "player_target_y_fixed": "0x00020000",
        "player_target_y_px": 512,
        "player_target_y_offset": "+0x394",
        "vertical_target_helper": "0x080080A4",
        "contact_cell_x": "((PlayerX_fixed-0x800)>>11) in {62,63}",
        "contact_cell_y": "((PlayerY_fixed-0x1800)>>11) in {55,56}",
        "integer_player_anchor_bounds": "x=504..519,y=464..479",
        "shared_bicycle_mode_global": "0x030005F4",
        "shared_bicycle_mode_value": 2,
        "portTo_semantics": "stored actor metadata; not used as a scene destination on the treetype-20 branch",
        "confidence": "high",
    }


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
        {"context":"normal", "opcode":-5, "semantic":"latent OBJ graphics-bank load",
         "target":"0x08005720", "proven_behavior":"latent generic path selects a 0x1800-byte ROM graphics bank by record argument and copies 0x1200+0x200 bytes into OBJ VRAM; dormant from canonical state-2 dialogue because the sole -5 record is script 6 and state-2 selectors are only 0..3", "handler":"0x08002F88", "confidence":"high"},
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




def extract_normal_dialogue_minus5_reachability(data: bytes) -> dict:
    """Close the normal-context opcode -5 path without inventing a trigger.

    The normal dialogue dispatcher has a real generic fallback that calls
    0x08005720(record.argument).  That target is an argument-indexed OBJ-VRAM
    graphics-bank loader.  In the public-demo data, however, the *only* -5
    record is script 6 / step 4 / argument 6.  Canonical state-2 dialogue
    actors select only scripts 0..3, while script 6 is selected by state-4
    collection progress index 4 and its -5 is intercepted by the dedicated
    state-4 handler at 0x080037F6.  Therefore the generic normal -5 loader is
    original code but unreachable from a normal public-demo boot.
    """
    # Parse the initialized dialogue pointer groups directly from the ROM.
    ptr_source_off = 0x00A8D73C
    groups: list[list[int]] = []
    current: list[int] = []
    for i in range(64):
        value = struct.unpack_from('<I', data, ptr_source_off + i * 4)[0]
        if ROM_BASE <= value < ROM_BASE + len(data):
            current.append(value)
            continue
        if value == 0 and current:
            groups.append(current)
            current = []
            continue
        if groups:
            break
    if current:
        groups.append(current)
    if not groups or len(groups[0]) != 7:
        raise ValueError('dialogue pointer-table shape drifted')

    dial_ptrs = groups[0]
    all_nearby_ptrs = sorted({ptr for group in groups for ptr in group})
    minus5_records: list[tuple[int, int, int, int]] = []
    for dial, ptr in enumerate(dial_ptrs):
        higher = [candidate for candidate in all_nearby_ptrs if candidate > ptr]
        if not higher:
            raise ValueError(f'dialogue script {dial} physical bound missing')
        count = (min(higher) - ptr) // 0x90
        for step in range(count):
            rec_off = ptr - ROM_BASE + step * 0x90
            opcode = struct.unpack_from('<i', data, rec_off + 0x88)[0]
            argument = struct.unpack_from('<i', data, rec_off + 0x8C)[0]
            if opcode == -5:
                minus5_records.append((dial, step, ROM_BASE + rec_off, argument))
    expected_minus5 = [(6, 4, 0x080117D8, 6)]
    if minus5_records != expected_minus5:
        raise ValueError(f'normal-dialogue -5 record inventory drifted: {minus5_records!r}')

    # The canonical serialized state-2 NPC/story actors are the sole normal
    # dialogue-selector sources.  Guard the complete recovered set, including
    # the invisible level-7 hotspots and the Katya/bicycle actor.
    state2_actors: list[tuple[int, int]] = []
    for off, props in _scan_serialized_actors(data):
        if props.get('spawnType') != 'npc':
            continue
        try:
            state = int(props.get('state', '0'), 0)
            dial = int(props.get('dial', '0'), 0)
        except ValueError:
            continue
        if state == 2:
            state2_actors.append((ROM_BASE + off, dial))
    expected_state2 = [
        (0x08018F08, 0), (0x08018F84, 1), (0x08019000, 1),
        (0x080191F8, 0), (0x08019274, 1), (0x080192F0, 2),
        (0x0801936C, 3),
    ]
    if state2_actors != expected_state2:
        raise ValueError(f'canonical state-2 dialogue actor set drifted: {state2_actors!r}')
    reachable_dials = sorted({dial for _, dial in state2_actors})
    if reachable_dials != [0, 1, 2, 3]:
        raise ValueError(f'canonical state-2 dialogue selector set drifted: {reachable_dials!r}')

    # Verify the state-4 selector chooses script 6 at progress index 4.
    state4_rows = extract_state4_collection_selector(data)
    progress4 = [row for row in state4_rows if int(row['progress_index']) == 4]
    if len(progress4) != 1 or int(progress4[0]['dialogue_script']) != 6:
        raise ValueError('state-4 progress index 4 no longer selects dialogue script 6')
    # Its -5 path is the dedicated final-sketch handler, not the generic call.
    if _thumb1_bl_target(data, 0x080037F8 - ROM_BASE) != 0x08004FE0:
        raise ValueError('state-4 -5 final-effect call drifted')

    # Verify the latent *normal* generic call and identify its target behavior.
    if _thumb1_bl_target(data, 0x08002F92 - ROM_BASE) != 0x08005720:
        raise ValueError('normal dialogue generic-record call target drifted')
    loader_sig = (
        0x2290, 0xB570, 0x0044, 0x4D0A, 0x1824, 0x02E4, 0x1961, 0x0152,
        0x4808, 0xF00B, 0xFA8F, 0x23A0, 0x2280, 0x015B, 0x18E1, 0x1949,
        0x0092, 0x4805, 0xF00B, 0xFA86,
    )
    if _unpack_halfwords(data, 0x08005720, len(loader_sig)) != loader_sig:
        raise ValueError('0x08005720 OBJ graphics-bank loader body drifted')
    if _thumb1_bl_target(data, 0x08005732 - ROM_BASE) != COPY_BYTES_HELPER or \
       _thumb1_bl_target(data, 0x08005744 - ROM_BASE) != COPY_BYTES_HELPER:
        raise ValueError('0x08005720 copy-helper calls drifted')
    source_base = struct.unpack_from('<I', data, 0x08005750 - ROM_BASE)[0]
    copy0_destination = struct.unpack_from('<I', data, 0x08005754 - ROM_BASE)[0]
    copy1_destination = struct.unpack_from('<I', data, 0x08005758 - ROM_BASE)[0]
    if (source_base, copy0_destination, copy1_destination) != (0x086493F0, 0x06010000, 0x06011400):
        raise ValueError('0x08005720 graphics source/destination literals drifted')

    return {
        'sole_minus5_script': 6,
        'sole_minus5_step': 4,
        'sole_minus5_record': '0x080117D8',
        'sole_minus5_argument': 6,
        'reachable_state2_dialogue_scripts': ','.join(str(v) for v in reachable_dials),
        'normal_minus5_reachable_from_canonical_state2': 'no',
        'state4_progress_index_for_script6': 4,
        'state4_minus5_override': '0x080037F6',
        'latent_generic_target': '0x08005720',
        'graphics_source_base': f'0x{source_base:08X}',
        'graphics_bank_stride': '0x1800',
        'copy0_destination': f'0x{copy0_destination:08X}',
        'copy0_size': '0x1200',
        'copy1_source_offset': '0x1400',
        'copy1_destination': f'0x{copy1_destination:08X}',
        'copy1_size': '0x0200',
        'reachability_conclusion': 'original normal-context graphics-bank path is dormant from canonical public-demo state-2 dialogue',
        'confidence': 'high',
    }

def extract_dialogue_audio_latch_semantics(data: bytes) -> list[dict]:
    """Close the 0x0300062C dialogue-presentation latch and page SFX lifecycle.

    State-2 dialogue and state-4 pickup activation share the same byte.  A
    zero byte selects SFX3 for the first text page; a nonzero byte selects
    SFX8 for a later text page.  Negative/control records bypass that page
    sound selection and dispatch their own opcode sounds.  The original
    one-shot mixer owns eight independent slots, so multiple control opcodes
    executed by one update can make multiple same-ID calls and must not be
    collapsed into one event by the reconstruction.
    """
    latch = 0x0300062C

    # Player construction hard-clears the latch and the adjacent byte.
    if _unpack_halfwords(data, 0x080063CE, 5) != (0x2200, 0x4B10, 0x0020, 0x701A, 0x705A):
        raise ValueError("dialogue latch constructor clear drifted")
    if struct.unpack_from('<I', data, 0x08006414 - ROM_BASE)[0] != latch:
        raise ValueError("dialogue latch constructor literal drifted")

    # State-2 first/later text selection and write-to-one convergence.
    if _unpack_halfwords(data, 0x08002E10, 9) != (
        0x4B7C, 0x9309, 0x781B, 0x2201, 0x2150, 0x2B00, 0xD000, 0xE244, 0x2003
    ):
        raise ValueError("state-2 dialogue page-sound gate drifted")
    if struct.unpack_from('<I', data, 0x08003004 - ROM_BASE)[0] != latch:
        raise ValueError("state-2 dialogue latch literal drifted")
    if _unpack_halfwords(data, 0x080032AA, 4) != (0x2008, 0xF7FE, 0xFC62, 0xE5B9):
        raise ValueError("state-2 SFX8 alternate branch drifted")
    if _unpack_halfwords(data, 0x08002E2C, 3) != (0x2301, 0x9A09, 0x7013):
        raise ValueError("state-2 dialogue latch set drifted")

    # State-4 uses the same zero/nonzero page-sound policy.
    if _unpack_halfwords(data, 0x08003066, 9) != (
        0x4BC3, 0x9309, 0x781B, 0x2201, 0x2150, 0x2B00, 0xD000, 0xE2F7, 0x2003
    ):
        raise ValueError("state-4 dialogue page-sound gate drifted")
    if struct.unpack_from('<I', data, 0x08003374 - ROM_BASE)[0] != latch:
        raise ValueError("state-4 dialogue latch literal drifted")
    if _unpack_halfwords(data, 0x08003666, 4) != (0x2008, 0xF7FE, 0xFA84, 0xE506):
        raise ValueError("state-4 SFX8 alternate branch drifted")
    if _unpack_halfwords(data, 0x08003082, 3) != (0x2301, 0x9A09, 0x7013):
        raise ValueError("state-4 dialogue latch set drifted")

    # Normal-context -1..-4 each call SFX7 and clear the saved latch pointer.
    normal_guards = (
        (0x080032D0, (0x2007, 0xF7FE, 0xFC4F, 0x2200, 0x9909, 0x700A)),
        (0x0800339C, (0x2007, 0x3204, 0x2150, 0xF7FE, 0xFBE7)),
        (0x080033C6, (0x2200, 0x9909, 0x700A)),
        (0x0800345C, (0x3203, 0x2150, 0x2007, 0xF7FE, 0xFB87)),
        (0x08003480, (0x2200, 0x9809, 0x7002)),
        (0x08003510, (0x3202, 0x2150, 0x2007, 0xF7FE, 0xFB2D)),
        (0x08003530, (0x2200, 0x9809, 0x7002)),
    )
    for address, expected in normal_guards:
        if _unpack_halfwords(data, address, len(expected)) != expected:
            raise ValueError(f"normal dialogue SFX7/latch-clear guard drifted at 0x{address:08X}")

    # State-4 selector -1 is deliberately silent and writes zero to the latch.
    if _unpack_halfwords(data, 0x080035C4, 9) != (
        0x4651, 0x9A08, 0x3201, 0x600A, 0x2264, 0x4252, 0x60EA, 0x4A2C, 0x7013
    ):
        raise ValueError("state-4 selector -1 silent clear path drifted")
    if struct.unpack_from('<I', data, 0x08003684 - ROM_BASE)[0] != latch:
        raise ValueError("state-4 selector -1 latch literal drifted")

    # State-4 terminal -1/-2/-3 each play SFX7 and clear the saved latch.
    state4_terminal_guards = (
        (0x08003742, (0x3202, 0x2150, 0x2007, 0xF7FE, 0xFA14)),
        (0x08003760, (0x2200, 0x9909, 0x700A)),
        (0x08003688, (0x3203, 0x2150, 0x2007, 0xF7FE, 0xFA71)),
        (0x080036AE, (0x2200, 0x9909, 0x700A)),
        (0x08003894, (0x2007, 0x3204, 0x2150, 0xF7FE, 0xF96B)),
        (0x080038BC, (0x2300, 0x9A09, 0x7013)),
    )
    for address, expected in state4_terminal_guards:
        if _unpack_halfwords(data, address, len(expected)) != expected:
            raise ValueError(f"state-4 terminal SFX7/latch-clear guard drifted at 0x{address:08X}")

    # State-4 -4 has no one-shot call in its handler and advances to the next
    # record without clearing the latch; -5 has its dedicated SFX13 path.
    if _unpack_halfwords(data, 0x080031E6, 10) != (
        0x4B68, 0x3205, 0x601A, 0x1C43, 0x00DA, 0x672B, 0x18D3, 0x2288, 0x011B, 0x18CB
    ):
        raise ValueError("state-4 -4 continuation handler drifted")
    if _unpack_halfwords(data, 0x080037F6, 8) != (
        0x2000, 0xF001, 0xFBF2, 0x2201, 0x2150, 0x200D, 0xF7FE, 0xF9B7
    ):
        raise ValueError("state-4 -5 SFX13 handler drifted")

    # play_once scans eight 0x1C-byte slots and allocates the first whose
    # active/secondary flags are both zero.  Calls in the same update are
    # therefore multiplicative rather than last-write-wins.
    if _unpack_halfwords(data, 0x08001B7E, 11) != (
        0x002B, 0x7E1C, 0x2C00, 0xD102, 0x781C, 0x2C00, 0xD009,
        0x3201, 0x331C, 0x2A08, 0xD1F5
    ):
        raise ValueError("one-shot eight-slot allocator loop drifted")

    return [
        {
            "phase": "constructor_clear", "latch": "0x0300062C", "value_before": "any",
            "trigger": "Player construction", "sound": "silent", "value_after": 0,
            "evidence": "0x080063CE..0x080063D6; literal 0x08006414", "confidence": "high",
        },
        {
            "phase": "state2_first_text", "latch": "0x0300062C", "value_before": 0,
            "trigger": "accepted state-2 fresh A whose target record is text/nonnegative",
            "sound": "SFX3@80", "value_after": 1,
            "evidence": "0x08002E10..0x08002E30", "confidence": "high",
        },
        {
            "phase": "state2_next_text", "latch": "0x0300062C", "value_before": 1,
            "trigger": "accepted state-2 fresh A whose immediate target record is text/nonnegative",
            "sound": "SFX8@80", "value_after": 1,
            "evidence": "0x08002E1A -> 0x080032AA -> 0x08002E26..0x08002E30", "confidence": "high",
        },
        {
            "phase": "normal_control_-1_to_-4", "latch": "0x0300062C", "value_before": 1,
            "trigger": "normal dialogue immediate target is opcode -1/-2/-3/-4; chained controls stay in same update",
            "sound": "SFX7@80 per record", "value_after": 0,
            "evidence": "0x080032D0;0x0800339C;0x08003460;0x08003514 plus latch clears", "confidence": "high",
        },
        {
            "phase": "state4_first_text", "latch": "0x0300062C", "value_before": 0,
            "trigger": "accepted state-4 fresh A whose target record is text/nonnegative",
            "sound": "SFX3@80", "value_after": 1,
            "evidence": "0x08003066..0x08003086", "confidence": "high",
        },
        {
            "phase": "state4_next_text", "latch": "0x0300062C", "value_before": 1,
            "trigger": "accepted state-4 fresh A whose immediate target record is text/nonnegative",
            "sound": "SFX8@80", "value_after": 1,
            "evidence": "0x08003070 -> 0x08003666 -> 0x0800307C..0x08003086", "confidence": "high",
        },
        {
            "phase": "state4_selector_minus1", "latch": "0x0300062C", "value_before": 0,
            "trigger": "state-4 collection selector == -1 on fresh A",
            "sound": "silent", "value_after": 0,
            "evidence": "0x080035C4..0x080035D4; literal 0x08003684", "confidence": "high",
        },
        {
            "phase": "state4_terminal_-1_to_-3", "latch": "0x0300062C", "value_before": 1,
            "trigger": "state-4 immediate target opcode -1/-2/-3",
            "sound": "SFX7@80", "value_after": 0,
            "evidence": "0x08003742;0x08003688;0x08003894 plus saved-latch clears", "confidence": "high",
        },
        {
            "phase": "state4_control_-4", "latch": "0x0300062C", "value_before": 1,
            "trigger": "state-4 immediate target opcode -4",
            "sound": "silent", "value_after": 1,
            "evidence": "0x080031E6 advances cursor into next record with no SFX call/latch clear", "confidence": "high",
        },
        {
            "phase": "state4_terminal_-5", "latch": "0x0300062C", "value_before": 1,
            "trigger": "state-4 immediate target opcode -5",
            "sound": "SFX13@80", "value_after": "terminal/final-effect path",
            "evidence": "0x080037F6..0x08003802", "confidence": "high",
        },
        {
            "phase": "mixer_multiplicity", "latch": "n/a", "value_before": "n/a",
            "trigger": "multiple play_once calls before mixer update",
            "sound": "8 independent one-shot slots", "value_after": "n/a",
            "evidence": "0x08001B7E..0x08001B92 scans 8 slots at 0x1C-byte stride", "confidence": "high",
        },
    ]


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

    if _unpack_halfwords(data, 0x08008318, 3) != (0x681B, 0x2B06, 0xD101):
        raise ValueError("Wardrobe hidden B+SELECT entry path drifted")
    if _unpack_halfwords(data, 0x08009672, 2) != (0x2200, 0x2107):
        raise ValueError("Wardrobe Level-7 exit request drifted")

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
        {"fact":"hidden_entry_input", "value":"keys_current == 0x0006 (B+SELECT)",
         "evidence":"0x08008318 loads current keys; 0x0800831A compares exact value 6 and 0x0800831C skips the scene request when unequal",
         "confidence":"high"},
        {"fact":"exit_behavior", "value":"fresh B -> Gameplay Level 7",
         "evidence":"Wardrobe B path uses fresh-key logic; 0x08009672 sets variant 0 and 0x08009674 sets level 7 before scene request",
         "confidence":"high"},
        {"fact":"wardrobe_navigation_sfx", "value":"none proven",
         "evidence":"SFX11 call sites 0x0800898E and 0x0800904E are outside the selector Left/Right branches 0x0800951E..0x080095C0",
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



def extract_player_controller_modes(data: bytes) -> list[dict]:
    """Recover the dedicated Player controller-mode global.

    The low-ROM code has exactly two literal references to 0x03000624.  The
    central Player_update dispatch compares only values 5 and 6; value 0 is
    the ordinary non-scripted path.  Other large Player_update state machines
    are driven by different Player fields/globals and must not be folded into
    this controller-mode inventory.
    """
    mode_global = 0x03000624
    refs = _thumb_literal_refs_to(data, mode_global, 0x08000000, 0x08012000)
    expected_refs = [0x080081F2, 0x08008806]
    if refs != expected_refs:
        raise ValueError(f"Player controller-mode global xrefs drifted: {refs!r}")

    dispatch = (0x9B09, 0x32FF, 0x681B, 0x4590, 0xDC02, 0x4642, 0x3203,
                0x61A2, 0x2B05, 0xD100, 0xE10C, 0x2B06, 0xD000, 0xE10F)
    if _unpack_halfwords(data, 0x080086BC, len(dispatch)) != dispatch:
        raise ValueError("Player controller-mode 5/6 dispatch drifted")

    boundary = (0x3301, 0x2200, 0x4830, 0x210A, 0xF7FD, 0xFA02,
                0x2305, 0x9A09, 0x6AA8, 0x6013)
    if _unpack_halfwords(data, 0x08008820, len(boundary)) != boundary:
        raise ValueError("Level-9 boundary mode-5 write drifted")

    mode5_head = (0x6F2B, 0x3301, 0x4699, 0x672B, 0x23B9, 0x005B, 0x61A3)
    if _unpack_halfwords(data, 0x0800935A, len(mode5_head)) != mode5_head:
        raise ValueError("Player mode-5 counter/+370 request block drifted")

    mode5_handoff = (0x2700, 0x4835, 0x60E0, 0x4835, 0x6007,
                     0x2006, 0x61A7, 0x9F09, 0x6038)
    if _unpack_halfwords(data, 0x080093A2, len(mode5_handoff)) != mode5_handoff:
        raise ValueError("Player mode-5 to mode-6 handoff drifted")

    mode6_exit = (0x2208, 0x2300, 0x6032, 0x9A09, 0x61E3, 0x6013)
    if _unpack_halfwords(data, 0x080094F4, len(mode6_exit)) != mode6_exit:
        raise ValueError("Player mode-6 exit block drifted")

    ref_text = "|".join(f"0x{ref:08X}" for ref in refs)
    common = {
        "mode_global": "0x03000624",
        "mode_global_literal_refs": ref_text,
        "confidence": "high",
    }
    return [
        {
            **common,
            "mode": 0,
            "level_guard": "",
            "entry": "ordinary Player_update path",
            "behavior": "normal gameplay / non-scripted controller path",
            "next_mode": "",
            "evidence": "0x080086BC dispatch falls through when value is neither 5 nor 6",
        },
        {
            **common,
            "mode": 5,
            "level_guard": "10 after queued Level-9 handoff",
            "entry": "0x08008820..0x08008832 writes 5",
            "behavior": "+370 fixed8 X each Level-10 update; increment controller counter; when X > 700 and counter > 350 snap Y to 870 and switch to mode 6",
            "next_mode": "6",
            "evidence": "0x0800935A counter/+370 block; 0x080093A2 handoff",
        },
        {
            **common,
            "mode": 6,
            "level_guard": "10",
            "entry": "mode-5 handoff",
            "behavior": "-256 fixed8 Y while Y > 780; Y <= 780 clears requested Y and controller mode",
            "next_mode": "0",
            "evidence": "mode-6 branch and 0x080094F4 exit block",
        },
    ]


def extract_camera_runtime_semantics(data: bytes) -> list[dict]:
    """Export the public-demo Player camera dead-zone and persistence contract.

    0x08006550 derives the Player body center from fixed8 fields +0x08/+0x10
    and +0x0C/+0x14, then moves the camera only when that center leaves the
    96..144 by 67..93 pixel dead-zone. 0x0800A2D4 clamps to the 30x20-tile
    viewport and publishes camera>>3 as the streaming origin. Gameplay-scene
    activation calls the level-resource loader, then the tracker and clamp in
    sequence; it does not reset either camera global between levels.
    """
    tracker_expected = (
        0x6882, 0x4694, 0x6903, 0x105B, 0x4463, 0x121B, 0xB510, 0x001C,
        0x490F, 0x680A, 0x3C90, 0x42A2, 0xDA01, 0x0022, 0x600C, 0x3B60,
        0x4293, 0xDA00, 0x600B, 0x6943, 0x105A, 0x68C3, 0x1A9B, 0x121B,
        0x0018, 0x4908, 0x680A, 0x385D, 0x4282, 0xDA01, 0x0002, 0x6008,
        0x3B43, 0x4293, 0xDA00, 0x600B, 0xBC10, 0xBC01, 0x4700, 0x46C0,
    )
    if _unpack_halfwords(data, 0x08006550, len(tracker_expected)) != tracker_expected:
        raise ValueError("Player camera dead-zone tracker drifted")
    if struct.unpack_from("<I", data, 0x080065A0 - ROM_BASE)[0] != 0x03000570:
        raise ValueError("camera-X global literal drifted")
    if struct.unpack_from("<I", data, 0x080065A4 - ROM_BASE)[0] != 0x0300056C:
        raise ValueError("camera-Y global literal drifted")

    clamp_expected = (
        0xB530, 0x4C11, 0x6821, 0x43CB, 0x17DB, 0x4019, 0x4D0F, 0x4B10,
        0x681A, 0x682B, 0x43D8, 0x3A1E, 0x17C0, 0x4003, 0x00D2, 0x429A,
        0xDD00, 0x001A, 0x4B0B, 0x681B, 0x3B14, 0x602A, 0x00DB, 0x428B,
        0xDD00, 0x000B, 0x4908, 0x6023, 0x10D2, 0x10DB, 0x600A, 0x604B,
    )
    if _unpack_halfwords(data, 0x0800A2D4, len(clamp_expected)) != clamp_expected:
        raise ValueError("camera clamp/stream-origin block drifted")
    clamp_literals = (
        struct.unpack_from("<I", data, 0x0800A31C - ROM_BASE)[0],
        struct.unpack_from("<I", data, 0x0800A320 - ROM_BASE)[0],
        struct.unpack_from("<I", data, 0x0800A324 - ROM_BASE)[0],
        struct.unpack_from("<I", data, 0x0800A328 - ROM_BASE)[0],
        struct.unpack_from("<I", data, 0x0800A32C - ROM_BASE)[0],
    )
    if clamp_literals != (0x0300056C, 0x03000570, 0x03000548, 0x0300054C, 0x030006C4):
        raise ValueError(f"camera clamp literals drifted: {clamp_literals!r}")

    # Gameplay-scene entry: BL load_level_record_resources; load Player;
    # BL 0x08006550 tracker; BL 0x0800A2D4 clamp/stream-index.
    scene_entry_expected = (0xF7FF, 0xFF82, 0x4C5A, 0x6A60, 0xF000, 0xFD7E, 0xF004, 0xFC3E)
    if _unpack_halfwords(data, 0x08005A48, len(scene_entry_expected)) != scene_entry_expected:
        raise ValueError("gameplay-scene camera activation sequence drifted")
    if _thumb_literal_refs_to(data, 0x03000570, 0x08005950, 0x080059FC):
        raise ValueError("level-resource loader unexpectedly references camera X")
    if _thumb_literal_refs_to(data, 0x0300056C, 0x08005950, 0x080059FC):
        raise ValueError("level-resource loader unexpectedly references camera Y")

    # Keep a conservative whole-code literal-reference closure.  Only the
    # tracker and clamp refs are direct writers; the rest are camera consumers
    # (draw/cull/stream helpers).  Any new reference forces this evidence to be
    # reclassified rather than silently assuming persistence remains true.
    x_refs = _thumb_literal_refs_to(data, 0x03000570, 0x08000000, 0x08012000)
    y_refs = _thumb_literal_refs_to(data, 0x0300056C, 0x08000000, 0x08012000)
    expected_x_refs = [
        0x08001448, 0x080026BA, 0x080027B4, 0x0800282A, 0x08004B8E,
        0x08005FB4, 0x08005FCA, 0x08006560, 0x08006616, 0x080068CE,
        0x08008CFE, 0x080094B8, 0x08009F88, 0x0800A002, 0x0800A2E0,
        0x0800AB8C, 0x0800ABF6, 0x0800AC4E, 0x0800ACD4, 0x0800AD30,
        0x0800ADE6,
    ]
    expected_y_refs = [
        0x08001518, 0x0800166C, 0x080026AE, 0x080027C0, 0x0800281E,
        0x08004B9A, 0x08005FE0, 0x08006582, 0x08006632, 0x08006B6C,
        0x08006C1A, 0x08008CF0, 0x080094AA, 0x08009F84, 0x08009FFE,
        0x0800A2D6, 0x0800AB96, 0x0800ABE4, 0x0800AC3C, 0x0800ACBA,
        0x0800AD18, 0x0800ADD2,
    ]
    if x_refs != expected_x_refs:
        raise ValueError(f"camera-X literal-reference closure drifted: {x_refs!r}")
    if y_refs != expected_y_refs:
        raise ValueError(f"camera-Y literal-reference closure drifted: {y_refs!r}")

    return [
        {
            "fact": "camera_globals",
            "value": "X=0x03000570,Y=0x0300056C",
            "evidence": "tracker literals 0x080065A0/0x080065A4; clamp literals 0x0800A31C/0x0800A320",
            "confidence": "high",
        },
        {
            "fact": "player_camera_center",
            "value": "X=(+0x08+(+0x10/2))>>8;Y=(+0x0C-(+0x14/2))>>8",
            "evidence": "0x08006550..0x0800657E fixed8 body-center arithmetic",
            "confidence": "high",
        },
        {
            "fact": "horizontal_deadzone",
            "value": "96..144 px",
            "evidence": "0x08006564 subtracts 0x90; 0x0800656E subtracts 0x60",
            "confidence": "high",
        },
        {
            "fact": "vertical_deadzone",
            "value": "67..93 px",
            "evidence": "0x08006586 subtracts 0x5D; 0x08006590 subtracts 0x43",
            "confidence": "high",
        },
        {
            "fact": "camera_clamp_viewport",
            "value": "30x20 tiles",
            "evidence": "0x0800A2EA subtracts 0x1E; 0x0800A2FC subtracts 0x14; both multiplied by 8",
            "confidence": "high",
        },
        {
            "fact": "stream_origin",
            "value": "camera_x>>3,camera_y>>3",
            "evidence": "0x0800A30C..0x0800A312 writes to 0x030006C4/+4",
            "confidence": "high",
        },
        {
            "fact": "scene_transition_camera",
            "value": "preserved",
            "evidence": "0x08005A48 loads level resources then 0x08005A50 calls tracker and 0x08005A54 calls clamp; 0x08005950 loader has no camera-global reference",
            "confidence": "high",
        },
        {
            "fact": "direct_writer_closure",
            "value": "tracker 0x08006550 + clamp 0x0800A2D4",
            "evidence": f"conservative literal refs guarded: X={len(x_refs)},Y={len(y_refs)}; non-writer refs are draw/cull/stream consumers",
            "confidence": "high",
        },
    ]


def extract_gameplay_frame_order(data: bytes) -> list[dict]:
    """Export the active GameplayScene draw/update and camera phase order.

    GameplayScene_update publishes/clamps the previously tracked camera,
    streams the world, starts OAM, traverses every object's draw slot (+0x10),
    finalizes OAM, and only then traverses every object's update slot (+0x0C).
    Player_update calls the dead-zone tracker from that later update traversal,
    so a newly tracked camera position is not published until the next active
    GameplayScene frame.
    """
    call_sites = (
        (0x08004B76, 0x0800A2D4, "camera_clamp_publish"),
        (0x08004B80, 0x0800A400, "world_stream"),
        (0x08004BBE, 0x0800AB28, "oam_begin"),
        (0x08004BC6, 0x08000B98, "object_draw_traversal"),
        (0x08004BCA, 0x0800AB34, "oam_end"),
        (0x08004BD0, 0x08001428, "object_update_traversal"),
    )
    actual_targets = []
    for site, expected_target, label in call_sites:
        target = _thumb1_bl_target(data, site - ROM_BASE)
        if target != expected_target:
            raise ValueError(
                f"GameplayScene {label} call drifted at 0x{site:08X}: "
                f"expected 0x{expected_target:08X}, got {target!r}"
            )
        actual_targets.append(target)

    player_vtable = 0x08019688
    update_ptr = struct.unpack_from("<I", data, player_vtable + 0x0C - ROM_BASE)[0]
    draw_ptr = struct.unpack_from("<I", data, player_vtable + 0x10 - ROM_BASE)[0]
    if update_ptr != 0x080081B1 or draw_ptr != 0x080065FD:
        raise ValueError(
            f"Player vtable update/draw slots drifted: update={update_ptr:#x}, draw={draw_ptr:#x}"
        )
    if struct.unpack_from("<H", data, 0x08000BAC - ROM_BASE)[0] != 0x691B:
        raise ValueError("generic draw traversal no longer loads vtable +0x10")
    if struct.unpack_from("<H", data, 0x0800160C - ROM_BASE)[0] != 0x68DB:
        raise ValueError("generic update traversal no longer loads vtable +0x0C")

    tracker_call = _thumb1_bl_target(data, 0x08008B7A - ROM_BASE)
    if tracker_call != 0x08006550:
        raise ValueError(f"Player_update camera tracker call drifted: {tracker_call!r}")

    return [
        {
            "fact": "active_scene_phase_order",
            "value": "camera clamp/publish -> world stream -> OAM begin -> object draw traversal -> OAM end -> object update traversal",
            "evidence": "BL chain 0x08004B76,0x08004B80,0x08004BBE,0x08004BC6,0x08004BCA,0x08004BD0",
            "confidence": "high",
        },
        {
            "fact": "object_draw_slot",
            "value": "vtable +0x10",
            "evidence": "0x08000BAC ldr r3,[r3,#0x10]; Player vtable 0x08019688 +0x10 = 0x080065FD Player_draw",
            "confidence": "high",
        },
        {
            "fact": "object_update_slot",
            "value": "vtable +0x0C",
            "evidence": "0x0800160C ldr r3,[r3,#0x0C]; Player vtable 0x08019688 +0x0C = 0x080081B1 Player_update",
            "confidence": "high",
        },
        {
            "fact": "player_camera_tracking_phase",
            "value": "Player_update tracks after current-frame draw; publication is next active GameplayScene frame",
            "evidence": "0x08008B7A BL 0x08006550 occurs in Player_update, while GameplayScene draw traversal precedes update traversal",
            "confidence": "high",
        },
    ]



def extract_gameplay_oam_insertion_order(data: bytes) -> list[dict]:
    """Bind insertion-ordered draw traversal to the shared monotonic OAM allocator.

    The common OBJ submit helper uses one incrementing OAM index.  Story overlays
    are loaded before the physical level list, and Player has one recovered
    physical-list ordinal per level.  Therefore equal-priority OBJ tie-breaking
    must follow overlay/physical insertion order rather than reserving Player at
    a globally lower OAM index.
    """
    expected = (
        0x18EB, 0x46B1, 0x6936, 0x691D, 0x0189, 0x4466, 0x4339,
        0x00F6, 0x4329, 0x8031, 0x21C0, 0x6A1B, 0x05C0, 0x0DC0,
        0x4318, 0x4B0A, 0x0052, 0x401A, 0x9B07, 0x0109, 0x029B,
        0x400B, 0x431A, 0x464B, 0x691B, 0x4320, 0x1C5C, 0x464B,
        0x8070, 0x80B2, 0x611C,
    )
    if _unpack_halfwords(data, 0x0800A958, len(expected)) != expected:
        raise ValueError('shared monotonic OAM submit sequence drifted')

    overlay_rows = extract_story_overlay_update_order(data)
    if overlay_rows[0]['relative_order'] != 'first':
        raise ValueError('story-overlay prefix ordering drifted')
    player_rows = extract_player_npc_update_order(data)

    rows = [
        {
            'fact': 'oam_allocator',
            'level': 'all',
            'value': 'shared monotonic OAM submission counter',
            'evidence': '0x0800A958..0x0800A994 writes OAM[counter] then increments the same counter',
            'runtime_consequence': 'draw traversal order is the equal-priority OBJ tie-break order',
            'confidence': 'high',
        },
        {
            'fact': 'story_overlay_prefix',
            'level': 'all',
            'value': 'story overlays before physical LevelRecord+0x38 actors',
            'evidence': '0x08005996 submits story overlay list before 0x080059AE physical actor list',
            'runtime_consequence': 'loaded overlay NPCs can own lower OAM indices than Player',
            'confidence': 'high',
        },
    ]
    for row in player_rows:
        rows.append({
            'fact': 'player_physical_index',
            'level': row['level'],
            'value': row['player_index'],
            'evidence': f"serialized Player record at {row['player_rom_addr']}",
            'runtime_consequence': 'insert Player after this many physical-list objects, following the overlay prefix',
            'confidence': 'high',
        })
    return rows

def extract_player_npc_update_order(data: bytes) -> list[dict]:
    """Export canonical Player-vs-physical-NPC update ordinals for all levels.

    The GameplayScene object manager updates the serialized level objects in
    insertion order. Physical NPCs are serialized as spawner records with
    spawnType=npc. In every canonical level they occur strictly after Player,
    so NPC motion/proximity/interaction logic consumes the Player state already
    produced by that frame's Player_update.
    """
    expected_player_indices = {0: 8, 1: 2, 2: 0, 3: 0, 4: 0, 5: 0,
                               6: 8, 7: 0, 8: 4, 9: 2, 10: 1}
    expected_npc_counts = {0: 3, 1: 9, 2: 9, 3: 1, 4: 5, 5: 28,
                           6: 3, 7: 0, 8: 2, 9: 21, 10: 11}
    rows: list[dict] = []
    total_npc_refs = 0
    base = LEVEL_RECORD_SOURCE_ROM - ROM_BASE
    for level in range(11):
        record_off = base + level * LEVEL_RECORD_SIZE
        actor_addr = struct.unpack_from('<I', data, record_off + 0x38)[0]
        off = actor_addr - ROM_BASE
        actors: list[tuple[int, int, dict[str, str]]] = []
        index = 0
        while True:
            parsed = _parse_serialized_actor(data, off)
            if parsed is None:
                break
            props, end = parsed
            actors.append((index, ROM_BASE + off, props))
            index += 1
            off = end

        players = [(i, addr, props) for i, addr, props in actors if props.get('type') == 'player']
        if len(players) != 1:
            raise ValueError(f'level {level} Player ordinal inventory drifted: {players!r}')
        player_index, player_addr, _ = players[0]
        if player_index != expected_player_indices[level]:
            raise ValueError(f'level {level} Player ordinal drifted: {player_index}')

        npcs = [(i, addr, props) for i, addr, props in actors
                if props.get('type') == 'spawner' and props.get('spawnType') == 'npc']
        if len(npcs) != expected_npc_counts[level]:
            raise ValueError(f'level {level} physical NPC count drifted: {len(npcs)}')
        if any(i <= player_index for i, _, _ in npcs):
            raise ValueError(f'level {level} contains pre-Player physical NPCs: {npcs!r}')
        total_npc_refs += len(npcs)

        rows.append({
            'level': str(level),
            'player_index': str(player_index),
            'player_rom_addr': f'0x{player_addr:08X}',
            'physical_npc_count': str(len(npcs)),
            'first_npc_index': str(npcs[0][0]) if npcs else '',
            'last_npc_index': str(npcs[-1][0]) if npcs else '',
            'all_npcs_after_player': '1',
            'runtime_consequence': 'physical NPC update/motion/proximity consumes same-frame post-Player state',
            'confidence': 'high',
        })
    if total_npc_refs != 92:
        raise ValueError(f'physical NPC level-reference total drifted: {total_npc_refs}')
    return rows


def extract_player_portal_update_order(data: bytes) -> list[dict]:
    """Export Player-relative ordinals for all code-proven generic Fgtile portals.

    The generic Fgtile updater is an ordinary serialized object update.  A
    portal before Player therefore tests the pre-movement Player position;
    a portal after Player tests the position produced by that frame's
    Player_update.  Only Levels 1 and 8 contain pre-Player generic portals.
    """
    expected_player_indices = {0: 8, 1: 2, 2: 0, 3: 0, 4: 0, 5: 0,
                               6: 8, 7: 0, 8: 4, 9: 2, 10: 1}
    expected_portal_counts = {0: 4, 1: 6, 2: 3, 3: 0, 4: 0, 5: 6,
                              6: 4, 7: 3, 8: 4, 9: 3, 10: 0}
    expected_pre = {
        (1, 0, 0x08533B70), (1, 1, 0x08533BB4),
        (8, 0, 0x0841A110), (8, 1, 0x0841A154),
        (8, 2, 0x0841A198), (8, 3, 0x0841A1DC),
    }
    rows: list[dict] = []
    total = 0
    pre_total = 0
    base = LEVEL_RECORD_SOURCE_ROM - ROM_BASE
    for level in range(11):
        record_off = base + level * LEVEL_RECORD_SIZE
        actor_addr = struct.unpack_from('<I', data, record_off + 0x38)[0]
        off = actor_addr - ROM_BASE
        actors: list[tuple[int, int, dict[str, str]]] = []
        index = 0
        while True:
            parsed = _parse_serialized_actor(data, off)
            if parsed is None:
                break
            props, end = parsed
            actors.append((index, ROM_BASE + off, props))
            index += 1
            off = end

        players = [(i, addr, props) for i, addr, props in actors if props.get('type') == 'player']
        if len(players) != 1:
            raise ValueError(f'level {level} Player ordinal inventory drifted: {players!r}')
        player_index = players[0][0]
        if player_index != expected_player_indices[level]:
            raise ValueError(f'level {level} Player ordinal drifted: {player_index}')

        portals: list[tuple[int, int, dict[str, str]]] = []
        for i, addr, props in actors:
            if props.get('type') != 'fgtile' or 'portTo' not in props:
                continue
            try:
                target = int(props['portTo'])
            except ValueError:
                continue
            if not 0 <= target <= 10:
                continue
            # Level-10 turn-4/5 records use portTo=8 only as metadata and are
            # handled by the recovered rusty-key traversal, never generic scene requests.
            if level == 10 and props.get('turn') in ('4', '5'):
                continue
            portals.append((i, addr, props))

        if len(portals) != expected_portal_counts[level]:
            raise ValueError(f'level {level} generic portal count drifted: {len(portals)}')
        total += len(portals)
        for i, addr, props in portals:
            pre = i < player_index
            key = (level, i, addr)
            if pre:
                pre_total += 1
                if key not in expected_pre:
                    raise ValueError(f'unexpected pre-Player portal: {key!r}')
            elif key in expected_pre:
                raise ValueError(f'expected pre-Player portal moved after Player: {key!r}')
            rows.append({
                'level': str(level),
                'player_index': str(player_index),
                'controller_index': str(i),
                'controller_rom_addr': f'0x{addr:08X}',
                'target_level': props['portTo'],
                'phase': 'pre_player' if pre else 'post_player',
                'runtime_consequence': (
                    'contact uses previous-frame Player position before Player_update'
                    if pre else
                    'contact uses same-frame Player position after Player_update'
                ),
                'confidence': 'high',
            })
    if total != 33 or pre_total != 6 or len(expected_pre) != 6:
        raise ValueError(f'generic portal ordering totals drifted: total={total}, pre={pre_total}')
    return rows


def extract_player_fgtile_update_order(data: bytes) -> list[dict]:
    """Export the canonical Player/Fgtile ordinals for the two special gates.

    Physical level actors are serialized contiguously at LevelRecord+0x38 and
    the generic object manager updates them in insertion order.  Level 9's
    treetype-20 bicycle controller and Level 10's turn-4/5 rusty-key gates all
    occur after Player, so their update logic consumes the Player state already
    produced by that frame's Player_update.
    """
    rows: list[dict] = []
    base = LEVEL_RECORD_SOURCE_ROM - ROM_BASE
    for level in (9, 10):
        record_off = base + level * LEVEL_RECORD_SIZE
        actor_addr = struct.unpack_from('<I', data, record_off + 0x38)[0]
        off = actor_addr - ROM_BASE
        actors: list[tuple[int, int, dict[str, str]]] = []
        index = 0
        while True:
            parsed = _parse_serialized_actor(data, off)
            if parsed is None:
                break
            props, end = parsed
            actors.append((index, ROM_BASE + off, props))
            index += 1
            off = end
        player_rows = [(i, addr, props) for i, addr, props in actors if props.get('type') == 'player']
        if len(player_rows) != 1:
            raise ValueError(f'level {level} Player ordinal inventory drifted: {player_rows!r}')
        player_index = player_rows[0][0]

        if level == 9:
            selected = [(i, addr, props) for i, addr, props in actors
                        if props.get('type') == 'fgtile' and props.get('treetype') == '20']
            if [(i, addr) for i, addr, _ in selected] != [(11, 0x08386FF0)]:
                raise ValueError(f'Level-9 treetype20 ordinal drifted: {selected!r}')
            if player_index != 2:
                raise ValueError(f'Level-9 Player ordinal drifted: {player_index}')
            for i, addr, props in selected:
                rows.append({
                    'level': str(level),
                    'player_index': str(player_index),
                    'controller_index': str(i),
                    'controller_rom_addr': f'0x{addr:08X}',
                    'controller_kind': 'treetype20_bicycle',
                    'metadata': f"treetype={props.get('treetype')};portTo={props.get('portTo')}",
                    'relative_order': 'after Player',
                    'runtime_consequence': 'fresh-A contact sees same-frame post-Player position; queued vertical target applies on the next Player update',
                    'confidence': 'high',
                })
        else:
            selected = [(i, addr, props) for i, addr, props in actors
                        if props.get('type') == 'fgtile' and props.get('turn') in ('4', '5')]
            expected = [
                (13, 0x08367380, '4'), (14, 0x083673CC, '4'),
                (15, 0x08367418, '5'), (16, 0x08367464, '5'),
            ]
            actual = [(i, addr, props.get('turn')) for i, addr, props in selected]
            if actual != expected:
                raise ValueError(f'Level-10 turn4/5 gate ordinal drifted: {actual!r}')
            if player_index != 1:
                raise ValueError(f'Level-10 Player ordinal drifted: {player_index}')
            for i, addr, props in selected:
                rows.append({
                    'level': str(level),
                    'player_index': str(player_index),
                    'controller_index': str(i),
                    'controller_rom_addr': f'0x{addr:08X}',
                    'controller_kind': f"turn{props.get('turn')}_rusty_key_gate",
                    'metadata': f"turn={props.get('turn')};portTo={props.get('portTo')}",
                    'relative_order': 'after Player',
                    'runtime_consequence': 'fresh-A gate geometry sees same-frame post-Player position; forced vertical target is queued for the next Player update',
                    'confidence': 'high',
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

    story_activation_row = extract_story_overlay_activation_policy(data)
    write_csv(args.out / "story_overlay_activation_policy.csv",
              list(story_activation_row), [story_activation_row])

    story_overlay_order_rows = extract_story_overlay_update_order(data)
    write_csv(args.out / "story_overlay_update_order.csv",
              ["phase","call_site","loader","list_source","relative_order",
               "runtime_consequence","confidence"], story_overlay_order_rows)

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

    player_rows = extract_player_sprite_pipeline(data)
    write_csv(args.out / "player_sprite_pipeline.csv", ["fact","value","evidence"], player_rows)

    player_idle_rows = extract_player_level_idle_selector(data)
    write_csv(args.out / "player_level_idle_selector.csv",
              ["level","record_rom_addr","record_field","idle_selector","load_addr",
               "player_field","store_addr","evidence","confidence"], player_idle_rows)

    player_motion_rows = extract_player_motion_collision_contract(data)
    write_csv(args.out / "player_motion_collision_contract.csv",
              ["fact","value","evidence","confidence"], player_motion_rows)

    camera_rows = extract_camera_runtime_semantics(data)
    write_csv(args.out / "camera_runtime_semantics.csv",
              ["fact","value","evidence","confidence"], camera_rows)

    frame_order_rows = extract_gameplay_frame_order(data)
    write_csv(args.out / "gameplay_frame_order.csv",
              ["fact","value","evidence","confidence"], frame_order_rows)

    oam_order_rows = extract_gameplay_oam_insertion_order(data)
    write_csv(args.out / "gameplay_oam_insertion_order.csv",
              ["fact","level","value","evidence","runtime_consequence","confidence"],
              oam_order_rows)

    player_portal_rows = extract_player_portal_update_order(data)
    write_csv(args.out / "player_portal_update_order.csv",
              ["level","player_index","controller_index","controller_rom_addr","target_level",
               "phase","runtime_consequence","confidence"], player_portal_rows)

    player_fgtile_rows = extract_player_fgtile_update_order(data)
    write_csv(args.out / "player_fgtile_update_order.csv",
              ["level","player_index","controller_index","controller_rom_addr","controller_kind",
               "metadata","relative_order","runtime_consequence","confidence"], player_fgtile_rows)

    player_npc_rows = extract_player_npc_update_order(data)
    write_csv(args.out / "player_npc_update_order.csv",
              ["level","player_index","player_rom_addr","physical_npc_count",
               "first_npc_index","last_npc_index","all_npcs_after_player",
               "runtime_consequence","confidence"], player_npc_rows)

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

    interaction_geometry_rows = extract_npc_interaction_geometry(data)
    write_csv(args.out / "npc_interaction_geometry.csv",
              ["state","dispatch_address","working_name","proximity_cells","geometry_condition",
               "activation","input_rule","grid_shift","actor_origin_bias_fixed","actor_origin_bias_cells",
               "scratch_state","activation_effect","evidence","confidence"],
              interaction_geometry_rows)

    state_rows = extract_npc_state_modes(data)
    write_csv(args.out / "npc_state_modes.csv",
              ["state","dispatch_address","working_name","proven_behavior","confidence"], state_rows)

    fixed_row = extract_npc_fixed_point_runtime(data)
    write_csv(args.out / "npc_fixed_point_runtime.csv", list(fixed_row), [fixed_row])

    special_rows = extract_npc_special_movers(data)
    write_csv(args.out / "npc_special_movers.csv",
              ["actor_rom_addr","legs_color","x_serialized","y_serialized","x_truncated_px","y_truncated_px",
               "turn","port_to","timer_address","timer_initial","timer_reload","proximity_radius_pixels",
               "activation_sfx","movement","confidence"], special_rows)

    inventory_rows = extract_actor_system_inventory(data)
    write_csv(args.out / "actor_system_inventory.csv",
              ["family","serialized_total","physical_count","story_overlay_count","factory","constructor",
               "update","draw","vtable","runtime_role","confidence"], inventory_rows)

    field_rows = extract_new_actor_field_semantics(data)
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

    minus5_row = extract_normal_dialogue_minus5_reachability(data)
    write_csv(args.out / "normal_dialogue_minus5_reachability.csv", list(minus5_row), [minus5_row])

    dialogue_audio_rows = extract_dialogue_audio_latch_semantics(data)
    write_csv(args.out / "dialogue_audio_latch_semantics.csv",
              ["phase","latch","value_before","trigger","sound","value_after","evidence","confidence"],
              dialogue_audio_rows)

    state4_rows = extract_state4_collection_selector(data)
    write_csv(args.out / "state4_collection_progression.csv",
              ["progress_index","dialogue_script","script_role","selector_global","selector_dispatch",
               "completion_behavior","confidence"], state4_rows)

    state3_field_row = extract_npc_state3_field_usage(data)
    write_csv(args.out / "npc_state3_field_usage.csv", list(state3_field_row), [state3_field_row])

    identity_rows = extract_story_entity_identities()
    write_csv(args.out / "story_entity_identities.csv",
              ["index","identity","semantic_role","identity_confidence","role_confidence","evidence"], identity_rows)

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

    interaction_response_rng_row = extract_player_interaction_response_rng(data)
    write_csv(args.out / "player_interaction_response_rng.csv", list(interaction_response_rng_row),
              [interaction_response_rng_row])

    interaction_state2_cursor_row = extract_player_interaction_state2_cursor(data)
    write_csv(args.out / "player_interaction_state2_cursor.csv", list(interaction_state2_cursor_row),
              [interaction_state2_cursor_row])

    interaction_runtime_dispatch_rows = extract_player_interaction_runtime_dispatch(data)
    write_csv(args.out / "player_interaction_runtime_dispatch.csv",
              ["action_index","action_label","page_base","quadrant","runtime_path","dispatcher",
               "dispatch_key","page_base_consulted","shared_flag_offset","reconstruction_warning","confidence"],
              interaction_runtime_dispatch_rows)

    interaction_leaf_commit_rows = extract_player_interaction_leaf_commit_semantics(data)
    write_csv(args.out / "player_interaction_leaf_commit_semantics.csv",
              ["action_index","action_label","page_base","quadrant","topic_count","fresh_a_gate",
               "fresh_a_outcome","post_countdown_path","runtime_class","b_return","evidence","confidence"],
              interaction_leaf_commit_rows)

    interaction_followup_refs = extract_player_interaction_followup_flag_references(data)
    write_csv(args.out / "player_interaction_followup_flag_references.csv",
              ["address","field","access","source","leaf_discriminator","confidence"],
              interaction_followup_refs)

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

    controller_mode_rows = extract_player_controller_modes(data)
    write_csv(args.out / "player_controller_modes.csv",
              ["mode","level_guard","entry","behavior","next_mode","mode_global",
               "mode_global_literal_refs","evidence","confidence"], controller_mode_rows)

    ending_copy_rows = extract_ending_vram_effect_copy_model(data)
    write_csv(args.out / "ending_vram_effect_copy_model.csv",
              ["copy","function","destination","source_bias","bytes_per_step","argument_bias",
               "size_formula","size_at_argument_0","copy_helper","scene_manager","confidence"],
              ending_copy_rows)

    ending_flag_row = extract_ending_event_flag_runtime(data)
    write_csv(args.out / "ending_event_flag_runtime.csv",
              list(ending_flag_row), [ending_flag_row])

    ending_runtime_rows = extract_ending_vram_effect_runtime(data)
    write_csv(args.out / "ending_vram_effect_runtime.csv",
              ["phase","handler","condition","argument_state","argument_update","event_flag",
               "event_flag_required","effect_function","effect_call","argument_before_call",
               "reachable_from_normal_boot","unreachable_reason","confidence"],
              ending_runtime_rows)

    ending_write_rows = extract_ending_effect_argument_writes(data)
    write_csv(args.out / "ending_effect_argument_writes.csv",
              ["store_address","global_base","field_offset","field_address","write","guard","confidence"],
              ending_write_rows)

    ending_alias_rows = extract_ending_effect_alias_write_closure(data)
    write_csv(args.out / "ending_effect_alias_write_closure.csv",
              ["target_name","target_address","exact_literal_occurrences",
               "candidate_literal_load_roots","write_sites","non_player_update_write_sites",
               "largest_proven_written_value_from_zero_seed","non_final_handler_write_sites",
               "closure_result","confidence"], ending_alias_rows)

    ending_boot_row = extract_ending_effect_boot_lifetime(data)
    write_csv(args.out / "ending_effect_boot_lifetime.csv",
              list(ending_boot_row), [ending_boot_row])

    ending_reachability_row = extract_ending_effect_static_reachability(data)
    write_csv(args.out / "ending_effect_static_reachability.csv",
              list(ending_reachability_row), [ending_reachability_row])

    ending_source_rows = extract_ending_vram_effect_level10_sources(data)
    write_csv(args.out / "ending_vram_effect_level10_sources.csv",
              ["level","copy","descriptor_iwram","descriptor_field","descriptor_value","source_bias",
               "effective_source_argument_0","argument_0_bytes","argument_0_end_exclusive",
               "sfx13_overlap_bytes","confidence"], ending_source_rows)

    ending_payload_rows = extract_ending_vram_effect_argument0_payloads(data)
    write_csv(args.out / "ending_vram_effect_argument0_payloads.csv",
              ["copy","reachable_argument","source","destination","byte_length",
               "destination_end_exclusive","vram_limit_exclusive","within_vram","sha256","confidence"],
              ending_payload_rows)

    level9_treetype20_row = extract_level9_treetype20_action(data)
    write_csv(args.out / "level9_treetype20_action.csv",
              list(level9_treetype20_row), [level9_treetype20_row])

    select_counter_row = extract_player_select_counter_closure(data)
    write_csv(args.out / "player_select_counter_closure.csv",
              list(select_counter_row), [select_counter_row])

    shared_mode_row = extract_player_shared_mode_reachability(data)
    write_csv(args.out / "player_shared_mode_reachability.csv",
              list(shared_mode_row), [shared_mode_row])

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
