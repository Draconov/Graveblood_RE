#!/usr/bin/env python3
"""Extract code-proven grass / Fgtile / Leaves foreground semantics.

This extractor is intentionally tied to Graveblood 0.0.1.1.5.2 demo.gba.
It validates the canonical ROM hash and records only behavior proven by the
recovered vtables, method bodies, startup-initialized IWRAM, and level data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

EXPECTED_SHA256 = "e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b"
ROM_BASE = 0x08000000
INIT_ROM_START = 0x00A8D738
INIT_RAM_START = 0x03000788

GRASS_VTABLE = 0x08018AD8
FGTILE_VTABLE = 0x08018E4C
LEAVES_VTABLE = 0x08019660
LEAF_PARTICLE_VTABLE = 0x08A8C1C0


def _rom_offset(addr: int, data: bytes) -> int:
    off = addr - ROM_BASE
    if off < 0 or off >= len(data):
        raise ValueError(f"ROM address outside image: 0x{addr:08X}")
    return off


def _u16(data: bytes, addr: int) -> int:
    return struct.unpack_from('<H', data, _rom_offset(addr, data))[0]


def _u32(data: bytes, addr: int) -> int:
    return struct.unpack_from('<I', data, _rom_offset(addr, data))[0]


def _vtable(data: bytes, addr: int) -> tuple[int, ...]:
    return struct.unpack_from('<8I', data, _rom_offset(addr, data))


def _iwram_u32(data: bytes, addr: int) -> int:
    off = INIT_ROM_START + (addr - INIT_RAM_START)
    if off < 0 or off + 4 > len(data):
        raise ValueError(f"startup IWRAM initializer outside ROM: 0x{addr:08X}")
    return struct.unpack_from('<I', data, off)[0]


def _iwram_u32_array(data: bytes, addr: int, count: int) -> list[int]:
    return [_iwram_u32(data, addr + i * 4) for i in range(count)]


def _require(condition: bool, description: str) -> None:
    if not condition:
        raise ValueError(f"foreground signature mismatch: {description}")


def extract_grass_semantics(data: bytes) -> dict[str, object]:
    table = _vtable(data, GRASS_VTABLE)
    _require(table[3] == 0x08002481, "grass vtable update")
    _require(table[4] == 0x08002685, "grass vtable draw")
    _require(_u16(data, 0x08002480) == 0x4770, "grass update bx lr")
    # Draw signatures: turn from +0x4C, base tile 0x48, shape enum 3.
    _require(_u16(data, 0x080026A4) == 0x234C, "grass turn field")
    _require(_u16(data, 0x080026A8) == 0x2348, "grass tile 0x48")
    _require(_u16(data, 0x080026C6) == 0x2303, "grass 16x16 shape enum")
    _require(_u16(data, 0x0800269C) == 0x234E, "grass legsColor field")
    return {
        'class': 'grass',
        'factory': '0x08002914',
        'vtable': f'0x{GRASS_VTABLE:08X}',
        'update': '0x08002480',
        'update_behavior': 'no_op',
        'draw': '0x08002684',
        'logical_tile': 0x48,
        'shape': '16x16',
        'hflip_source': 'turn_bit0',
        'hide_condition': 'legsColor_eq_1',
        'priority': '1_if_actor_below_player_else_2',
        'screen_x': 'actor_x-camera_x',
        'screen_y': 'actor_y-16-camera_y',
    }


def extract_fgtile_visual_semantics(data: bytes) -> dict[str, object]:
    table = _vtable(data, FGTILE_VTABLE)
    _require(table[3] == 0x08003B99, "Fgtile update vtable slot")
    _require(table[4] == 0x08003AE9, "Fgtile draw vtable slot")
    _require(_u16(data, 0x08003AE8) == 0x4770, "Fgtile draw bx lr")
    return {
        'class': 'fgtile',
        'factory': '0x08003AEC',
        'vtable': f'0x{FGTILE_VTABLE:08X}',
        'update': '0x08003B98',
        'draw': '0x08003AE8',
        'draw_behavior': 'no_op',
        'visual_conclusion': 'interaction_control_metadata_only',
    }


def extract_leaves_semantics(data: bytes) -> dict[str, object]:
    table = _vtable(data, LEAVES_VTABLE)
    _require(table[3] == 0x08005F81, "Leaves update vtable slot")
    _require(table[4] == 0x08005EDD, "Leaves draw vtable slot")
    _require(_u16(data, 0x08005EDC) == 0x4770, "Leaves draw bx lr")
    _require(_u16(data, 0x08005FBC) == 0x429E, "Leaves camera threshold compare")
    _require(_u16(data, 0x08005FC0) == 0x2317, "Leaves cooldown reset 23")
    _require(_u16(data, 0x08006014) == 0xF005, "Leaves particle constructor BL prefix")
    return {
        'class': 'leaves',
        'factory': '0x08005EE0',
        'vtable': f'0x{LEAVES_VTABLE:08X}',
        'update': '0x08005F80',
        'draw': '0x08005EDC',
        'draw_behavior': 'no_op',
        'role': 'global_leaf_particle_emitter',
        'initial_cooldown': _iwram_u32(data, 0x03001040),
        'reset_cooldown': 23,
        'cycle_index_global': '0x03000628',
        'cycle_values': '0..5',
        'camera_x_threshold': 2000,
        'x_offsets': _iwram_u32_array(data, 0x03001044, 6),
        'y_offsets': _iwram_u32_array(data, 0x0300106C, 6),
        'spawn_x_equation': '(camera_x+260+x_offset)<<8',
        'spawn_y_equation': '(camera_y-80+y_offset)<<8',
        'particle_constructor': '0x0800B2BC',
    }


def extract_leaf_particle_semantics(data: bytes) -> dict[str, object]:
    table = _vtable(data, LEAF_PARTICLE_VTABLE)
    _require(table[3] == 0x0800AB61, "leaf particle update vtable slot")
    _require(table[4] == 0x0800AC1D, "leaf particle draw vtable slot")
    _require(_u16(data, 0x0800B2E2) == 0x3BA0, "leaf particle vx construction")
    _require(_u16(data, 0x0800B2E8) == 0x332D, "leaf particle vy construction step 1")
    _require(_u16(data, 0x0800B2EA) == 0x33FF, "leaf particle vy construction step 2")
    _require(_u16(data, 0x0800AC6E) == 0x210A, "leaf particle frame countdown 10")
    return {
        'class': 'leaf_particle',
        'constructor': '0x0800B2BC',
        'vtable': f'0x{LEAF_PARTICLE_VTABLE:08X}',
        'update': '0x0800AB60',
        'draw': '0x0800AC1C',
        'velocity_x_fixed8': -150,
        'velocity_y_fixed8': 150,
        'velocity_y_clamp_fixed8': 0x400,
        'frame_tiles': _iwram_u32_array(data, 0x03001B4C, 4),
        'initial_frame_countdown': 10,
        'shape': '8x8',
        'priority': 0,
        'cull_condition': 'x<camera_x-30_or_y>camera_y+180',
        'screen_x': '(fixed_x>>8)-4-camera_x',
        'screen_y': '(fixed_y>>8)-8-camera_y',
    }


def extract_leaves_level_usage(root: Path) -> list[dict[str, object]]:
    actors_path = root / 'data' / 'actors.csv'
    levels_path = root / 'data' / 'levels.csv'
    by_level: dict[int, int] = {}
    with actors_path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['type'].lower() != 'leaves':
                continue
            for token in row['normal_level_indices'].split(';'):
                if token.strip():
                    level = int(token)
                    by_level[level] = by_level.get(level, 0) + 1
    dimensions: dict[int, tuple[int, int]] = {}
    with levels_path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            dimensions[int(row['level_index'])] = (
                int(row['world_width_tiles']), int(row['world_height_tiles'])
            )
    rows: list[dict[str, object]] = []
    for level in sorted(by_level):
        width, _ = dimensions[level]
        max_camera_x = max(0, width * 8 - 240)
        rows.append({
            'level': level,
            'leaves_count': by_level[level],
            'world_width_tiles': width,
            'max_camera_x': max_camera_x,
            'can_cross_camera_x_2000': max_camera_x > 2000,
        })
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def _write_disasm(root: Path, out: Path, rom_path: Path, name: str, offset: int, size: int) -> None:
    result = subprocess.run(
        [sys.executable, str(root / 'tools' / 'disasm_thumb_chunk.py'), str(rom_path), hex(offset), hex(size)],
        cwd=root, check=True, capture_output=True, text=True,
    )
    path = out / 'disasm' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.stdout, encoding='utf-8')


def generate(root: Path, out: Path, rom_path: Path) -> None:
    data = rom_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f'canonical ROM SHA-256 mismatch: {digest}')

    grass = extract_grass_semantics(data)
    fgtile = extract_fgtile_visual_semantics(data)
    leaves = extract_leaves_semantics(data)
    particle = extract_leaf_particle_semantics(data)
    _write_csv(out / 'data' / 'foreground_actor_semantics.csv', [grass, fgtile, {
        **{k: v for k, v in leaves.items() if k not in ('x_offsets', 'y_offsets')},
    }, particle])
    _write_csv(out / 'data' / 'leaves_emitter_semantics.csv', [{
        'initial_cooldown': leaves['initial_cooldown'],
        'reset_cooldown': leaves['reset_cooldown'],
        'cycle_index_global': leaves['cycle_index_global'],
        'cycle_values': leaves['cycle_values'],
        'camera_x_threshold': leaves['camera_x_threshold'],
        'x_offsets': ';'.join(str(v) for v in leaves['x_offsets']),
        'y_offsets': ';'.join(str(v) for v in leaves['y_offsets']),
        'spawn_x_equation': leaves['spawn_x_equation'],
        'spawn_y_equation': leaves['spawn_y_equation'],
        'particle_constructor': leaves['particle_constructor'],
        'frame_tiles': ';'.join(f'0x{v:02X}' for v in particle['frame_tiles']),
    }])
    _write_csv(out / 'data' / 'leaves_level_usage.csv', extract_leaves_level_usage(root))

    for name, offset, size in (
        ('grass_draw_08002684.txt', 0x2684, 0x58),
        ('leaves_update_08005F80.txt', 0x5F80, 0xB0),
        ('leaf_particle_update_0800AB60.txt', 0xAB60, 0x50),
        ('leaf_particle_draw_0800AC1C.txt', 0xAC1C, 0x60),
        ('leaf_particle_constructor_0800B2BC.txt', 0xB2BC, 0x60),
    ):
        _write_disasm(root, out, rom_path, name, offset, size)


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
