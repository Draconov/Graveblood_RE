#!/usr/bin/env python3
import csv
import hashlib
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_PATH = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000
BG_BASE = 0x08608A9C
OBJ_BASE = 0x08310654
PAGES = (6, 2, 1, 0, 3, 4, 5)
BANKS = (15, 13, 12, 11, 6, 4, 5)
CHUNK_UNITS = (0x24C, 0x25C, 0x26C, 0x27C)


def rom_slice(data: bytes, address: int, size: int) -> bytes:
    off = address - ROM_BASE
    return data[off:off + size]


def expected_page(data: bytes, page: int) -> bytes:
    return rom_slice(data, BG_BASE + 0xD0C0 + page * 0x2000, 0x2000)


def expected_preview(data: bytes, bank: int) -> bytes:
    chunks = []
    for unit in CHUNK_UNITS:
        source_unit = bank * 192 + unit
        chunks.append(rom_slice(data, OBJ_BASE + source_unit * 64, 128))
    return b''.join(chunks)


class WardrobeRuntimeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM_PATH.read_bytes()

    def halfword(self, address: int) -> int:
        off = address - ROM_BASE
        return int.from_bytes(self.data[off:off + 2], 'little')

    def test_hidden_entry_is_exact_current_b_plus_select_equality(self):
        self.assertEqual(self.halfword(0x08008318), 0x681B)
        self.assertEqual(self.halfword(0x0800831A), 0x2B06)
        self.assertEqual(self.halfword(0x0800831C), 0xD101)
        self.assertEqual(self.halfword(0x0800831E) & 0xF800, 0xF000)

    def test_player_lighting_pass_precedes_hidden_wardrobe_branch(self):
        # Player_update computes/applies the four-entry OBJ lighting refresh at
        # 0x08008312, then immediately checks exact B+SELECT (6) and branches
        # into the hidden Wardrobe path.  Wardrobe therefore does not freeze
        # the gameplay lighting clock/cursor while its modal UI is active.
        self.assertEqual(self.halfword(0x08008312) & 0xF800, 0xF000)
        self.assertEqual(self.halfword(0x08008316), 0x465B)
        self.assertEqual(self.halfword(0x08008318), 0x681B)
        self.assertEqual(self.halfword(0x0800831A), 0x2B06)
        self.assertEqual(self.halfword(0x0800831E) & 0xF800, 0xF000)

    def test_exit_requests_gameplay_level7(self):
        self.assertEqual(self.halfword(0x08009672), 0x2200)
        self.assertEqual(self.halfword(0x08009674), 0x2107)
        self.assertEqual(self.halfword(0x08009678) & 0xF800, 0xF000)

    def test_left_right_and_b_are_fresh_key_checks(self):
        self.assertEqual(self.halfword(0x08008FB8), 0x2220)
        self.assertEqual(self.halfword(0x08008FD2), 0x2210)
        self.assertEqual(self.halfword(0x08008FEA), 0x2302)

    def test_selector_navigation_branches_have_no_sfx11_call_site(self):
        with (ROOT / 'data' / 'audio_call_sites.csv').open(newline='') as f:
            rows = list(csv.DictReader(f))
        sfx11 = [int(row['call_address'], 16) for row in rows if row['sound_id'] == '11']
        self.assertEqual(sfx11, [0x0800898E, 0x0800904E])
        nav_ranges = ((0x0800951E, 0x08009588), (0x08009588, 0x080095C0))
        self.assertTrue(all(not (lo <= addr < hi) for addr in sfx11 for lo, hi in nav_ranges))

    def test_runtime_extractor_and_outputs_exist(self):
        self.assertTrue((ROOT / 'tools' / 'extract_wardrobe_runtime.py').exists(),
                        'missing Wardrobe runtime asset extractor')
        self.assertTrue((ROOT / 'reconstruction' / 'data' / 'wardrobe_assets.c').exists(),
                        'missing generated Wardrobe runtime assets')
        self.assertTrue((ROOT / 'data' / 'wardrobe_runtime_assets.csv').exists(),
                        'missing Wardrobe runtime evidence export')

    def test_generated_asset_payloads_match_exact_rom_slices(self):
        script = ROOT / 'tools' / 'extract_wardrobe_runtime.py'
        self.assertTrue(script.exists(), 'extractor missing')
        spec = importlib.util.spec_from_file_location('extract_wardrobe_runtime', script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        extracted = mod.extract_runtime_assets(self.data)
        self.assertEqual(tuple(extracted['pages']), PAGES)
        self.assertEqual(tuple(extracted['banks']), BANKS)
        self.assertEqual(extracted['labels'], ['Favorite Skirt'] + ['Not for demo'] * 6)
        for i, page in enumerate(PAGES):
            self.assertEqual(extracted['bg_pages'][i], expected_page(self.data, page))
        for i, bank in enumerate(BANKS):
            self.assertEqual(extracted['preview_tiles'][i], expected_preview(self.data, bank))
            self.assertEqual(len(extracted['preview_tiles'][i]), 512)

    def test_generated_evidence_hashes_match_payloads(self):
        evidence = ROOT / 'data' / 'wardrobe_runtime_assets.csv'
        self.assertTrue(evidence.exists(), 'Wardrobe runtime evidence export missing')
        with evidence.open(newline='') as f:
            rows = list(csv.DictReader(f))
        page_rows = [r for r in rows if r['kind'] == 'bg_page']
        preview_rows = [r for r in rows if r['kind'] == 'preview_obj']
        self.assertEqual(len(page_rows), 7)
        self.assertEqual(len(preview_rows), 7)
        for i, row in enumerate(page_rows):
            self.assertEqual(int(row['selector']), i)
            self.assertEqual(int(row['value']), PAGES[i])
            self.assertEqual(row['sha256'], hashlib.sha256(expected_page(self.data, PAGES[i])).hexdigest())
        for i, row in enumerate(preview_rows):
            self.assertEqual(int(row['selector']), i)
            self.assertEqual(int(row['value']), BANKS[i])
            self.assertEqual(row['sha256'], hashlib.sha256(expected_preview(self.data, BANKS[i])).hexdigest())


class WardrobeRuntimeHostTests(unittest.TestCase):
    def test_pure_runtime_matches_selector_range_fresh_navigation_and_level7_exit(self):
        gba_h = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8;
typedef uint16_t u16;
#define KEY_A 0x0001
#define KEY_B 0x0002
#define KEY_SELECT 0x0004
#define KEY_START 0x0008
#define KEY_RIGHT 0x0010
#define KEY_LEFT 0x0020
#define KEY_UP 0x0040
#define KEY_DOWN 0x0080
#define KEY_R 0x0100
#define KEY_L 0x0200
#endif
'''
        harness = r'''
#include <assert.h>
#include <graveblood/wardrobe.h>

int main(void)
{
    GbWardrobeRuntime wardrobe;
    gb_wardrobe_init(&wardrobe);
    assert(wardrobe.selector == 0);

    GbInput held_entry = { .held = KEY_B | KEY_SELECT, .pressed = 0 };
    GbWardrobeTick tick = gb_wardrobe_update(&wardrobe, &held_entry);
    assert(!tick.exit_gameplay);
    assert(wardrobe.selector == 0);

    GbInput left_at_zero = { .held = KEY_LEFT, .pressed = KEY_LEFT };
    gb_wardrobe_update(&wardrobe, &left_at_zero);
    assert(wardrobe.selector == 0);

    GbInput right = { .held = KEY_RIGHT, .pressed = KEY_RIGHT };
    for(int i = 0; i < 8; ++i)
        gb_wardrobe_update(&wardrobe, &right);
    assert(wardrobe.selector == 6);

    GbInput a = { .held = KEY_A, .pressed = KEY_A };
    tick = gb_wardrobe_update(&wardrobe, &a);
    assert(wardrobe.selector == 6);
    assert(!tick.exit_gameplay);

    GbInput left = { .held = KEY_LEFT, .pressed = KEY_LEFT };
    tick = gb_wardrobe_update(&wardrobe, &left);
    assert(wardrobe.selector == 5);
    assert(tick.selector_changed);

    GbInput b_held_not_fresh = { .held = KEY_B, .pressed = 0 };
    tick = gb_wardrobe_update(&wardrobe, &b_held_not_fresh);
    assert(!tick.exit_gameplay);

    GbInput b_fresh = { .held = KEY_B, .pressed = KEY_B };
    tick = gb_wardrobe_update(&wardrobe, &b_fresh);
    assert(tick.exit_gameplay);
    assert(tick.gameplay_level == 7);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h)
            (td / 'test.c').write_text(harness)
            exe = td / 'test'
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/game/wardrobe.c'),
                str(td / 'test.c'), '-o', str(exe),
            ], check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)


