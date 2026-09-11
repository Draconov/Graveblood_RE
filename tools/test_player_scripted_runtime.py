#!/usr/bin/env python3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GBA_H = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_SELECT (1u << 2)
#define KEY_START (1u << 3)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
'''

HARNESS = r'''
#include <assert.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/input.h>

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

static GbLevelAssets open_level(u8 id)
{
    static const u16 open[16384] = {0};
    GbLevelAssets level = {0};
    level.level_id = id;
    level.world_width_tiles = 128;
    level.world_height_tiles = 128;
    level.collision = open;
    return level;
}

int main(void)
{
    GbPlayer p;
    GbInput right = { .held = KEY_RIGHT };
    GbInput idle = {0};
    GbLevelAssets level9 = open_level(9);
    GbLevelAssets level10 = open_level(10);

    gb_player_spawn(&p, 2555, 400);
    assert(gb_player_try_level10_boundary(&p, 9) == 0);
    assert(p.script_mode == 0);

    p.x = 2556;
    p.x_fixed = 2556 << 8;
    assert(gb_player_try_level10_boundary(&p, 8) == 0);
    assert(gb_player_try_level10_boundary(&p, 9) == 1);
    assert(p.script_mode == 5);
    assert(gb_player_try_level10_boundary(&p, 9) == 0);

    /* Mode 5 suppresses normal input before the queued Level-10 load. */
    gb_player_update(&p, &level9, &right);
    assert(p.request_x_fixed == 0);
    assert(p.request_y_fixed == 0);
    assert(p.x_fixed == (2556 << 8));
    assert(p.script_mode == 5);

    /* In Level 10, mode 5 requests +370 fixed8 and advances its controller
       counter.  The >700 / >350 test is made before applying that frame's
       request; crossing both switches to mode 6 and snaps Y to 870. */
    gb_player_spawn(&p, 701, 500);
    p.script_mode = 5;
    p.script_counter = 350;
    gb_player_update(&p, &level10, &idle);
    assert(p.script_counter == 351);
    assert(p.script_mode == 6);
    assert(p.y_fixed == (870 << 8));
    assert(p.y == 870);
    assert(p.request_x_fixed == 0);

    /* Mode 6 climbs at exactly -256 fixed8 while Y > 780.  At Y == 780,
       the following update clears the script without another step. */
    for(int i = 0; i < 90; ++i)
    {
        gb_player_update(&p, &level10, &right);
    }
    assert(p.y_fixed == (780 << 8));
    assert(p.y == 780);
    assert(p.script_mode == 6);
    gb_player_update(&p, &level10, &right);
    assert(p.script_mode == 0);
    assert(p.y_fixed == (780 << 8));
    assert(p.request_y_fixed == 0);

    return 0;
}
'''

class PlayerScriptedRuntimeTests(unittest.TestCase):
    def test_level9_boundary_and_level10_script(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'player_script_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], cwd=ROOT, check=True)

    def test_game_checks_boundary_before_normal_player_update_and_preserves_mode(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('gb_player_try_level10_boundary(&player, world.assets->level_id)', game)
        boundary = game.index('gb_player_try_level10_boundary(&player, world.assets->level_id)')
        normal = game.index('gb_player_update(&player, world.assets, &input);')
        self.assertLess(boundary, normal)
        self.assertIn('gb_scene_request_gameplay(&scene, 10, 10);', game)
        self.assertIn('saved_script_mode', game)
        self.assertIn('saved_script_counter', game)
        self.assertIn('GbPlayer player = {0};', game)

if __name__ == '__main__':
    unittest.main()
