#!/usr/bin/env python3
import csv
import os
import unittest
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_PATH = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))

class WorldProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = ROM_PATH.read_bytes()

    def test_hidden_level9_boundary_evidence_is_machine_readable(self):
        path = ROOT / 'data' / 'player_direct_scene_transitions.csv'
        self.assertTrue(path.exists(), 'missing direct Player transition export')
        with path.open(encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['source_level'], '9')
        self.assertEqual(row['destination'], '10')
        self.assertEqual(row['x_condition'], '>2555')
        self.assertEqual(row['required_mode'], '0')
        self.assertEqual(row['mode_after_request'], '5')
        self.assertEqual(row['delay_updates'], '10')
        self.assertEqual(row['request_callsite'], '0x08008828')
        # Literal pool behind the branch pins threshold=0x9FB and globals.
        self.assertEqual(int.from_bytes(self.rom[0x8550:0x8554], 'little'), 0x000009FB)
        self.assertEqual(int.from_bytes(self.rom[0x88E0:0x88E4], 'little'), 0x03000624)
        self.assertEqual(int.from_bytes(self.rom[0x88E4:0x88E8], 'little'), 0x03000808)
        self.assertEqual(int.from_bytes(self.rom[0x88E8:0x88EC], 'little'), 0x0300080C)

    def test_composed_gameplay_graph_has_34_edges_and_reaches_every_level(self):
        path = ROOT / 'data' / 'world_progression_graph.csv'
        self.assertTrue(path.exists(), 'missing composed world progression graph')
        with path.open(encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        gameplay = [r for r in rows if r['edge_class'] == 'gameplay']
        self.assertEqual(len(gameplay), 34)
        self.assertEqual(sum(r['transition_type'] == 'fgtile_portal' for r in gameplay), 33)
        direct = [r for r in gameplay if r['transition_type'] == 'player_boundary']
        self.assertEqual(len(direct), 1)
        self.assertEqual((direct[0]['source'], direct[0]['destination']), ('9', '10'))
        self.assertEqual(direct[0]['delay_updates'], '10')

        adj = defaultdict(set)
        for row in gameplay:
            adj[int(row['source'])].add(int(row['destination']))
        seen = {7}
        q = deque([7])
        while q:
            src = q.popleft()
            for dst in adj[src]:
                if dst not in seen:
                    seen.add(dst)
                    q.append(dst)
        self.assertEqual(seen, set(range(11)))

        # Movement-only special gates are deliberately not scene edges.
        text = '\n'.join(','.join(r.values()) for r in rows)
        self.assertNotIn('treetype=20', text)
        self.assertNotIn('collection_gate', text)

if __name__ == '__main__':
    unittest.main()
