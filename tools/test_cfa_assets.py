#!/usr/bin/env python3
import importlib.util
import os
import tempfile
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / 'tools' / 'generate_cfa_assets.py'


class CfaAssetTests(unittest.TestCase):
    def _module(self):
        self.assertTrue(GENERATOR.is_file(), 'tools/generate_cfa_assets.py')
        spec = importlib.util.spec_from_file_location('generate_cfa_assets', GENERATOR)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_recovered_level_metadata_and_supported_portals(self):
        g = self._module()
        specs = g.build_level_specs(ROOT)
        self.assertEqual((29, 24), (specs[7].width, specs[7].height))
        self.assertEqual((37, 43), (specs[8].width, specs[8].height))
        self.assertEqual((147, 125), specs[7].spawn)
        self.assertEqual((123, 115), specs[8].spawn)
        self.assertEqual([8, 8, 6], [p.target_level for p in specs[7].portals])
        self.assertEqual([9, 9, 7, 7], [p.target_level for p in specs[8].portals])

    def test_tilesets_fit_one_8bpp_character_block(self):
        g = self._module()
        for level in (7, 8):
            image = g.load_world_image(ROOT, level)
            packed = g.pack_background(image)
            self.assertLessEqual(len(packed.tiles), 256)
            self.assertLessEqual(len(packed.palette), 256)

    def test_player_animation_is_16_frames_and_fits_one_4bpp_palette(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        packed = g.pack_player_animation(rom)
        self.assertEqual((16, 32), packed.size)
        self.assertEqual(16, packed.frame_count)
        self.assertLessEqual(len(packed.palette), 16)
        self.assertEqual(16 * 256, len(packed.data))

    def test_player_animation_pack_has_no_deprecation_warnings(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        with warnings.catch_warnings():
            warnings.simplefilter('error', DeprecationWarning)
            g.pack_player_animation(rom)

    def test_player_animation_checked_in_asset_declares_all_frames(self):
        assets_h = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        player_c = (ROOT / 'reconstruction/data/player_sprite.c').read_text(encoding='utf-8')
        self.assertIn('GB_PLAYER_FRAME_COUNT = 16', assets_h)
        self.assertIn('gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128]', assets_h)
        self.assertIn('gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128]', player_c)

    def test_collision_assets_preserve_original_u16_cells(self):
        assets_h = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        generator = GENERATOR.read_text(encoding='utf-8')
        level7 = (ROOT / 'reconstruction/data/level07_assets.c').read_text(encoding='utf-8')
        self.assertIn('const u16* collision;', assets_h)
        self.assertIn('const u16 {name}_collision', generator)
        self.assertIn('const u16 gb_level07_collision[696]', level7)

    def test_generator_is_deterministic_against_checked_in_outputs(self):
        g = self._module()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            g.generate_all(ROOT, out)
            expected_root = ROOT / 'reconstruction'
            generated = sorted(p.relative_to(out) for p in out.rglob('*') if p.is_file())
            self.assertTrue(generated)
            for rel in generated:
                expected = expected_root / rel
                self.assertTrue(expected.is_file(), rel)
                self.assertEqual(expected.read_bytes(), (out / rel).read_bytes(), rel)


if __name__ == '__main__':
    unittest.main()
