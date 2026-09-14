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


def u16(data: bytes, addr: int) -> int:
    return struct.unpack_from('<H', data, addr - ROM_BASE)[0]


def u32(data: bytes, addr: int) -> int:
    return struct.unpack_from('<I', data, addr - ROM_BASE)[0]


def thumb_bl_target(data: bytes, addr: int) -> int:
    off = addr - ROM_BASE
    hi, lo = struct.unpack_from('<HH', data, off)
    if hi & 0xF800 != 0xF000 or lo & 0xF800 != 0xF800:
        raise AssertionError(f'not Thumb BL at {addr:#010x}: {hi:#06x} {lo:#06x}')
    upper = hi & 0x7FF
    if upper & 0x400:
        upper -= 0x800
    delta = (upper << 12) + ((lo & 0x7FF) << 1)
    return (addr + 4 + delta) & 0xFFFFFFFF


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

static const GbActorDescriptor test_descriptors[1] = {
    { .actor_class = GB_ACTOR_LEAVES, .rom_order = 0 }
};
const GbActorDescriptor gb_actor_descriptors[GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT] = {{0}};
const u16 gb_level_actor_indices[GB_ACTOR_LEVEL_REFERENCE_COUNT] = {0};
const GbActorLevelIndexSpan gb_actor_level_spans[11] = {
    {0, 1}, {0,0}, {0,0}, {0,0}, {0,0}, {0,0}, {0,0}, {0,0}, {0,0}, {0,0}, {0,0}
};
const u8 gb_player_physical_indices[11] = {1,0,0,0,0,0,0,0,0,0,0};
const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT] = { { {0}, 0 } };
const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS] = {{{0}}};

static int active_particles(const GbActorSystem* system)
{
    int count = 0;
    for(int i = 0; i < GB_LEAF_PARTICLE_CAPACITY; ++i)
        count += system->leaf_particles[i].active != 0;
    return count;
}

