#!/usr/bin/env python3
import csv
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))


def load_semantics_module():
    path = ROOT / 'tools' / 'extract_extended_semantics.py'
    spec = importlib.util.spec_from_file_location('graveblood_extended_semantics', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NormalDialogueMinus5ReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_semantics_module()
        cls.rom = ROM.read_bytes()

    def test_extractor_closes_normal_minus5_reachability(self):
        self.assertTrue(
            hasattr(self.mod, 'extract_normal_dialogue_minus5_reachability'),
            'Step 12 requires a ROM-backed normal -5 reachability extractor',
        )
        row = self.mod.extract_normal_dialogue_minus5_reachability(self.rom)
        self.assertEqual('6', str(row['sole_minus5_script']))
        self.assertEqual('4', str(row['sole_minus5_step']))
        self.assertEqual('6', str(row['sole_minus5_argument']))
        self.assertEqual('0,1,2,3', row['reachable_state2_dialogue_scripts'])
        self.assertEqual('no', row['normal_minus5_reachable_from_canonical_state2'])
        self.assertEqual('4', str(row['state4_progress_index_for_script6']))
        self.assertEqual('0x080037F6', row['state4_minus5_override'])

    def test_generic_target_is_argument_selected_obj_vram_bank_loader(self):
        row = self.mod.extract_normal_dialogue_minus5_reachability(self.rom)
        self.assertEqual('0x08005720', row['latent_generic_target'])
        self.assertEqual('0x086493F0', row['graphics_source_base'])
        self.assertEqual('0x1800', row['graphics_bank_stride'])
        self.assertEqual('0x06010000', row['copy0_destination'])
        self.assertEqual('0x1200', row['copy0_size'])
        self.assertEqual('0x1400', row['copy1_source_offset'])
        self.assertEqual('0x06011400', row['copy1_destination'])
        self.assertEqual('0x0200', row['copy1_size'])

    def test_context_semantics_call_it_a_dormant_obj_bank_load(self):
        keyed = {(r['context'], r['opcode']): r for r in self.mod.extract_dialogue_context_semantics()}
        row = keyed[('normal', -5)]
        self.assertEqual('latent OBJ graphics-bank load', row['semantic'])
        self.assertIn('dormant', row['proven_behavior'])
        self.assertIn('0x1800', row['proven_behavior'])

    def test_checked_in_csv_matches_extractor(self):
        csv_path = ROOT / 'data' / 'normal_dialogue_minus5_reachability.csv'
        self.assertTrue(csv_path.exists(), 'Step 12 evidence CSV must be checked in')
        with csv_path.open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(1, len(rows))
        expected = {k: str(v) for k, v in self.mod.extract_normal_dialogue_minus5_reachability(self.rom).items()}
        self.assertEqual(expected, rows[0])


if __name__ == '__main__':
    unittest.main()
