#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000


class GameplayOamInsertionOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM.read_bytes()

    def test_rom_oam_submit_allocates_monotonic_oam_indices(self):
        # 0x0800A958 obtains the shared OAM submission counter from +0x10,
        # writes the 8-byte entry at 0x07000000 + counter*8, then increments
        # the same counter at 0x0800A98C..0x0800A994.
        seq = tuple(struct.unpack_from('<H', self.data, addr - ROM_BASE)[0]
                    for addr in range(0x0800A958, 0x0800A996, 2))
        self.assertEqual(seq, (
            0x18EB, 0x46B1, 0x6936, 0x691D, 0x0189, 0x4466, 0x4339,
            0x00F6, 0x4329, 0x8031, 0x21C0, 0x6A1B, 0x05C0, 0x0DC0,
            0x4318, 0x4B0A, 0x0052, 0x401A, 0x9B07, 0x0109, 0x029B,
            0x400B, 0x431A, 0x464B, 0x691B, 0x4320, 0x1C5C, 0x464B,
            0x8070, 0x80B2, 0x611C,
        ))

    def test_generated_runtime_exposes_player_physical_insertion_index(self):
        header = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        actor_data = (ROOT / 'reconstruction/data/actor_data.c').read_text(encoding='utf-8')
        self.assertIn('gb_player_physical_indices[11]', header,
                      'RED: runtime has no generated Player insertion-index table yet')
        self.assertIn('gb_player_physical_indices[11]', actor_data)

    def test_gameplay_uses_one_insertion_order_oam_pass(self):
        header = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('gb_video_draw_gameplay_objects', header,
                      'RED: unified insertion-order gameplay draw API is missing')
        self.assertIn('gb_video_draw_gameplay_objects(actors, player, story', game)
        self.assertIn('gb_video_draw_gameplay_objects(&actors, &player, &story', game)


    def test_unified_gameplay_draw_places_overlay_before_player_and_physical_npc_after(self):
        gba_h = r"""
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;
typedef struct { volatile u16 x; volatile u16 y; } GbTestBgOffset;
extern volatile u16 gb_test_vcount, gb_test_dispcnt, gb_test_bgctrl[4];
extern volatile GbTestBgOffset gb_test_bg_offset[4];
extern volatile u16 gb_test_bg_colors[256], gb_test_obj_colors[256], gb_test_oam[512];
extern volatile u16 gb_test_vram[0x18000 / 2];
#define REG_VCOUNT gb_test_vcount
#define REG_DISPCNT gb_test_dispcnt
#define BGCTRL gb_test_bgctrl
#define BG_OFFSET gb_test_bg_offset
#define BG_COLORS gb_test_bg_colors
#define OBJ_COLORS gb_test_obj_colors
#define OAM gb_test_oam
#define MAP_BASE_ADR(n) ((void*)(gb_test_vram + ((n) * 0x800 / 2)))
#define CHAR_BASE_ADR(n) ((void*)(gb_test_vram + ((n) * 0x4000 / 2)))
#define SPR_VRAM(n) ((void*)(gb_test_vram + 0x10000 / 2))
#define MODE_0 0u
#define BG0_ON (1u << 8)
#define BG1_ON (1u << 9)
#define BG2_ON (1u << 10)
#define BG3_ON (1u << 11)
#define OBJ_ON (1u << 12)
#define OBJ_1D_MAP (1u << 6)
#define BG_SIZE_0 0u
#define BG_256_COLOR (1u << 7)
#define CHAR_BASE(n) ((u16)((n) << 2))
#define SCREEN_BASE(n) ((u16)((n) << 8))
#define BG_PRIORITY(n) ((u16)(n))
#endif
"""
        harness = r"""
#include <assert.h>
#include <graveblood/video.h>

volatile u16 gb_test_vcount, gb_test_dispcnt, gb_test_bgctrl[4];
volatile GbTestBgOffset gb_test_bg_offset[4];
volatile u16 gb_test_bg_colors[256], gb_test_obj_colors[256], gb_test_oam[512];
volatile u16 gb_test_vram[0x18000 / 2];

const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT] = { {24, 0} };
const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_MAX_FRAMES * GB_ACTOR_FRAME_HALFWORDS] = {0};
const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = {0};
const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {0};
const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * GB_PLAYER_FRAME_HALFWORDS] = {0};
const u16 gb_player_bicycle_obj_frames[GB_PLAYER_BICYCLE_FRAME_COUNT * GB_PLAYER_BICYCLE_FRAME_HALFWORDS] = {0};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {0};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {0};
const u8 gb_player_physical_indices[11] = {8,2,0,0,0,0,8,0,4,2,1};

int gb_actor_npc_should_draw(const GbActor* actor) { (void)actor; return 1; }
u8 gb_actor_npc_frame_for_draw(GbActor* actor) { (void)actor; return 1; }
int gb_actor_grass_draw_state(const GbActor* actor, s16 y, GbGrassDrawState* out)
{ (void)actor; (void)y; (void)out; return 0; }
u8 gb_leaf_particle_frame_for_draw(GbLeafParticle* p) { (void)p; return 0; }
s16 gb_leaf_particle_pixel_x(const GbLeafParticle* p) { (void)p; return 0; }
s16 gb_leaf_particle_pixel_y(const GbLeafParticle* p) { (void)p; return 0; }
s16 gb_actor_pixel_x(const GbActor* a) { return (s16)(a->fixed_x / 256); }
s16 gb_actor_pixel_y(const GbActor* a) { return (s16)(a->fixed_y / 256); }
u8 gb_player_frame_index(const GbPlayer* p) { (void)p; return 0; }

static void init_npc(GbActor* actor, const GbActorDescriptor* desc, int x, u8 overlay)
{
    actor->descriptor = desc;
    actor->fixed_x = x * 256;
    actor->fixed_y = 80 * 256;
    actor->visual_legs_color = 24;
    actor->active = 1;
    actor->story_overlay_index = overlay;
}

int main(void)
{
    const GbActorDescriptor desc = {
        .actor_class = GB_ACTOR_NPC, .legs_color = 24, .subtype = 0, .num = 1, .setglobal = 0
    };
    GbLevelAssets level = { .level_id = 2 };
    GbActorSystem system = {0};
    GbPlayer player = {0};
    GbStoryRuntime story = {0};
    system.level = &level;
    system.count = 2;
    init_npc(&system.actors[0], &desc, 50, 0); /* inserted story overlay */
    init_npc(&system.actors[1], &desc, 150, GB_ACTOR_STORY_NONE); /* post-Player physical NPC */
    player.x = 100; player.y = 80;

    gb_video_draw_gameplay_objects(&system, &player, &story, 0, 0);

    /* Equal-priority OAM order must follow insertion traversal: overlay first,
       Player second, physical NPC third. Each ordinary NPC/Player consumes two cells. */
    assert((gb_test_oam[0 * 4 + 1] & 0x01FF) == 50);
    assert((gb_test_oam[1 * 4 + 1] & 0x01FF) == 50);
    assert((gb_test_oam[2 * 4 + 1] & 0x01FF) == 100);
    assert((gb_test_oam[3 * 4 + 1] & 0x01FF) == 100);
    assert((gb_test_oam[4 * 4 + 1] & 0x01FF) == 150);
    assert((gb_test_oam[5 * 4 + 1] & 0x01FF) == 150);
    assert((gb_test_oam[0 * 4 + 2] & 0x0C00) == (2u << 10));
    assert((gb_test_oam[2 * 4 + 2] & 0x0C00) == (2u << 10));
    assert((gb_test_oam[4 * 4 + 2] & 0x0C00) == (2u << 10));
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'oam_order.c').write_text(harness, encoding='utf-8')
            exe = td / 'oam_order'
            proc = subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/video.c'),
                str(td / 'oam_order.c'), '-Wl,--gc-sections', '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_semantic_export_binds_oam_allocator_to_player_insertion_indices(self):
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        from extract_extended_semantics import extract_gameplay_oam_insertion_order
        rows = extract_gameplay_oam_insertion_order(self.data)
        player_rows = [row for row in rows if row['fact'] == 'player_physical_index']
        self.assertEqual([int(row['value']) for row in player_rows],
                         [8, 2, 0, 0, 0, 0, 8, 0, 4, 2, 1])
        self.assertEqual(rows[0]['fact'], 'oam_allocator')
        self.assertIn('monotonic', rows[0]['value'])
        self.assertEqual(rows[1]['fact'], 'story_overlay_prefix')
        csv_text = (ROOT / 'data/gameplay_oam_insertion_order.csv').read_text(encoding='utf-8')
        self.assertIn('player_physical_index', csv_text)


if __name__ == '__main__':
    unittest.main()
