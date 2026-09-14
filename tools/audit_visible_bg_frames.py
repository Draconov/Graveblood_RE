#!/usr/bin/env python3
"""ROM-backed visible gameplay BG frame parity audit.

The low-level helpers model GBA 8bpp text backgrounds directly from one
64 KiB BG-VRAM byte array.  Keeping character and screen-map memory in the
same array is intentional: tile indices 864..1023 alias screenblocks 27..31
in Graveblood's charblock-0 layout.  Each checkpoint begins from the GBA
cold-boot contract that VRAM is BIOS-zeroed; the recovered level loader then
defines the same character/map regions that the cartridge writes.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import argparse
import csv
import hashlib
import importlib.util
from pathlib import Path
import re
import struct
import sys

BG_VRAM_BYTES = 0x10000
SCREENBLOCK_BYTES = 0x800
TEXT_BG_SIDE_PX = 256
TILE_BYTES_8BPP = 64


def sample_text_bg(
    vram: bytes | bytearray,
    screenblock: int,
    scroll_x: int,
    scroll_y: int,
    screen_x: int,
    screen_y: int,
) -> dict[str, int | bool | None]:
    """Sample one pixel from a 32x32 8bpp text BG.

    Graveblood uses size-0 text backgrounds, so the map wraps every 256 px.
    Screen entries use tile bits 0..9 and H/V flip bits 10..11.
    """
    if len(vram) < BG_VRAM_BYTES:
        raise ValueError("BG VRAM image must contain 0x10000 bytes")
    if not 0 <= screenblock <= 31:
        raise ValueError("screenblock must be 0..31")

    world_x = (screen_x + scroll_x) & 0xFF
    world_y = (screen_y + scroll_y) & 0xFF
    map_x = world_x >> 3
    map_y = world_y >> 3
    pixel_x = world_x & 7
    pixel_y = world_y & 7
    map_cell = map_y * 32 + map_x
    map_off = screenblock * SCREENBLOCK_BYTES + map_cell * 2
    entry = vram[map_off] | (vram[map_off + 1] << 8)
    tile_index = entry & 0x03FF
    hflip = bool(entry & 0x0400)
    vflip = bool(entry & 0x0800)
    if hflip:
        pixel_x = 7 - pixel_x
    if vflip:
        pixel_y = 7 - pixel_y

    tile_off = tile_index * TILE_BYTES_8BPP
    palette_index = vram[tile_off + pixel_y * 8 + pixel_x]
    alias = tile_off // SCREENBLOCK_BYTES if tile_off >= 0xD800 else None
    return {
        "palette_index": palette_index,
        "entry": entry,
        "tile_index": tile_index,
        "hflip": hflip,
        "vflip": vflip,
        "map_x": map_x,
        "map_y": map_y,
        "map_cell": map_cell,
        "tile_screenblock_alias": alias,
    }


def compose_bg_frame(
    vram: bytes | bytearray,
    backgrounds: Iterable[Mapping[str, int]],
    *,
    width: int = 240,
    height: int = 160,
) -> bytes:
    """Compose BG palette indices using GBA text-BG priority/transparency."""
    ordered = sorted(backgrounds, key=lambda bg: (bg["priority"], bg["bg_index"]))
    out = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            color = 0
            for bg in ordered:
                sample = sample_text_bg(
                    vram,
                    int(bg["screenblock"]),
                    int(bg["scroll_x"]),
                    int(bg["scroll_y"]),
                    x,
                    y,
                )
                candidate = int(sample["palette_index"])
                if candidate != 0:
                    color = candidate
                    break
            out[y * width + x] = color
    return bytes(out)


def colorize_bg_frame(index_frame: bytes, palette: tuple[int, ...]) -> bytes:
    """Convert composed palette indices into little-endian GBA BGR555 pixels."""
    out = bytearray(len(index_frame) * 2)
    for index, palette_index in enumerate(index_frame):
        color = int(palette[palette_index]) if palette_index < len(palette) else 0
        out[index * 2] = color & 0xFF
        out[index * 2 + 1] = (color >> 8) & 0xFF
    return bytes(out)


def color_frame_diff(expected: bytes, actual: bytes, *, width: int = 240) -> dict[str, object]:
    """Compare little-endian BGR555 frame buffers one pixel at a time."""
    if len(expected) != len(actual) or len(expected) % 2:
        raise ValueError("color frame buffers must have identical even byte lengths")
    mismatch = 0
    first = None
    for pixel in range(len(expected) // 2):
        off = pixel * 2
        if expected[off:off + 2] == actual[off:off + 2]:
            continue
        mismatch += 1
        if first is None:
            first = (pixel % width, pixel // width)
    return {"mismatch_pixels": mismatch, "first_mismatch": first}


def visible_pixel_detail(
    vram: bytes | bytearray,
    backgrounds: Iterable[Mapping[str, int]],
    x: int,
    y: int,
) -> dict[str, object]:
    ordered = sorted(backgrounds, key=lambda bg: (bg["priority"], bg["bg_index"]))
    for bg in ordered:
        sample = sample_text_bg(
            vram,
            int(bg["screenblock"]),
            int(bg["scroll_x"]),
            int(bg["scroll_y"]),
            x,
            y,
        )
        if int(sample["palette_index"]) == 0:
            continue
        return {
            "bg_index": int(bg["bg_index"]),
            "screenblock": int(bg["screenblock"]),
            **sample,
        }
    return {
        "bg_index": -1,
        "screenblock": -1,
        "palette_index": 0,
        "entry": 0,
        "tile_index": 0,
        "hflip": False,
        "vflip": False,
        "map_x": -1,
        "map_y": -1,
        "map_cell": -1,
        "tile_screenblock_alias": None,
    }

def frame_diff(expected: bytes, actual: bytes, *, width: int = 240) -> dict[str, object]:
    """Return deterministic mismatch count and first differing coordinate."""
    if len(expected) != len(actual):
        raise ValueError("frame buffers must have identical length")
    mismatch = 0
    first = None
    for index, (a, b) in enumerate(zip(expected, actual)):
        if a == b:
            continue
        mismatch += 1
        if first is None:
            first = (index % width, index // width)
    return {"mismatch_pixels": mismatch, "first_mismatch": first}



def _load_local_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _clamp_camera(spec, x: int, y: int) -> tuple[int, int]:
    max_x = (int(spec.width) - 30) * 8
    max_y = (int(spec.height) - 20) * 8
    if x < 0:
        x = 0
    if x > max_x:
        x = max_x
    if y < 0:
        y = 0
    if y > max_y:
        y = max_y
    return int(x), int(y)


def _spawn_camera(spec) -> tuple[int, int]:
    camera_x = 0
    camera_y = 0
    center_x = int(spec.spawn[0]) + 8
    center_y = int(spec.spawn[1]) - 8
    if camera_x < center_x - 144:
        camera_x = center_x - 144
    if camera_x > center_x - 96:
        camera_x = center_x - 96
    if camera_y < center_y - 93:
        camera_y = center_y - 93
    if camera_y > center_y - 67:
        camera_y = center_y - 67
    return _clamp_camera(spec, camera_x, camera_y)


def build_checkpoints(root: Path, rom: bytes) -> list[dict[str, object]]:
    """Return deterministic visible-BG audit checkpoints.

    Mutation checkpoints always start from a freshly loaded level and apply at
    most one ordinary Fgtile patch branch.  Alias checkpoints are selected
    directly from the canonical ROM's high-tile summary; the summary is used
    only to choose camera positions, never as expected frame data.
    """
    root = Path(root)
    generator = _load_local_module(
        root / "tools" / "generate_cfa_assets.py", "generate_cfa_assets_visible_bg"
    )
    render_maps = _load_local_module(
        root / "tools" / "render_maps.py", "render_maps_visible_bg"
    )
    specs = generator.build_level_specs(root)
    actors = generator.build_actor_runtime_data(root)
    rows: list[dict[str, object]] = []

    def add(level: int, camera_x: int, camera_y: int, state_label: str,
            *, mutation_patch_index: int | None = None,
            mutation_branch: str = "", physical_index: int | None = None) -> None:
        camera_x, camera_y = _clamp_camera(specs[level], camera_x, camera_y)
        row = {
            "level": level,
            "camera_x": camera_x,
            "camera_y": camera_y,
            "state_label": state_label,
            "mutation_patch_index": mutation_patch_index,
            "mutation_branch": mutation_branch,
            "physical_index": physical_index,
        }
        key = (level, camera_x, camera_y, state_label, mutation_patch_index)
        if key not in seen:
            seen.add(key)
            rows.append(row)

    seen: set[tuple[object, ...]] = set()
    for level in range(11):
        spec = specs[level]
        spawn_x, spawn_y = _spawn_camera(spec)
        add(level, spawn_x, spawn_y, "spawn")
        max_x = (spec.width - 30) * 8
        max_y = (spec.height - 20) * 8
        for label, x, y in (
            ("corner_top_left", 0, 0),
            ("corner_top_right", max_x, 0),
            ("corner_bottom_left", 0, max_y),
            ("corner_bottom_right", max_x, max_y),
        ):
            add(level, x, y, label)

        player_index = actors.player_indices[level]
        for compact_index, descriptor_index in enumerate(actors.level_indices[level]):
            descriptor = actors.physical[descriptor_index]
            physical_index = compact_index if compact_index < player_index else compact_index + 1
            if not (
                descriptor.actor_class == generator.ACTOR_CLASS_FGTILE
                and descriptor.port_to == 33
                and descriptor.turn in (0, 1)
                and descriptor.treetype not in (1, 20)
            ):
                continue
            camera_x = descriptor.x - 120
            camera_y = descriptor.y - 80
            for branch, patch_index in (
                ("base", descriptor.treetype),
                ("alternate", descriptor.treetype + 1),
            ):
                add(
                    level,
                    camera_x,
                    camera_y,
                    f"fgtile_{physical_index}_{branch}",
                    mutation_patch_index=patch_index,
                    mutation_branch=branch,
                    physical_index=physical_index,
                )

    # Select one camera per level/layer/screenblock alias class.  This keeps the
    # audit compact while guaranteeing Level 2's palette-overrun aliases are
    # visible in at least one deterministic frame checkpoint.
    alias_seen: set[tuple[int, str, int]] = set()
    for alias in render_maps.runtime_alias_summary(rom):
        level = int(alias["level_index"])
        layer = str(alias["layer"])
        screenblock = int(alias["screenblock"])
        alias_key = (level, layer, screenblock)
        if alias_key in alias_seen:
            continue
        alias_seen.add(alias_key)
        cells = str(alias["world_cells"]).split(";")
        if not cells or ":" not in cells[0]:
            continue
        cell_x, cell_y = (int(value) for value in cells[0].split(":"))
        add(
            level,
            cell_x * 8 - 120,
            cell_y * 8 - 80,
            f"alias_{layer}_sb{screenblock}",
        )

    rows.sort(key=lambda row: (
        int(row["level"]), int(row["camera_y"]), int(row["camera_x"]),
        str(row["state_label"]),
        -1 if row["mutation_patch_index"] is None else int(row["mutation_patch_index"]),
    ))
    return rows



ROM_BASE = 0x08000000
INIT_ROM_START = 0x08A8D738
INIT_RAM_START = 0x03000788
FGTILE_PATCH_TABLE_RAM = 0x03000884
FGTILE_PATCH_COUNT = 18
FGTILE_PATCH_SOURCE_BASE_32 = 1680


def _asset_symbol(level: int, variant: int = 0) -> str:
    return f"gb_level{level:02d}" if variant == 0 else f"gb_level{level:02d}_v{variant}"


def _asset_path(root: Path, level: int, variant: int = 0) -> Path:
    suffix = "" if variant == 0 else f"_v{variant}"
    return root / "reconstruction" / "data" / f"level{level:02d}{suffix}_assets.c"


def _parse_u16_array(path: Path, symbol: str) -> tuple[int, ...]:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"const\s+u16\s+{re.escape(symbol)}\s*\[[^\]]+\]\s*=\s*\{{(.*?)\}}\s*;",
        text,
        re.S,
    )
    if not match:
        raise ValueError(f"missing u16 array {symbol} in {path}")
    values = re.findall(r"0x[0-9A-Fa-f]+|(?<![A-Za-z_])\d+", match.group(1))
    return tuple(int(value, 0) for value in values)


def _u16_bytes(values: tuple[int, ...]) -> bytes:
    return struct.pack(f"<{len(values)}H", *values) if values else b""


def _canonical_patch_table(rom: bytes) -> tuple[tuple[int, int, int], ...]:
    table_addr = INIT_ROM_START + (FGTILE_PATCH_TABLE_RAM - INIT_RAM_START)
    off = table_addr - ROM_BASE
    return tuple(
        struct.unpack_from("<III", rom, off + index * 12)
        for index in range(FGTILE_PATCH_COUNT)
    )


def _re_patch_table(root: Path) -> tuple[tuple[int, int, int], ...]:
    text = (root / "reconstruction" / "source" / "engine" / "video.c").read_text(encoding="utf-8")
    match = re.search(
        r"gb_fgtile_tile_patches\s*\[[^\]]+\]\s*=\s*\{(.*?)\};",
        text,
        re.S,
    )
    if not match:
        raise ValueError("production Fgtile patch table is missing")
    rows = tuple(
        tuple(int(value) for value in row)
        for row in re.findall(r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}", match.group(1))
    )
    if len(rows) != FGTILE_PATCH_COUNT:
        raise ValueError(f"expected {FGTILE_PATCH_COUNT} production patch rows, got {len(rows)}")
    return rows


def _write_u16(vram: bytearray, screenblock: int, cell: int, value: int) -> None:
    off = screenblock * SCREENBLOCK_BYTES + cell * 2
    vram[off] = value & 0xFF
    vram[off + 1] = (value >> 8) & 0xFF


def _stream_entry(state: Mapping[str, object], layer_name: str, world_x: int, world_y: int) -> int:
    width = int(state["width"])
    height = int(state["height"])
    cell = world_y * width + world_x
    cell_count = width * height
    layer = state[layer_name]
    assert isinstance(layer, tuple)
    if 0 <= cell < cell_count:
        source_id = int(layer[cell])
        translation = state["translation"]
        assert isinstance(translation, tuple)
        return int(translation[source_id]) if source_id < len(translation) else 0
    if cell < -1 or cell > cell_count + width:
        return 0
    guard = state[f"{layer_name}_guard"]
    assert isinstance(guard, tuple)
    guard_index = 0 if cell < 0 else cell - cell_count + 1
    return int(guard[guard_index])


def _load_maps_into_vram(vram: bytearray, state: Mapping[str, object], camera_x: int, camera_y: int) -> None:
    translation = state["translation"]
    fixed_map = state["fixed_map"]
    assert isinstance(translation, tuple)
    assert isinstance(fixed_map, tuple)
    fixed_width = int(state["fixed_width"])
    fixed_height = int(state["fixed_height"])

    # Level load clears BG1/BG2/BG3; BG0 is also clear in normal gameplay.
    for screenblock in (27, 28, 29, 30):
        start = screenblock * SCREENBLOCK_BYTES
        vram[start:start + SCREENBLOCK_BYTES] = b"\0" * SCREENBLOCK_BYTES

    for y in range(min(fixed_height, 32)):
        for x in range(fixed_width):
            source_id = int(fixed_map[y * fixed_width + x])
            entry = int(translation[source_id]) if source_id < len(translation) else 0
            if x < 32:
                _write_u16(vram, 29, y * 32 + x, entry)
            elif x < 64:
                _write_u16(vram, 30, y * 32 + (x - 32), entry)

    left = camera_x >> 3
    top = camera_y >> 3
    for layer_name, screenblock in (("layer_a", 29), ("layer_b", 28)):
        for row in range(21):
            world_y = top + row
            for column in range(31):
                world_x = left + column
                entry = _stream_entry(state, layer_name, world_x, world_y)
                ring_cell = (world_y & 31) * 32 + (world_x & 31)
                _write_u16(vram, screenblock, ring_cell, entry)


def _apply_patch_canonical(
    vram: bytearray,
    rom: bytes,
    graphics,
    table: tuple[tuple[int, int, int], ...],
    patch_index: int | None,
) -> None:
    if patch_index is None:
        return
    destination_32, source_32, count_64 = table[patch_index]
    destination = destination_32 * 32
    count = count_64 * 64
    source = int(graphics.bg_tiles_addr) + source_32 * 32 - ROM_BASE
    vram[destination:destination + count] = rom[source:source + count]


def _apply_patch_re(
    vram: bytearray,
    state: Mapping[str, object],
    table: tuple[tuple[int, int, int], ...],
    patch_index: int | None,
) -> None:
    if patch_index is None:
        return
    destination_32, source_32, count_64 = table[patch_index]
    if source_32 < FGTILE_PATCH_SOURCE_BASE_32:
        raise ValueError("production patch source precedes checked-in patch source base")
    destination = destination_32 * 32
    count = count_64 * 64
    relative = (source_32 - FGTILE_PATCH_SOURCE_BASE_32) * 32
    patch_source = state["patch_source"]
    assert isinstance(patch_source, bytes)
    if relative + count > len(patch_source):
        raise ValueError("production patch source overruns checked-in patch bytes")
    vram[destination:destination + count] = patch_source[relative:relative + count]


def _backgrounds(camera_x: int, camera_y: int) -> tuple[dict[str, int], ...]:
    # C99 signed integer division truncates toward zero.
    parallax_x = int(camera_x / 4)
    parallax_y = int(camera_y / 4)
    return (
        {"bg_index": 0, "priority": 0, "screenblock": 27, "scroll_x": 0, "scroll_y": 0},
        {"bg_index": 1, "priority": 1, "screenblock": 28, "scroll_x": camera_x, "scroll_y": camera_y},
        {"bg_index": 2, "priority": 2, "screenblock": 29, "scroll_x": camera_x, "scroll_y": camera_y},
        {"bg_index": 3, "priority": 3, "screenblock": 30, "scroll_x": parallax_x, "scroll_y": parallax_y},
    )


class _AuditContext:
    def __init__(self, root: Path, rom: bytes):
        self.root = Path(root)
        self.rom = rom
        self.generator = _load_local_module(
            self.root / "tools" / "generate_cfa_assets.py", "generate_cfa_assets_visible_frame_ctx"
        )
        self.specs = self.generator.build_level_specs(self.root)
        self.variants = self.generator.build_graphics_variants(self.root)
        self.canonical_patch_table = _canonical_patch_table(rom)
        self.production_patch_table = _re_patch_table(self.root)
        self._canonical_states: dict[int, dict[str, object]] = {}
        self._re_states: dict[int, dict[str, object]] = {}

    def canonical_state(self, level: int) -> dict[str, object]:
        cached = self._canonical_states.get(level)
        if cached is not None:
            return cached
        spec = self.specs[level]
        runtime = self.generator.load_runtime_background(self.root, self.rom, spec, 0)
        state: dict[str, object] = {
            "width": spec.width,
            "height": spec.height,
            "fixed_width": spec.fixed_width,
            "fixed_height": spec.fixed_height,
            "palette": runtime.palette,
            "tile_bytes": runtime.tile_bytes,
            "patch_source": runtime.patch_source_bytes,
            "translation": runtime.translation,
            "layer_a": runtime.layer_a,
            "layer_b": runtime.layer_b,
            "layer_a_guard": runtime.layer_a_guard,
            "layer_b_guard": runtime.layer_b_guard,
            "fixed_map": runtime.fixed_map,
        }
        self._canonical_states[level] = state
        return state

    def re_state(self, level: int) -> dict[str, object]:
        cached = self._re_states.get(level)
        if cached is not None:
            return cached
        spec = self.specs[level]
        path = _asset_path(self.root, level, 0)
        symbol = _asset_symbol(level, 0)
        tile_words = _parse_u16_array(path, f"{symbol}_bg_tiles")
        patch_words = _parse_u16_array(path, f"{symbol}_bg_patch_source")
        state: dict[str, object] = {
            "width": spec.width,
            "height": spec.height,
            "fixed_width": spec.fixed_width,
            "fixed_height": spec.fixed_height,
            "palette": _parse_u16_array(path, f"{symbol}_bg_palette"),
            "tile_bytes": _u16_bytes(tile_words),
            "patch_source": _u16_bytes(patch_words),
            "translation": _parse_u16_array(path, f"{symbol}_translation"),
            "layer_a": _parse_u16_array(path, f"{symbol}_layer_a"),
            "layer_b": _parse_u16_array(path, f"{symbol}_layer_b"),
            "layer_a_guard": _parse_u16_array(path, f"{symbol}_layer_a_guard"),
            "layer_b_guard": _parse_u16_array(path, f"{symbol}_layer_b_guard"),
            "fixed_map": _parse_u16_array(path, f"{symbol}_fixed_map"),
        }
        self._re_states[level] = state
        return state

    def frame(self, checkpoint: Mapping[str, object], *, canonical: bool) -> tuple[bytes, bytearray]:
        level = int(checkpoint["level"])
        camera_x = int(checkpoint["camera_x"])
        camera_y = int(checkpoint["camera_y"])
        patch_index_raw = checkpoint.get("mutation_patch_index")
        patch_index = None if patch_index_raw is None else int(patch_index_raw)
        state = self.canonical_state(level) if canonical else self.re_state(level)
        tile_bytes = state["tile_bytes"]
        assert isinstance(tile_bytes, bytes)
        vram = bytearray(BG_VRAM_BYTES)
        vram[:len(tile_bytes)] = tile_bytes
        _load_maps_into_vram(vram, state, camera_x, camera_y)
        if canonical:
            _apply_patch_canonical(
                vram,
                self.rom,
                self.variants[(level, 0)],
                self.canonical_patch_table,
                patch_index,
            )
        else:
            _apply_patch_re(vram, state, self.production_patch_table, patch_index)
        frame = compose_bg_frame(vram, _backgrounds(camera_x, camera_y))
        return frame, vram


def build_canonical_frame(root: Path, rom: bytes, checkpoint: Mapping[str, object]) -> bytes:
    return _AuditContext(Path(root), rom).frame(checkpoint, canonical=True)[0]


def build_re_frame(root: Path, rom: bytes, checkpoint: Mapping[str, object]) -> bytes:
    return _AuditContext(Path(root), rom).frame(checkpoint, canonical=False)[0]


def _visible_alias_summary(vram: bytes | bytearray, backgrounds) -> tuple[int, str]:
    count = 0
    screenblocks: set[int] = set()
    for y in range(160):
        for x in range(240):
            detail = visible_pixel_detail(vram, backgrounds, x, y)
            alias = detail.get("tile_screenblock_alias")
            if alias is None:
                continue
            count += 1
            screenblocks.add(int(alias))
    return count, ";".join(str(value) for value in sorted(screenblocks))


REPORT_FIELDS = (
    "level", "camera_x", "camera_y", "state_label", "physical_index",
    "mutation_branch", "mutation_patch_index", "expected_sha256", "re_sha256",
    "mismatch_pixels", "visible_alias_pixels", "visible_alias_screenblocks",
    "first_mismatch_x", "first_mismatch_y", "classification",
    "expected_bg_index", "re_bg_index", "expected_screenblock", "re_screenblock",
    "expected_entry", "re_entry", "expected_tile_index", "re_tile_index",
    "expected_palette_index", "re_palette_index", "expected_color", "re_color",
    "expected_tile_alias_sb", "re_tile_alias_sb",
)


def _mismatch_classification(
    expected: Mapping[str, object], actual: Mapping[str, object],
    expected_color: int, actual_color: int,
) -> str:
    if int(expected["bg_index"]) != int(actual["bg_index"]):
        return "priority_or_transparency"
    if int(expected["entry"]) != int(actual["entry"]):
        return "tilemap_entry"
    if int(expected["tile_index"]) != int(actual["tile_index"]):
        return "tile_index"
    if int(expected["palette_index"]) != int(actual["palette_index"]):
        if expected.get("tile_screenblock_alias") is not None or actual.get("tile_screenblock_alias") is not None:
            return "screenblock_alias_pixels"
        return "tile_graphics"
    if expected_color != actual_color:
        return "palette_color"
    if expected.get("tile_screenblock_alias") is not None or actual.get("tile_screenblock_alias") is not None:
        return "screenblock_alias_pixels"
    return "pixel_state"


def build_visible_bg_report(root: Path, rom: bytes, checkpoints=None) -> list[dict[str, object]]:
    context = _AuditContext(Path(root), rom)
    rows: list[dict[str, object]] = []
    selected = build_checkpoints(Path(root), rom) if checkpoints is None else list(checkpoints)
    for checkpoint in selected:
        expected_indices, expected_vram = context.frame(checkpoint, canonical=True)
        actual_indices, actual_vram = context.frame(checkpoint, canonical=False)
        level = int(checkpoint["level"])
        expected_palette = context.canonical_state(level)["palette"]
        actual_palette = context.re_state(level)["palette"]
        assert isinstance(expected_palette, tuple) and isinstance(actual_palette, tuple)
        expected = colorize_bg_frame(expected_indices, expected_palette)
        actual = colorize_bg_frame(actual_indices, actual_palette)
        diff = color_frame_diff(expected, actual)
        first = diff["first_mismatch"]
        backgrounds = _backgrounds(int(checkpoint["camera_x"]), int(checkpoint["camera_y"]))
        if str(checkpoint["state_label"]).startswith("alias_"):
            visible_alias_pixels, visible_alias_screenblocks = _visible_alias_summary(
                expected_vram, backgrounds
            )
        else:
            visible_alias_pixels, visible_alias_screenblocks = 0, ""
        row: dict[str, object] = {
            **checkpoint,
            "expected_sha256": hashlib.sha256(expected).hexdigest(),
            "re_sha256": hashlib.sha256(actual).hexdigest(),
            **diff,
            "visible_alias_pixels": visible_alias_pixels,
            "visible_alias_screenblocks": visible_alias_screenblocks,
            "first_mismatch_x": "",
            "first_mismatch_y": "",
            "classification": "match",
            "expected_bg_index": "",
            "re_bg_index": "",
            "expected_screenblock": "",
            "re_screenblock": "",
            "expected_entry": "",
            "re_entry": "",
            "expected_tile_index": "",
            "re_tile_index": "",
            "expected_palette_index": "",
            "re_palette_index": "",
            "expected_color": "",
            "re_color": "",
            "expected_tile_alias_sb": "",
            "re_tile_alias_sb": "",
        }
        if first is not None:
            x, y = first
            expected_detail = visible_pixel_detail(expected_vram, backgrounds, x, y)
            actual_detail = visible_pixel_detail(actual_vram, backgrounds, x, y)
            expected_palette_index = int(expected_detail["palette_index"])
            actual_palette_index = int(actual_detail["palette_index"])
            expected_color = (int(expected_palette[expected_palette_index])
                              if expected_palette_index < len(expected_palette) else 0)
            actual_color = (int(actual_palette[actual_palette_index])
                            if actual_palette_index < len(actual_palette) else 0)
            row.update({
                "first_mismatch_x": x,
                "first_mismatch_y": y,
                "classification": _mismatch_classification(
                    expected_detail, actual_detail, expected_color, actual_color
                ),
                "expected_bg_index": expected_detail["bg_index"],
                "re_bg_index": actual_detail["bg_index"],
                "expected_screenblock": expected_detail["screenblock"],
                "re_screenblock": actual_detail["screenblock"],
                "expected_entry": expected_detail["entry"],
                "re_entry": actual_detail["entry"],
                "expected_tile_index": expected_detail["tile_index"],
                "re_tile_index": actual_detail["tile_index"],
                "expected_palette_index": expected_detail["palette_index"],
                "re_palette_index": actual_detail["palette_index"],
                "expected_color": expected_color,
                "re_color": actual_color,
                "expected_tile_alias_sb": (
                    "" if expected_detail["tile_screenblock_alias"] is None
                    else expected_detail["tile_screenblock_alias"]
                ),
                "re_tile_alias_sb": (
                    "" if actual_detail["tile_screenblock_alias"] is None
                    else actual_detail["tile_screenblock_alias"]
                ),
            })
        rows.append(row)
    return rows


def write_visible_bg_report(root: Path, rom: bytes, out: Path) -> None:
    rows = build_visible_bg_report(Path(root), rom)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            serialized = {field: row.get(field, "") for field in REPORT_FIELDS}
            for field in ("expected_entry", "re_entry", "expected_color", "re_color"):
                if serialized[field] != "":
                    serialized[field] = f"0x{int(serialized[field]):04X}"
            writer.writerow(serialized)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, default=root / "data" / "visible_bg_frame_parity.csv"
    )
    args = parser.parse_args()
    write_visible_bg_report(args.root, args.rom.read_bytes(), args.out)


if __name__ == "__main__":
    main()
