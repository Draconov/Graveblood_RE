#!/usr/bin/env python3
"""Generate CFA-style checked-in reconstruction assets for all canonical demo levels.

The normal GBA build consumes generated C files and never needs the original
ROM. Regeneration uses the checked-in RE renders/actor tables plus the
canonical demo ROM for exact streamed BG resources, u16 collision grids, portal
geometry, and Player animation source frames.
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
    OBJ_PALETTE_SOURCE,
    OBJ_TILES_SOURCE,
    npc_source_base,
    npc_source_bias_from_rom,
    npc_source_rows,
    player_animation_initializers_from_rom,
    player_animation_source_bases,
    reconstruct_player_frame_from_source_rows,
)

ROM_BASE = 0x08000000
LEVELS = tuple(range(11))

ACTOR_CLASS_NPC = 0
ACTOR_CLASS_GRASS = 1
ACTOR_CLASS_FGTILE = 2
ACTOR_CLASS_LEAVES = 3
ACTOR_CLASS_PLAYER = 4
ACTOR_VISUAL_NONE = 0xFF


@dataclass(frozen=True)
class PortalSpec:
    x: int
    y: int
    width: int
    height: int
    target_level: int
    num: int


@dataclass(frozen=True)
class GraphicsVariantSpec:
    level: int
    variant: int
    bg_tiles_addr: int
    translation_addr: int
    palette_addr: int


@dataclass(frozen=True)
class LevelSpec:
    level: int
    width: int
    height: int
    fixed_width: int
    fixed_height: int
    spawn: tuple[int, int]
    visual_a_addr: int
    collision_addr: int
    visual_b_addr: int
    fixed_map_addr: int
    portals: tuple[PortalSpec, ...]


@dataclass(frozen=True)
class RuntimeBackground:
    palette: tuple[int, ...]
    tile_bytes: bytes
    translation: tuple[int, ...]
    layer_a: tuple[int, ...]
    layer_b: tuple[int, ...]
    fixed_map: tuple[int, ...]


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


@dataclass(frozen=True)
class ActorDescriptorSpec:
    x: int
    y: int
    width: int
    height: int
    rom_order: int
    port_to: int
    actor_class: int
    subtype: int
    legs_color: int
    num: int
    state: int
    route: int
    dial: int
    turn: int
    level: int
    setglobal: int
    visual_index: int


@dataclass(frozen=True)
class StoryActorSpec:
    overlay_index: int
    level: int
    descriptor: ActorDescriptorSpec


@dataclass(frozen=True)
class ActorRuntimeData:
    physical: tuple[ActorDescriptorSpec, ...]
    level_indices: dict[int, tuple[int, ...]]
    story: tuple[StoryActorSpec, ...]
    routes: tuple[tuple[tuple[int, int], ...], ...]
    visuals: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PackedActorSpriteBank:
    frame_count: int
    palette: tuple[int, ...]
    data: bytes


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def build_graphics_variants(root: Path) -> dict[tuple[int, int], GraphicsVariantSpec]:
    out: dict[tuple[int, int], GraphicsVariantSpec] = {}
    for row in _read_csv(root / 'data' / 'level_graphics_variants.csv'):
        level = int(row['level_index'])
        variant = int(row['variant_index'])
        out[(level, variant)] = GraphicsVariantSpec(
            level=level,
            variant=variant,
            bg_tiles_addr=int(row['bg_tiles_source'], 16),
            translation_addr=int(row['tile_translation_table'], 16),
            palette_addr=int(row['bg_palette_source'], 16),
        )
    return out


def build_level_specs(root: Path) -> dict[int, LevelSpec]:
    levels = {int(r['level_index']): r for r in _read_csv(root / 'data' / 'levels.csv')}
    actors = _read_csv(root / 'data' / 'actors.csv')
    edges = {
        (int(r['source_level']), r['actor_rom_offset'].upper()): r
        for r in _read_csv(root / 'data' / 'portal_edges.csv')
    }
    out: dict[int, LevelSpec] = {}
    for level in LEVELS:
        row = levels[level]
        portals: list[PortalSpec] = []
        for actor in actors:
            edge = edges.get((level, actor['rom_offset'].upper()))
            if edge is None:
                continue
            portals.append(PortalSpec(
                x=round(float(actor['x'])),
                y=round(float(actor['y'])),
                width=round(float(actor['width'])),
                height=round(float(actor['height'])),
                target_level=int(edge['destination']),
                num=int(edge['num']),
            ))
        out[level] = LevelSpec(
            level=level,
            width=int(row['world_width_tiles']),
            height=int(row['world_height_tiles']),
            fixed_width=int(row['fixed_tilemap_width']),
            fixed_height=int(row['fixed_tilemap_height']),
            spawn=(round(float(row['player_x'])), round(float(row['player_y']))),
            visual_a_addr=int(row['visual_layer_a_addr'], 16),
            collision_addr=int(row['collision_grid_addr'], 16),
            visual_b_addr=int(row['visual_layer_b_addr'], 16),
            fixed_map_addr=int(row['fixed_tilemap_addr'], 16),
            portals=tuple(portals),
        )
    return out


def _actor_number(row: dict[str, str], field: str, *, default: int = 0,
                  minimum: int = -32768, maximum: int = 65535) -> int:
    raw = row.get(field, '')
    value = default if raw == '' else round(float(raw))
    if not minimum <= value <= maximum:
        raise ValueError(f'actor field {field}={value} outside [{minimum},{maximum}]')
    return value


def _actor_class(row: dict[str, str]) -> int:
    spawn_type = row.get('spawnType', '')
    actor_type = row.get('type', '')
    if spawn_type == 'npc':
        return ACTOR_CLASS_NPC
    if spawn_type == 'grass':
        return ACTOR_CLASS_GRASS
    if actor_type == 'fgtile':
        return ACTOR_CLASS_FGTILE
    if actor_type == 'leaves':
        return ACTOR_CLASS_LEAVES
    if actor_type == 'player':
        return ACTOR_CLASS_PLAYER
    raise ValueError(f'unsupported level actor class: spawnType={spawn_type!r} type={actor_type!r}')


def build_actor_runtime_data(root: Path) -> ActorRuntimeData:
    """Build immutable actor/runtime metadata from canonical CSV exports.

    The 251 level-referenced source records include 10 Player records. Player
    records remain level spawn metadata, so the generated runtime descriptor
    table contains the other 241 unique records. Shared Level 0/6 records are
    represented once and referenced from both level index lists.
    """
    actor_rows = _read_csv(root / 'data' / 'actors.csv')
    story_rows = _read_csv(root / 'data' / 'standalone_spawners.csv')
    route_rows = _read_csv(root / 'data' / 'npc_routes.csv')

    physical: list[ActorDescriptorSpec] = []
    level_indices: dict[int, list[int]] = {level: [] for level in LEVELS}
    visual_list: list[tuple[int, int]] = []
    visual_index: dict[tuple[int, int], int] = {}

    def visual_for(actor_class: int, legs_color: int, subtype: int) -> int:
        if actor_class != ACTOR_CLASS_NPC:
            return ACTOR_VISUAL_NONE
        key = (legs_color, subtype)
        found = visual_index.get(key)
        if found is None:
            found = len(visual_list)
            if found >= ACTOR_VISUAL_NONE:
                raise ValueError('too many actor visuals for u8 visual index')
            visual_index[key] = found
            visual_list.append(key)
        return found

    source_order = 0
    for row in actor_rows:
        refs = tuple(int(value) for value in row.get('normal_level_indices', '').split(';') if value)
        if not refs:
            continue
        if any(level not in LEVELS for level in refs):
            raise ValueError(f'actor references unsupported levels: {refs}')
        actor_class = _actor_class(row)
        rom_order = source_order
        source_order += 1
        if actor_class == ACTOR_CLASS_PLAYER:
            continue

        legs_color = _actor_number(row, 'legsColor', minimum=0, maximum=255)
        subtype = _actor_number(row, 'subtype', minimum=0, maximum=255)
        descriptor = ActorDescriptorSpec(
            x=_actor_number(row, 'x', minimum=-32768, maximum=32767),
            y=_actor_number(row, 'y', minimum=-32768, maximum=32767),
            width=_actor_number(row, 'width', minimum=-32768, maximum=32767),
            height=_actor_number(row, 'height', minimum=-32768, maximum=32767),
            rom_order=rom_order,
            port_to=_actor_number(row, 'portTo', minimum=0, maximum=65535),
            actor_class=actor_class,
            subtype=subtype,
            legs_color=legs_color,
            num=_actor_number(row, 'num', minimum=0, maximum=65535),
            state=_actor_number(row, 'state', minimum=0, maximum=255),
            route=_actor_number(row, 'route', minimum=0, maximum=255),
            dial=_actor_number(row, 'dial', minimum=0, maximum=255),
            turn=_actor_number(row, 'turn', minimum=0, maximum=255),
            level=_actor_number(row, 'level', default=255, minimum=0, maximum=255),
            setglobal=_actor_number(row, 'setglobal', minimum=0, maximum=255),
            visual_index=visual_for(actor_class, legs_color, subtype),
        )
        index = len(physical)
        physical.append(descriptor)
        for level in refs:
            level_indices[level].append(index)

    if source_order != 251:
        raise ValueError(f'expected 251 level-referenced actor records, got {source_order}')

    story: list[StoryActorSpec] = []
    for row in story_rows:
        actor_class = ACTOR_CLASS_NPC
        legs_color = _actor_number(row, 'legsColor', minimum=0, maximum=255)
        subtype = _actor_number(row, 'subtype', minimum=0, maximum=255)
        level = _actor_number(row, 'level', minimum=0, maximum=10)
        overlay_index = int(row['index'])
        descriptor = ActorDescriptorSpec(
            x=_actor_number(row, 'x', minimum=-32768, maximum=32767),
            y=_actor_number(row, 'y', minimum=-32768, maximum=32767),
            width=_actor_number(row, 'width', minimum=-32768, maximum=32767),
            height=_actor_number(row, 'height', minimum=-32768, maximum=32767),
            rom_order=0x8000 + overlay_index,
            port_to=_actor_number(row, 'portTo', minimum=0, maximum=65535),
            actor_class=actor_class,
            subtype=subtype,
            legs_color=legs_color,
            num=_actor_number(row, 'num', minimum=0, maximum=65535),
            state=_actor_number(row, 'state', minimum=0, maximum=255),
            route=_actor_number(row, 'route', minimum=0, maximum=255),
            dial=_actor_number(row, 'dial', minimum=0, maximum=255),
            turn=_actor_number(row, 'turn', minimum=0, maximum=255),
            level=level,
            setglobal=_actor_number(row, 'setglobal', minimum=0, maximum=255),
            visual_index=visual_for(actor_class, legs_color, subtype),
        )
        story.append(StoryActorSpec(overlay_index=overlay_index, level=level, descriptor=descriptor))

    routes_by_id: dict[int, list[tuple[int, int]]] = {route: [] for route in range(5)}
    for row in route_rows:
        route = int(row['route_id'])
        waypoint = int(row['waypoint_index'])
        if route not in routes_by_id:
            raise ValueError(f'route id {route} outside recovered table')
        if waypoint != len(routes_by_id[route]):
            raise ValueError(f'route {route} waypoint order is not contiguous')
        routes_by_id[route].append((int(row['x']), int(row['y'])))
    routes = tuple(tuple(routes_by_id[route]) for route in range(5))
    if any(len(route) != 6 for route in routes):
        raise ValueError('each recovered NPC route must contain six waypoints')

    result = ActorRuntimeData(
        physical=tuple(physical),
        level_indices={level: tuple(level_indices[level]) for level in LEVELS},
        story=tuple(story),
        routes=routes,
        visuals=tuple(visual_list),
    )
    if len(result.physical) != 241:
        raise ValueError(f'expected 241 non-Player actor descriptors, got {len(result.physical)}')
    if sum(len(v) for v in result.level_indices.values()) != 290:
        raise ValueError('unexpected level actor reference count')
    if len(result.story) != 16:
        raise ValueError('unexpected story-overlay count')
    return result


def pack_actor_sprite_bank(rom: bytes, visuals: tuple[tuple[int, int], ...]) -> PackedActorSpriteBank:
    """Pack exact frame-1 NPC source rows into contiguous 16x32 8bpp frames."""
    palette = _read_u16_array(rom, OBJ_PALETTE_SOURCE, 256)
    bias = npc_source_bias_from_rom(rom)
    source_base_off = OBJ_TILES_SOURCE - ROM_BASE
    out = bytearray()
    for legs_color, subtype in visuals:
        base = npc_source_base(bias, legs_color, subtype, 1)
        for row_base in npc_source_rows(base):
            for source_tile in (row_base, row_base + 1):
                off = source_base_off + source_tile * 64
                blob = rom[off:off + 64]
                if len(blob) != 64:
                    raise ValueError(f'NPC source tile {source_tile} overruns ROM')
                out.extend(blob)
    return PackedActorSpriteBank(frame_count=len(visuals), palette=palette, data=bytes(out))


def _read_u16_array(rom: bytes, addr: int, count: int) -> tuple[int, ...]:
    off = addr - ROM_BASE
    if off < 0 or off + count * 2 > len(rom):
        raise ValueError(f'u16 array at 0x{addr:08X} overruns ROM')
    return struct.unpack_from(f'<{count}H', rom, off)


def load_runtime_background(
    root: Path,
    rom: bytes,
    spec: LevelSpec,
    variant: int = 0,
) -> RuntimeBackground:
    descriptor = build_graphics_variants(root)[(spec.level, variant)]
    bg_tiles_addr = descriptor.bg_tiles_addr
    translation_addr = descriptor.translation_addr
    palette_addr = descriptor.palette_addr

    tile_off = bg_tiles_addr - ROM_BASE
    tile_bytes = rom[tile_off:tile_off + 0xD800]
    if len(tile_bytes) != 0xD800:
        raise ValueError('background tile blob overruns ROM')

    world_cells = spec.width * spec.height
    fixed_cells = spec.fixed_width * spec.fixed_height
    layer_a = _read_u16_array(rom, spec.visual_a_addr, world_cells)
    layer_b = _read_u16_array(rom, spec.visual_b_addr, world_cells)
    fixed_map = _read_u16_array(rom, spec.fixed_map_addr, fixed_cells)
    max_source = max((*layer_a, *layer_b, *fixed_map), default=0)
    translation = _read_u16_array(rom, translation_addr, max_source + 1)
    palette = _read_u16_array(rom, palette_addr, 256)

    return RuntimeBackground(
        palette=palette,
        tile_bytes=tile_bytes,
        translation=translation,
        layer_a=layer_a,
        layer_b=layer_b,
        fixed_map=fixed_map,
    )


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


def _asset_symbol(level: int, variant: int) -> str:
    return f'gb_level{level:02d}' if variant == 0 else f'gb_level{level:02d}_v{variant}'


def _asset_filename(level: int, variant: int) -> str:
    return f'level{level:02d}_assets.c' if variant == 0 else f'level{level:02d}_v{variant}_assets.c'


def _asset_c(
    level: int,
    variant: int,
    spec: LevelSpec,
    runtime: RuntimeBackground,
    collision: tuple[int, ...],
) -> str:
    portal_rows = []
    for p in spec.portals:
        portal_rows.append(f'    {{ {p.x}, {p.y}, {p.width}, {p.height}, {p.target_level}, {p.num} }}')
    portals = ',\n'.join(portal_rows) if portal_rows else '    { 0, 0, 0, 0, 0, 0 }'
    name = _asset_symbol(level, variant)
    tile_words = _bytes_to_u16(runtime.tile_bytes)
    return f"""#include <graveblood/assets.h>

