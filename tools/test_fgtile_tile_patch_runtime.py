#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000
INIT_ROM_START = 0x08A8D738
INIT_RAM_START = 0x03000788
FGTILE_PATCH_TABLE_RAM = 0x03000884

EXPECTED_PATCHES = [
    (906, 2710, 176), (906, 1680, 176),
    (906, 2710, 176), (906, 3060, 176),
    (184, 3594, 26), (184, 3412, 26),
    (456, 3466, 64), (456, 3648, 64),
    (906, 1680, 176), (906, 3774, 176),
    (584, 4126, 76), (584, 4430, 76),
    (584, 4430, 76), (584, 4278, 76),
    (742, 2084, 132), (742, 2354, 132),
    (736, 2348, 135), (736, 1814, 135),
]

GBA_H = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef int8_t s8; typedef uint8_t u8; typedef int16_t s16; typedef uint16_t u16;
typedef int32_t s32; typedef uint32_t u32;
#define KEY_A 1u
#endif
'''

HARNESS = r'''
#include <assert.h>
#include <string.h>
#include <graveblood/actors.h>
#include <graveblood/assets.h>

const GbActorDescriptor gb_actor_descriptors[GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT] = {{0}};
const u16 gb_level_actor_indices[GB_ACTOR_LEVEL_REFERENCE_COUNT] = {0};
const GbActorLevelIndexSpan gb_actor_level_spans[11] = {
    {0, 1}, {0, 0}, {0, 0}, {0, 0}, {0, 0}, {0, 0},
    {0, 0}, {0, 0}, {0, 0}, {0, 0}, {0, 0}
};
const u8 gb_player_physical_indices[11] = {1,0,0,0,0,0,0,0,0,0,0};
const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT] = { { .actor = {0}, .overlay_index = 0 } };
const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS] = {{{0}}};

static void setup(GbActorSystem* system, GbLevelAssets* level,
                  GbActorDescriptor* desc, s16 x, s16 y, s16 treetype, u8 turn)
{
    memset(system, 0, sizeof(*system));
    memset(level, 0, sizeof(*level));
    memset(desc, 0, sizeof(*desc));
    level->level_id = 0;
    desc->x = x;
    desc->y = y;
    desc->actor_class = GB_ACTOR_FGTILE;
    desc->port_to = 33;
    desc->treetype = treetype;
    desc->turn = turn;
    system->level = level;
    system->count = 1;
    system->actors[0].descriptor = desc;
    system->actors[0].story_overlay_index = GB_ACTOR_STORY_NONE;
    system->actors[0].fixed_x = (s32)x << GB_ACTOR_FIXED_SHIFT;
    system->actors[0].fixed_y = (s32)y << GB_ACTOR_FIXED_SHIFT;
    system->actors[0].active = 1;
}

static GbPlayer player_at(s16 x, s16 y)
{
    GbPlayer p;
    memset(&p, 0, sizeof(p));
    p.x = x; p.y = y;
    p.x_fixed = (s32)x << GB_ACTOR_FIXED_SHIFT;
    p.y_fixed = (s32)y << GB_ACTOR_FIXED_SHIFT;
    return p;
}

