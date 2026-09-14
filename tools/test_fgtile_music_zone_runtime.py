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
FADE_TABLE_ROM = 0x08A8E370


def u16(data: bytes, addr: int) -> int:
    return struct.unpack_from('<H', data, addr - ROM_BASE)[0]


EXPECTED_FADE = [
    142, 140, 138, 136, 134, 132, 130, 128, 126, 124,
    122, 120, 118, 116, 114, 112, 110, 108, 106, 104,
    102, 100, 98, 96, 94, 92, 90, 88, 86, 84,
    82, 80, 78, 76, 74, 72, 70, 68, 66, 64,
    62, 60, 58, 56, 54, 52, 50, 48, 46, 44,
    42, 40, 38, 36, 34, 32, 30, 28, 26, 24,
    22, 20, 18, 16, 14, 12, 10, 8, 6, 4,
    2, 0, 0, 0, 0,
]

GBA_H = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef int8_t s8; typedef uint8_t u8; typedef int16_t s16; typedef uint16_t u16;
typedef int32_t s32; typedef uint32_t u32;
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
const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT] = {
    { .actor = {0}, .overlay_index = 0 }
};
const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS] = {{{0}}};

static void setup_zone(GbActorSystem* system, GbLevelAssets* level, GbActorDescriptor* desc)
{
    memset(system, 0, sizeof(*system));
    memset(level, 0, sizeof(*level));
    memset(desc, 0, sizeof(*desc));
    level->level_id = 0;
    desc->x = 100;
    desc->y = 200;
    desc->width = 4;
    desc->height = 40;
    desc->actor_class = GB_ACTOR_FGTILE;
    desc->port_to = 33;
    desc->treetype = 1;
    desc->turn = 2;
    system->level = level;
    system->count = 1;
    system->actors[0].descriptor = desc;
    system->actors[0].story_overlay_index = GB_ACTOR_STORY_NONE;
    system->actors[0].fixed_x = (s32)desc->x << GB_ACTOR_FIXED_SHIFT;
    system->actors[0].fixed_y = (s32)desc->y << GB_ACTOR_FIXED_SHIFT;
    system->actors[0].active = 1;
}

static void place_player(GbPlayer* p, s16 x, s16 y)
{
    gb_player_spawn(p, x, y);
}

