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
FONT_TABLE_ADDR = 0x080199A0
FONT_GLYPH_COUNT = 127
MONSTER_TILE_ARGS = (0x159, 0x178, 0x17A, 0x198, 0x19A)
LEVEL_STATIC_TILE_ARGS = (0x17C, 0x17E, 0x19C, 0x19E)
BG0_UI_TILE_COUNT = 87
ENDING_ARG0_COPY1_SOURCE = 0x08641361
ENDING_ARG0_COPY1_BYTES = 96000
ENDING_ARG0_COPY2_SOURCE = 0x0836EE54
ENDING_ARG0_COPY2_BYTES = 16000


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
    player_idle_selector: int
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
    player_indices: tuple[int, ...]
    story: tuple[StoryActorSpec, ...]
    routes: tuple[tuple[tuple[int, int], ...], ...]
    visuals: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PackedActorSpriteBank:
    frame_count: int
    palette: tuple[int, ...]
    data: bytes


@dataclass(frozen=True)
class PackedForegroundSpriteBank:
    grass: bytes
    leaf_frames: bytes


@dataclass(frozen=True)
class DialogueRecordSpec:
    speaker: str
    text: str
    opcode: int
    argument: int


@dataclass(frozen=True)
class MessageRecordSpec:
    stream_id: int
    story_stage: int
    title: str
    sender: str
    body: str


@dataclass(frozen=True)
class SocialProfileSpec:
    selector: int
    name: str
    topic_ratings: tuple[int, ...]


@dataclass(frozen=True)
class SocialActionSpec:
    index: int
    label: str
    node_type: int
    field_24: int
    field_28: int
    child_base: int


@dataclass(frozen=True)
class SocialResponseSpec:
    action: str
    topic_index: int
    slot: int
    profile_value_class: int
    variant: int
    text: str


@dataclass(frozen=True)
class StoryRuntimeData:
    dialogue_scripts: tuple[tuple[DialogueRecordSpec, ...], ...]
    messages: tuple[MessageRecordSpec, ...]
    social_profiles: tuple[SocialProfileSpec, ...]
    social_actions: tuple[SocialActionSpec, ...]
    subject_topics: tuple[str, ...]
    ask_topics: tuple[str, ...]
    criticize_topics: tuple[str, ...]
    social_responses: tuple[SocialResponseSpec, ...]


@dataclass(frozen=True)
class FontGlyphSpec:
    pixel_width: int
    rows: tuple[int, ...]
    control: bool


@dataclass(frozen=True)
class CanonicalFont:
    bitmap_base_index: int
    glyphs: tuple[FontGlyphSpec, ...]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def build_story_runtime_data(root: Path) -> StoryRuntimeData:
    dialogue_rows = _read_csv(root / 'data' / 'dialogue_scripts.csv')
    scripts: list[list[DialogueRecordSpec]] = [[] for _ in range(7)]
    for row in dialogue_rows:
        dial = int(row['dial_index'])
        step = int(row['step'])
        if not 0 <= dial < len(scripts):
            raise ValueError(f'unsupported dialogue script {dial}')
        if step != len(scripts[dial]):
            raise ValueError(f'non-contiguous dialogue script {dial} step {step}')
        scripts[dial].append(DialogueRecordSpec(
            speaker=row['speaker'],
            text=row['text'],
            opcode=int(row['opcode']),
            argument=int(row['argument']),
        ))

    messages = tuple(
        MessageRecordSpec(
            stream_id=int(row['stream_id']),
            story_stage=int(row['story_stage']),
            title=row['title'],
            sender=row['sender'],
            body=row['body'],
        )
        for row in _read_csv(root / 'data' / 'message_streams.csv')
    )

    profile_rows = _read_csv(root / 'data' / 'player_interaction_social_profile_topics.csv')
    grouped_profiles: dict[int, list[dict[str, str]]] = {0: [], 1: []}
    for row in profile_rows:
        selector = int(row['selector_index'])
        if selector in grouped_profiles:
            grouped_profiles[selector].append(row)
    profiles: list[SocialProfileSpec] = []
    for selector in (0, 1):
        rows = sorted(grouped_profiles[selector], key=lambda r: int(r['topic_index']))
        if len(rows) != 9 or [int(r['topic_index']) for r in rows] != list(range(9)):
            raise ValueError(f'incomplete social profile {selector}')
        profiles.append(SocialProfileSpec(
            selector=selector,
            name=rows[0]['name'],
            topic_ratings=tuple(int(r['rating']) for r in rows),
        ))

    actions = tuple(
        SocialActionSpec(
            index=int(row['index']),
            label=row['label'],
            node_type=int(row['node_type']),
            field_24=int(row['field_24']),
            field_28=int(row['field_28']),
            child_base=int(row['child_base']) if row['child_base'] else 0,
        )
        for row in _read_csv(root / 'data' / 'player_interaction_action_table.csv')
    )

    secondary = {
        row['action_label']: tuple(part for part in row['topics'].split('|') if part)
        for row in _read_csv(root / 'data' / 'player_interaction_secondary_topics.csv')
    }
    responses = tuple(
        SocialResponseSpec(
            action=row['action'],
            topic_index=int(row['topic_index']),
            slot=int(row['slot']),
            profile_value_class=int(row['profile_value_class']),
            variant=int(row['variant']),
            text=row['text'],
        )
        for row in _read_csv(root / 'data' / 'player_interaction_topic_response_texts.csv')
    )
    return StoryRuntimeData(
        dialogue_scripts=tuple(tuple(script) for script in scripts),
        messages=messages,
        social_profiles=tuple(profiles),
        social_actions=actions,
        subject_topics=secondary['SUBJECT'],
        ask_topics=secondary['Ask about'],
        criticize_topics=secondary['CRITICIZE'],
        social_responses=responses,
    )


