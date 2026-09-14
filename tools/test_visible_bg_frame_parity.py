#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import inspect
import os
import re
import shutil
import tempfile
import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools" / "audit_visible_bg_frames.py"


def rom_path():
    value = os.environ.get("GRAVEBLOOD_ROM")
    if not value:
        raise unittest.SkipTest("GRAVEBLOOD_ROM is required")
    return Path(value)


def load_module():
    spec = importlib.util.spec_from_file_location("audit_visible_bg_frames_test", AUDIT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VisibleBgFrameParityTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_audit_module_exists(self):
        self.assertTrue(AUDIT.is_file(), "visible BG frame audit tool is missing")

    def test_public_compositor_helpers_exist(self):
        for name in ("sample_text_bg", "compose_bg_frame", "frame_diff"):
            self.assertTrue(callable(getattr(self.mod, name, None)), f"missing helper {name}")

    def test_checkpoint_builder_exists(self):
        self.assertTrue(callable(getattr(self.mod, "build_checkpoints", None)),
                        "missing build_checkpoints")

    def test_frame_builders_exist(self):
        for name in ("build_canonical_frame", "build_re_frame", "build_visible_bg_report"):
            self.assertTrue(callable(getattr(self.mod, name, None)), f"missing {name}")

    def test_report_api_accepts_explicit_checkpoint_subset(self):
        parameters = inspect.signature(self.mod.build_visible_bg_report).parameters
        self.assertIn("checkpoints", parameters)

    def test_report_writer_exists(self):
        self.assertTrue(callable(getattr(self.mod, "write_visible_bg_report", None)),
                        "missing write_visible_bg_report")

    def test_checked_in_report_exists(self):
        report = ROOT / "data" / "visible_bg_frame_parity.csv"
        self.assertTrue(report.is_file(), report)

    def test_checked_in_report_is_reproducible_and_zero_mismatch(self):
        report = ROOT / "data" / "visible_bg_frame_parity.csv"
        self.assertTrue(report.is_file(), report)
        with tempfile.TemporaryDirectory() as td_raw:
            regenerated = Path(td_raw) / "visible_bg_frame_parity.csv"
            self.mod.write_visible_bg_report(ROOT, rom_path().read_bytes(), regenerated)
            self.assertEqual(report.read_bytes(), regenerated.read_bytes())
        with report.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(121, len(rows))
        self.assertEqual(set(range(11)), {int(row["level"]) for row in rows})
        self.assertEqual([], [row for row in rows if int(row["mismatch_pixels"]) != 0])
        self.assertTrue(any(int(row["visible_alias_pixels"]) > 0 for row in rows))

    def test_canonical_and_checked_in_re_match_level1_spawn(self):
        rom = rom_path().read_bytes()
        checkpoint = next(
            row for row in self.mod.build_checkpoints(ROOT, rom)
            if row["level"] == 1 and row["state_label"] == "spawn"
        )
        canonical = self.mod.build_canonical_frame(ROOT, rom, checkpoint)
        actual = self.mod.build_re_frame(ROOT, rom, checkpoint)
        self.assertEqual(240 * 160, len(canonical))
        self.assertEqual(canonical, actual)

    def test_level2_alias_checkpoint_reports_visible_screenblock_alias_pixels(self):
        rom = rom_path().read_bytes()
        checkpoint = next(
            row for row in self.mod.build_checkpoints(ROOT, rom)
            if row["level"] == 2 and row["state_label"] == "alias_B_sb30"
        )
        row = self.mod.build_visible_bg_report(ROOT, rom, [checkpoint])[0]
        self.assertIn("visible_alias_pixels", row)
        self.assertIn("visible_alias_screenblocks", row)
        self.assertGreater(row["visible_alias_pixels"], 0)
        self.assertIn("30", row["visible_alias_screenblocks"].split(";"))

    def test_mutated_checked_in_tile_is_reported_with_first_pixel_diagnostics(self):
        rom = rom_path().read_bytes()
        checkpoint = next(
            row for row in self.mod.build_checkpoints(ROOT, rom)
            if row["level"] == 1 and row["state_label"] == "spawn"
        )
        with tempfile.TemporaryDirectory() as td_raw:
            temp_root = Path(td_raw) / "repo"
            temp_root.mkdir()
            os.symlink(ROOT / "data", temp_root / "data", target_is_directory=True)
            os.symlink(ROOT / "tools", temp_root / "tools", target_is_directory=True)
            (temp_root / "reconstruction").mkdir()
            os.symlink(
                ROOT / "reconstruction" / "source",
                temp_root / "reconstruction" / "source",
                target_is_directory=True,
            )
            (temp_root / "reconstruction" / "data").mkdir()
            source = ROOT / "reconstruction" / "data" / "level01_assets.c"
            text = source.read_text(encoding="utf-8")
            pattern = r"(const\s+u16\s+gb_level01_bg_tiles\[[^]]+\]\s*=\s*\{\s*)(?:0x[0-9A-Fa-f]+|\d+)"
            mutated, count = re.subn(pattern, r"\g<1>0x0101", text, count=1)
            self.assertEqual(1, count)
            (temp_root / "reconstruction" / "data" / "level01_assets.c").write_text(
                mutated, encoding="utf-8"
            )

            row = self.mod.build_visible_bg_report(temp_root, rom, [checkpoint])[0]
            self.assertGreater(row["mismatch_pixels"], 0)
            self.assertEqual((0, 0), row["first_mismatch"])
            for key in (
                "expected_bg_index", "re_bg_index",
                "expected_entry", "re_entry",
                "expected_tile_index", "re_tile_index",
                "expected_palette_index", "re_palette_index",
            ):
                self.assertIn(key, row)
            self.assertEqual(0, row["re_bg_index"])
            self.assertEqual(0, row["re_tile_index"])
            self.assertEqual(1, row["re_palette_index"])

    def test_mutated_checked_in_palette_is_reported_as_visible_color_mismatch(self):
        rom = rom_path().read_bytes()
        checkpoint = next(
            row for row in self.mod.build_checkpoints(ROOT, rom)
            if row["level"] == 1 and row["state_label"] == "spawn"
        )
        canonical = self.mod.build_canonical_frame(ROOT, rom, checkpoint)
        palette_index = max(set(canonical), key=canonical.count)
        self.assertNotEqual(0, palette_index)

        with tempfile.TemporaryDirectory() as td_raw:
            temp_root = Path(td_raw) / "repo"
            temp_root.mkdir()
            os.symlink(ROOT / "data", temp_root / "data", target_is_directory=True)
            os.symlink(ROOT / "tools", temp_root / "tools", target_is_directory=True)
            (temp_root / "reconstruction").mkdir()
            os.symlink(
                ROOT / "reconstruction" / "source",
                temp_root / "reconstruction" / "source",
                target_is_directory=True,
            )
            (temp_root / "reconstruction" / "data").mkdir()
            source = ROOT / "reconstruction" / "data" / "level01_assets.c"
            text = source.read_text(encoding="utf-8")
            match = re.search(
                r"(const\s+u16\s+gb_level01_bg_palette\[[^]]+\]\s*=\s*\{)(.*?)(\}\s*;)",
                text, re.S,
            )
            self.assertIsNotNone(match)
            body = match.group(2)
            tokens = list(re.finditer(r"0x[0-9A-Fa-f]+|(?<![A-Za-z_])\d+", body))
            self.assertGreater(len(tokens), palette_index)
            token = tokens[palette_index]
            original = int(token.group(0), 0)
            replacement = 0x7FFF if original != 0x7FFF else 0x001F
            mutated_body = body[:token.start()] + f"0x{replacement:04X}" + body[token.end():]
            mutated = text[:match.start(2)] + mutated_body + text[match.end(2):]
            (temp_root / "reconstruction" / "data" / "level01_assets.c").write_text(
                mutated, encoding="utf-8"
            )

            row = self.mod.build_visible_bg_report(temp_root, rom, [checkpoint])[0]
            self.assertGreater(row["mismatch_pixels"], 0)
            self.assertEqual("palette_color", row["classification"])
            self.assertEqual(palette_index, row["expected_palette_index"])
            self.assertEqual(palette_index, row["re_palette_index"])
            self.assertNotEqual(row["expected_color"], row["re_color"])

    def test_checkpoint_builder_covers_all_levels_edges_patches_and_level2_alias(self):
        checkpoints = self.mod.build_checkpoints(ROOT, rom_path().read_bytes())
        self.assertEqual(set(range(11)), {row["level"] for row in checkpoints})
        for level in range(11):
            labels = {row["state_label"] for row in checkpoints if row["level"] == level}
            self.assertIn("spawn", labels)
            self.assertTrue(any(label.startswith("corner_") for label in labels), level)

        patch_rows = [row for row in checkpoints if row["state_label"].startswith("fgtile_")]
        self.assertTrue(patch_rows, "ordinary Fgtile patch checkpoints are missing")
        branches = {row["mutation_branch"] for row in patch_rows}
        self.assertEqual({"base", "alternate"}, branches)
        self.assertTrue(any(row["level"] == 2 and row["state_label"].startswith("alias_")
                            for row in checkpoints),
                        "Level 2 high-tile alias checkpoint is missing")

        keys = [(row["level"], row["camera_x"], row["camera_y"], row["state_label"],
                 row.get("mutation_patch_index")) for row in checkpoints]
        self.assertEqual(len(keys), len(set(keys)))

    def _vram(self):
        return bytearray(0x10000)

    def _set_map_entry(self, vram: bytearray, screenblock: int, cell: int, entry: int):
        off = screenblock * 0x800 + cell * 2
        vram[off] = entry & 0xFF
        vram[off + 1] = entry >> 8

    def test_samples_8bpp_text_tile_and_flip_bits(self):
        vram = self._vram()
        tile = 5
        tile_off = tile * 64
        vram[tile_off + 3 * 8 + 2] = 7
        vram[tile_off + (7 - 3) * 8 + (7 - 2)] = 9

        self._set_map_entry(vram, 28, 0, tile)
        normal = self.mod.sample_text_bg(vram, 28, 0, 0, 2, 3)
        self.assertEqual(7, normal["palette_index"])
        self.assertEqual(tile, normal["tile_index"])
        self.assertEqual(tile, normal["entry"])

        self._set_map_entry(vram, 28, 0, tile | 0x0400 | 0x0800)
        flipped = self.mod.sample_text_bg(vram, 28, 0, 0, 2, 3)
        self.assertEqual(9, flipped["palette_index"])
        self.assertTrue(flipped["hflip"])
        self.assertTrue(flipped["vflip"])

    def test_scroll_wraps_32x32_text_map(self):
        vram = self._vram()
        tile = 6
        vram[tile * 64] = 11
        self._set_map_entry(vram, 28, 1, tile)
        sample = self.mod.sample_text_bg(vram, 28, 8, 0, 0, 0)
        self.assertEqual(11, sample["palette_index"])
        self.assertEqual(1, sample["map_x"])
        self.assertEqual(0, sample["map_y"])

        # 256-pixel text-BG wrapping: x=248 + scroll 8 wraps to map column 0.
        self._set_map_entry(vram, 28, 0, tile)
        wrapped = self.mod.sample_text_bg(vram, 28, 8, 0, 248, 0)
        self.assertEqual(0, wrapped["map_x"])
        self.assertEqual(11, wrapped["palette_index"])

    def test_high_tile_fetch_aliases_screenblock_bytes(self):
        vram = self._vram()
        # Tile 864 starts exactly at 0xD800, screenblock 27.
        vram[0xD800 + 2 * 8 + 1] = 13
        self._set_map_entry(vram, 28, 0, 864)
        sample = self.mod.sample_text_bg(vram, 28, 0, 0, 1, 2)
        self.assertEqual(864, sample["tile_index"])
        self.assertEqual(13, sample["palette_index"])
        self.assertEqual(27, sample["tile_screenblock_alias"])

    def test_composes_priority_and_palette_zero_transparency(self):
        vram = self._vram()
        # BG0 tile 1 is transparent at pixel (0,0); BG1 tile 2 is opaque.
        vram[2 * 64] = 5
        self._set_map_entry(vram, 27, 0, 1)
        self._set_map_entry(vram, 28, 0, 2)
        backgrounds = [
            {"bg_index": 0, "priority": 0, "screenblock": 27, "scroll_x": 0, "scroll_y": 0},
            {"bg_index": 1, "priority": 1, "screenblock": 28, "scroll_x": 0, "scroll_y": 0},
        ]
        frame = self.mod.compose_bg_frame(vram, backgrounds, width=1, height=1)
        self.assertEqual(bytes([5]), frame)

        vram[1 * 64] = 7
        frame = self.mod.compose_bg_frame(vram, backgrounds, width=1, height=1)
        self.assertEqual(bytes([7]), frame)

    def test_frame_diff_reports_count_and_first_coordinate(self):
        expected = bytes([1, 2, 3, 4, 5, 6])
        actual = bytes([1, 9, 3, 8, 5, 6])
        diff = self.mod.frame_diff(expected, actual, width=3)
        self.assertEqual(2, diff["mismatch_pixels"])
        self.assertEqual((1, 0), diff["first_mismatch"])


if __name__ == "__main__":
    unittest.main()