class WardrobeVideoSourceTests(unittest.TestCase):
    def test_video_has_canonical_wardrobe_preview_mode_without_gameplay_bank_mutation(self):
        header = (ROOT / 'reconstruction/include/graveblood/video.h').read_text()
        source = (ROOT / 'reconstruction/source/engine/video.c').read_text()
        self.assertIn('void gb_video_load_wardrobe(void);', header)
        self.assertIn('void gb_video_draw_wardrobe(u8 selector);', header)
        self.assertIn('gb_wardrobe_bg_pages[selector]', source)
        self.assertIn('gb_wardrobe_preview_tiles[i]', source)
        self.assertIn('gb_wardrobe_labels[selector]', source)
        self.assertIn('#define GB_WARDROBE_TITLE_MAP_X 6', source)
        self.assertIn('#define GB_WARDROBE_TITLE_MAP_Y 2', source)
        self.assertIn('#define GB_WARDROBE_TITLE_COLUMNS 8', source)
        self.assertIn('#define GB_WARDROBE_LABEL_MAP_X 5', source)
        self.assertIn('#define GB_WARDROBE_LABEL_MAP_Y 14', source)
        self.assertIn('#define GB_WARDROBE_LABEL_COLUMNS 15', source)
        self.assertIn('#define GB_WARDROBE_EXIT_MAP_X 6', source)
        self.assertIn('#define GB_WARDROBE_EXIT_MAP_Y 17', source)
        self.assertIn('#define GB_WARDROBE_EXIT_COLUMNS 15', source)
        self.assertIn('#define GB_WARDROBE_TEXT_FOREGROUND_INDEX 5', source)
        self.assertIn('gb_wardrobe_text_upload_row("Wardrobe"', source)
        self.assertIn('gb_wardrobe_text_upload_row(gb_wardrobe_labels[selector]', source)
        self.assertIn('gb_wardrobe_text_upload_row("(B) to exit"', source)
        wardrobe_draw = source[source.index('void gb_video_draw_wardrobe(u8 selector)'):source.index('void gb_video_load_wardrobe(void)')]
        self.assertNotIn('gb_story_ui_begin();', wardrobe_draw)
        self.assertNotIn('GB_WARDROBE_BG_MAP_', wardrobe_draw)
        self.assertIn('GB_WARDROBE_SELECTOR_LOGICAL_TILE 0x4A', source)
        self.assertIn('const int selector_x = (selector + 1) * 16;', wardrobe_draw)
        self.assertIn('GB_WARDROBE_CHOICE_COUNT * 2 + row', wardrobe_draw)
        self.assertIn('GB_WARDROBE_BG_PAGE_HALFWORDS', source)
        self.assertIn('GB_OBJ_256_COLOR', source)
        self.assertIn('gb_video_restore_gameplay_obj_assets', source)
        self.assertNotIn('0x0300103C', source)

        load = source[source.index('void gb_video_load_wardrobe(void)'):source.index('static void gb_pda_text_clear(void)')]
        self.assertNotIn('OBJ_1D_MAP', load, 'original Wardrobe stays in gameplay 2D OBJ mapping')
        self.assertNotIn('REG_DISPCNT =', load, 'original Wardrobe path does not rewrite DISPCNT')
        self.assertNotIn('BGCTRL[', load, 'Wardrobe preserves live BG control state')
        self.assertNotIn('BG_COLORS', load, 'Wardrobe preserves the live gameplay palette')
        self.assertNotIn('gb_video_set_camera', load, 'Wardrobe preserves the live gameplay camera')
        self.assertNotIn('gb_clear_u16', load, 'Wardrobe must not erase the live gameplay tilemaps')
        self.assertNotIn('gb_video_level =', load, 'Wardrobe must preserve the active gameplay lighting source')
        self.assertIn('#define GB_WARDROBE_PREVIEW_LOGICAL_BASE 0x62', source)
        self.assertIn('gb_stage_8bpp_16x32(logical_root, gb_wardrobe_preview_tiles[i]);', source)
        self.assertIn('(u16)(logical_root * 2u)', source)
        self.assertIn('(u16)((logical_root + 32u) * 2u)', source)


    def test_hardware_style_wardrobe_preserves_scene_and_draws_choices_highlight_and_text(self):
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
#include <string.h>
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
const u16 gb_title_obj_tiles[GB_TITLE_OBJ_TILE_HALFWORDS] = {{
    [0x4A * 32] = 0xBEEF,
    [0x5A * 32] = 0xCAFE,
}};
const u16 gb_wardrobe_bg_pages[GB_WARDROBE_CHOICE_COUNT][GB_WARDROBE_BG_PAGE_HALFWORDS] = {{
    {{ [0] = 0xA111 }}, {{ [0] = 0xA222 }}, {{ [0] = 0xA333 }}, {{ [0] = 0xA444 }},
    {{ [0] = 0xA555 }}, {{ [0] = 0xA666 }}, {{ [0] = 0xA777 }},
}};
const u16 gb_wardrobe_preview_tiles[GB_WARDROBE_CHOICE_COUNT][GB_WARDROBE_PREVIEW_HALFWORDS] = {{
    {{ [0] = 0x1101 }}, {{ [0] = 0x1102 }}, {{ [0] = 0x1103 }}, {{ [0] = 0x1104 }},
    {{ [0] = 0x1105 }}, {{ [0] = 0x1106 }}, {{ [0] = 0x1107 }},
}};
const char* const gb_wardrobe_labels[GB_WARDROBE_CHOICE_COUNT] = {{
    "Favorite Skirt", "Not for demo", "Not for demo", "Not for demo",
    "Not for demo", "Not for demo", "Not for demo"
}};
const GbFontGlyph gb_font_glyphs[GB_FONT_GLYPH_COUNT] = {{
    ['W'] = {{ 1, {{1,1,1,1,1,1,1,1}} }},
    ['F'] = {{ 1, {{1,1,1,1,1,1,1,1}} }},
    ['('] = {{ 1, {{1,1,1,1,1,1,1,1}} }},
}};
static const u16 ui_tiles[GB_BG0_UI_TILE_COUNT] = {{ {ui_values} }};
static const u16 palette[256] = {{0}};