def extract_canonical_font(rom: bytes) -> CanonicalFont:
    off = FONT_TABLE_ADDR - ROM_BASE
    if off < 0 or off + FONT_GLYPH_COUNT * 2 > len(rom):
        raise ValueError('canonical font table outside ROM')
    entries = struct.unpack_from(f'<{FONT_GLYPH_COUNT}H', rom, off)
    bitmap_base = entries[0]
    glyphs: list[FontGlyphSpec] = []
    for code, raw in enumerate(entries):
        signed = raw if raw < 0x8000 else raw - 0x10000
        if code == 0 or signed < 0:
            glyphs.append(FontGlyphSpec(0, (0,) * 8, code != 0))
            continue
        pair_width = (signed >> 10) & 0x1F
        pixel_width = pair_width * 2
        bitmap_offset = raw & 0x03FF
        rows = [0] * 8
        for pair in range(pair_width):
            word_off = off + 2 * (bitmap_base + bitmap_offset + pair)
            if word_off + 2 > len(rom):
                raise ValueError(f'font glyph {code} bitmap outside ROM')
            word = struct.unpack_from('<H', rom, word_off)[0]
            for y in range(8):
                bits = (word >> (y * 2)) & 0x03
                if bits & 1:
                    rows[y] |= 1 << (pair * 2)
                if bits & 2:
                    rows[y] |= 1 << (pair * 2 + 1)
        glyphs.append(FontGlyphSpec(pixel_width, tuple(rows), False))
    return CanonicalFont(bitmap_base, tuple(glyphs))


def pack_monster_sprite_bank(rom: bytes) -> PackedActorSpriteBank:
    src_base = OBJ_TILES_SOURCE - ROM_BASE
    if src_base < 0 or src_base + 0x8000 > len(rom):
        raise ValueError('initial OBJ source outside ROM')
    initial = rom[src_base:src_base + 0x8000]
    packed = bytearray()
    for tile_arg in MONSTER_TILE_ARGS:
        base = tile_arg & 0x1FF
        for logical in (base, base + 1, base + 16, base + 17):
            start = logical * 64
            packed.extend(initial[start:start + 64])
    palette_off = OBJ_PALETTE_SOURCE - ROM_BASE
    palette = struct.unpack_from('<256H', rom, palette_off)
    return PackedActorSpriteBank(len(MONSTER_TILE_ARGS), tuple(palette), bytes(packed))


def pack_level_static_obj_bank(rom: bytes) -> PackedActorSpriteBank:
    """Pack the four initial-OBJ 16x16 pieces drawn by Player_draw in Levels 9/10."""
    src_base = OBJ_TILES_SOURCE - ROM_BASE
    if src_base < 0 or src_base + 0x8000 > len(rom):
        raise ValueError('initial OBJ source outside ROM')
    initial = rom[src_base:src_base + 0x8000]
    packed = bytearray()
    for tile_arg in LEVEL_STATIC_TILE_ARGS:
        base = tile_arg & 0x1FF
        for logical in (base, base + 1, base + 16, base + 17):
            start = logical * 64
            packed.extend(initial[start:start + 64])
    palette_off = OBJ_PALETTE_SOURCE - ROM_BASE
    palette = struct.unpack_from('<256H', rom, palette_off)
    return PackedActorSpriteBank(len(LEVEL_STATIC_TILE_ARGS), tuple(palette), bytes(packed))


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
                x=_actor_number(actor, 'x'),
                y=_actor_number(actor, 'y'),
                width=_actor_number(actor, 'width'),
                height=_actor_number(actor, 'height'),
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
            player_idle_selector=int(row['record_flag_3c']),
            portals=tuple(portals),
        )
    return out


