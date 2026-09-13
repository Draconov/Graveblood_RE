#!/usr/bin/env python3
"""ROM-backed gameplay OBJ-lighting parity tests."""
from __future__ import annotations

from pathlib import Path
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / 'reconstruction'
INCLUDE = RECON / 'include'
ROM_PATH = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000
OBJ_SOURCE = 0x08366E58
OBJ_LIGHTING_SOURCE_COUNT = 200
LIGHTING_TABLE = 0x08A8E26C
START_CLOCK = 48000

GBA_HEADER = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;
typedef struct { volatile u16 x; volatile u16 y; } GbTestBgOffset;
#define REG_VCOUNT (*(volatile u16*)0x04000006u)
#define REG_DISPCNT (*(volatile u16*)0x04000000u)
#define BGCTRL ((volatile u16*)0x04000008u)
#define BG_OFFSET ((volatile GbTestBgOffset*)0x04000010u)
#define BG_COLORS ((volatile u16*)0x05000000u)
#define OBJ_COLORS ((volatile u16*)0x05000200u)
#define OAM ((volatile u16*)0x07000000u)
#define MAP_BASE_ADR(n) ((void*)(uintptr_t)(0x06000000u + (unsigned)(n) * 0x800u))
#define CHAR_BASE_ADR(n) ((void*)(uintptr_t)(0x06000000u + (unsigned)(n) * 0x4000u))
#define SPR_VRAM(n) ((void*)(uintptr_t)(0x06010000u + (unsigned)(n) * 32u))
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
#define KEY_A 1u
#define KEY_B 2u
#define KEY_SELECT 4u
#define KEY_START 8u
#define KEY_RIGHT 16u
#define KEY_LEFT 32u
#define KEY_UP 64u
#define KEY_DOWN 128u
#define KEY_R 256u
#define KEY_L 512u
#endif
'''


def div0(n: int, d: int) -> int:
    q = abs(n) // abs(d)
    return -q if (n < 0) ^ (d < 0) else q


def lighting_params(clock: int) -> tuple[int, int, int, int, int]:
    table = [
        (1, 2, 20, 2, 12), (0, 1, 17, 2, 9), (1, 2, 24, 2, 10),
        (10, 10, 32, 4, 3), (18, 18, 21, 5, 1), (30, 30, 30, 10, 0),
        (29, 29, 28, 6, 2), (29, 29, 25, 5, 5), (13, 13, 22, 4, 7),
        (21, 16, 2, 3, 10), (5, 0, 8, 2, 8), (2, 0, 16, 2, 11),
        (1, 2, 20, 2, 12),
    ]
    hour = (clock // 3600) % 24
    slot = (hour - (hour & 1)) // 2
    factor = ((clock // 60) % 120) // 3
    a, b = table[slot], table[slot + 1]
    return tuple(a[i] + div0((b[i] - a[i]) * factor, 40) for i in range(5))


def transform_color(color: int, params: tuple[int, int, int, int, int]) -> int:
    c0, c1, c2, divisor, contrast = params
    scale = float(((contrast + 31) * 259.0) / ((259 - contrast) * 31.0))
    packed = 0
    for shift, target in ((0, c0), (5, c1), (10, c2)):
        source = (color >> shift) & 31
        adjusted = source + div0(target - source, divisor)
        value = int(float(adjusted - 16) * scale + 16.0)
        value = max(0, min(31, value))
        packed |= value << shift
    return packed


class GameplayLightingRomEvidenceTests(unittest.TestCase):
    def test_startup_clock_and_13_slot_lighting_table_match_rom(self):
        rom = ROM_PATH.read_bytes()
        clock = struct.unpack_from('<I', rom, 0xA8D804)[0]
        self.assertEqual(START_CLOCK, clock)
        records = [struct.unpack_from('<5i', rom, 0xA8E26C + i * 20) for i in range(13)]
        self.assertEqual((29, 29, 28, 6, 2), records[6])
        self.assertEqual((29, 29, 25, 5, 5), records[7])
        self.assertEqual(records[0], records[12])
        self.assertEqual((29, 29, 27, 6, 3), lighting_params(clock))

    def test_generated_assets_preserve_200_halfword_obj_lighting_source(self):
        header = (RECON / 'include/graveblood/assets.h').read_text(encoding='utf-8')
        source = (RECON / 'data/actor_sprite_data.c').read_text(encoding='utf-8')
        self.assertIn('GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT = 200', header)
        self.assertIn('gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT]', source)
        body = re.search(
            r'gb_actor_obj_lighting_source\[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT\]\s*=\s*\{(.*?)\};',
            source, re.S,
        )
        self.assertIsNotNone(body)
        values = [int(v, 16) for v in re.findall(r'0x[0-9A-Fa-f]{4}', body.group(1))]
        expected = struct.unpack_from('<200H', ROM_PATH.read_bytes(), OBJ_SOURCE - ROM_BASE)
        self.assertEqual(list(expected), values)


@unittest.skipUnless(sys.platform.startswith('linux'), 'literal GBA mmap validation requires Linux')
class GameplayLightingRuntimeTests(unittest.TestCase):
    def test_level_load_full_transform_and_first_four_entry_tick_match_reference(self):
        params0 = lighting_params(START_CLOCK)
        params1 = lighting_params(START_CLOCK + 1)
        # Pair 4/5 must source from the level BG palette, not the OBJ source.
        expected0 = transform_color(0x1234, params0)
        expected4 = transform_color(0x001F, params0)
        expected5 = transform_color(0x03E0, params0)
        # Pair 200/201 also comes from the level BG palette.
        expected200 = transform_color(0x7C00, params0)
        # First Player-update lighting tick advances cursor 0 -> 4 and clock 48000 -> 48001.
        expected4_tick = transform_color(0x001F, params1)
        expected5_tick = transform_color(0x03E0, params1)

        harness = f'''\