int main(void)
{{
    GbLevelAssets level = {{0}};
    level.level_id = 7;
    level.bg_palette = palette;
    level.bg0_ui_tiles = ui_tiles;
    gb_video_load_level(&level);

    volatile u16* map0 = (volatile u16*)MAP_BASE_ADR(27);
    map0[4 * 32 + 7] = 0x5AA5;
    map0[10 * 32 + 20] = 0x6BB6;
    gb_test_bg_offset[0].x = 123;
    gb_test_bg_offset[0].y = 45;
    gb_test_bgctrl[0] = 0x1A2B;

    gb_video_load_wardrobe();

    /* Entering Wardrobe must preserve the live camera/BG state and room map. */
    assert(gb_test_bg_offset[0].x == 123);
    assert(gb_test_bg_offset[0].y == 45);
    assert(gb_test_bgctrl[0] == 0x1A2B);
    assert(map0[4 * 32 + 7] == 0x5AA5);
    assert(map0[10 * 32 + 20] == 0x6BB6);

    /* Selector 0 swaps only the 0x2000-byte BG graphics page at 0x06003000. */
    assert(gb_test_vram[0x3000 / 2] == 0xA111);

    /* Exact text windows: title 8 tiles, label 15, exit 15. */
    assert(map0[2 * 32 + 6] == ui_tiles[0]);
    assert(map0[2 * 32 + 13] == ui_tiles[7]);
    assert(map0[14 * 32 + 5] == ui_tiles[8]);
    assert(map0[14 * 32 + 19] == ui_tiles[22]);
    assert(map0[17 * 32 + 6] == ui_tiles[23]);
    assert(map0[17 * 32 + 20] == ui_tiles[37]);
    assert(gb_test_vram[ui_tiles[0] * 32] == 0x0005); /* yellow index 5 */

    /* Seven outfit choices are visible at x=16..112, y=48/64. */
    for(int i = 0; i < 7; ++i)
    {{
        const int top = i * 2;
        const int bottom = top + 1;
        const u16 root = (u16)(0x62 + i * 2);
        assert((gb_test_oam[top * 4] & 0x00FF) == 48);
        assert((gb_test_oam[top * 4 + 1] & 0x01FF) == (u16)(16 + i * 16));
        assert((gb_test_oam[top * 4 + 2] & 0x03FF) == root * 2u);
        assert((gb_test_oam[bottom * 4] & 0x00FF) == 64);
        assert((gb_test_oam[bottom * 4 + 1] & 0x01FF) == (u16)(16 + i * 16));
        assert((gb_test_oam[bottom * 4 + 2] & 0x03FF) == (root + 32u) * 2u);
    }}

    /* Selector highlight is the reference baseline OBJ tile 0x4A, two cells. */
    assert((gb_test_oam[14 * 4] & 0x00FF) == 48);
    assert((gb_test_oam[15 * 4] & 0x00FF) == 64);
    assert((gb_test_oam[14 * 4 + 1] & 0x01FF) == 16);
    assert((gb_test_oam[15 * 4 + 1] & 0x01FF) == 16);
    assert((gb_test_oam[14 * 4 + 2] & 0x03FF) == 0x4A * 2u);
    assert((gb_test_oam[15 * 4 + 2] & 0x03FF) == 0x4A * 2u);
    volatile u16* obj = gb_test_vram + 0x10000 / 2;
    assert(obj[0x4A * 32] == 0xBEEF);
    assert(obj[0x5A * 32] == 0xCAFE);

    gb_video_draw_wardrobe(3);
    assert(gb_test_vram[0x3000 / 2] == 0xA444);
    assert((gb_test_oam[14 * 4 + 1] & 0x01FF) == 64);
    assert((gb_test_oam[15 * 4 + 1] & 0x01FF) == 64);
    return 0;
}}
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'wardrobe_video.c').write_text(harness, encoding='utf-8')
            exe = td / 'wardrobe_video'
            proc = subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/video.c'),
                str(td / 'wardrobe_video.c'), '-Wl,--gc-sections', '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


