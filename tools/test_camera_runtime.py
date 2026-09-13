#!/usr/bin/env python3
from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_BASE = 0x08000000
ROM_SHA256 = "e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b"


def rom_path() -> Path:
    value = os.environ.get("GRAVEBLOOD_ROM")
    if not value:
        raise unittest.SkipTest("GRAVEBLOOD_ROM is required")
    return Path(value)


def read_u16(data: bytes, addr: int) -> int:
    return struct.unpack_from("<H", data, addr - ROM_BASE)[0]


def read_u32(data: bytes, addr: int) -> int:
    return struct.unpack_from("<I", data, addr - ROM_BASE)[0]


class CameraRuntimeTests(unittest.TestCase):
    def test_rom_camera_tracker_uses_deadzone_and_30x20_clamp(self):
        import hashlib

        data = rom_path().read_bytes()
        self.assertEqual(ROM_SHA256, hashlib.sha256(data).hexdigest())

        tracker = [read_u16(data, 0x08006550 + i * 2) for i in range(40)]
        self.assertEqual(
            [
                0x6882, 0x4694, 0x6903, 0x105B, 0x4463, 0x121B, 0xB510, 0x001C,
                0x490F, 0x680A, 0x3C90, 0x42A2, 0xDA01, 0x0022, 0x600C, 0x3B60,
                0x4293, 0xDA00, 0x600B, 0x6943, 0x105A, 0x68C3, 0x1A9B, 0x121B,
                0x0018, 0x4908, 0x680A, 0x385D, 0x4282, 0xDA01, 0x0002, 0x6008,
                0x3B43, 0x4293, 0xDA00, 0x600B, 0xBC10, 0xBC01, 0x4700, 0x46C0,
            ],
            tracker,
        )
        self.assertEqual(0x03000570, read_u32(data, 0x080065A0))
        self.assertEqual(0x0300056C, read_u32(data, 0x080065A4))

        clamp = [read_u16(data, 0x0800A2D4 + i * 2) for i in range(32)]
        self.assertEqual(0x3A1E, clamp[11], "camera X clamp must subtract 30 tiles")
        self.assertEqual(0x3B14, clamp[20], "camera Y clamp must subtract 20 tiles")
        self.assertEqual(0x0300056C, read_u32(data, 0x0800A31C))
        self.assertEqual(0x03000570, read_u32(data, 0x0800A320))
        self.assertEqual(0x03000548, read_u32(data, 0x0800A324))
        self.assertEqual(0x0300054C, read_u32(data, 0x0800A328))
        self.assertEqual(0x030006C4, read_u32(data, 0x0800A32C))

    def test_world_camera_follows_rom_deadzone_and_persists_across_level_loads(self):
        harness = r'''\
#include <graveblood/world.h>
#include <stdio.h>

static int full_count;
static int column_count;
static int row_count;
static int last_a;
static int last_b;
static s16 last_camera_x;
static s16 last_camera_y;

void gb_video_load_level(const GbLevelAssets* level) { (void) level; }
void gb_video_set_camera(s16 x, s16 y) { last_camera_x = x; last_camera_y = y; }
void gb_video_stream_full(const GbLevelAssets* level, s16 left, s16 top)
{ (void)level; ++full_count; last_a = left; last_b = top; }
void gb_video_stream_column(const GbLevelAssets* level, s16 world_x, s16 top)
{ (void)level; ++column_count; last_a = world_x; last_b = top; }
void gb_video_stream_row(const GbLevelAssets* level, s16 left, s16 world_y)
{ (void)level; ++row_count; last_a = left; last_b = world_y; }

static int require(int condition, const char* message)
{
    if(! condition) { fputs(message, stderr); fputc('\n', stderr); return 0; }
    return 1;
}

int main(void)
{
    GbLevelAssets level_a = {0};
    GbLevelAssets level_b = {0};
    level_a.world_width_tiles = 100;
    level_a.world_height_tiles = 100;
    level_b.world_width_tiles = 80;
    level_b.world_height_tiles = 60;

    GbWorld world = {0};
    gb_world_load(&world, &level_a);
    if(!require(world.camera_x == 0 && world.camera_y == 0, "zero seed")) return 1;

    gb_world_update_camera(&world, 120, 88); /* center 128,80: inside ROM dead-zone */
    if(!require(world.camera_x == 0 && world.camera_y == 0, "initial dead-zone")) return 1;
    if(!require(full_count == 1 && column_count == 0 && row_count == 0, "initial full fill")) return 1;

    gb_world_update_camera(&world, 128, 88); /* center 136,80: still inside */
    if(!require(world.camera_x == 0 && world.camera_y == 0, "x must not snap to center")) return 1;
    if(!require(column_count == 0 && row_count == 0, "no stream before dead-zone edge")) return 1;

    gb_world_update_camera(&world, 144, 88); /* center 152 => camera X 8 */
    if(!require(world.camera_x == 8 && world.camera_y == 0, "right dead-zone follow")) return 1;
    if(!require(column_count == 1 && world.stream_tile_x == 1, "one-tile x stream")) return 1;

    gb_world_update_camera(&world, 144, 109); /* center Y 101 => camera Y 8 */
    if(!require(world.camera_x == 8 && world.camera_y == 8, "bottom dead-zone follow")) return 1;
    if(!require(row_count == 1 && world.stream_tile_y == 1, "one-tile y stream")) return 1;

    gb_world_update_camera(&world, 200, 109); /* center X 208 => camera X 64 */
    if(!require(world.camera_x == 64 && world.camera_y == 8, "large right follow")) return 1;
    if(!require(full_count == 1 && column_count == 8, "seven-tile movement stays incremental")) return 1;

    gb_world_update_camera(&world, 140, 109); /* center X 148 < camera+96 => camera X 52 */
    if(!require(world.camera_x == 52 && world.camera_y == 8, "left dead-zone follow")) return 1;

    /* Scene load invalidates streaming, but original camera globals persist. */
    gb_world_load(&world, &level_b);
    if(!require(world.camera_x == 52 && world.camera_y == 8, "level load must preserve camera")) return 1;
    if(!require(world.stream_valid == 0, "level load must invalidate stream")) return 1;
    if(!require(last_camera_x == 52 && last_camera_y == 8, "video camera must preserve load position")) return 1;

    /* center=(160,80) sits exactly at the persisted left/top dead-zone interior. */
    gb_world_update_camera(&world, 152, 88);
    if(!require(world.camera_x == 52 && world.camera_y == 8, "persisted dead-zone must remain stable")) return 1;

    /* Clamp against the 30x20 tile viewport bounds. */
    gb_world_update_camera(&world, 5000, 5000);
    if(!require(world.camera_x == (80 - 30) * 8, "right world clamp")) return 1;
    if(!require(world.camera_y == (60 - 20) * 8, "bottom world clamp")) return 1;
    gb_world_update_camera(&world, -1000, -1000);
    if(!require(world.camera_x == 0 && world.camera_y == 0, "top-left world clamp")) return 1;

    /* Level 7 is narrower than the 30-tile viewport.  The ROM first
       clamps the tracked camera to >= 0, then applies the signed maximum
       (29 - 30) * 8, so the published camera is deliberately -8. */
    GbLevelAssets narrow = {0};
    narrow.world_width_tiles = 29;
    narrow.world_height_tiles = 24;
    GbWorld narrow_world = {0};
    gb_world_load(&narrow_world, &narrow);
    gb_world_update_camera(&narrow_world, 147, 125);
    if(!require(narrow_world.camera_x == -8 && narrow_world.camera_y == 24,
                "Level 7 signed viewport clamp")) return 1;
    if(!require(narrow_world.stream_tile_x == -1 && narrow_world.stream_tile_y == 3,
                "Level 7 negative stream origin")) return 1;
    return 0;
}
'''
        gba_h = r'''\
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
#endif
'''
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / "gba.h").write_text(gba_h, encoding="utf-8")
            (td / "camera_test.c").write_text(harness, encoding="utf-8")
            exe = td / "camera_test"
            proc = subprocess.run(
                [
                    "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-I", str(td), "-I", str(ROOT / "reconstruction/include"),
                    str(ROOT / "reconstruction/source/engine/world.c"),
                    str(td / "camera_test.c"), "-o", str(exe),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stdout + run.stderr)

    def test_game_zero_initializes_persistent_world_camera_state(self):
        game = (ROOT / "reconstruction/source/game/graveblood.c").read_text(encoding="utf-8")
        self.assertIn("GbWorld world = {0};", game)

    def test_camera_semantics_csv_matches_rom_extractor(self):
        import csv
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "extract_extended_semantics_camera", ROOT / "tools/extract_extended_semantics.py"
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, "extract_camera_runtime_semantics"))
        expected = mod.extract_camera_runtime_semantics(rom_path().read_bytes())
        by_fact = {row["fact"]: row for row in expected}
        self.assertEqual("96..144 px", by_fact["horizontal_deadzone"]["value"])
        self.assertEqual("67..93 px", by_fact["vertical_deadzone"]["value"])
        self.assertEqual("30x20 tiles", by_fact["camera_clamp_viewport"]["value"])
        self.assertEqual("camera_x>>3,camera_y>>3", by_fact["stream_origin"]["value"])
        self.assertEqual("preserved", by_fact["scene_transition_camera"]["value"])
        csv_path = ROOT / "data/camera_runtime_semantics.csv"
        self.assertTrue(csv_path.is_file())
        with csv_path.open(newline="", encoding="utf-8") as handle:
            actual = list(csv.DictReader(handle))
        normalized = [{key: str(value) for key, value in row.items()} for row in expected]
        self.assertEqual(normalized, actual)



if __name__ == "__main__":
    unittest.main()
