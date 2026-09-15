#!/usr/bin/env python3
from __future__ import annotations
import csv
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DialogueUiParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        with (ROOT / 'data' / 'dialogue_scripts.csv').open(newline='', encoding='utf-8') as f:
            cls.rows = list(csv.DictReader(f))

    def test_normal_dialogue_window_geometry_is_recovered_tile_by_tile(self):
        video = self.video
        self.assertIn('#define GB_DIALOGUE_WINDOW_MAP_X 1', video)
        self.assertIn('#define GB_DIALOGUE_WINDOW_MAP_Y 13', video)
        self.assertIn('#define GB_DIALOGUE_WINDOW_COLUMNS 20', video)
        self.assertIn('#define GB_DIALOGUE_WINDOW_ROWS 6', video)
        self.assertIn('#define GB_DIALOGUE_TEXT_COLUMNS 18', video)
        self.assertIn('#define GB_DIALOGUE_TEXT_ROWS 4', video)
        self.assertIn('#define GB_DIALOGUE_TEXT_MAP_X 2', video)
        self.assertIn('#define GB_DIALOGUE_TEXT_MAP_Y 14', video)
        self.assertIn('GB_DIALOGUE_BORDER_VERTICAL_TILE 3', video)
        self.assertIn('GB_DIALOGUE_BORDER_CORNER_TILE 4', video)
        self.assertIn('GB_DIALOGUE_BORDER_HORIZONTAL_TILE 5', video)
        upload = video[video.index('static void gb_dialogue_ui_upload_at'):video.index('static void gb_dialogue_ui_upload(void)')]
        self.assertIn('GB_DIALOGUE_BORDER_CORNER_TILE | GB_BG_MAP_VFLIP', upload)
        self.assertIn('GB_DIALOGUE_BORDER_CORNER_TILE | GB_BG_MAP_HFLIP | GB_BG_MAP_VFLIP', upload)
        self.assertIn('GB_DIALOGUE_BORDER_CORNER_TILE;', upload)
        self.assertIn('GB_DIALOGUE_BORDER_CORNER_TILE | GB_BG_MAP_HFLIP;', upload)
        self.assertIn('GB_DIALOGUE_BORDER_HORIZONTAL_TILE | GB_BG_MAP_VFLIP', upload)
        self.assertIn('window_x + GB_DIALOGUE_WINDOW_COLUMNS - 1', upload)
        self.assertIn('window_y + GB_DIALOGUE_WINDOW_ROWS - 1', upload)

    def test_dialogue_box_clear_and_upload_paths_cover_exact_window(self):
        video = self.video
        self.assertIn('for(int row = 0; row < GB_DIALOGUE_WINDOW_ROWS; ++row)', video)
        self.assertIn('for(int col = 0; col < GB_DIALOGUE_WINDOW_COLUMNS; ++col)', video)
        self.assertIn('map[(GB_DIALOGUE_WINDOW_MAP_Y + row) * 32 + GB_DIALOGUE_WINDOW_MAP_X + col] = 0;', video)
        self.assertIn('gb_dialogue_ui_upload_at(GB_SOCIAL_RESPONSE_WINDOW_MAP_X,', video)
        self.assertIn('gb_dialogue_ui_upload();', video)

    def test_dialogue_portrait_starts_immediately_right_of_window(self):
        video = self.video
        self.assertIn('static const s16 x16[17] = {', video)
        self.assertIn('168, 184, 200, 216', video)
        self.assertIn('static const s16 y16[17] = {', video)
        self.assertIn('72, 72, 72', video)
        self.assertIn('static const s16 x8[11] = {', video)
        self.assertIn('232, 232, 232, 232, 232', video)
        self.assertIn('224, 224, 224, 224, 224, 224', video)
        self.assertIn('17 16x16 and 11 8x8 cells', video)

    def test_record_by_record_portrait_argument_inventory_matches_recovered_dialogue(self):
        rows = [r for r in self.rows if int(r['opcode']) == 0]
        args = {int(r['argument']) for r in rows}
        self.assertEqual(args, {0, 1, 2, 3, 4})
        by_arg = {arg: [] for arg in sorted(args)}
        for row in rows:
            by_arg[int(row['argument'])].append((int(row['dial_index']), int(row['step']), row['speaker'], row['text']))

        expected_speakers = {
            0: {'Vika', 'Test Girl 1'},
            1: {'Vika'},
            2: {'Vika'},
            3: {'IQ 54'},
            4: {'Katya'},
        }
        for arg, speakers in expected_speakers.items():
            self.assertEqual({speaker for _, _, speaker, _ in by_arg[arg]}, speakers)

        self.assertIn((0, 0, 'Vika', 'My favorite console, so much good memories...'), by_arg[0])
        self.assertIn((1, 3, 'Test Girl 1', 'Done! Press A and then check your messages'), by_arg[0])
        self.assertIn((0, 1, 'Vika', 'I wish I had more games to play'), by_arg[1])
        self.assertIn((1, 1, 'Vika', 'Maybe I should find a work...'), by_arg[2])
        self.assertIn((2, 7, 'IQ 54', 'Could you help me to find all of my 5 sketches, please?'), by_arg[3])
        self.assertIn((3, 8, 'Katya', "And take my bicycle if you want. It's kinda far from here, I believe"), by_arg[4])


    def test_hardware_style_dialogue_map_uses_reference_border_orientation(self):
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
        ui_values = ','.join(str(500 + i) for i in range(87))
        harness = rf"""
#include <assert.h>
#include <graveblood/video.h>

volatile u16 gb_test_vcount, gb_test_dispcnt, gb_test_bgctrl[4];
volatile GbTestBgOffset gb_test_bg_offset[4];
volatile u16 gb_test_bg_colors[256], gb_test_obj_colors[256], gb_test_oam[512];
volatile u16 gb_test_vram[0x18000 / 2];

const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT] = {{0}};
const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT] = {{0}};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {{0}};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {{0}};
const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = {{0}};
const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {{0}};
const u16 gb_social_selector_maps[GB_SOCIAL_SELECTOR_STATE_COUNT * GB_SOCIAL_SELECTOR_MAP_CELLS] = {{0}};
const GbSocialActionData gb_social_actions[GB_SOCIAL_ACTION_COUNT] = {{0}};
const char* const gb_social_subject_topics[GB_SOCIAL_SUBJECT_TOPIC_COUNT] = {{0}};
const char* const gb_social_ask_topics[GB_SOCIAL_ASK_TOPIC_COUNT] = {{0}};
const char* const gb_social_criticize_topics[GB_SOCIAL_CRITICIZE_TOPIC_COUNT] = {{0}};
const GbFontGlyph gb_font_glyphs[GB_FONT_GLYPH_COUNT] = {{0}};
const char* gb_story_social_profile_name(const GbStoryRuntime* story) {{ (void)story; return 0; }}
static const u16 ui_tiles[GB_BG0_UI_TILE_COUNT] = {{ {ui_values} }};
static const u16 palette[256] = {{0}};
static const GbDialogueRecord rec = {{ "Vika", "X", 0, 0 }};
const GbDialogueRecord* gb_story_dialogue_record(const GbStoryRuntime* story)
{{ return story && story->dialogue.active ? &rec : 0; }}

int main(void)
{{
    GbLevelAssets level = {{0}};
    level.level_id = 7;
    level.bg_palette = palette;
    level.bg0_ui_tiles = ui_tiles;
    gb_video_load_level(&level);

    GbStoryRuntime story = {{0}};
    story.dialogue.active = 1;
    gb_video_draw_story_ui(&story);
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(27);

    /* Reference orientation: top border is V-flipped, bottom is unflipped. */
    assert(map[13 * 32 + 1] == (4u | (1u << 11)));
    assert(map[13 * 32 + 20] == (4u | (1u << 10) | (1u << 11)));
    assert(map[18 * 32 + 1] == 4u);
    assert(map[18 * 32 + 20] == (4u | (1u << 10)));
    assert(map[13 * 32 + 2] == (5u | (1u << 11)));
    assert(map[18 * 32 + 2] == 5u);
    assert(map[14 * 32 + 1] == 3u);
    assert(map[14 * 32 + 20] == (3u | (1u << 10)));
    assert(map[14 * 32 + 2] == ui_tiles[0]);
    assert(map[17 * 32 + 19] == ui_tiles[71]);
    return 0;
}}
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'dialogue_map.c').write_text(harness, encoding='utf-8')
            exe = td / 'dialogue_map'
            proc = subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/video.c'),
                str(td / 'dialogue_map.c'), '-Wl,--gc-sections', '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_runtime_uses_record_argument_directly_with_no_character_specific_remap(self):
        video = self.video
        self.assertIn('const GbDialogueRecord* record = gb_story_dialogue_record(story);', video)
        self.assertIn('record->argument >= GB_DIALOGUE_PORTRAIT_BANK_COUNT', video)
        self.assertIn('gb_stage_dialogue_portrait_bank((u8)record->argument);', video)
        draw_fn = video[video.index('static int gb_video_draw_dialogue_portrait'):video.index('static int gb_video_draw_social_reaction')]
        self.assertNotIn('speaker', draw_fn)
        self.assertNotIn('switch(', draw_fn)
        self.assertNotIn('portrait_map', draw_fn)


if __name__ == '__main__':
    unittest.main()
