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
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
#define KEY_A      (1u << 0)
#define KEY_B      (1u << 1)
#define KEY_SELECT (1u << 2)
#define KEY_START  (1u << 3)
#define KEY_RIGHT  (1u << 4)
#define KEY_LEFT   (1u << 5)
#define KEY_UP     (1u << 6)
#define KEY_DOWN   (1u << 7)
#endif
'''

HARNESS = r'''
#include <assert.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/collision.h>

static GbLevelAssets level_with_grid(const u16* grid, u16 w, u16 h)
{
    GbLevelAssets level = {0};
    level.world_width_tiles = w;
    level.world_height_tiles = h;
    level.collision = grid;
    return level;
}

static void spawn_fixed(GbPlayer* p, int x, int y)
{
    gb_player_spawn(p, (s16)x, (s16)y);
    assert(p->x_fixed == x * 256);
    assert(p->y_fixed == y * 256);
    assert(p->collision_width_fixed == 0x1000);
    assert(p->collision_height_fixed == 0x1000);
}

int main(void)
{
    static u16 open[64] = {0};
    GbLevelAssets level = level_with_grid(open, 8, 8);
    GbPlayer p;

    /* ROM 0x08004670 adds request fixed8 directly: half-pixel motion
       must survive even when public pixel coordinates do not change. */
    spawn_fixed(&p, 16, 24);
    p.request_x_fixed = 128;
    p.request_y_fixed = 0;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 16 * 256 + 128);
    assert(p.x == 16);
    assert(p.collision_status == 0);

    /* +X mid-body tile 14 is the solver's special horizontal blocker. */
    for(int i = 0; i < 64; ++i) open[i] = 0;
    spawn_fixed(&p, 16, 24);
    /* right candidate x = 32px -> cell 4; mid y = 17px -> cell 2 */
    open[2 * 8 + 4] = 14;
    p.request_x_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 16 * 256);
    assert(p.request_x_fixed == 0);
    assert(p.collision_status == 7);

    /* -X uses the mirrored special block/status 11. */
    for(int i = 0; i < 64; ++i) open[i] = 0;
    spawn_fixed(&p, 16, 24);
    /* left candidate x = 15px -> cell 1; mid y = 17px -> cell 2 */
    open[2 * 8 + 1] = 14;
    p.request_x_fixed = -256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 16 * 256);
    assert(p.request_x_fixed == 0);
    assert(p.collision_status == 11);

    /* Downward center collision zeros Y request and ORs 0x31. */
    for(int i = 0; i < 64; ++i) open[i] = 0;
    spawn_fixed(&p, 16, 24);
    /* bottom candidate y = 25px -> row 3; center x = 24px -> cell 3 */
    open[3 * 8 + 3] = 1;
    p.request_y_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.y_fixed == 24 * 256);
    assert(p.request_y_fixed == 0);
    assert((p.collision_status & 0x31) == 0x31);

    /* Upward center collision uses 0x51.  The original top probe is
       one fixed8 unit shy of the next cell boundary. */
    for(int i = 0; i < 64; ++i) open[i] = 0;
    spawn_fixed(&p, 16, 24);
    /* top candidate for -1px lands in row 0; center x is cell 3. */
    open[0 * 8 + 3] = 1;
    p.request_y_fixed = -256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.y_fixed == 24 * 256);
    assert(p.request_y_fixed == 0);
    assert((p.collision_status & 0x51) == 0x51);

    return 0;
}
'''


CORNER_HARNESS = r"""
#include <assert.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/collision.h>

static void clear_grid(u16* grid) { for(int i = 0; i < 64; ++i) grid[i] = 0; }
static GbLevelAssets make_level(u16* grid)
{
    GbLevelAssets level = {0};
    level.world_width_tiles = 8;
    level.world_height_tiles = 8;
    level.collision = grid;
    return level;
}
static void spawn(GbPlayer* p, int x, int y) { gb_player_spawn(p, (s16)x, (s16)y); }

int main(void)
{
    u16 grid[64] = {0};
    GbLevelAssets level = make_level(grid);
    GbPlayer p;

    spawn(&p, 16, 24); clear_grid(grid); grid[1 * 8 + 4] = 1;
    p.request_x_fixed = 256; gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 17 * 256); assert(p.y_fixed == 25 * 256);

    spawn(&p, 16, 24); clear_grid(grid); grid[3 * 8 + 4] = 1;
    p.request_x_fixed = 256; gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 17 * 256); assert(p.y_fixed == 23 * 256);

    spawn(&p, 16, 24); clear_grid(grid); grid[1 * 8 + 1] = 1;
    p.request_x_fixed = -256; gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 15 * 256); assert(p.y_fixed == 25 * 256);

    spawn(&p, 16, 24); clear_grid(grid); grid[3 * 8 + 1] = 1;
    p.request_x_fixed = -256; gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 15 * 256); assert(p.y_fixed == 23 * 256);

    spawn(&p, 13, 24); clear_grid(grid); grid[3 * 8 + 3] = 1;
    p.request_y_fixed = 256; gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 12 * 256); assert(p.y_fixed == 25 * 256);

    spawn(&p, 13, 24); clear_grid(grid); grid[3 * 8 + 1] = 1;
    p.request_y_fixed = 256; gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 14 * 256); assert(p.y_fixed == 25 * 256);

    spawn(&p, 13, 24); clear_grid(grid); grid[0 * 8 + 3] = 1;
    p.request_y_fixed = -256; gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 12 * 256); assert(p.y_fixed == 23 * 256);

    spawn(&p, 13, 24); clear_grid(grid); grid[0 * 8 + 1] = 1;
    p.request_y_fixed = -256; gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 14 * 256); assert(p.y_fixed == 23 * 256);
    return 0;
}

"""



DIAGONAL_CORNER_HARNESS = r"""
#include <assert.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/collision.h>

static void clear_grid(u16* grid) { for(int i = 0; i < 64; ++i) grid[i] = 0; }
static GbLevelAssets make_level(u16* grid)
{
    GbLevelAssets level = {0};
    level.world_width_tiles = 8;
    level.world_height_tiles = 8;
    level.collision = grid;
    return level;
}
static void spawn(GbPlayer* p) { gb_player_spawn(p, 16, 24); }

int main(void)
{
    u16 grid[64] = {0};
    GbLevelAssets level = make_level(grid);
    GbPlayer p;

    /* With simultaneous Y motion, a horizontal top/bottom corner does not
       take the axis-only +/-1px slide and does not cancel X. */
    spawn(&p); clear_grid(grid); grid[1 * 8 + 4] = 1;
    p.request_x_fixed = 256; p.request_y_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 17 * 256); assert(p.y_fixed == 25 * 256);

    spawn(&p); clear_grid(grid); grid[3 * 8 + 4] = 1;
    p.request_x_fixed = 256; p.request_y_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 17 * 256); assert(p.y_fixed == 25 * 256);

    spawn(&p); clear_grid(grid); grid[1 * 8 + 1] = 1;
    p.request_x_fixed = -256; p.request_y_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 15 * 256); assert(p.y_fixed == 25 * 256);

    spawn(&p); clear_grid(grid); grid[3 * 8 + 1] = 1;
    p.request_x_fixed = -256; p.request_y_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 15 * 256); assert(p.y_fixed == 25 * 256);
    return 0;
}
"""

DOUBLE_CORNER_HARNESS = r"""
#include <assert.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/collision.h>

static void clear_grid(u16* grid) { for(int i = 0; i < 64; ++i) grid[i] = 0; }
static GbLevelAssets make_level(u16* grid)
{
    GbLevelAssets level = {0};
    level.world_width_tiles = 8;
    level.world_height_tiles = 8;
    level.collision = grid;
    return level;
}
static void spawn(GbPlayer* p, int x, int y) { gb_player_spawn(p, (s16)x, (s16)y); }

int main(void)
{
    u16 grid[64] = {0};
    GbLevelAssets level = make_level(grid);
    GbPlayer p;

    /* 0x08004826 tentatively slides down around a top X-corner, but if
       the validation sample is occupied the ROM restores Y and still
       carries the horizontal request. */
    spawn(&p, 16, 24); clear_grid(grid);
    grid[1 * 8 + 4] = 1; grid[3 * 8 + 4] = 1;
    p.request_x_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 17 * 256); assert(p.y_fixed == 24 * 256);

    spawn(&p, 16, 24); clear_grid(grid);
    grid[1 * 8 + 1] = 1; grid[3 * 8 + 1] = 1;
    p.request_x_fixed = -256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 15 * 256); assert(p.y_fixed == 24 * 256);

    /* 0x08004866/0x080049A8 tentatively slide left around a right Y-corner.
       If the opposite corner is also occupied the ROM restores X and still
       carries Y. */
    spawn(&p, 13, 24); clear_grid(grid);
    grid[3 * 8 + 3] = 1; grid[3 * 8 + 1] = 1;
    p.request_y_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 13 * 256); assert(p.y_fixed == 25 * 256);

    spawn(&p, 13, 24); clear_grid(grid);
    grid[0 * 8 + 3] = 1; grid[0 * 8 + 1] = 1;
    p.request_y_fixed = -256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 13 * 256); assert(p.y_fixed == 23 * 256);

    /* Vertical corner probes use the pre-motion body edge row, not the
       destination center-probe row.  This matters for requests that cross
       an 8-pixel cell boundary (interaction alignment can do that). */
    spawn(&p, 13, 31); clear_grid(grid);
    grid[3 * 8 + 3] = 1;
    p.request_y_fixed = 512;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 12 * 256); assert(p.y_fixed == 33 * 256);

    spawn(&p, 13, 24); clear_grid(grid);
    grid[0 * 8 + 3] = 1;
    p.request_y_fixed = -2048;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 12 * 256); assert(p.y_fixed == 16 * 256);

    /* A blocked vertical center still falls through the side-corner phase. */
    spawn(&p, 13, 24); clear_grid(grid);
    grid[3 * 8 + 2] = 1; grid[3 * 8 + 3] = 1;
    p.request_y_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 12 * 256); assert(p.y_fixed == 24 * 256);
    assert((p.collision_status & 0x31) == 0x31);

    spawn(&p, 13, 24); clear_grid(grid);
    grid[0 * 8 + 2] = 1; grid[0 * 8 + 3] = 1;
    p.request_y_fixed = -256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 12 * 256); assert(p.y_fixed == 24 * 256);
    assert((p.collision_status & 0x51) == 0x51);

    /* Horizontal tile-14 blocking cancels X/status, then re-probes the
       current body edge for the normal axis-only corner correction. */
    spawn(&p, 16, 24); clear_grid(grid);
    grid[2 * 8 + 4] = 14; grid[1 * 8 + 3] = 1;
    p.request_x_fixed = 256;
    gb_collision_apply_player_motion(&level, &p);
    assert(p.x_fixed == 16 * 256); assert(p.y_fixed == 25 * 256);
    assert(p.collision_status == 7);
    return 0;
}
"""

NORMAL_MOVEMENT_HARNESS = r"""
#include <assert.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/input.h>

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

int main(void)
{
    static const u16 open[256] = {0};
    GbLevelAssets level = {0};
    level.world_width_tiles = 16;
    level.world_height_tiles = 16;
    level.collision = open;
    GbPlayer p;
    gb_player_spawn(&p, 32, 48);

    /* Normal mode cardinal requests are exactly one fixed8 pixel. */
    GbInput right = { .held = KEY_RIGHT };
    gb_player_update(&p, &level, &right);
    assert(p.request_x_fixed == 256);
    assert(p.request_y_fixed == 0);
    assert(p.x_fixed == 33 * 256);
    assert(p.y_fixed == 48 * 256);
    assert(p.x == 33 && p.y == 48);

    /* The next normal update clears a stale request on an unheld axis. */
    GbInput idle = {0};
    gb_player_update(&p, &level, &idle);
    assert(p.request_x_fixed == 0);
    assert(p.request_y_fixed == 0);
    assert(p.x_fixed == 33 * 256);

    /* LEFT takes precedence over RIGHT; UP takes precedence over DOWN. */
    GbInput all = { .held = KEY_LEFT | KEY_RIGHT | KEY_UP | KEY_DOWN };
    gb_player_update(&p, &level, &all);
    assert(p.request_x_fixed == -256);
    assert(p.request_y_fixed == -256);
    assert(p.x_fixed == 32 * 256);
    assert(p.y_fixed == 47 * 256);

    /* External pixel teleports are re-synchronized without destroying a
       legitimate subpixel remainder when the integer pixel is unchanged. */
    p.x = 40;
    p.y = 50;
    gb_player_update(&p, &level, &idle);
    assert(p.x_fixed == 40 * 256);
    assert(p.y_fixed == 50 * 256);

    p.x_fixed = 40 * 256 + 128;
    p.x = 40;
    gb_player_update(&p, &level, &idle);
    assert(p.x_fixed == 40 * 256 + 128);
    assert(p.x == 40);
    return 0;
}

"""

class PlayerCollisionRuntimeTests(unittest.TestCase):
    def test_double_corner_validation_restores_slide_but_keeps_primary_axis(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(DOUBLE_CORNER_HARNESS, encoding='utf-8')
            exe = td / 'double_corner_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], cwd=ROOT, check=True)

    def test_one_pixel_corner_corrections(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(CORNER_HARNESS, encoding='utf-8')
            exe = td / 'player_corner_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], cwd=ROOT, check=True)

    def test_diagonal_horizontal_corners_keep_x_motion(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(DIAGONAL_CORNER_HARNESS, encoding='utf-8')
            exe = td / 'diagonal_corner_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], cwd=ROOT, check=True)

    def test_normal_mode_uses_fixed8_cardinal_requests(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(NORMAL_MOVEMENT_HARNESS, encoding='utf-8')
            exe = td / 'normal_movement_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], cwd=ROOT, check=True)

    def test_fixed8_collision_contract(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'player_collision_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], cwd=ROOT, check=True)

if __name__ == '__main__':
    unittest.main()
