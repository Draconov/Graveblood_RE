#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))


def u16(data: bytes, addr: int) -> int:
    off = addr - 0x08000000
    return int.from_bytes(data[off:off + 2], 'little')


def u32(data: bytes, addr: int) -> int:
    off = addr - 0x08000000
    return int.from_bytes(data[off:off + 4], 'little')


class GameplayFrameOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM.read_bytes()

    def test_rom_gameplay_scene_draws_before_object_updates(self):
        data = self.data
        # GameplayScene_update 0x08004B74 has the stable high-level call chain:
        # clamp camera -> stream -> OAM begin -> generic draw -> OAM end -> generic update.
        self.assertEqual(u16(data, 0x08004B76), 0xF005)
        self.assertEqual(u16(data, 0x08004B78), 0xFBAD)  # BL 0x0800A2D4
        self.assertEqual(u16(data, 0x08004B7E), 0x4818)
        self.assertEqual(u16(data, 0x08004B80), 0xF005)
        self.assertEqual(u16(data, 0x08004B82), 0xFC3E)  # BL 0x0800A400
        self.assertEqual(u16(data, 0x08004BBE), 0xF005)
        self.assertEqual(u16(data, 0x08004BC0), 0xFFB3)  # BL 0x0800AB28
        self.assertEqual(u16(data, 0x08004BC6), 0xF7FB)
        self.assertEqual(u16(data, 0x08004BC8), 0xFFE7)  # BL 0x08000B98
        self.assertEqual(u16(data, 0x08004BCA), 0xF005)
        self.assertEqual(u16(data, 0x08004BCC), 0xFFB3)  # BL 0x0800AB34
        self.assertEqual(u16(data, 0x08004BD0), 0xF7FC)
        self.assertEqual(u16(data, 0x08004BD2), 0xFC2A)  # BL 0x08001428

        # The generic manager slots are independently classified by the Player vtable.
        # Player vtable base is 0x08019688: +0x0C update=0x080081B1,
        # +0x10 draw=0x080065FD. 0x08000B98 calls +0x10; 0x08001428 calls +0x0C.
        self.assertEqual(u32(data, 0x08019688 + 0x0C), 0x080081B1)
        self.assertEqual(u32(data, 0x08019688 + 0x10), 0x080065FD)
        self.assertEqual(u16(data, 0x08000BAC), 0x691B)  # ldr r3,[r3,#0x10]
        self.assertEqual(u16(data, 0x0800160C), 0x68DB)  # ldr r3,[r3,#0x0C]

    def test_frame_order_csv_matches_rom_extractor(self):
        spec = importlib.util.spec_from_file_location(
            "extract_extended_semantics", ROOT / "tools/extract_extended_semantics.py")
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "extract_gameplay_frame_order"),
                        "gameplay frame-order extractor is missing")
        expected = module.extract_gameplay_frame_order(self.data)
        csv_path = ROOT / "data/gameplay_frame_order.csv"
        self.assertTrue(csv_path.is_file(), csv_path)
        with csv_path.open(newline="", encoding="utf-8") as f:
            actual = list(csv.DictReader(f))
        self.assertEqual(actual, expected)

    def test_player_scene_open_inputs_run_in_update_phase_after_gameplay_draw(self):
        data = self.data
        # Both hidden Wardrobe entry and PDA START gate are inside Player_update,
        # whose manager slot is invoked only after GameplayScene's draw traversal.
        self.assertEqual(tuple(u16(data, a) for a in (0x08008318, 0x0800831A, 0x0800831C)),
                         (0x681B, 0x2B06, 0xD101))
        self.assertEqual(u16(data, 0x0800849E), 0x2208)
        self.assertTrue(0x080081B0 <= 0x08008318 < 0x08009C00)
        self.assertTrue(0x080081B0 <= 0x0800849E < 0x08009C00)

        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        publish = game.index('gb_world_publish_camera(&world);')
        draw = game.index('gb_video_draw_gameplay_objects(&actors, &player, &story,', publish)
        start_gate = game.index('(input.pressed & KEY_START)')
        wardrobe_gate = game.index('input.held == (KEY_B | KEY_SELECT)')
        self.assertLess(draw, start_gate)
        self.assertLess(draw, wardrobe_gate)

    def test_world_camera_tracking_is_deferred_until_publish(self):
        harness = r'''\
#include <graveblood/world.h>
#include <stdio.h>

static int full_count, column_count, row_count, set_camera_count;
static s16 last_camera_x, last_camera_y;
void gb_video_load_level(const GbLevelAssets* assets) { (void)assets; }
void gb_video_stream_full(const GbLevelAssets* assets, s16 x, s16 y) { (void)assets; (void)x; (void)y; ++full_count; }
void gb_video_stream_column(const GbLevelAssets* assets, s16 x, s16 y) { (void)assets; (void)x; (void)y; ++column_count; }
void gb_video_stream_row(const GbLevelAssets* assets, s16 x, s16 y) { (void)assets; (void)x; (void)y; ++row_count; }
void gb_video_set_camera(s16 x, s16 y) { last_camera_x=x; last_camera_y=y; ++set_camera_count; }

static int require(int cond, const char* msg) { if(!cond) { puts(msg); return 0; } return 1; }

int main(void) {
    GbLevelAssets assets = {0};
    assets.world_width_tiles = 80;
    assets.world_height_tiles = 60;
    GbWorld world = {0};
    gb_world_load(&world, &assets);
    set_camera_count = 0; /* ignore load publication */

    gb_world_publish_camera(&world);
    if(!require(full_count == 1 && set_camera_count == 1 && last_camera_x == 0, "initial publish")) return 1;

    gb_world_track_camera(&world, 144, 88); /* center x=152 -> pending camera x=8 */
    if(!require(world.camera_x == 8, "tracker updates pending camera")) return 1;
    if(!require(full_count == 1 && column_count == 0 && row_count == 0, "tracker must not stream")) return 1;
    if(!require(set_camera_count == 1 && last_camera_x == 0, "tracker must not publish video camera")) return 1;

    gb_world_publish_camera(&world);
    if(!require(column_count == 1 && world.stream_tile_x == 1, "next publish streams pending camera")) return 1;
    if(!require(set_camera_count == 2 && last_camera_x == 8, "next publish exposes pending camera")) return 1;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as td_value:
            td = Path(td_value)
            (td / 'gba.h').write_text('typedef signed char s8; typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32; typedef short s16; typedef int s32;\n', encoding='utf-8')
            (td / 'test.c').write_text(harness, encoding='utf-8')
            exe = td / 'test'
            cmd = [
                'cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/world.c'), str(td / 'test.c'), '-o', str(exe),
            ]
            built = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(exe)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)

    def test_clean_room_gameplay_draw_precedes_updates_and_tracking_is_deferred(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('gb_world_publish_camera(&world);', game)
        self.assertIn('gb_world_track_camera(&world, player.x, player.y);', game)
        publish = game.index('gb_world_publish_camera(&world);')
        draw_actors = game.index('gb_video_draw_gameplay_objects(&actors, &player, &story,', publish)
        overlay_update = game.index('gb_actor_system_update_overlays(', draw_actors)
        pre_player_loop = game.index(
            'for(u8 physical_index = 0; physical_index < player_physical_index; ++physical_index)',
            overlay_update)
        player_update = game.index('gb_player_update(&player, world.assets, &input);', pre_player_loop)
        track = game.index('gb_world_track_camera(&world, player.x, player.y);', player_update)
        self.assertLess(publish, draw_actors)
        self.assertLess(draw_actors, overlay_update)
        self.assertLess(overlay_update, pre_player_loop)
        self.assertLess(pre_player_loop, player_update)
        self.assertLess(player_update, track)
        # The active-gameplay tail must not immediately publish the just-tracked camera.
        tail = game[track:game.index('\n    }\n}', track)]
        self.assertNotIn('gb_world_publish_camera(&world);', tail)
        self.assertNotIn('gb_video_draw_gameplay_objects(&actors, &player, &story,', tail)


if __name__ == '__main__':
    unittest.main()