int main(void)
{
    GbActorSystem system;
    GbLevelAssets level;
    memset(&system, 0, sizeof(system));
    memset(&level, 0, sizeof(level));
    gb_actor_system_init(&system);
    level.level_id = 0;
    system.level = &level;
    system.count = 1;
    system.actors[0].descriptor = &test_descriptors[0];
    system.actors[0].story_overlay_index = GB_ACTOR_STORY_NONE;
    system.actors[0].active = 1;

    /* Force a spawn on the serialized Leaves slot. */
    system.leaf_emitter_cooldown = 0;
    system.leaf_emitter_cycle = 0;
    assert(gb_actor_system_update_physical_leaves_at(&system, 0, 2100, 100) == 1);
    assert(active_particles(&system) == 1);
    GbLeafParticle* p = &system.leaf_particles[0];
    const s32 spawn_x = (2100 + 260 + 250) * GB_LEAF_FIXED_ONE;
    const s32 spawn_y = (100 - 80 + 60) * GB_LEAF_FIXED_ONE;
    assert(p->fixed_x == spawn_x);
    assert(p->fixed_y == spawn_y);

    /* ROM manager appends the newborn to the active vector.  The vector end is
       reloaded after Leaves_update, so the newborn receives LeafParticle_update
       in this same update traversal, after all serialized objects. */
    gb_actor_system_update_leaf_particles(&system, 2100, 100);
    assert(p->fixed_x == spawn_x - 150);
    assert(p->fixed_y == spawn_y + 150);
    assert(gb_leaf_particle_pixel_x(p) == (s16)((spawn_x - 150) / 256));

    /* The combined compatibility helper must preserve the same spawn-then-update
       order; it must not revert to the old update-old-particles-then-spawn path. */
    memset(&system, 0, sizeof(system));
    gb_actor_system_init(&system);
    system.level = &level;
    system.count = 1;
    system.actors[0].descriptor = &test_descriptors[0];
    system.actors[0].story_overlay_index = GB_ACTOR_STORY_NONE;
    system.actors[0].active = 1;
    system.leaf_emitter_cooldown = 0;
    system.leaf_emitter_cycle = 0;
    gb_actor_system_update_environment(&system, 2100, 100);
    p = &system.leaf_particles[0];
    assert(p->active);
    assert(p->fixed_x == spawn_x - 150);
    assert(p->fixed_y == spawn_y + 150);
    return 0;
}
'''


class LeafParticleUpdateOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = ROM.read_bytes()

    def test_rom_appends_new_leaf_to_live_update_vector_and_reloads_end(self):
        d = self.rom
        # Leaves_update allocates 0x58 bytes, constructs a LeafParticle and
        # inserts it into the global object manager at 0x03000024.
        self.assertEqual(0x0800E0A4, thumb_bl_target(d, 0x08005FF2))
        self.assertEqual(0x0800B2BC, thumb_bl_target(d, 0x08006014))
        self.assertEqual(0x03000024, u32(d, 0x08006044))
        self.assertEqual(0x08000D00, thumb_bl_target(d, 0x0800602A))

        # LeafParticle_constructor initializes active/global byte +0x31 = 1 and
        # lifecycle +0x2C = 0, making it eligible for the active-vector pass.
        self.assertEqual(0x2531, u16(d, 0x0800B2C2))
        self.assertEqual(0x5544, u16(d, 0x0800B2D0))
        self.assertEqual(0x62C3, u16(d, 0x0800B2CA))

        # Object insertion passes manager+0x14 to vector::push_back 0x0800D7D0.
        self.assertEqual(0x3014, u16(d, 0x08000DE6))
        self.assertEqual(0x0800D7D0, thumb_bl_target(d, 0x08000DEE))
        self.assertEqual(0x601A, u16(d, 0x0800D7E0))  # *end = object
        self.assertEqual(0x3304, u16(d, 0x0800D7E6))  # end += sizeof(pointer)

        # Active-vector update calls vtable+0x0C then reloads both begin/end
        # before testing the next index. Therefore an appended newborn is
        # visited later in the same traversal instead of waiting a frame.
        self.assertEqual(0x68DB, u16(d, 0x0800160C))
        self.assertEqual(0x696B, u16(d, 0x08001622))
        self.assertEqual(0x69AA, u16(d, 0x08001624))
        self.assertEqual(0x3401, u16(d, 0x08001626))
        self.assertEqual(0x0800190E, thumb_bl_target(d, 0x08001610))

        # The particle update itself applies velocity immediately.
        self.assertEqual(0x4463, u16(d, 0x0800AB6A))
        self.assertEqual(0x188A, u16(d, 0x0800AB6C))
        self.assertEqual(0x6083, u16(d, 0x0800AB70))
        self.assertEqual(0x60C2, u16(d, 0x0800AB74))

    def test_serialized_leaves_are_physical_slot_zero_before_player(self):
        with (ROOT / 'data/actors.csv').open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        leaves = [r for r in rows if r.get('type') == 'leaves' and r.get('normal_level_indices')]
        self.assertEqual(3, len(leaves))
        levels = sorted(int(x) for r in leaves for x in r['normal_level_indices'].split(';'))
        self.assertEqual([0, 6, 9, 10], levels)

        # Those source lists all begin with Leaves; the generated Player ordinal
        # is later in every one of those levels.
        player_order = {}
        with (ROOT / 'data/player_npc_update_order.csv').open(newline='', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                player_order[int(r['level'])] = int(r['player_index'])
        self.assertTrue(all(player_order[level] > 0 for level in levels))

    def test_clean_room_exposes_split_emitter_and_particle_update_phases(self):
        actors_h = (ROOT / 'reconstruction/include/graveblood/actors.h').read_text(encoding='utf-8')
        self.assertIn('gb_actor_system_update_physical_leaves_at', actors_h)
        self.assertIn('gb_actor_system_update_leaf_particles', actors_h)

    def test_gameplay_scheduler_runs_leaves_at_physical_slot_and_particles_after_objects(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertNotIn('gb_actor_system_update_environment(&actors', game)

        pre_start = game.index('for(u8 physical_index = 0; physical_index < player_physical_index; ++physical_index)')
        pre_end = game.index('/* The latched ending flag', pre_start)
        pre = game[pre_start:pre_end]
        leaves = pre.index('gb_actor_system_update_physical_leaves_at(')
        fgtile = pre.index('gb_actor_system_update_physical_fgtile_at(')
        portal = pre.index('gb_portal_try_activate_physical_index(')
        self.assertLess(leaves, fgtile)
        self.assertLess(fgtile, portal)

        interaction = game.index('if(gb_story_ui_active(&story))')
        interaction_end = game.index("else\n        {", interaction)
        self.assertIn("gb_actor_system_update_physical_leaves_at(\n                &actors, 0, world.camera_x, world.camera_y);",
                      game[interaction:interaction_end])

        post_loop = game.index('for(u16 index = (u16)player_physical_index + 1;', interaction_end)
        particle_update = game.index('gb_actor_system_update_leaf_particles(', post_loop)
        sfx_drain = game.index('for(;;)', post_loop)
        self.assertLess(post_loop, particle_update)
        self.assertLess(particle_update, sfx_drain)

    def test_modal_entry_happens_at_player_slot_after_preplayer_leaves(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        # Wardrobe/PDA gates are inside Player_update in the ROM.  Level 0/6/9/10
        # all serialize Leaves at physical slot 0 before Player, so the clean-room
        # modal entry frame must run that pre-Player slot before either gate.
        overlay = game.index('gb_actor_system_update_overlays(&actors, &player, &input, &interaction);')
        pre_loop = game.index(
            'for(u8 physical_index = 0; physical_index < player_physical_index; ++physical_index)')
        leaves = game.index('gb_actor_system_update_physical_leaves_at(', pre_loop)
        wardrobe = game.index('input.held == (KEY_B | KEY_SELECT)')
        pda = game.index('(input.pressed & KEY_START)')
        self.assertLess(overlay, pre_loop)
        self.assertLess(pre_loop, leaves)
        self.assertLess(leaves, wardrobe)
        self.assertLess(wardrobe, pda)

    def test_host_runtime_newborn_gets_same_frame_particle_update(self):
        cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
        self.assertIsNotNone(cc)
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'leaf_order_test'
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
