#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import os
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000


class StoryOverlayUpdateOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM.read_bytes()

    def test_rom_loads_story_overlay_list_before_physical_level_actor_list(self):
        # load_level_record_resources selects the story-overlay list, passes it
        # to the generic actor-list loader, then loads LevelRecord+0x38 and
        # passes that physical list to the same loader.  The generic object
        # manager preserves insertion order, so every overlay precedes Player.
        seq = tuple(struct.unpack_from('<H', self.data, addr - ROM_BASE)[0]
                    for addr in range(0x08005988, 0x080059B2, 2))
        self.assertEqual(seq, (
            0x6B2B, 0x009A, 0x4B22, 0x4E23, 0x189B, 0x6B59, 0x0030,
            0xF7FB, 0xFB85,
            0x69A8, 0xF7FF, 0xFF1E, 0x2201, 0x491F, 0x481F,
            0xF004, 0xFD2B,
            0x6BA1, 0x0030, 0xF7FB, 0xFB79,
        ))

    def test_overlay_update_order_csv_matches_rom_extractor(self):
        spec = importlib.util.spec_from_file_location(
            'extract_extended_semantics', ROOT / 'tools/extract_extended_semantics.py')
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'extract_story_overlay_update_order'),
                        'story-overlay update-order extractor is missing')
        expected = module.extract_story_overlay_update_order(self.data)
        csv_path = ROOT / 'data/story_overlay_update_order.csv'
        self.assertTrue(csv_path.is_file(), csv_path)
        with csv_path.open(newline='', encoding='utf-8') as f:
            actual = list(csv.DictReader(f))
        self.assertEqual(actual, expected)

    def test_clean_room_keeps_story_overlay_phase_before_player(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        overlay = game.index('gb_actor_system_update_overlays(&actors, &player, &input, &interaction);')
        player = game.index('gb_player_update(&player, world.assets, &input);')
        self.assertLess(overlay, player,
                        'story overlays are inserted before the physical list and must update before Player')


if __name__ == '__main__':
    unittest.main()
