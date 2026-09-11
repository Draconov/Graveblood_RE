#!/usr/bin/env python3
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('render_sprites', ROOT / 'tools' / 'render_sprites.py')
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class ObjRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba')).read_bytes()

    def test_obj_renderer_tool_exists(self):
        self.assertTrue((ROOT / 'tools' / 'render_sprites.py').exists())

    def test_low_level_tile_arg_decodes_8bpp_tile_and_flip_flags(self):
        # 0x0800A8F0 maps logical 8bpp tile N to ATTR2 tile index N*2,
        # while tile-arg bits 10/11 become ATTR1 H/V flip bits.
        decoded = mod.decode_obj_tile_arg(0x155 | 0x400 | 0x800)
        self.assertEqual(decoded['logical_tile'], 0x155)
        self.assertEqual(decoded['hardware_tile'], 0x2AA)
        self.assertTrue(decoded['hflip'])
        self.assertTrue(decoded['vflip'])

    def test_shape_enum_matches_oam_shape_and_size_table(self):
        self.assertEqual([mod.obj_dimensions(i) for i in range(4)], [
            (8, 8), (8, 16), (16, 8), (16, 16)
        ])

    def test_2d_obj_mapping_wraps_each_8bpp_tile_row_by_16_logical_tiles(self):
        # DISPCNT bit 6 is clear: OBJ uses 2D mapping. Hardware tile rows are
        # 32 32-byte units apart, i.e. 16 logical 64-byte 8bpp tiles.
        self.assertEqual(mod.obj_2d_logical_tile(0x48, 0, 0), 0x48)
        self.assertEqual(mod.obj_2d_logical_tile(0x48, 1, 0), 0x49)
        self.assertEqual(mod.obj_2d_logical_tile(0x48, 0, 1), 0x58)
        self.assertEqual(mod.obj_2d_logical_tile(0x48, 1, 1), 0x59)

    def test_source_tile_capacity_is_bounded_by_obj_palette_source(self):
        self.assertEqual(mod.obj_source_tile_capacity(), 5536)

    def test_complete_source_atlas_has_all_source_tiles(self):
        image = mod.render_source_tile_atlas(self.data, columns=32)
        self.assertEqual(image.size, (256, 1384))

    def test_reference_artifact_export_writes_atlas_frames_and_summary(self):
        with tempfile.TemporaryDirectory() as td:
            outputs = mod.write_reference_sprite_artifacts(self.data, Path(td))
            names = {p.name for p in outputs}
            self.assertIn('obj_source_atlas.png', names)
            self.assertIn('character_source_2198.png', names)
            self.assertIn('player_branch_candidate_3468.png', names)
            self.assertIn('sprite_summary.json', names)
            self.assertTrue(all(p.exists() for p in outputs))

    def test_reference_summary_classifies_grass_and_leaf_tiles_separately(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            outputs = mod.write_reference_sprite_artifacts(self.data, Path(td))
            summary_path = next(path for path in outputs if path.name == 'sprite_summary.json')
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            self.assertIn('grass_tile_note', summary)
            self.assertNotIn('leaves_tile_note', summary)
            self.assertEqual(['0x4C', '0x4D', '0x5C', '0x5D'], summary['leaf_particle_frame_tiles'])
            self.assertTrue((Path(td) / 'grass_logical_tile_0x48.png').is_file())
            self.assertTrue((Path(td) / 'leaf_particle_frame_0x4C.png').is_file())

    def test_source_sheet_can_render_known_character_piece_beyond_initial_upload(self):
        image = mod.render_source_obj_sprite(self.data, 2198, 2)
        self.assertEqual(image.size, (16, 8))
        self.assertEqual(image.getbbox(), (1, 0, 15, 8))
        self.assertEqual(image.getpixel((1, 0)), (180, 213, 41, 255))
        self.assertEqual(image.getpixel((7, 7)), (98, 41, 156, 255))

    def test_dynamic_obj_copy_targets_8bpp_logical_slots(self):
        vram = bytearray(0x8000)
        mod.copy_source_tiles_to_obj_vram(self.data, vram, 0x60, 2198, 2)
        source_off = mod.OBJ_TILES_SOURCE - mod.ROM_BASE + 2198 * 64
        self.assertEqual(vram[0x60 * 64:0x62 * 64], self.data[source_off:source_off + 128])

    def test_initial_obj_vram_is_the_code_proven_0x8000_byte_upload(self):
        vram = mod.initial_obj_vram(self.data)
        self.assertEqual(len(vram), 0x8000)
        src = mod.OBJ_TILES_SOURCE - mod.ROM_BASE
        self.assertEqual(vram[:256], self.data[src:src + 256])

    def test_four_row_dynamic_copy_reconstructs_known_16x32_character_frame(self):
        # 2198 is a known-valid Vika-style bank/frame sample; it is not
        # claimed to be the constructor/default equipped outfit.
        image = mod.reconstruct_player_frame_from_source_rows(self.data, 2198)
        self.assertEqual(image.size, (16, 32))
        self.assertEqual(image.getbbox(), (0, 0, 15, 32))
        # Stable pixels spanning the upper and lower 16x16 OAM pieces.
        self.assertEqual(image.getpixel((1, 0)), (180, 213, 41, 255))
        self.assertEqual(image.getpixel((7, 23)), (213, 230, 255, 255))

    def test_player_animation_initializers_are_read_from_startup_data(self):
        init = mod.player_animation_initializers_from_rom(self.data)
        self.assertEqual(init['bank'], 15)
        self.assertEqual(init['state'], 8)
        self.assertEqual(init['frame'], 1)
        self.assertEqual(init['countdown'], 5)

    def test_default_player_animation_source_bases_match_draw_branches(self):
        sources = mod.player_animation_source_bases(15)
        self.assertEqual(sources['regular_walk'], (3456, 3458, 3460, 3462, 3464, 3466))
        self.assertEqual(sources['up_walk'], (3520, 3522, 3524, 3526, 3528, 3530))
        self.assertEqual(sources['idle_unique'], (3468, 3470, 3532, 3534))
        self.assertEqual(
            sources['idle_sequence'],
            (3468, 3470, 3532, 3534, 3534, 3532, 3470, 3468),
        )
        self.assertEqual(
            sources['idle_selector1'],
            (3392, 3394, 3396, 3398, 3400, 3402, 3404, 3406),
        )

    def test_default_player_animation_has_sixteen_unique_packed_frames(self):
        sources = mod.player_animation_source_bases(15)
        packed = sources['regular_walk'] + sources['up_walk'] + sources['idle_unique']
        self.assertEqual(len(packed), 16)
        self.assertEqual(len(set(packed)), 16)


    def test_npc_source_bias_comes_from_initialized_iwram_field(self):
        self.assertEqual(mod.npc_source_bias_from_rom(self.data), 0xE00)
        self.assertEqual(mod.NPC_SOURCE_BIAS_RAM, 0x030007FC)

    def test_story_npc_frame_uses_code_proven_initialized_bias(self):
        image = mod.reconstruct_npc_frame(self.data, legs_color=200, subtype=0, frame=1)
        self.assertEqual(image.size, (16, 32))
        self.assertEqual(image.getbbox(), (1, 0, 15, 32))
        self.assertEqual(image.getpixel((7, 0)), (238, 222, 180, 255))
        self.assertEqual(image.getpixel((7, 31)), (24, 74, 32, 255))

    def test_npc_source_frame_formula_matches_draw_routine(self):
        self.assertEqual(mod.npc_source_base(0, legs_color=56, subtype=0, frame=1), 448)
        self.assertEqual(mod.npc_source_base(0, legs_color=56, subtype=0, frame=2), 450)
        self.assertEqual(mod.npc_source_base(0, legs_color=24, subtype=4, frame=1), 196)
        self.assertEqual(mod.npc_source_rows(196), (196, 212, 228, 244))

    def test_npc_dynamic_obj_rows_match_0x0800274c_staging_math(self):
        self.assertEqual(mod.npc_dynamic_logical_rows(0, 0, 0), (0x60, 0x70, 0x80, 0x90))
        self.assertEqual(mod.npc_dynamic_logical_rows(1, 0, 0), (0x90, 0xA0, 0xB0, 0xC0))

    def test_story_entity_contact_sheet_renders_all_standalone_records(self):
        records = [
            {'index': i, 'level': 10 if i >= 11 else 0, 'legsColor': 24 if i >= 11 else 56,
             'subtype': 6 if i >= 11 else 0, 'state': 4 if i >= 11 else 2, 'dial': 3 if i >= 11 else 0}
            for i in range(16)
        ]
        image = mod.render_story_entity_contact_sheet(self.data, records, columns=8)
        self.assertEqual(image.size, (8 * 80, 2 * 72))
        # State-4 rows deliberately demonstrate that the NPC runtime class can render non-human entities.
        self.assertNotEqual(image.getbbox(), None)

    def test_story_entity_sprite_rows_record_exact_source_selection(self):
        records = [{'index': 4, 'level': 0, 'legsColor': 200, 'subtype': 0, 'state': 3, 'dial': 2}]
        rows = mod.story_entity_sprite_rows(self.data, records)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source_base'], 5184)
        self.assertEqual(rows[0]['source_rows'], '5184;5200;5216;5232')
        self.assertEqual(rows[0]['runtime_class'], 'npc')

    def test_state4_monster_render_branch_reconstructs_creature_composite(self):
        image = mod.render_state4_monster_composite(self.data, animation_counter=24)
        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.getbbox(), (16, 6, 47, 43))
        self.assertEqual(image.getpixel((31, 20)), (32, 16, 41, 255))
        self.assertEqual(image.getpixel((20, 25)), (57, 82, 74, 255))

if __name__ == '__main__':
    unittest.main()
