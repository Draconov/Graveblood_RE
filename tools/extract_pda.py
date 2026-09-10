#!/usr/bin/env python3
"""Extract the canonical public-demo PDA maps and proven control semantics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from disasm_thumb_chunk import disassemble_thumb_blob  # noqa: E402

ROM_BASE = 0x08000000
CANONICAL_SHA256 = 'e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b'
PAGE_NAMES = ('MESSAGES', 'STATUS', 'FRIENDS', 'BACKPACK')
PAGE_BRANCHES = (0x08007642, 0x0800795C, 0x0800777A, 0x08007A10)
PAGE_RAW_MAPS = (0x086540A4, 0x08653BF4, 0x08653744, 0x08653294)
PDA_TRANSLATION = 0x0864825C
PDA_MAP_CELLS = 30 * 20
PDA_TEXT_COLUMNS = 29
PDA_TEXT_ROWS = 5
PDA_TEXT_TILE_COUNT = PDA_TEXT_COLUMNS * PDA_TEXT_ROWS
PDA_LEVEL_TILE_LIMIT = 0xD800 // 64

IWRAM_DATA_ROM = 0x08A8D738
IWRAM_DATA_RAM = 0x03000788
FRIENDS_ORDER_TABLE_RAM = 0x03000814
FRIENDS_PROFILE_TABLE_RAM = 0x03001118
FRIENDS_VISIBLE_ROWS = 3
FRIENDS_COUNT = 6
FRIENDS_EXPECTED_ORDER = (2, 0, 1, 3, 4, 5)
FRIENDS_EXPECTED_NAMES = ('Kate', 'Stas', 'IQ 54', 'Kiata', 'Alex', 'Evelina')

PAGE_SELECTOR_RAM = 0x03000614
RETURN_PENDING_RAM = 0x03000618
MESSAGE_SLOT_BOUNDS = (0, 3)

DISASM_RANGES = (
    ('pda_renderer_080075F8.txt', 0x75F8, 0x430),
    ('pda_open_0800849E.txt', 0x849E, 0x70),
    ('pda_navigation_080088EC.txt', 0x88EC, 0x7C0),
    ('pda_messages_select_08009568.txt', 0x9568, 0x180),
    ('pda_friends_navigation_080089BE.txt', 0x89BE, 0x720),
)

EXPECTED_PAGE_MAP_HASHES = (
    '8be8fb65d2fd54d1dc3a3ba6bd978bbd9075419048008a1922306685bf722aeb',
    'fd82be70bb76e5ccfbeb8deac04753647da5912c7188ba2d9d3b83403bfbfa24',
    '3673fd5e021a8456ef076f9e2519dfa306a1540e02631ffa5f16c4f2c7466170',
    '5d86cd4006daffb840d5cdcb0e72802ac37dc5e3854403cda3f2a5da6e3c7919',
)


@dataclass(frozen=True)
class PdaData:
    page_names: tuple[str, ...]
    raw_map_addresses: tuple[int, ...]
    translation_address: int
    page_maps: tuple[tuple[int, ...], ...]
    friends_profile_order: tuple[int, ...]
    friends_names: tuple[str, ...]
    friends_visible_rows: int
    message_slot_bounds: tuple[int, int]
    ordinary_close_key_proven: bool
    text_tile_ids: tuple[int, ...]


def _off(addr: int) -> int:
    return addr - ROM_BASE


def _u16(rom: bytes, addr: int) -> int:
    return struct.unpack_from('<H', rom, _off(addr))[0]


def _u32(rom: bytes, addr: int) -> int:
    return struct.unpack_from('<I', rom, _off(addr))[0]


def _u16s(rom: bytes, addr: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f'<{count}H', rom, _off(addr))


def _ram_init_off(ram_addr: int) -> int:
    if ram_addr < IWRAM_DATA_RAM:
        raise ValueError(f'RAM address 0x{ram_addr:08X} is below initialized IWRAM block')
    return IWRAM_DATA_ROM + (ram_addr - IWRAM_DATA_RAM) - ROM_BASE


def _ram_u32(rom: bytes, ram_addr: int) -> int:
    return struct.unpack_from('<I', rom, _ram_init_off(ram_addr))[0]


def _ram_cstr(rom: bytes, ram_addr: int, limit: int = 20) -> str:
    off = _ram_init_off(ram_addr)
    raw = rom[off:off + limit].split(b'\0', 1)[0]
    return raw.decode('ascii')


def _validate_rom(rom: bytes) -> None:
    digest = hashlib.sha256(rom).hexdigest()
    if digest != CANONICAL_SHA256:
        raise ValueError(f'canonical ROM SHA-256 mismatch: {digest}')

    # Page renderer dispatch: selector 0/1/2/3 and invalid fallback setter.
    expected_halfwords = {
        0x08007612: 0x4BE1,  # LDR page selector literal
        0x08007616: 0x2D00,
        0x0800761A: 0x2D01,
        0x08007620: 0x2D02,
        0x08007626: 0x2D03,
        0x0800762C: 0x2201,
        0x08007630: 0x701A,  # STRB 1 -> return-pending byte
        0x0800849E: 0x2208,  # START bit
        0x080084C2: 0x2000,  # stop channel 0
        0x080084CA: 0x2001,  # stop channel 1
        0x080084D0: 0x2002,  # stop channel 2
        0x080084DA: 0x2006,  # SFX6
        0x0800898C: 0x2150,  # SFX11 previous-page volume
        0x0800904C: 0x2150,  # SFX11 next-page volume
    }
    for addr, value in expected_halfwords.items():
        actual = _u16(rom, addr)
        if actual != value:
            raise ValueError(f'PDA signature drifted at 0x{addr:08X}: 0x{actual:04X} != 0x{value:04X}')


def _translate_pages(rom: bytes) -> tuple[tuple[int, ...], ...]:
    raw_pages = tuple(_u16s(rom, addr, PDA_MAP_CELLS) for addr in PAGE_RAW_MAPS)
    max_source = max(max(page) for page in raw_pages)
    translation = _u16s(rom, PDA_TRANSLATION, max_source + 1)
    pages = tuple(tuple(translation[source] for source in raw) for raw in raw_pages)
    for index, page in enumerate(pages):
        packed = struct.pack('<600H', *page)
        digest = hashlib.sha256(packed).hexdigest()
        if digest != EXPECTED_PAGE_MAP_HASHES[index]:
            raise ValueError(f'PDA page {index} map drifted: {digest}')
    return pages


def _friends(rom: bytes) -> tuple[tuple[int, ...], tuple[str, ...]]:
    # Runtime table starts [2,0,1,3,4,5,-1,...]. Six valid entries feed the
    # three-row FRIENDS window, and 0x030005DC is its independent scroll offset.
    order = tuple(_ram_u32(rom, FRIENDS_ORDER_TABLE_RAM + i * 4) for i in range(FRIENDS_COUNT))
    if order != FRIENDS_EXPECTED_ORDER:
        raise ValueError(f'FRIENDS order drifted: {order!r}')
    sentinel = _ram_u32(rom, FRIENDS_ORDER_TABLE_RAM + FRIENDS_COUNT * 4)
    if sentinel != 0xFFFFFFFF:
        raise ValueError(f'FRIENDS sentinel drifted: 0x{sentinel:08X}')
    profile_ptrs = tuple(_ram_u32(rom, FRIENDS_PROFILE_TABLE_RAM + index * 4) for index in order)
    names = tuple(_ram_cstr(rom, ptr) for ptr in profile_ptrs)
    if names != FRIENDS_EXPECTED_NAMES:
        raise ValueError(f'FRIENDS names drifted: {names!r}')
    return order, names


def _literal_occurrences(rom: bytes, value: int, code_limit: int = 0x20000) -> tuple[int, ...]:
    needle = struct.pack('<I', value)
    result = []
    pos = 0
    while True:
        pos = rom.find(needle, pos)
        if pos < 0:
            break
        if pos < code_limit:
            result.append(ROM_BASE + pos)
        pos += 1
    return tuple(result)


def extract_pda(rom: bytes) -> PdaData:
    _validate_rom(rom)
    pages = _translate_pages(rom)
    order, names = _friends(rom)

    # Exact direct literals used by the executable. The only direct setter of
    # RETURN_PENDING_RAM to 1 is 0x0800762E/30; the return helper clears it.
    return_literals = _literal_occurrences(rom, RETURN_PENDING_RAM)
    expected_literals = (0x080049A0, 0x0800696C, 0x080075F4, 0x0800799C, 0x08008564, 0x080088D8)
    if return_literals != expected_literals:
        raise ValueError(f'PDA return flag literal inventory drifted: {return_literals!r}')

    page_literals = _literal_occurrences(rom, PAGE_SELECTOR_RAM)
    expected_page_literals = (0x08006CF4, 0x08007998, 0x08008588, 0x08008BA4, 0x080090EC)
    if page_literals != expected_page_literals:
        raise ValueError(f'PDA page selector literal inventory drifted: {page_literals!r}')

    chrome_tiles = {entry & 0x03FF for page in pages for entry in page}
    text_tile_ids = tuple(tile for tile in range(PDA_LEVEL_TILE_LIMIT) if tile not in chrome_tiles)[:PDA_TEXT_TILE_COUNT]
    if len(text_tile_ids) != PDA_TEXT_TILE_COUNT:
        raise ValueError('not enough PDA-safe dynamic text tiles outside chrome map references')

    return PdaData(
        PAGE_NAMES,
        PAGE_RAW_MAPS,
        PDA_TRANSLATION,
        pages,
        order,
        names,
        FRIENDS_VISIBLE_ROWS,
        MESSAGE_SLOT_BOUNDS,
        False,
        text_tile_ids,
    )


def _format_u16(values: tuple[int, ...], per_line: int = 12) -> str:
    lines = []
    for i in range(0, len(values), per_line):
        lines.append('    ' + ', '.join(f'0x{v:04X}' for v in values[i:i + per_line]) + ',')
    return '\n'.join(lines)


def _c_string(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _runtime_c(data: PdaData) -> str:
    page_rows = []
    for page in data.page_maps:
        page_rows.append('    {\n' + _format_u16(page) + '\n    },')
    names = ',\n'.join('    ' + _c_string(name) for name in data.friends_names)
    text_tiles = _format_u16(data.text_tile_ids)
    return f'''#include <graveblood/assets.h>\n\nconst u16 gb_pda_page_maps[GB_PDA_PAGE_COUNT][GB_PDA_MAP_CELLS] = {{\n{chr(10).join(page_rows)}\n}};\n\nconst char* const gb_pda_friend_names[GB_PDA_FRIEND_COUNT] = {{\n{names}\n}};\n\nconst u16 gb_pda_text_tile_ids[GB_PDA_TEXT_TILE_COUNT] = {{\n{text_tiles}\n}};\n'''


def _write_csv(path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(rows)


def _write_semantics(data: PdaData, out: Path) -> None:
    _write_csv(out / 'data/pda_runtime_semantics.csv', ('fact', 'value', 'evidence'), [
        ('page_selector', '0x03000614 values 0..3', '0x080075F8 dispatch + bounded shoulder writers'),
        ('open_input', 'fresh START', '0x0800849E-0x080084AC'),
        ('open_audio', 'stop channels 0,1,2; SFX6 volume 0x50', '0x080084C2-0x080084DC'),
        ('open_page', 'reset to MESSAGES selector 0', '0x080084E4-0x080084E8'),
        ('page_navigation', 'fresh R shoulder page+1; fresh L shoulder page-1; bounds 0..3; no wrap', '0x0800896C-0x08008994 and 0x0800903A-0x08009054'),
        ('page_navigation_sfx', 'SFX11 volume 0x50', '0x08008988-0x0800898E and 0x08009048-0x0800904E'),
        ('ordinary_close', 'no ordinary direct close input proven', 'page selector writers are open->0 and bounded shoulder +/-1; return flag direct setter is invalid-page fallback only'),
        ('return_pending', '0x03000618 set=1 only by invalid-page renderer fallback; helper 0x080075C8 clears it', 'literal/reference inventory + 0x0800762C-0x08007630 + 0x080075E8-0x080075EC'),
        ('return_helper_audio', 'SFX7 volume 0x50', '0x080075CC-0x080075D2'),
    ])

    _write_csv(out / 'data/pda_page_render_sources.csv',
               ('selector', 'page', 'renderer_branch', 'map_mode', 'raw_map', 'translation', 'dynamic_policy', 'confidence'), [
        (0, 'MESSAGES', '0x08007642', 0, '0x086540A4', '0x0864825C', 'message title/sender/body from selected recovered stream', 'high'),
        (1, 'STATUS', '0x0800795C', 1, '0x08653BF4', '0x0864825C', 'header only in public-demo branch', 'high'),
        (2, 'FRIENDS', '0x0800777A', 2, '0x08653744', '0x0864825C', 'three-row window over six initialized NPC metadata names', 'high'),
        (3, 'BACKPACK', '0x08007A10', 3, '0x08653294', '0x0864825C', 'header only in public-demo branch', 'high'),
    ])

    _write_csv(out / 'data/pda_cursor_semantics.csv', ('page', 'keys', 'bounds', 'sfx', 'evidence'), [
        ('MESSAGES', 'dpad LEFT/RIGHT', '0..3; skip selector -1', 'SFX4 volume 0x50', 'page==0 gates at 0x0800892E/0x0800894E; helpers 0x08009568/0x08009594'),
        ('STATUS', 'none proven', 'n/a', 'none', 'renderer branch is header-only'),
        ('FRIENDS', 'dpad UP/DOWN', 'cursor row 0..2 plus scroll over 6 entries', 'SFX4 volume 0x50 on success; SFX12 volume 0x50 at absolute top/bottom boundary', 'page==2 gates at 0x080089BE/0x0800905E; success calls 0x080089F8/0x0800909C; boundary calls 0x08009B58/0x08009AA2; table 0x03000814; scroll 0x030005DC'),
        ('BACKPACK', 'none proven', 'n/a', 'none', 'renderer branch is header-only'),
    ])

    _write_csv(out / 'data/pda_friends_entries.csv', ('list_index', 'profile_table_index', 'name', 'initialized_name_ram', 'confidence'), [
        (0, 2, 'Kate', '0x030011C4', 'high'),
        (1, 0, 'Stas', '0x03001224', 'high'),
        (2, 1, 'IQ 54', '0x030011F4', 'high'),
        (3, 3, 'Kiata', '0x03001194', 'high'),
        (4, 4, 'Alex', '0x03001164', 'high'),
        (5, 5, 'Evelina', '0x03001134', 'high'),
    ])


def generate(repo_root: Path, out: Path, rom_path: Path) -> None:
    rom = rom_path.read_bytes()
    data = extract_pda(rom)
    _write_semantics(data, out)
    runtime = out / 'reconstruction/data/pda_assets.c'
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(_runtime_c(data), encoding='utf-8')

    for name, offset, size in DISASM_RANGES:
        path = out / 'disasm' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(disassemble_thumb_blob(rom[offset:offset + size], ROM_BASE + offset), encoding='utf-8')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', type=Path)
    ap.add_argument('--out', type=Path, default=ROOT)
    args = ap.parse_args()
    generate(ROOT, args.out, args.rom)


if __name__ == '__main__':
    main()
