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

static GbLevelAssets open_level(void)
{
    static const u16 open[16384] = {0};
    GbLevelAssets level = {0};
    level.level_id = 10;
    level.world_width_tiles = 128;
    level.world_height_tiles = 128;
    level.collision = open;
    return level;
}

int main(void)
{
    GbPlayer p;
    GbInput idle = {0};
    GbLevelAssets level = open_level();

    gb_player_spawn(&p, 808, 392);
    assert(p.motion_reset_x == 1);
    assert(p.motion_reset_y == 1);

    gb_player_queue_vertical_target(&p, 360);
    assert(p.x == 808 && p.y == 392);
    assert(p.request_y_fixed == (360 - 392) * 256);
    assert(p.motion_reset_x == 0);
    assert(p.motion_reset_y == 0);

    /* Clearing the two ROM-backed +0x390/+0x394 sentinels lets the queued
       request survive exactly one normal Player update and reach collision. */
    gb_player_update(&p, &level, &idle);
    assert(p.y_fixed == (360 << 8));
    assert(p.y == 360);
    assert(p.motion_reset_x == 1);
    assert(p.motion_reset_y == 1);
    assert(p.request_y_fixed == (360 - 392) * 256);

    /* The next ordinary update sees the re-armed sentinel and clears stale
       request state, so the target delta cannot repeat. */
    gb_player_update(&p, &level, &idle);
    assert(p.y_fixed == (360 << 8));
    assert(p.request_y_fixed == 0);
    return 0;
}
'''

class PlayerForcedTargetRuntimeTests(unittest.TestCase):
    def test_vertical_target_survives_one_normal_update(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'forced_target_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], cwd=ROOT, check=True)

    def test_story_queues_forced_vertical_motion_instead_of_teleporting(self):
        story = (ROOT / 'reconstruction/source/game/story.c').read_text(encoding='utf-8')
        self.assertIn('gb_player_queue_vertical_target(player, gate->target_y);', story)
        self.assertIn('gb_player_queue_vertical_target(player, 512);', story)
        self.assertNotIn('player->y = gate->target_y;', story)
        self.assertNotIn('player->y = 512;', story)

if __name__ == '__main__':
    unittest.main()
