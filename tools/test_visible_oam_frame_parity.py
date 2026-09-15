#!/usr/bin/env python3
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/graveblood_reference/Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000


class VisibleOamFrameParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = ROM.read_bytes()

    def test_rom_monster_branch_precedes_level9_level10_parked_bicycle_dispatch(self):
        # Player_draw begins by checking the fifth-sketch/monster global and
        # branches directly to 0x080068BC.  Bicycle mode and level 9/10 parked
        # composites are tested only afterwards, so they cannot coexist.
        half = lambda addr: struct.unpack_from('<H', self.rom, addr - ROM_BASE)[0]
        self.assertEqual(0x2B01, half(0x08006610))
        self.assertEqual(0xD100, half(0x08006612))
        self.assertEqual(0xE152, half(0x08006614))
        self.assertEqual(0x2B02, half(0x0800661E))
        self.assertEqual(0x2B09, half(0x08006626))
        self.assertEqual(0x2B0A, half(0x0800662C))

    def test_re_level10_monster_draw_suppresses_parked_bicycle_oam(self):
        gba_h = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16; typedef uint32_t u32; typedef int32_t s32;
typedef struct { volatile u16 x; volatile u16 y; } GbTestBgOffset;
extern volatile u16 gb_test_vcount, gb_test_dispcnt, gb_test_bgctrl[4];
extern volatile GbTestBgOffset gb_test_bg_offset[4];
extern volatile u16 gb_test_bg_colors[256], gb_test_obj_colors[256], gb_test_oam[512], gb_test_vram[0x18000 / 2];
#define REG_VCOUNT gb_test_vcount
#define REG_DISPCNT gb_test_dispcnt
#define BGCTRL gb_test_bgctrl
#define BG_OFFSET gb_test_bg_offset
#define BG_COLORS gb_test_bg_colors
#define OBJ_COLORS gb_test_obj_colors
#define OAM gb_test_oam
#define MAP_BASE_ADR(n) ((void*)(gb_test_vram + ((n) * 0x800 / 2)))
#define CHAR_BASE_ADR(n) ((void*)(gb_test_vram + ((n) * 0x4000 / 2)))
#define SPR_VRAM(n) ((void*)(gb_test_vram + 0x10000 / 2))
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
'''
        harness = r'''
#include <assert.h>
#include <graveblood/video.h>

volatile u16 gb_test_vcount, gb_test_dispcnt, gb_test_bgctrl[4];
volatile GbTestBgOffset gb_test_bg_offset[4];
volatile u16 gb_test_bg_colors[256], gb_test_obj_colors[256], gb_test_oam[512], gb_test_vram[0x18000 / 2];

const u16 gb_actor_obj_palette[GB_ACTOR_OBJ_PALETTE_COUNT] = {0};
const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT] = {0};
const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT] = {0};
const u16 gb_player_obj_palette[16] = {0};
const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * GB_PLAYER_FRAME_HALFWORDS] = {0};
const u16 gb_player_bicycle_obj_frames[GB_PLAYER_BICYCLE_FRAME_COUNT * GB_PLAYER_BICYCLE_FRAME_HALFWORDS] = {0};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {0};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {0};
const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT] = {{0,0}};
const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_MAX_FRAMES * GB_ACTOR_FRAME_HALFWORDS] = {0};
const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = {0};
const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {0};
const u16 gb_dialogue_portrait_obj_banks[GB_DIALOGUE_PORTRAIT_BANK_COUNT * GB_DIALOGUE_PORTRAIT_BANK_HALFWORDS] = {0};
static const u16 pal[256] = {0};

const GbDialogueRecord* gb_story_dialogue_record(const GbStoryRuntime* story) { (void)story; return 0; }
u8 gb_player_frame_index(const GbPlayer* player) { (void)player; return 0; }

