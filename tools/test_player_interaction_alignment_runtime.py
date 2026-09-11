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

static GbLevelAssets open_level(void)
{
    static const u16 open[16384] = {0};
    GbLevelAssets level = {0};
    level.world_width_tiles = 128;
    level.world_height_tiles = 128;
    level.collision = open;
    return level;
}

int main(void)
{
    GbPlayer p;
    GbLevelAssets level = open_level();

    /* Anchor at/right: endpoint is actorX-19, actorY, facing value 1. */
    gb_player_spawn(&p, 100, 200);
    gb_player_queue_social_alignment(&p, 150, 220);
    assert(p.request_x_fixed == ((150 - 100) * 256 - 0x1300));
    assert(p.request_y_fixed == (220 - 200) * 256);
    assert(p.facing_right == 1);
    assert(p.motion_reset_x == 0 && p.motion_reset_y == 0);
    gb_player_resolve_queued_motion(&p, &level);
    assert(p.x_fixed == (131 << 8));
    assert(p.y_fixed == (220 << 8));
    assert(p.x == 131 && p.y == 220);
    assert(p.motion_reset_x == 1 && p.motion_reset_y == 1);

    /* Anchor left: endpoint is actorX+19, actorY, facing value 0. */
    gb_player_spawn(&p, 100, 200);
    gb_player_queue_social_alignment(&p, 80, 180);
    assert(p.request_x_fixed == ((80 - 100) * 256 + 0x1300));
    assert(p.request_y_fixed == (180 - 200) * 256);
    assert(p.facing_right == 0);
    gb_player_resolve_queued_motion(&p, &level);
    assert(p.x_fixed == (99 << 8));
    assert(p.y_fixed == (180 << 8));
    assert(p.x == 99 && p.y == 180);

    /* Dialogue alignment is vertical-only and reuses 0x080080A4 semantics. */
    gb_player_spawn(&p, 300, 240);
    gb_player_queue_vertical_target(&p, 264);
    gb_player_resolve_queued_motion(&p, &level);
    assert(p.x_fixed == (300 << 8));
    assert(p.y_fixed == (264 << 8));
    return 0;
}
'''

class PlayerInteractionAlignmentRuntimeTests(unittest.TestCase):
    def test_social_and_dialogue_alignment_helpers_use_collision_motion(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'interaction_align_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], cwd=ROOT, check=True)

    def test_game_resolves_alignment_before_starting_story_ui(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('gb_player_queue_social_alignment(&player, interaction.actor_x, interaction.actor_y);', game)
        self.assertIn('actors.actors[interaction.actor_index].descriptor->legs_color != 1', game)
        self.assertIn('gb_player_queue_vertical_target(&player, interaction.actor_y);', game)
        self.assertIn('gb_player_resolve_queued_motion(&player, world.assets);', game)
        self.assertLess(game.index('gb_player_resolve_queued_motion(&player, world.assets);'),
                        game.index('gb_story_handle_interaction(&story, &actors, &interaction);'))

if __name__ == '__main__':
    unittest.main()
