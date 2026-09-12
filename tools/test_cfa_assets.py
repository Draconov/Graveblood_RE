#!/usr/bin/env python3
import importlib.util
import hashlib
import struct
import os
import csv
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
        self.assertEqual([1, 0, 1, 1, 0, 0, 1, 0, 0, 1, 1],
                         [specs[level].player_idle_selector for level in range(11)])
        self.assertEqual([8, 8, 6], [p.target_level for p in specs[7].portals])
        self.assertEqual([9, 9, 7, 7], [p.target_level for p in specs[8].portals])
        # Fgtile portal geometry passes through the same atoi-style property parser
        # as actor descriptors: decimal source strings truncate before storage.
        self.assertEqual((75, 281), (specs[8].portals[0].x, specs[8].portals[0].y))
        self.assertTrue(any((p.x, p.y) == (511, 408) for p in specs[0].portals))

    def test_actor_numeric_parser_matches_rom_atoi_truncation(self):
        g = self._module()
        self.assertEqual(1423, g._actor_number({'x': '1423.667'}, 'x'))
        self.assertEqual(10, g._actor_number({'x': '10.999'}, 'x'))
        self.assertEqual(-3, g._actor_number({'x': '-3.9'}, 'x'))

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

    def test_generator_emits_all_variant_units_and_only_code_proven_scene_portals(self):
        g = self._module()
        specs = g.build_level_specs(ROOT)
        self.assertEqual(33, sum(len(spec.portals) for spec in specs.values()))
        self.assertNotIn(524, [p.target_level for p in specs[9].portals])

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
        self.assertEqual(33, len(normal))
        self.assertTrue(all(target in specs for target in normal))
        self.assertEqual([], special)

    def test_actor_runtime_data_preserves_canonical_population_and_routes(self):
        g = self._module()
        data = g.build_actor_runtime_data(ROOT)
        self.assertEqual(241, len(data.physical))
        self.assertEqual(290, sum(len(data.level_indices[level]) for level in range(11)))
        self.assertEqual(16, len(data.story))
        self.assertEqual(5, len(data.routes))
        self.assertTrue(all(len(route) == 6 for route in data.routes))
        self.assertEqual(34, len(data.visuals))
        self.assertIn((200, 0), data.visuals)
        self.assertIn((208, 0), data.visuals)
        self.assertIn((216, 0), data.visuals)

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
        # Missing setglobal properties retain the ROM parser/constructor default 1.
        # The 16 standalone story overlays explicitly serialize setglobal=0.
        self.assertTrue(all(item.setglobal == 1 for item in data.physical))
        self.assertTrue(all(item.descriptor.setglobal == 0 for item in data.story))

    def test_generator_emits_actor_data_routes_and_exact_npc_frame_bank(self):
        g = self._module()
        rom_path = Path(os.environ['GRAVEBLOOD_ROM'])
        data = g.build_actor_runtime_data(ROOT)
        packed = g.pack_actor_sprite_bank(rom_path.read_bytes(), data.visuals)
        self.assertEqual(256, len(packed.palette))
        self.assertEqual(34 * 8, packed.frame_count)
        self.assertEqual(34 * 8 * 512, len(packed.data))
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
            self.assertIn('GB_ACTOR_VISUAL_COUNT = 34', header)
            self.assertIn('GB_ACTOR_MAX_FRAMES = 8', header)
            self.assertIn('GB_ACTOR_ROUTE_COUNT = 5', header)

    def test_generator_packs_level9_level10_parked_bicycle_from_initial_obj_bank(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        self.assertTrue(hasattr(g, 'pack_level_static_obj_bank'))
        packed = g.pack_level_static_obj_bank(rom)
        self.assertEqual(4, packed.frame_count)
        self.assertEqual(4 * 16 * 16, len(packed.data))

        # Player_draw submits the same four 16x16 initial-OBJ pieces as the
        # parked 32x32 bicycle composite in Levels 9 and 10: 0x17C/0x17E over 0x19C/0x19E.
        source_base = g.OBJ_TILES_SOURCE - g.ROM_BASE
        expected = bytearray()
        for tile_arg in (0x17C, 0x17E, 0x19C, 0x19E):
            base = tile_arg & 0x1FF
            for logical in (base, base + 1, base + 16, base + 17):
                start = source_base + logical * 64
                expected.extend(rom[start:start + 64])
        self.assertEqual(bytes(expected), packed.data)

    def test_generator_packs_exact_grass_and_leaf_particle_tiles(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        foreground = g.pack_foreground_sprite_bank(rom)
        source_base = g.OBJ_TILES_SOURCE - g.ROM_BASE
        expected_grass = b''.join(
            rom[source_base + tile * 64:source_base + (tile + 1) * 64]
            for tile in (0x48, 0x49, 0x58, 0x59)
        )
        expected_leaves = b''.join(
            rom[source_base + tile * 64:source_base + (tile + 1) * 64]
            for tile in (0x4C, 0x4D, 0x5C, 0x5D)
        )
        self.assertEqual(expected_grass, foreground.grass)
        self.assertEqual(expected_leaves, foreground.leaf_frames)
        self.assertEqual(256, len(foreground.grass))
        self.assertEqual(256, len(foreground.leaf_frames))

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            g.generate_all(ROOT, out, Path(os.environ['GRAVEBLOOD_ROM']))
            ctext = (out / 'data/actor_sprite_data.c').read_text(encoding='utf-8')
            htext = (out / 'include/graveblood/assets.h').read_text(encoding='utf-8')
            self.assertIn('gb_grass_obj_tiles', ctext)
            self.assertIn('gb_leaf_obj_frames', ctext)
            self.assertIn('GB_GRASS_OBJ_HALFWORDS = 128', htext)
            self.assertIn('GB_LEAF_FRAME_COUNT = 4', htext)
            self.assertIn('GB_LEAF_FRAME_HALFWORDS = 32', htext)

    def test_story_runtime_data_and_canonical_font_contract(self):
        g = self._module()
        story = g.build_story_runtime_data(ROOT)
        self.assertEqual(7, len(story.dialogue_scripts))
        self.assertEqual(58, sum(len(script) for script in story.dialogue_scripts))
        self.assertEqual(6, len(story.messages))
        self.assertEqual(('Stas', 'Julia'), tuple(profile.name for profile in story.social_profiles))
        self.assertEqual(18, sum(len(profile.topic_ratings) for profile in story.social_profiles))
        self.assertEqual(20, len(story.social_actions))
        self.assertEqual(216, len(story.social_responses))

        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        font = g.extract_canonical_font(rom)
        self.assertEqual(127, len(font.glyphs))
        self.assertEqual(127, font.bitmap_base_index)
        self.assertTrue(all(font.glyphs[i].control for i in range(1, 32)))
        self.assertEqual(4, font.glyphs[32].pixel_width)
        self.assertEqual(6, font.glyphs[ord('A')].pixel_width)
        self.assertEqual(4, font.glyphs[ord('i')].pixel_width)
        self.assertEqual((0, 0, 0, 0, 0, 0, 0, 0), font.glyphs[32].rows)
        self.assertNotEqual((0, 0, 0, 0, 0, 0, 0, 0), font.glyphs[ord('A')].rows)

    def test_generator_emits_story_font_and_monster_runtime_assets(self):
        g = self._module()
        rom_path = Path(os.environ['GRAVEBLOOD_ROM'])
        monster = g.pack_monster_sprite_bank(rom_path.read_bytes())
        self.assertEqual(5, monster.frame_count)
        self.assertEqual(5 * 256, len(monster.data))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            g.generate_all(ROOT, out, rom_path)
            for rel in ('data/story_data.c', 'data/font_data.c', 'data/monster_sprite.c'):
                self.assertTrue((out / rel).is_file(), rel)
            header = (out / 'include/graveblood/assets.h').read_text(encoding='utf-8')
            self.assertIn('GB_DIALOGUE_SCRIPT_COUNT = 7', header)
            self.assertIn('GB_DIALOGUE_RECORD_COUNT = 58', header)
            self.assertIn('GB_MESSAGE_RECORD_COUNT = 6', header)
            self.assertIn('GB_SOCIAL_PROFILE_COUNT = 2', header)
            self.assertIn('GB_SOCIAL_RESPONSE_COUNT = 216', header)
            self.assertIn('GB_MONSTER_SPRITE_COUNT = 5', header)

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

    def test_level2_generated_translation_preserves_unchecked_rom_overrun_entries(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        specs = g.build_level_specs(ROOT)
        runtime = g.load_runtime_background(ROOT, rom, specs[2])

        # 0x0800A330 performs translation[source_id] with no bounds check.
        # Level 2 references IDs through 3216, so the generated clean-room
        # table must retain the adjacent ROM halfwords instead of truncating
        # at the nominal translation/palette boundary.
        self.assertEqual(len(runtime.translation), 3217)
        self.assertEqual(runtime.translation[2260], 0x7F9D)
        self.assertEqual(max(runtime.layer_a), 3216)

    def test_every_level_variant_has_87_world_safe_bg0_ui_tiles(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        specs = g.build_level_specs(ROOT)
        variants = g.build_graphics_variants(ROOT)
        for level, variant in sorted(variants):
            runtime = g.load_runtime_background(ROOT, rom, specs[level], variant)
            ui_tiles = g.select_bg0_ui_tiles(runtime, 87)
            self.assertEqual(87, len(ui_tiles), (level, variant))
            self.assertEqual(87, len(set(ui_tiles)), (level, variant))
            self.assertTrue(all(0 <= tile < 864 for tile in ui_tiles), (level, variant))

            used_sources = set(runtime.layer_a) | set(runtime.layer_b) | set(runtime.fixed_map)
            used_tiles = {
                runtime.translation[source] & 0x03FF
                for source in used_sources
                if source < len(runtime.translation)
            }
            self.assertTrue(set(ui_tiles).isdisjoint(used_tiles), (level, variant))

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            g.generate_all(ROOT, out, Path(os.environ['GRAVEBLOOD_ROM']))
            header = (out / 'include' / 'graveblood' / 'assets.h').read_text(encoding='utf-8')
            self.assertIn('GB_BG0_UI_TILE_COUNT = 87', header)
            self.assertIn('const u16* bg0_ui_tiles;', header)
            sample = (out / 'data' / 'level00_assets.c').read_text(encoding='utf-8')
            self.assertIn('gb_level00_bg0_ui_tiles[GB_BG0_UI_TILE_COUNT]', sample)
            self.assertIn('.bg0_ui_tiles = gb_level00_bg0_ui_tiles', sample)

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

    def test_player_animation_is_24_frames_and_fits_one_4bpp_palette(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        packed = g.pack_player_animation(rom)
        self.assertEqual((16, 32), packed.size)
        self.assertEqual(24, packed.frame_count)
        self.assertLessEqual(len(packed.palette), 16)
        self.assertEqual(24 * 256, len(packed.data))

    def test_player_animation_pack_has_no_deprecation_warnings(self):
        g = self._module()
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        with warnings.catch_warnings():
            warnings.simplefilter('error', DeprecationWarning)
            g.pack_player_animation(rom)

    def test_player_animation_checked_in_asset_declares_all_frames(self):
        assets_h = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        player_c = (ROOT / 'reconstruction/data/player_sprite.c').read_text(encoding='utf-8')
        self.assertIn('GB_PLAYER_FRAME_COUNT = 24', assets_h)
        self.assertIn('gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128]', assets_h)
        self.assertIn('gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128]', player_c)

    def test_collision_assets_preserve_original_u16_cells(self):
        assets_h = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        generator = GENERATOR.read_text(encoding='utf-8')
        level7 = (ROOT / 'reconstruction/data/level07_assets.c').read_text(encoding='utf-8')
        self.assertIn('const u16* collision;', assets_h)
        self.assertIn('const u16 {name}_collision', generator)
        self.assertIn('const u16 gb_level07_collision[696]', level7)

    def test_canonical_audio_table_payloads_and_final_sketch_call(self):
        rom_path = Path(os.environ['GRAVEBLOOD_ROM'])
        rom = rom_path.read_bytes()
        self.assertEqual(
            'e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b',
            hashlib.sha256(rom).hexdigest(),
        )
        expected = [
            (0x088F68C8, 0x18435C),
            (0x087FBE00, 0x0FAAC5),
            (0x08663E00, 0x198000),
            (0x08A82954, 0x0D6D),
            (0x08A83EF4, 0x0248),
            (0x08A8413C, 0x4482),
            (0x08A885C0, 0x3A67),
            (0x08A8222C, 0x0728),
            (0x08A82140, 0x00EC),
            (0x08A7E110, 0x3476),
            (0x08A7AC24, 0x34EC),
            (0x08A81588, 0x0BB6),
            (0x08A836C4, 0x082D),
            (0x0865669C, 0xD762),
        ]
        actual = [struct.unpack_from('<II', rom, 0x65662C + i * 8) for i in range(14)]
        self.assertEqual(expected, actual)

        extractor = ROOT / 'tools' / 'extract_audio.py'
        self.assertTrue(extractor.is_file(), extractor)
        audio_dir = ROOT / 'reconstruction' / 'data' / 'audio'
        for sound_id, (pointer, length) in enumerate(expected):
            pcm = audio_dir / f'sample_{sound_id:02d}.pcm'
            self.assertTrue(pcm.is_file(), pcm)
            start = pointer - 0x08000000
            self.assertGreaterEqual(start, 0)
            self.assertLessEqual(start + length, len(rom))
            self.assertEqual(rom[start:start + length], pcm.read_bytes(), pcm.name)

        self.assertTrue(all(length > 1_000_000 for _, length in expected[:3]))
        self.assertTrue(all(length < 100_000 for _, length in expected[3:]))
        call_sites = (ROOT / 'data' / 'audio_call_sites.csv').read_text(encoding='utf-8')
        self.assertIn('0x08003802', call_sites)
        self.assertIn(',13,', call_sites)
        self.assertIn('final-sketch', call_sites.lower())
        self.assertTrue(call_sites.startswith('call_address,target,caller,sound_id,play_mode,volume,'))
        self.assertIn('0x08002E22,0x08001B74,npc_state2_fresh_a_activation,3,one-shot,80', call_sites)
        self.assertIn('first state-2 text page when 0x0300062C latch is zero,high', call_sites)
        self.assertIn('0x08003078,0x08001B74,npc_state4_fresh_a_activation,3,one-shot,80', call_sites)
        self.assertIn('first state-4 text page when 0x0300062C latch is zero,high', call_sites)
        self.assertIn('0x0800426C,0x08001B74,Fgtile_update,5,one-shot,80,generic scene portal activation,high', call_sites)
        self.assertIn('0x08004B2A,0x08001B74,TitleScene_update,6,one-shot,80,fresh START title transition,high', call_sites)
        self.assertIn('0x080089F8,0x08001B74,Player_update,4,one-shot,80,FRIENDS successful UP navigation,high', call_sites)
        self.assertIn('0x0800909C,0x08001B74,Player_update,4,one-shot,80,FRIENDS successful DOWN navigation,high', call_sites)
        self.assertIn('0x0800368E,0x08001B74,npc_state4_fresh_a_activation,7,one-shot,80,state4 dialogue opcode -2 terminal,high', call_sites)
        self.assertIn('0x08003748,0x08001B74,npc_state4_fresh_a_activation,7,one-shot,80,state4 dialogue opcode -1 terminal,high', call_sites)
        self.assertIn('0x0800389A,0x08001B74,state4_final_collection_handler,7,one-shot,80,state4 dialogue opcode -3 terminal,high', call_sites)
        self.assertIn('0x0800898E,0x08001B74,Player_update,11,one-shot,80,PDA menu tab previous (fresh L; MESSAGES/STATUS/FRIENDS/BACKPACK),high', call_sites)
        self.assertIn('0x0800904E,0x08001B74,Player_update,11,one-shot,80,PDA menu tab next (fresh R; MESSAGES/STATUS/FRIENDS/BACKPACK),high', call_sites)
        self.assertIn('0x080032AC,0x08001B74,npc_state4_fresh_a_activation,8,one-shot,80,subsequent state-2 text page while 0x0300062C latch is nonzero,high', call_sites)
        self.assertIn('0x08003668,0x08001B74,npc_state4_fresh_a_activation,8,one-shot,80,subsequent state-4 text page while 0x0300062C latch is nonzero,high', call_sites)
        self.assertIn('0x08003298,0x08001B74,npc_special_proximity_latch,9,one-shot,80,legsColor 0x70 NPC proximity latch activation,high', call_sites)
        self.assertIn('0x08009AA2,0x08001B74,Player_update,12,one-shot,80,FRIENDS DOWN-at-bottom boundary feedback,high', call_sites)
        self.assertIn('0x08009B58,0x08001B74,Player_update,12,one-shot,80,FRIENDS UP-at-top boundary feedback,high', call_sites)
        self.assertIn('0x08009C16,0x08001B74,Player_update,10,one-shot,30,fresh R bicycle action while shared ride mode 0x030005F4 == 2,high', call_sites)
        self.assertIn('0x080032D2,0x08001B74,npc_state4_fresh_a_activation,7,one-shot,80,normal dialogue opcode -4 set story/progression stage,high', call_sites)
        self.assertIn('0x080033A2,0x08001B74,npc_state4_fresh_a_activation,7,one-shot,80,normal dialogue opcode -3 add auxiliary message stream,high', call_sites)
        self.assertIn('0x08003462,0x08001B74,npc_state4_fresh_a_activation,7,one-shot,80,normal dialogue opcode -2 set primary message stream,high', call_sites)
        self.assertIn('0x08003516,0x08001B74,npc_state4_fresh_a_activation,7,one-shot,80,normal dialogue opcode -1 set dialogue step,high', call_sites)
        self.assertIn('0x08003D5C,0x08001B74,Fgtile_update,5,one-shot,80,fresh-A generic Fgtile activation for turn != 4/5,high', call_sites)
        self.assertIn('0x080084DC,0x08001B74,Player_update,6,one-shot,80,fresh START PDA/menu open,high', call_sites)
        self.assertIn('0x080075D2,0x08001B74,pda_return_to_gameplay_transition_candidate,7,one-shot,80,PDA/menu return-to-gameplay transition; consumes 0x03000618 pending flag,high', call_sites)
        self.assertIn('0x08009904,0x08001B74,Player_update,4,one-shot,80,PDA MESSAGES cursor previous (fresh LEFT; cursor 0..3),high', call_sites)
        self.assertIn('0x0800999E,0x08001B74,Player_update,4,one-shot,80,PDA MESSAGES cursor next (fresh RIGHT; cursor 0..3),high', call_sites)
        self.assertIn('0x08009CCA,0x08001B74,Player_update,7,one-shot,80,interaction state-2 return/back (fresh B),high', call_sites)
        self.assertIn('0x0800B2A6,0x08001B74,latent_projectile_constructor,4,one-shot,80,latent projectile constructor; technical role recovered from update/draw (vtable 0x08A8C198),high', call_sites)
        self.assertIn('0x0800B37E,0x08001B74,hit_death_burst_constructor,3,one-shot,80,hit/death burst constructor; technical role recovered from update/draw (vtable 0x08A8C1E8),high', call_sites)

        pda_pages = (ROOT / 'data' / 'pda_menu_pages.csv').read_text(encoding='utf-8').splitlines()
        self.assertEqual('selector,page_name,renderer_branch,key_policy,evidence', pda_pages[0])
        self.assertEqual(['0,MESSAGES,0x08007642,L decrements only when selector > 0,0x080075F8 dispatches selector 0 to MESSAGES branch'], [pda_pages[1]])
        self.assertIn('1,STATUS,0x0800795C', pda_pages[2])
        self.assertIn('2,FRIENDS,0x0800777A', pda_pages[3])
        self.assertIn('3,BACKPACK,0x08007A10,R increments only when selector <= 2', pda_pages[4])

        known_globals = (ROOT / 'data' / 'known_globals.csv').read_text(encoding='utf-8')
        self.assertIn('0x03000614,pda_menu_page_selector', known_globals)

        loop_rows = [line for line in call_sites.splitlines() if ',0x08001BDC,' in line]
        self.assertEqual(3, len(loop_rows), loop_rows)
        self.assertEqual(
            ['0x08005A8A', '0x08008AA0', '0x08009428'],
            [row.split(',', 1)[0] for row in loop_rows],
        )
        self.assertTrue(all(',dynamic,2,144,' in row for row in loop_rows), loop_rows)
        self.assertFalse(any(',2,one-shot,' in row for row in call_sites.splitlines()))

        music_routes = (ROOT / 'data' / 'audio_music_routes.csv').read_text(encoding='utf-8')
        self.assertIn('sample 2 unreachable/orphaned in public demo', music_routes)
        self.assertIn(',2,high,', music_routes)
        self.assertIn('exhaustive full-ROM loop-player scan finds exactly three calls', music_routes)

    def test_effect_object_runtime_semantics_and_static_reachability(self):
        semantics_path = ROOT / 'data' / 'effect_object_semantics.csv'
        reachability_path = ROOT / 'data' / 'effect_object_reachability.csv'
        self.assertTrue(semantics_path.is_file(), semantics_path)
        self.assertTrue(reachability_path.is_file(), reachability_path)

        semantics = {
            row['effect_role']: row
            for row in csv.DictReader(semantics_path.read_text(encoding='utf-8').splitlines())
        }
        self.assertEqual({'latent_projectile', 'hit_death_burst'}, set(semantics))

        projectile = semantics['latent_projectile']
        self.assertEqual('0x0800B250', projectile['constructor'])
        self.assertEqual('0x08A8C198', projectile['vtable'])
        self.assertEqual('0x0800AEA8', projectile['update'])
        self.assertEqual('0x0800ABCC', projectile['draw'])
        self.assertEqual('4', projectile['sfx_id'])
        self.assertEqual('80', projectile['sfx_volume'])
        self.assertEqual('1', projectile['width_fixed8'])
        self.assertEqual('1', projectile['height_fixed8'])
        self.assertIn('position_init', projectile)
        self.assertEqual('x=input_x;y=input_y', projectile['position_init'])
        self.assertEqual('0x5000', projectile['initial_timer_or_budget'])
        self.assertEqual('0x126 active;0x124 terminal', projectile['draw_tiles'])
        self.assertEqual('1', projectile['obj_priority'])
        self.assertEqual('vtable+0x1C', projectile['hit_callback'])
        self.assertEqual('60', projectile['hit_argument'])
        self.assertIn('max(abs(vx),abs(vy))', projectile['update_contract'])
        self.assertIn('budget < -10', projectile['terminal_rule'])
        self.assertIn('object overlap removes immediately', projectile['terminal_rule'])

        burst = semantics['hit_death_burst']
        self.assertEqual('0x0800B31C', burst['constructor'])
        self.assertEqual('0x08A8C1E8', burst['vtable'])
        self.assertEqual('0x0800ABBC', burst['update'])
        self.assertEqual('0x0800AC88', burst['draw'])
        self.assertEqual('3', burst['sfx_id'])
        self.assertEqual('80', burst['sfx_volume'])
        self.assertEqual('0x2000', burst['width_fixed8'])
        self.assertEqual('0x2000', burst['height_fixed8'])
        self.assertEqual('x=input_center_x-0x1000;y=input_center_y+0x1000', burst['position_init'])
        self.assertEqual('-1', burst['initial_timer_or_budget'])
        self.assertEqual('0x127;0x128;0x12A;0x12C', burst['draw_tiles'])
        self.assertEqual('1', burst['obj_priority'])
        self.assertEqual('optional vtable+0x1C propagation', burst['hit_callback'])
        self.assertEqual('constructor arg6', burst['hit_argument'])
        self.assertIn('counter > 31', burst['terminal_rule'])
        self.assertIn('four 8-update phases', burst['update_contract'])

        reachability = {
            row['subject']: row
            for row in csv.DictReader(reachability_path.read_text(encoding='utf-8').splitlines())
        }
        projectile_reach = reachability['latent_projectile_constructor']
        self.assertEqual('none', projectile_reach['direct_bl_callers'])
        self.assertEqual('none', projectile_reach['literal_pointer_references'])
        self.assertEqual('no_static_root_in_public_demo', projectile_reach['status'])

        burst_reach = reachability['hit_death_burst_constructor']
        self.assertEqual('0x0800272A;0x080060FC', burst_reach['direct_bl_callers'])
        self.assertEqual('NPC_hit_callback;Player_hit_callback', burst_reach['roots'])
        self.assertEqual('arg6=0 at both direct call sites', burst_reach['propagation'])
        self.assertEqual('no_external_root_in_public_demo', burst_reach['status'])

        dispatch = reachability['vtable_slot_0x1C_dispatch']
        self.assertEqual('0x0800AF6A;0x0800B3C4', dispatch['direct_bl_callers'])
        self.assertIn('projectile hit', dispatch['evidence'])
        self.assertIn('burst optional propagation', dispatch['evidence'])

        known_functions_path = ROOT / 'data' / 'known_functions.csv'
        self.assertNotIn(b'\r\n', known_functions_path.read_bytes())
        known_functions = known_functions_path.read_text(encoding='utf-8')
        symbols = (ROOT / 'data' / 'graveblood_001152.sym').read_text(encoding='utf-8')
        call_sites = (ROOT / 'data' / 'audio_call_sites.csv').read_text(encoding='utf-8')
        self.assertIn('0x0800B250,latent_projectile_constructor,', known_functions)
        self.assertIn('0x0800B31C,hit_death_burst_constructor,', known_functions)
        self.assertIn('0800B250 latent_projectile_constructor', symbols)
        self.assertIn('0800B31C hit_death_burst_constructor', symbols)
        self.assertNotIn('effect_object_sfx4_constructor_candidate', known_functions)
        self.assertNotIn('effect_object_sfx3_constructor_candidate', known_functions)
        self.assertIn(',latent_projectile_constructor,4,one-shot,80,', call_sites)
        self.assertIn(',hit_death_burst_constructor,3,one-shot,80,', call_sites)

        for name in (
            'effect_object_sfx4_update_0800AEA8.txt',
            'effect_object_sfx4_draw_0800ABCC.txt',
            'effect_object_sfx3_update_0800ABBC.txt',
            'effect_object_sfx3_draw_0800AC88.txt',
            'effect_object_npc_hit_callback_080026E8.txt',
            'effect_object_player_hit_callback_080060C4.txt',
        ):
            self.assertTrue((ROOT / 'disasm' / name).is_file(), name)

    def test_all_one_shot_audio_calls_have_high_confidence_semantics(self):
        rows = list(csv.DictReader((ROOT / 'data' / 'audio_call_sites.csv').read_text(encoding='utf-8').splitlines()))
        one_shot = [row for row in rows if row['target'] == '0x08001B74']
        self.assertGreater(len(one_shot), 0)
        unresolved = [
            (row['call_address'], row['caller'], row['recovered_action'], row['confidence'])
            for row in one_shot
            if row['confidence'] != 'high' or 'unresolved' in row['recovered_action'].lower()
        ]
        self.assertEqual([], unresolved)

        closure_path = ROOT / 'data' / 'audio_one_shot_closure.csv'
        self.assertTrue(closure_path.is_file(), closure_path)
        closure = list(csv.DictReader(closure_path.read_text(encoding='utf-8').splitlines()))
        self.assertEqual(1, len(closure))
        self.assertEqual('30', closure[0]['one_shot_call_count'])
        self.assertEqual('30', closure[0]['high_confidence_count'])
        self.assertEqual('0', closure[0]['medium_confidence_count'])
        self.assertEqual('3;4;5;6;7;8;9;10;11;12;13', closure[0]['reachable_sound_ids'])
        self.assertEqual('yes', closure[0]['static_one_shot_call_graph_closed'])

        for name in (
            'audio_pda_return_080075C8.txt',
            'audio_pda_open_080084B0.txt',
            'audio_pda_messages_cursor_080098D0.txt',
            'audio_interaction_confirm_08009C80.txt',
            'audio_effect_sfx4_constructor_0800B250.txt',
            'audio_effect_sfx3_constructor_0800B31C.txt',
        ):
            self.assertTrue((ROOT / 'disasm' / name).is_file(), name)

        music_runtime = (ROOT / 'data' / 'audio_music_runtime.csv').read_text(encoding='utf-8')
        self.assertIn('loop_player_signature,"(sound_id, mode, volume)"', music_runtime)
        self.assertIn('one_shot_signature,"(sound_id, volume)"', music_runtime)
        self.assertIn('fade_table_runtime,0x030013C0', music_runtime)
        self.assertIn('fade_table_rom,0x08A8E370', music_runtime)
        self.assertIn('fade_table_words,75', music_runtime)
        self.assertIn('fade_terminal_quirk', music_runtime)
        self.assertIn('channel_record_bytes,28', music_runtime)
        self.assertIn('mode_1_end_behavior,deactivate at aligned sample end', music_runtime)
        self.assertIn('mode_2_end_behavior,loop by resetting sample cursor', music_runtime)
        self.assertIn('loop_reserved_flag,channel+0x18=1', music_runtime)
        self.assertIn('allocator_policy,first channel with mode=0 and reserved=0 among eight records', music_runtime)

        fade = (ROOT / 'data' / 'audio_music_fade.csv').read_text(encoding='utf-8').splitlines()
        self.assertEqual('index,value', fade[0])
        self.assertEqual('0,142', fade[1])
        self.assertEqual('70,2', fade[71])
        self.assertEqual('71,0', fade[72])
        self.assertEqual('74,0', fade[75])
        self.assertEqual(76, len(fade))

    def test_generator_emits_exact_safe_argument0_ending_payloads(self):
        g = self._module()
        rom_path = Path(os.environ['GRAVEBLOOD_ROM'])
        rom = rom_path.read_bytes()
        copy1, copy2 = g.extract_ending_argument0_payloads(rom)
        self.assertEqual(96000, len(copy1))
        self.assertEqual(16000, len(copy2))
        self.assertEqual('841d321b25a5e9c304146f4e6501745ef35b9d27e69e98560262c76a27381514', hashlib.sha256(copy1).hexdigest())
        self.assertEqual('17b8dc8ca34e26a634fb21d91d413dbda19bd58b9623e1848a4d1eb3157cb3d2', hashlib.sha256(copy2).hexdigest())

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            g.generate_all(ROOT, out, rom_path)
            first = out / 'data/ending/argument0_copy1.bin'
            second = out / 'data/ending/argument0_copy2.bin'
            asm = out / 'data/ending_effect.s'
            header = out / 'include/graveblood/assets.h'
            self.assertEqual(copy1, first.read_bytes())
            self.assertEqual(copy2, second.read_bytes())
            atext = asm.read_text(encoding='utf-8')
            self.assertIn('.global gb_ending_arg0_copy1', atext)
            self.assertIn('.incbin "../data/ending/argument0_copy1.bin"', atext)
            self.assertIn('.global gb_ending_arg0_copy2', atext)
            self.assertIn('.incbin "../data/ending/argument0_copy2.bin"', atext)
            htext = header.read_text(encoding='utf-8')
            self.assertIn('GB_ENDING_ARG0_COPY1_BYTES = 96000', htext)
            self.assertIn('GB_ENDING_ARG0_COPY2_BYTES = 16000', htext)
            self.assertIn('extern const u8 gb_ending_arg0_copy1[GB_ENDING_ARG0_COPY1_BYTES];', htext)
            self.assertIn('extern const u8 gb_ending_arg0_copy2[GB_ENDING_ARG0_COPY2_BYTES];', htext)

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


    def test_title_scene_canonical_asset_contract(self):
        extractor = ROOT / 'tools' / 'extract_title_scene.py'
        self.assertTrue(extractor.is_file(), 'tools/extract_title_scene.py')
        spec = importlib.util.spec_from_file_location('extract_title_scene', extractor)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        assets = module.extract_title_assets(rom)
        self.assertEqual(0x08019CC4, module.TITLE_BG_TILES_ADDR)
        self.assertEqual(0x0802B148, module.TITLE_TRANSLATION_ADDR)
        self.assertEqual(0x0802BB0C, module.TITLE_PALETTE_ADDR)
        self.assertEqual(0x08655814, module.TITLE_MAP_ADDR)
        self.assertEqual(0x0802BCCC, module.TITLE_BG_PALETTE_COUNT_ADDR)
        self.assertEqual(0x08310654, module.TITLE_OBJ_TILES_ADDR)
        self.assertEqual(0x8000, module.TITLE_OBJ_TILES_BYTES)
        self.assertEqual(0x08366E58, module.TITLE_OBJ_PALETTE_ADDR)
        self.assertEqual(0x08366F10, module.TITLE_OBJ_PALETTE_COUNT_ADDR)
        self.assertEqual(0x08652DB4, module.TITLE_OBJ_HIGH_PALETTE_ADDR)
        self.assertEqual(0xD800, len(assets.bg_tiles))
        self.assertEqual(223, len(assets.palette))
        self.assertEqual(0x8000, len(assets.obj_tiles))
        self.assertEqual(91, len(assets.obj_palette))
        self.assertEqual(32, len(assets.obj_high_palette))
        self.assertEqual(600, len(assets.map_entries))
        self.assertEqual(4, len(assets.anim_a))
        self.assertEqual(4, len(assets.anim_b))
        self.assertTrue(all(len(frame) == 0xC00 for frame in assets.anim_a))
        self.assertTrue(all(len(frame) == 0x600 for frame in assets.anim_b))
        self.assertEqual(b'PRESS START...', assets.prompt_text)
        self.assertEqual(14, len(assets.prompt_tiles))
        self.assertEqual(14, len(assets.blank_tiles))
        self.assertTrue(all(tile == assets.blank_tiles[0] for tile in assets.blank_tiles))

        raw0 = struct.unpack_from('<H', rom, module.TITLE_MAP_ADDR - module.ROM_BASE)[0]
        translated0 = struct.unpack_from('<H', rom, module.TITLE_TRANSLATION_ADDR - module.ROM_BASE + raw0 * 2)[0]
        self.assertEqual(translated0, assets.map_entries[0])
        first_prompt = struct.unpack_from(
            '<H', rom, module.TITLE_TRANSLATION_ADDR - module.ROM_BASE + (ord('P') + 32) * 2
        )[0]
        self.assertEqual(first_prompt, assets.prompt_tiles[0])
        self.assertEqual(
            struct.unpack_from('<H', rom, module.TITLE_TRANSLATION_ADDR - module.ROM_BASE + 4)[0],
            assets.underlay_tile,
        )

    def test_title_scene_extractor_emits_runtime_evidence(self):
        extractor = ROOT / 'tools' / 'extract_title_scene.py'
        self.assertTrue(extractor.is_file(), 'tools/extract_title_scene.py')
        spec = importlib.util.spec_from_file_location('extract_title_scene_emit', extractor)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            module.generate(ROOT, out, Path(os.environ['GRAVEBLOOD_ROM']))
            runtime = out / 'reconstruction/data/title_assets.c'
            semantics = out / 'data/title_scene_semantics.csv'
            self.assertTrue(runtime.is_file())
            self.assertTrue(semantics.is_file())
            ctext = runtime.read_text(encoding='utf-8')
            self.assertIn('gb_title_bg_tiles[0xD800 / 2]', ctext)
            self.assertIn('gb_title_bg_palette[GB_TITLE_BG_PALETTE_COUNT]', ctext)
            self.assertIn('gb_title_obj_tiles[GB_TITLE_OBJ_TILE_HALFWORDS]', ctext)
            self.assertIn('gb_title_obj_palette[GB_TITLE_OBJ_PALETTE_COUNT]', ctext)
            self.assertIn('gb_title_obj_high_palette[GB_TITLE_OBJ_HIGH_PALETTE_COUNT]', ctext)
            self.assertIn('const u16 gb_title_underlay_tile', ctext)
            self.assertIn('gb_title_map[GB_TITLE_MAP_CELLS]', ctext)
            self.assertIn('gb_title_anim_a[GB_TITLE_ANIMATION_STATES]', ctext)
            self.assertIn('gb_title_anim_b[GB_TITLE_ANIMATION_STATES]', ctext)
            self.assertIn('gb_title_prompt_tiles[GB_TITLE_PROMPT_LENGTH]', ctext)
            stext = semantics.read_text(encoding='utf-8')
            self.assertIn('display_control,0x1F00', stext)
            import csv
            rows = {row['fact']: row for row in csv.DictReader(stext.splitlines())}
            self.assertEqual('BG0=0x1B80 BG1=0x1C81 BG2=0x1D82 BG3=0x1E83', rows['bg_controls']['value'])
            self.assertIn('artwork_destination,BG1 screenblock28', stext)
            self.assertIn('prompt_destination,BG0 screenblock27', stext)
            self.assertIn('backing_destination,"BG2 screenblock29 + BG3 screenblock30, 64x32"', stext)
            self.assertIn('bg_palette_count,223', stext)
            self.assertIn('obj_palette_count,91', stext)
            self.assertIn('obj_high_palette_count,32', stext)
            self.assertIn('obj_mapping,2D', stext)
            self.assertIn('display_setup_blanking,forced blank set during setup and cleared before return', stext)
            self.assertIn('scroll_offsets,BG0HOFS/BG0VOFS..BG3HOFS/BG3VOFS=0', stext)
            self.assertEqual('attr0=0x02F0 attr1=0x01F0 attr2=0x0C00', rows['hidden_oam']['value'])
            self.assertIn('start_sfx,SFX6 volume80', stext)


    def test_pda_extractor_recovers_exact_page_maps_and_controls(self):
        extractor = ROOT / 'tools' / 'extract_pda.py'
        self.assertTrue(extractor.is_file(), 'tools/extract_pda.py')
        spec = importlib.util.spec_from_file_location('extract_pda', extractor)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        rom = Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        data = module.extract_pda(rom)
        self.assertEqual(('MESSAGES', 'STATUS', 'FRIENDS', 'BACKPACK'), data.page_names)
        self.assertEqual((0x086540A4, 0x08653BF4, 0x08653744, 0x08653294), data.raw_map_addresses)
        self.assertEqual(0x0864825C, data.translation_address)
        self.assertEqual((600, 600, 600, 600), tuple(len(page) for page in data.page_maps))
        hashes = tuple(hashlib.sha256(struct.pack('<600H', *page)).hexdigest() for page in data.page_maps)
        self.assertEqual((
            '8be8fb65d2fd54d1dc3a3ba6bd978bbd9075419048008a1922306685bf722aeb',
            'fd82be70bb76e5ccfbeb8deac04753647da5912c7188ba2d9d3b83403bfbfa24',
            '3673fd5e021a8456ef076f9e2519dfa306a1540e02631ffa5f16c4f2c7466170',
            '5d86cd4006daffb840d5cdcb0e72802ac37dc5e3854403cda3f2a5da6e3c7919',
        ), hashes)
        self.assertEqual(('Kate', 'Stas', 'IQ 54', 'Kiata', 'Alex', 'Evelina'), data.friends_names)
        self.assertEqual((2, 0, 1, 3, 4, 5), data.friends_profile_order)
        self.assertEqual(3, data.friends_visible_rows)
        self.assertEqual((0, 3), data.message_slot_bounds)
        self.assertFalse(data.ordinary_close_key_proven)
        self.assertEqual(145, len(data.text_tile_ids))
        chrome_tiles = {entry & 0x03FF for page in data.page_maps for entry in page}
        self.assertTrue(all(tile not in chrome_tiles for tile in data.text_tile_ids))
        self.assertEqual(len(set(data.text_tile_ids)), len(data.text_tile_ids))
        self.assertLess(max(data.text_tile_ids), 864)

    def test_pda_generator_writes_deterministic_evidence_and_runtime_assets(self):
        extractor = ROOT / 'tools' / 'extract_pda.py'
        spec = importlib.util.spec_from_file_location('extract_pda_generate', extractor)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            module.generate(ROOT, out, Path(os.environ['GRAVEBLOOD_ROM']))
            for rel in (
                'data/pda_runtime_semantics.csv',
                'data/pda_page_render_sources.csv',
                'data/pda_cursor_semantics.csv',
                'data/pda_friends_entries.csv',
                'reconstruction/data/pda_assets.c',
                'disasm/pda_renderer_080075F8.txt',
                'disasm/pda_open_0800849E.txt',
                'disasm/pda_navigation_080088EC.txt',
                'disasm/pda_messages_select_08009568.txt',
                'disasm/pda_friends_navigation_080089BE.txt',
            ):
                self.assertTrue((out / rel).is_file(), rel)
            runtime = list(csv.DictReader((out / 'data/pda_runtime_semantics.csv').read_text(encoding='utf-8').splitlines()))
            actions = {row['fact']: row for row in runtime}
            self.assertEqual('fresh START', actions['open_input']['value'])
            self.assertIn('channels 0,1,2', actions['open_audio']['value'])
            self.assertEqual('fresh R shoulder page+1; fresh L shoulder page-1; bounds 0..3; no wrap', actions['page_navigation']['value'])
            self.assertEqual('no ordinary direct close input proven', actions['ordinary_close']['value'])
            cursor = list(csv.DictReader((out / 'data/pda_cursor_semantics.csv').read_text(encoding='utf-8').splitlines()))
            by_page = {row['page']: row for row in cursor}
            self.assertEqual('dpad LEFT/RIGHT', by_page['MESSAGES']['keys'])
            self.assertEqual('0..3; skip selector -1', by_page['MESSAGES']['bounds'])
            self.assertEqual('dpad UP/DOWN', by_page['FRIENDS']['keys'])
            self.assertEqual('cursor row 0..2 plus scroll over 6 entries', by_page['FRIENDS']['bounds'])
            self.assertEqual('SFX4 volume 0x50 on success; SFX12 volume 0x50 at absolute top/bottom boundary', by_page['FRIENDS']['sfx'])
            ctext = (out / 'reconstruction/data/pda_assets.c').read_text(encoding='utf-8')
            self.assertIn('gb_pda_page_maps[GB_PDA_PAGE_COUNT][GB_PDA_MAP_CELLS]', ctext)
            self.assertIn('gb_pda_friend_names[GB_PDA_FRIEND_COUNT]', ctext)
            self.assertIn('gb_pda_text_tile_ids[GB_PDA_TEXT_TILE_COUNT]', ctext)

if __name__ == '__main__':
    unittest.main()
