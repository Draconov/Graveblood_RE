#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import generate_cfa_assets as gen

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', ROOT.parent / 'Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000
OBJ_TILES_SOURCE = 0x08310654


def _expected_faces(rom: bytes) -> bytes:
    bank_off = OBJ_TILES_SOURCE - ROM_BASE + 0x9800
    bank = rom[bank_off:bank_off + 0x800]
    if len(bank) != 0x800:
        raise AssertionError('reaction bank truncated')
    out = bytearray()
    for root in (0, 2, 4, 6, 8):
        for logical in (root, root + 1, root + 16, root + 17):
            off = logical * 64
            out.extend(bank[off:off + 64])
    return bytes(out)


class SocialReactionRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = ROM.read_bytes()

    def test_rom_loads_9800_face_bank_and_maps_subject_criticize_classes(self):
        def h(addr: int) -> int:
            return struct.unpack_from('<H', self.rom, addr - ROM_BASE)[0]
        def w(addr: int) -> int:
            return struct.unpack_from('<I', self.rom, addr - ROM_BASE)[0]

        # 0x08004C60: current graphics OBJ source + 0x9800 -> OBJ VRAM,
        # exactly 0x800 bytes.
        self.assertEqual((0x2398, 0x021B, 0x2280, 0x0112),
                         tuple(h(a) for a in (0x08004C70, 0x08004C72,
                                              0x08004C76, 0x08004C7C)))
        self.assertEqual(0x06010000, w(0x08004C90))

        # Pending-response countdown: quadrant 0 jumps to the direct class
        # renderer; quadrant 3 enters an inline 4-class transform.
        self.assertEqual((0x2E00, 0xD100),
                         tuple(h(a) for a in (0x08008CC2, 0x08008CC4)))
        self.assertEqual(0xE3E1, h(0x08008CC6))  # -> 0x0800948C
        self.assertEqual((0x2E03, 0xD000),
                         tuple(h(a) for a in (0x08008CC8, 0x08008CCA)))
        self.assertEqual((0x2204, 0x1AD2),
                         tuple(h(a) for a in (0x08008CE6, 0x08008CEA)))

        # Common/direct reaction geometry: topic class *2 logical root,
        # x = player-screen-x -20 + 40*facing, y = collision-top -37,
        # enum-3 16x16 submit.  Priority argument is zero on the CRITICIZE
        # duplicate body and inherited zero on the direct SUBJECT body.
        self.assertEqual((0x00AB, 0x195B, 0x00DB, 0x3814, 0x18C0,
                          0x0052, 0x3925, 0x2303),
                         tuple(h(a) for a in (0x080094C2, 0x080094C4,
                                              0x080094C6, 0x080094C8,
                                              0x080094CA, 0x080094CC,
                                              0x080094CE, 0x080094D2)))
        self.assertEqual((0x2300, 0x0052, 0x9300, 0x3925, 0x3303),
                         tuple(h(a) for a in (0x08008D12, 0x08008D14,
                                              0x08008D16, 0x08008D18,
                                              0x08008D1A)))

    def test_pack_social_reaction_faces_matches_9800_bank(self):
        expected = _expected_faces(self.rom)
        actual = gen.pack_social_reaction_faces(self.rom)
        self.assertEqual(5 * 256, len(expected))
        self.assertEqual(expected, actual)
        self.assertEqual('b7ce4f032b8db8ba93de7b28d50a9442656fb03c516f09cb9190f660c8010ff3',
                         hashlib.sha256(actual).hexdigest())

    def test_generator_exports_reaction_faces(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'reconstruction'
            gen.generate_all(ROOT, out, ROM)
            unit = (out / 'data/social_selector_assets.c').read_text(encoding='utf-8')
            header = (out / 'include/graveblood/assets.h').read_text(encoding='utf-8')
            self.assertIn('gb_social_reaction_obj_faces', unit)
            self.assertIn('GB_SOCIAL_REACTION_FACE_COUNT = 5', header)
            self.assertIn('GB_SOCIAL_REACTION_FACE_HALFWORDS = 128', header)
            self.assertIn('extern const u16 gb_social_reaction_obj_faces', header)

    def test_post_delay_draws_subject_and_criticize_reactions_only(self):
        gba_h = r'''
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
'''
        harness = r'''
#include <assert.h>
#include <graveblood/video.h>

volatile u16 gb_test_vcount, gb_test_dispcnt, gb_test_bgctrl[4];
volatile GbTestBgOffset gb_test_bg_offset[4];
volatile u16 gb_test_bg_colors[256], gb_test_obj_colors[256], gb_test_oam[512];
volatile u16 gb_test_vram[0x18000 / 2];

const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * GB_PLAYER_FRAME_HALFWORDS] = {0};
const u16 gb_player_bicycle_obj_frames[GB_PLAYER_BICYCLE_FRAME_COUNT * GB_PLAYER_BICYCLE_FRAME_HALFWORDS] = {0};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {0};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {0};
u8 gb_player_frame_index(const GbPlayer* p) { (void)p; return 0; }

static int find_reaction(int x, int y, int attr2)
{
    for(int i = 0; i < 9; ++i)
    {
        if((gb_test_oam[i * 4] & 0x00FF) == (u16)y &&
           (gb_test_oam[i * 4 + 1] & 0x01FF) == (u16)x &&
           gb_test_oam[i * 4 + 2] == (u16)attr2)
        {
            return 1;
        }
    }
    return 0;
}

static void clear_oam(void)
{
    for(int i = 0; i < 512; ++i) gb_test_oam[i] = 0;
}

int main(void)
{
    GbPlayer player = {0};
    GbStoryRuntime story = {0};
    player.x = 100; player.y = 100;
    player.x_fixed = 100 << 8; player.y_fixed = 100 << 8;
    player.collision_height_fixed = 0x1000;
    player.facing_right = 1;
    story.social.state = GB_SOCIAL_POST_DELAY;
    story.social.profile_selector = 0;
    story.social.topic_index = 2;
    story.social.selected_quadrant = 0;
    story.state.social_profiles[0].topic_class[2] = 3;

    clear_oam();
    gb_video_draw_player_state(&player, &story, 10, 20);
    /* x = 100-10-20+40 = 110; y = ((100<<8)-0x1000+1)>>8 -20-37 = 27.
       Class 3 => logical root 6 => ATTR2 8bpp tile index 12, priority 0. */
    assert(find_reaction(110, 27, 12));

    /* CRITICIZE mirrors class 1 to 4-1=3, and facing left uses x-20. */
    story.social.selected_quadrant = 3;
    story.state.social_profiles[0].topic_class[2] = 1;
    player.facing_right = 0;
    clear_oam();
    gb_video_draw_player_state(&player, &story, 10, 20);
    assert(find_reaction(70, 27, 12));

    /* Ask-about has no delayed reaction OAM. */
    story.social.selected_quadrant = 1;
    clear_oam();
    gb_video_draw_player_state(&player, &story, 10, 20);
    assert(!find_reaction(70, 27, 12));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'reaction.c').write_text(harness, encoding='utf-8')
            exe = td / 'reaction'
            proc = subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/video.c'),
                str(ROOT / 'reconstruction/data/social_selector_assets.c'),
                str(td / 'reaction.c'), '-Wl,--gc-sections', '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr + run.stdout)


if __name__ == '__main__':
    unittest.main()
