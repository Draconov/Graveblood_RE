#!/usr/bin/env python3
"""Render Graveblood 0.0.1.1.5.2 world layers directly from the ROM.

The renderer follows the code-proven GBA path:
  source u16 tile id -> translation table -> 8bpp text-BG screen entry
  -> 64-byte 8x8 tile -> 256-entry BGR555 palette.

It deliberately treats tile indices >= 864 as unresolved dynamic/overlap tiles.
The game copies 0xD800 bytes of BG character data to charblock 0, so indices
864+ alias the screenblock region beginning at 0x0600D800 and can depend on
runtime tilemap contents. Those cells are left transparent in layer renders.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import struct
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
_EXTRACT_SPEC = importlib.util.spec_from_file_location(
    "extract_structure", ROOT / "tools" / "extract_structure.py"
)
extract = importlib.util.module_from_spec(_EXTRACT_SPEC)
_EXTRACT_SPEC.loader.exec_module(extract)

ROM_BASE = 0x08000000
BG_TILE_COPY_BYTES = 0xD800
BG_TILE_BYTES_8BPP = 64
BG_TILE_COUNT = BG_TILE_COPY_BYTES // BG_TILE_BYTES_8BPP  # 864
STATE_SELECTOR_RAM = 0x03000858
BG_CONTROLS = (0x1B80, 0x1C81, 0x1D82, 0x1E83)


def gba_to_off(addr: int, n: int) -> int:
    if not (ROM_BASE <= addr < ROM_BASE + n):
        raise ValueError(f"not a ROM pointer: 0x{addr:08X}")
    return addr - ROM_BASE


def decode_bg_control(value: int) -> dict[str, int]:
    """Decode the text-background fields used by Graveblood's BGxCNT."""
    size_code = (value >> 14) & 0x3
    dims = ((32, 32), (64, 32), (32, 64), (64, 64))[size_code]
    return {
        "raw": value,
        "priority": value & 0x3,
        "charblock": (value >> 2) & 0x3,
        "mosaic": (value >> 6) & 0x1,
        "bpp": 8 if value & 0x80 else 4,
        "screenblock": (value >> 8) & 0x1F,
        "size_code": size_code,
        "width_tiles": dims[0],
        "height_tiles": dims[1],
    }


def variant_selector_from_state_index(data: bytes, index: int) -> int:
    """Read the selector consumed by 0x08005C54 from 0x03000858[index]."""
    ram_addr = STATE_SELECTOR_RAM + index * 4
    rom_off = extract.init_ram_to_rom_off(ram_addr)
    return struct.unpack_from("<I", data, rom_off)[0]


def _level_words(data: bytes, level_index: int) -> tuple[int, ...]:
    if not 0 <= level_index < extract.LEVEL_COUNT:
        raise ValueError(f"level index out of range: {level_index}")
    off = extract.LEVEL_DESC_OFF + level_index * extract.LEVEL_DESC_SIZE
    return struct.unpack_from("<16I", data, off)


def _variant_descriptor(data: bytes, level_index: int, variant_index: int) -> dict:
    words = _level_words(data, level_index)
    ptrs = extract.level_graphics_variant_ptrs(words)
    if not 0 <= variant_index < len(ptrs):
        raise ValueError(
            f"level {level_index} has {len(ptrs)} graphics variant(s), "
            f"not variant {variant_index}"
        )
    return extract.parse_graphics_descriptor(data, ptrs[variant_index])


def _palette_rgb(data: bytes, addr: int) -> list[tuple[int, int, int]]:
    off = gba_to_off(addr, len(data))
    raw = struct.unpack_from("<256H", data, off)
    out = []
    for value in raw:
        r = (value & 0x1F) * 255 // 31
        g = ((value >> 5) & 0x1F) * 255 // 31
        b = ((value >> 10) & 0x1F) * 255 // 31
        out.append((r, g, b))
    return out


def _translation_table(data: bytes, addr: int, count: int) -> tuple[int, ...]:
    """Read exactly as many halfword entries as the source layers address.

    0x0800A330 does not clamp source tile IDs. Some levels intentionally use
    IDs above 2047, so adjacent ROM data is part of the effective lookup
    address space even when another descriptor pointer falls inside it.
    """
    off = gba_to_off(addr, len(data))
    if off + count * 2 > len(data):
        raise ValueError("translation lookup overruns ROM")
    return struct.unpack_from(f"<{count}H", data, off)


