#!/usr/bin/env python3
import csv
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_PATH = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))
SPEC = importlib.util.spec_from_file_location('render_maps', ROOT / 'tools' / 'render_maps.py')
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class MapRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM_PATH.read_bytes()

    def test_background_control_is_8bpp_text_mode(self):
        bg0 = mod.decode_bg_control(0x1B80)
        bg1 = mod.decode_bg_control(0x1C81)
        bg2 = mod.decode_bg_control(0x1D82)
        bg3 = mod.decode_bg_control(0x1E83)
        self.assertEqual([b['bpp'] for b in (bg0, bg1, bg2, bg3)], [8, 8, 8, 8])
        self.assertEqual([b['screenblock'] for b in (bg0, bg1, bg2, bg3)], [27, 28, 29, 30])
        self.assertEqual([b['priority'] for b in (bg0, bg1, bg2, bg3)], [0, 1, 2, 3])

    def test_level0_fgtile_triggers_resolve_to_variants_1_and_2(self):
        # fgtile code passes treetype+1 into the state-index wrapper.
        self.assertEqual(mod.variant_selector_from_state_index(self.data, 0 + 1), 1)
        self.assertEqual(mod.variant_selector_from_state_index(self.data, 6 + 1), 2)

    def test_level0_variant0_renders_as_8bpp_world(self):
        image = mod.render_level_world(self.data, level_index=0, variant_index=0)
        self.assertEqual(image.size, (2048, 2048))
        # Stable pixel in the road/house area. A 4bpp decoder does not produce this.
        self.assertEqual(image.convert('RGB').getpixel((300, 300)), (148, 156, 180))

    def test_world_composite_respects_bg_priority(self):
        # World layer A is streamed to BG1 (priority 1) and layer B to BG2
        # (priority 2). Where both are opaque, A must be visible on top.
        image = mod.render_level_world(self.data, level_index=0, variant_index=0)
        self.assertEqual(image.getpixel((1176, 80)), (98, 197, 106, 255))

    def test_packed_static_tilemap_splits_bg2_and_bg3(self):
        # The 64x32 source at level+0x1C is two 32-column BG maps packed
        # side-by-side. 0x080057DC writes columns 0..31 to screenblock 29
        # (BG2) and columns 32..63 to screenblock 30 (BG3).
        bg2, bg3, unresolved2, unresolved3 = mod.render_static_bg_layers(
            self.data, level_index=0, variant_index=0
        )
        self.assertEqual(bg2.size, (256, 256))
        self.assertEqual(bg3.size, (256, 256))
        self.assertGreaterEqual(unresolved2, 0)
        self.assertGreaterEqual(unresolved3, 0)

    def test_translation_lookup_is_not_artificially_capped_at_2048(self):
        # Level 2 legitimately contains source IDs above 2047. 0x0800A330
        # performs an unchecked halfword lookup, so the static renderer must
        # model the same address arithmetic instead of inventing a 2048-entry cap.
        _image, runtime_aliases = mod.render_world_layer(self.data, 2, 0, "A")
        self.assertEqual(runtime_aliases, 4)

    def test_level2_layer_a_runtime_alias_is_palette_overrun_into_bg1(self):
        classify = getattr(mod, "runtime_alias_summary", None)
        if classify is None:
            self.fail("runtime alias classification is not implemented")

        rows = classify(self.data)
        match = [
            row for row in rows
            if row["level_index"] == 2
            and row["variant_index"] == 0
            and row["layer"] == "A"
            and row["source_id"] == 2260
        ]
        self.assertEqual(len(match), 1)
        row = match[0]
        self.assertEqual(row["cell_count"], 4)
        self.assertEqual(row["world_cells"], "109:85;119:85;109:96;119:96")
        self.assertEqual(row["lookup_region"], "bg_palette")
        self.assertEqual(row["palette_index"], 210)
        self.assertEqual(row["translation_entry"], 0x7F9D)
        self.assertEqual(row["tile_index"], 925)
        self.assertEqual(row["vram_address"], 0x0600E740)
        self.assertEqual(row["screenblock"], 28)
        self.assertEqual(row["screenblock_offset"], 0x740)
        self.assertEqual(row["screenblock_owner"], "BG1 streamed world layer A")

    def test_runtime_alias_report_is_reproducible_and_complete(self):
        writer = getattr(mod, "write_runtime_alias_summary", None)
        if writer is None:
            self.fail("runtime alias report writer is not implemented")

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "runtime_alias_summary.csv"
            writer(self.data, path)
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 81)
        self.assertEqual(sum(int(row["cell_count"]) for row in rows), 1689)
        self.assertEqual(
            sum(int(row["cell_count"]) for row in rows if row["lookup_region"] == "bg_palette"),
            158,
        )
        row = next(
            row for row in rows
            if row["level_index"] == "2"
            and row["variant_index"] == "0"
            and row["layer"] == "A"
            and row["source_id"] == "2260"
        )
        self.assertEqual(row["lookup_address"], "0x085E2B3C")
        self.assertEqual(row["translation_entry"], "0x7F9D")
        self.assertEqual(row["vram_address"], "0x0600E740")
        self.assertEqual(row["screenblock_offset"], "0x740")

    def test_actor_overlay_labels_only_code_proven_generic_portals_as_portals(self):
        level9_special = {
            'type': 'fgtile', 'portTo': '524', 'treetype': '20', 'turn': '',
        }
        level10_gate = {
            'type': 'fgtile', 'portTo': '8', 'treetype': '', 'turn': '4',
        }
        normal = {
            'type': 'fgtile', 'portTo': '8', 'treetype': '', 'turn': '',
        }
        self.assertEqual('bicycle->Y512', mod.actor_overlay_label(level9_special, 9))
        self.assertEqual('forced-gate', mod.actor_overlay_label(level10_gate, 10))
        self.assertEqual('portal->8', mod.actor_overlay_label(normal, 9))


if __name__ == '__main__':
    unittest.main()
