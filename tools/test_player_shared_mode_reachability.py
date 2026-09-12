#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import extract_extended_semantics as semantics

ROM = Path(os.environ.get('GRAVEBLOOD_ROM', ROOT.parent / 'Graveblood 0.0.1.1.5.2 demo.gba'))


class PlayerSharedModeReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = ROM.read_bytes()

    def test_public_demo_closes_shared_mode1_as_unreachable(self):
        row = semantics.extract_player_shared_mode_reachability(self.data)

        self.assertEqual('0x030005F4', row['shared_mode_global'])
        self.assertEqual(0, row['boot_initial_value'])
        self.assertEqual('0;2', row['reachable_values_from_normal_boot'])
        self.assertEqual('no', row['mode1_reachable_from_normal_boot'])
        self.assertEqual('yes', row['mode2_reachable_from_normal_boot'])
        self.assertEqual('0x080041CE', row['mode2_writer'])
        self.assertEqual('0x08005A7C', row['scene_entry_normalizer'])
        self.assertEqual('0x080093AA', row['level10_clear_writer'])
        self.assertEqual('preserve 2; otherwise write 0', row['scene_entry_policy'])
        self.assertEqual('0x08006818;0x08006A66;0x08008A5C', row['dormant_mode1_code_sites'])
        self.assertIn('no code-proven writer of 1', row['closure_result'])

    def test_checked_in_reachability_evidence_matches_extractor(self):
        import csv

        evidence = ROOT / 'data/player_shared_mode_reachability.csv'
        self.assertTrue(evidence.exists(), 'missing shared-mode reachability evidence CSV')
        with evidence.open(newline='', encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(1, len(rows))
        expected = semantics.extract_player_shared_mode_reachability(self.data)
        self.assertEqual({key: str(value) for key, value in expected.items()}, rows[0])

    def test_writer_candidate_inventory_distinguishes_false_aliases(self):
        row = semantics.extract_player_shared_mode_reachability(self.data)
        self.assertEqual(65, row['candidate_literal_load_roots'])
        self.assertEqual(
            '0x080041CE;0x080041EC;0x08004230;0x0800424C;0x08004276;'
            '0x0800428A;0x0800429E;0x080042D0;0x080042DC;0x080042E8;'
            '0x08005A7C;0x08008986;0x08009046;0x08009094;0x080093AA',
            row['conservative_candidate_store_sites'],
        )
        self.assertEqual('0x080041CE;0x08005A7C;0x080093AA', row['resolved_true_write_sites'])
        self.assertEqual(
            '0x080041EC;0x08004230;0x0800424C;0x08004276;0x0800428A;'
            '0x0800429E;0x080042D0;0x080042DC;0x080042E8;0x08008986;'
            '0x08009046;0x08009094',
            row['resolved_false_alias_sites'],
        )


if __name__ == '__main__':
    unittest.main()
