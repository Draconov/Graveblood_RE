#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import hashlib
import struct
import subprocess
import sys

ROM_BASE = 0x08000000
CANONICAL_SHA256 = 'e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b'
TITLE_DESCRIPTOR_RAM = 0x03000EA4
TITLE_DESCRIPTOR_ROM = 0x08A8DE54
TITLE_BG_TILES_ADDR = 0x08019CC4
TITLE_BG_TILES_BYTES = 0xD800
TITLE_TRANSLATION_ADDR = 0x0802B148
TITLE_PALETTE_ADDR = 0x0802BB0C
TITLE_BG_PALETTE_COUNT_ADDR = 0x0802BCCC
TITLE_BG_PALETTE_COUNT = 0xDF
TITLE_OBJ_TILES_ADDR = 0x08310654
TITLE_OBJ_TILES_BYTES = 0x8000
TITLE_OBJ_PALETTE_ADDR = 0x08366E58
TITLE_OBJ_PALETTE_COUNT_ADDR = 0x08366F10
TITLE_OBJ_PALETTE_COUNT = 0x5B
TITLE_OBJ_HIGH_PALETTE_ADDR = 0x08652DB4
TITLE_OBJ_HIGH_PALETTE_COUNT = 32
TITLE_MAP_ADDR = 0x08655814
TITLE_MAP_WIDTH = 30
TITLE_MAP_HEIGHT = 20
TITLE_ANIM_A_DEST = 0x2F00
TITLE_ANIM_A_BASE = 0xC480
TITLE_ANIM_A_STRIDE = 0xC00
TITLE_ANIM_A_BYTES = 0xC00
TITLE_ANIM_B_DEST = 0x3B00
TITLE_ANIM_B_BASE = 0xF480
TITLE_ANIM_B_STRIDE = 0x800
TITLE_ANIM_B_BYTES = 0x600
TITLE_ANIMATION_STATES = 4
TITLE_PROMPT = b'PRESS START...'
TITLE_PROMPT_X = 9
TITLE_PROMPT_Y = 9
TITLE_TRANSITION_DELAY = 120
TITLE_START_LEVEL = 7


@dataclass(frozen=True)
class TitleAssets:
    bg_tiles: bytes
    palette: tuple[int, ...]
    obj_tiles: bytes
    obj_palette: tuple[int, ...]
    obj_high_palette: tuple[int, ...]
    map_entries: tuple[int, ...]
    underlay_tile: int
    anim_a: tuple[bytes, ...]
    anim_b: tuple[bytes, ...]
    prompt_text: bytes
    prompt_tiles: tuple[int, ...]
    blank_tiles: tuple[int, ...]


def _slice(rom: bytes, addr: int, size: int) -> bytes:
    off = addr - ROM_BASE
    if off < 0 or off + size > len(rom):
        raise ValueError(f'ROM slice out of range: 0x{addr:08X}+0x{size:X}')
    return rom[off:off + size]


def _u16s(rom: bytes, addr: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f'<{count}H', rom, addr - ROM_BASE)


def _u32(rom: bytes, addr: int) -> int:
    return struct.unpack_from('<I', rom, addr - ROM_BASE)[0]


