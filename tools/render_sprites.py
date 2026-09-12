#!/usr/bin/env python3
"""Render Graveblood 0.0.1.1.5.2 OBJ graphics directly from ROM.

The code mirrors the hardware rules proven from 0x0800A8F0 and the dynamic
OBJ uploader at 0x08004F04:
- OBJ graphics are 8bpp (64 bytes per 8x8 logical tile)
- DISPCNT uses 2D OBJ mapping
- logical tile N is encoded to hardware ATTR2 tile index N*2
- logical tile rows in 2D mapping advance by 16 8bpp tiles
- OBJ palette index 0 is transparent
- dynamic animation graphics can be copied from source tiles beyond the
  initial 0x8000-byte upload into slots beginning at logical tile 0x60.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import struct
from PIL import Image, ImageDraw

ROM_BASE = 0x08000000
EXPECTED_SHA256 = "e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b"
OBJ_TILES_SOURCE = 0x08310654
OBJ_PALETTE_SOURCE = 0x08366E58
OBJ_INITIAL_COPY_BYTES = 0x8000
OBJ_TILE_BYTES_8BPP = 64
OBJ_LOGICAL_TILE_COUNT = OBJ_INITIAL_COPY_BYTES // OBJ_TILE_BYTES_8BPP
OBJ_SHAPES = ((8, 8), (8, 16), (16, 8), (16, 16))
INIT_ROM_OFFSET = 0x00A8D738
INIT_RAM_START = 0x03000788
NPC_SOURCE_BIAS_RAM = 0x030007FC
PLAYER_BANK_RAM = 0x0300103C
PLAYER_ANIMATION_STATE_RAM = 0x03001254
PLAYER_ANIMATION_FRAME_RAM = 0x03001258
PLAYER_ANIMATION_COUNTDOWN_RAM = 0x030012A8
PLAYER_ANIMATION_BANK_STRIDE = 192


def obj_source_tile_capacity() -> int:
    """Complete 64-byte source tiles before the code-proven OBJ palette."""
    return (OBJ_PALETTE_SOURCE - OBJ_TILES_SOURCE) // OBJ_TILE_BYTES_8BPP


def decode_obj_tile_arg(tile_arg: int) -> dict[str, int | bool]:
    logical_tile = tile_arg & 0x1FF
    return {
        "logical_tile": logical_tile,
        "hardware_tile": logical_tile << 1,
        "hflip": bool(tile_arg & 0x400),
        "vflip": bool(tile_arg & 0x800),
    }


def obj_dimensions(shape_enum: int) -> tuple[int, int]:
    if not 0 <= shape_enum < len(OBJ_SHAPES):
        raise ValueError(f"invalid Graveblood OBJ shape enum: {shape_enum}")
    return OBJ_SHAPES[shape_enum]


def obj_2d_logical_tile(base_tile: int, tile_x: int, tile_y: int) -> int:
    # Hardware 2D mapping advances one row by 32 32-byte units. An 8bpp tile
    # occupies two such units, so this is 16 logical 64-byte tiles per row.
    return (base_tile + tile_x + tile_y * 16) & 0x1FF


def _rom_off(addr: int, data: bytes) -> int:
    off = addr - ROM_BASE
    if off < 0 or off >= len(data):
        raise ValueError(f"not a ROM pointer: 0x{addr:08X}")
    return off


def _obj_palette(data: bytes) -> list[tuple[int, int, int]]:
    off = _rom_off(OBJ_PALETTE_SOURCE, data)
    raw = struct.unpack_from('<256H', data, off)
    out = []
    for value in raw:
        out.append((
            (value & 0x1F) * 255 // 31,
            ((value >> 5) & 0x1F) * 255 // 31,
            ((value >> 10) & 0x1F) * 255 // 31,
        ))
    return out


def _render_source_tile(data: bytes, source_tile: int, palette=None) -> Image.Image:
    if palette is None:
        palette = _obj_palette(data)
    off = _rom_off(OBJ_TILES_SOURCE, data) + source_tile * OBJ_TILE_BYTES_8BPP
    indices = data[off:off + OBJ_TILE_BYTES_8BPP]
    if len(indices) != OBJ_TILE_BYTES_8BPP:
        raise ValueError(f"OBJ source tile {source_tile} overruns ROM")
    rgba = []
    for pal_index in indices:
        r, g, b = palette[pal_index]
        rgba.append((r, g, b, 0 if pal_index == 0 else 255))
    image = Image.new('RGBA', (8, 8))
    image.putdata(rgba)
    return image


def render_source_tile_atlas(data: bytes, columns: int = 32) -> Image.Image:
    """Render every complete ROM-side OBJ source tile into a compact atlas."""
    if columns <= 0:
        raise ValueError("columns must be positive")
    count = obj_source_tile_capacity()
    rows = (count + columns - 1) // columns
    palette = _obj_palette(data)
    out = Image.new("RGBA", (columns * 8, rows * 8), (0, 0, 0, 0))
    for tile in range(count):
        x = (tile % columns) * 8
        y = (tile // columns) * 8
        out.alpha_composite(_render_source_tile(data, tile, palette), (x, y))
    return out


def render_source_obj_sprite(data: bytes, base_tile: int, shape_enum: int) -> Image.Image:
    """Render a shape directly from the large ROM-side OBJ source sheet.

    Unlike OAM rendering, base_tile here may exceed 0x1FF because the game
    uses 0x08004F04 to pull animation tiles beyond the initial OBJ upload and
    copy them into hardware-visible dynamic slots.
    """
    width, height = obj_dimensions(shape_enum)
    palette = _obj_palette(data)
    out = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    for ty in range(height // 8):
        for tx in range(width // 8):
            source_tile = base_tile + tx + ty * 16
            out.alpha_composite(_render_source_tile(data, source_tile, palette), (tx * 8, ty * 8))
    return out


def copy_source_tiles_to_obj_vram(
    data: bytes,
    obj_vram: bytearray,
    dst_logical_tile: int,
    src_tile: int,
    tile_count: int,
) -> None:
    """Mirror the effective tile copy performed by 0x08004F04."""
    dst = dst_logical_tile * OBJ_TILE_BYTES_8BPP
    src = _rom_off(OBJ_TILES_SOURCE, data) + src_tile * OBJ_TILE_BYTES_8BPP
    size = tile_count * OBJ_TILE_BYTES_8BPP
    if dst < 0 or dst + size > len(obj_vram):
        raise ValueError('dynamic OBJ copy exceeds OBJ VRAM buffer')
    if src < 0 or src + size > len(data):
        raise ValueError('dynamic OBJ copy exceeds ROM source')
    obj_vram[dst:dst + size] = data[src:src + size]


def initial_obj_vram(data: bytes) -> bytearray:
    src = _rom_off(OBJ_TILES_SOURCE, data)
    blob = data[src:src + OBJ_INITIAL_COPY_BYTES]
    if len(blob) != OBJ_INITIAL_COPY_BYTES:
        raise ValueError("initial OBJ upload overruns ROM")
    return bytearray(blob)


def _render_vram_tile(obj_vram: bytes | bytearray, logical_tile: int, palette) -> Image.Image:
    off = logical_tile * OBJ_TILE_BYTES_8BPP
    indices = obj_vram[off:off + OBJ_TILE_BYTES_8BPP]
    if len(indices) != OBJ_TILE_BYTES_8BPP:
        raise ValueError(f"OBJ VRAM tile {logical_tile} out of range")
    image = Image.new("RGBA", (8, 8))
    rgba = []
    for pal_index in indices:
        r, g, b = palette[pal_index]
        rgba.append((r, g, b, 0 if pal_index == 0 else 255))
    image.putdata(rgba)
    return image


def render_obj_vram_sprite(
    data: bytes,
    obj_vram: bytes | bytearray,
    tile_arg: int,
    shape_enum: int,
) -> Image.Image:
    decoded = decode_obj_tile_arg(tile_arg)
    width, height = obj_dimensions(shape_enum)
    palette = _obj_palette(data)
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    base = int(decoded["logical_tile"])
    for ty in range(height // 8):
        for tx in range(width // 8):
            logical_tile = obj_2d_logical_tile(base, tx, ty)
            out.alpha_composite(
                _render_vram_tile(obj_vram, logical_tile, palette),
                (tx * 8, ty * 8),
            )
    if decoded["hflip"]:
        out = out.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if decoded["vflip"]:
        out = out.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return out


def npc_source_bias_from_rom(data: bytes) -> int:
    """Return the initialized value copied to IWRAM 0x030007FC at startup.

    Graveblood's startup data copy maps ROM offset 0xA8D738 to IWRAM
    0x03000788.  NPC draw 0x0800274C reads [0x030007FC] as the base of
    its ROM-side character graphics selection.
    """
    off = INIT_ROM_OFFSET + (NPC_SOURCE_BIAS_RAM - INIT_RAM_START)
    if off < 0 or off + 4 > len(data):
        raise ValueError("NPC source-bias initializer is outside ROM")
    return struct.unpack_from("<I", data, off)[0]


def _initialized_iwram_u32(data: bytes, ram_addr: int) -> int:
    """Read one startup-initialized IWRAM dword from the canonical data copy."""
    off = INIT_ROM_OFFSET + (ram_addr - INIT_RAM_START)
    if off < 0 or off + 4 > len(data):
        raise ValueError(f"IWRAM initializer 0x{ram_addr:08X} is outside ROM")
    return struct.unpack_from("<I", data, off)[0]


def player_animation_initializers_from_rom(data: bytes) -> dict[str, int]:
    """Return the startup values consumed by Player_draw/update animation code.

    These are copied by the normal startup data initializer before the Player
    object is constructed.  The bank is the shared avatar/wardrobe graphics
    bank; state/frame/countdown are the shared animation state used by the
    Player draw/update routines.
    """
    return {
        "bank": _initialized_iwram_u32(data, PLAYER_BANK_RAM),
        "state": _initialized_iwram_u32(data, PLAYER_ANIMATION_STATE_RAM),
        "frame": _initialized_iwram_u32(data, PLAYER_ANIMATION_FRAME_RAM),
        "countdown": _initialized_iwram_u32(data, PLAYER_ANIMATION_COUNTDOWN_RAM),
    }


def player_animation_source_bases(bank: int) -> dict[str, tuple[int, ...]]:
    """Return the exact normal-branch Player source bases for one graphics bank.

    Player_draw uses one six-frame sequence for states 2..6, a second six-frame
    sequence for state 7, and an eight-phase idle for state 8.  The idle has
    only four unique packed poses because phases 5..8 mirror phases 4..1.
    """
    base = bank * PLAYER_ANIMATION_BANK_STRIDE
    regular = tuple(base + 0x240 + 2 * frame for frame in range(6))
    up = tuple(base + 0x280 + 2 * frame for frame in range(6))
    idle_unique = (
        base + 0x24C,
        base + 0x24E,
        base + 0x28C,
        base + 0x28E,
    )
    idle_sequence = (
        idle_unique[0], idle_unique[1], idle_unique[2], idle_unique[3],
        idle_unique[3], idle_unique[2], idle_unique[1], idle_unique[0],
    )
    # Player_draw 0x080067D6 reads Player+0x1E0.  Selector 1 diverts
    # state-8 idle to the contiguous source branch at 0x08006C06, whose
    # row base is bank*192 + 0x200 + 2*(frame-1).
    idle_selector1 = tuple(base + 0x200 + 2 * frame for frame in range(8))
    return {
        "regular_walk": regular,
        "up_walk": up,
        "idle_unique": idle_unique,
        "idle_sequence": idle_sequence,
        "idle_selector1": idle_selector1,
    }


def npc_source_base(shared_source_bias: int, legs_color: int, subtype: int, frame: int) -> int:
    """Mirror the source-tile base math in NPC draw routine 0x0800274C.

    The routine combines the initialized source base at ``[0x030007FC]``,
    actor ``legsColor`` (+0x4E), actor subtype (+0x28), and the 1-based
    animation frame counter (+0x78).
    """
    if frame < 1:
        raise ValueError("NPC animation frame is 1-based")
    return shared_source_bias + legs_color * 8 + subtype + 2 * (frame - 1)


def npc_source_rows(source_base: int) -> tuple[int, int, int, int]:
    """Four 16x8 source rows selected by the NPC dynamic staging loop."""
    return tuple(source_base + row * 16 for row in range(4))


def reconstruct_npc_frame(data: bytes, legs_color: int, subtype: int, frame: int = 1) -> Image.Image:
    """Reconstruct one 16x32 NPC frame using the ROM-initialized source base."""
    source_base = npc_source_base(npc_source_bias_from_rom(data), legs_color, subtype, frame)
    return reconstruct_player_frame_from_source_rows(data, source_base)


def npc_dynamic_logical_rows(slot_a4: int, slot_a8: int, slot_c8: int) -> tuple[int, int, int, int]:
    """Logical OBJ rows targeted by NPC draw before its two 16x16 submits.

    The caller forms ``base = 24*actor[A4] + actor[A8] + actor[C8]`` and
    passes ``(base + {0,8,16,24}) << 6`` to 0x08004F04.  That upload routine
    interprets r0 as a halfword offset from 0x06011800, yielding logical
    8bpp rows ``0x60 + 2*base + {0x00,0x10,0x20,0x30}``.
    """
    base = 24 * slot_a4 + slot_a8 + slot_c8
    logical = 0x60 + 2 * base
    return tuple(logical + row * 16 for row in range(4))


def _record_int(record: dict, key: str, default: int = 0) -> int:
    value = record.get(key, default)
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def story_entity_sprite_rows(data: bytes, records: list[dict]) -> list[dict]:
    """Return exact sprite-source selections for story-controlled runtime-NPC records."""
    bias = npc_source_bias_from_rom(data)
    out = []
    for pos, record in enumerate(records):
        legs = _record_int(record, "legsColor")
        subtype = _record_int(record, "subtype")
        frame = max(1, _record_int(record, "frame", 1))
        source = npc_source_base(bias, legs, subtype, frame)
        rows = npc_source_rows(source)
        out.append({
            "index": _record_int(record, "index", pos),
            "level": record.get("level", ""),
            "state": record.get("state", ""),
            "dial": record.get("dial", ""),
            "legsColor": legs,
            "subtype": subtype,
            "frame": frame,
            "source_bias": bias,
            "source_base": source,
            "source_rows": ";".join(str(value) for value in rows),
            "runtime_class": "npc",
        })
    return out


def render_story_entity_contact_sheet(data: bytes, records: list[dict], columns: int = 8) -> Image.Image:
    """Render standalone story-controlled runtime-NPC records as a labeled sheet.

    This intentionally labels them *entities*: the concrete ``npc`` runtime class
    is reused by non-human interactables (the state-4 sketch/paper records), so
    visual/semantic identity is not inferred solely from the C++ class.
    """
    if columns <= 0:
        raise ValueError("columns must be positive")
    cell_w, cell_h = 80, 72
    rows = max(1, (len(records) + columns - 1) // columns)
    out = Image.new("RGBA", (columns * cell_w, rows * cell_h), (24, 24, 24, 255))
    draw = ImageDraw.Draw(out)
    bias = npc_source_bias_from_rom(data)
    for pos, record in enumerate(records):
        cx = (pos % columns) * cell_w
        cy = (pos // columns) * cell_h
        legs = _record_int(record, "legsColor")
        subtype = _record_int(record, "subtype")
        frame = max(1, _record_int(record, "frame", 1))
        sprite = reconstruct_npc_frame(data, legs, subtype, frame)
        sprite = sprite.resize((32, 64), Image.Resampling.NEAREST)
        out.alpha_composite(sprite, (cx + 2, cy + 4))
        idx = _record_int(record, "index", pos)
        level = record.get("level", "")
        state = record.get("state", "")
        dial = record.get("dial", "")
        source = npc_source_base(bias, legs, subtype, frame)
        draw.text((cx + 36, cy + 4), f"#{idx}", fill=(255, 255, 255, 255))
        draw.text((cx + 36, cy + 16), f"L{level} S{state}", fill=(210, 210, 210, 255))
        draw.text((cx + 36, cy + 28), f"D{dial}", fill=(210, 210, 210, 255))
        draw.text((cx + 36, cy + 40), f"src {source}", fill=(180, 180, 180, 255))
    return out


def reconstruct_player_frame_from_source_rows(data: bytes, source_base: int) -> Image.Image:
    """Reproduce the normal player draw's four-row dynamic OBJ staging.

    0x080065FC fills logical rows 0x60/0x70/0x80/0x90 from four source
    rows separated by 16 logical tiles. It then submits two enum-3 (16x16)
    OAM sprites rooted at 0x60 and 0x80, stacked vertically.
    """
    vram = initial_obj_vram(data)
    for row in range(4):
        copy_source_tiles_to_obj_vram(
            data, vram, 0x60 + row * 16, source_base + row * 16, 2
        )
    top = render_obj_vram_sprite(data, vram, 0x60, 3)
    bottom = render_obj_vram_sprite(data, vram, 0x80, 3)
    out = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
    out.alpha_composite(top, (0, 0))
    out.alpha_composite(bottom, (0, 16))
    return out


MONSTER_RENDER_FLAG_RAM = 0x0300061C
MONSTER_ANIMATION_STATE_RAM = 0x03000570
# Exact tile arguments submitted by Player_draw 0x080068BC when the state-4
# -4 handler has enabled the special monster-render branch.
MONSTER_TILE_ARGS = (0x159, 0x178, 0x17A, 0x198, 0x19A)


def render_state4_monster_composite(data: bytes, animation_counter: int = 24) -> Image.Image:
    """Reconstruct Player_draw's state-4 monster composite from initial OBJ VRAM.

    When [0x0300061C] == 1, Player_draw bypasses normal Vika animation and
    submits five enum-3 (16x16) sprites around the player's X coordinate.
    [0x03000570 + 8] increments up to 24 and supplies their vertical offset.
    The canvas is normalized with player X at 24 so the hardware composition
    can be inspected independently of camera position.
    """
    if not 0 <= animation_counter <= 25:
        raise ValueError("monster animation counter must be in the observed 0..25 range")
    vram = initial_obj_vram(data)
    out = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    positions = (
        (24, animation_counter - 20),
        (16, animation_counter - 4),
        (32, animation_counter - 4),
        (16, animation_counter + 12),
        (32, animation_counter + 12),
    )
    for tile_arg, position in zip(MONSTER_TILE_ARGS, positions):
        sprite = render_obj_vram_sprite(data, vram, tile_arg, 3)
        out.alpha_composite(sprite, position)
    return out


def write_reference_sprite_artifacts(data: bytes, out_dir: Path) -> list[Path]:
    """Write a compact, conservative OBJ evidence set for the RE workspace."""
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"wrong ROM SHA-256: {digest}")
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    atlas_path = out_dir / "obj_source_atlas.png"
    render_source_tile_atlas(data, columns=32).save(atlas_path)
    outputs.append(atlas_path)

    known_path = out_dir / "character_source_2198.png"
    reconstruct_player_frame_from_source_rows(data, 2198).save(known_path)
    outputs.append(known_path)

    candidate_path = out_dir / "player_branch_candidate_3468.png"
    reconstruct_player_frame_from_source_rows(data, 3468).save(candidate_path)
    outputs.append(candidate_path)

    grass_path = out_dir / "grass_logical_tile_0x48.png"
    obj_vram = initial_obj_vram(data)
    render_obj_vram_sprite(data, obj_vram, 0x48, 3).save(grass_path)
    outputs.append(grass_path)

    for leaf_tile in (0x4C, 0x4D, 0x5C, 0x5D):
        leaf_path = out_dir / f"leaf_particle_frame_0x{leaf_tile:02X}.png"
        render_obj_vram_sprite(data, obj_vram, leaf_tile, 0).save(leaf_path)
        outputs.append(leaf_path)

    monster_path = out_dir / "state4_monster_composite.png"
    render_state4_monster_composite(data, animation_counter=24).save(monster_path)
    outputs.append(monster_path)

    source_bytes = OBJ_PALETTE_SOURCE - OBJ_TILES_SOURCE
    summary = {
        "canonical_rom_sha256": digest,
        "obj_tiles_source": f"0x{OBJ_TILES_SOURCE:08X}",
        "obj_palette_source": f"0x{OBJ_PALETTE_SOURCE:08X}",
        "initial_obj_upload_bytes": OBJ_INITIAL_COPY_BYTES,
        "logical_tile_bytes_8bpp": OBJ_TILE_BYTES_8BPP,
        "complete_source_tiles_before_palette": obj_source_tile_capacity(),
        "source_bytes_remainder_before_palette": source_bytes % OBJ_TILE_BYTES_8BPP,
        "character_source_2198_note": "Known-valid Vika-style 16x32 frame sample; not claimed as constructor/default outfit.",
        "player_branch_candidate_3468_note": "Proven selector-0 idle reference: source 3468 is the first frame of the selector-0 idle sequence used on Levels 1, 4, 5, 7, and 8; scene activation copies LevelRecord+0x3C to Player+0x1E0 before the first active update.",
        "grass_tile_note": "Grass_draw 0x08002684 submits logical tile 0x48 as a 16x16 sprite; 2D OBJ rows use 0x48/0x49 and 0x58/0x59.",
        "leaf_particle_frame_tiles": ["0x4C", "0x4D", "0x5C", "0x5D"],
        "leaf_particle_note": "Leaves actor draw is a no-op; Leaves_update 0x08005F80 emits transient 0x0800B2BC particles whose draw method 0x0800AC1C cycles these four 8x8 initial-OBJ tiles.",
        "npc_source_bias_iwram": f"0x{NPC_SOURCE_BIAS_RAM:08X}",
        "npc_source_bias_initialized_value": npc_source_bias_from_rom(data),
        "npc_source_formula": "sourceBias + legsColor*8 + subtype + 2*(frame-1)",
        "npc_semantic_warning": "The npc runtime class is also used for non-human interactive entities; class identity alone must not be used as story identity.",
        "state4_monster_render_flag": f"0x{MONSTER_RENDER_FLAG_RAM:08X}",
        "state4_monster_animation_state": f"0x{MONSTER_ANIMATION_STATE_RAM:08X}",
        "state4_monster_tiles": [f"0x{value:X}" for value in MONSTER_TILE_ARGS],
        "state4_monster_note": "Player_draw 0x080068BC replaces normal player rendering with this five-sprite creature composite when the state-4 -4 handler sets 0x0300061C=1.",
    }
    summary_path = out_dir / "sprite_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    outputs.append(summary_path)
    return outputs
