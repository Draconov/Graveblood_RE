#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))


class PlayerFgtileUpdateOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM.read_bytes()
        spec = importlib.util.spec_from_file_location('extract_structure', ROOT / 'tools/extract_structure.py')
        cls.structure = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.structure)
        with (ROOT / 'data/levels.csv').open(newline='', encoding='utf-8') as f:
            cls.levels = {int(row['level_index']): row for row in csv.DictReader(f)}

    def _level_actors(self, level: int):
        off = int(self.levels[level]['actor_table_rom_offset'], 16)
        return [(index, self.structure.actor_dict(props))
                for index, (_, props) in enumerate(self.structure.walk_actor_table(self.data, off))]

    def test_level9_bicycle_fgtile_updates_after_player(self):
        actors = self._level_actors(9)
        player_index = next(index for index, actor in actors if actor.get('type') == 'player')
        bicycle = [(index, actor) for index, actor in actors if actor.get('type') == 'fgtile' and actor.get('treetype') == '20']
        self.assertEqual(player_index, 2)
        self.assertEqual(len(bicycle), 1)
        self.assertEqual(bicycle[0][0], 11)
        self.assertGreater(bicycle[0][0], player_index)
        self.assertEqual(bicycle[0][1].get('portTo'), '524')

    def test_level10_turn45_gates_update_after_player(self):
        actors = self._level_actors(10)
        player_index = next(index for index, actor in actors if actor.get('type') == 'player')
        gates = [(index, actor) for index, actor in actors
                 if actor.get('type') == 'fgtile' and actor.get('turn') in ('4', '5')]
        self.assertEqual(player_index, 1)
        self.assertEqual([index for index, _ in gates], [13, 14, 15, 16])
        self.assertTrue(all(index > player_index for index, _ in gates))
        self.assertEqual({actor.get('portTo') for _, actor in gates}, {'8'})

    def test_order_csv_matches_rom_extractor(self):
        spec = importlib.util.spec_from_file_location(
            'extract_extended_semantics', ROOT / 'tools/extract_extended_semantics.py')
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'extract_player_fgtile_update_order'),
                        'Player/Fgtile order extractor is missing')
        expected = module.extract_player_fgtile_update_order(self.data)
        csv_path = ROOT / 'data/player_fgtile_update_order.csv'
        self.assertTrue(csv_path.is_file(), csv_path)
        with csv_path.open(newline='', encoding='utf-8') as f:
            actual = list(csv.DictReader(f))
        self.assertEqual(actual, expected)

    def test_clean_room_runs_post_player_fgtile_gates_after_player_update(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        player_update = game.index('gb_player_update(&player, world.assets, &input);')
        level10_gate = game.index('gb_story_try_level10_gate(&story, world.assets, &player, &input)')
        bicycle_gate = game.index('gb_story_try_level9_treetype20_action(world.assets, &player, &input)')
        self.assertLess(player_update, level10_gate)
        self.assertLess(player_update, bicycle_gate)


if __name__ == '__main__':
    unittest.main()