def extract_title_assets(rom: bytes) -> TitleAssets:
    # The ROM copy is a startup template. Runtime-only count fields are patched
    # by the static initializer, so verify both the raw pointers and the
    # initializer constants instead of pretending the zero template counts are
    # the live descriptor.
    descriptor = _slice(rom, TITLE_DESCRIPTOR_ROM, 0x24)
    words = struct.unpack('<9I', descriptor)
    expected = (
        TITLE_BG_TILES_ADDR,
        0,
        TITLE_TRANSLATION_ADDR,
        TITLE_PALETTE_ADDR,
        0,
        TITLE_OBJ_TILES_ADDR,
        0,
        TITLE_OBJ_PALETTE_ADDR,
        0,
    )
    if words != expected:
        raise ValueError(f'title descriptor drifted: {words!r}')

    bg_palette_count = _u32(rom, TITLE_BG_PALETTE_COUNT_ADDR)
    obj_palette_count = _u32(rom, TITLE_OBJ_PALETTE_COUNT_ADDR)
    if bg_palette_count != TITLE_BG_PALETTE_COUNT:
        raise ValueError(f'title BG palette count drifted: {bg_palette_count}')
    if obj_palette_count != TITLE_OBJ_PALETTE_COUNT:
        raise ValueError(f'title OBJ palette count drifted: {obj_palette_count}')

    bg_tiles = _slice(rom, TITLE_BG_TILES_ADDR, TITLE_BG_TILES_BYTES)
    palette = _u16s(rom, TITLE_PALETTE_ADDR, TITLE_BG_PALETTE_COUNT)
    obj_tiles = _slice(rom, TITLE_OBJ_TILES_ADDR, TITLE_OBJ_TILES_BYTES)
    obj_palette = _u16s(rom, TITLE_OBJ_PALETTE_ADDR, TITLE_OBJ_PALETTE_COUNT)
    obj_high_palette = _u16s(rom, TITLE_OBJ_HIGH_PALETTE_ADDR, TITLE_OBJ_HIGH_PALETTE_COUNT)

    raw_map = _u16s(rom, TITLE_MAP_ADDR, TITLE_MAP_WIDTH * TITLE_MAP_HEIGHT)
    max_source = max(max(raw_map), ord('P') + 32, ord(' ') + 32, 2)
    translation = _u16s(rom, TITLE_TRANSLATION_ADDR, max_source + 1)
    map_entries = tuple(translation[source] for source in raw_map)
    underlay_tile = translation[2]

    anim_a = tuple(
        _slice(
            rom,
            TITLE_BG_TILES_ADDR + TITLE_ANIM_A_BASE + state * TITLE_ANIM_A_STRIDE,
            TITLE_ANIM_A_BYTES,
        )
        for state in range(TITLE_ANIMATION_STATES)
    )
    anim_b = tuple(
        _slice(
            rom,
            TITLE_BG_TILES_ADDR + TITLE_ANIM_B_BASE + state * TITLE_ANIM_B_STRIDE,
            TITLE_ANIM_B_BYTES,
        )
        for state in range(TITLE_ANIMATION_STATES)
    )

    # 0x0800A830 uses level-0 index base 0x40, so printable code C maps to
    # translation[(0x40 - 0x20) + C] == translation[C + 32].
    prompt_tiles = tuple(translation[code + 32] for code in TITLE_PROMPT)
    space_tile = translation[ord(' ') + 32]
    blank_tiles = tuple(space_tile for _ in TITLE_PROMPT)

    return TitleAssets(
        bg_tiles,
        palette,
        obj_tiles,
        obj_palette,
        obj_high_palette,
        map_entries,
        underlay_tile,
        anim_a,
        anim_b,
        TITLE_PROMPT,
        prompt_tiles,
        blank_tiles,
    )


def _format_u16(values, per_line=10) -> str:
    vals = list(values)
    lines = []
    for i in range(0, len(vals), per_line):
        chunk = vals[i:i + per_line]
        lines.append('    ' + ', '.join(f'0x{v:04X}' for v in chunk) + ',')
    return '\n'.join(lines)


def _bytes_as_u16(data: bytes) -> tuple[int, ...]:
    if len(data) & 1:
        raise ValueError('expected even byte count')
    return struct.unpack(f'<{len(data)//2}H', data)