def _actor_number(row: dict[str, str], field: str, *, default: int = 0,
                  minimum: int = -32768, maximum: int = 65535) -> int:
    raw = row.get(field, '')
    value = default if raw == '' else int(float(raw))
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
    level_object_counts: dict[int, int] = {level: 0 for level in LEVELS}
    player_indices: dict[int, int] = {}
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
        for level in refs:
            if actor_class == ACTOR_CLASS_PLAYER:
                if level in player_indices:
                    raise ValueError(f'level {level} has multiple Player records')
                player_indices[level] = level_object_counts[level]
            level_object_counts[level] += 1
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
            setglobal=_actor_number(row, 'setglobal', default=1, minimum=0, maximum=255),
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

    # NPC_update state 3 rewrites actor+0x4E from the serialized base family to
    # base+8 for horizontal/down motion and base+16 for upward motion.  These
    # moving families are not separate serialized actors, so append their exact
    # ROM source pairs after descriptor indexing is complete to keep every
    # existing descriptor visual_index stable.
    for item in story:
        descriptor = item.descriptor
        if descriptor.actor_class != ACTOR_CLASS_NPC or descriptor.state != 3:
            continue
        for legs_color in (descriptor.legs_color + 8, descriptor.legs_color + 16):
            key = (legs_color, descriptor.subtype)
            if key not in visual_index:
                found = len(visual_list)
                if found >= ACTOR_VISUAL_NONE:
                    raise ValueError('too many actor visuals for u8 visual index')
                visual_index[key] = found
                visual_list.append(key)

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

    expected_player_indices = (8, 2, 0, 0, 0, 0, 8, 0, 4, 2, 1)
    actual_player_indices = tuple(player_indices.get(level, -1) for level in LEVELS)
    if actual_player_indices != expected_player_indices:
        raise ValueError(
            f'Player physical insertion indices drifted: {actual_player_indices!r}'
        )

    result = ActorRuntimeData(
        physical=tuple(physical),
        level_indices={level: tuple(level_indices[level]) for level in LEVELS},
        player_indices=actual_player_indices,
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
    """Pack all eight ROM-addressable NPC frames for each recovered visual."""
    palette = _read_u16_array(rom, OBJ_PALETTE_SOURCE, 256)
    bias = npc_source_bias_from_rom(rom)
    source_base_off = OBJ_TILES_SOURCE - ROM_BASE
    out = bytearray()
    for legs_color, subtype in visuals:
        for frame in range(1, 9):
            base = npc_source_base(bias, legs_color, subtype, frame)
            for row_base in npc_source_rows(base):
                for source_tile in (row_base, row_base + 1):
                    off = source_base_off + source_tile * 64
                    blob = rom[off:off + 64]
                    if len(blob) != 64:
                        raise ValueError(f'NPC source tile {source_tile} overruns ROM')
                    out.extend(blob)
    return PackedActorSpriteBank(frame_count=len(visuals) * 8, palette=palette, data=bytes(out))


def pack_foreground_sprite_bank(rom: bytes) -> PackedForegroundSpriteBank:
    """Pack exact initial-OBJ grass and leaf tiles for the 1D clean-room layout.

    The original uses 2D OBJ mapping.  Grass logical tile 0x48 therefore uses
    rows 0x48/0x49 and 0x58/0x59.  The leaf particle frame table points at
    four independent 8x8 tiles: 0x4C, 0x4D, 0x5C, 0x5D.
    """
    source_base = OBJ_TILES_SOURCE - ROM_BASE
    if source_base < 0 or source_base + 0x8000 > len(rom):
        raise ValueError('initial OBJ source outside ROM')

    def tile(logical: int) -> bytes:
        off = source_base + logical * 64
        blob = rom[off:off + 64]
        if len(blob) != 64:
            raise ValueError(f'foreground OBJ tile {logical} overruns ROM')
        return blob

    grass = b''.join(tile(index) for index in (0x48, 0x49, 0x58, 0x59))
    leaf_frames = b''.join(tile(index) for index in (0x4C, 0x4D, 0x5C, 0x5D))
    return PackedForegroundSpriteBank(grass=grass, leaf_frames=leaf_frames)


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


def select_bg0_ui_tiles(runtime: RuntimeBackground, count: int = BG0_UI_TILE_COUNT) -> tuple[int, ...]:
    """Return world-unreferenced 8bpp tile IDs below screenblock 27."""
    used_sources = set(runtime.layer_a) | set(runtime.layer_b) | set(runtime.fixed_map)
    used_tiles = {
        runtime.translation[source] & 0x03FF
        for source in used_sources
        if source < len(runtime.translation)
    }
    safe = tuple(tile for tile in range(864) if tile not in used_tiles)
    if len(safe) < count:
        raise ValueError(f'need {count} BG0 UI tiles, only {len(safe)} world-safe IDs exist')
    return safe[:count]


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
    packed_sources = (sources['regular_walk'] + sources['up_walk'] +
                      sources['idle_unique'] + sources['idle_selector1'])
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


def pack_player_bicycle_animation(rom: bytes) -> bytes:
    """Materialize Player_draw's six-frame, five-sprite bicycle composition.

    The original remains in 2D OBJ mode and dynamically stages five source
    ranges into logical tiles 0x151/0x160/0x170/0x180/0x190.  The clean-room
    game uses 1D OBJ mapping, so each of the five submitted 16x16 roots is
    repacked into contiguous 1D tile order while preserving exact 8bpp palette
    indices.  The six source offsets are the ROM table at 0x08019968.
    """
    frame_offsets = struct.unpack_from('<6I', rom, 0x08019968 - ROM_BASE)
    if frame_offsets != (0, 4, 8, 0x50, 0x54, 0x58):
        raise ValueError(f'unexpected bicycle frame offsets: {frame_offsets!r}')

    source_off = OBJ_TILES_SOURCE - ROM_BASE
    initial = bytearray(rom[source_off:source_off + 0x8000])
    if len(initial) != 0x8000:
        raise ValueError('initial OBJ bank truncated while packing bicycle frames')

    out = bytearray()
    for frame_offset in frame_offsets:
        vram = bytearray(initial)
        uploads = (
            (0x151, frame_offset + 0x1501, 2),
            (0x160, frame_offset + 0x1510, 4),
            (0x170, frame_offset + 0x1520, 4),
            (0x180, frame_offset + 0x1530, 4),
            (0x190, frame_offset + 0x1540, 4),
        )
        for dst_tile, src_tile, count in uploads:
            src = source_off + src_tile * 64
            blob = rom[src:src + count * 64]
            if len(blob) != count * 64:
                raise ValueError(f'bicycle source tile 0x{src_tile:X} overruns ROM')
            dst = dst_tile * 64
            vram[dst:dst + count * 64] = blob

        for root_tile in (0x151, 0x170, 0x172, 0x190, 0x192):
            for tile_y in range(2):
                for tile_x in range(2):
                    tile = root_tile + tile_x + tile_y * 16
                    out.extend(vram[tile * 64:(tile + 1) * 64])

    if len(out) != 6 * 5 * 4 * 64:
        raise ValueError('unexpected bicycle packed size')
    return bytes(out)


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
    ui_tiles = select_bg0_ui_tiles(runtime)
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

const u16 {name}_bg0_ui_tiles[GB_BG0_UI_TILE_COUNT] = {{
{_c_values(ui_tiles, 16)}
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
    .player_idle_selector = {spec.player_idle_selector},
    .bg_tile_halfwords = {len(tile_words)},
    .translation_count = {len(runtime.translation)},
    .bg_palette = {name}_bg_palette,
    .bg_tiles = {name}_bg_tiles,
    .translation = {name}_translation,
    .layer_a = {name}_layer_a,
    .layer_b = {name}_layer_b,
    .fixed_map = {name}_fixed_map,
    .collision = {name}_collision,
    .bg0_ui_tiles = {name}_bg0_ui_tiles,
    .portals = {name}_portals,
    .portal_count = {len(spec.portals)},
}};
"""



def _player_c(sprite: PackedSprite) -> str:
    palette = [_bgr555(c) for c in sprite.palette] + [0] * (16 - len(sprite.palette))
    return f'''#include <graveblood/assets.h>\n\nconst u16 gb_player_obj_palette[16] = {{\n{_c_values(palette, 8, 4)}\n}};\n\nconst u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128] = {{\n{_c_values(_bytes_to_u16(sprite.data), 12, 4)}\n}};\n'''


def _player_bicycle_c(data: bytes) -> str:
    return f"""#include <graveblood/assets.h>

const u16 gb_player_bicycle_obj_frames[GB_PLAYER_BICYCLE_FRAME_COUNT * GB_PLAYER_BICYCLE_FRAME_HALFWORDS] = {{
{_c_values(_bytes_to_u16(data), 12, 4)}
}};
"""


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

const u8 gb_player_physical_indices[11] = {{
{_c_values(data.player_indices, 11)}
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


def _actor_sprite_c(
    data: ActorRuntimeData, sprites: PackedActorSpriteBank, foreground: PackedForegroundSpriteBank
) -> str:
    visuals = ',\n'.join(f'    {{ {legs}, {subtype} }}' for legs, subtype in data.visuals)
    words = _bytes_to_u16(sprites.data)
    grass_words = _bytes_to_u16(foreground.grass)
    leaf_words = _bytes_to_u16(foreground.leaf_frames)
    return f"""#include <graveblood/assets.h>

const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT] = {{
{visuals}
}};

