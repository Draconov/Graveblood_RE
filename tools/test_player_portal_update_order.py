#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))


class PlayerPortalUpdateOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM.read_bytes()
        spec = importlib.util.spec_from_file_location('extract_structure', ROOT / 'tools/extract_structure.py')
        cls.structure = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.structure)
        with (ROOT / 'data/levels.csv').open(newline='', encoding='utf-8') as f:
            cls.levels = {int(row['level_index']): row for row in csv.DictReader(f)}
        with (ROOT / 'data/portal_edges.csv').open(newline='', encoding='utf-8') as f:
            cls.edges = {(int(row['source_level']), int(row['actor_rom_offset'], 16)): row
                         for row in csv.DictReader(f)}

    def _level_actors(self, level: int):
        off = int(self.levels[level]['actor_table_rom_offset'], 16)
        return [(index, rom_off, self.structure.actor_dict(props))
                for index, (rom_off, props) in enumerate(self.structure.walk_actor_table(self.data, off))]

    def test_generic_portals_split_six_pre_player_and_twenty_seven_post_player(self):
        pre = []
        post = []
        for level in range(11):
            actors = self._level_actors(level)
            player_index = next(index for index, _, actor in actors if actor.get('type') == 'player')
            for index, rom_off, _ in actors:
                edge = self.edges.get((level, rom_off))
                if edge is None:
                    continue
                row = (level, index, rom_off + 0x08000000, int(edge['destination']))
                (pre if index < player_index else post).append(row)
        self.assertEqual(len(pre), 6)
        self.assertEqual(len(post), 27)
        self.assertEqual([(level, index) for level, index, _, _ in pre],
                         [(1, 0), (1, 1), (8, 0), (8, 1), (8, 2), (8, 3)])

    def test_portal_order_csv_matches_rom_extractor(self):
        spec = importlib.util.spec_from_file_location(
            'extract_extended_semantics', ROOT / 'tools/extract_extended_semantics.py')
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'extract_player_portal_update_order'),
                        'Player/portal order extractor is missing')
        expected = module.extract_player_portal_update_order(self.data)
        csv_path = ROOT / 'data/player_portal_update_order.csv'
        self.assertTrue(csv_path.is_file(), csv_path)
        with csv_path.open(newline='', encoding='utf-8') as f:
            actual = list(csv.DictReader(f))
        self.assertEqual(actual, expected)

    def test_clean_room_evaluates_portals_on_both_sides_of_player_update(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        compact = ' '.join(game.split())
        pre_text = 'gb_portal_try_activate_phase( world.assets, &player, &input, GB_PORTAL_PHASE_PRE_PLAYER);'
        post_text = 'gb_portal_try_activate_phase( world.assets, &player, &input, GB_PORTAL_PHASE_POST_PLAYER);'
        self.assertIn(pre_text, compact, 'pre-Player portal phase is missing')
        self.assertIn(post_text, compact, 'post-Player portal phase is missing')
        pre_call = compact.index(pre_text)
        player_call = compact.index('gb_player_update(&player, world.assets, &input);')
        post_call = compact.index(post_text)
        self.assertLess(pre_call, player_call)
        self.assertLess(player_call, post_call)


if __name__ == '__main__':
    unittest.main()
