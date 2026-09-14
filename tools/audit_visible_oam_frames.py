#!/usr/bin/env python3
"""ROM-backed visible OBJ/OAM parity audit for Graveblood_RE.

The compositor models gameplay OBJ pixels only.  Palette index zero is
transparent; lower OBJ priority wins and, for equal priority, the lower OAM
index wins.  Coordinates use the GBA's 9-bit X / 8-bit Y wrap semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import sys
import hashlib
import re
import struct
from typing import Iterable, Sequence

SCREEN_W = 240
SCREEN_H = 160
TRANSPARENT = 0xFFFF

TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@dataclass(frozen=True)
class ObjPiece:
    label: str
    width: int
    height: int
    pixels: bytes
    x: int
    y: int
    priority: int
    oam_index: int
    hflip: bool = False

    def __post_init__(self) -> None:
        if len(self.pixels) != self.width * self.height:
            raise ValueError(
                f"{self.label}: expected {self.width * self.height} pixels, got {len(self.pixels)}"
            )
        if not 0 <= self.priority <= 3:
            raise ValueError(f"{self.label}: OBJ priority outside 0..3")


@dataclass(frozen=True)
class ObjFrame:
    colors: tuple[int, ...]
    owners: tuple[str | None, ...]
    keys: tuple[tuple[int, int] | None, ...]


@dataclass(frozen=True)
class FrameDiff:
    mismatch_count: int
    first_x: int | None
    first_y: int | None
    expected_color: int | None
    actual_color: int | None
    expected_owner: str | None
    actual_owner: str | None
    classification: str


def oam_screen_x(raw: int) -> int:
    value = raw & 0x1FF
    return value - 0x200 if value >= 0x100 else value


def oam_screen_y(raw: int) -> int:
    value = raw & 0xFF
    return value - 0x100 if value >= 0xA0 else value


def decode_tiled_8bpp(blob: bytes, width: int, height: int) -> bytes:
    if width <= 0 or height <= 0 or width % 8 or height % 8:
        raise ValueError("8bpp OBJ dimensions must be positive multiples of 8")
    tile_cols = width // 8
    tile_rows = height // 8
    expected = tile_cols * tile_rows * 64
    if len(blob) != expected:
        raise ValueError(f"expected {expected} tiled bytes, got {len(blob)}")
    out = bytearray(width * height)
    for ty in range(tile_rows):
        for tx in range(tile_cols):
            tile_off = (ty * tile_cols + tx) * 64
            for py in range(8):
                src = tile_off + py * 8
                dst = (ty * 8 + py) * width + tx * 8
                out[dst:dst + 8] = blob[src:src + 8]
    return bytes(out)


def compose_obj_frame(pieces: Iterable[ObjPiece], palette: Sequence[int]) -> ObjFrame:
    if len(palette) < 256:
        raise ValueError("OBJ palette must expose 256 entries")
    colors = [TRANSPARENT] * (SCREEN_W * SCREEN_H)
    owners: list[str | None] = [None] * (SCREEN_W * SCREEN_H)
    keys: list[tuple[int, int] | None] = [None] * (SCREEN_W * SCREEN_H)
    for piece in pieces:
        key = (piece.priority, piece.oam_index)
        for py in range(piece.height):
            sy = piece.y + py
            if sy < 0 or sy >= SCREEN_H:
                continue
            for px in range(piece.width):
                sx = piece.x + px
                if sx < 0 or sx >= SCREEN_W:
                    continue
                source_x = piece.width - 1 - px if piece.hflip else px
                pal_index = piece.pixels[py * piece.width + source_x]
                if pal_index == 0:
                    continue
                dst = sy * SCREEN_W + sx
                old = keys[dst]
                if old is not None and old <= key:
                    continue
                colors[dst] = int(palette[pal_index]) & 0xFFFF
                owners[dst] = piece.label
                keys[dst] = key
    return ObjFrame(tuple(colors), tuple(owners), tuple(keys))


def compare_frames(expected: ObjFrame, actual: ObjFrame) -> FrameDiff:
    if len(expected.colors) != len(actual.colors):
        raise ValueError("frame dimensions differ")
    mismatch = 0
    first = None
    for i, (want, got) in enumerate(zip(expected.colors, actual.colors)):
        if want != got:
            mismatch += 1
            if first is None:
                first = i
    if first is None:
        return FrameDiff(0, None, None, None, None, None, None, "match")
    exp_owner = expected.owners[first]
    act_owner = actual.owners[first]
    if exp_owner != act_owner:
        classification = "object_coverage_or_order"
    else:
        classification = "pixel_color"
    return FrameDiff(
        mismatch,
        first % SCREEN_W,
        first // SCREEN_W,
        expected.colors[first],
        actual.colors[first],
        exp_owner,
        act_owner,
        classification,
    )


def frame_hash(frame: ObjFrame) -> str:
    raw = bytearray()
    for color in frame.colors:
        raw.extend(struct.pack('<H', color))
    return hashlib.sha256(raw).hexdigest()


def parse_u16_array(path: Path, symbol: str) -> tuple[int, ...]:
    text = path.read_text(encoding='utf-8')
    match = re.search(
        rf"const\s+u16\s+{re.escape(symbol)}\s*\[[^;=]*\]\s*=\s*\{{(.*?)\}};",
        text,
        re.S,
    )
    if not match:
        raise ValueError(f"could not find {symbol} in {path}")
    return tuple(int(token, 0) for token in re.findall(r"0x[0-9A-Fa-f]+|\b\d+\b", match.group(1)))


def u16_words_to_bytes(words: Sequence[int]) -> bytes:
    return b''.join(struct.pack('<H', word & 0xFFFF) for word in words)

@dataclass(frozen=True)
class AuditRow:
    name: str
    family: str
    expected_hash: str
    actual_hash: str
    mismatch_count: int
    first_x: int | None
    first_y: int | None
    expected_owner: str | None
    actual_owner: str | None
    classification: str


def _parse_visual_specs(path: Path) -> tuple[tuple[int, int], ...]:
    text = path.read_text(encoding='utf-8')
    match = re.search(
        r"const\s+GbActorVisualSpec\s+gb_actor_visuals\s*\[[^]]+\]\s*=\s*\{(.*?)\};",
        text,
        re.S,
    )
    if not match:
        raise ValueError(f"could not find gb_actor_visuals in {path}")
    rows = re.findall(r"\{\s*(\d+)\s*,\s*(\d+)\s*\}", match.group(1))
    return tuple((int(a), int(b)) for a, b in rows)


def _full_palette(low: Sequence[int], high: Sequence[int]) -> tuple[int, ...]:
    if len(low) != 91 or len(high) != 32:
        raise ValueError(f"unexpected gameplay OBJ palette sizes {len(low)}/{len(high)}")
    palette = [0] * 256
    palette[:91] = [int(v) & 0xFFFF for v in low]
    palette[224:256] = [int(v) & 0xFFFF for v in high]
    return tuple(palette)


def _chunk(data: bytes, offset: int, size: int) -> bytes:
    blob = data[offset:offset + size]
    if len(blob) != size:
        raise ValueError(f"asset chunk {offset}:{offset + size} outside {len(data)} bytes")
    return blob


def _stacked_16x32_pieces(label: str, packed: bytes, x: int, top_y: int,
                           priority: int, first_oam: int, hflip: bool = False) -> tuple[ObjPiece, ...]:
    pixels = decode_tiled_8bpp(packed, 16, 32)
    top = b''.join(pixels[row * 16:(row + 1) * 16] for row in range(16))
    bottom = b''.join(pixels[row * 16:(row + 1) * 16] for row in range(16, 32))
    # Canonical Player/NPC draw submits bottom first, then top.
    return (
        ObjPiece(label + ':bottom', 16, 16, bottom, x, top_y + 16, priority, first_oam, hflip),
        ObjPiece(label + ':top', 16, 16, top, x, top_y, priority, first_oam + 1, hflip),
    )


def _pieces_16x16(label: str, packed: bytes, positions: Sequence[tuple[int, int]],
                    priority: int, first_oam: int) -> tuple[ObjPiece, ...]:
    if len(packed) != len(positions) * 256:
        raise ValueError(f"{label}: expected {len(positions) * 256} bytes, got {len(packed)}")
    out = []
    for i, (x, y) in enumerate(positions):
        pixels = decode_tiled_8bpp(_chunk(packed, i * 256, 256), 16, 16)
        out.append(ObjPiece(f'{label}:{i}', 16, 16, pixels, x, y, priority, first_oam + i, False))
    return tuple(out)


def _piece_8x8(label: str, packed: bytes, x: int, y: int, priority: int, oam: int) -> ObjPiece:
    return ObjPiece(label, 8, 8, decode_tiled_8bpp(packed, 8, 8), x, y, priority, oam, False)


def _re_monster_includes_static(root: Path) -> bool:
    text = (root / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
    start = text.index('if(story && story->state.monster_render_enabled)')
    end = text.index('gb_monster_animation_counter = 0;', start)
    return 'gb_video_draw_level_static_composite' in text[start:end]


def _asset_sets(root: Path, rom: bytes, mutation: tuple[str, int] | None = None):
    # Keep canonical and RE asset paths independent: canonical bytes are rebuilt
    # from the ROM source sheet; RE bytes are parsed from the checked-in C arrays.
    from tools.generate_cfa_assets import (
        _pack_actor_base_palette,
        pack_actor_obj_high_palette,
        pack_actor_sprite_bank,
        pack_foreground_sprite_bank,
        pack_level_static_obj_bank,
        pack_monster_sprite_bank,
        pack_player_animation,
        pack_player_bicycle_animation,
    )

    actor_c = root / 'reconstruction/data/actor_sprite_data.c'
    visuals = _parse_visual_specs(actor_c)
    canonical = {
        'palette': _full_palette(_pack_actor_base_palette(rom), pack_actor_obj_high_palette(rom)),
        'player': pack_player_animation(rom).data,
        'npc': pack_actor_sprite_bank(rom, visuals).data,
        'grass': pack_foreground_sprite_bank(rom).grass,
        'leaf': pack_foreground_sprite_bank(rom).leaf_frames,
        'bicycle': pack_player_bicycle_animation(rom),
        'monster': pack_monster_sprite_bank(rom).data,
        'static': pack_level_static_obj_bank(rom).data,
        'visuals': visuals,
    }
    actual = {
        'palette': _full_palette(
            parse_u16_array(actor_c, 'gb_actor_obj_palette'),
            parse_u16_array(actor_c, 'gb_actor_obj_high_palette'),
        ),
        'player': u16_words_to_bytes(parse_u16_array(root / 'reconstruction/data/player_sprite.c', 'gb_player_obj_tiles')),
        'npc': u16_words_to_bytes(parse_u16_array(actor_c, 'gb_actor_obj_frames')),
        'grass': u16_words_to_bytes(parse_u16_array(actor_c, 'gb_grass_obj_tiles')),
        'leaf': u16_words_to_bytes(parse_u16_array(actor_c, 'gb_leaf_obj_frames')),
        'bicycle': u16_words_to_bytes(parse_u16_array(root / 'reconstruction/data/player_bicycle_sprite.c', 'gb_player_bicycle_obj_frames')),
        'monster': u16_words_to_bytes(parse_u16_array(root / 'reconstruction/data/monster_sprite.c', 'gb_monster_obj_frames')),
        'static': u16_words_to_bytes(parse_u16_array(root / 'reconstruction/data/monster_sprite.c', 'gb_level_static_obj_tiles')),
        'visuals': visuals,
    }
    if mutation is not None:
        family, index = mutation
        if family == 'palette':
            altered = list(actual['palette'])
            if not 0 <= index < len(altered):
                raise ValueError('mutation palette index outside asset')
            altered[index] ^= 1
            actual['palette'] = tuple(altered)
        else:
            if family not in actual or not isinstance(actual[family], (bytes, bytearray)):
                raise ValueError(f'unsupported audit mutation {mutation!r}')
            altered = bytearray(actual[family])
            if not 0 <= index < len(altered):
                raise ValueError('mutation byte index outside asset')
            altered[index] ^= 1
            actual[family] = bytes(altered)
    return canonical, actual


def _checkpoint_piece_pairs(root: Path, rom: bytes, mutation: tuple[str, int] | None = None):
    can, act = _asset_sets(root, rom, mutation)
    rows: list[tuple[str, str, tuple[ObjPiece, ...], tuple[ObjPiece, ...]]] = []

    # 24 canonical source frames plus one horizontal-flip case.
    for frame in range(24):
        off = frame * 512
        name = f'player_frame_{frame:02d}'
        rows.append((name, 'player',
                     _stacked_16x32_pieces(name, _chunk(can['player'], off, 512), 112, 64, 2, 0),
                     _stacked_16x32_pieces(name, _chunk(act['player'], off, 512), 112, 64, 2, 0)))
    rows.append(('player_frame_00_hflip', 'player',
                 _stacked_16x32_pieces('player_frame_00_hflip', _chunk(can['player'], 0, 512), 112, 64, 2, 0, True),
                 _stacked_16x32_pieces('player_frame_00_hflip', _chunk(act['player'], 0, 512), 112, 64, 2, 0, True)))

    # Every recovered NPC visual family at frame 1, plus the full 8-frame
    # sequence for visual 0 and explicit depth/H-flip samples.
    visual_count = len(can['visuals'])
    for visual in range(visual_count):
        off = (visual * 8) * 512
        name = f'npc_visual_{visual:02d}_frame_1'
        rows.append((name, 'npc',
                     _stacked_16x32_pieces(name, _chunk(can['npc'], off, 512), 112, 64, 2, 0),
                     _stacked_16x32_pieces(name, _chunk(act['npc'], off, 512), 112, 64, 2, 0)))
    for frame in range(2, 9):
        off = (frame - 1) * 512
        name = f'npc_visual_00_frame_{frame}'
        rows.append((name, 'npc',
                     _stacked_16x32_pieces(name, _chunk(can['npc'], off, 512), 112, 64, 2, 0),
                     _stacked_16x32_pieces(name, _chunk(act['npc'], off, 512), 112, 64, 2, 0)))
    for name, priority, flip in (('npc_depth_front', 1, False), ('npc_hflip', 2, True)):
        rows.append((name, 'npc',
                     _stacked_16x32_pieces(name, _chunk(can['npc'], 0, 512), 112, 64, priority, 0, flip),
                     _stacked_16x32_pieces(name, _chunk(act['npc'], 0, 512), 112, 64, priority, 0, flip)))

    grass_can = decode_tiled_8bpp(can['grass'], 16, 16)
    grass_act = decode_tiled_8bpp(act['grass'], 16, 16)
    for name, priority, flip in (('grass_priority1', 1, False), ('grass_priority2', 2, False), ('grass_hflip', 2, True)):
        rows.append((name, 'grass',
                     (ObjPiece(name, 16, 16, grass_can, 112, 80, priority, 0, flip),),
                     (ObjPiece(name, 16, 16, grass_act, 112, 80, priority, 0, flip),)))

    for frame in range(4):
        name = f'leaf_frame_{frame}'
        rows.append((name, 'leaf',
                     (_piece_8x8(name, _chunk(can['leaf'], frame * 64, 64), 116, 80, 0, 0),),
                     (_piece_8x8(name, _chunk(act['leaf'], frame * 64, 64), 116, 80, 0, 0),)))

    bike_positions = ((120, 60), (112, 76), (128, 76), (112, 92), (128, 92))
    for frame in range(6):
        off = frame * 5 * 256
        name = f'bicycle_riding_frame_{frame + 1}'
        rows.append((name, 'bicycle_riding',
                     _pieces_16x16(name, _chunk(can['bicycle'], off, 1280), bike_positions, 2, 0),
                     _pieces_16x16(name, _chunk(act['bicycle'], off, 1280), bike_positions, 2, 0)))

    parked_positions = ((104, 72), (120, 72), (104, 88), (120, 88))
    for level in (9, 10):
        name = f'bicycle_parked_level_{level}'
        rows.append((name, 'bicycle_parked',
                     _pieces_16x16(name, can['static'], parked_positions, 2, 0),
                     _pieces_16x16(name, act['static'], parked_positions, 2, 0)))

    for counter in (1, 8, 16, 25):
        name = f'monster_counter_{counter:02d}'
        positions = ((120, counter - 20), (112, counter - 4), (128, counter - 4),
                     (112, counter + 12), (128, counter + 12))
        rows.append((name, 'monster',
                     _pieces_16x16(name, can['monster'], positions, 2, 0),
                     _pieces_16x16(name, act['monster'], positions, 2, 0)))

    # Level 10 exclusivity is intentionally derived from production source on
    # the RE side so the original monster-vs-parked-bicycle dispatch bug is
    # visible to this audit as well as to the host runtime regression.
    name = 'monster_level10_exclusive'
    counter = 25
    positions = ((120, counter - 20), (112, counter - 4), (128, counter - 4),
                 (112, counter + 12), (128, counter + 12))
    expected = _pieces_16x16(name, can['monster'], positions, 2, 0)
    actual = list(_pieces_16x16(name, act['monster'], positions, 2, 0))
    if _re_monster_includes_static(root):
        actual.extend(_pieces_16x16(name + ':parked', act['static'], parked_positions, 2, 5))
    rows.append((name, 'monster', expected, tuple(actual)))
    return rows, can['palette'], act['palette']


def run_audit(root: Path, rom: bytes, mutation: tuple[str, int] | None = None) -> list[AuditRow]:
    piece_rows, expected_palette, actual_palette = _checkpoint_piece_pairs(root, rom, mutation)
    out: list[AuditRow] = []
    for name, family, expected_pieces, actual_pieces in piece_rows:
        expected = compose_obj_frame(expected_pieces, expected_palette)
        actual = compose_obj_frame(actual_pieces, actual_palette)
        diff = compare_frames(expected, actual)
        out.append(AuditRow(
            name=name,
            family=family,
            expected_hash=frame_hash(expected),
            actual_hash=frame_hash(actual),
            mismatch_count=diff.mismatch_count,
            first_x=diff.first_x,
            first_y=diff.first_y,
            expected_owner=diff.expected_owner,
            actual_owner=diff.actual_owner,
            classification=diff.classification,
        ))
    return out


def write_audit_csv(rows: Sequence[AuditRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow((
            'checkpoint', 'family', 'canonical_bgr555_sha256', 're_bgr555_sha256',
            'mismatch_count', 'first_x', 'first_y', 'canonical_owner', 're_owner',
            'classification',
        ))
        for row in rows:
            writer.writerow((
                row.name, row.family, row.expected_hash, row.actual_hash,
                row.mismatch_count,
                '' if row.first_x is None else row.first_x,
                '' if row.first_y is None else row.first_y,
                row.expected_owner or '', row.actual_owner or '', row.classification,
            ))


def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    rom = args.rom.read_bytes()
    rows = run_audit(root, rom)
    output = args.output or (root / 'data/visible_oam_frame_parity.csv')
    write_audit_csv(rows, output)
    bad = [row for row in rows if row.mismatch_count]
    print(f'{len(rows)} visible OBJ/OAM checkpoints; {len(bad)} mismatches')
    for row in bad[:20]:
        print(f'{row.name}: {row.mismatch_count} pixels ({row.classification})')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(_main())
