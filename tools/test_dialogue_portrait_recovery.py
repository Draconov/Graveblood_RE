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


def thumb_bl_target(data: bytes, addr: int) -> int | None:
    off = addr - ROM_BASE
    hi, lo = struct.unpack_from('<HH', data, off)
    if hi & 0xF800 != 0xF000 or lo & 0xF800 != 0xF800:
        return None
    upper = hi & 0x07FF
    if upper & 0x0400:
        upper -= 0x0800
    disp = (upper << 12) | ((lo & 0x07FF) << 1)
    return (addr + 4 + disp) & 0xFFFFFFFF


class DialoguePortraitRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM.read_bytes()

    def test_reference_text_record_falls_through_to_indexed_portrait_bank_loader(self):
        # Normal dialogue reads record+0x8C into r0 then opcode 0 reaches 0x08005720.
        self.assertEqual(struct.unpack_from('<HH', self.data, 0x08002F88 - ROM_BASE),
                         (0x218C, 0x5858))
        self.assertEqual(thumb_bl_target(self.data, 0x08002F92), 0x08005720)
        # State-4 text records use the same live bank loader.
        self.assertEqual(thumb_bl_target(self.data, 0x08003206), 0x08005720)

    def test_reference_portrait_loader_uses_five_0x1800_stride_banks(self):
        # 0x08005720 computes argument * 3 * 0x800 and copies the two
        # hardware-visible graphics spans into OBJ VRAM.
        self.assertEqual(struct.unpack_from('<I', self.data, 0x08005750 - ROM_BASE)[0],
                         0x086493F0)
        self.assertEqual(struct.unpack_from('<I', self.data, 0x08005754 - ROM_BASE)[0],
                         0x06010000)
        self.assertEqual(struct.unpack_from('<I', self.data, 0x08005758 - ROM_BASE)[0],
                         0x06011400)
        seq = struct.unpack_from('<7H', self.data, 0x08005720 - ROM_BASE)
        self.assertEqual(seq[:6], (0x2290, 0xB570, 0x0044, 0x4D0A, 0x1824, 0x02E4))

    def test_reference_right_side_compositor_submits_28_cells(self):
        submit_sites = (0x080080E6, 0x08008128, 0x08008162, 0x0800818C)
        for site in submit_sites:
            self.assertEqual(thumb_bl_target(self.data, site), 0x0800A8F0)
        # Fixed anchors recovered from the four loops: the portrait occupies
        # x=168..239 and y=72..151, entirely to the right of the 20x6 text box.
        self.assertEqual(struct.unpack_from('<H', self.data, 0x080080DC - ROM_BASE)[0], 0x3015)
        self.assertEqual(struct.unpack_from('<H', self.data, 0x0800811E - ROM_BASE)[0], 0x3016)
        self.assertEqual(struct.unpack_from('<H', self.data, 0x08008160 - ROM_BASE)[0], 0x20E8)
        self.assertEqual(struct.unpack_from('<H', self.data, 0x0800818A - ROM_BASE)[0], 0x20E0)

    def test_reconstruction_stages_and_draws_dialogue_portrait(self):
        assets_h = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        self.assertIn('GB_DIALOGUE_PORTRAIT_BANK_COUNT = 5', assets_h,
                      'RED: canonical five-bank dialogue portrait payload is not generated')
        self.assertIn('gb_dialogue_portrait_obj_banks', assets_h)
        self.assertIn('gb_video_draw_dialogue_portrait', video,
                      'RED: active dialogue never submits the reference right-side portrait')
        self.assertIn('gb_story_dialogue_record(story)', video)

    def test_active_dialogue_stages_selected_bank_and_submits_exact_right_side_oam(self):
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
#define SPR_VRAM(n) ((void*)((volatile uint8_t*)gb_test_vram + 0x10000 + ((n) * 32)))
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
#include <string.h>
#include <graveblood/video.h>

volatile u16 gb_test_vcount, gb_test_dispcnt, gb_test_bgctrl[4];
volatile GbTestBgOffset gb_test_bg_offset[4];
volatile u16 gb_test_bg_colors[256], gb_test_obj_colors[256], gb_test_oam[512];
volatile u16 gb_test_vram[0x18000 / 2];