#define _GNU_SOURCE
#include <assert.h>
#include <string.h>
#include <sys/mman.h>
#include <graveblood/video.h>

const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT] = {{ [24] = 0x1111, [31] = 0x2222 }};
const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT] = {{
    [0] = 0x1234, [4] = 0x7FFF, [5] = 0x7FFF, [8] = 0x4210, [199] = 0x2D6B
}};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {{0}};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {{0}};
const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = {{0}};
const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {{0}};

static u16 bg_palette[256];
static const u16 dummy[1] = {{0}};
static GbLevelAssets level = {{
    .level_id = 7, .graphics_variant = 0,
    .world_width_tiles = 29, .world_height_tiles = 24,
    .fixed_width_tiles = 0, .fixed_height_tiles = 0,
    .bg_tile_halfwords = 0, .translation_count = 1,
    .bg_palette = bg_palette, .bg_tiles = dummy, .translation = dummy,
    .layer_a = dummy, .layer_b = dummy, .fixed_map = dummy, .collision = dummy,
}};

static void map_region(unsigned long address, unsigned long size) {{
    void* p = mmap((void*)address, size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(p == (void*)address); memset(p, 0, size);
}}

int main(void) {{
    map_region(0x04000000u, 0x2000); map_region(0x05000000u, 0x1000);
    map_region(0x06000000u, 0x18000); map_region(0x07000000u, 0x1000);
    bg_palette[4] = 0x001F; bg_palette[5] = 0x03E0;
    bg_palette[200] = 0x7C00; bg_palette[201] = 0x4210;
    gb_video_init();
    gb_video_load_level(&level);
    assert(OBJ_COLORS[0] == 0x{expected0:04X});
    assert(OBJ_COLORS[4] == 0x{expected4:04X});
    assert(OBJ_COLORS[5] == 0x{expected5:04X});
    assert(OBJ_COLORS[200] == 0x{expected200:04X});
    assert(OBJ_COLORS[248] == 0x1111); /* outside initial 0..247 transform */
    assert(OBJ_COLORS[255] == 0x2222);
    OBJ_COLORS[4] = OBJ_COLORS[5] = 0;
    gb_video_gameplay_lighting_tick(1);
    assert(OBJ_COLORS[4] == 0x{expected4_tick:04X});
    assert(OBJ_COLORS[5] == 0x{expected5_tick:04X});
    return 0;
}}
'''
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_HEADER, encoding='utf-8')
            hp = td / 'lighting.c'; hp.write_text(harness, encoding='utf-8')
            exe = td / 'lighting'
            cmd = [
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections', '-I', str(td), '-I', str(INCLUDE),
                str(RECON / 'source/engine/video.c'), str(hp), '-Wl,--gc-sections', '-o', str(exe),
            ]
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            proc = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)

    def test_player_construction_reset_restarts_cursor_but_not_clock(self):
        params_after_tick = lighting_params(START_CLOCK + 1)
        expected4 = transform_color(0x001F, params_after_tick)

        harness = f'''\
#define _GNU_SOURCE
#include <assert.h>
#include <string.h>
#include <sys/mman.h>
#include <graveblood/video.h>

const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT] = {{0}};
const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT] = {{
    [4] = 0x001F, [8] = 0x03E0
}};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {{0}};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {{0}};
const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = {{0}};
const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {{0}};

static u16 bg_palette[256];
static const u16 dummy[1] = {{0}};
static GbLevelAssets level = {{
    .level_id = 7, .graphics_variant = 0,
    .world_width_tiles = 29, .world_height_tiles = 24,
    .fixed_width_tiles = 0, .fixed_height_tiles = 0,
    .bg_tile_halfwords = 0, .translation_count = 1,
    .bg_palette = bg_palette, .bg_tiles = dummy, .translation = dummy,
    .layer_a = dummy, .layer_b = dummy, .fixed_map = dummy, .collision = dummy,
}};

