#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = 'e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b'
AUDIT = ROOT / 'tools' / 'audit_bg_state.py'


def rom_path() -> Path:
    value = os.environ.get('GRAVEBLOOD_ROM')
    if not value:
        raise unittest.SkipTest('GRAVEBLOOD_ROM is required')
    return Path(value)


def load_audit_module():
    spec = importlib.util.spec_from_file_location('audit_bg_state', AUDIT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GBA_H = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef int8_t s8; typedef uint8_t u8; typedef int16_t s16; typedef uint16_t u16;
typedef int32_t s32; typedef uint32_t u32;
#endif
'''

HARNESS = r'''
#include <stdio.h>
#include <graveblood/stream.h>

static int require(int ok, const char* msg)
{
    if(!ok) { fputs(msg, stderr); fputc('\n', stderr); return 0; }
    return 1;
}

int main(void)
{
    /* Reachable canonical stream cells span -1 through N+width.  The clean-room
       asset stores already-translated guard values for exactly those cells. */
    static const u16 translation[] = { 0, 11, 22, 33, 44, 55 };
    static const u16 layer_a[] = { 1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 1, 2 };
    static const u16 layer_b[] = { 5, 4, 3, 2, 1, 5, 4, 3, 2, 1, 5, 4 };
    /* width=4 => guard cells are [-1, N, N+1, N+2, N+3, N+4]. */
    static const u16 guard_a[] = { 0x1111, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666 };
    static const u16 guard_b[] = { 0xAAAA, 0xBBBB, 0xCCCC, 0xDDDD, 0xEEEE, 0xFFFF };
    GbLevelAssets level = {0};
    level.world_width_tiles = 4;
    level.world_height_tiles = 3;
    level.translation = translation;
    level.translation_count = 6;
    level.layer_a = layer_a;
    level.layer_b = layer_b;
    level.layer_a_guard = guard_a;
    level.layer_b_guard = guard_b;

    if(!require(gb_stream_entry(&level, layer_a, 0, 0) == 11, "normal A")) return 1;
    if(!require(gb_stream_entry(&level, layer_b, 0, 0) == 55, "normal B")) return 1;
    if(!require(gb_stream_entry(&level, layer_a, -1, 0) == 0x1111, "pre-guard A")) return 1;
    if(!require(gb_stream_entry(&level, layer_b, -1, 0) == 0xAAAA, "pre-guard B")) return 1;
    if(!require(gb_stream_entry(&level, layer_a, 0, 3) == 0x2222, "post-guard A N")) return 1;
    if(!require(gb_stream_entry(&level, layer_b, 4, 3) == 0xFFFF, "post-guard B N+width")) return 1;
    /* Values outside the only camera-reachable unchecked range remain fail-closed. */
    if(!require(gb_stream_entry(&level, layer_a, -2, 0) == 0, "far-before")) return 1;
    if(!require(gb_stream_entry(&level, layer_a, 5, 3) == 0, "far-after")) return 1;
    return 0;
}
'''


class BgStateParityTests(unittest.TestCase):
    def test_canonical_bg_state_audit_reports_zero_clean_room_mismatches(self):
        self.assertTrue(AUDIT.is_file(), AUDIT)
        data = rom_path().read_bytes()
        self.assertEqual(ROM_SHA256, hashlib.sha256(data).hexdigest())
        audit = load_audit_module()
        rows = audit.build_bg_state_report(ROOT, data)
        self.assertGreaterEqual(len(rows), 13)
        mismatches = [row for row in rows if int(row['mismatch_bytes']) != 0]
        self.assertEqual([], mismatches)
        levels = {(int(row['level']), int(row['variant'])) for row in rows if row['state_type'] == 'initial'}
        self.assertEqual(13, len(levels))
        guard_rows = [row for row in rows if row['state_type'] == 'stream_guard']
        self.assertEqual(22, len(guard_rows))
        patch_rows = [row for row in rows if row['state_type'] == 'fgtile_patch']
        self.assertGreater(len(patch_rows), 0)

    def test_checked_in_report_is_reproducible(self):
        self.assertTrue(AUDIT.is_file(), AUDIT)
        report = ROOT / 'data' / 'bg_state_parity.csv'
        self.assertTrue(report.is_file(), report)
        audit = load_audit_module()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'bg_state_parity.csv'
            audit.write_bg_state_report(ROOT, rom_path().read_bytes(), out)
            self.assertEqual(report.read_bytes(), out.read_bytes())

    def test_stream_runtime_preserves_reachable_unchecked_guard_cells(self):
        cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
        self.assertIsNotNone(cc)
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'stream_guard_test'
            built = subprocess.run(
                [
                    cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                    str(ROOT / 'reconstruction/source/engine/stream.c'),
                    str(td / 'harness.c'), '-o', str(exe),
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, built.returncode, built.stdout + built.stderr)
            ran = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, ran.returncode, ran.stdout + ran.stderr)


if __name__ == '__main__':
    unittest.main()
