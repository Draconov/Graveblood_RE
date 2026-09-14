#!/usr/bin/env python3
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ForegroundRuntimeTests(unittest.TestCase):
    def test_host_runtime_matches_grass_and_leaf_state_machine(self):
        cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
        self.assertIsNotNone(cc)
        actors_c = ROOT / 'reconstruction/source/game/actors.c'
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text('''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef int8_t s8; typedef uint8_t u8; typedef int16_t s16; typedef uint16_t u16;
typedef int32_t s32; typedef uint32_t u32;
#define KEY_A 1
#endif
''', encoding='utf-8')
            harness = r'''
#include <assert.h>
#include <string.h>
#include <graveblood/actors.h>
#include <graveblood/assets.h>

const GbActorDescriptor gb_actor_descriptors[GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT] = {{0}};
const u16 gb_level_actor_indices[GB_ACTOR_LEVEL_REFERENCE_COUNT] = {0};
const GbActorLevelIndexSpan gb_actor_level_spans[11] = {{0}};
const u8 gb_player_physical_indices[11] = {0};
const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT] = { { {0}, 0 } };
const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS] = {{{0}}};

static int active_particles(const GbActorSystem* system)
{
    int count = 0;
    for(int i = 0; i < GB_LEAF_PARTICLE_CAPACITY; ++i) count += system->leaf_particles[i].active != 0;
    return count;
}

int main(void)
{
    GbActorSystem system;
    memset(&system, 0xCC, sizeof(system));
    gb_actor_system_init(&system);
    assert(system.count == 0);
    assert(system.leaf_emitter_cooldown == 12);
    assert(system.leaf_emitter_cycle == 0);
    assert(active_particles(&system) == 0);

    static const GbActorDescriptor leaves = { .actor_class = GB_ACTOR_LEAVES };
    system.count = 1;
    system.actors[0].descriptor = &leaves;
    system.actors[0].active = 1;

    for(int i = 0; i < 12; ++i) gb_actor_system_update_environment(&system, 2100, 0);
    assert(system.leaf_emitter_cooldown == 0);
    assert(active_particles(&system) == 0);

    gb_actor_system_update_environment(&system, 2100, 0);
    assert(system.leaf_emitter_cycle == 1);
    assert(system.leaf_emitter_cooldown == 23);
    assert(active_particles(&system) == 1);
    GbLeafParticle* p = &system.leaf_particles[0];
    /* The compatibility wrapper preserves the ROM manager's live-vector order:
       a freshly appended LeafParticle receives its first velocity step in the
       same update as the Leaves emitter that created it. */
    const s32 spawn_x = (2100 + 260 + 250) * 256;
    const s32 spawn_y = (-80 + 60) * 256;
    assert(p->fixed_x == spawn_x - 150);
    assert(p->fixed_y == spawn_y + 150);
    assert(p->velocity_x == -150);
    assert(p->velocity_y == 150);
    assert(p->frame == 0);
    assert(p->frame_countdown == 10);

    s32 old_x = p->fixed_x, old_y = p->fixed_y;
    gb_actor_system_update_environment(&system, 2100, 0);
    assert(p->fixed_x == old_x - 150);
    assert(p->fixed_y == old_y + 150);
    assert(system.leaf_emitter_cooldown == 22);

    for(int i = 0; i < 10; ++i) assert(gb_leaf_particle_frame_for_draw(p) == 0);
    assert(p->frame_countdown == 0);
    assert(gb_leaf_particle_frame_for_draw(p) == 1);
    assert(p->frame_countdown == 10);

    /* Camera <= 2000 advances the shared six-step cycle but emits nothing. */
    for(int i = 0; i < GB_LEAF_PARTICLE_CAPACITY; ++i) system.leaf_particles[i].active = 0;
    system.leaf_emitter_cooldown = 0;
    system.leaf_emitter_cycle = 5;
    gb_actor_system_update_environment(&system, 2000, 0);
    assert(system.leaf_emitter_cycle == 0);
    assert(system.leaf_emitter_cooldown == 23);
    assert(active_particles(&system) == 0);

    /* Scene load clears transient particles but preserves the original global emitter state. */
    system.leaf_particles[3].active = 1;
    system.leaf_emitter_cooldown = 7;
    system.leaf_emitter_cycle = 4;
    GbLevelAssets invalid = { .level_id = 255 };
    gb_actor_system_load(&system, &invalid);
    assert(active_particles(&system) == 0);
    assert(system.leaf_emitter_cooldown == 7);
    assert(system.leaf_emitter_cycle == 4);

    GbActor grass = {0};
    GbGrassDrawState draw = {0};
    static const GbActorDescriptor grass_desc = {
        .x = 100, .y = 120, .actor_class = GB_ACTOR_GRASS, .turn = 1, .legs_color = 0
    };
    grass.descriptor = &grass_desc;
    grass.fixed_x = 100 * GB_ACTOR_FIXED_ONE;
    grass.fixed_y = 120 * GB_ACTOR_FIXED_ONE;
    grass.active = 1;
    assert(gb_actor_grass_draw_state(&grass, 100, &draw) == 1);
    assert(draw.hflip == 1);
    assert(draw.priority == 1);
    assert(gb_actor_grass_draw_state(&grass, 120, &draw) == 1);
    assert(draw.priority == 2);

    static const GbActorDescriptor hidden_grass_desc = {
        .x = 100, .y = 120, .actor_class = GB_ACTOR_GRASS, .legs_color = 1
    };
    grass.descriptor = &hidden_grass_desc;
    assert(gb_actor_grass_draw_state(&grass, 100, &draw) == 0);
    return 0;
}
'''
            (td / 'foreground_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'foreground_test'
            cmd = [
                cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(actors_c), str(td / 'foreground_test.c'), '-o', str(exe),
            ]
            built = subprocess.run(cmd, text=True, capture_output=True)
            self.assertEqual(0, built.returncode, built.stdout + built.stderr)
            ran = subprocess.run([str(exe)], text=True, capture_output=True)
            self.assertEqual(0, ran.returncode, ran.stdout + ran.stderr)

    def test_video_contract_stages_grass_and_leaf_pixels_in_recovered_2d_obj_mapping(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        header = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        start = video.index('static void gb_video_configure_gameplay_display(void)')
        end = video.index('static void gb_video_configure_title_display(void)', start)
        gameplay_config = video[start:end]
        self.assertNotIn('OBJ_1D_MAP', gameplay_config)
        self.assertIn('REG_DISPCNT = MODE_0 | BG0_ON | BG1_ON | BG2_ON | BG3_ON | OBJ_ON;', gameplay_config)
        self.assertIn('gb_grass_obj_tiles', video)
        self.assertIn('gb_leaf_obj_frames', video)
        self.assertIn('gb_actor_grass_draw_state', video)
        self.assertIn('gb_leaf_particle_frame_for_draw', video)
        self.assertIn('const GbPlayer* player', header)

if __name__ == '__main__':
    unittest.main()
