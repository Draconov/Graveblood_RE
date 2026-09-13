#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))


class PlayerNpcUpdateOrderTests(unittest.TestCase):
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
        return [(index, rom_off + 0x08000000, self.structure.actor_dict(props))
                for index, (rom_off, props) in enumerate(self.structure.walk_actor_table(self.data, off))]

    def test_all_physical_npcs_update_after_player_in_every_level(self):
        expected_player_indices = {0: 8, 1: 2, 2: 0, 3: 0, 4: 0, 5: 0,
                                   6: 8, 7: 0, 8: 4, 9: 2, 10: 1}
        total_npcs = 0
        for level in range(11):
            actors = self._level_actors(level)
            players = [(i, addr, actor) for i, addr, actor in actors if actor.get('type') == 'player']
            self.assertEqual(len(players), 1, (level, players))
            player_index = players[0][0]
            self.assertEqual(player_index, expected_player_indices[level], level)
            npcs = [(i, addr, actor) for i, addr, actor in actors if actor.get('type') == 'spawner' and actor.get('spawnType') == 'npc']
            total_npcs += len(npcs)
            self.assertTrue(all(i > player_index for i, _, _ in npcs),
                            (level, player_index, [(i, hex(addr)) for i, addr, _ in npcs]))
        self.assertEqual(total_npcs, 92)

    def test_order_csv_matches_rom_extractor(self):
        spec = importlib.util.spec_from_file_location(
            'extract_extended_semantics', ROOT / 'tools/extract_extended_semantics.py')
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'extract_player_npc_update_order'),
                        'Player/NPC order extractor is missing')
        expected = module.extract_player_npc_update_order(self.data)
        csv_path = ROOT / 'data/player_npc_update_order.csv'
        self.assertTrue(csv_path.is_file(), csv_path)
        with csv_path.open(newline='', encoding='utf-8') as f:
            actual = list(csv.DictReader(f))
        self.assertEqual(actual, expected)

    def test_clean_room_updates_physical_npcs_at_their_serialized_post_player_slots(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        compact = ' '.join(game.split())
        self.assertIn('gb_actor_system_update_overlays(&actors, &player, &input, &interaction);', game,
                      'scoped story-overlay update API is missing')
        self.assertIn('gb_actor_system_update_physical_npc_at( &actors, &player, physical_index);', compact,
                      'exact physical-index NPC update API is missing')
        self.assertNotIn('gb_actor_system_update_physical_npcs(&actors, &player);', game,
                         'bulk physical-NPC bucket must not replace serialized traversal')
        player_update = compact.index('gb_player_update(&player, world.assets, &input);')
        overlay_update = compact.index('gb_actor_system_update_overlays(&actors, &player, &input, &interaction);')
        physical_update = compact.index('gb_actor_system_update_physical_npc_at( &actors, &player, physical_index);')
        self.assertLess(overlay_update, player_update)
        self.assertLess(player_update, physical_update,
                        'physical NPC motion/proximity must consume same-frame Player state')


if __name__ == '__main__':
    unittest.main()