const u16 gb_actor_obj_palette[256] = {{
{_c_values(sprites.palette, 10, 4)}
}};

const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_MAX_FRAMES * GB_ACTOR_FRAME_HALFWORDS] = {{
{_c_values(words, 12, 4)}
}};

const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = {{
{_c_values(grass_words, 12, 4)}
}};

const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {{
{_c_values(leaf_words, 12, 4)}
}};
"""


def _c_string(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'


def _story_data_c(data: StoryRuntimeData) -> str:
    record_blocks: list[str] = []
    script_rows: list[str] = []
    for dial, script in enumerate(data.dialogue_scripts):
        rows = ',\n'.join(
            f'    {{ {_c_string(rec.speaker)}, {_c_string(rec.text)}, {rec.opcode}, {rec.argument} }}'
            for rec in script
        )
        record_blocks.append(
            f'static const GbDialogueRecord gb_dialogue_script_{dial}[{len(script)}] = {{\n{rows}\n}};'
        )
        script_rows.append(f'    {{ gb_dialogue_script_{dial}, {len(script)} }}')

    message_rows = ',\n'.join(
        f'    {{ {m.stream_id}, {m.story_stage}, {_c_string(m.title)}, {_c_string(m.sender)}, {_c_string(m.body)} }}'
        for m in data.messages
    )
    profile_rows = ',\n'.join(
        '    { ' + _c_string(p.name) + ', { ' + ', '.join(str(v) for v in p.topic_ratings) + ' } }'
        for p in data.social_profiles
    )
    action_rows = ',\n'.join(
        f'    {{ {_c_string(a.label)}, {a.node_type}, {a.field_24}, {a.field_28}, {a.child_base} }}'
        for a in data.social_actions
    )

    def string_array(name: str, values: tuple[str, ...]) -> str:
        rows = ',\n'.join(f'    {_c_string(value)}' for value in values)
        return f'const char* const {name}[{len(values)}] = {{\n{rows}\n}};'

    response_rows = ',\n'.join(
        f'    {{ {0 if r.action == "SUBJECT" else 3}, {r.topic_index}, {r.slot}, '
        f'{r.profile_value_class}, {r.variant}, {_c_string(r.text)} }}'
        for r in data.social_responses
    )
    return f"""#include <graveblood/assets.h>

