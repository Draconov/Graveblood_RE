#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import extract_extended_semantics as semantics

ROM = Path(os.environ.get('GRAVEBLOOD_ROM', ROOT.parent / 'Graveblood 0.0.1.1.5.2 demo.gba'))


class DialogueAudioLatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = ROM.read_bytes()

    def test_extractor_exposes_dialogue_audio_latch_lifecycle(self):
        self.assertTrue(
            hasattr(semantics, 'extract_dialogue_audio_latch_semantics'),
            'missing ROM-backed dialogue-audio latch extractor',
        )
        rows = semantics.extract_dialogue_audio_latch_semantics(self.data)
        by_phase = {row['phase']: row for row in rows}
        self.assertEqual('0x0300062C', by_phase['constructor_clear']['latch'])
        self.assertEqual('0', str(by_phase['constructor_clear']['value_after']))
        self.assertEqual('SFX3@80', by_phase['state2_first_text']['sound'])
        self.assertEqual('1', str(by_phase['state2_first_text']['value_after']))
        self.assertEqual('SFX8@80', by_phase['state2_next_text']['sound'])
        self.assertEqual('SFX7@80 per record', by_phase['normal_control_-1_to_-4']['sound'])
        self.assertEqual('0', str(by_phase['normal_control_-1_to_-4']['value_after']))
        self.assertEqual('SFX3@80', by_phase['state4_first_text']['sound'])
        self.assertEqual('SFX8@80', by_phase['state4_next_text']['sound'])
        self.assertEqual('silent', by_phase['state4_selector_minus1']['sound'])
        self.assertEqual('0', str(by_phase['state4_selector_minus1']['value_after']))
        self.assertEqual('SFX7@80', by_phase['state4_terminal_-1_to_-3']['sound'])
        self.assertEqual('SFX13@80', by_phase['state4_terminal_-5']['sound'])
        self.assertEqual('8 independent one-shot slots', by_phase['mixer_multiplicity']['sound'])

    def test_checked_in_dialogue_audio_latch_csv_matches_extractor(self):
        self.assertTrue(
            hasattr(semantics, 'extract_dialogue_audio_latch_semantics'),
            'missing ROM-backed dialogue-audio latch extractor',
        )
        evidence = ROOT / 'data/dialogue_audio_latch_semantics.csv'
        self.assertTrue(evidence.exists(), 'missing dialogue audio latch evidence CSV')
        with evidence.open(newline='', encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        expected = semantics.extract_dialogue_audio_latch_semantics(self.data)
        self.assertEqual(
            [{key: str(value) for key, value in row.items()} for row in expected],
            rows,
        )


if __name__ == '__main__':
    unittest.main()