class WardrobeGameIntegrationTests(unittest.TestCase):
    def test_game_uses_exact_hidden_combo_suspends_gameplay_and_exits_to_level7_without_sfx11(self):
        scene_h = (ROOT / 'reconstruction/include/graveblood/scene.h').read_text()
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text()
        self.assertIn('GB_SCENE_WARDROBE', scene_h)
        self.assertIn('#include <graveblood/wardrobe.h>', game)
        self.assertIn('GbWardrobeRuntime wardrobe;', game)
        self.assertIn('input.held == (KEY_B | KEY_SELECT)', game)
        self.assertIn('int player_locked = gb_story_player_controls_locked(&story);', game)
        self.assertIn('if(! player_locked && input.held == (KEY_B | KEY_SELECT))', game)
        self.assertIn('scene.active = GB_SCENE_WARDROBE;', game)
        self.assertIn('gb_video_load_wardrobe();', game)
        wardrobe_branch = game[game.index('if(scene.active == GB_SCENE_WARDROBE)'):game.index('/* GameplayScene_update publishes/streams the camera')]
        self.assertIn('gb_video_gameplay_lighting_tick(1);', wardrobe_branch,
                      'active Wardrobe frames must retain Player_update lighting cadence')
        player_lighting = game.index(
            'gb_video_gameplay_lighting_tick(interaction_clock_paused ? 0 : 1);')
        combo_start = game.index('input.held == (KEY_B | KEY_SELECT)', player_lighting)
        pda_start = game.index('if(input.pressed & KEY_START)', combo_start)
        self.assertLess(player_lighting, combo_start)
        self.assertLess(combo_start, pda_start)
        self.assertIn('gb_wardrobe_update(&wardrobe, &input)', game)
        self.assertIn('gb_video_draw_wardrobe(wardrobe.selector);', game)
        wardrobe_draws = wardrobe_branch.count('gb_video_draw_wardrobe(wardrobe.selector);')
        self.assertEqual(wardrobe_draws, 1)
        self.assertIn('gb_scene_request_gameplay(&scene, 7, 10);', game)
        self.assertNotIn('gb_enter_level(&world, &player, &actors, &story, 7);', game)
        self.assertNotIn('gb_audio_play_sfx(11)', game)


if __name__ == '__main__':
    unittest.main()