{chr(10).join(record_blocks)}

const GbDialogueScript gb_dialogue_scripts[GB_DIALOGUE_SCRIPT_COUNT] = {{
{',\n'.join(script_rows)}
}};

const GbMessageRecord gb_message_records[GB_MESSAGE_RECORD_COUNT] = {{
{message_rows}
}};

const GbSocialProfileData gb_social_profiles[GB_SOCIAL_PROFILE_COUNT] = {{
{profile_rows}
}};

const GbSocialActionData gb_social_actions[GB_SOCIAL_ACTION_COUNT] = {{
{action_rows}
}};

{string_array('gb_social_subject_topics', data.subject_topics)}
{string_array('gb_social_ask_topics', data.ask_topics)}
{string_array('gb_social_criticize_topics', data.criticize_topics)}

const GbSocialResponseData gb_social_responses[GB_SOCIAL_RESPONSE_COUNT] = {{
{response_rows}
}};
"""


def _font_data_c(font: CanonicalFont) -> str:
    rows = ',\n'.join(
        f'    {{ {glyph.pixel_width}, {{ ' + ', '.join(f'0x{row:04X}' for row in glyph.rows) + ' } }'
        for glyph in font.glyphs
    )
    return f"""#include <graveblood/assets.h>

const GbFontGlyph gb_font_glyphs[GB_FONT_GLYPH_COUNT] = {{
{rows}
}};
"""


def _monster_sprite_c(monster: PackedActorSpriteBank, level_static: PackedActorSpriteBank) -> str:
    return f"""#include <graveblood/assets.h>

const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {{
{_c_values(_bytes_to_u16(monster.data), 12, 4)}
}};