def _title_c(assets: TitleAssets) -> str:
    anim_a_rows = []
    for frame in assets.anim_a:
        anim_a_rows.append('    {\n' + _format_u16(_bytes_as_u16(frame), 12) + '\n    },')
    anim_b_rows = []
    for frame in assets.anim_b:
        anim_b_rows.append('    {\n' + _format_u16(_bytes_as_u16(frame), 12) + '\n    },')
    return f'''#include <graveblood/assets.h>\n\nconst u16 gb_title_bg_tiles[0xD800 / 2] = {{\n{_format_u16(_bytes_as_u16(assets.bg_tiles), 12)}\n}};\n\nconst u16 gb_title_bg_palette[GB_TITLE_BG_PALETTE_COUNT] = {{\n{_format_u16(assets.palette, 10)}\n}};\n\nconst u16 gb_title_obj_tiles[GB_TITLE_OBJ_TILE_HALFWORDS] = {{\n{_format_u16(_bytes_as_u16(assets.obj_tiles), 12)}\n}};\n\nconst u16 gb_title_obj_palette[GB_TITLE_OBJ_PALETTE_COUNT] = {{\n{_format_u16(assets.obj_palette, 10)}\n}};\n\nconst u16 gb_title_obj_high_palette[GB_TITLE_OBJ_HIGH_PALETTE_COUNT] = {{\n{_format_u16(assets.obj_high_palette, 10)}\n}};\n\nconst u16 gb_title_underlay_tile = 0x{assets.underlay_tile:04X};\n\nconst u16 gb_title_map[GB_TITLE_MAP_CELLS] = {{\n{_format_u16(assets.map_entries, 10)}\n}};\n\nconst u16 gb_title_anim_a[GB_TITLE_ANIMATION_STATES][GB_TITLE_ANIM_A_HALFWORDS] = {{\n{chr(10).join(anim_a_rows)}\n}};\n\nconst u16 gb_title_anim_b[GB_TITLE_ANIMATION_STATES][GB_TITLE_ANIM_B_HALFWORDS] = {{\n{chr(10).join(anim_b_rows)}\n}};\n\nconst u16 gb_title_prompt_tiles[GB_TITLE_PROMPT_LENGTH] = {{\n{_format_u16(assets.prompt_tiles, 14)}\n}};\n\nconst u16 gb_title_blank_tiles[GB_TITLE_PROMPT_LENGTH] = {{\n{_format_u16(assets.blank_tiles, 14)}\n}};\n'''


def _write_semantics(path: Path) -> None:
    rows = [
        ('descriptor_iwram', '0x03000EA4', 'startup-initialized title graphics descriptor'),
        ('descriptor_rom', '0x08A8DE54', 'startup template for title graphics descriptor'),
        ('bg_tiles', '0x08019CC4', '0xD800 bytes copied to BG char memory on TitleScene enter'),
        ('translation', '0x0802B148', 'title tile translation table'),
        ('bg_palette', '0x0802BB0C', 'canonical title BG palette source'),
        ('bg_palette_count', '223', 'startup initializer writes 0xDF from ROM 0x0802BCCC to descriptor +0x10'),
        ('obj_tiles', '0x08310654 bytes=0x8000', 'graphics loader 0x0800575C copies descriptor +0x14 to OBJ VRAM'),
        ('obj_palette', '0x08366E58', 'canonical title OBJ palette source'),
        ('obj_palette_count', '91', 'startup initializer writes 0x5B from ROM 0x08366F10 to descriptor +0x20'),
        ('obj_high_palette', '0x08652DB4', 'graphics loader copies fixed 32 colors to OBJ palette indices 224..255'),
        ('obj_high_palette_count', '32', 'fixed 0x40-byte copy at 0x080057B4-0x080057C2'),
        ('display_control', '0x1F00', 'Mode 0 + BG0/BG1/BG2/BG3/OBJ; 2D OBJ mapping; 0x0800A208'),
        ('display_setup_blanking', 'forced blank set during setup and cleared before return', '0x0800A208 temporarily sets DISPCNT bit7 while clearing/configuring video state, then returns with final 0x1F00'),
        ('scroll_offsets', 'BG0HOFS/BG0VOFS..BG3HOFS/BG3VOFS=0', '0x0800A208 clears all eight text-BG scroll registers during Title display setup'),
        ('obj_mapping', '2D', 'DISPCNT bit6 is clear in exact 0x1F00 Title display control'),
        ('bg_controls', 'BG0=0x1B80 BG1=0x1C81 BG2=0x1D82 BG3=0x1E83', '0x0800A208 exact BGCNT writes'),
        ('map_source', '0x08655814', '30x20 raw map used by fixed-map mode 5'),
        ('artwork_destination', 'BG1 screenblock28', '0x0800A700 mode5 stores translated entries at base 0x0600D800 + 0x800'),
        ('prompt_destination', 'BG0 screenblock27', 'text writer 0x0800A830 uses 0x0600D800'),
        ('backing_destination', 'BG2 screenblock29 + BG3 screenblock30, 64x32', '0x08005894 splits fixed level-0 width 64 at x=32'),
        ('backing_tile', 'translation[2]', '0x0800589C loads halfword [translation + 4]'),
        ('hidden_oam', 'attr0=0x02F0 attr1=0x01F0 attr2=0x0C00', '0x0800A208 canonical 128-entry hidden OAM initialization'),
        ('anim_a', 'dest=0x2F00 base=0xC480 stride=0xC00 bytes=0xC00 states=4', 'TitleScene_update first tile patch'),
        ('anim_b', 'dest=0x3B00 base=0xF480 stride=0x800 bytes=0x600 states=4', 'TitleScene_update second tile patch'),
        ('animation_cadence', 'counter<=5 same state; counter>5 advance 0,1,2,3,0', 'TitleScene_update 0x08004A78'),
        ('prompt', 'PRESS START... at tile (9,9)', 'string 0x08A8C324 and text call 0x08004ACE'),
        ('prompt_blink', 'frame_counter bit4: 0=visible 1=blank', 'global 0x03000554 test at 0x08004AFC'),
        ('start_input', 'fresh START bit 0x0008', 'current/previous key globals 0x030006BC/0x030006C0'),
        ('start_transition', 'Gameplay level 7 arg0 delay120', 'TitleScene_update 0x08004B18-0x08004B40'),
        ('start_sfx', 'SFX6 volume80', 'one-shot 0x08004B2A; callee 0x08001B74 consumes only r0/r1, incoming r2 is non-semantic'),
        ('title_music', 'none code-proven', 'no TitleScene loop-player call; exhaustive public-demo loop-player scan has only three gameplay calls'),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['fact', 'value', 'evidence'])
        w.writerows(rows)