const u16 {name}_bg_palette[256] = {{
{_c_values(runtime.palette, 10, 4)}
}};

const u16 {name}_bg_tiles[{len(tile_words)}] = {{
{_c_values(tile_words, 12, 4)}
}};

const u16 {name}_translation[{len(runtime.translation)}] = {{
{_c_values(runtime.translation, 12, 4)}
}};

const u16 {name}_layer_a[{len(runtime.layer_a)}] = {{
{_c_values(runtime.layer_a, 20)}
}};

const u16 {name}_layer_b[{len(runtime.layer_b)}] = {{
{_c_values(runtime.layer_b, 20)}
}};

const u16 {name}_fixed_map[{len(runtime.fixed_map)}] = {{
{_c_values(runtime.fixed_map, 20)}
}};

const u16 {name}_collision[{len(collision)}] = {{
{_c_values(collision, 24)}
}};

const GbPortal {name}_portals[{max(1, len(spec.portals))}] = {{
{portals}
}};

const GbLevelAssets {name}_assets = {{
    .level_id = {level},
    .graphics_variant = {variant},
    .world_width_tiles = {spec.width},
    .world_height_tiles = {spec.height},
    .fixed_width_tiles = {spec.fixed_width},
    .fixed_height_tiles = {spec.fixed_height},
    .spawn_x = {spec.spawn[0]},
    .spawn_y = {spec.spawn[1]},
    .bg_tile_halfwords = {len(tile_words)},
    .translation_count = {len(runtime.translation)},
    .bg_palette = {name}_bg_palette,
    .bg_tiles = {name}_bg_tiles,
    .translation = {name}_translation,
    .layer_a = {name}_layer_a,
    .layer_b = {name}_layer_b,
    .fixed_map = {name}_fixed_map,
    .collision = {name}_collision,
    .portals = {name}_portals,
    .portal_count = {len(spec.portals)},
}};
"""



def _player_c(sprite: PackedSprite) -> str:
    palette = [_bgr555(c) for c in sprite.palette] + [0] * (16 - len(sprite.palette))
    return f'''#include <graveblood/assets.h>\n\nconst u16 gb_player_obj_palette[16] = {{\n{_c_values(palette, 8, 4)}\n}};\n\nconst u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128] = {{\n{_c_values(_bytes_to_u16(sprite.data), 12, 4)}\n}};\n'''


def _actor_descriptor_c(d: ActorDescriptorSpec) -> str:
    return (
        f'{{ {d.x}, {d.y}, {d.width}, {d.height}, {d.rom_order}, {d.port_to}, '
        f'{d.num}, {d.actor_class}, {d.subtype}, {d.legs_color}, {d.state}, '
        f'{d.route}, {d.dial}, {d.turn}, {d.level}, {d.setglobal}, {d.visual_index} }}'
    )


def _actor_data_c(data: ActorRuntimeData) -> str:
    descriptor_rows = ',\n'.join('    ' + _actor_descriptor_c(d) for d in data.physical)
    flat_indices: list[int] = []
    spans: list[tuple[int, int]] = []
    for level in LEVELS:
        start = len(flat_indices)
        flat_indices.extend(data.level_indices[level])
        spans.append((start, len(data.level_indices[level])))
    story_rows = ',\n'.join(
        '    { ' + _actor_descriptor_c(item.descriptor) + f', {item.overlay_index} }}'
        for item in data.story
    )
    span_rows = ',\n'.join(f'    {{ {start}, {count} }}' for start, count in spans)
    return f"""#include <graveblood/assets.h>