int main(void)
{
    GbActorSystem system;
    GbLevelAssets level;
    GbActorDescriptor desc;
    GbPlayer p;

    setup_zone(&system, &level, &desc);
    place_player(&p, 92, 192); /* probe=(92,208) = first point of 2x40 strip */
    gb_player_music_reset(&p, 0);
    assert(gb_actor_system_update_physical_fgtile_music_at(&system, &p, 0) == 1);
    assert(p.music_selector_desired == 1);

    /* Staying on the strip repeats the original toggle rule: desired==treetype
       writes zero instead of inventing an edge-trigger latch. */
    assert(gb_actor_system_update_physical_fgtile_music_at(&system, &p, 0) == 1);
    assert(p.music_selector_desired == 0);

    /* Outside the 2x40 contact strip no selector write occurs. */
    place_player(&p, 94, 192);
    gb_player_music_reset(&p, 0);
    assert(gb_actor_system_update_physical_fgtile_music_at(&system, &p, 0) == 0);
    assert(p.music_selector_desired == 0);

    /* Wrong controller metadata must not alias the music-zone path. */
    place_player(&p, 92, 192);
    desc.turn = 1;
    assert(gb_actor_system_update_physical_fgtile_music_at(&system, &p, 0) == 0);
    desc.turn = 2; desc.port_to = 0;
    assert(gb_actor_system_update_physical_fgtile_music_at(&system, &p, 0) == 0);
    desc.port_to = 33; desc.treetype = 20;
    assert(gb_actor_system_update_physical_fgtile_music_at(&system, &p, 0) == 0);

    /* Player music selector fade: mismatch starts with table[1] == 140 and
       replacement happens on the 75th Player update at full 0x90 volume. */
    gb_player_music_reset(&p, 0);
    p.music_selector_desired = 1;
    GbPlayerMusicAction action = gb_player_music_tick(&p);
    assert(action.set_volume == 1);
    assert(action.volume == 140);
    assert(action.replace_music == 0);
    assert(p.music_fade_counter == 1);
    assert(p.music_selector_applied == 0);

    for(int i = 1; i < 74; ++i)
    {
        action = gb_player_music_tick(&p);
    }
    assert(p.music_fade_counter == 74);
    assert(action.set_volume == 1);
    assert(action.volume == 0);
    assert(action.replace_music == 0);

    action = gb_player_music_tick(&p);
    assert(action.replace_music == 1);
    assert(action.selector == 1);
    assert(action.volume == 0x90);
    assert(p.music_selector_applied == 1);
    assert(p.music_fade_counter == 0);

    /* ROM quirk: if desired flips back to applied while a fade is partially
       complete, the counter is retained rather than rewound. */
    gb_player_music_reset(&p, 0);
    p.music_selector_desired = 1;
    (void)gb_player_music_tick(&p);
    (void)gb_player_music_tick(&p);
    assert(p.music_fade_counter == 2);
    p.music_selector_desired = 0;
    action = gb_player_music_tick(&p);
    assert(action.set_volume == 0 && action.replace_music == 0);
    assert(p.music_fade_counter == 2);
    p.music_selector_desired = 1;
    action = gb_player_music_tick(&p);
    assert(p.music_fade_counter == 3);
    assert(action.volume == 136);

    return 0;
}
'''


class FgtileMusicZoneRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = ROM.read_bytes()

    def test_rom_turn2_branch_targets_player_desired_selector(self):
        d = self.rom
        # turn==2 dispatch into the 2x40 controller branch.
        self.assertEqual(0x2B02, u16(d, 0x08003BEC))
        self.assertEqual(0xD000, u16(d, 0x08003BEE))
        # The branch builds Player+0x1CC as 0x8D + 0x40 + 0xFF.
        self.assertEqual(0x338D, u16(d, 0x08003C1A))
        self.assertEqual(0x3340, u16(d, 0x08003C1E))
        self.assertEqual(0x33FF, u16(d, 0x08003C20))
        # On contact it compares desired selector with treetype and either writes
        # treetype or zero to that Player field.
        self.assertEqual(0x589B, u16(d, 0x08003CFE))
        self.assertEqual(0x459A, u16(d, 0x08003D00))
        self.assertEqual(0x5098, u16(d, 0x08003D08))
        self.assertEqual(0x5098, u16(d, 0x08003D20))

    def test_public_demo_serializes_exact_turn2_music_zones(self):
        with (ROOT / 'data/actors.csv').open(newline='', encoding='utf-8') as f:
            rows = [r for r in csv.DictReader(f)
                    if r.get('type') == 'fgtile' and r.get('turn') == '2']
        got = [(r['rom_addr'], r['normal_level_indices'], r['x'], r['y'],
                r['width'], r['height'], r['treetype'], r['portTo']) for r in rows]
        self.assertEqual([
            ('0x0841DAFC', '5', '722', '458.667', '4', '40', '1', ''),
            ('0x084E7724', '2', '722', '458.667', '4', '40', '1', ''),
            ('0x0853B120', '0;6', '654', '885.334', '4', '40', '1', ''),
        ], got)

    def test_music_zone_physical_ordinals_split_around_player(self):
        counts = {level: 0 for level in range(11)}
        zone_indices = {}
        with (ROOT / 'data/actors.csv').open(newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                refs = [int(value) for value in row.get('normal_level_indices', '').split(';') if value]
                for level in refs:
                    index = counts[level]
                    if row.get('type') == 'fgtile' and row.get('turn') == '2':
                        zone_indices[level] = index
                    counts[level] += 1
        self.assertEqual({0: 3, 2: 4, 5: 4, 6: 3}, zone_indices)

        # Generated Player ordinals prove Levels 0/6 run the zone before Player,
        # while Levels 2/5 run it after Player.
        player_indices = [8, 2, 0, 0, 0, 0, 8, 0, 4, 2, 1]
        self.assertLess(zone_indices[0], player_indices[0])
        self.assertLess(zone_indices[6], player_indices[6])
        self.assertGreater(zone_indices[2], player_indices[2])
        self.assertGreater(zone_indices[5], player_indices[5])

    def test_rom_music_fade_table_and_selector_offsets_are_exact(self):
        actual = list(struct.unpack_from('<75I', self.rom, FADE_TABLE_ROM - ROM_BASE))
        self.assertEqual(EXPECTED_FADE, actual)
        # desired=Player+0x1CC, applied=+0x1D0 and threshold 75.
        self.assertEqual(0x22E6, u16(self.rom, 0x08008328))
        self.assertEqual(0x0052, u16(self.rom, 0x0800832A))
        self.assertEqual(0x58A1, u16(self.rom, 0x0800832C))
        self.assertEqual(0x3204, u16(self.rom, 0x0800832E))
        self.assertEqual(0x58A2, u16(self.rom, 0x08008330))
        self.assertEqual(0x2B4B, u16(self.rom, 0x08008A82))

    def test_clean_room_exposes_music_zone_and_player_music_state(self):
        actor_h = (ROOT / 'reconstruction/include/graveblood/actor.h').read_text(encoding='utf-8')
        actors_h = (ROOT / 'reconstruction/include/graveblood/actors.h').read_text(encoding='utf-8')
        audio_h = (ROOT / 'reconstruction/include/graveblood/audio.h').read_text(encoding='utf-8')
        self.assertIn('music_selector_desired', actor_h)
        self.assertIn('music_selector_applied', actor_h)
        self.assertIn('music_fade_counter', actor_h)
        self.assertIn('GbPlayerMusicAction', actor_h)
        self.assertIn('gb_player_music_reset', actor_h)
        self.assertIn('gb_player_music_tick', actor_h)
        self.assertIn('gb_actor_system_update_physical_fgtile_music_at', actors_h)
        self.assertIn('gb_audio_set_music_volume', audio_h)

    def test_host_runtime_reproduces_zone_toggle_and_75_update_fade(self):
        cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
        self.assertIsNotNone(cc)
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'fgtile_music_test'
            cmd = [
                cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(ROOT / 'reconstruction/source/game/actors.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ]
            built = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, built.returncode, built.stdout + built.stderr)
            ran = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, ran.returncode, ran.stdout + ran.stderr)

    def test_game_scheduler_places_music_zones_at_physical_slots_and_fade_at_player(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        pre = game.index('for(u8 physical_index = 0; physical_index < player_physical_index; ++physical_index)')
        player = game.index('gb_player_update(&player, world.assets, &input);', pre)
        post = game.index('for(u16 index = (u16)player_physical_index + 1;', player)
        pre_music = game.index('gb_actor_system_update_physical_fgtile_music_at(', pre)
        wardrobe = game.index('input.held == (KEY_B | KEY_SELECT)', pre)
        music_tick = game.index('gb_player_music_tick(&player)', wardrobe)
        pda = game.index('(input.pressed & KEY_START)', music_tick)
        post_music = game.index('gb_actor_system_update_physical_fgtile_music_at(', post)
        self.assertLess(pre_music, wardrobe)
        self.assertLess(wardrobe, music_tick)
        self.assertLess(music_tick, pda)
        self.assertLess(pda, player)
        self.assertGreater(post_music, player)

        interaction = game.index('if(gb_story_ui_active(&story))')
        interaction_end = game.index("else\n        {", interaction)
        self.assertIn('gb_player_music_tick(&player)', game[interaction:interaction_end])


if __name__ == '__main__':
    unittest.main()