def _tile_cache(data: bytes, addr: int, palette: list[tuple[int, int, int]]):
    off = gba_to_off(addr, len(data))
    tiles = data[off : off + BG_TILE_COPY_BYTES]
    if len(tiles) != BG_TILE_COPY_BYTES:
        raise ValueError("BG tile blob overruns ROM")
    cache: dict[tuple[int, bool, bool], Image.Image] = {}

    def get(tile_index: int, hflip: bool, vflip: bool) -> Image.Image | None:
        if tile_index >= BG_TILE_COUNT:
            return None
        key = (tile_index, hflip, vflip)
        image = cache.get(key)
        if image is not None:
            return image
        start = tile_index * BG_TILE_BYTES_8BPP
        indices = tiles[start : start + BG_TILE_BYTES_8BPP]
        rgba = bytearray(8 * 8 * 4)
        for i, pal_index in enumerate(indices):
            r, g, b = palette[pal_index]
            j = i * 4
            rgba[j : j + 4] = bytes((r, g, b, 0 if pal_index == 0 else 255))
        image = Image.frombytes("RGBA", (8, 8), bytes(rgba))
        if hflip:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if vflip:
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        cache[key] = image
        return image

    return get


def render_world_layer(
    data: bytes,
    level_index: int,
    variant_index: int,
    layer: str,
) -> tuple[Image.Image, int]:
    """Render world layer A or B; return image and unresolved dynamic-cell count."""
    layer = layer.upper()
    if layer not in {"A", "B"}:
        raise ValueError("layer must be A or B")
    words = _level_words(data, level_index)
    world_w, world_h, _, _ = extract.reconstruct_level_dimensions(data)[level_index]
    layer_addr = words[0x08 // 4] if layer == "A" else words[0x10 // 4]
    desc = _variant_descriptor(data, level_index, variant_index)
    palette = _palette_rgb(data, desc["bg_palette_source"])
    get_tile = _tile_cache(data, desc["bg_tiles_source"], palette)

    layer_off = gba_to_off(layer_addr, len(data))
    source_ids = struct.unpack_from(f"<{world_w * world_h}H", data, layer_off)
    translation = _translation_table(
        data, desc["tile_translation_table"], max(source_ids, default=0) + 1
    )
    out = Image.new("RGBA", (world_w * 8, world_h * 8), (0, 0, 0, 0))
    unresolved = 0
    for cell, source_id in enumerate(source_ids):
        if source_id >= len(translation):
            unresolved += 1
            continue
        entry = translation[source_id]
        tile_index = entry & 0x03FF
        tile = get_tile(tile_index, bool(entry & 0x0400), bool(entry & 0x0800))
        if tile is None:
            unresolved += 1
            continue
        x = (cell % world_w) * 8
        y = (cell // world_w) * 8
        out.alpha_composite(tile, (x, y))
    return out, unresolved


def render_static_bg_layers(
    data: bytes,
    level_index: int,
    variant_index: int = 0,
) -> tuple[Image.Image, Image.Image, int, int]:
    """Render the two static/bootstrap maps packed at level+0x1C.

    0x080057DC treats columns 0..31 as screenblock 29 (BG2) and columns
    32..63 as screenblock 30 (BG3).  The source therefore stores two
    independent 32-column text-BG maps side-by-side rather than one spatial
    64-column world map.
    """
    words = _level_words(data, level_index)
    _, _, packed_w, packed_h = extract.reconstruct_level_dimensions(data)[level_index]
    source_addr = words[0x1C // 4]
    desc = _variant_descriptor(data, level_index, variant_index)
    palette = _palette_rgb(data, desc["bg_palette_source"])
    get_tile = _tile_cache(data, desc["bg_tiles_source"], palette)

    source_off = gba_to_off(source_addr, len(data))
    source_ids = struct.unpack_from(f"<{packed_w * packed_h}H", data, source_off)
    translation = _translation_table(
        data, desc["tile_translation_table"], max(source_ids, default=0) + 1
    )
    bg2_w = min(32, packed_w)
    bg3_w = max(0, packed_w - 32)
    bg2 = Image.new("RGBA", (bg2_w * 8, packed_h * 8), (0, 0, 0, 0))
    bg3 = Image.new("RGBA", (bg3_w * 8, packed_h * 8), (0, 0, 0, 0))
    unresolved = [0, 0]

    for y in range(packed_h):
        for x in range(packed_w):
            source_id = source_ids[y * packed_w + x]
            entry = translation[source_id]
            tile_index = entry & 0x03FF
            tile = get_tile(tile_index, bool(entry & 0x0400), bool(entry & 0x0800))
            target_index = 0 if x < 32 else 1
            if tile is None:
                unresolved[target_index] += 1
                continue
            if target_index == 0:
                bg2.alpha_composite(tile, (x * 8, y * 8))
            else:
                bg3.alpha_composite(tile, ((x - 32) * 8, y * 8))
    return bg2, bg3, unresolved[0], unresolved[1]


def render_level_world(data: bytes, level_index: int, variant_index: int = 0) -> Image.Image:
    """Composite streamed world layers according to their hardware priority.

    Layer A is streamed to BG1 (priority 1), while layer B is streamed to
    BG2 (priority 2).  BG1 therefore wins wherever both pixels are opaque.
    """
    desc = _variant_descriptor(data, level_index, variant_index)
    palette = _palette_rgb(data, desc["bg_palette_source"])
    layer_a, _ = render_world_layer(data, level_index, variant_index, "A")
    layer_b, _ = render_world_layer(data, level_index, variant_index, "B")
    out = Image.new("RGBA", layer_a.size, palette[0] + (255,))
    out.alpha_composite(layer_b)
    out.alpha_composite(layer_a)
    return out


def _parse_actor_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _level_has_actor(row: dict[str, str], level_index: int) -> bool:
    return str(level_index) in row.get("normal_level_indices", "").split(";")


def actor_overlay_label(row: dict[str, str], level_index: int) -> str:
    kind = row.get("type", "actor")
    if kind == "player":
        return "PLAYER"
    if kind != "fgtile":
        return kind
    if level_index == 9 and row.get("treetype") == "20" and row.get("portTo") == "524":
        return "treetype20->Y512"
    if level_index == 10 and row.get("turn") in {"4", "5"} and row.get("portTo") == "8":
        return "forced-gate"
    if row.get("portTo"):
        return f"portal->{row['portTo']}"
    return kind


def add_actor_overlay(image: Image.Image, actor_rows: Iterable[dict[str, str]], level_index: int) -> Image.Image:
    """Draw compact markers for recovered actors/portals without obscuring the map."""
    out = image.copy()
    draw = ImageDraw.Draw(out)
    for row in actor_rows:
        if not _level_has_actor(row, level_index):
            continue
        try:
            x = float(row.get("x", ""))
            y = float(row.get("y", ""))
        except ValueError:
            continue
        kind = row.get("type", "actor")
        radius = 5 if kind == "player" else 3
        px, py = round(x), round(y)
        # Keep overlay intentionally monochrome/high-contrast; semantic labels carry meaning.
        draw.ellipse((px-radius, py-radius, px+radius, py+radius), outline="white", width=2)
        label = actor_overlay_label(row, level_index)
        draw.text((px + radius + 2, py - radius), label, fill="white", stroke_width=2, stroke_fill="black")
    return out


def render_all(rom_path: Path, out_dir: Path, actors_csv: Path | None = None) -> None:
    data = rom_path.read_bytes()
    digest = extract.hashlib.sha256(data).hexdigest()
    if digest != extract.EXPECTED_SHA256:
        raise SystemExit(f"wrong ROM SHA-256: {digest}")
    out_dir.mkdir(parents=True, exist_ok=True)
    actors = _parse_actor_rows(actors_csv) if actors_csv and actors_csv.exists() else []
    dims = extract.reconstruct_level_dimensions(data)
    summary_rows = []
    for level_index in range(extract.LEVEL_COUNT):
        words = _level_words(data, level_index)
        variants = extract.level_graphics_variant_ptrs(words)
        for variant_index in range(len(variants)):
            a, unresolved_a = render_world_layer(data, level_index, variant_index, "A")
            b, unresolved_b = render_world_layer(data, level_index, variant_index, "B")
            desc = _variant_descriptor(data, level_index, variant_index)
            palette = _palette_rgb(data, desc["bg_palette_source"])
            world = Image.new("RGBA", a.size, palette[0] + (255,))
            world.alpha_composite(b)
            world.alpha_composite(a)
            base = f"level{level_index:02d}_v{variant_index}"
            a.save(out_dir / f"{base}_layerA.png")
            b.save(out_dir / f"{base}_layerB.png")
            world.save(out_dir / f"{base}_world.png")
            if actors:
                add_actor_overlay(world, actors, level_index).save(out_dir / f"{base}_actors.png")
            summary_rows.append({
                "level_index": level_index,
                "variant_index": variant_index,
                "width_tiles": dims[level_index][0],
                "height_tiles": dims[level_index][1],
                "unresolved_dynamic_cells_A": unresolved_a,
                "unresolved_dynamic_cells_B": unresolved_b,
            })
    with (out_dir / "render_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0]))
        w.writeheader()
        w.writerows(summary_rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--actors", type=Path, default=ROOT / "data" / "actors.csv")
    args = ap.parse_args()
    render_all(args.rom, args.out_dir, args.actors)


if __name__ == "__main__":
    main()
