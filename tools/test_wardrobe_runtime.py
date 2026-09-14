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
        self.assertIn('GB_WARDROBE_BG_PAGE_HALFWORDS', source)
        self.assertIn('GB_OBJ_256_COLOR', source)
        self.assertIn('gb_video_restore_gameplay_obj_assets', source)
        self.assertNotIn('0x0300103C', source)

        load = source[source.index('void gb_video_load_wardrobe(void)'):source.index('static void gb_pda_text_clear(void)')]
        self.assertNotIn('OBJ_1D_MAP', load, 'original Wardrobe stays in gameplay 2D OBJ mapping')
        self.assertNotIn('REG_DISPCNT =', load, 'original Wardrobe path does not rewrite DISPCNT')
        self.assertNotIn('gb_copy_u16(OBJ_COLORS', load, 'Wardrobe inherits the live gameplay OBJ palette')
        self.assertNotIn('gb_video_level =', load, 'Wardrobe must preserve the active gameplay lighting source')
        self.assertIn('#define GB_WARDROBE_PREVIEW_LOGICAL_BASE 0x62', source)
        self.assertIn('gb_stage_8bpp_16x32(logical_root, gb_wardrobe_preview_tiles[i]);', source)
        self.assertIn('(u16)(logical_root * 2u)', source)
        self.assertIn('(u16)((logical_root + 32u) * 2u)', source)


class WardrobeGameIntegrationTests(unittest.TestCase):
    def test_game_uses_exact_hidden_combo_suspends_gameplay_and_exits_to_level7_without_sfx11(self):
        scene_h = (ROOT / 'reconstruction/include/graveblood/scene.h').read_text()
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text()
        self.assertIn('GB_SCENE_WARDROBE', scene_h)
        self.assertIn('#include <graveblood/wardrobe.h>', game)
        self.assertIn('GbWardrobeRuntime wardrobe;', game)
        self.assertIn('input.held == (KEY_B | KEY_SELECT)', game)
        self.assertIn('const int interaction_active = gb_story_ui_active(&story);', game)
        self.assertIn('if(! interaction_active)', game)
        self.assertIn('scene.active = GB_SCENE_WARDROBE;', game)
        self.assertIn('gb_video_load_wardrobe();', game)
        wardrobe_branch = game[game.index('if(scene.active == GB_SCENE_WARDROBE)'):game.index('/* GameplayScene_update publishes/streams the camera')]
        self.assertIn('gb_video_gameplay_lighting_tick(1);', wardrobe_branch,
                      'active Wardrobe frames must retain Player_update lighting cadence')
        player_lighting = game.index(
            'gb_video_gameplay_lighting_tick(interaction_active ? 0 : 1);')
        combo_start = game.index('input.held == (KEY_B | KEY_SELECT)', player_lighting)
        pda_start = game.index('if(input.pressed & KEY_START)', combo_start)
        self.assertLess(player_lighting, combo_start)
        self.assertLess(combo_start, pda_start)
        self.assertIn('gb_wardrobe_update(&wardrobe, &input)', game)
        self.assertIn('gb_video_draw_wardrobe(wardrobe.selector);', game)
        self.assertIn('gb_scene_request_gameplay(&scene, 7, 10);', game)
        self.assertNotIn('gb_enter_level(&world, &player, &actors, &story, 7);', game)
        self.assertNotIn('gb_audio_play_sfx(11)', game)


if __name__ == '__main__':
    unittest.main()
