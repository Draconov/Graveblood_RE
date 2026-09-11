#!/usr/bin/env python3
import csv
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', ROOT.parent / 'Graveblood 0.0.1.1.5.2 demo.gba'))

spec = importlib.util.spec_from_file_location('extract_extended_semantics', ROOT / 'tools/extract_extended_semantics.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class PlayerControllerModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM.read_bytes()

    def test_controller_mode_inventory_is_only_normal_5_6(self):
        rows = mod.extract_player_controller_modes(self.data)
        self.assertEqual({0, 5, 6}, {int(row['mode']) for row in rows})
        by_mode = {int(row['mode']): row for row in rows}
        self.assertIn('normal gameplay', by_mode[0]['behavior'])
        self.assertIn('+370 fixed8 X', by_mode[5]['behavior'])
        self.assertIn('counter > 350', by_mode[5]['behavior'])
        self.assertEqual('6', str(by_mode[5]['next_mode']))
        self.assertIn('-256 fixed8 Y', by_mode[6]['behavior'])
        self.assertIn('Y > 780', by_mode[6]['behavior'])
        self.assertEqual('0', str(by_mode[6]['next_mode']))
        for row in rows:
            self.assertEqual('0x080081F2|0x08008806', row['mode_global_literal_refs'])

    def test_generated_controller_mode_csv_matches_extractor(self):
        csv_path = ROOT / 'data/player_controller_modes.csv'
        self.assertTrue(csv_path.exists())
        with csv_path.open(newline='', encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual({'0', '5', '6'}, {row['mode'] for row in rows})

if __name__ == '__main__':
    unittest.main()