const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {{
{_c_values(_bytes_to_u16(level_static.data), 12, 4)}
}};
"""


def _assets_h(variants: dict[tuple[int, int], GraphicsVariantSpec], actor_visual_count: int) -> str:
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
    const char* speaker;
    const char* text;
    s16 opcode;
    s16 argument;
}} GbDialogueRecord;

typedef struct {{
    const GbDialogueRecord* records;
    u16 count;
}} GbDialogueScript;

typedef struct {{
    u8 stream_id;
    s8 story_stage;
    const char* title;
    const char* sender;
    const char* body;
}} GbMessageRecord;

typedef struct {{
    const char* name;
    s8 topic_ratings[9];
}} GbSocialProfileData;

typedef struct {{
    const char* label;
    u8 node_type;
    u8 field_24;
    u8 field_28;
    u8 child_base;
}} GbSocialActionData;

typedef struct {{
    u8 quadrant;
    u8 topic_index;
    u8 slot;
    u8 profile_value_class;
    u8 variant;
    const char* text;
}} GbSocialResponseData;

typedef struct {{
    u8 pixel_width;
    u16 rows[8];
}} GbFontGlyph;

typedef enum {{
    GB_AUDIO_ROLE_MUSIC = 0,
    GB_AUDIO_ROLE_SFX = 1,
}} GbAudioRole;

typedef struct {{
    const s8* data;
    u32 byte_length;
    u8 role;
}} GbAudioSample;

typedef struct {{
    u8 level_id;
    u8 graphics_variant;
    u16 world_width_tiles;
    u16 world_height_tiles;
    u16 fixed_width_tiles;
    u16 fixed_height_tiles;
    s16 spawn_x;
    s16 spawn_y;
    u8 player_idle_selector;
    u16 bg_tile_halfwords;
    u16 translation_count;
    const u16* bg_palette;
    const u16* bg_tiles;
    const u16* translation;
    const u16* layer_a;
    const u16* layer_b;
    const u16* fixed_map;
    const u16* collision;
    const u16* bg0_ui_tiles;
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
    GB_ACTOR_VISUAL_COUNT = {actor_visual_count},
    GB_ACTOR_MAX_FRAMES = 8,
    GB_ACTOR_FRAME_HALFWORDS = 256,
    GB_GRASS_OBJ_HALFWORDS = 128,
    GB_LEAF_FRAME_COUNT = 4,
    GB_LEAF_FRAME_HALFWORDS = 32,
    GB_DIALOGUE_SCRIPT_COUNT = 7,
    GB_DIALOGUE_RECORD_COUNT = 58,
    GB_MESSAGE_RECORD_COUNT = 6,
    GB_SOCIAL_PROFILE_COUNT = 2,
    GB_SOCIAL_ACTION_COUNT = 20,
    GB_SOCIAL_SUBJECT_TOPIC_COUNT = 9,
    GB_SOCIAL_ASK_TOPIC_COUNT = 5,
    GB_SOCIAL_CRITICIZE_TOPIC_COUNT = 9,
    GB_SOCIAL_RESPONSE_COUNT = 216,
    GB_FONT_GLYPH_COUNT = 127,
    GB_MONSTER_SPRITE_COUNT = 5,
    GB_MONSTER_SPRITE_HALFWORDS = 128,
    GB_LEVEL_STATIC_SPRITE_COUNT = 4,
    GB_LEVEL_STATIC_SPRITE_HALFWORDS = 128,
    GB_BG0_UI_TILE_COUNT = 87,
    GB_TITLE_MAP_WIDTH = 30,
    GB_TITLE_MAP_HEIGHT = 20,
    GB_TITLE_MAP_CELLS = 600,
    GB_TITLE_ANIMATION_STATES = 4,
    GB_TITLE_ANIM_A_HALFWORDS = 1536,
    GB_TITLE_ANIM_B_HALFWORDS = 768,
    GB_TITLE_PROMPT_LENGTH = 14,
    GB_TITLE_BG_PALETTE_COUNT = 223,
    GB_TITLE_OBJ_TILE_HALFWORDS = 0x8000 / 2,
    GB_TITLE_OBJ_PALETTE_COUNT = 91,
    GB_TITLE_OBJ_HIGH_PALETTE_COUNT = 32,
    GB_PDA_PAGE_COUNT = 4,
    GB_PDA_MAP_WIDTH = 30,
    GB_PDA_MAP_HEIGHT = 20,
    GB_PDA_MAP_CELLS = 600,
    GB_PDA_FRIEND_COUNT = 6,
    GB_PDA_TEXT_COLUMNS = 29,
    GB_PDA_TEXT_ROWS = 5,
    GB_PDA_TEXT_TILE_COUNT = 145,
    GB_WARDROBE_CHOICE_COUNT = 7,
    GB_WARDROBE_BG_PAGE_HALFWORDS = 4096,
    GB_WARDROBE_PREVIEW_HALFWORDS = 256,
    GB_AUDIO_SAMPLE_COUNT = 14,
    GB_AUDIO_MUSIC_SAMPLE_COUNT = 3,
    GB_ENDING_ARG0_COPY1_BYTES = 96000,
    GB_ENDING_ARG0_COPY2_BYTES = 16000,
    GB_ENDING_VRAM_BYTES = 0x18000,
    GB_ENDING_OBJ_VRAM_OFFSET = 0x10000,
}};

extern const GbActorDescriptor gb_actor_descriptors[GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT];
extern const u16 gb_level_actor_indices[GB_ACTOR_LEVEL_REFERENCE_COUNT];
extern const GbActorLevelIndexSpan gb_actor_level_spans[11];
extern const u8 gb_player_physical_indices[11];
extern const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT];
extern const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS];
extern const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT];
extern const u16 gb_actor_obj_palette[256];
extern const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_MAX_FRAMES * GB_ACTOR_FRAME_HALFWORDS];
extern const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS];
extern const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS];
extern const GbDialogueScript gb_dialogue_scripts[GB_DIALOGUE_SCRIPT_COUNT];
extern const GbMessageRecord gb_message_records[GB_MESSAGE_RECORD_COUNT];
extern const GbSocialProfileData gb_social_profiles[GB_SOCIAL_PROFILE_COUNT];
extern const GbSocialActionData gb_social_actions[GB_SOCIAL_ACTION_COUNT];
extern const char* const gb_social_subject_topics[GB_SOCIAL_SUBJECT_TOPIC_COUNT];
extern const char* const gb_social_ask_topics[GB_SOCIAL_ASK_TOPIC_COUNT];
extern const char* const gb_social_criticize_topics[GB_SOCIAL_CRITICIZE_TOPIC_COUNT];
extern const GbSocialResponseData gb_social_responses[GB_SOCIAL_RESPONSE_COUNT];
extern const GbFontGlyph gb_font_glyphs[GB_FONT_GLYPH_COUNT];
extern const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS];
extern const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS];
extern const u16 gb_title_bg_tiles[0xD800 / 2];
extern const u16 gb_title_bg_palette[GB_TITLE_BG_PALETTE_COUNT];
extern const u16 gb_title_obj_tiles[GB_TITLE_OBJ_TILE_HALFWORDS];
extern const u16 gb_title_obj_palette[GB_TITLE_OBJ_PALETTE_COUNT];
extern const u16 gb_title_obj_high_palette[GB_TITLE_OBJ_HIGH_PALETTE_COUNT];
extern const u16 gb_title_underlay_tile;
extern const u16 gb_title_map[GB_TITLE_MAP_CELLS];
extern const u16 gb_title_anim_a[GB_TITLE_ANIMATION_STATES][GB_TITLE_ANIM_A_HALFWORDS];
extern const u16 gb_title_anim_b[GB_TITLE_ANIMATION_STATES][GB_TITLE_ANIM_B_HALFWORDS];
extern const u16 gb_title_prompt_tiles[GB_TITLE_PROMPT_LENGTH];
extern const u16 gb_title_blank_tiles[GB_TITLE_PROMPT_LENGTH];
extern const u16 gb_pda_page_maps[GB_PDA_PAGE_COUNT][GB_PDA_MAP_CELLS];
extern const char* const gb_pda_friend_names[GB_PDA_FRIEND_COUNT];
extern const u16 gb_pda_text_tile_ids[GB_PDA_TEXT_TILE_COUNT];
extern const u8 gb_wardrobe_bg_page_indices[GB_WARDROBE_CHOICE_COUNT];
extern const u8 gb_wardrobe_obj_banks[GB_WARDROBE_CHOICE_COUNT];
extern const char* const gb_wardrobe_labels[GB_WARDROBE_CHOICE_COUNT];
extern const u16 gb_wardrobe_bg_pages[GB_WARDROBE_CHOICE_COUNT][GB_WARDROBE_BG_PAGE_HALFWORDS];
extern const u16 gb_wardrobe_preview_tiles[GB_WARDROBE_CHOICE_COUNT][GB_WARDROBE_PREVIEW_HALFWORDS];
extern const GbAudioSample gb_audio_samples[GB_AUDIO_SAMPLE_COUNT];
extern const u8 gb_ending_arg0_copy1[GB_ENDING_ARG0_COPY1_BYTES];
extern const u8 gb_ending_arg0_copy2[GB_ENDING_ARG0_COPY2_BYTES];

enum {{
    GB_PLAYER_FRAME_COUNT = 24,
    GB_PLAYER_BICYCLE_FRAME_COUNT = 6,
    GB_PLAYER_BICYCLE_SPRITE_COUNT = 5,
    GB_PLAYER_BICYCLE_SPRITE_HALFWORDS = 128,
    GB_PLAYER_BICYCLE_FRAME_HALFWORDS = GB_PLAYER_BICYCLE_SPRITE_COUNT * GB_PLAYER_BICYCLE_SPRITE_HALFWORDS,
}};

extern const u16 gb_player_obj_palette[16];
extern const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128];
extern const u16 gb_player_bicycle_obj_frames[GB_PLAYER_BICYCLE_FRAME_COUNT * GB_PLAYER_BICYCLE_FRAME_HALFWORDS];

#endif
"""