const GbActorDescriptor gb_actor_descriptors[GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT] = {{
{descriptor_rows}
}};

const u16 gb_level_actor_indices[GB_ACTOR_LEVEL_REFERENCE_COUNT] = {{
{_c_values(flat_indices, 18)}
}};

const GbActorLevelIndexSpan gb_actor_level_spans[11] = {{
{span_rows}
}};

const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT] = {{
{story_rows}
}};
"""


def _actor_routes_c(data: ActorRuntimeData) -> str:
    route_rows = []
    for route in data.routes:
        points = ', '.join(f'{{ {x}, {y} }}' for x, y in route)
        route_rows.append(f'    {{ {points} }}')
    rows = ',\n'.join(route_rows)
    return f"""#include <graveblood/assets.h>

const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS] = {{
{rows}
}};
"""


def _actor_sprite_c(data: ActorRuntimeData, sprites: PackedActorSpriteBank) -> str:
    visuals = ',\n'.join(f'    {{ {legs}, {subtype} }}' for legs, subtype in data.visuals)
    words = _bytes_to_u16(sprites.data)
    return f"""#include <graveblood/assets.h>

const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT] = {{
{visuals}
}};

const u16 gb_actor_obj_palette[256] = {{
{_c_values(sprites.palette, 10, 4)}
}};

