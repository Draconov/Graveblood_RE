#!/usr/bin/env python3
"""Generate CFA-style checked-in reconstruction assets for Levels 7 and 8.

The normal GBA build consumes generated C files and never needs the original
ROM. Regeneration uses the checked-in RE renders/actor tables plus the
canonical demo ROM for the recovered u16 collision grids and exact Player
animation source frames.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from render_sprites import (  # noqa: E402
    player_animation_initializers_from_rom,
    player_animation_source_bases,
    reconstruct_player_frame_from_source_rows,
)

ROM_BASE = 0x08000000
LEVELS = (7, 8)


@dataclass(frozen=True)
class PortalSpec:
    x: int
    y: int
    width: int
    height: int
    target_level: int
    num: int


@dataclass(frozen=True)
class LevelSpec:
    level: int
    width: int
    height: int
    spawn: tuple[int, int]
    collision_addr: int
    portals: tuple[PortalSpec, ...]


@dataclass(frozen=True)
class PackedBackground:
    width: int
    height: int
    palette: tuple[tuple[int, int, int], ...]
    tiles: tuple[bytes, ...]
    cell_tiles: tuple[int, ...]


@dataclass(frozen=True)
class PackedSprite:
    size: tuple[int, int]
    frame_count: int
    palette: tuple[tuple[int, int, int], ...]
    data: bytes


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def build_level_specs(root: Path) -> dict[int, LevelSpec]:
    levels = {int(r['level_index']): r for r in _read_csv(root / 'data' / 'levels.csv')}
    actors = _read_csv(root / 'data' / 'actors.csv')
    out: dict[int, LevelSpec] = {}
    for level in LEVELS:
        row = levels[level]
        portals: list[PortalSpec] = []
        for actor in actors:
            indices = {x.strip() for x in actor.get('normal_level_indices', '').replace(';', ',').split(',') if x.strip()}
            if str(level) not in indices or actor.get('type') != 'fgtile':
                continue
            portals.append(PortalSpec(
                x=round(float(actor['x'])),
                y=round(float(actor['y'])),
                width=round(float(actor['width'])),
                height=round(float(actor['height'])),
                target_level=int(actor['portTo']),
                num=int(actor['num']),
            ))
        out[level] = LevelSpec(
            level=level,
            width=int(row['world_width_tiles']),
            height=int(row['world_height_tiles']),
            spawn=(round(float(row['player_x'])), round(float(row['player_y']))),
            collision_addr=int(row['collision_grid_addr'], 16),
            portals=tuple(portals),
        )
    return out


def load_world_image(root: Path, level: int) -> Image.Image:
    return Image.open(root / 'renders' / 'maps' / f'level{level:02d}_v0_world.png').convert('RGB')


def _palette_for_image(image: Image.Image) -> tuple[tuple[int, int, int], ...]:
    colors = {rgb for _, rgb in image.getcolors(maxcolors=1_000_000) or []}
    first = image.getpixel((0, 0))
    ordered = [first] + sorted(c for c in colors if c != first)
    if len(ordered) > 256:
        raise ValueError(f'8bpp background needs <=256 colors, got {len(ordered)}')
    return tuple(ordered)


def pack_background(image: Image.Image) -> PackedBackground:
    if image.width % 8 or image.height % 8:
        raise ValueError('world image dimensions must be multiples of 8')
    palette = _palette_for_image(image)
    index = {rgb: i for i, rgb in enumerate(palette)}
    tiles: list[bytes] = []
    tile_index: dict[bytes, int] = {}
    cells: list[int] = []
    for ty in range(image.height // 8):
        for tx in range(image.width // 8):
            blob = bytearray()
            for py in range(8):
                for px in range(8):
                    blob.append(index[image.getpixel((tx * 8 + px, ty * 8 + py))])
            key = bytes(blob)
            found = tile_index.get(key)
            if found is None:
                found = len(tiles)
                if found >= 256:
                    raise ValueError('tileset exceeds one 8bpp character block')
                tile_index[key] = found
                tiles.append(key)
            cells.append(found)
    return PackedBackground(
        width=image.width // 8,
        height=image.height // 8,
        palette=palette,
        tiles=tuple(tiles),
        cell_tiles=tuple(cells),
    )


def _pack_4bpp_image(image: Image.Image, index: dict[tuple[int, int, int], int]) -> bytes:
    if image.size != (16, 32):
        raise ValueError(f'unexpected player sprite size {image.size}')
    out = bytearray()
    for tile_y in range(4):
        for tile_x in range(2):
            nibbles: list[int] = []
            for py in range(8):
                for px in range(8):
                    rgba = image.getpixel((tile_x * 8 + px, tile_y * 8 + py))
                    nibbles.append(0 if rgba[3] == 0 else index[rgba[:3]])
            for i in range(0, 64, 2):
                out.append(nibbles[i] | (nibbles[i + 1] << 4))
    return bytes(out)


def pack_player_animation(rom: bytes) -> PackedSprite:
    init = player_animation_initializers_from_rom(rom)
    sources = player_animation_source_bases(init['bank'])
    packed_sources = sources['regular_walk'] + sources['up_walk'] + sources['idle_unique']
    images = [reconstruct_player_frame_from_source_rows(rom, source) for source in packed_sources]
    opaque = sorted({
        rgba[:3]
        for image in images
        for rgba in (image.get_flattened_data() if hasattr(image, 'get_flattened_data') else image.getdata())
        if rgba[3]
    })
    if len(opaque) > 15:
        raise ValueError('player animation exceeds one 4bpp OBJ palette')
    palette = ((0, 0, 0), *opaque)
    index = {rgb: i + 1 for i, rgb in enumerate(opaque)}
    data = b''.join(_pack_4bpp_image(image, index) for image in images)
    return PackedSprite((16, 32), len(images), tuple(palette), data)


def _find_rom(root: Path, explicit: Path | None = None) -> Path:
    candidates = []
    if explicit:
        candidates.append(explicit)
    env_rom = os.environ.get('GRAVEBLOOD_ROM')
    if env_rom:
        candidates.append(Path(env_rom))
    candidates += [
        root / 'Graveblood 0.0.1.1.5.2 demo.gba',
        root.parent / 'Graveblood 0.0.1.1.5.2 demo.gba',
    ]
    for p in candidates:
        if p and p.is_file():
            return p.resolve()
    raise FileNotFoundError(
        'canonical demo ROM is required for collision and Player-animation asset regeneration; '
        'place "Graveblood 0.0.1.1.5.2 demo.gba" beside the repository or pass --rom'
    )


def _read_collision(rom: bytes, spec: LevelSpec) -> tuple[int, ...]:
    off = spec.collision_addr - ROM_BASE
    count = spec.width * spec.height
    return struct.unpack_from(f'<{count}H', rom, off)


def _bgr555(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    rr = (r * 31 + 127) // 255
    gg = (g * 31 + 127) // 255
    bb = (b * 31 + 127) // 255
    return rr | (gg << 5) | (bb << 10)


def _bytes_to_u16(data: bytes) -> list[int]:
    if len(data) % 2:
        raise ValueError('byte data must have even length')
    return [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]


def _hardware_map(cells: Iterable[int], width: int, height: int) -> list[int]:
    src = list(cells)
    out = [0] * 4096
    for y in range(height):
        for x in range(width):
            block = (x // 32) + (y // 32) * 2
            dst = block * 1024 + (y % 32) * 32 + (x % 32)
            out[dst] = src[y * width + x]
    return out


def _c_values(values: Iterable[int], width: int = 12, hex_width: int | None = None) -> str:
    vals = list(values)
    lines = []
    for i in range(0, len(vals), width):
        chunk = vals[i:i + width]
        if hex_width is None:
            formatted = ', '.join(str(v) for v in chunk)
        else:
            formatted = ', '.join(f'0x{v:0{hex_width}X}' for v in chunk)
        lines.append('    ' + formatted + (',' if i + width < len(vals) else ''))
    return '\n'.join(lines)


def _asset_c(level: int, spec: LevelSpec, bg: PackedBackground, collision: tuple[int, ...]) -> str:
    palette = [_bgr555(c) for c in bg.palette] + [0] * (256 - len(bg.palette))
    tile_bytes = b''.join(bg.tiles) + bytes((256 - len(bg.tiles)) * 64)
    hardware_map = _hardware_map(bg.cell_tiles, bg.width, bg.height)
    portal_rows = []
    for p in spec.portals:
        portal_rows.append(f'    {{ {p.x}, {p.y}, {p.width}, {p.height}, {p.target_level}, {p.num} }}')
    portals = ',\n'.join(portal_rows) if portal_rows else '    { 0, 0, 0, 0, 0, 0 }'
    name = f'gb_level{level:02d}'
    return f'''#include <graveblood/assets.h>\n\nconst u16 {name}_palette[256] = {{\n{_c_values(palette, 10, 4)}\n}};\n\nconst u16 {name}_tiles[8192] = {{\n{_c_values(_bytes_to_u16(tile_bytes), 12, 4)}\n}};\n\nconst u16 {name}_map[4096] = {{\n{_c_values(hardware_map, 12)}\n}};\n\nconst u16 {name}_collision[{len(collision)}] = {{\n{_c_values(collision, 24)}\n}};\n\nconst GbPortal {name}_portals[{max(1, len(spec.portals))}] = {{\n{portals}\n}};\n\nconst GbLevelAssets {name}_assets = {{\n    .level_id = {level},\n    .world_width_tiles = {spec.width},\n    .world_height_tiles = {spec.height},\n    .spawn_x = {spec.spawn[0]},\n    .spawn_y = {spec.spawn[1]},\n    .tile_count = {len(bg.tiles)},\n    .palette_count = {len(bg.palette)},\n    .palette = {name}_palette,\n    .tiles = {name}_tiles,\n    .map = {name}_map,\n    .collision = {name}_collision,\n    .portals = {name}_portals,\n    .portal_count = {len(spec.portals)},\n}};\n'''


def _player_c(sprite: PackedSprite) -> str:
    palette = [_bgr555(c) for c in sprite.palette] + [0] * (16 - len(sprite.palette))
    return f'''#include <graveblood/assets.h>\n\nconst u16 gb_player_obj_palette[16] = {{\n{_c_values(palette, 8, 4)}\n}};\n\nconst u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128] = {{\n{_c_values(_bytes_to_u16(sprite.data), 12, 4)}\n}};\n'''


def _assets_h() -> str:
    return '''#ifndef GRAVEBLOOD_ASSETS_H\n#define GRAVEBLOOD_ASSETS_H\n\n#include <gba.h>\n\ntypedef struct {\n    s16 x;\n    s16 y;\n    u8 width;\n    u8 height;\n    u8 target_level;\n    u16 num;\n} GbPortal;\n\ntypedef struct {\n    u8 level_id;\n    u8 world_width_tiles;\n    u8 world_height_tiles;\n    s16 spawn_x;\n    s16 spawn_y;\n    u16 tile_count;\n    u16 palette_count;\n    const u16* palette;\n    const u16* tiles;\n    const u16* map;\n    const u16* collision;\n    const GbPortal* portals;\n    u8 portal_count;\n} GbLevelAssets;\n\nextern const GbLevelAssets gb_level07_assets;\nextern const GbLevelAssets gb_level08_assets;\nenum { GB_PLAYER_FRAME_COUNT = 16 };\n\nextern const u16 gb_player_obj_palette[16];\nextern const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128];\n\n#endif\n'''


def _tilesheet(bg: PackedBackground) -> Image.Image:
    cols = 16
    rows = max(1, math.ceil(len(bg.tiles) / cols))
    sheet = Image.new('RGB', (cols * 8, rows * 8), bg.palette[0])
    for tile_i, blob in enumerate(bg.tiles):
        tile = Image.new('RGB', (8, 8))
        px = tile.load()
        for i, pal_i in enumerate(blob):
            px[i % 8, i // 8] = bg.palette[pal_i]
        sheet.paste(tile, ((tile_i % cols) * 8, (tile_i // cols) * 8))
    return sheet


def _tmx(level: int, spec: LevelSpec, bg: PackedBackground) -> str:
    csv_rows = []
    for y in range(bg.height):
        csv_rows.append(','.join(str(bg.cell_tiles[y * bg.width + x] + 1) for x in range(bg.width)))
    object_rows = [
        f'    <object id="1" name="Player spawn" type="player" x="{spec.spawn[0]}" y="{spec.spawn[1]}"/>',
    ]
    for i, p in enumerate(spec.portals, start=2):
        object_rows.append(
            f'    <object id="{i}" name="Portal to {p.target_level}" type="fgtile" '
            f'x="{p.x}" y="{p.y}" width="{p.width}" height="{p.height}">'
            f'<properties><property name="portTo" type="int" value="{p.target_level}"/>'
            f'<property name="num" type="int" value="{p.num}"/></properties></object>'
        )
    return f'''<?xml version="1.0" encoding="UTF-8"?>\n<map version="1.10" tiledversion="1.11" orientation="orthogonal" renderorder="right-down" width="{bg.width}" height="{bg.height}" tilewidth="8" tileheight="8" infinite="0" nextlayerid="3" nextobjectid="{len(object_rows)+1}">\n  <tileset firstgid="1" name="level{level:02d}" tilewidth="8" tileheight="8" tilecount="{len(bg.tiles)}" columns="16">\n    <image source="generated/level{level:02d}_tiles.png" width="128" height="{max(8, math.ceil(len(bg.tiles)/16)*8)}"/>\n  </tileset>\n  <layer id="1" name="World" width="{bg.width}" height="{bg.height}">\n    <data encoding="csv">\n{escape(chr(10).join(csv_rows))}\n    </data>\n  </layer>\n  <objectgroup id="2" name="Actors">\n{chr(10).join(object_rows)}\n  </objectgroup>\n</map>\n'''


def generate_all(root: Path, out: Path, rom_path: Path | None = None) -> None:
    out = Path(out)
    (out / 'data').mkdir(parents=True, exist_ok=True)
    (out / 'include' / 'graveblood').mkdir(parents=True, exist_ok=True)
    (out / 'maps' / 'generated').mkdir(parents=True, exist_ok=True)
    specs = build_level_specs(root)
    rom_file = _find_rom(root, rom_path)
    rom = rom_file.read_bytes()
    for level in LEVELS:
        spec = specs[level]
        bg = pack_background(load_world_image(root, level))
        collision = _read_collision(rom, spec)
        (out / 'data' / f'level{level:02d}_assets.c').write_text(
            _asset_c(level, spec, bg, collision), encoding='utf-8'
        )
        _tilesheet(bg).save(out / 'maps' / 'generated' / f'level{level:02d}_tiles.png', optimize=False)
        (out / 'maps' / f'level{level:02d}.tmx').write_text(_tmx(level, spec, bg), encoding='utf-8')
    sprite = pack_player_animation(rom)
    (out / 'data' / 'player_sprite.c').write_text(_player_c(sprite), encoding='utf-8')
    (out / 'include' / 'graveblood' / 'assets.h').write_text(_assets_h(), encoding='utf-8')


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=root)
    ap.add_argument('--out', type=Path, default=root / 'reconstruction')
    ap.add_argument('--rom', type=Path)
    args = ap.parse_args()
    generate_all(args.root, args.out, args.rom)


if __name__ == '__main__':
    main()
