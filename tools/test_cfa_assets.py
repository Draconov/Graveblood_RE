#!/usr/bin/env python3
import importlib.util
import os
import tempfile
import sys
import unittest
import warnings
from pathlib import Path

from PIL import Image, ImageChops

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

    def test_generator_exposes_all_levels_and_all_graphics_variants(self):
        g = self._module()
        specs = g.build_level_specs(ROOT)
        self.assertEqual(list(range(11)), sorted(specs))
        self.assertEqual((782, 128), (specs[9].width, specs[9].height))

        variants = g.build_graphics_variants(ROOT)
        self.assertEqual(13, len(variants))
        self.assertEqual([0, 1, 2], sorted(v for (level, v) in variants if level == 0))
        for level in range(1, 11):
            self.assertIn((level, 0), variants)

    def test_generator_emits_all_variant_units_and_preserves_all_physical_portals(self):
        g = self._module()
        specs = g.build_level_specs(ROOT)
        self.assertEqual(38, sum(len(spec.portals) for spec in specs.values()))
        self.assertIn(524, [p.target_level for p in specs[9].portals])

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            g.generate_all(ROOT, out, Path(os.environ['GRAVEBLOOD_ROM']))
            assets = sorted((out / 'data').glob('level*_assets.c'))
            self.assertEqual(13, len(assets))
            names = {p.name for p in assets}
            self.assertIn('level00_assets.c', names)
            self.assertIn('level00_v1_assets.c', names)
            self.assertIn('level00_v2_assets.c', names)
            self.assertIn('level10_assets.c', names)
            self.assertTrue((out / 'data' / 'level_registry.c').is_file())

    def test_all_normal_physical_portal_targets_have_runtime_levels(self):
        g = self._module()
        specs = g.build_level_specs(ROOT)
        targets = [p.target_level for spec in specs.values() for p in spec.portals]
        normal = [target for target in targets if 0 <= target <= 10]
        special = [target for target in targets if target < 0 or target > 10]
        self.assertEqual(37, len(normal))
        self.assertTrue(all(target in specs for target in normal))
        self.assertEqual([524], special)

    def test_actor_runtime_data_preserves_canonical_population_and_routes(self):
        g = self._module()
        data = g.build_actor_runtime_data(ROOT)
        self.assertEqual(241, len(data.physical))
        self.assertEqual(290, sum(len(data.level_indices[level]) for level in range(11)))
        self.assertEqual(16, len(data.story))
        self.assertEqual(5, len(data.routes))
        self.assertTrue(all(len(route) == 6 for route in data.routes))
        self.assertEqual(32, len(data.visuals))

        combined = []
        for level in range(11):
            physical = len(data.level_indices[level])
            story = sum(1 for item in data.story if item.level == level)
            combined.append(physical + story)
            rom_orders = [data.physical[index].rom_order for index in data.level_indices[level]]
            self.assertEqual(sorted(rom_orders), rom_orders, f'level {level} actor order')
        self.assertEqual(65, max(combined))

        # Shared Level 0/6 records must reference the same immutable descriptors.
        shared = set(data.level_indices[0]) & set(data.level_indices[6])
        self.assertTrue(shared)
        self.assertTrue(all(data.physical[index].actor_class != g.ACTOR_CLASS_PLAYER for index in shared))

    def test_generator_emits_actor_data_routes_and_exact_npc_frame_bank(self):
        g = self._module()
        rom_path = Path(os.environ['GRAVEBLOOD_ROM'])
        data = g.build_actor_runtime_data(ROOT)
        packed = g.pack_actor_sprite_bank(rom_path.read_bytes(), data.visuals)
        self.assertEqual(256, len(packed.palette))
        self.assertEqual(32, packed.frame_count)
        self.assertEqual(32 * 512, len(packed.data))
        self.assertLess(max(packed.data), 240, 'palette bank 15 must remain free for Player 4bpp colors')

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            g.generate_all(ROOT, out, rom_path)
            self.assertTrue((out / 'data' / 'actor_data.c').is_file())
            self.assertTrue((out / 'data' / 'actor_routes.c').is_file())
            self.assertTrue((out / 'data' / 'actor_sprite_data.c').is_file())
            header = (out / 'include' / 'graveblood' / 'assets.h').read_text(encoding='utf-8')
            self.assertIn('GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT = 241', header)
            self.assertIn('GB_ACTOR_STORY_DESCRIPTOR_COUNT = 16', header)
            self.assertIn('GB_ACTOR_VISUAL_COUNT = 32', header)
            self.assertIn('GB_ACTOR_ROUTE_COUNT = 5', header)

    def test_runtime_background_asset_model_uses_exact_streamed_sources(self):
        g = self._module()
        self.assertTrue(hasattr(g, 'load_runtime_background'))
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        specs = g.build_level_specs(ROOT)
        for level, expected_cells in ((7, 696), (8, 1591)):
            runtime = g.load_runtime_background(ROOT, rom, specs[level])
            self.assertEqual(256, len(runtime.palette))
            self.assertEqual(0xD800, len(runtime.tile_bytes))
            self.assertEqual(expected_cells, len(runtime.layer_a))
            self.assertEqual(expected_cells, len(runtime.layer_b))
            self.assertEqual(2048, len(runtime.fixed_map))
            self.assertEqual(634, len(runtime.translation))

    def test_checked_in_level_assets_use_streamed_model_and_16bit_dimensions(self):
        assets_h = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        self.assertIn('u16 world_width_tiles;', assets_h)
        self.assertIn('u16 world_height_tiles;', assets_h)
        self.assertIn('const u16* bg_palette;', assets_h)
        self.assertIn('const u16* bg_tiles;', assets_h)
        self.assertIn('u16 bg_tile_halfwords;', assets_h)
        self.assertIn('const u16* translation;', assets_h)
        self.assertIn('u16 translation_count;', assets_h)
        self.assertIn('const u16* layer_a;', assets_h)
        self.assertIn('const u16* layer_b;', assets_h)
        self.assertIn('const u16* fixed_map;', assets_h)
        self.assertNotIn('const u16* map;', assets_h)

    def test_runtime_streamed_sources_render_pixel_identically_to_all_reference_worlds(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        specs = g.build_level_specs(ROOT)
        variants = g.build_graphics_variants(ROOT)

        def rgb555(value):
            return (
                (value & 0x1F) * 255 // 31,
                ((value >> 5) & 0x1F) * 255 // 31,
                ((value >> 10) & 0x1F) * 255 // 31,
            )

        for level, variant in sorted(variants):
            spec = specs[level]
            runtime = g.load_runtime_background(ROOT, rom, spec, variant)
            palette = [rgb555(value) for value in runtime.palette]

            def layer_image(source):
                image = Image.new('RGBA', (spec.width * 8, spec.height * 8), (0, 0, 0, 0))
                for cell, source_id in enumerate(source):
                    entry = runtime.translation[source_id]
                    tile_index = entry & 0x03FF
                    tile_bytes = runtime.tile_bytes[tile_index * 64:(tile_index + 1) * 64]
                    tile = Image.new('RGBA', (8, 8))
                    pixels = []
                    for palette_index in tile_bytes:
                        rgb = palette[palette_index]
                        pixels.append((*rgb, 0 if palette_index == 0 else 255))
                    tile.putdata(pixels)
                    if entry & 0x0400:
                        tile = tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    if entry & 0x0800:
                        tile = tile.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    image.alpha_composite(tile, ((cell % spec.width) * 8, (cell // spec.width) * 8))
                return image

            layer_a = layer_image(runtime.layer_a)
            layer_b = layer_image(runtime.layer_b)
            rendered = Image.new('RGBA', layer_a.size, palette[0] + (255,))
            rendered.alpha_composite(layer_b)
            rendered.alpha_composite(layer_a)
            expected = Image.open(
                ROOT / 'renders' / 'maps' / f'level{level:02d}_v{variant}_world.png'
            ).convert('RGBA')
            diff = ImageChops.difference(rendered, expected)
            self.assertIsNone(diff.getbbox(), f'level {level} variant {variant} streamed world differs')


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