const u16 gb_actor_obj_palette[GB_ACTOR_OBJ_PALETTE_COUNT] = {0};
const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT] = {0};
const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT] = {0};
const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * GB_PLAYER_FRAME_HALFWORDS] = {0};
const u16 gb_player_bicycle_obj_frames[GB_PLAYER_BICYCLE_FRAME_COUNT * GB_PLAYER_BICYCLE_FRAME_HALFWORDS] = {0};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {0};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {0};
const u16 gb_social_action_obj_icons[GB_SOCIAL_ACTION_ICON_COUNT * GB_SOCIAL_ACTION_ICON_HALFWORDS] = {0};
const u16 gb_social_reaction_obj_faces[GB_SOCIAL_REACTION_FACE_COUNT * GB_SOCIAL_REACTION_FACE_HALFWORDS] = {0};
const u16 gb_social_selector_maps[GB_SOCIAL_SELECTOR_STATE_COUNT * GB_SOCIAL_SELECTOR_MAP_CELLS] = {0};
const GbFontGlyph gb_font_glyphs[GB_FONT_GLYPH_COUNT] = {0};

u8 gb_player_frame_index(const GbPlayer* player) { (void)player; return 0; }
static const GbDialogueRecord record = { "Vika", "Maybe I should find a work...", 0, 2 };
const GbDialogueRecord* gb_story_dialogue_record(const GbStoryRuntime* story)
{ return story && story->dialogue.active ? &record : 0; }

int main(void)
{
    GbPlayer player = {0};
    GbStoryRuntime story = {0};
    story.dialogue.active = 1;
    player.x = 100; player.y = 80;
    player.x_fixed = 100 * 256; player.y_fixed = 80 * 256;
    for(unsigned i = 0; i < sizeof(gb_test_vram) / sizeof(gb_test_vram[0]); ++i)
        gb_test_vram[i] = 0xA55A;

    gb_video_draw_player_state(&player, &story, 0, 0);

    static const u16 x16[17] = {168,184,200,216,168,184,200,216,176,192,208,176,192,208,176,192,208};
    static const u16 y16[17] = {120,120,120,120,136,136,136,136,72,72,72,88,88,88,104,104,104};
    static const u16 t16[17] = {8,10,12,14,40,42,44,46,0,2,4,32,34,36,64,66,68};
    for(int i = 0; i < 17; ++i) {
        assert((gb_test_oam[i*4] & 0x00FF) == y16[i]);
        assert((gb_test_oam[i*4+1] & 0x01FF) == x16[i]);
        assert((gb_test_oam[i*4+1] & (1u<<14)) != 0);
        assert((gb_test_oam[i*4+2] & 0x03FF) == t16[i] * 2u);
    }
    static const u16 x8[11] = {232,232,232,232,232,224,224,224,224,224,224};
    static const u16 y8[11] = {112,120,128,136,144,72,80,88,96,104,112};
    static const u16 t8[11] = {7,23,39,55,71,6,22,38,54,70,86};
    for(int j = 0; j < 11; ++j) {
        int i = 17 + j;
        assert((gb_test_oam[i*4] & 0x00FF) == y8[j]);
        assert((gb_test_oam[i*4+1] & 0x01FF) == x8[j]);
        assert((gb_test_oam[i*4+1] & (1u<<14)) == 0);
        assert((gb_test_oam[i*4+2] & 0x03FF) == t8[j] * 2u);
    }

    volatile u16* obj = gb_test_vram + 0x10000/2;
    const u16* bank2 = gb_dialogue_portrait_obj_banks + 2 * GB_DIALOGUE_PORTRAIT_BANK_HALFWORDS;
    for(int i = 0; i < 32; ++i) assert(obj[i] == bank2[i]);
    for(int i = 0; i < 32; ++i)
        assert(obj[0x1400/2 + i] == bank2[GB_DIALOGUE_PORTRAIT_HEAD_HALFWORDS + i]);
    assert(obj[0x1200/2] == 0xA55A);
    assert(obj[0x13FE/2] == 0xA55A);
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'portrait.c').write_text(harness, encoding='utf-8')
            exe = td / 'portrait'
            proc = subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/video.c'),
                str(ROOT / 'reconstruction/data/dialogue_portrait_assets.c'),
                str(td / 'portrait.c'), '-Wl,--gc-sections', '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