const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_FRAME_HALFWORDS] = {{
{_c_values(words, 12, 4)}
}};
"""


def _assets_h(variants: dict[tuple[int, int], GraphicsVariantSpec]) -> str:
    declarations = '\n'.join(
        f'extern const GbLevelAssets {_asset_symbol(level, variant)}_assets;'
        for level, variant in sorted(variants)
    )
    return f"""#ifndef GRAVEBLOOD_ASSETS_H
#define GRAVEBLOOD_ASSETS_H

#include <gba.h>

typedef struct {{
    s16 x;
    s16 y;
    u8 width;
    u8 height;
    u16 target_level;
    u16 num;
}} GbPortal;

typedef enum {{
    GB_ACTOR_NPC = 0,
    GB_ACTOR_GRASS = 1,
    GB_ACTOR_FGTILE = 2,
    GB_ACTOR_LEAVES = 3,
}} GbActorClass;

typedef struct {{
    s16 x;
    s16 y;
    s16 width;
    s16 height;
    u16 rom_order;
    u16 port_to;
    u16 num;
    u8 actor_class;
    u8 subtype;
    u8 legs_color;
    u8 state;
    u8 route;
    u8 dial;
    u8 turn;
    u8 level;
    u8 setglobal;
    u8 visual_index;
}} GbActorDescriptor;

