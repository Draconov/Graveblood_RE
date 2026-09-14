#!/usr/bin/env python3
"""Audit canonical-vs-clean-room gameplay BG state.

The report covers three state classes:
- initial gameplay BG palette + character data for every recovered graphics variant;
- camera-reachable unchecked world-stream guard cells for both streamed layers;
- every reachable ordinary Fgtile BG-character patch branch.

Canonical bytes come directly from the public-demo ROM. Clean-room bytes come
from the checked-in generated C assets so generator drift is visible rather
than hidden by reusing one in-memory extraction for both sides.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import re
import struct
import sys
from pathlib import Path

ROM_BASE = 0x08000000
INIT_ROM_START = 0x08A8D738
INIT_RAM_START = 0x03000788
FGTILE_PATCH_TABLE_RAM = 0x03000884
FGTILE_PATCH_COUNT = 18
FGTILE_PATCH_SOURCE_BASE_32 = 1680

FIELDS = (
    'level', 'variant', 'state_type', 'layer', 'physical_index', 'turn',
    'patch_index', 'destination_offset', 'copy_bytes',
    'expected_sha256', 're_sha256', 'mismatch_bytes', 'notes',
)


def _load_generator(root: Path):
    path = root / 'tools' / 'generate_cfa_assets.py'
    spec = importlib.util.spec_from_file_location('generate_cfa_assets_bg_audit', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _asset_symbol(level: int, variant: int) -> str:
    return f'gb_level{level:02d}' if variant == 0 else f'gb_level{level:02d}_v{variant}'


def _asset_path(root: Path, level: int, variant: int) -> Path:
    name = f'level{level:02d}_assets.c' if variant == 0 else f'level{level:02d}_v{variant}_assets.c'
    return root / 'reconstruction' / 'data' / name


def _parse_u16_array(path: Path, symbol: str) -> tuple[int, ...] | None:
    text = path.read_text(encoding='utf-8')
    match = re.search(
        rf'const\s+u16\s+{re.escape(symbol)}\s*\[[^\]]+\]\s*=\s*\{{(.*?)\}}\s*;',
        text,
        re.S,
    )
    if not match:
        return None
    values = re.findall(r'0x[0-9A-Fa-f]+|(?<![A-Za-z_])\d+', match.group(1))
    return tuple(int(value, 0) for value in values)


def _u16_bytes(values: tuple[int, ...]) -> bytes:
    return struct.pack(f'<{len(values)}H', *values) if values else b''


def _mismatch_bytes(expected: bytes, actual: bytes) -> int:
    shared = sum(a != b for a, b in zip(expected, actual))
    return shared + abs(len(expected) - len(actual))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row(level: int, variant: int, state_type: str, expected: bytes, actual: bytes,
         *, layer: str = '', physical_index: str = '', turn: str = '',
         patch_index: str = '', destination_offset: str = '', copy_bytes: str = '',
         notes: str = '') -> dict[str, str]:
    return {
        'level': str(level),
        'variant': str(variant),
        'state_type': state_type,
        'layer': layer,
        'physical_index': str(physical_index),
        'turn': str(turn),
        'patch_index': str(patch_index),
        'destination_offset': str(destination_offset),
        'copy_bytes': str(copy_bytes),
        'expected_sha256': _sha(expected),
        're_sha256': _sha(actual),
        'mismatch_bytes': str(_mismatch_bytes(expected, actual)),
        'notes': notes,
    }


def _patch_table(rom: bytes) -> tuple[tuple[int, int, int], ...]:
    table_addr = INIT_ROM_START + (FGTILE_PATCH_TABLE_RAM - INIT_RAM_START)
    off = table_addr - ROM_BASE
    return tuple(
        struct.unpack_from('<III', rom, off + index * 12)
        for index in range(FGTILE_PATCH_COUNT)
    )


def _active_patch_controllers(generator, root: Path):
    data = generator.build_actor_runtime_data(root)
    for level in range(11):
        player_index = data.player_indices[level]
        for compact_index, descriptor_index in enumerate(data.level_indices[level]):
            descriptor = data.physical[descriptor_index]
            physical_index = compact_index if compact_index < player_index else compact_index + 1
            if (descriptor.actor_class == generator.ACTOR_CLASS_FGTILE and
                    descriptor.port_to == 33 and descriptor.turn in (0, 1) and
                    descriptor.treetype not in (1, 20)):
                yield level, physical_index, descriptor


def build_bg_state_report(root: Path, rom: bytes) -> list[dict[str, str]]:
    root = Path(root)
    generator = _load_generator(root)
    specs = generator.build_level_specs(root)
    variants = generator.build_graphics_variants(root)
    patch_table = _patch_table(rom)
    rows: list[dict[str, str]] = []

    # Exact initial palette + 0xD800 character data for all recovered variants.
    runtime_cache = {}
    re_cache = {}
    for (level, variant), descriptor in sorted(variants.items()):
        runtime = generator.load_runtime_background(root, rom, specs[level], variant)
        runtime_cache[(level, variant)] = runtime
        path = _asset_path(root, level, variant)
        symbol = _asset_symbol(level, variant)
        re_palette = _parse_u16_array(path, f'{symbol}_bg_palette') or ()
        re_tiles = _parse_u16_array(path, f'{symbol}_bg_tiles') or ()
        re_patch_source = _parse_u16_array(path, f'{symbol}_bg_patch_source') or ()
        re_cache[(level, variant)] = (re_palette, re_tiles, re_patch_source)
        expected = _u16_bytes(runtime.palette) + runtime.tile_bytes
        actual = _u16_bytes(re_palette) + _u16_bytes(re_tiles)
        rows.append(_row(
            level, variant, 'initial', expected, actual,
            notes=(f'palette@0x{descriptor.palette_addr:08X} + '
                   f'0xD800 BG chars@0x{descriptor.bg_tiles_addr:08X}'),
        ))

    # The active demo uses variant 0 for gameplay. Preserve the unchecked
    # guard results reached by the inclusive 31x21 streamer at camera edges.
    for level in range(11):
        runtime = runtime_cache[(level, 0)]
        path = _asset_path(root, level, 0)
        symbol = _asset_symbol(level, 0)
        for layer, expected_values in (
            ('A', runtime.layer_a_guard),
            ('B', runtime.layer_b_guard),
        ):
            actual_values = _parse_u16_array(path, f'{symbol}_layer_{layer.lower()}_guard')
            if actual_values is None:
                actual_values = tuple(0 for _ in expected_values)
            expected = _u16_bytes(expected_values)
            actual = _u16_bytes(actual_values)
            rows.append(_row(
                level, 0, 'stream_guard', expected, actual, layer=layer,
                notes=(f'cell -1 plus cells N..N+width; '
                       f'{len(expected_values)} already-translated halfwords'),
            ))

    # Reproduce each reachable ordinary Fgtile transition from a freshly loaded
    # level.  Both treetype and treetype+1 are possible states of the strip.
    for level, physical_index, descriptor in _active_patch_controllers(generator, root):
        runtime = runtime_cache[(level, 0)]
        re_palette, re_tiles, re_patch_source_words = re_cache[(level, 0)]
        del re_palette
        re_base = bytearray(_u16_bytes(re_tiles))
        expected_base = bytearray(runtime.tile_bytes)
        re_patch_source = _u16_bytes(re_patch_source_words)
        graphics = variants[(level, 0)]
        for branch, patch_index in (('base', descriptor.treetype), ('alternate', descriptor.treetype + 1)):
            destination_32, source_32, count_64 = patch_table[patch_index]
            destination = destination_32 * 32
            copy_bytes = count_64 * 64
            canonical_source = graphics.bg_tiles_addr + source_32 * 32
            source_off = canonical_source - ROM_BASE
            expected = bytearray(expected_base)
            expected[destination:destination + copy_bytes] = rom[source_off:source_off + copy_bytes]

            actual = bytearray(re_base)
            relative = (source_32 - FGTILE_PATCH_SOURCE_BASE_32) * 32
            actual[destination:destination + copy_bytes] = re_patch_source[relative:relative + copy_bytes]
            rows.append(_row(
                level, 0, 'fgtile_patch', bytes(expected), bytes(actual),
                physical_index=str(physical_index), turn=str(descriptor.turn),
                patch_index=str(patch_index), destination_offset=f'0x{destination:04X}',
                copy_bytes=str(copy_bytes),
                notes=f'{branch} strip state; treetype={descriptor.treetype}',
            ))

    return rows


def write_bg_state_report(root: Path, rom: bytes, out: Path) -> None:
    rows = build_bg_state_report(root, rom)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=root)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=root / 'data' / 'bg_state_parity.csv')
    args = ap.parse_args()
    write_bg_state_report(args.root, args.rom.read_bytes(), args.out)


if __name__ == '__main__':
    main()
