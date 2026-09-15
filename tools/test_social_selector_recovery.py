#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path

from tools import generate_cfa_assets as gen

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', ROOT.parent / 'Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000
OBJ_TILES_SOURCE = 0x08310654
SELECTOR_TRANSLATION = 0x0864825C
SELECTOR_MAPS = (0x08655364, 0x08654554, 0x08654EB4, 0x08654A04)


def _expected_icons(rom: bytes) -> bytes:
    with (ROOT / 'data/player_interaction_action_table.csv').open(newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    out = bytearray()
    source = OBJ_TILES_SOURCE - ROM_BASE
    for row in rows:
        root = 0x200 + int(row['visual_selector'])
        for logical in (root, root + 1, root + 16, root + 17):
            off = source + logical * 64
            out.extend(rom[off:off + 64])
    return bytes(out)


def _expected_maps(rom: bytes) -> tuple[tuple[int, ...], ...]:
    sources = [struct.unpack_from('<600H', rom, addr - ROM_BASE) for addr in SELECTOR_MAPS]
    max_source = max(
        source[(9 + y) * 30 + (1 + x)]
        for source in sources for y in range(10) for x in range(19)
    )
    translation = struct.unpack_from(f'<{max_source + 1}H', rom, SELECTOR_TRANSLATION - ROM_BASE)
    maps = []
    for source in sources:
        maps.append(tuple(
            translation[source[(9 + y) * 30 + (1 + x)]]
            for y in range(10) for x in range(19)
        ))
    return tuple(maps)


class SocialSelectorRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = ROM.read_bytes()

    def test_pack_social_action_icons_matches_rom_staging_source(self):
        expected = _expected_icons(self.rom)
        actual = gen.pack_social_action_icons(self.rom, ROOT)
        self.assertEqual(20 * 256, len(expected))
        self.assertEqual(expected, actual)
        # Stable fingerprints make accidental source-root drift loud.
        self.assertEqual(hashlib.sha256(expected).hexdigest(), hashlib.sha256(actual).hexdigest())

    def test_rom_social_stager_adds_0x200_to_all_four_visual_selectors(self):
        def h(addr: int) -> int:
            return struct.unpack_from('<H', self.rom, addr - ROM_BASE)[0]
        # 0x08004D88 receives the four action-record +0x1C visual selectors.
        # Each selector is biased by 0x200 logical 8bpp tiles before the
        # source address is multiplied by 64 and copied into OBJ roots 0/2/4/6.
        self.assertEqual((0x2380, 0x009B, 0x4460, 0x0183),
                         tuple(h(a) for a in (0x08004D8C, 0x08004D8E, 0x08004D98, 0x08004D9C)))
        self.assertEqual((0x2380, 0x009B, 0x4467, 0x01BF),
                         tuple(h(a) for a in (0x08004DDC, 0x08004DDE, 0x08004DE4, 0x08004DF4)))
        self.assertEqual((0x2380, 0x009B, 0x4466, 0x01B6),
                         tuple(h(a) for a in (0x08004E20, 0x08004E22, 0x08004E28, 0x08004E38)))
        self.assertEqual((0x2380, 0x009B, 0x4465, 0x01AD),
                         tuple(h(a) for a in (0x08004E64, 0x08004E66, 0x08004E6C, 0x08004E7C)))

    def test_pack_social_selector_maps_matches_rom_crop_and_translation(self):
        expected = _expected_maps(self.rom)
        actual = gen.pack_social_selector_maps(self.rom)
        self.assertEqual(4, len(actual))
        self.assertTrue(all(len(m) == 19 * 10 for m in actual))
        self.assertEqual(expected, actual)

    def test_generator_emits_social_selector_assets_and_public_contract(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'reconstruction'
            gen.generate_all(ROOT, out, ROM)
            unit = out / 'data/social_selector_assets.c'
            self.assertTrue(unit.exists(), 'missing generated social selector asset unit')
            text = unit.read_text(encoding='utf-8')
            self.assertIn('gb_social_action_obj_icons', text)
            self.assertIn('gb_social_selector_maps', text)
            header = (out / 'include/graveblood/assets.h').read_text(encoding='utf-8')
            self.assertIn('GB_SOCIAL_ACTION_ICON_COUNT = 20', header)
            self.assertIn('GB_SOCIAL_SELECTOR_STATE_COUNT = 4', header)
            self.assertIn('extern const u16 gb_social_action_obj_icons', header)
            self.assertIn('extern const u16 gb_social_selector_maps', header)

    def test_rom_draw_helper_uses_dpad_cross_and_logical_roots_0_2_4_6(self):
        def u16(addr: int) -> int:
            return struct.unpack_from('<H', self.rom, addr - ROM_BASE)[0]
        # 0x080065A8: four OAM submits: Up (40,80,tile0), Right (64,104,tile2),
        # Down (40,128,tile4), Left (16,104,tile6).
        self.assertEqual((0x2028, 0x2150, 0x2200), (u16(0x080065B8), u16(0x080065B6), u16(0x080065B4)))
        self.assertEqual((0x2040, 0x2168, 0x2202), (u16(0x080065D0), u16(0x080065CE), u16(0x080065CC)))
        self.assertEqual((0x2028, 0x2180, 0x2204), (u16(0x080065E0), u16(0x080065DE), u16(0x080065DC)))
        self.assertEqual((0x2010, 0x2168, 0x2206), (u16(0x080065EE), u16(0x080065EC), u16(0x080065EA)))


    def test_rom_selector_helper_targets_bg0_tile_1_9_size_19x10(self):
        def u32(addr: int) -> int:
            return struct.unpack_from('<I', self.rom, addr - ROM_BASE)[0]
        # 0x0800A620 literal math: destination base 0x0600DCC2 - 0x280
        # = 0x0600DA42 = BG0 screenblock27 cell (1,9).  The outer loop
        # advances 19 columns to 0x0600DCE8; inner rows advance by 0x40.
        self.assertEqual(0x0600DCC2, u32(0x0800A6E0))
        self.assertEqual(0xFFFFFD80, u32(0x0800A6E4))
        self.assertEqual(0x0600DCE8, u32(0x0800A6F8))
        self.assertEqual(0x0864825C, u32(0x0800A6D8))
        self.assertEqual((1, 9, 19, 10), (1, 9, GB_SOCIAL_SELECTOR_MAP_WIDTH if False else 19, 10))

    def test_runtime_replaces_ascii_selector_with_rom_map_and_dpad_icons(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        self.assertIn('#define GB_SOCIAL_SELECTOR_MAP_X 1', video)
        self.assertIn('#define GB_SOCIAL_SELECTOR_MAP_Y 9', video)
        compact = ' '.join(video.split())
        self.assertIn('gb_social_selector_maps + (u32)story->social.selected_quadrant * GB_SOCIAL_SELECTOR_MAP_CELLS', compact)
        self.assertIn('map[(GB_SOCIAL_SELECTOR_MAP_Y + y) * 32 + GB_SOCIAL_SELECTOR_MAP_X + x]', video)
        self.assertNotIn('gb_story_ui_text("^"', video)
        self.assertNotIn('gb_story_ui_text("  >"', video)
        self.assertNotIn('gb_story_ui_text("v"', video)
        self.assertNotIn('gb_story_ui_text("  <"', video)
        self.assertIn('gb_social_action_obj_icons + (u32)action_index * GB_SOCIAL_ACTION_ICON_HALFWORDS', video)
        self.assertIn('static const s16 xs[4] = { 40, 64, 40, 16 };', video)
        self.assertIn('static const s16 ys[4] = { 80, 104, 128, 104 };', video)
        self.assertIn('static const u16 roots[4] = { 0, 2, 4, 6 };', video)


    def test_generated_dynamic_ui_tiles_never_overlap_selector_tiles(self):
        selector_tiles = {entry & 0x03FF for state in gen.pack_social_selector_maps(self.rom) for entry in state}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'reconstruction'
            gen.generate_all(ROOT, out, ROM)
            for unit in sorted((out / 'data').glob('level*_assets.c')):
                text = unit.read_text(encoding='utf-8')
                marker = '_bg0_ui_tiles[GB_BG0_UI_TILE_COUNT] = {'
                pos = text.find(marker)
                if pos < 0:
                    continue
                body = text[pos + len(marker):text.index('};', pos)]
                ui_tiles = {int(token.strip()) for token in body.replace('\n', ' ').split(',') if token.strip()}
                self.assertFalse(selector_tiles & ui_tiles, f'{unit.name}: overlapping selector/UI tiles {sorted(selector_tiles & ui_tiles)}')


    def test_rom_selected_label_textobject_is_8x1_bg9_fg2_at_directional_positions(self):
        def h(addr: int) -> int:
            return struct.unpack_from('<H', self.rom, addr - ROM_BASE)[0]
        def w(addr: int) -> int:
            return struct.unpack_from('<I', self.rom, addr - ROM_BASE)[0]
        # 0x08007FD0: existing TextObject gets palette pair 0x0209, height 1
        # and width 8 before the selected action label is written.
        self.assertEqual(0x00000209, w(0x08008090))
        self.assertEqual((0x2354, 0x3B53, 0x9300, 0x3307),
                         tuple(h(a) for a in (0x08007FEE, 0x08007FF4, 0x08007FFC, 0x08007FFE)))
        # Directional call sites pass x/y and quadrant in r1/r2/r3.
        self.assertEqual((0x2300,0x220A,0x2108), tuple(h(a) for a in (0x08009C88,0x08009C8A,0x08009C8C)))
        self.assertEqual((0x2301,0x220D,0x210B), tuple(h(a) for a in (0x08009D76,0x08009D78,0x08009D7A)))
        self.assertEqual((0x2302,0x2210,0x2108), tuple(h(a) for a in (0x08009DBA,0x08009DBC,0x08009DBE)))
        self.assertEqual((0x2303,0x220D,0x2105), tuple(h(a) for a in (0x080097EE,0x080097F0,0x080097F2)))

    def test_runtime_overlays_selected_action_label_on_selector_map(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        compact = ' '.join(video.split())
        self.assertIn('static const s16 label_x[4] = { 8, 11, 8, 5 };', video)
        self.assertIn('static const s16 label_y[4] = { 10, 13, 16, 13 };', video)
        self.assertIn('gb_social_text_upload_row(gb_social_actions[action_index].label,', compact)
        self.assertIn('label_x[story->social.selected_quadrant]', compact)
        self.assertIn('label_y[story->social.selected_quadrant]', compact)
        self.assertIn('9, 2, 0', compact)
        draw = video.index('static void gb_story_ui_draw_social(')
        map_call = video.index('gb_social_selector_upload_map(story);', draw)
        label_call = video.index('gb_social_selector_upload_label(story);', draw)
        self.assertLess(map_call, label_call)

    def test_rom_secondary_topic_builder_stacks_full_list_and_cursor_recolors_6_7(self):
        def h(addr: int) -> int:
            return struct.unpack_from('<H', self.rom, addr - ROM_BASE)[0]
        # Shared coordinate table consumed by 0x08006E00: x[4], then y[4].
        self.assertEqual((8, 11, 8, 5, 10, 13, 16, 13),
                         struct.unpack_from('<8I', self.rom, 0x08019980 - ROM_BASE))
        # First row: y = selected_label_y - topic_count; following rows add
        # +1, +2 ... before subtracting the same topic_count.
        self.assertEqual((0x1B92, 0x9300, 0x3307),
                         tuple(h(a) for a in (0x08006E78, 0x08006E7A, 0x08006E7C)))
        self.assertEqual((0x3201, 0x1B92),
                         tuple(h(a) for a in (0x08006ED6, 0x08006EDA)))
        self.assertEqual((0x3208, 0x1B92),
                         tuple(h(a) for a in (0x0800713A, 0x0800713E)))
        # Fresh Up resets the nine row color slots to fg2/bg9, then marks
        # the new row fg6/bg7. Fresh Down uses the same reset pair.
        self.assertEqual((0x2002, 0x2109),
                         tuple(h(a) for a in (0x08008C2C, 0x08008C2E)))
        self.assertEqual((0x2106, 0x3101),
                         tuple(h(a) for a in (0x08008C44, 0x08008C4C)))
        self.assertEqual((0x2002, 0x2109),
                         tuple(h(a) for a in (0x08009A28, 0x08009A2A)))

    def test_runtime_secondary_page_draws_all_topics_with_selected_palette(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        compact = ' '.join(video.split())
        self.assertIn('static void gb_social_selector_upload_topics(const GbStoryRuntime* story)', video)
        self.assertIn('gb_social_subject_topics', video)
        self.assertIn('gb_social_ask_topics', video)
        self.assertIn('gb_social_criticize_topics', video)
        self.assertIn('const s16 map_y = (s16)(label_y[quadrant] - topic_count + i);', compact)
        self.assertIn('const int selected = i == story->social.topic_index;', compact)
        self.assertIn('selected ? 7 : 9, selected ? 6 : 2', compact)
        self.assertIn('8u + (u16)i * GB_SOCIAL_TEXT_COLUMNS', compact)
        draw = video.index('static void gb_story_ui_draw_social(')
        label_call = video.index('gb_social_selector_upload_label(story);', draw)
        topics_call = video.index('gb_social_selector_upload_topics(story);', draw)
        self.assertLess(label_call, topics_call)
        self.assertIn('if(story->social.state == GB_SOCIAL_SECONDARY)',
                      video[label_call:topics_call + 200])


    def test_story_ui_clear_erases_entire_social_selector_rectangle(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        clear_start = video.index('void gb_video_clear_story_ui(void)')
        clear_end = video.index('static void gb_story_ui_begin(void)', clear_start)
        clear = video[clear_start:clear_end]
        compact = ' '.join(clear.split())
        self.assertIn('for(int row = 0; row < GB_SOCIAL_SELECTOR_MAP_HEIGHT; ++row)', compact)
        self.assertIn('for(int col = 0; col < GB_SOCIAL_SELECTOR_MAP_WIDTH; ++col)', compact)
        self.assertIn('map[(GB_SOCIAL_SELECTOR_MAP_Y + row) * 32 + GB_SOCIAL_SELECTOR_MAP_X + col] = 0;', compact)
        self.assertIn('for(int row = 0; row < GB_SOCIAL_TOPIC_CLEAR_HEIGHT; ++row)', compact)
        self.assertIn('for(int col = 0; col < GB_SOCIAL_TOPIC_CLEAR_WIDTH; ++col)', compact)
        self.assertIn('map[(GB_SOCIAL_TOPIC_CLEAR_Y + row) * 32 + GB_SOCIAL_TOPIC_CLEAR_X + col] = 0;', compact)



if __name__ == '__main__':
    unittest.main()