typedef struct {{
    GbActorDescriptor actor;
    u8 overlay_index;
}} GbStoryActorDescriptor;

typedef struct {{
    u16 offset;
    u16 count;
}} GbActorLevelIndexSpan;

typedef struct {{
    s16 x;
    s16 y;
}} GbRoutePoint;

typedef struct {{
    u8 legs_color;
    u8 subtype;
}} GbActorVisualSpec;

typedef struct {{
    u8 level_id;
    u8 graphics_variant;
    u16 world_width_tiles;
    u16 world_height_tiles;
    u16 fixed_width_tiles;
    u16 fixed_height_tiles;
    s16 spawn_x;
    s16 spawn_y;
    u16 bg_tile_halfwords;
    u16 translation_count;
    const u16* bg_palette;
    const u16* bg_tiles;
    const u16* translation;
    const u16* layer_a;
    const u16* layer_b;
    const u16* fixed_map;
    const u16* collision;
    const GbPortal* portals;
    u8 portal_count;
}} GbLevelAssets;

{declarations}

const GbLevelAssets* gb_level_assets(int level_id, int graphics_variant);
const GbLevelAssets* gb_level_default_assets(int level_id);

enum {{
    GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT = 241,
    GB_ACTOR_LEVEL_REFERENCE_COUNT = 290,
    GB_ACTOR_STORY_DESCRIPTOR_COUNT = 16,
    GB_ACTOR_ROUTE_COUNT = 5,
    GB_ACTOR_ROUTE_POINTS = 6,
    GB_ACTOR_VISUAL_COUNT = 32,
    GB_ACTOR_FRAME_HALFWORDS = 256,
}};

