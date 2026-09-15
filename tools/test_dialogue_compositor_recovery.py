#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_generator():
    path = ROOT / 'tools/generate_cfa_assets.py'
    spec = importlib.util.spec_from_file_location('generate_cfa_assets_dialogue_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DialogueCompositorRecoveryTests(unittest.TestCase):
    def test_dynamic_ui_scratch_never_reuses_dialogue_border_tiles(self):
        mod = load_generator()
        runtime = mod.RuntimeBackground(
            palette=(0,) * 256,
            tile_bytes=b'', patch_source_bytes=b'',
            translation=tuple(range(900)),
            layer_a=(), layer_b=(), layer_a_guard=(), layer_b_guard=(), fixed_map=(),
        )
        selected = mod.select_bg0_ui_tiles(runtime, 80)
        self.assertTrue({3, 4, 5}.isdisjoint(selected), selected[:12])

    def test_dialogue_writer_preflights_whole_words_and_uses_rom_separator(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        self.assertIn('static int gb_dialogue_ui_word_width(const char* text)', video)
        self.assertIn('const int word_width = gb_dialogue_ui_word_width(text);', video)
        self.assertIn("if(code == ' ')", video)
        self.assertIn("if(*x == 0)", video)
        self.assertIn('gb_dialogue_ui_text(":                              ", &x, &y);', video)
        speaker = video.index('gb_dialogue_ui_text(record->speaker, &x, &y);')
        text = video.index('gb_dialogue_ui_text(record->text, &x, &y);', speaker)
        self.assertNotIn('gb_dialogue_ui_newline(&x, &y);', video[speaker:text])

    def test_social_response_uses_shifted_normal_dialogue_window_and_is_fully_cleared(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        self.assertIn('#define GB_SOCIAL_RESPONSE_WINDOW_MAP_X 5', video)
        self.assertIn('#define GB_SOCIAL_RESPONSE_WINDOW_MAP_Y 13', video)
        self.assertIn('gb_dialogue_ui_upload_at(GB_SOCIAL_RESPONSE_WINDOW_MAP_X,', video)
        self.assertIn('gb_dialogue_ui_text(profile, &x, &y);', video)
        self.assertIn('gb_dialogue_ui_text(":                              ", &x, &y);', video)
        self.assertIn('GB_SOCIAL_RESPONSE_WINDOW_MAP_X + col', video)


if __name__ == '__main__':
    unittest.main()