def extract_ending_argument0_payloads(rom: bytes) -> tuple[bytes, bytes]:
    copy1_off = ENDING_ARG0_COPY1_SOURCE - ROM_BASE
    copy2_off = ENDING_ARG0_COPY2_SOURCE - ROM_BASE
    copy1 = rom[copy1_off:copy1_off + ENDING_ARG0_COPY1_BYTES]
    copy2 = rom[copy2_off:copy2_off + ENDING_ARG0_COPY2_BYTES]
    if len(copy1) != ENDING_ARG0_COPY1_BYTES or len(copy2) != ENDING_ARG0_COPY2_BYTES:
        raise ValueError('ending argument-0 payload truncated')
    if hashlib.sha256(copy1).hexdigest() != '841d321b25a5e9c304146f4e6501745ef35b9d27e69e98560262c76a27381514':
        raise ValueError('ending argument-0 copy1 drifted')
    if hashlib.sha256(copy2).hexdigest() != '17b8dc8ca34e26a634fb21d91d413dbda19bd58b9623e1848a4d1eb3157cb3d2':
        raise ValueError('ending argument-0 copy2 drifted')
    return copy1, copy2


def _ending_effect_s() -> str:
    return """.section .rodata
.balign 4

.global gb_ending_arg0_copy1
gb_ending_arg0_copy1:
    .incbin \"../data/ending/argument0_copy1.bin\"
    .balign 4

.global gb_ending_arg0_copy2
gb_ending_arg0_copy2:
    .incbin \"../data/ending/argument0_copy2.bin\"
    .balign 4
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
    (out / 'data' / 'ending').mkdir(parents=True, exist_ok=True)
    (out / 'include' / 'graveblood').mkdir(parents=True, exist_ok=True)
    (out / 'maps' / 'generated').mkdir(parents=True, exist_ok=True)
    specs = build_level_specs(root)
    variants = build_graphics_variants(root)
    rom_file = _find_rom(root, rom_path)
    rom = rom_file.read_bytes()
    actor_data = build_actor_runtime_data(root)
    actor_sprites = pack_actor_sprite_bank(rom, actor_data.visuals)
    foreground_sprites = pack_foreground_sprite_bank(rom)
    story_data = build_story_runtime_data(root)
    font = extract_canonical_font(rom)
    monster = pack_monster_sprite_bank(rom)
    level_static = pack_level_static_obj_bank(rom)
    ending_copy1, ending_copy2 = extract_ending_argument0_payloads(rom)

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
    bicycle = pack_player_bicycle_animation(rom)
    (out / 'data' / 'player_sprite.c').write_text(_player_c(sprite), encoding='utf-8')
    (out / 'data' / 'player_bicycle_sprite.c').write_text(_player_bicycle_c(bicycle), encoding='utf-8')
    (out / 'data' / 'actor_data.c').write_text(_actor_data_c(actor_data), encoding='utf-8')
    (out / 'data' / 'actor_routes.c').write_text(_actor_routes_c(actor_data), encoding='utf-8')
    (out / 'data' / 'actor_sprite_data.c').write_text(_actor_sprite_c(actor_data, actor_sprites, foreground_sprites), encoding='utf-8')
    (out / 'data' / 'story_data.c').write_text(_story_data_c(story_data), encoding='utf-8')
    (out / 'data' / 'font_data.c').write_text(_font_data_c(font), encoding='utf-8')
    (out / 'data' / 'monster_sprite.c').write_text(_monster_sprite_c(monster, level_static), encoding='utf-8')
    (out / 'data' / 'ending' / 'argument0_copy1.bin').write_bytes(ending_copy1)
    (out / 'data' / 'ending' / 'argument0_copy2.bin').write_bytes(ending_copy2)
    (out / 'data' / 'ending_effect.s').write_text(_ending_effect_s(), encoding='utf-8')
    (out / 'data' / 'level_registry.c').write_text(_registry_c(variants), encoding='utf-8')
    (out / 'include' / 'graveblood' / 'assets.h').write_text(
        _assets_h(variants, len(actor_data.visuals)), encoding='utf-8'
    )


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