extern const GbActorDescriptor gb_actor_descriptors[GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT];
extern const u16 gb_level_actor_indices[GB_ACTOR_LEVEL_REFERENCE_COUNT];
extern const GbActorLevelIndexSpan gb_actor_level_spans[11];
extern const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT];
extern const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS];
extern const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT];
extern const u16 gb_actor_obj_palette[256];
extern const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_FRAME_HALFWORDS];

enum {{ GB_PLAYER_FRAME_COUNT = 16 }};

extern const u16 gb_player_obj_palette[16];
extern const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128];

#endif
"""


def _registry_c(variants: dict[tuple[int, int], GraphicsVariantSpec]) -> str:
    rows = []
    for level in LEVELS:
        cases = []
        for variant in sorted(v for (lvl, v) in variants if lvl == level):
            symbol = _asset_symbol(level, variant)
            cases.append(f'        case {variant}: return &{symbol}_assets;')
        cases_text = '\n'.join(cases)
        rows.append(
            f'    case {level}:\n'
            f'        switch(graphics_variant)\n'
            f'        {{\n{cases_text}\n        default: return 0;\n        }}'
        )
    rows_text = '\n'.join(rows)
    return f"""#include <graveblood/assets.h>

const GbLevelAssets* gb_level_assets(int level_id, int graphics_variant)
{{
    switch(level_id)
    {{
{rows_text}
    default:
        return 0;
    }}
}}

