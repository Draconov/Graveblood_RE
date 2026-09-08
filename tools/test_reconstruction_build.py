#!/usr/bin/env python3
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVKIT_IMAGE = 'devkitpro/devkitarm:20260610'
ROM_NAME = 'Graveblood_RE.gba'
DEV_TAG = 'Graveblood_RE_v0.0.1-dev'
DEV_RELEASE_ROM = 'Graveblood_RE_v0.0.1.gba'


class ReconstructionBuildScaffoldTests(unittest.TestCase):
    def test_cfa_devkitpro_project_files_exist(self):
        required = (
            'reconstruction/Makefile',
            'reconstruction/source/main.c',
            'reconstruction/source/engine/video.c',
            'reconstruction/source/engine/input.c',
            'reconstruction/source/engine/collision.c',
            'reconstruction/source/engine/portal.c',
            'reconstruction/source/engine/world.c',
            'reconstruction/source/game/player.c',
            'reconstruction/source/game/graveblood.c',
            'reconstruction/include/graveblood/assets.h',
            'reconstruction/include/graveblood/world.h',
            'reconstruction/README.md',
            'DEVELOPING_AND_BUILDING.md',
            '.github/workflows/build-release-rom.yml',
        )
        for rel in required:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_old_butano_runtime_and_notes_are_removed(self):
        self.assertFalse((ROOT / 'reconstruction/src/main.cpp').exists())
        self.assertFalse((ROOT / 'BUTANO_REBUILD_NOTES.md').exists())
        self.assertFalse((ROOT / 'docs/superpowers/specs/2026-09-07-graveblood-build-release-design.md').exists())
        self.assertFalse((ROOT / 'docs/superpowers/plans/2026-09-07-graveblood-build-release.md').exists())

    def test_makefile_uses_devkitarm_gba_rules_and_libgba(self):
        text = (ROOT / 'reconstruction/Makefile').read_text(encoding='utf-8')
        self.assertIn('TARGET := Graveblood_RE', text)
        self.assertIn('include $(DEVKITARM)/gba_rules', text)
        self.assertIn('LIBS := -lgba', text)
        self.assertIn('LIBDIRS := $(LIBGBA)', text)
        self.assertIn('SOURCES := source source/engine source/game data', text)
        self.assertIn('export PATH := $(DEVKITARM)/bin:$(PATH)', text)
        self.assertIn('-std=gnu11', text)
        self.assertNotIn('LIBBUTANO', text)
        self.assertNotIn('butano.mak', text)

    def test_runtime_is_mode0_cfa_style_and_not_mode3_debug_shell(self):
        combined = '\n'.join(
            p.read_text(encoding='utf-8')
            for p in (ROOT / 'reconstruction/source').rglob('*.c')
        )
        self.assertIn('MODE_0', combined)
        self.assertIn('BG0_ON', combined)
        self.assertIn('BG_256_COLOR', combined)
        self.assertIn('OAM', combined)
        self.assertIn('gb_world_load', combined)
        self.assertIn('gb_player_update', combined)
        self.assertIn('gb_portal_try_activate', combined)
        self.assertNotIn('MODE_3', combined)
        self.assertNotIn('alternate_backdrop', combined)
        self.assertNotIn('PRESS A TO START', combined)

    def test_runtime_has_real_level7_level8_slice(self):
        assets = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        world = (ROOT / 'reconstruction/source/engine/world.c').read_text(encoding='utf-8')
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('gb_level07_assets', assets)
        self.assertIn('gb_level08_assets', assets)
        self.assertIn('GB_LEVEL_07', game)
        self.assertIn('GB_LEVEL_08', game)
        self.assertIn('world_width_tiles', world)
        self.assertIn('BG_OFFSET[0]', world)

    def test_development_guide_is_devkitpro_only(self):
        text = (ROOT / 'DEVELOPING_AND_BUILDING.md').read_text(encoding='utf-8')
        self.assertIn('devkitPro', text)
        self.assertIn('devkitARM', text)
        self.assertIn('libgba', text)
        self.assertIn('make -C reconstruction -j4', text)
        self.assertIn('make -C reconstruction clean', text)
        self.assertIn(ROM_NAME, text)
        self.assertIn(DEV_TAG, text)
        self.assertIn(DEV_RELEASE_ROM, text)
        self.assertIn('mGBA', text)
        self.assertNotIn('GValiente/butano', text)
        self.assertNotIn('LIBBUTANO', text)

    def test_workspace_readme_describes_cfa_devkitpro_reconstruction(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('CFA', text)
        self.assertIn('devkitPro', text)
        self.assertIn('libgba', text)
        self.assertIn('Level 7', text)
        self.assertIn('Level 8', text)
        self.assertNotIn('clean-room C++/Butano project', text)
        self.assertNotIn('BUTANO_REBUILD_NOTES.md', text)

    def test_workflow_builds_directly_in_devkitpro_without_engine_checkout(self):
        path = ROOT / '.github/workflows/build-release-rom.yml'
        text = path.read_text(encoding='utf-8')
        self.assertIn(DEVKIT_IMAGE, text)
        self.assertIn('make -C reconstruction -j"$(nproc)"', text)
        self.assertIn(ROM_NAME, text)
        self.assertIn('name: Graveblood_RE-rom', text)
        self.assertIn('actions/upload-artifact@v4', text)
        self.assertIn('actions/download-artifact@v4', text)
        self.assertNotIn('repository: GValiente/butano', text)
        self.assertNotIn('path: vendor/butano', text)
        self.assertNotIn('LIBBUTANO', text)

    def test_workflow_releases_only_version_tags(self):
        text = (ROOT / '.github/workflows/build-release-rom.yml').read_text(encoding='utf-8')
        self.assertIn("startsWith(github.ref, 'refs/tags/Graveblood_RE_v')", text)
        self.assertIn("endsWith(github.ref, '-dev')", text)
        self.assertIn('Graveblood_RE_v${VERSION}.gba', text)
        self.assertIn('contents: write', text)
        self.assertIn('gh release create', text)
        self.assertIn('gh release upload', text)
        self.assertIn('--clobber', text)

    def test_no_obsolete_butano_reference_in_active_build_files(self):
        active = [
            ROOT / 'reconstruction/Makefile',
            ROOT / 'reconstruction/README.md',
            ROOT / 'DEVELOPING_AND_BUILDING.md',
            ROOT / '.github/workflows/build-release-rom.yml',
        ]
        for path in active:
            text = path.read_text(encoding='utf-8').lower()
            self.assertNotIn('butano', text, path)

    def test_generated_roms_and_build_outputs_are_gitignored(self):
        text = (ROOT / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('reconstruction/build/', text)
        self.assertIn('reconstruction/*.gba', text)
        self.assertIn('reconstruction/*.elf', text)
        self.assertIn('reconstruction/*.map', text)

    def test_input_poll_reports_held_and_rising_edge_dpad_bits(self):
        harness = r"""
#include <assert.h>
#include <graveblood/input.h>

volatile u16 gb_test_keyinput = 0x03FF;

int main(void)
{
    gb_input_reset();
    gb_test_keyinput = (u16)(0x03FFu & (u16)~KEY_RIGHT);
    GbInput first = gb_input_poll();
    assert((first.held & KEY_RIGHT) != 0);
    assert((first.pressed & KEY_RIGHT) != 0);

    GbInput held = gb_input_poll();
    assert((held.held & KEY_RIGHT) != 0);
    assert((held.pressed & KEY_RIGHT) == 0);

    gb_test_keyinput = 0x03FF;
    GbInput released = gb_input_poll();
    assert((released.held & KEY_RIGHT) == 0);
    return 0;
}
"""
        gba_h = r"""
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
extern volatile u16 gb_test_keyinput;
#define REG_KEYINPUT gb_test_keyinput
#define KEY_A      (1u << 0)
#define KEY_B      (1u << 1)
#define KEY_RIGHT  (1u << 4)
#define KEY_LEFT   (1u << 5)
#define KEY_UP     (1u << 6)
#define KEY_DOWN   (1u << 7)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'input_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'input_test'
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/input.c'),
                str(td / 'input_test.c'), '-o', str(exe),
            ], check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_level7_spawn_moves_on_zero_collision_cells_and_nonzero_blocks(self):
        harness = r"""
#include <assert.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/collision.h>
#include <graveblood/input.h>

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

int main(void)
{
    GbPlayer player;
    gb_player_spawn(&player, gb_level07_assets.spawn_x, gb_level07_assets.spawn_y);

    const s16 original_x = player.x;
    GbInput right = { .held = KEY_RIGHT, .pressed = KEY_RIGHT };
    gb_player_update(&player, &gb_level07_assets, &right);
    assert(player.x == original_x + 1);

    static const u16 blocked_grid[4] = { 14, 14, 14, 14 };
    GbLevelAssets blocked = gb_level07_assets;
    blocked.world_width_tiles = 2;
    blocked.world_height_tiles = 2;
    blocked.collision = blocked_grid;
    gb_player_spawn(&player, 8, 8);
    const s16 blocked_x = player.x;
    gb_player_update(&player, &blocked, &right);
    assert(player.x == blocked_x);
    return 0;
}
"""
        gba_h = r"""
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
#define KEY_A      (1u << 0)
#define KEY_B      (1u << 1)
#define KEY_RIGHT  (1u << 4)
#define KEY_LEFT   (1u << 5)
#define KEY_UP     (1u << 6)
#define KEY_DOWN   (1u << 7)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'movement_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'movement_test'
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(ROOT / 'reconstruction/data/level07_assets.c'),
                str(td / 'movement_test.c'), '-o', str(exe),
            ], check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_player_animation_preserves_timer_and_horizontal_facing_across_direction_changes(self):
        harness = r"""
#include <assert.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/input.h>

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

int main(void)
{
    static const u16 open_grid[16] = { 0 };
    GbLevelAssets level = { 0 };
    level.world_width_tiles = 4;
    level.world_height_tiles = 4;
    level.collision = open_grid;

    GbPlayer player;
    gb_player_spawn(&player, 16, 16);
    assert(player.animation_state == GB_PLAYER_ANIM_IDLE);
    assert(player.animation_frame == 1);
    assert(player.animation_countdown == 5);
    assert(player.facing_right == 0);
    assert(gb_player_frame_index(&player) == 12);

    GbInput right = { .held = KEY_RIGHT, .pressed = KEY_RIGHT };
    for(int i = 0; i < 6; ++i)
    {
        gb_player_update(&player, &level, &right);
    }
    assert(player.animation_state == GB_PLAYER_ANIM_WALK_REGULAR);
    assert(player.animation_frame == 2);
    assert(player.animation_countdown == 5);
    assert(player.facing_right == 1);
    assert(gb_player_frame_index(&player) == 1);

    GbInput up = { .held = KEY_UP, .pressed = KEY_UP };
    gb_player_update(&player, &level, &up);
    assert(player.animation_state == GB_PLAYER_ANIM_WALK_UP);
    assert(player.animation_frame == 2);
    assert(player.animation_countdown == 4);
    assert(player.facing_right == 1);
    assert(gb_player_frame_index(&player) == 7);

    GbInput idle = { 0 };
    gb_player_update(&player, &level, &idle);
    assert(player.animation_state == GB_PLAYER_ANIM_IDLE);
    assert(player.animation_frame == 2);
    assert(player.animation_countdown == 3);
    assert(player.facing_right == 1);
    assert(gb_player_frame_index(&player) == 13);
    return 0;
}
"""
        gba_h = r"""
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
#define KEY_A      (1u << 0)
#define KEY_B      (1u << 1)
#define KEY_RIGHT  (1u << 4)
#define KEY_LEFT   (1u << 5)
#define KEY_UP     (1u << 6)
#define KEY_DOWN   (1u << 7)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'animation_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'animation_test'
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(td / 'animation_test.c'), '-o', str(exe),
            ], check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_public_repo_identity_and_no_credits_file(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('Graveblood_RE', readme)
        self.assertFalse((ROOT / 'CREDITS.md').exists())


if __name__ == '__main__':
    unittest.main()