def _write_disasm(root: Path, out: Path, rom_path: Path, name: str, offset: int, size: int) -> None:
    cmd = [sys.executable, str(root / 'tools' / 'disasm_thumb_chunk.py'), str(rom_path), hex(offset), hex(size)]
    result = subprocess.run(cmd, cwd=root, check=True, capture_output=True, text=True)
    path = out / 'disasm' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.stdout, encoding='utf-8')


def generate(root: Path, out: Path, rom_path: Path) -> None:
    rom = rom_path.read_bytes()
    digest = hashlib.sha256(rom).hexdigest()
    if digest != CANONICAL_SHA256:
        raise ValueError(f'canonical ROM SHA-256 mismatch: {digest}')
    assets = extract_title_assets(rom)
    runtime = out / 'reconstruction' / 'data' / 'title_assets.c'
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(_title_c(assets), encoding='utf-8')
    _write_semantics(out / 'data' / 'title_scene_semantics.csv')
    _write_disasm(root, out, rom_path, 'title_scene_enter_08005914.txt', 0x5914, 0x2C)
    _write_disasm(root, out, rom_path, 'title_scene_08004A74.txt', 0x4A74, 0xD0)
    _write_disasm(root, out, rom_path, 'title_start_transition_08004AFC.txt', 0x4AFC, 0x48)
    _write_disasm(root, out, rom_path, 'title_graphics_loader_0800575C.txt', 0x575C, 0x80)
    _write_disasm(root, out, rom_path, 'title_fixed_backing_08005894.txt', 0x5894, 0x80)
    _write_disasm(root, out, rom_path, 'title_display_setup_0800A208.txt', 0xA208, 0xD0)
    _write_disasm(root, out, rom_path, 'title_map_mode5_0800A700.txt', 0xA700, 0xF0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', type=Path)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    out = (args.out or root).resolve()
    generate(root, out, args.rom.resolve())


if __name__ == '__main__':
    main()