const GbLevelAssets* gb_level_default_assets(int level_id)
{{
    return gb_level_assets(level_id, 0);
}}
"""



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
    variants = build_graphics_variants(root)
    rom_file = _find_rom(root, rom_path)
    rom = rom_file.read_bytes()
    actor_data = build_actor_runtime_data(root)
    actor_sprites = pack_actor_sprite_bank(rom, actor_data.visuals)

    for level, variant in sorted(variants):
        spec = specs[level]
        runtime = load_runtime_background(root, rom, spec, variant)
        collision = _read_collision(rom, spec)
        (out / 'data' / _asset_filename(level, variant)).write_text(
            _asset_c(level, variant, spec, runtime, collision), encoding='utf-8'
        )

    # These compact Tiled helper files are editor conveniences, not runtime assets.
    # Keep them only for the two small currently-authored levels; large worlds use
    # the streamed source arrays above and are not flattened into a 256-tile sheet.
    for level in (7, 8):
        spec = specs[level]
        bg = pack_background(load_world_image(root, level))
        _tilesheet(bg).save(out / 'maps' / 'generated' / f'level{level:02d}_tiles.png', optimize=False)
        (out / 'maps' / f'level{level:02d}.tmx').write_text(_tmx(level, spec, bg), encoding='utf-8')

    sprite = pack_player_animation(rom)
    (out / 'data' / 'player_sprite.c').write_text(_player_c(sprite), encoding='utf-8')
    (out / 'data' / 'actor_data.c').write_text(_actor_data_c(actor_data), encoding='utf-8')
    (out / 'data' / 'actor_routes.c').write_text(_actor_routes_c(actor_data), encoding='utf-8')
    (out / 'data' / 'actor_sprite_data.c').write_text(_actor_sprite_c(actor_data, actor_sprites), encoding='utf-8')
    (out / 'data' / 'level_registry.c').write_text(_registry_c(variants), encoding='utf-8')
    (out / 'include' / 'graveblood' / 'assets.h').write_text(_assets_h(variants), encoding='utf-8')


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
