#!/usr/bin/env python3
"""Initial structural extractor for Graveblood 0.0.1.1.5.2 demo.gba.

This is deliberately ROM-specific. It validates the exact SHA-256 before
extracting the structures established during the first reverse-engineering pass.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, struct
from collections import Counter, defaultdict
from pathlib import Path

EXPECTED_SHA256 = "e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b"
ROM_BASE = 0x08000000
TYPE_KEY_ADDR = 0x08A8C2E0
LEVEL_DESC_OFF = 0x00A8D9C0
LEVEL_COUNT = 11
LEVEL_DESC_SIZE = 0x40
STANDALONE_SPAWNER_START = 0x00018E94
STANDALONE_SPAWNER_COUNT = 16
DIALOGUE_PTR_SOURCE_OFF = 0x00A8D73C
DIALOGUE_RECORD_SIZE = 0x90
DIALOGUE_SPEAKER_SIZE = 0x1B
DIALOGUE_TEXT_END = 0x88
INIT_ROM_START = 0x00A8D738
INIT_RAM_START = 0x03000788

# Runtime dimensions are patched by the static constructor at 0x0800DBF4.
# The fixed render map is 64x32 for every normal level except level 6, which
# is a compact 30x20 special structure.
FIXED_TILEMAP_DIMS = [(64, 32)] * 6 + [(30, 20)] + [(64, 32)] * 4

ACTOR_RUNTIME_FIELDS = [
    # property, runtime offset, storage, parser default, transform, evidence
    ("x", 0x08, "s32", 100, "value << 8", "0x08004414 -> str [actor+0x08]"),
    ("y", 0x0C, "s32", 100, "value << 8", "0x08004438 -> str [actor+0x0C]"),
    ("turn", 0x4C, "s16", 0, "identity", "0x08004460 -> strh [actor+0x4C]"),
    ("subtype", 0x28, "s32", 0, "identity", "0x08004492 -> str [actor+0x28]"),
    ("treetype", 0x54, "s16", 1, "identity", "0x080044BC -> strh [actor+0x54]"),
    ("legsColor", 0x4E, "s16", 0, "identity", "0x080044EC -> strh [actor+0x4E]"),
    ("num", 0x50, "s16", 150, "identity", "0x0800451A -> strh [actor+0x50]"),
    ("portTo", 0x52, "s16", 33, "identity", "0x08004548 -> strh [actor+0x52]"),
    ("level", 0x56, "s16", -1, "identity", "0x08004578 -> strh [actor+0x56]"),
    ("setglobal", 0x58, "s16", 1, "identity", "0x080045A8 -> strh [actor+0x58]"),
    ("state", 0x5A, "s16", 0, "identity", "0x080045D6 -> strh [actor+0x5A]"),
    ("dial", 0x5C, "s32", 0, "identity", "0x080045FE -> str [actor+0x5C]"),
    ("route", 0x64, "s32", 0, "identity", "0x0800462A -> str [actor+0x64]"),
]

KNOWN_FUNCTIONS = [
    (0x08000384, "actor_property_int_lookup_candidate", "repeatedly parses named integer actor properties with caller-supplied defaults"),
    (0x080000C0, "rom_entry_target", "ARM reset-vector target"),
    (0x080000E0, "crt_start_arm", "early runtime/stack setup"),
    (0x08000108, "crt_start_thumb", "runtime startup after ARM->Thumb switch"),
    (0x080010A4, "actor_list_loader_candidate", "0x08005950 calls it for the selected story-overlay list and again for LevelRecord+0x38 physical actors"),
    (0x08002268, "irq_handler_candidate", "installed at 0x03007FFC; VBlank/IRQ dispatch candidate"),
    (0x0800274C, "NPC_draw", "vtable 0x08018B00 draw method; stages four dynamic 16x8 source rows and submits two 16x16 OAM sprites"),
    (0x08002914, "grass_factory", "spawnType=grass registry target; allocates 0x6C-byte grass/leaves object"),
    (0x0800298C, "npc_dialogue_actor_update_candidate", "dispatches actor state modes and consumes dial-indexed 0x90-byte dialogue records"),
    (0x08003998, "NPC_constructor", "called by NPC factory to initialize 0xFC-byte NPC/interactive-entity object"),
    (0x08003A60, "NPC_factory", "spawnType=npc registry target; allocates 0xFC bytes and calls 0x08003998"),
    (0x08003AEC, "fgtile_factory", "spawnType=fgtile registry target; allocates 0x90-byte foreground-tile object"),
    (0x080037F6, "state4_final_collection_handler", "state-4 opcode -5 handler; calls 0x08004FE0, plays SFX 13, sets 0x03000678=1, increments collection index, consumes pickup and clears dialogue"),
    (0x08003B98, "Fgtile_update", "foreground-tile update; turn=4/5 switches after collection index 3->4 to a fresh-A forced vertical gate action; generic portTo -> request_scene block remains separate at 0x08004258"),
    (0x080043AC, "actor_level_global_policy_candidate", "level mismatch invokes actor virtual method; setglobal==0 sets inherited actor+0x31 culling-bypass flag"),
    (0x080043F8, "actor_common_property_parse_candidate", "maps named actor properties into runtime object fields"),
    (0x08004670, "apply_actor_motion_with_tile_collision_candidate", "reads actor +0x18/+0x1C requested displacement, collision-tests the world tile grid, and applies permitted components to +0x08/+0x0C"),
    (0x08004A74, "TitleScene_exit", "no-op exit (bx lr)"),
    (0x08004F04, "dynamic_obj_tile_upload", "copies ROM-side 8bpp animation tiles into hardware-visible OBJ VRAM working slots"),
    (0x08004FE0, "ending_vram_effect_candidate", "called by state-4 final-sketch opcode -5 handler and repeated while ending event flag is active; copies 1500*(arg+64) bytes to 0x06000000 and 250*(arg+64) bytes to 0x06010000"),
    (0x08004A78, "TitleScene_update", "PRESS START input and delayed scene transition"),
    (0x08004B74, "GameplayScene_update", "active gameplay scene update"),
    (0x08004C10, "GameplayScene_exit", "gameplay scene exit"),
    (0x08005914, "TitleScene_enter", "title scene enter/init"),
    (0x0800575C, "upload_level_graphics_resources", "level+0x24 graphics descriptor: BG/OBJ tile uploads, palettes, translation-table pointer"),
    (0x080057DC, "upload_fixed_tilemap", "translates level+0x1C tile IDs through 0x03000560 into BG screenblocks"),
    (0x08005720, "normal_dialogue_record_action_candidate", "normal dialogue generic record-action fallback calls this with record argument; state-4 -5 uses separate handler"),
    (0x08005950, "load_level_record_resources", "consumes selected 0x40-byte runtime level record and loads graphics, fixed map, streaming layers and actors"),
    (0x08005A2C, "GameplayScene_enter", "loads level id; selects record at 0x03000A10 + id*0x40"),
    (0x08005BEC, "set_level_graphics_variant", "stores selector at scene-manager+0x1C, loads descriptor from current level record +0x24+selector*4, then reloads graphics/fixed/streamed layers"),
    (0x08005C54, "set_level_graphics_variant_from_state_index", "looks up a selector at 0x03000858 + index*4 and forwards it to 0x08005BEC; only direct call recovered at 0x08003F18"),
    (0x0800A330, "stream_world_tile_layers_region", "streams translated cells from visual world layers A/B into BG tilemap buffers"),
    (0x0800A400, "update_streamed_world_tilemaps_on_scroll", "updates streamed tilemap window as camera/scroll position changes"),
    (0x0800DBF4, "static_level_runtime_initializer", "patches runtime level-record dimensions and other static initialized fields; dimension patch segment at 0x0800DD74"),
    (0x08005C30, "request_scene", "queues pending scene + args + delay"),
    (0x08005CB0, "scene_manager_update", "transition/enter/exit/update virtual dispatch"),
    (0x08005ED8, "bx_r3_trampoline", "interworking/indirect-call trampoline"),
    (0x0800621C, "Player_constructor", "player factory constructor; initializes sprite stride and copies 10x20-byte wardrobe label table to object+0x2B4"),
    (0x08006418, "Player_factory", "registered player actor factory; allocates/constructs Player object"),
    (0x08006430, "Wardrobe_draw_selected_label", "standalone helper used by Player_update Wardrobe path; draws label at Player+0x2B4 + Player+0x240*20"),
    (0x080065FC, "Player_draw", "stages dynamic 8bpp OBJ rows and submits stacked hardware sprites for the player"),
    (0x080068BC, "Player_draw_state4_monster_branch", "entered when 0x0300061C==1; submits five 16x16 OBJ sprites forming reconstructed dark creature composite"),
    (0x080080A4, "Player_apply_vertical_target_delta", "reads Player+0x394 interaction Y, stores targetY-currentY at +0x1C, then clears dual-purpose fields +0x390/+0x394"),
    (0x080081B0, "Player_update", "Player vtable update method at 0x08019694; dispatches 0x03000610 interaction-active state through Player+0x1EC"),
    (0x08005EDA, "bx_r5_trampoline", "interworking/indirect-call trampoline"),
    (0x08006D6C, "message_selector_slot_copy_candidate", "selects one of four message selector slots for Messages UI"),
    (0x0800A208, "configure_gameplay_backgrounds", "programs BG0..BG3 as 8bpp text backgrounds at screenblocks 27..30 with priorities 0..3"),
    (0x0800A8F0, "submit_obj_oam", "writes OAM entry from screen position, logical 8bpp tile, Graveblood size enum, flips and priority"),
    (0x0800D968, "register_spawn_factories_npc_grass", "binds literal spawnType keys npc/grass to concrete factory callbacks"),
    (0x0800DBB4, "register_spawn_factory_fgtile", "binds literal spawnType key fgtile to 0x08003AEC"),
    (0x0800D870, "main", "VBlank-synchronized main loop; reads KEYINPUT and updates scene manager"),
    (0x0801061C, "cpp_runtime_init_candidate", "startup-time runtime/global-constructor-style initializer; alpha homolog at 0x08008B20"),
]

KNOWN_GLOBALS = [
    (0x03000548, "world_grid_width_tiles", "level+0x00; used in collision/world-layer indexing"),
    (0x0300054C, "world_grid_height_tiles", "level+0x04; paired with world width"),
    (0x03000550, "collision_grid_ptr", "level+0x0C; u16 world collision grid"),
    (0x0300055C, "tile_translation_index_base", "level+0x20; values 0x40/0x3E0 and consumed by streamed renderer"),
    (0x03000560, "tile_translation_table_ptr", "graphics descriptor +0x08; translates source tile IDs before VRAM upload"),
    (0x03000564, "visual_world_layer_b_ptr", "level+0x10; second streamed u16 world tile layer"),
    (0x03000568, "visual_world_layer_a_ptr", "level+0x08; first streamed u16 world tile layer"),
    (0x03000554, "frame_counter", "incremented once per VBlank/main-loop iteration"),
    (0x03000574, "npc_spatial_query_scratch_candidate", "used by NPC state 1/2/4 proximity/collision queries; not the route table"),
    (0x030005BC, "scene_manager", "pending/active scene state"),
    (0x030005C4, "scene_transition_delay", "scene_manager +0x08"),
    (0x030005C8, "pending_scene", "scene_manager +0x0C"),
    (0x030005F8, "active_scene", "scene_manager +0x3C"),
    (0x03000610, "player_interaction_active_flag", "NPC fresh-A handler sets to 1 at 0x08002FF2 after copying dial/X/Y into Player; Player_update gates +0x1EC interaction dispatch at 0x08008BC8 and clears it at 0x0800965C"),
    (0x0300061C, "state4_monster_render_flag", "state-4 opcode -4 sets to 1; Player_draw branches to 0x080068BC when value == 1"),
    (0x03000620, "state4_collection_progress_index", "state-4 branch indexes six-entry selector with this value; completed pickups increment it; Fgtile_update gates behavior at >3"),
    (0x03000674, "ending_effect_progress_counter_candidate", "incremented while opcode -5 event flag is active and fed to 0x08004FE0"),
    (0x03000678, "ending_event_active_flag", "set to 1 by state-4 final-sketch opcode -5 handler 0x080037F6; monitored by gameplay update"),
    (0x030006AC, "story_progression_stage", "written by normal-context dialogue opcode -4; consumed as stage index by Messages UI; state-4 pickup -4 does not write it"),
    (0x030006BC, "keys_current", "inverted KEYINPUT mask"),
    (0x030006C0, "keys_previous", "previous frame key mask"),
    (0x030007FC, "npc_obj_source_base_initialized", "initialized to 0xE00 from ROM 0x08A8D7AC; NPC draw reads it as ROM-side OBJ source-bank base"),
    (0x0300078C, "dialogue_script_pointer_table", "initialized from ROM 0xA8D73C; indexed by actor dial at 0x08002DF2"),
    (0x03000808, "level_id_or_transition_arg", "set to 7 on title Start; consumed by gameplay enter"),
    (0x0300083C, "story_entity_overlay_list_slot0", "startup-initialized to 0x08018E94; selected by level loader before physical level actors"),
    (0x03000840, "story_entity_overlay_list_slot1", "startup-initialized to 0x08018E94; second selector slot, identical in this demo"),
    (0x0300080C, "GameplayScene_object", "vtable 0x08018E88"),
    (0x03000A0C, "TitleScene_object", "vtable 0x08018E74"),
    (0x030005D4, "current_level_record_ptr", "scene-manager base+0x18; set by 0x08005950"),
    (0x030005D8, "level_graphics_variant_selector", "scene-manager base+0x1C; initialized to 0 by level loader and written by 0x08005BEC"),
    (0x03000A10, "level_runtime_record_array", "11 records, 0x40-byte stride; GameplayScene_enter indexes by level id"),
    (0x030014EC, "message_stream_pointer_table", "three initialized message-stream pointers; indexed after selecting a message slot"),
    (0x03001808, "message_selector_aux3", "third auxiliary selector; initialized -1; filled by opcode -3 first-free policy"),
    (0x0300180C, "message_selector_aux2", "second auxiliary selector; initialized -1; filled by opcode -3 first-free policy"),
    (0x03001810, "message_selector_aux1", "first auxiliary selector; initialized -1; filled by opcode -3 first-free policy"),
    (0x03001814, "message_selector_primary", "primary selector; initialized -1; set by dialogue opcode -2"),
    (0x03001818, "npc_route_pointer_table", "five route pointers; state==3 indexes this table with actor.route"),
    (0x0300103C, "player_live_graphics_bank", "initialized to 15; Player_draw uses it as the live ROM-side graphics-bank selector; no Wardrobe mutation recovered in the public demo"),
    (0x03001254, "player_animation_state_block", "Player animation state at +0 and frame at +4; direct xrefs are Player draw/update animation paths, not Wardrobe state"),
    (0x03007FFC, "irq_callback_slot", "startup/main installs 0x08002268 here"),
]

FOCUS_TERMS = [
    "PRESS START", "THERE IS NO PLAYER", "Not for demo", "KISS CHEEK", "KISS LIPS",
    "MESSAGES", "FROM:", "No new messages", "STATUS", "FRIENDS", "BACKPACK", "Wardrobe",
    "Go meet IQ", "Find sketches", "Katya", "IQ 54", "Vika", "Favorite Skirt",
    "UNKNOWN ACTOR TYPE", "spawnType", "spawner", "fgtile", "portTo", "setglobal", "dial",
]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def init_ram_to_rom_off(addr: int) -> int:
    if addr < INIT_RAM_START:
        raise ValueError(f"not in initialized IWRAM block: 0x{addr:08X}")
    return INIT_ROM_START + (addr - INIT_RAM_START)


def reconstruct_level_dimensions(data: bytes):
    """Recover runtime dimensions patched by the constructor at 0x0800DBF4.

    For levels other than the special level 6, the world-grid metadata is the
    two dwords immediately preceding visual layer A: height, then width. Level 6
    stores its 20x30 metadata after the compact 600-cell block instead. Fixed
    tilemap dimensions are independently confirmed by the constructor.
    """
    dims = []
    for i in range(LEVEL_COUNT):
        vals = struct.unpack_from("<16I", data, LEVEL_DESC_OFF + i * LEVEL_DESC_SIZE)
        visual_a = vals[0x08 // 4]
        if i == 6:
            world_w, world_h = 30, 20
            meta_off = gba_to_off(0x08656624, len(data))
            assert meta_off is not None
            assert struct.unpack_from("<II", data, meta_off) == (20, 30)
        else:
            voff = gba_to_off(visual_a, len(data))
            assert voff is not None and voff >= 8
            world_h, world_w = struct.unpack_from("<II", data, voff - 8)
        fixed_w, fixed_h = FIXED_TILEMAP_DIMS[i]
        fixed_ptr = vals[0x1C // 4]
        foff = gba_to_off(fixed_ptr, len(data))
        assert foff is not None
        end_meta = foff + fixed_w * fixed_h * 2
        assert struct.unpack_from("<II", data, end_meta) == (fixed_h, fixed_w)
        dims.append((world_w, world_h, fixed_w, fixed_h))
    return dims


def level_graphics_variant_ptrs(level_words):
    """Return contiguous graphics descriptor pointers from +0x24..+0x34.

    0x08005BEC indexes the current 0x40-byte level record as
    *(record + 0x24 + selector*4).  In the recovered records, valid descriptor
    slots are contiguous and terminate at the first zero before +0x38, which is
    the actor-list pointer.
    """
    out = []
    for byte_off in range(0x24, 0x38, 4):
        ptr = level_words[byte_off // 4]
        if ptr == 0:
            break
        out.append(ptr)
    return out


def parse_graphics_descriptor(data: bytes, iwram_addr: int):
    """Decode the 0x24-byte graphics descriptor referenced by level +0x24."""
    off = init_ram_to_rom_off(iwram_addr)
    vals = struct.unpack_from("<9I", data, off)
    return {
        "descriptor_iwram_addr": iwram_addr,
        "descriptor_source_rom_offset": off,
        "bg_tiles_source": vals[0x00 // 4],
        "field_04": vals[0x04 // 4],
        "tile_translation_table": vals[0x08 // 4],
        "bg_palette_source": vals[0x0C // 4],
        "bg_palette_halfwords": vals[0x10 // 4],
        "obj_tiles_source": vals[0x14 // 4],
        "field_18": vals[0x18 // 4],
        "obj_palette_source": vals[0x1C // 4],
        "obj_palette_halfwords": vals[0x20 // 4],
    }


def layer_summary(data: bytes, addr: int, cells: int):
    off = gba_to_off(addr, len(data))
    if off is None:
        raise ValueError(f"not a ROM layer pointer: 0x{addr:08X}")
    blob = data[off:off + cells * 2]
    if len(blob) != cells * 2:
        raise ValueError(f"layer overruns ROM: 0x{addr:08X}")
    values = struct.unpack_from(f"<{cells}H", blob) if cells else ()
    counts = Counter(values)
    return {
        "sha256": hashlib.sha256(blob).hexdigest(),
        "unique_values": len(counts),
        "zero_cells": counts.get(0, 0),
        "value14_cells": counts.get(14, 0),
        "min_value": min(values) if values else 0,
        "max_value": max(values) if values else 0,
    }


def gba_to_off(addr: int, n: int) -> int | None:
    if ROM_BASE <= addr < ROM_BASE + n:
        return addr - ROM_BASE
    return None


def cstr(data: bytes, addr: int, max_len: int = 512) -> str | None:
    off = gba_to_off(addr, len(data))
    if off is None:
        return None
    end = data.find(b"\0", off, min(len(data), off + max_len))
    if end < 0:
        return None
    raw = data[off:end]
    if not raw:
        return ""
    try:
        s = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    if any(ord(ch) < 0x20 and ch not in "\t\r\n" for ch in s):
        return None
    return s


def parse_actor(data: bytes, off: int):
    if u32(data, off) != TYPE_KEY_ADDR:
        return None
    props = []
    p = off
    # actor is key_ptr,value_ptr pairs terminated by a zero dword
    for _ in range(64):
        key_addr = u32(data, p)
        if key_addr == 0:
            return props, p + 4
        val_addr = u32(data, p + 4)
        key = cstr(data, key_addr)
        val = cstr(data, val_addr)
        if key is None or val is None:
            return None
        props.append((key, val, key_addr, val_addr))
        p += 8
    return None


def actor_dict(props):
    d = {}
    for k, v, _, _ in props:
        # retain first occurrence as the user-facing semantic value
        d.setdefault(k, v)
    return d


def fixed_cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace")


def dialogue_opcode_interpretation(opcode: int) -> str:
    """Return the *normal dialogue context* interpretation used in dialogue_scripts.csv.

    State-4 pickups reuse the same 0x90-byte record format but have their own
    dispatcher, so -4/-5 must not be universalized here.  The authoritative
    context matrix is exported by extract_extended_semantics.py.
    """
    semantics = {
        0: "normal context: dialogue/content record; argument consumed by generic handler",
        -1: "normal context: set actor dialogue-step (+0x70) to argument",
        -2: "normal context: set primary message-stream selector 0x03001814 to argument",
        -3: "normal context: insert argument into first free auxiliary selector: 0x03001810/0x0300180C/0x03001808",
        -4: "normal context: set story/progression stage 0x030006AC to argument; state-4 pickup context overrides this opcode",
        -5: "normal context: generic record-action fallback calls 0x08005720(argument); state-4 pickup context overrides this opcode",
    }
    return semantics.get(opcode, "unclassified")


def dialogue_pointer_groups(data: bytes):
    """Parse ROM-pointer groups at the initialized dialogue-table source.

    The first zero-terminated group is the table indexed by actor.dial. Nearby
    groups are retained only to derive physical bounds for the first group.
    """
    groups, cur = [], []
    for i in range(64):
        v = u32(data, DIALOGUE_PTR_SOURCE_OFF + i * 4)
        if ROM_BASE <= v < ROM_BASE + len(data):
            cur.append(v)
            continue
        if v == 0 and cur:
            groups.append(cur)
            cur = []
            continue
        if groups:
            break
    if cur:
        groups.append(cur)
    return groups


def walk_actor_table(data: bytes, off: int):
    rows = []
    p = off
    while p + 8 <= len(data) and u32(data, p) == TYPE_KEY_ADDR:
        parsed = parse_actor(data, p)
        if not parsed:
            break
        props, end = parsed
        rows.append((p, props))
        p = end
    return rows


def scan_all_actor_records(data: bytes):
    records = []
    needle = struct.pack("<I", TYPE_KEY_ADDR)
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            break
        if pos % 4 == 0:
            parsed = parse_actor(data, pos)
            if parsed:
                records.append((pos, parsed[0]))
        start = pos + 1
    # record starts are unique because only valid key/value series survive parse
    uniq = {}
    for off, props in records:
        uniq[off] = props
    return sorted(uniq.items())


def header_info(data: bytes):
    chk = (-0x19 - sum(data[0xA0:0xBD])) & 0xFF
    return {
        "rom_size": len(data),
        "rom_size_hex": f"0x{len(data):X}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "entry_bytes": data[0:4].hex(),
        "title_raw_hex": data[0xA0:0xAC].hex(),
        "game_code_raw_hex": data[0xAC:0xB0].hex(),
        "maker": data[0xB0:0xB2].decode("ascii", errors="replace"),
        "fixed_value": data[0xB2],
        "unit_code": data[0xB3],
        "device_type": data[0xB4],
        "version": data[0xBC],
        "header_checksum_stored": data[0xBD],
        "header_checksum_calculated": chk,
        "header_checksum_valid": data[0xBD] == chk,
    }


def write_csv(path: Path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--allow-other-sha", action="store_true", help="debug only")
    args = ap.parse_args()
    data = args.rom.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != EXPECTED_SHA256 and not args.allow_other_sha:
        raise SystemExit(f"Wrong ROM SHA-256: {sha}\nExpected: {EXPECTED_SHA256}")
    args.out.mkdir(parents=True, exist_ok=True)

    info = header_info(data)
    save_sigs = ["SRAM_", "EEPROM_", "FLASH_", "FLASH512_", "FLASH1M_", "SIIRTC_V"]
    info["standard_save_signatures"] = {sig: data.find(sig.encode("ascii")) for sig in save_sigs}
    (args.out / "rom_info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")

    # Discover every physical actor record first.
    all_records = scan_all_actor_records(data)
    all_by_off = {off: props for off, props in all_records}

    # Parse the true 0x40-byte per-level runtime-record source and map actor
    # records through +0x38. Runtime +0/+4/+14/+18 are zero in this source and
    # patched by the static constructor; reconstruct_level_dimensions() recovers
    # their effective values.
    level_rows = []
    runtime_struct_rows = []
    graphics_rows = []
    graphics_variant_rows = []
    world_layer_rows = []
    collision_rows = []
    record_to_levels = defaultdict(list)
    dimensions = reconstruct_level_dimensions(data)
    for i in range(LEVEL_COUNT):
        doff = LEVEL_DESC_OFF + i * LEVEL_DESC_SIZE
        vals = struct.unpack_from("<16I", data, doff)
        world_w, world_h, fixed_w, fixed_h = dimensions[i]
        actor_addr = vals[0x38 // 4]
        actor_off = actor_addr - ROM_BASE
        actors = walk_actor_table(data, actor_off)
        for aoff, _ in actors:
            record_to_levels[aoff].append(i)
        types = Counter(actor_dict(p).get("type", "?") for _, p in actors)
        player = next((actor_dict(p) for _, p in actors if actor_dict(p).get("type") == "player"), {})
        level_rows.append({
            "level_index": i,
            "record_source_rom_offset": f"0x{doff:08X}",
            "runtime_record_addr": f"0x{0x03000A10 + i*0x40:08X}",
            "world_width_tiles": world_w,
            "world_height_tiles": world_h,
            "fixed_tilemap_width": fixed_w,
            "fixed_tilemap_height": fixed_h,
            "visual_layer_a_addr": f"0x{vals[0x08//4]:08X}",
            "collision_grid_addr": f"0x{vals[0x0C//4]:08X}",
            "visual_layer_b_addr": f"0x{vals[0x10//4]:08X}",
            "fixed_tilemap_addr": f"0x{vals[0x1C//4]:08X}",
            "tile_translation_index_base": f"0x{vals[0x20//4]:X}",
            "graphics_descriptor_iwram": f"0x{vals[0x24//4]:08X}",
            "actor_table_addr": f"0x{actor_addr:08X}",
            "actor_table_rom_offset": f"0x{actor_off:08X}",
            "record_flag_3c": vals[0x3C//4],
            "actor_count": len(actors),
            "player_count": types.get("player", 0),
            "spawner_count": types.get("spawner", 0),
            "fgtile_count": types.get("fgtile", 0),
            "leaves_count": types.get("leaves", 0),
            "player_x": player.get("x", ""),
            "player_y": player.get("y", ""),
            "player_width": player.get("width", ""),
            "player_height": player.get("height", ""),
        })

        runtime_row = {
            "level_index": i,
            "source_rom_offset": f"0x{doff:08X}",
            "runtime_addr": f"0x{0x03000A10+i*0x40:08X}",
            "runtime_world_width_00": world_w,
            "runtime_world_height_04": world_h,
            "runtime_fixed_width_14": fixed_w,
            "runtime_fixed_height_18": fixed_h,
        }
        for wi, val in enumerate(vals):
            runtime_row[f"source_word_{wi*4:02X}"] = f"0x{val:08X}"
        runtime_struct_rows.append(runtime_row)

        variant_ptrs = level_graphics_variant_ptrs(vals)
        for variant_index, descriptor_ptr in enumerate(variant_ptrs):
            vg = parse_graphics_descriptor(data, descriptor_ptr)
            variant_row = {
                "level_index": i,
                "variant_index": variant_index,
                "record_field_offset": f"0x{0x24 + variant_index*4:02X}",
                "descriptor_iwram_addr": f"0x{vg['descriptor_iwram_addr']:08X}",
                "descriptor_source_rom_offset": f"0x{vg['descriptor_source_rom_offset']:08X}",
                "bg_tiles_source": f"0x{vg['bg_tiles_source']:08X}",
                "bg_tiles_copy_bytes": "0xD800",
                "tile_translation_table": f"0x{vg['tile_translation_table']:08X}",
                "bg_palette_source": f"0x{vg['bg_palette_source']:08X}",
                "bg_palette_halfwords": vg["bg_palette_halfwords"],
                "obj_tiles_source": f"0x{vg['obj_tiles_source']:08X}",
                "obj_tiles_copy_bytes": "0x8000",
                "obj_palette_source": f"0x{vg['obj_palette_source']:08X}",
                "obj_palette_halfwords": vg["obj_palette_halfwords"],
                "field_04": f"0x{vg['field_04']:08X}",
                "field_18": f"0x{vg['field_18']:08X}",
            }
            graphics_variant_rows.append(variant_row)
            if variant_index == 0:
                graphics_rows.append({k: v for k, v in variant_row.items() if k not in ("variant_index", "record_field_offset")})

        world_cells = world_w * world_h
        fixed_cells = fixed_w * fixed_h
        layer_defs = [
            ("visual_A", vals[0x08//4], world_cells),
            ("collision", vals[0x0C//4], world_cells),
            ("visual_B", vals[0x10//4], world_cells),
            ("fixed_tilemap", vals[0x1C//4], fixed_cells),
        ]
        for role, addr, cells in layer_defs:
            stats = layer_summary(data, addr, cells)
            world_layer_rows.append({
                "level_index": i, "role": role, "rom_addr": f"0x{addr:08X}",
                "rom_offset": f"0x{addr-ROM_BASE:08X}", "width": fixed_w if role == "fixed_tilemap" else world_w,
                "height": fixed_h if role == "fixed_tilemap" else world_h, "cells": cells,
                **stats,
            })
        cstats = layer_summary(data, vals[0x0C//4], world_cells)
        collision_rows.append({
            "level_index": i, "width": world_w, "height": world_h, "cells": world_cells,
            "collision_addr": f"0x{vals[0x0C//4]:08X}", **cstats,
            "structure_note": "level 6 shares +0x0C and +0x10; treat collision role as special-case pending deeper trace" if i == 6 else "",
        })

    write_csv(args.out / "levels.csv", list(level_rows[0]), level_rows)
    write_csv(args.out / "level_runtime_structs.csv", list(runtime_struct_rows[0]), runtime_struct_rows)
    write_csv(args.out / "level_graphics_descriptors.csv", list(graphics_rows[0]), graphics_rows)
    write_csv(args.out / "level_graphics_variants.csv", list(graphics_variant_rows[0]), graphics_variant_rows)
    write_csv(args.out / "level_world_layers.csv", list(world_layer_rows[0]), world_layer_rows)
    write_csv(args.out / "collision_summary.csv", list(collision_rows[0]), collision_rows)

    raw_desc_rows = []
    for i in range(LEVEL_COUNT):
        doff = LEVEL_DESC_OFF + i * LEVEL_DESC_SIZE
        vals = struct.unpack_from("<16I", data, doff)
        row = {"level_index": i, "record_source_rom_offset": f"0x{doff:08X}"}
        for wi, val in enumerate(vals):
            row[f"word_{wi*4:02X}"] = f"0x{val:08X}"
        raw_desc_rows.append(row)
    write_csv(args.out / "level_descriptors_raw.csv", list(raw_desc_rows[0]), raw_desc_rows)

    # Flatten actor records into one row each, preserving semantic properties.
    actor_fields = [
        "rom_offset", "rom_addr", "normal_level_indices", "classification",
        "type", "name", "x", "y", "width", "height", "spawnType", "subtype", "treetype",
        "legsColor", "num", "portTo", "level", "setglobal", "state", "route", "dial", "turn",
        "all_properties_json",
    ]
    actor_rows = []
    for off, props in all_records:
        d = actor_dict(props)
        levels = record_to_levels.get(off, [])
        if levels:
            cls = "level_descriptor_table"
        elif STANDALONE_SPAWNER_START <= off < 0x00019700:
            cls = "standalone_spawner_metadata"
        else:
            cls = "unassigned"
        row = {
            "rom_offset": f"0x{off:08X}",
            "rom_addr": f"0x{ROM_BASE+off:08X}",
            "normal_level_indices": ";".join(map(str, levels)),
            "classification": cls,
            "all_properties_json": json.dumps({k:v for k,v,_,_ in props}, ensure_ascii=False),
        }
        for k in actor_fields[4:-1]:
            row[k] = d.get(k, "")
        actor_rows.append(row)
    write_csv(args.out / "actors.csv", actor_fields, actor_rows)

    # Runtime property layout recovered from the parser at 0x080043F8.
    runtime_field_rows = [{
        "property": prop,
        "runtime_offset": f"0x{off:02X}",
        "storage": storage,
        "parser_default": default,
        "transform": transform,
        "evidence": evidence,
    } for prop, off, storage, default, transform, evidence in ACTOR_RUNTIME_FIELDS]
    write_csv(args.out / "actor_runtime_fields.csv", list(runtime_field_rows[0]), runtime_field_rows)

    # Proven level-transition edges: 0x08004258 loads actor+0x52 (portTo)
    # and passes it as request_scene(GameplayScene, level, 0, 10).
    portal_rows = []
    for row in actor_rows:
        if row["type"] != "fgtile" or row["portTo"] == "":
            continue
        try:
            dest = int(row["portTo"], 0)
        except ValueError:
            continue
        for source_s in row["normal_level_indices"].split(";"):
            if not source_s:
                continue
            source = int(source_s)
            portal_rows.append({
                "source_level": source,
                "destination": dest,
                "destination_kind": "level" if 0 <= dest < LEVEL_COUNT else "special_or_out_of_range",
                "actor_rom_offset": row["rom_offset"],
                "x": row["x"],
                "y": row["y"],
                "num": row["num"],
                "turn": row["turn"],
            })
    portal_rows.sort(key=lambda r: (r["source_level"], r["destination"], r["actor_rom_offset"]))
    write_csv(args.out / "portal_edges.csv", [
        "source_level", "destination", "destination_kind", "actor_rom_offset", "x", "y", "num", "turn"
    ], portal_rows)

    # Dialogue scripts selected by actor.dial. The first pointer group at the
    # source table contains seven scripts. Every record is 0x90 bytes:
    # speaker[0x1B], text[0x6D], s32 opcode, s32 argument.
    dgroups = dialogue_pointer_groups(data)
    dial_ptrs = dgroups[0] if dgroups else []
    all_nearby_ptrs = sorted({p for g in dgroups for p in g})
    dialogue_rows = []
    dialogue_table_rows = []
    for dial, ptr in enumerate(dial_ptrs):
        higher = [p for p in all_nearby_ptrs if p > ptr]
        if not higher:
            continue
        end = min(higher)
        count = (end - ptr) // DIALOGUE_RECORD_SIZE
        dialogue_table_rows.append({
            "dial_index": dial, "script_addr": f"0x{ptr:08X}",
            "script_rom_offset": f"0x{ptr-ROM_BASE:08X}",
            "record_count": count, "physical_end_addr": f"0x{end:08X}",
        })
        for step in range(count):
            off = ptr - ROM_BASE + step * DIALOGUE_RECORD_SIZE
            rec = data[off:off + DIALOGUE_RECORD_SIZE]
            if len(rec) != DIALOGUE_RECORD_SIZE:
                continue
            speaker = fixed_cstr(rec[:DIALOGUE_SPEAKER_SIZE])
            text = fixed_cstr(rec[DIALOGUE_SPEAKER_SIZE:DIALOGUE_TEXT_END])
            opcode = struct.unpack_from("<i", rec, 0x88)[0]
            arg = struct.unpack_from("<i", rec, 0x8C)[0]
            dialogue_rows.append({
                "dial_index": dial, "step": step,
                "record_addr": f"0x{ROM_BASE+off:08X}",
                "record_rom_offset": f"0x{off:08X}",
                "speaker": speaker, "text": text,
                "opcode": opcode, "argument": arg,
                "opcode_interpretation": dialogue_opcode_interpretation(opcode),
            })
    if dialogue_table_rows:
        write_csv(args.out / "dialogue_table.csv", list(dialogue_table_rows[0]), dialogue_table_rows)
    if dialogue_rows:
        write_csv(args.out / "dialogue_scripts.csv", list(dialogue_rows[0]), dialogue_rows)

    # Standalone 16-record spawner table (verified contiguous).
    stand = walk_actor_table(data, STANDALONE_SPAWNER_START)[:STANDALONE_SPAWNER_COUNT]
    stand_rows = []
    for idx, (off, props) in enumerate(stand):
        d = actor_dict(props)
        stand_rows.append({"index": idx, "rom_offset": f"0x{off:08X}", **{k:d.get(k,"") for k in actor_fields[4:-1]}})
    write_csv(args.out / "standalone_spawners.csv", list(stand_rows[0]), stand_rows)

    # Focused useful strings. We only include printable ASCII spans containing known terms.
    found = {}
    i = 0
    while i < len(data):
        if 0x20 <= data[i] <= 0x7E:
            j = i
            while j < len(data) and (0x20 <= data[j] <= 0x7E or data[j] in (9,10,13)):
                j += 1
            if j-i >= 3:
                s = data[i:j].decode("ascii", errors="ignore")
                if any(t.lower() in s.lower() for t in FOCUS_TERMS):
                    found[(i,s)] = None
            i = j + 1
        else:
            i += 1
    focus_rows = [{"rom_offset": f"0x{off:08X}", "rom_addr": f"0x{ROM_BASE+off:08X}", "text": s.replace("\r","\\r").replace("\n","\\n")} for off,s in found]
    write_csv(args.out / "strings_focus.csv", ["rom_offset","rom_addr","text"], focus_rows)

    write_csv(args.out / "known_functions.csv", ["address","name","evidence"], [
        {"address":f"0x{a:08X}","name":n,"evidence":e} for a,n,e in KNOWN_FUNCTIONS])
    write_csv(args.out / "known_globals.csv", ["address","name","evidence"], [
        {"address":f"0x{a:08X}","name":n,"evidence":e} for a,n,e in KNOWN_GLOBALS])
    sym_lines = [f"{a:08X} {n}" for a,n,_ in KNOWN_FUNCTIONS + KNOWN_GLOBALS]
    (args.out / "graveblood_001152.sym").write_text("\n".join(sym_lines) + "\n", encoding="ascii")

    summary = {
        "physical_actor_records": len(all_records),
        "normal_level_descriptors": len(level_rows),
        "normal_level_actor_references_unique": len(record_to_levels),
        "standalone_spawners": len(stand),
        "level_actor_records_unique": len(record_to_levels),
        "unassigned_records": sum(1 for r in actor_rows if r["classification"] == "unassigned"),
        "focused_strings": len(focus_rows),
        "portal_edges": len(portal_rows),
        "dialogue_scripts": len(dialogue_table_rows),
        "dialogue_records": len(dialogue_rows),
    }
    (args.out / "extraction_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
