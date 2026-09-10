#!/usr/bin/env python3
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / 'tools' / 'extract_foreground.py'

class ForegroundExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXTRACTOR.is_file():
            raise AssertionError('tools/extract_foreground.py')
        spec = importlib.util.spec_from_file_location('extract_foreground', EXTRACTOR)
        cls.mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.mod)
        cls.rom_path = Path(os.environ['GRAVEBLOOD_ROM'])
        cls.data = cls.rom_path.read_bytes()

    def test_grass_and_fgtile_visual_contracts(self):
        grass = self.mod.extract_grass_semantics(self.data)
        self.assertEqual('0x08018AD8', grass['vtable'])
        self.assertEqual('0x08002480', grass['update'])
        self.assertEqual('no_op', grass['update_behavior'])
        self.assertEqual('0x08002684', grass['draw'])
        self.assertEqual(0x48, grass['logical_tile'])
        self.assertEqual('16x16', grass['shape'])
        self.assertEqual('turn_bit0', grass['hflip_source'])
        self.assertEqual('legsColor_eq_1', grass['hide_condition'])
        self.assertEqual('1_if_actor_below_player_else_2', grass['priority'])

        fgtile = self.mod.extract_fgtile_visual_semantics(self.data)
        self.assertEqual('0x08018E4C', fgtile['vtable'])
        self.assertEqual('0x08003AE8', fgtile['draw'])
        self.assertEqual('no_op', fgtile['draw_behavior'])

    def test_leaves_emitter_and_particle_contract(self):
        leaves = self.mod.extract_leaves_semantics(self.data)
        self.assertEqual('0x08005EE0', leaves['factory'])
        self.assertEqual('0x08019660', leaves['vtable'])
        self.assertEqual('0x08005EDC', leaves['draw'])
        self.assertEqual('no_op', leaves['draw_behavior'])
        self.assertEqual('0x08005F80', leaves['update'])
        self.assertEqual(12, leaves['initial_cooldown'])
        self.assertEqual(23, leaves['reset_cooldown'])
        self.assertEqual(2000, leaves['camera_x_threshold'])
        self.assertEqual([350, 250, 170, 0, 340, 290], leaves['x_offsets'])
        self.assertEqual([40, 60, 80, 30, 20, 50], leaves['y_offsets'])
        self.assertEqual('(camera_x+260+x_offset)<<8', leaves['spawn_x_equation'])
        self.assertEqual('(camera_y-80+y_offset)<<8', leaves['spawn_y_equation'])
        self.assertEqual('0x0800B2BC', leaves['particle_constructor'])

        particle = self.mod.extract_leaf_particle_semantics(self.data)
        self.assertEqual('0x08A8C1C0', particle['vtable'])
        self.assertEqual('0x0800AB60', particle['update'])
        self.assertEqual('0x0800AC1C', particle['draw'])
        self.assertEqual(-150, particle['velocity_x_fixed8'])
        self.assertEqual(150, particle['velocity_y_fixed8'])
        self.assertEqual([0x4C, 0x4D, 0x5C, 0x5D], particle['frame_tiles'])
        self.assertEqual(10, particle['initial_frame_countdown'])
        self.assertEqual('8x8', particle['shape'])
        self.assertEqual(0, particle['priority'])
        self.assertEqual('x<camera_x-30_or_y>camera_y+180', particle['cull_condition'])

    def test_level_usage_proves_only_level9_can_cross_emitter_threshold(self):
        rows = self.mod.extract_leaves_level_usage(ROOT)
        by_level = {row['level']: row for row in rows}
        self.assertEqual([0, 6, 9, 10], sorted(by_level))
        self.assertEqual(1, by_level[9]['leaves_count'])
        self.assertEqual(6016, by_level[9]['max_camera_x'])
        self.assertTrue(by_level[9]['can_cross_camera_x_2000'])
        self.assertFalse(by_level[0]['can_cross_camera_x_2000'])
        self.assertFalse(by_level[6]['can_cross_camera_x_2000'])
        self.assertFalse(by_level[10]['can_cross_camera_x_2000'])

    def test_structure_symbol_map_names_foreground_methods_separately(self):
        sym = (ROOT / 'data/graveblood_001152.sym').read_text(encoding='utf-8')
        for line in (
            '08002684 Grass_draw',
            '08005EE0 Leaves_factory',
            '08005F80 Leaves_update',
            '0800AB60 LeafParticle_update',
            '0800AC1C LeafParticle_draw',
            '0800B2BC LeafParticle_constructor',
        ):
            self.assertIn(line, sym)

    def test_generator_writes_foreground_evidence_and_disassembly(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self.mod.generate(ROOT, out, self.rom_path)
            for rel in (
                'data/foreground_actor_semantics.csv',
                'data/leaves_emitter_semantics.csv',
                'data/leaves_level_usage.csv',
                'disasm/grass_draw_08002684.txt',
                'disasm/leaves_update_08005F80.txt',
                'disasm/leaf_particle_update_0800AB60.txt',
                'disasm/leaf_particle_draw_0800AC1C.txt',
                'disasm/leaf_particle_constructor_0800B2BC.txt',
            ):
                self.assertTrue((out / rel).is_file(), rel)

if __name__ == '__main__':
    unittest.main()