static void map_region(unsigned long address, unsigned long size) {{
    void* p = mmap((void*)address, size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(p == (void*)address); memset(p, 0, size);
}}

int main(void) {{
    map_region(0x04000000u, 0x2000); map_region(0x05000000u, 0x1000);
    map_region(0x06000000u, 0x18000); map_region(0x07000000u, 0x1000);
    bg_palette[4] = 0x001F;
    gb_video_init();
    gb_video_load_level(&level);

    /* First Player update advances cursor 0 -> 4 and world clock 48000 -> 48001. */
    gb_video_gameplay_lighting_tick(1);

    /* Canonical level reconstruction creates a fresh Player; Player+0x398 is
       constructor-zeroed, while the global day/night clock survives. */
    gb_video_load_level(&level);
    gb_video_gameplay_lighting_reset_cursor();
    OBJ_COLORS[4] = 0;
    OBJ_COLORS[8] = 0x7777;
    gb_video_gameplay_lighting_tick(0);
    assert(OBJ_COLORS[4] == 0x{expected4:04X});
    assert(OBJ_COLORS[8] == 0x7777);
    return 0;
}}
'''
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_HEADER, encoding='utf-8')
            hp = td / 'lighting_reload.c'; hp.write_text(harness, encoding='utf-8')
            exe = td / 'lighting_reload'
            cmd = [
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections', '-I', str(td), '-I', str(INCLUDE),
                str(RECON / 'source/engine/video.c'), str(hp), '-Wl,--gc-sections', '-o', str(exe),
            ]
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            proc = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)

    def test_cursor_continues_while_clock_pauses_and_never_touches_252_255(self):
        params = lighting_params(START_CLOCK)
        expected4 = transform_color(0x001F, params)
        expected248 = transform_color(0x4210, params)
        expected0 = transform_color(0x1234, params)

        harness = f'''\
#define _GNU_SOURCE
#include <assert.h>
#include <string.h>
#include <sys/mman.h>
#include <graveblood/video.h>

const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT] = {{ [24] = 0x4210, [28] = 0x5555, [31] = 0x6666 }};
const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT] = {{
    [0] = 0x1234, [4] = 0x001F, [136] = 0x03E0
}};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {{0}};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {{0}};
const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = {{0}};
const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {{0}};

static u16 bg_palette[256];
static const u16 dummy[1] = {{0}};
static GbLevelAssets level = {{
    .level_id = 7, .graphics_variant = 0,
    .world_width_tiles = 29, .world_height_tiles = 24,
    .fixed_width_tiles = 0, .fixed_height_tiles = 0,
    .bg_tile_halfwords = 0, .translation_count = 1,
    .bg_palette = bg_palette, .bg_tiles = dummy, .translation = dummy,
    .layer_a = dummy, .layer_b = dummy, .fixed_map = dummy, .collision = dummy,
}};

static void map_region(unsigned long address, unsigned long size) {{
    void* p = mmap((void*)address, size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(p == (void*)address); memset(p, 0, size);
}}

int main(void) {{
    map_region(0x04000000u, 0x2000); map_region(0x05000000u, 0x1000);
    map_region(0x06000000u, 0x18000); map_region(0x07000000u, 0x1000);
    bg_palette[4] = 0x001F; bg_palette[5] = 0x03E0;
    bg_palette[248] = 0x4210; bg_palette[249] = 0x4210;
    gb_video_init();
    gb_video_load_level(&level);

    /* Interaction-active Player_update pauses the world clock, but still
       advances Player+0x398 and refreshes four OBJ palette entries. */
    OBJ_COLORS[4] = 0;
    gb_video_gameplay_lighting_tick(0);
    assert(OBJ_COLORS[4] == 0x{expected4:04X});

    /* Tick 62 reaches cursor 248 and updates only 248..251. */
    for(int i = 1; i < 62; ++i) gb_video_gameplay_lighting_tick(0);
    assert(OBJ_COLORS[248] == 0x{expected248:04X});
    assert(OBJ_COLORS[252] == 0x5555);
    assert(OBJ_COLORS[255] == 0x6666);

    /* Tick 63 wraps the amortized cursor to 0..3, still at the same clock. */
    OBJ_COLORS[0] = 0;
    gb_video_gameplay_lighting_tick(0);
    assert(OBJ_COLORS[0] == 0x{expected0:04X});
    assert(OBJ_COLORS[252] == 0x5555);
    assert(OBJ_COLORS[255] == 0x6666);
    return 0;
}}
'''
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_HEADER, encoding='utf-8')
            hp = td / 'lighting_pause.c'; hp.write_text(harness, encoding='utf-8')
            exe = td / 'lighting_pause'
            cmd = [
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections', '-I', str(td), '-I', str(INCLUDE),
                str(RECON / 'source/engine/video.c'), str(hp), '-Wl,--gc-sections', '-o', str(exe),
            ]
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            proc = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)


if __name__ == '__main__':
    unittest.main()