int main(void)
{
    GbLevelAssets level = {0};
    GbPlayer player = {0};
    GbStoryRuntime story = {0};
    level.level_id = 10;
    level.bg_palette = pal;
    player.x = 720;
    player.y = 900;
    story.state.monster_render_enabled = 1;
    gb_video_load_level(&level);
    gb_video_draw_player_state(&player, &story, 680, 860);

    for(int i = 0; i < 5; ++i)
        assert((gb_test_oam[i * 4] & 0x00FF) != 160);
    for(int i = 5; i < 9; ++i)
        assert((gb_test_oam[i * 4] & 0x00FF) == 160);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'monster_oam.c').write_text(harness, encoding='utf-8')
            exe = td / 'monster_oam'
            proc = subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/video.c'),
                str(ROOT / 'reconstruction/data/social_selector_assets.c'),
                str(td / 'monster_oam.c'), '-Wl,--gc-sections', '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_oam_audit_compositor_hardware_rules(self):
        from tools.audit_visible_oam_frames import (
            ObjPiece, compose_obj_frame, decode_tiled_8bpp, oam_screen_x, oam_screen_y,
        )

        # Four 8x8 tiles laid out as one 16x16 OBJ.
        tiles = bytes([1] * 64 + [2] * 64 + [3] * 64 + [4] * 64)
        pixels = decode_tiled_8bpp(tiles, 16, 16)
        self.assertEqual(1, pixels[0])
        self.assertEqual(2, pixels[8])
        self.assertEqual(3, pixels[8 * 16])
        self.assertEqual(4, pixels[8 * 16 + 8])

        self.assertEqual(-8, oam_screen_x(0x1F8))
        self.assertEqual(-8, oam_screen_y(0xF8))

        palette = tuple(range(256))
        base = bytearray([0] * 64)
        base[0] = 5
        base[7] = 6
        front = ObjPiece('front', 8, 8, bytes(base), 20, 20, 1, 4, False)
        back = ObjPiece('back', 8, 8, bytes([7] * 64), 20, 20, 2, 0, False)
        frame = compose_obj_frame((back, front), palette)
        self.assertEqual(5, frame.colors[20 * 240 + 20])
        # Palette index 0 is transparent, so the lower-priority OBJ shows through.
        self.assertEqual(7, frame.colors[20 * 240 + 21])

        flipped = ObjPiece('flip', 8, 8, bytes(base), 40, 20, 1, 0, True)
        frame = compose_obj_frame((flipped,), palette)
        self.assertEqual(6, frame.colors[20 * 240 + 40])
        self.assertEqual(5, frame.colors[20 * 240 + 47])

        # Equal priority: lower OAM index wins.
        a = ObjPiece('a', 8, 8, bytes([8] * 64), 60, 20, 1, 2, False)
        b = ObjPiece('b', 8, 8, bytes([9] * 64), 60, 20, 1, 1, False)
        frame = compose_obj_frame((a, b), palette)
        self.assertEqual(9, frame.colors[20 * 240 + 60])
        self.assertEqual('b', frame.owners[20 * 240 + 60])

    def test_oam_audit_mismatch_attribution(self):
        from tools.audit_visible_oam_frames import ObjPiece, compare_frames, compose_obj_frame
        palette = tuple(range(256))
        expected = compose_obj_frame((ObjPiece('player', 8, 8, bytes([1] * 64), 10, 10, 2, 0, False),), palette)
        actual = compose_obj_frame((ObjPiece('player', 8, 8, bytes([2] * 64), 10, 10, 2, 0, False),), palette)
        diff = compare_frames(expected, actual)
        self.assertEqual(64, diff.mismatch_count)
        self.assertEqual((10, 10), (diff.first_x, diff.first_y))
        self.assertEqual('player', diff.expected_owner)
        self.assertEqual('player', diff.actual_owner)
        self.assertEqual('pixel_color', diff.classification)

    def test_visible_oam_checkpoint_coverage_and_zero_mismatch(self):
        from tools.audit_visible_oam_frames import run_audit
        rows = run_audit(ROOT, self.rom)
        families = {row.family for row in rows}
        self.assertEqual({
            'player', 'npc', 'grass', 'leaf', 'bicycle_riding',
            'bicycle_parked', 'monster',
        }, families)
        self.assertGreaterEqual(sum(row.family == 'player' for row in rows), 25)
        self.assertGreaterEqual(sum(row.family == 'npc' for row in rows), 41)
        self.assertEqual(4, sum(row.family == 'leaf' for row in rows))
        self.assertEqual(6, sum(row.family == 'bicycle_riding' for row in rows))
        self.assertEqual(2, sum(row.family == 'bicycle_parked' for row in rows))
        self.assertGreaterEqual(sum(row.family == 'monster' for row in rows), 4)
        mismatches = [row for row in rows if row.mismatch_count]
        self.assertEqual([], mismatches, [(row.name, row.mismatch_count, row.classification) for row in mismatches[:10]])

    def test_checked_in_player_asset_mutation_is_detected(self):
        from tools.audit_visible_oam_frames import run_audit
        rows = run_audit(ROOT, self.rom, mutation=('player', 0))
        affected = [row for row in rows if row.family == 'player' and row.mismatch_count]
        self.assertTrue(affected)
        self.assertIn(affected[0].classification, {'pixel_color', 'object_coverage_or_order'})

    def test_visible_oam_audit_cli_runs_from_repository_root(self):
        with tempfile.TemporaryDirectory() as td_raw:
            output = Path(td_raw) / 'visible_oam.csv'
            proc = subprocess.run([
                'python3', str(ROOT / 'tools/audit_visible_oam_frames.py'),
                '--root', str(ROOT), '--rom', str(ROM), '--output', str(output),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(output.is_file())
            self.assertIn('visible OBJ/OAM checkpoints; 0 mismatches', proc.stdout)

    def test_checked_in_obj_palette_mutation_is_detected(self):
        from tools.audit_visible_oam_frames import run_audit
        rows = run_audit(ROOT, self.rom, mutation=('palette', 8))
        affected = [row for row in rows if row.mismatch_count]
        self.assertTrue(affected)
        self.assertTrue(any(row.classification == 'pixel_color' for row in affected))

    def test_checked_visible_oam_csv_regenerates_byte_identically(self):
        from tools.audit_visible_oam_frames import run_audit, write_audit_csv
        with tempfile.TemporaryDirectory() as td_raw:
            out = Path(td_raw) / 'visible_oam_frame_parity.csv'
            write_audit_csv(run_audit(ROOT, self.rom), out)
            self.assertEqual(
                (ROOT / 'data/visible_oam_frame_parity.csv').read_bytes(),
                out.read_bytes(),
            )


if __name__ == '__main__':
    unittest.main()
