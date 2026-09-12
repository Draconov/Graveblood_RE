#!/usr/bin/env python3
from __future__ import annotations

import csv
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


class PlayerSelectCounterClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = ROM.read_bytes()

    def test_fresh_select_counter_is_reachable_but_has_no_proven_gameplay_consumer(self):
        row = semantics.extract_player_select_counter_closure(self.data)

        self.assertEqual('Player+0x1BC', row['field'])
        self.assertEqual(11, row['constructor_initial_value'])
        self.assertEqual(3, row['lower_bound'])
        self.assertEqual(8, row['accepted_fresh_select_presses_per_spawn'])
        self.assertEqual('fresh SELECT (current bit 0x0004 set; previous clear)', row['input_gate'])
        self.assertEqual('0x08008518', row['primary_gate_transfer'])
        self.assertEqual('0x080090BE', row['decrement_store'])
        self.assertEqual('0x080090C0 -> 0x0800851C', row['post_decrement_transfer'])
        self.assertEqual('0x08008708 -> 0x080090C4', row['state12_block_entry'])
        self.assertEqual('no', row['select_reaches_state12_block'])
        self.assertEqual('none code-proven beyond the counter guard/decrement itself', row['gameplay_consumer'])
        self.assertEqual('standalone SELECT remains inert in the clean-room runtime', row['reconstruction_policy'])

    def test_checked_in_select_counter_evidence_matches_extractor(self):
        evidence = ROOT / 'data/player_select_counter_closure.csv'
        self.assertTrue(evidence.exists(), 'missing SELECT-counter closure evidence CSV')
        with evidence.open(newline='', encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(1, len(rows))
        expected = semantics.extract_player_select_counter_closure(self.data)
        self.assertEqual({key: str(value) for key, value in expected.items()}, rows[0])

    def test_cleanroom_player_does_not_invent_a_standalone_select_action(self):
        source = (ROOT / 'reconstruction/source/game/player.c').read_text(encoding='utf-8')
        self.assertNotIn('KEY_SELECT', source)
        self.assertNotIn('GB_INPUT_KEY_SELECT', source)


if __name__ == '__main__':
    unittest.main()