int main(void)
{
    GbActorSystem system;
    GbLevelAssets level;
    GbActorDescriptor desc;
    u8 patch = 0xFF;

    /* turn=0 is the recovered 2x90 vertical strip.  The first column is
       processed in the current update and selects the base patch. */
    setup(&system, &level, &desc, 100, 200, 4, 0);
    GbPlayer p = player_at(92, 200); /* probe=(92,216), first strip half */
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 1);
    assert(patch == 4);
    assert(system.actors[0].fgtile_x_offset == 0);

    /* The second column is latched at the end of the scan and fires on the
       next object update, selecting treetype+1 and shifting the strip -16. */
    setup(&system, &level, &desc, 100, 200, 4, 0);
    p = player_at(93, 200);
    patch = 0xFF;
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 0);
    assert(system.actors[0].fgtile_pending == 1);
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 1);
    assert(patch == 5);
    assert(system.actors[0].fgtile_x_offset == -16);
    assert(system.actors[0].fgtile_pending == 0);

    /* The -16 hysteresis strip selects the base patch when crossed back. */
    p = player_at(76, 200);
    patch = 0xFF;
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 1);
    assert(patch == 4);
    assert(system.actors[0].fgtile_x_offset == 0);

    /* turn=1 is the recovered 90x2 horizontal strip.  Crossing the initial
       lower line selects +1 and shifts Y by -16; crossing back selects base. */
    setup(&system, &level, &desc, 100, 200, 6, 1);
    p = player_at(100, 192); /* probe y=208, first 45 columns */
    patch = 0xFF;
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 1);
    assert(patch == 7);
    assert(system.actors[0].fgtile_y_offset == -16);
    p = player_at(100, 176); /* probe y=192, shifted first line */
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 1);
    assert(patch == 6);
    assert(system.actors[0].fgtile_y_offset == 0);

    /* Right half of the 90x2 scan carries the one-update latch too. */
    setup(&system, &level, &desc, 100, 200, 8, 1);
    p = player_at(150, 192); /* x=150 is in second 45-column half */
    patch = 0xFF;
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 0);
    assert(system.actors[0].fgtile_pending == 1);
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 1);
    assert(patch == 9);

    /* Parser-default/nonvisual treetype=1, turn=2 metadata, and generic
       portals are not ordinary tile-patch controllers. */
    setup(&system, &level, &desc, 100, 200, 1, 0);
    p = player_at(92, 200);
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 0);
    desc.treetype = 4; desc.turn = 2;
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 0);
    desc.turn = 0; desc.port_to = 0;
    assert(gb_actor_system_update_physical_fgtile_at(&system, &p, 0, &patch) == 0);
    return 0;
}
'''


class FgtileTilePatchRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = ROM.read_bytes()

    def test_rom_initialized_patch_table_is_exact(self):
        table_rom = INIT_ROM_START + (FGTILE_PATCH_TABLE_RAM - INIT_RAM_START)
        actual = [
            struct.unpack_from('<III', self.rom, table_rom - ROM_BASE + i * 12)
            for i in range(len(EXPECTED_PATCHES))
        ]
        self.assertEqual(EXPECTED_PATCHES, actual)
        # The active patch source window is descriptor-relative and extends
        # beyond the initial 0xD800-byte background upload.
        self.assertEqual(0xD200, min(src * 32 for _, src, _ in actual))
        self.assertEqual(0x23CC0, max(src * 32 + count * 64 for _, src, count in actual))

    def test_serialized_public_demo_has_active_turn01_patch_controllers_but_no_turn3(self):
        with (ROOT / 'data/actors.csv').open(newline='', encoding='utf-8') as f:
            rows = [r for r in csv.DictReader(f)
                    if r.get('normal_level_indices') and r.get('type') == 'fgtile']
        turns = [int(float(r['turn'])) if r.get('turn') else 0 for r in rows]
        self.assertNotIn(3, turns)
        active = []
        for r in rows:
            # XML parser default is portTo=33 and treetype=1 when omitted.
            port_to = int(float(r['portTo'])) if r.get('portTo') else 33
            treetype = int(float(r['treetype'])) if r.get('treetype') else 1
            turn = int(float(r['turn'])) if r.get('turn') else 0
            if port_to == 33 and turn in (0, 1) and treetype not in (1, 20):
                active.append((int(r['normal_level_indices'].split(';')[0]), turn, treetype))
        self.assertTrue(active)
        self.assertTrue(all(0 <= treetype + 1 < len(EXPECTED_PATCHES) for _, _, treetype in active))
        self.assertTrue(all(treetype % 2 == 0 for _, _, treetype in active))

    def test_clean_room_exposes_treetype_and_physical_fgtile_patch_runtime(self):
        assets_h = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        actors_h = (ROOT / 'reconstruction/include/graveblood/actors.h').read_text(encoding='utf-8')
        video_h = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        self.assertIn('s16 treetype;', assets_h)
        self.assertIn('gb_actor_system_update_physical_fgtile_at', actors_h)
        self.assertIn('gb_video_apply_fgtile_patch', video_h)

    def test_host_runtime_reproduces_strip_latch_and_hysteresis(self):
        cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
        self.assertIsNotNone(cc)
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'fgtile_patch_test'
            cmd = [
                cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/actors.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ]
            built = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, built.returncode, built.stdout + built.stderr)
            ran = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, ran.returncode, ran.stdout + ran.stderr)


if __name__ == '__main__':
    unittest.main()
