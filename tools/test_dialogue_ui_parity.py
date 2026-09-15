#!/usr/bin/env python3
from __future__ import annotations
import csv
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
        self.assertIn('map[window_y * 32 + window_x] = GB_DIALOGUE_BORDER_CORNER_TILE;', video)
        self.assertIn('window_x + GB_DIALOGUE_WINDOW_COLUMNS - 1', video)
        self.assertIn('window_y + GB_DIALOGUE_WINDOW_ROWS - 1', video)
        self.assertIn('GB_BG_MAP_HFLIP', video)
        self.assertIn('GB_BG_MAP_VFLIP', video)

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
