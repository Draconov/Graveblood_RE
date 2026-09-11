#!/usr/bin/env python3
import re
import shutil
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
            'reconstruction/source/engine/audio.c',
            'reconstruction/source/engine/portal.c',
            'reconstruction/source/engine/world.c',
            'reconstruction/source/engine/stream.c',
            'reconstruction/source/game/player.c',
            'reconstruction/source/game/actors.c',
            'reconstruction/source/game/graveblood.c',
            'reconstruction/source/game/ending.c',
            'reconstruction/source/game/wardrobe.c',
            'reconstruction/include/graveblood/assets.h',
            'reconstruction/include/graveblood/ending.h',
            'reconstruction/include/graveblood/wardrobe.h',
            'reconstruction/include/graveblood/audio.h',
            'reconstruction/include/graveblood/actors.h',
            'reconstruction/data/actor_data.c',
            'reconstruction/data/actor_routes.c',
            'reconstruction/data/actor_sprite_data.c',
            'reconstruction/data/audio_data.c',
            'reconstruction/data/audio_samples.s',
            'reconstruction/data/ending_effect.s',
            'reconstruction/data/ending/argument0_copy1.bin',
            'reconstruction/data/ending/argument0_copy2.bin',
            'reconstruction/data/wardrobe_assets.c',
            'reconstruction/data/audio/sample_00.pcm',
            'reconstruction/data/audio/sample_13.pcm',
            'reconstruction/include/graveblood/world.h',
            'reconstruction/include/graveblood/stream.h',
            'reconstruction/README.md',
            'DEVELOPING_AND_BUILDING.md',
            '.github/workflows/build-release-rom.yml',
        )
        for rel in required:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_reachable_final_effect_replays_exact_argument0_vram_copy_before_draw(self):
        ending = ROOT / 'reconstruction/source/game/ending.c'
        header = ROOT / 'reconstruction/include/graveblood/ending.h'
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        video_h = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertTrue(ending.is_file(), ending)
        self.assertTrue(header.is_file(), header)
        etext = ending.read_text(encoding='utf-8')
        self.assertIn('GB_ENDING_ARG0_COPY1_BYTES', etext)
        self.assertIn('GB_ENDING_ARG0_COPY2_BYTES', etext)
        self.assertIn('GB_ENDING_OBJ_VRAM_OFFSET', etext)
        self.assertIn('gb_ending_arg0_copy1', etext)
        self.assertIn('gb_ending_arg0_copy2', etext)
        self.assertIn('void gb_video_apply_final_effect(void)', video)
        self.assertIn('gb_ending_apply_argument0((volatile u8*)0x06000000)', video)
        self.assertIn('void gb_video_apply_final_effect(void);', video_h)
        self.assertIn('if(story.state.final_effect_pending)', game)
        self.assertIn('gb_video_apply_final_effect();', game)
        effect_index = game.index('gb_video_apply_final_effect();')
        frame_camera_index = game.index('gb_world_update_camera(&world, player.x, player.y);', effect_index)
        self.assertLess(effect_index, frame_camera_index)

        gba_h = '''\n#ifndef GBA_H\n#define GBA_H\n#include <stdint.h>\ntypedef uint8_t u8;\ntypedef int8_t s8;\ntypedef uint16_t u16;\ntypedef int16_t s16;\ntypedef uint32_t u32;\ntypedef int32_t s32;\n#endif\n'''
        harness = '''\n#include <assert.h>\n#include <string.h>\n#include <graveblood/assets.h>\n#include <graveblood/ending.h>\n\nconst u8 gb_ending_arg0_copy1[GB_ENDING_ARG0_COPY1_BYTES] = {\n    [0] = 0x11, [0x10000] = 0x22, [0x13E80] = 0x66,\n    [GB_ENDING_ARG0_COPY1_BYTES - 1] = 0x33\n};\nconst u8 gb_ending_arg0_copy2[GB_ENDING_ARG0_COPY2_BYTES] = {\n    [0] = 0x44, [GB_ENDING_ARG0_COPY2_BYTES - 1] = 0x55\n};\n\nint main(void)\n{\n    static u8 vram[GB_ENDING_VRAM_BYTES];\n    memset(vram, 0xAA, sizeof(vram));\n    gb_ending_apply_argument0(vram);\n    assert(vram[0] == 0x11);\n    assert(vram[GB_ENDING_OBJ_VRAM_OFFSET] == 0x44);\n    assert(vram[GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES - 1] == 0x55);\n    assert(vram[0x13E80] == 0x66);\n    assert(vram[GB_ENDING_ARG0_COPY1_BYTES - 1] == 0x33);\n    assert(vram[GB_ENDING_ARG0_COPY1_BYTES] == 0xAA);\n    assert(vram[GB_ENDING_VRAM_BYTES - 1] == 0xAA);\n    return 0;\n}\n'''
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'ending_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'ending_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ending), str(td / 'ending_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)

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

    def test_makefile_exposes_project_headers_to_angle_bracket_includes(self):
        text = (ROOT / 'reconstruction/Makefile').read_text(encoding='utf-8')
        self.assertIn('$(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir))', text)
        self.assertNotIn('$(foreach dir,$(INCLUDES),-iquote $(CURDIR)/$(dir))', text)

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

    def test_video_uses_recovered_four_bg_layout_and_parallax_scroll(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        header = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        self.assertIn('#define GB_BG0_SCREENBLOCK 27', video)
        self.assertIn('#define GB_BG1_SCREENBLOCK 28', video)
        self.assertIn('#define GB_BG2_SCREENBLOCK 29', video)
        self.assertIn('#define GB_BG3_SCREENBLOCK 30', video)
        self.assertIn('BGCTRL[0]', video)
        self.assertIn('BGCTRL[1]', video)
        self.assertIn('BGCTRL[2]', video)
        self.assertIn('BGCTRL[3]', video)
        self.assertGreaterEqual(video.count('BG_SIZE_0'), 4)
        self.assertIn('BG_PRIORITY(0)', video)
        self.assertIn('BG_PRIORITY(1)', video)
        self.assertIn('BG_PRIORITY(2)', video)
        self.assertIn('BG_PRIORITY(3)', video)
        for token in ('BG0_ON', 'BG1_ON', 'BG2_ON', 'BG3_ON'):
            self.assertIn(token, video)
        self.assertIn('level->bg_tile_halfwords', video)
        self.assertIn('level->fixed_map', video)
        self.assertIn('gb_video_stream_full', header)
        self.assertIn('gb_video_stream_column', header)
        self.assertIn('gb_video_stream_row', header)
        self.assertIn('BG_OFFSET[0].x = 0', video)
        self.assertIn('BG_OFFSET[1].x = (u16)x', video)
        self.assertIn('BG_OFFSET[2].x = (u16)x', video)
        self.assertIn('BG_OFFSET[3].x = (u16)(x / 4)', video)
        self.assertIn('BG_OFFSET[3].y = (u16)(y / 4)', video)

    def test_runtime_has_all_level_registry_and_game_uses_default_lookup(self):
        assets = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        world = (ROOT / 'reconstruction/source/engine/world.c').read_text(encoding='utf-8')
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        registry = (ROOT / 'reconstruction/data/level_registry.c').read_text(encoding='utf-8')
        for level in range(11):
            self.assertIn(f'gb_level{level:02d}_assets', assets)
        self.assertIn('gb_level00_v1_assets', assets)
        self.assertIn('gb_level00_v2_assets', assets)
        self.assertIn('const GbLevelAssets* gb_level_assets', assets)
        self.assertIn('const GbLevelAssets* gb_level_default_assets', assets)
        self.assertIn('case 10:', registry)
        self.assertIn('gb_level_default_assets(level_id)', game)
        self.assertNotIn('static const GbLevelAssets* gb_level_by_id', game)
        self.assertNotIn('GB_LEVEL_08', game)
        self.assertIn('world_width_tiles', world)
        self.assertIn('gb_video_stream_full', world)
        self.assertIn('gb_video_set_camera', world)

    def test_generated_level_registry_resolves_all_defaults_and_level0_variants(self):
        declarations = []
        for level in range(11):
            width = 782 if level == 9 else 1
            declarations.append(
                f'const GbLevelAssets gb_level{level:02d}_assets = {{ .level_id = {level}, .graphics_variant = 0, .world_width_tiles = {width} }};'
            )
        declarations.extend([
            'const GbLevelAssets gb_level00_v1_assets = { .level_id = 0, .graphics_variant = 1 };',
            'const GbLevelAssets gb_level00_v2_assets = { .level_id = 0, .graphics_variant = 2 };',
        ])
        harness = """\n#include <assert.h>\n#include <graveblood/assets.h>\n\nDECLARATIONS\n\nint main(void)\n{\n    for(int level = 0; level <= 10; ++level)\n    {\n        const GbLevelAssets* assets = gb_level_default_assets(level);\n        assert(assets != 0);\n        assert(assets->level_id == level);\n        assert(assets->graphics_variant == 0);\n    }\n    assert(gb_level_assets(0, 1) == &gb_level00_v1_assets);\n    assert(gb_level_assets(0, 2) == &gb_level00_v2_assets);\n    assert(gb_level_assets(1, 1) == 0);\n    assert(gb_level_assets(11, 0) == 0);\n    assert(gb_level_default_assets(9)->world_width_tiles == 782);\n    return 0;\n}\n""".replace('DECLARATIONS', '\n'.join(declarations))
        gba_h = """\n#ifndef GBA_H\n#define GBA_H\n#include <stdint.h>\ntypedef uint8_t u8;\ntypedef int8_t s8;\ntypedef uint16_t u16;\ntypedef int16_t s16;\ntypedef uint32_t u32;\ntypedef int32_t s32;\n#endif\n"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'registry_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'registry_test'
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/data/level_registry.c'),
                str(td / 'registry_test.c'), '-o', str(exe),
            ], check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_game_lifecycle_loads_updates_and_draws_actor_system(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('#include <graveblood/actors.h>', game)
        self.assertIn('GbActorSystem actors;', game)
        self.assertIn('GbInteractionEvent interaction;', game)
        self.assertIn('gb_actor_system_load(actors, assets)', game)
        self.assertIn('gb_actor_system_update(&actors, &player, &input, &interaction)', game)
        self.assertIn('gb_video_draw_actors(&actors, &player, world.camera_x, world.camera_y)', game)
        self.assertGreaterEqual(game.count('gb_enter_level(&world, &player, &actors,'), 2)

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
        self.assertIn('all 11 canonical level records', text)
        self.assertIn('13 recovered graphics variants', text)
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

    def test_all_generated_level_units_link_with_registry_on_host(self):
        level_units = sorted((ROOT / 'reconstruction/data').glob('level*_assets.c'))
        self.assertEqual(13, len(level_units))
        harness = r"""
#include <assert.h>
#include <graveblood/assets.h>

int main(void)
{
    for(int level = 0; level <= 10; ++level)
    {
        const GbLevelAssets* assets = gb_level_default_assets(level);
        assert(assets != 0);
        assert(assets->level_id == level);
    }
    assert(gb_level_assets(0, 1) != 0);
    assert(gb_level_assets(0, 2) != 0);
    assert(gb_level_assets(10, 1) == 0);
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
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'all_levels_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'all_levels_test'
            subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                *map(str, level_units),
                str(ROOT / 'reconstruction/data/level_registry.c'),
                str(td / 'all_levels_test.c'), '-o', str(exe),
            ], check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_actor_video_uses_bounded_dynamic_8bpp_slots_and_preserves_player_palette(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        header = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        self.assertIn('void gb_video_draw_actors', header)
        self.assertIn('#define GB_ACTOR_OAM_FIRST 5', video)
        self.assertIn('#define GB_ACTOR_OAM_COUNT 52', video)
        self.assertIn('#define GB_OBJ_256_COLOR (1u << 13)', video)
        self.assertIn('#define GB_PLAYER_PALETTE_BANK 15', video)
        self.assertIn('gb_copy_u16(OBJ_COLORS, gb_actor_obj_palette, 256)', video)
        self.assertIn('OBJ_COLORS + GB_PLAYER_PALETTE_BANK * 16', video)
        self.assertIn('(GB_PLAYER_PALETTE_BANK << 12)', video)
        self.assertIn('GB_PLAYER_FRAME_COUNT * 128', video)
        self.assertIn('GB_MONSTER_OBJ_TILE_BASE', video)
        self.assertIn('GB_ACTOR_FRAME_HALFWORDS', video)
        self.assertIn('actor->descriptor->actor_class == GB_ACTOR_NPC', video)
        self.assertIn('actor->descriptor->actor_class == GB_ACTOR_GRASS', video)
        self.assertIn('GB_LEAF_PARTICLE_CAPACITY', video)
        self.assertIn('actor->descriptor->visual_index >= GB_ACTOR_VISUAL_COUNT', video)

    def test_actor_video_compiles_with_host_gba_contract(self):
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
typedef struct { volatile u16 x; volatile u16 y; } GbTestBgOffset;
extern volatile u16 gb_test_vcount;
extern volatile u16 gb_test_dispcnt;
extern volatile u16 gb_test_bgctrl[4];
extern volatile GbTestBgOffset gb_test_bg_offset[4];
extern volatile u16 gb_test_bg_colors[256];
extern volatile u16 gb_test_obj_colors[256];
extern volatile u16 gb_test_oam[512];
extern volatile u16 gb_test_vram[0x18000 / 2];
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
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            obj = td / 'video.o'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                '-c', str(ROOT / 'reconstruction/source/engine/video.c'), '-o', str(obj),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(obj.is_file())

    def test_story_video_uses_canonical_font_safe_bg0_tiles_and_monster_oam(self):
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        header = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        self.assertIn('void gb_video_clear_story_ui', header)
        self.assertIn('void gb_video_draw_story_ui', header)
        self.assertIn('void gb_video_draw_message', header)
        self.assertIn('void gb_video_draw_player_state', header)
        self.assertIn('#define GB_STORY_UI_COLUMNS 29', video)
        self.assertIn('#define GB_STORY_UI_ROWS 3', video)
        self.assertIn('#define GB_TEXT_BACKGROUND_INDEX 1', video)
        self.assertIn('#define GB_TEXT_FOREGROUND_INDEX 2', video)
        self.assertIn('level->bg0_ui_tiles', video)
        self.assertIn('gb_font_glyphs', video)
        self.assertIn('gb_monster_obj_frames', video)
        self.assertIn('animation_counter - 20', video)
        self.assertIn('animation_counter + 12', video)

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
typedef struct { volatile u16 x; volatile u16 y; } GbTestBgOffset;
extern volatile u16 gb_test_vcount;
extern volatile u16 gb_test_dispcnt;
extern volatile u16 gb_test_bgctrl[4];
extern volatile GbTestBgOffset gb_test_bg_offset[4];
extern volatile u16 gb_test_bg_colors[256];
extern volatile u16 gb_test_obj_colors[256];
extern volatile u16 gb_test_oam[512];
extern volatile u16 gb_test_vram[0x18000 / 2];
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
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            obj = td / 'video_story.o'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                '-c', str(ROOT / 'reconstruction/source/engine/video.c'), '-o', str(obj),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(obj.is_file())

    def test_pda_video_uses_exact_chrome_and_safe_dynamic_text_layer(self):
        header = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        video_h = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        self.assertIn('GB_PDA_PAGE_COUNT = 4', header)
        self.assertIn('GB_PDA_MAP_CELLS = 600', header)
        self.assertIn('GB_PDA_FRIEND_COUNT = 6', header)
        self.assertIn('GB_PDA_TEXT_COLUMNS = 29', header)
        self.assertIn('GB_PDA_TEXT_ROWS = 5', header)
        self.assertIn('GB_PDA_TEXT_TILE_COUNT = 145', header)
        self.assertIn('gb_pda_page_maps[GB_PDA_PAGE_COUNT][GB_PDA_MAP_CELLS]', header)
        self.assertIn('gb_pda_friend_names[GB_PDA_FRIEND_COUNT]', header)
        self.assertIn('gb_pda_text_tile_ids[GB_PDA_TEXT_TILE_COUNT]', header)
        self.assertIn('gb_video_load_pda', video_h)
        self.assertIn('gb_video_draw_pda', video_h)

        harness = r'''
#include <assert.h>
#include <string.h>
#include <graveblood/video.h>

volatile u16 gb_test_vcount;
volatile u16 gb_test_dispcnt;
volatile u16 gb_test_bgctrl[4];
volatile GbTestBgOffset gb_test_bg_offset[4];
volatile u16 gb_test_bg_colors[256];
volatile u16 gb_test_obj_colors[256];
volatile u16 gb_test_oam[512];
volatile u16 gb_test_vram[0x18000 / 2];

const u16 gb_actor_obj_palette[256] = {0};
const u16 gb_player_obj_palette[16] = {0};
const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128] = {0};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {0};

static const u16 level_palette[256] = {0};
static const u16 level_tiles[1] = {0};
static const GbLevelAssets level = {
    .level_id = 7, .bg_palette = level_palette, .bg_tiles = level_tiles,
    .bg_tile_halfwords = 1
};
static const GbMessageRecord message = { .title = "HELLO", .sender = "IQ 54", .body = "BODY" };

const GbMessageRecord* gb_story_message_primary(const GbStoryRuntime* story) { (void)story; return &message; }
const GbMessageRecord* gb_story_message_auxiliary(const GbStoryRuntime* story, u8 slot) { (void)story; (void)slot; return &message; }

int main(void)
{
    GbPdaRuntime pda;
    gb_pda_reset(&pda);
    gb_pda_open(&pda);
    GbStoryRuntime story;
    memset(&story, 0, sizeof(story));
    for(unsigned i = 0; i < sizeof(gb_test_vram) / sizeof(gb_test_vram[0]); ++i)
        gb_test_vram[i] = 0xBEEF;

    gb_video_load_pda(&level, &pda, &story);
    assert(gb_test_dispcnt == (MODE_0 | BG0_ON | BG1_ON));
    assert(gb_test_bgctrl[0] == (BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(27) | BG_PRIORITY(0)));
    assert(gb_test_bgctrl[1] == (BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(28) | BG_PRIORITY(1)));
    for(int i = 0; i < 4; ++i)
        assert(gb_test_bg_offset[i].x == 0 && gb_test_bg_offset[i].y == 0);

    volatile u16* chrome = (volatile u16*)MAP_BASE_ADR(28);
    assert(chrome[0] == gb_pda_page_maps[GB_PDA_MESSAGES][0]);
    assert(chrome[19 * 32 + 29] == gb_pda_page_maps[GB_PDA_MESSAGES][19 * 30 + 29]);
    volatile u16* text_map = (volatile u16*)MAP_BASE_ADR(27);
    for(int row = 0; row < GB_PDA_TEXT_ROWS; ++row)
        for(int col = 0; col < GB_PDA_TEXT_COLUMNS; ++col)
            assert(text_map[(1 + row) * 32 + col] == gb_pda_text_tile_ids[row * GB_PDA_TEXT_COLUMNS + col]);

    pda.page = GB_PDA_FRIENDS;
    pda.friends_scroll = 2;
    pda.friends_cursor = 1;
    gb_video_draw_pda(&pda, &story);
    assert(chrome[0] == gb_pda_page_maps[GB_PDA_FRIENDS][0]);

    pda.page = GB_PDA_STATUS;
    gb_video_draw_pda(&pda, &story);
    assert(chrome[0] == gb_pda_page_maps[GB_PDA_STATUS][0]);
    pda.page = GB_PDA_BACKPACK;
    gb_video_draw_pda(&pda, &story);
    assert(chrome[0] == gb_pda_page_maps[GB_PDA_BACKPACK][0]);
    return 0;
}
'''
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
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_START (1u << 3)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#define KEY_R (1u << 8)
#define KEY_L (1u << 9)
#endif
'''
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'pda_video_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'pda_video_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/video.c'),
                str(ROOT / 'reconstruction/source/game/pda.c'),
                str(ROOT / 'reconstruction/data/pda_assets.c'),
                str(ROOT / 'reconstruction/data/font_data.c'),
                str(td / 'pda_video_test.c'), '-Wl,--gc-sections', '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_actor_runtime_population_routes_and_interaction_events(self):
        harness = r"""
#include <assert.h>
#include <graveblood/actors.h>

static const GbActorDescriptor social_desc = {
    .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC,
    .state = 1, .dial = 7, .visual_index = 0
};
static const GbActorDescriptor dialogue4_desc = {
    .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC,
    .state = 2, .legs_color = 1, .dial = 3, .visual_index = 0
};
static const GbActorDescriptor dialogue5_desc = {
    .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC,
    .state = 2, .legs_color = 24, .dial = 4, .visual_index = 0
};
static const GbActorDescriptor collection_desc = {
    .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC,
    .state = 4, .dial = 5, .visual_index = 0
};

static void one_actor(GbActorSystem* system, const GbActorDescriptor* desc)
{
    system->count = 1;
    system->actors[0].descriptor = desc;
    system->actors[0].fixed_x = ((s32)desc->x) << GB_ACTOR_FIXED_SHIFT;
    system->actors[0].fixed_y = ((s32)desc->y) << GB_ACTOR_FIXED_SHIFT;
    system->actors[0].frame = 1;
    system->actors[0].waypoint_index = 0;
    system->actors[0].facing_right = 0;
    system->actors[0].active = 1;
    system->actors[0].special_mover_latched = desc->port_to != 0;
}

int main(void)
{
    GbLevelAssets level = { 0 };
    GbActorSystem system;
    GbInteractionEvent event;
    GbInput none = { 0, 0 };
    GbInput fresh_a = { KEY_A, KEY_A };
    GbInput held_a = { KEY_A, 0 };
    GbPlayer player = { 0 };

    gb_actor_system_init(&system);
    assert(GB_ACTOR_FIXED_SHIFT == 8);
    assert(system.npc_special_timer == 15);
    level.level_id = 0;
    gb_actor_system_load(&system, &level);
    assert(system.count == 55);
    for(unsigned i = 1; i < 49; ++i)
        assert(system.actors[i - 1].descriptor->rom_order < system.actors[i].descriptor->rom_order);
    for(unsigned i = 49; i < system.count; ++i)
        assert(system.actors[i].descriptor->rom_order >= 0x8000);

    level.level_id = 3;
    gb_actor_system_load(&system, &level);
    assert(system.count == 65);
    assert(system.count <= GB_ACTOR_CAPACITY);

    level.level_id = 0;
    gb_actor_system_load(&system, &level);
    GbActor* route_actor = 0;
    for(unsigned i = 0; i < system.count; ++i)
    {
        if(system.actors[i].descriptor->state == 3)
        {
            route_actor = &system.actors[i];
            break;
        }
    }
    assert(route_actor != 0);
    const s32 before_x = route_actor->fixed_x;
    const s32 before_y = route_actor->fixed_y;
    gb_actor_system_update(&system, &player, &none, &event);
    assert(route_actor->fixed_x == before_x + GB_ACTOR_ROUTE_SPEED_FIXED);
    assert(route_actor->fixed_y == before_y + GB_ACTOR_ROUTE_SPEED_FIXED);
    assert(route_actor->facing_right == 1);
    assert(event.type == GB_INTERACTION_NONE);

    route_actor->waypoint_index = 5;
    route_actor->fixed_x = ((s32)gb_actor_routes[0][5].x) << 11;
    route_actor->fixed_y = ((s32)gb_actor_routes[0][5].y) << 11;
    gb_actor_system_update(&system, &player, &none, &event);
    assert(route_actor->waypoint_index == 0);

    one_actor(&system, &social_desc);
    player.x = 80; player.y = 80;
    gb_actor_system_update(&system, &player, &fresh_a, &event);
    assert(event.type == GB_INTERACTION_SOCIAL && event.dial == 7);
    player.x = 119; player.y = 119;
    gb_actor_system_update(&system, &player, &fresh_a, &event);
    assert(event.type == GB_INTERACTION_SOCIAL);
    player.x = 120; player.y = 100;
    gb_actor_system_update(&system, &player, &fresh_a, &event);
    assert(event.type == GB_INTERACTION_NONE);
    player.x = 100; player.y = 100;
    gb_actor_system_update(&system, &player, &held_a, &event);
    assert(event.type == GB_INTERACTION_NONE);

    one_actor(&system, &dialogue4_desc);
    player.x = 80; player.y = 80;
    gb_actor_system_update(&system, &player, &fresh_a, &event);
    assert(event.type == GB_INTERACTION_DIALOGUE && event.dial == 3);
    player.x = 112; player.y = 100;
    gb_actor_system_update(&system, &player, &fresh_a, &event);
    assert(event.type == GB_INTERACTION_NONE);

    one_actor(&system, &dialogue5_desc);
    player.x = 119; player.y = 119;
    gb_actor_system_update(&system, &player, &fresh_a, &event);
    assert(event.type == GB_INTERACTION_DIALOGUE && event.dial == 4);

    one_actor(&system, &collection_desc);
    player.x = 80; player.y = 80;
    gb_actor_system_update(&system, &player, &fresh_a, &event);
    assert(event.type == GB_INTERACTION_COLLECTION && event.dial == 5);
    assert(event.actor_index == 0 && event.state == 4);
    assert(event.actor_x == 100 && event.actor_y == 100);

    /* legsColor 40 is the unique continuous -150 fixed-X mover. */
    static const GbActorDescriptor mover40 = {
        .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC, .legs_color = 40
    };
    one_actor(&system, &mover40);
    const s32 mover40_before = system.actors[0].fixed_x;
    gb_actor_system_update(&system, &player, &none, &event);
    assert(system.actors[0].fixed_x == mover40_before - 150);

    /* legsColor 112 checks proximity on the shared countdown, latches, emits SFX9,
       then uses x += 600*turn-300 and y -= 250 every update. */
    static const GbActorDescriptor mover112 = {
        .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC, .legs_color = 112, .turn = 1
    };
    one_actor(&system, &mover112);
    system.npc_special_timer = 0;
    player.x = 100; player.y = 92;
    const s32 special_x = system.actors[0].fixed_x;
    const s32 special_y = system.actors[0].fixed_y;
    gb_actor_system_update(&system, &player, &none, &event);
    assert(system.actors[0].special_mover_latched == 1);
    assert(system.npc_special_timer == 4);
    assert(gb_actor_system_take_pending_sfx(&system) == 9);
    assert(gb_actor_system_take_pending_sfx(&system) == -1);
    assert(system.actors[0].fixed_x == special_x + 300);
    assert(system.actors[0].fixed_y == special_y - 250);
    const s32 latched_x = system.actors[0].fixed_x;
    const s32 latched_y = system.actors[0].fixed_y;
    gb_actor_system_update(&system, &player, &none, &event);
    assert(system.actors[0].fixed_x == latched_x + 300);
    assert(system.actors[0].fixed_y == latched_y - 250);

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
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'actor_runtime_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'actor_runtime_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/game/actors.c'),
                str(ROOT / 'reconstruction/data/actor_data.c'),
                str(ROOT / 'reconstruction/data/actor_routes.c'),
                str(td / 'actor_runtime_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_story_game_loop_integration_and_level10_rusty_key_gate(self):
        graveblood = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('#include <graveblood/story.h>', graveblood)
        self.assertIn('#include <graveblood/audio.h>', graveblood)
        self.assertIn('GbStoryRuntime story;', graveblood)
        self.assertIn('gb_audio_init();', graveblood)
        self.assertIn('gb_story_init(&story);', graveblood)
        self.assertIn('gb_audio_play_music(level_id == 10 ? 1 : 0);', graveblood)
        self.assertNotIn('gb_audio_play_music(2)', graveblood)
        self.assertIn('gb_story_take_pending_sfx(&story)', graveblood)
        self.assertIn('gb_audio_play_sfx((u8)pending_sfx)', graveblood)
        self.assertIn('gb_actor_system_take_pending_sfx(&actors)', graveblood)
        self.assertIn('gb_audio_play_sfx((u8)actor_sfx)', graveblood)
        self.assertLess(graveblood.index('gb_actor_system_take_pending_sfx(&actors)'),
                        graveblood.index('gb_story_try_level10_gate(&story'))
        self.assertIn('gb_story_on_level_load(story, actors);', graveblood)
        self.assertIn('gb_story_handle_interaction(&story, &actors, &interaction);', graveblood)
        self.assertIn('gb_story_update(&story, &actors, &input);', graveblood)
        self.assertIn('gb_story_try_level10_gate(&story, world.assets, &player, &input)', graveblood)
        self.assertIn('gb_video_draw_story_ui(&story);', graveblood)
        self.assertIn('gb_video_draw_player_state(&player, &story,', graveblood)

        harness = r"""
#include <assert.h>
#include <graveblood/story.h>

int main(void)
{
    GbStoryRuntime story;
    GbLevelAssets level = {0};
    GbPlayer player = {0};
    GbInput input = {0};

    gb_story_init(&story);
    level.level_id = 10;
    input.pressed = KEY_A;
    input.held = KEY_A;

    /* turn=4 gate: exact recovered contact grid, pre-key blocks generic portal. */
    player.x = 808;
    player.y = 392;
    story.state.collection_progress = 3;
    assert(gb_story_try_level10_gate(&story, &level, &player, &input) == GB_STORY_GATE_BLOCKED);
    assert(player.x == 808 && player.y == 392);

    /* collection progress 3->4 activates the forced vertical path; X is not consumed. */
    story.state.collection_progress = 4;
    player.x = 810;
    player.y = 392;
    assert(gb_story_try_level10_gate(&story, &level, &player, &input) == GB_STORY_GATE_TRAVERSED);
    assert(player.x == 810);
    assert(player.y == 360);

    /* turn=5 uses the other recovered target. */
    player.x = 808;
    player.y = 360;
    assert(gb_story_try_level10_gate(&story, &level, &player, &input) == GB_STORY_GATE_TRAVERSED);
    assert(player.x == 808);
    assert(player.y == 410);

    /* A held without a fresh press is not an interaction. */
    input.pressed = 0;
    input.held = KEY_A;
    player.x = 808;
    player.y = 392;
    assert(gb_story_try_level10_gate(&story, &level, &player, &input) == GB_STORY_GATE_NONE);
    assert(player.y == 392);

    /* Outside Level 10 the special gate path is inactive. */
    input.pressed = KEY_A;
    level.level_id = 9;
    assert(gb_story_try_level10_gate(&story, &level, &player, &input) == GB_STORY_GATE_NONE);

    /* Raw portal rectangle outside the special contact grid is still blocked so
       the turn-4/5 records can never fall through to generic portTo=8. */
    level.level_id = 10;
    story.state.collection_progress = 4;
    player.x = 808;
    player.y = 384;
    assert(gb_story_try_level10_gate(&story, &level, &player, &input) == GB_STORY_GATE_BLOCKED);
    assert(player.y == 384);
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
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
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
"""
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'gate_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'gate_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/game/story.c'),
                str(ROOT / 'reconstruction/data/story_data.c'),
                str(td / 'gate_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)

    def test_story_level9_treetype20_vertical_target_action(self):
        graveblood = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('gb_story_try_level9_treetype20_action(world.assets, &player, &input)', graveblood)

        harness = r"""
#include <assert.h>
#include <graveblood/story.h>

int main(void)
{
    GbLevelAssets level = {0};
    GbPlayer player = {0};
    GbInput input = {0};

    level.level_id = 9;
    input.pressed = KEY_A;
    input.held = KEY_A;

    /* Canonical Level-9 treetype=20 Fgtile occupies 512,456..528,472. */
    player.x = 512;
    player.y = 456;
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_TRAVERSED);
    assert(player.x == 512);
    assert(player.y == 512);

    /* It is a fresh-A action, not an automatic contact trigger. */
    player.y = 456;
    input.pressed = 0;
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_NONE);
    assert(player.y == 456);

    /* The special action exists only in Level 9 and never consumes portTo=524. */
    input.pressed = KEY_A;
    level.level_id = 8;
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_NONE);
    assert(player.y == 456);

    /* Outside the physical tile rectangle it does nothing. */
    level.level_id = 9;
    player.x = 511;
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_NONE);
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
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'level9_special_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'level9_special_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/game/story.c'),
                str(ROOT / 'reconstruction/data/story_data.c'),
                str(td / 'level9_special_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)

    def test_generic_portal_activation_plays_canonical_sfx5_once(self):
        harness = r"""
#include <assert.h>
#include <graveblood/portal.h>

static int played_id = -1;
static int played_count = 0;
int gb_audio_play_sfx(u8 sound_id)
{
    played_id = sound_id;
    ++played_count;
    return 0;
}

int main(void)
{
    const GbPortal portals[] = {
        { .x = 10, .y = 20, .width = 16, .height = 16, .target_level = 8, .num = 1 }
    };
    GbLevelAssets level = { 0 };
    level.portals = portals;
    level.portal_count = 1;
    GbPlayer player = { 0 };
    player.x = 12;
    player.y = 22;
    GbInput fresh_a = { KEY_A, KEY_A };
    GbInput none = { 0, 0 };

    assert(gb_portal_try_activate(&level, &player, &none) == -1);
    assert(played_count == 0);
    assert(gb_portal_try_activate(&level, &player, &fresh_a) == 8);
    assert(played_id == 5);
    assert(played_count == 1);
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
#define KEY_A (1u << 0)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'portal_audio_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'portal_audio_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/portal.c'),
                str(td / 'portal_audio_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)

    def test_story_runtime_dialogue_collection_messages_social_and_actor_cursor(self):
        harness = r"""
#include <assert.h>
#include <string.h>
#include <graveblood/actors.h>
#include <graveblood/story.h>

static const GbActorDescriptor dialogue_desc = {
    .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC,
    .state = 2, .dial = 0, .visual_index = 0
};
static const GbActorDescriptor social_stas_desc = {
    .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC,
    .state = 1, .dial = 0, .visual_index = 0
};
static const GbActorDescriptor social_invalid_desc = {
    .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC,
    .state = 1, .dial = 2, .visual_index = 0
};

static void one_actor(GbActorSystem* system, const GbActorDescriptor* desc, u8 overlay)
{
    system->count = 1;
    system->actors[0].descriptor = desc;
    system->actors[0].fixed_x = ((s32)desc->x) << GB_ACTOR_FIXED_SHIFT;
    system->actors[0].fixed_y = ((s32)desc->y) << GB_ACTOR_FIXED_SHIFT;
    system->actors[0].frame = 1;
    system->actors[0].waypoint_index = 0;
    system->actors[0].facing_right = 0;
    system->actors[0].active = 1;
    system->actors[0].story_overlay_index = overlay;
    system->actors[0].dialogue_step = -1;
    system->actors[0].consumed = 0;
    system->actors[0].story_visible = 1;
}

static GbInteractionEvent event_for(GbInteractionType type, u8 dial)
{
    GbInteractionEvent event = { 0 };
    event.type = type;
    event.actor_index = 0;
    event.dial = dial;
    return event;
}

int main(void)
{
    GbStoryRuntime story;
    GbActorSystem actors;
    GbInput fresh_a = { KEY_A, KEY_A };
    GbInput fresh_up = { KEY_UP, KEY_UP };
    GbInput fresh_right = { KEY_RIGHT, KEY_RIGHT };
    GbInput fresh_down = { KEY_DOWN, KEY_DOWN };
    GbInput fresh_left = { KEY_LEFT, KEY_LEFT };
    GbInput fresh_b = { KEY_B, KEY_B };
    GbInput none = { 0, 0 };

    gb_story_init(&story);
    assert(story.state.collection_progress == 0);
    assert(story.state.primary_message_stream == -1);
    assert(story.state.auxiliary_message_streams[0] == -1);
    assert(story.state.auxiliary_message_streams[1] == -1);
    assert(story.state.auxiliary_message_streams[2] == -1);
    assert(story.state.monster_render_enabled == 0);
    assert(story.state.final_effect_pending == 0);
    assert(gb_story_take_pending_sfx(&story) == -1);
    assert(story.state.social_profiles[0].topic_class[1] == 4);
    assert(story.state.social_profiles[1].topic_class[6] == 4);

    GbLevelAssets level0 = { 0 };
    level0.level_id = 0;
    gb_actor_system_load(&actors, &level0);
    assert(actors.count != 0);
    for(unsigned i = 0; i < actors.count; ++i)
    {
        assert(actors.actors[i].dialogue_step == -1);
        assert(actors.actors[i].consumed == 0);
        assert(actors.actors[i].story_visible == 1);
    }

    /* Normal dialogue starts from raw actor cursor + 1. */
    one_actor(&actors, &dialogue_desc, GB_ACTOR_STORY_NONE);
    GbInteractionEvent dialogue = event_for(GB_INTERACTION_DIALOGUE, 0);
    gb_story_handle_interaction(&story, &actors, &dialogue);
    assert(gb_story_take_pending_sfx(&story) == 3);
    assert(gb_story_take_pending_sfx(&story) == -1);
    assert(gb_story_ui_active(&story));
    assert(gb_story_dialogue_record(&story) == &gb_dialogue_scripts[0].records[0]);
    assert(strcmp(gb_story_dialogue_record(&story)->speaker, "Vika") == 0);
    gb_story_update(&story, &actors, &fresh_a); /* step 1 */
    assert(gb_story_dialogue_record(&story) == &gb_dialogue_scripts[0].records[1]);
    gb_story_update(&story, &actors, &fresh_a); /* step 2 */
    gb_story_update(&story, &actors, &fresh_a); /* runs -2, then -1 */
    assert(! gb_story_ui_active(&story));
    assert(story.state.primary_message_stream == 0);
    assert(actors.actors[0].dialogue_step == 4);
    assert(gb_story_message_primary(&story) == &gb_message_records[0]);

    /* Re-entering the same NPC begins at raw cursor 4 + 1 = step 5. */
    gb_story_handle_interaction(&story, &actors, &dialogue);
    assert(gb_story_take_pending_sfx(&story) == 3);
    assert(gb_story_dialogue_record(&story) == &gb_dialogue_scripts[0].records[5]);
    gb_story_update(&story, &actors, &fresh_a);
    gb_story_update(&story, &actors, &fresh_a);
    assert(! gb_story_ui_active(&story));
    assert(actors.actors[0].dialogue_step == 4);

    /* Message lookup is clean-room bounded by extracted stream/stage rows. */
    story.state.story_stage = 1;
    assert(gb_story_message_primary(&story) == &gb_message_records[1]);
    story.state.story_stage = 7;
    assert(gb_story_message_primary(&story) == 0);
    story.state.story_stage = 0;

    /* Collection selector: progress 1/2 are silent, progress 3 runs script 5. */
    static const GbActorDescriptor collection_desc = {
        .x = 100, .y = 100, .actor_class = GB_ACTOR_NPC,
        .state = 4, .dial = 3, .level = 10, .visual_index = 0
    };
    GbInteractionEvent pickup = event_for(GB_INTERACTION_COLLECTION, 3);
    one_actor(&actors, &collection_desc, 11);
    story.state.collection_progress = 1;
    gb_story_handle_interaction(&story, &actors, &pickup);
    assert(gb_story_take_pending_sfx(&story) == 3);
    assert(story.state.collection_progress == 2);
    assert(actors.actors[0].consumed && ! actors.actors[0].active);
    assert(story.state.consumed_story_overlays & (1u << 11));

    one_actor(&actors, &collection_desc, 12);
    story.state.collection_progress = 3;
    gb_story_handle_interaction(&story, &actors, &pickup);
    assert(gb_story_take_pending_sfx(&story) == 3);
    assert(gb_story_dialogue_record(&story) == &gb_dialogue_scripts[5].records[0]);
    gb_story_update(&story, &actors, &fresh_a);
    assert(gb_story_dialogue_record(&story) == &gb_dialogue_scripts[5].records[1]);
    gb_story_update(&story, &actors, &fresh_a);
    assert(! gb_story_ui_active(&story));
    assert(story.state.collection_progress == 4);
    assert(actors.actors[0].consumed);
    /* Canonical state4 opcode -1 branch plays SFX7 at 0x08003748. */
    assert(gb_story_take_pending_sfx(&story) == 7);
    assert(gb_story_take_pending_sfx(&story) == -1);

    /* Sixth selector uses script 0; its state4 -2 branch plays the same SFX7. */
    one_actor(&actors, &collection_desc, 14);
    story.state.collection_progress = 5;
    gb_story_handle_interaction(&story, &actors, &pickup);
    assert(gb_story_take_pending_sfx(&story) == 3);
    gb_story_update(&story, &actors, &fresh_a); /* step 1 */
    gb_story_update(&story, &actors, &fresh_a); /* step 2 */
    gb_story_update(&story, &actors, &fresh_a); /* state4 -2 terminal */
    assert(! gb_story_ui_active(&story));
    assert(story.state.collection_progress == 6);
    assert(actors.actors[0].consumed);
    assert(gb_story_take_pending_sfx(&story) == 7);
    assert(gb_story_take_pending_sfx(&story) == -1);

    /* Fifth pickup: -4 enables monster, -5 terminates safely without raw VRAM effect. */
    one_actor(&actors, &collection_desc, 15);
    story.state.collection_progress = 4;
    gb_story_handle_interaction(&story, &actors, &pickup);
    assert(gb_story_dialogue_record(&story) == &gb_dialogue_scripts[6].records[0]);
    gb_story_update(&story, &actors, &fresh_a); /* -4 then content step 2 */
    assert(story.state.monster_render_enabled == 1);
    assert(gb_story_dialogue_record(&story) == &gb_dialogue_scripts[6].records[2]);
    gb_story_update(&story, &actors, &fresh_a); /* content step 3 */
    gb_story_update(&story, &actors, &fresh_a); /* -5 terminal */
    assert(story.state.final_effect_pending == 1);
    assert(story.state.collection_progress == 5);
    assert(actors.actors[0].consumed && ! actors.actors[0].active);
    assert(! gb_story_ui_active(&story));
    assert(gb_story_take_pending_sfx(&story) == 13);
    assert(gb_story_take_pending_sfx(&story) == -1);

    /* Consumed overlay persistence survives an actor-system reload. */
    one_actor(&actors, &collection_desc, 15);
    gb_story_on_level_load(&story, &actors);
    assert(actors.actors[0].consumed && ! actors.actors[0].active);

    /* Only the two code-proven social profile selectors are accepted. */
    gb_story_init(&story);
    one_actor(&actors, &social_invalid_desc, GB_ACTOR_STORY_NONE);
    GbInteractionEvent social_bad = event_for(GB_INTERACTION_SOCIAL, 2);
    gb_story_handle_interaction(&story, &actors, &social_bad);
    assert(! gb_story_ui_active(&story));

    one_actor(&actors, &social_stas_desc, GB_ACTOR_STORY_NONE);
    GbInteractionEvent social = event_for(GB_INTERACTION_SOCIAL, 0);
    gb_story_handle_interaction(&story, &actors, &social);
    assert(story.social.state == GB_SOCIAL_ROOT_SELECTOR);
    assert(strcmp(gb_story_social_profile_name(&story), "Stas") == 0);
    /* State 1 D-pad updates Player+0x1E4 only; fresh A confirms the choice. */
    gb_story_update(&story, &actors, &fresh_right);
    assert(story.social.state == GB_SOCIAL_ROOT_SELECTOR);
    assert(story.social.page_base == 0);
    assert(story.social.selected_quadrant == 1);
    gb_story_update(&story, &actors, &fresh_up); /* select TALK */
    assert(story.social.page_base == 0);
    assert(story.social.selected_quadrant == 0);
    gb_story_update(&story, &actors, &fresh_a);  /* confirm TALK submenu */
    assert(story.social.page_base == 4);
    assert(story.social.selected_quadrant == 0);
    gb_story_update(&story, &actors, &fresh_b);  /* child-page B returns to root, no SFX */
    assert(story.social.state == GB_SOCIAL_ROOT_SELECTOR);
    assert(story.social.page_base == 0);
    assert(gb_story_take_pending_sfx(&story) == -1);
    gb_story_update(&story, &actors, &fresh_a);  /* confirm TALK submenu again */
    assert(story.social.page_base == 4);
    gb_story_update(&story, &actors, &fresh_a);  /* confirm SUBJECT */
    assert(story.social.state == GB_SOCIAL_SECONDARY);
    assert(story.social.topic_count == 9);
    gb_story_update(&story, &actors, &fresh_right); /* ignored in vertical topic list */
    assert(story.social.topic_index == 0);
    assert(gb_story_take_pending_sfx(&story) == -1);
    gb_story_update(&story, &actors, &fresh_down);
    assert(story.social.topic_index == 1);
    assert(gb_story_take_pending_sfx(&story) == 4);
    gb_story_update(&story, &actors, &fresh_up);
    assert(story.social.topic_index == 0);
    assert(gb_story_take_pending_sfx(&story) == 4);
    gb_story_update(&story, &actors, &fresh_a); /* sports, class 3 */
    assert(story.social.state == GB_SOCIAL_POST_DELAY);
    assert(story.social.post_countdown == 150);
    assert(story.state.social_score_mirror == 0);
    assert(story.state.social_profiles[0].score == 0);
    assert(gb_story_social_response(&story) == 0);
    for(int i = 0; i < 150; ++i)
        gb_story_update(&story, &actors, &none);
    assert(story.social.state == GB_SOCIAL_POST_DELAY);
    assert(story.social.post_countdown == 0);
    assert(story.state.social_profiles[0].score == 0);
    gb_story_update(&story, &actors, &none); /* expiry dispatch */
    assert(story.social.state == GB_SOCIAL_RESPONSE);
    assert(story.state.social_score_mirror == 0); /* mirror is pre-delta */
    assert(story.state.social_profiles[0].score == 2);
    assert(gb_story_social_response(&story) != 0);
    /* The canonical response RNG starts at state 1; first SUBJECT draw is variant 1. */
    assert(strcmp(gb_story_social_response(&story),
                  gb_story_lookup_social_response(0, 0, 3, 1)) == 0);

    /* Pure response lookup is bounded and class-2 is the recovered neutral line. */
    assert(strcmp(gb_story_lookup_social_response(0, 0, 2, 0), "I don't really care") == 0);
    assert(gb_story_lookup_social_response(0, 9, 3, 0) == 0);
    assert(gb_story_lookup_social_response(3, 0, 9, 0) == 0);
    assert(gb_story_message_auxiliary(&story, 3) == 0);

    /* Fresh A dismisses response; follow-up leaves remain shared, not invented. */
    gb_story_update(&story, &actors, &fresh_a);
    assert(! gb_story_ui_active(&story));

    gb_story_init(&story);
    story.state.social_profiles[0].score = 3;
    one_actor(&actors, &social_stas_desc, GB_ACTOR_STORY_NONE);
    gb_story_handle_interaction(&story, &actors, &social);
    gb_story_update(&story, &actors, &fresh_a);     /* confirm TALK */
    gb_story_update(&story, &actors, &fresh_right); /* select Ask about quadrant 1 */
    assert(story.social.state == GB_SOCIAL_ROOT_SELECTOR);
    gb_story_update(&story, &actors, &fresh_a);     /* confirm Ask about */
    assert(story.social.state == GB_SOCIAL_SECONDARY);
    assert(story.social.topic_count == 5);
    gb_story_update(&story, &actors, &fresh_a);
    assert(story.social.state == GB_SOCIAL_POST_DELAY);
    assert(story.social.followup_armed == 0);
    for(int i = 0; i < 150; ++i)
        gb_story_update(&story, &actors, &none);
    gb_story_update(&story, &actors, &none);
    assert(story.social.state == GB_SOCIAL_RESPONSE);
    assert(story.social.followup_armed == 1);
    /* 0x080090F8 mirrors 10 * profile score before quadrant dispatch. */
    assert(story.state.social_score_mirror == 30);
    gb_story_update(&story, &actors, &fresh_a);
    assert(! gb_story_ui_active(&story));

    /* Quadrants 1/2 do not call the response RNG; the next SUBJECT is still draw #1. */
    gb_story_handle_interaction(&story, &actors, &social);
    gb_story_update(&story, &actors, &fresh_a);     /* confirm TALK */
    gb_story_update(&story, &actors, &fresh_a);     /* confirm SUBJECT */
    gb_story_update(&story, &actors, &fresh_a);     /* sports, class 3 */
    for(int i = 0; i < 150; ++i)
        gb_story_update(&story, &actors, &none);
    gb_story_update(&story, &actors, &none);
    assert(strcmp(gb_story_social_response(&story),
                  gb_story_lookup_social_response(0, 0, 3, 1)) == 0);
    gb_story_update(&story, &actors, &fresh_a);
    assert(! gb_story_ui_active(&story));

    /* CRITICIZE uses the same first RNG draw but reduces it modulo 2. */
    gb_story_init(&story);
    one_actor(&actors, &social_stas_desc, GB_ACTOR_STORY_NONE);
    gb_story_handle_interaction(&story, &actors, &social);
    gb_story_update(&story, &actors, &fresh_a);     /* confirm TALK */
    gb_story_update(&story, &actors, &fresh_left);  /* select CRITICIZE */
    assert(story.social.state == GB_SOCIAL_ROOT_SELECTOR);
    gb_story_update(&story, &actors, &fresh_a);     /* confirm CRITICIZE */
    assert(story.social.state == GB_SOCIAL_SECONDARY);
    assert(story.social.topic_count == 9);
    gb_story_update(&story, &actors, &fresh_a);     /* sports, class 3 */
    assert(story.social.state == GB_SOCIAL_POST_DELAY);
    assert(story.state.social_profiles[0].score == 0);
    for(int i = 0; i < 150; ++i)
        gb_story_update(&story, &actors, &none);
    gb_story_update(&story, &actors, &none);
    assert(story.state.social_score_mirror == 0);
    assert(story.state.social_profiles[0].score == -2);
    assert(strcmp(gb_story_social_response(&story),
                  gb_story_lookup_social_response(3, 0, 3, 1)) == 0);
    gb_story_update(&story, &actors, &fresh_a);
    assert(! gb_story_ui_active(&story));

    /* Zero-count leaves still enter state 2; B returns to root and plays SFX7. */
    gb_story_init(&story);
    one_actor(&actors, &social_stas_desc, GB_ACTOR_STORY_NONE);
    gb_story_handle_interaction(&story, &actors, &social);
    gb_story_update(&story, &actors, &fresh_right); /* select FLIRT */
    assert(story.social.page_base == 0);
    gb_story_update(&story, &actors, &fresh_a);     /* confirm FLIRT submenu */
    assert(story.social.page_base == 8);
    gb_story_update(&story, &actors, &fresh_down);  /* select DIRTY JOKE */
    gb_story_update(&story, &actors, &fresh_a);     /* confirm zero-count leaf */
    assert(story.social.state == GB_SOCIAL_SECONDARY);
    assert(story.social.topic_count == 0);
    gb_story_update(&story, &actors, &fresh_a); /* non-TALK leaf has no code-proven commit */
    assert(story.social.state == GB_SOCIAL_SECONDARY);
    assert(story.social.page_base == 8);
    gb_story_update(&story, &actors, &fresh_b);
    assert(story.social.state == GB_SOCIAL_ROOT_SELECTOR);
    assert(story.social.page_base == 0);
    assert(story.social.selected_quadrant == 0);
    assert(gb_story_take_pending_sfx(&story) == 7);

    /* Invalid dialogue/script and exhausted collection indices fail closed. */
    gb_story_init(&story);
    one_actor(&actors, &dialogue_desc, GB_ACTOR_STORY_NONE);
    GbInteractionEvent invalid_dialogue = event_for(GB_INTERACTION_DIALOGUE, 99);
    gb_story_handle_interaction(&story, &actors, &invalid_dialogue);
    assert(! gb_story_ui_active(&story));
    story.state.collection_progress = 6;
    GbInteractionEvent exhausted_pickup = event_for(GB_INTERACTION_COLLECTION, 3);
    gb_story_handle_interaction(&story, &actors, &exhausted_pickup);
    assert(story.state.collection_progress == 6);
    assert(! gb_story_ui_active(&story));

    (void)none;
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
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'story_runtime_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'story_runtime_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/game/story.c'),
                str(ROOT / 'reconstruction/source/game/actors.c'),
                str(ROOT / 'reconstruction/data/story_data.c'),
                str(ROOT / 'reconstruction/data/actor_data.c'),
                str(ROOT / 'reconstruction/data/actor_routes.c'),
                str(td / 'story_runtime_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_pda_pure_runtime_matches_proven_navigation_and_boundaries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inc = root / 'include'
            (inc / 'graveblood').mkdir(parents=True)
            (inc / 'gba.h').write_text('''#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16; typedef uint32_t u32; typedef int32_t s32;
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
''')
            for name in ('input.h', 'story.h', 'actors.h', 'assets.h', 'pda.h'):
                src = ROOT / 'reconstruction/include/graveblood' / name
                if src.is_file():
                    shutil.copy2(src, inc / 'graveblood' / name)
            harness = root / 'pda_harness.c'
            harness.write_text('''#include <assert.h>
#include <graveblood/pda.h>

static GbPdaTick press(GbPdaRuntime* pda, GbStoryState* story, u16 key) {
    GbInput in = { key, key };
    return gb_pda_update(pda, story, &in);
}

int main(void) {
    GbPdaRuntime pda; GbStoryState story = {0}; GbPdaTick tick;
    story.primary_message_stream = 0;
    story.auxiliary_message_streams[0] = 1;
    story.auxiliary_message_streams[1] = 2;
    story.auxiliary_message_streams[2] = -1;

    gb_pda_reset(&pda);
    pda.message_slot = 2;
    gb_pda_open(&pda);
    assert(pda.active == 1 && pda.page == GB_PDA_MESSAGES);
    assert(pda.message_slot == 2);
    assert(pda.friends_cursor == 0 && pda.friends_scroll == 0);

    tick = press(&pda, &story, KEY_R); assert(pda.page == GB_PDA_STATUS && tick.rerender && tick.sfx_id == 11);
    tick = press(&pda, &story, KEY_R); assert(pda.page == GB_PDA_FRIENDS && tick.rerender && tick.sfx_id == 11);
    tick = press(&pda, &story, KEY_R); assert(pda.page == GB_PDA_BACKPACK && tick.rerender && tick.sfx_id == 11);
    tick = press(&pda, &story, KEY_R); assert(pda.page == GB_PDA_BACKPACK && !tick.rerender && tick.sfx_id == -1);
    tick = press(&pda, &story, KEY_L); assert(pda.page == GB_PDA_FRIENDS && tick.sfx_id == 11);

    pda.page = GB_PDA_MESSAGES; pda.message_slot = 0;
    tick = press(&pda, &story, KEY_RIGHT); assert(pda.message_slot == 1 && tick.sfx_id == 4);
    tick = press(&pda, &story, KEY_RIGHT); assert(pda.message_slot == 2 && tick.sfx_id == 4);
    tick = press(&pda, &story, KEY_RIGHT); assert(pda.message_slot == 2 && tick.sfx_id == -1 && !tick.rerender);
    tick = press(&pda, &story, KEY_LEFT); assert(pda.message_slot == 1 && tick.sfx_id == 4);

    pda.page = GB_PDA_FRIENDS; pda.friends_cursor = 0; pda.friends_scroll = 0;
    tick = press(&pda, &story, KEY_UP); assert(pda.friends_cursor == 0 && pda.friends_scroll == 0 && tick.sfx_id == 12);
    tick = press(&pda, &story, KEY_DOWN); assert(pda.friends_cursor == 1 && pda.friends_scroll == 0 && tick.sfx_id == 4);
    tick = press(&pda, &story, KEY_DOWN); assert(pda.friends_cursor == 2 && pda.friends_scroll == 0 && tick.sfx_id == 4);
    tick = press(&pda, &story, KEY_DOWN); assert(pda.friends_cursor == 2 && pda.friends_scroll == 1 && tick.sfx_id == 4);
    tick = press(&pda, &story, KEY_DOWN); assert(pda.friends_scroll == 2 && tick.sfx_id == 4);
    tick = press(&pda, &story, KEY_DOWN); assert(pda.friends_scroll == 3 && tick.sfx_id == 4);
    tick = press(&pda, &story, KEY_DOWN); assert(pda.friends_scroll == 3 && tick.sfx_id == 12 && !tick.rerender);
    pda.friends_cursor = 0; pda.friends_scroll = 1;
    tick = press(&pda, &story, KEY_UP); assert(pda.friends_cursor == 0 && pda.friends_scroll == 0 && tick.sfx_id == 4);

    pda.page = GB_PDA_BACKPACK;
    tick = press(&pda, &story, KEY_B); assert(pda.active == 1 && !tick.return_requested && tick.sfx_id == -1);
    pda.page = GB_PDA_FRIENDS; pda.friends_cursor = 2; pda.friends_scroll = 3;
    tick = press(&pda, &story, KEY_START);
    assert(pda.active == 1 && pda.page == GB_PDA_MESSAGES);
    assert(pda.friends_cursor == 0 && pda.friends_scroll == 0);
    assert(tick.rerender && tick.sfx_id == 6 && tick.stop_reserved_audio);

    pda.return_pending = 1;
    tick = press(&pda, &story, 0);
    assert(tick.return_requested && tick.sfx_id == 7);
    return 0;
}
''')
            exe = root / 'pda_harness'
            cmd = [
                'gcc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                '-I', str(inc), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/game/pda.c'), str(harness), '-o', str(exe),
            ]
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)

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

    def test_stream_ring_translates_and_updates_rows_and_columns(self):
        harness = r"""
#include <graveblood/assets.h>
#include <graveblood/stream.h>
#include <stdio.h>

static int require(int condition, const char* message)
{
    if(! condition)
    {
        fputs(message, stderr);
        fputc('\n', stderr);
        return 0;
    }
    return 1;
}

int main(void)
{
    static const u16 translation[25] = {
        0,
        0x0401, 0x0802, 0x0C03, 0x0004, 0x0005, 0x0006,
        0x0007, 0x0008, 0x0009, 0x000A, 0x000B, 0x000C,
        0x000D, 0x000E, 0x000F, 0x0010, 0x0011, 0x0012,
        0x0013, 0x0014, 0x0015, 0x0016, 0x0017, 0x0018
    };
    static const u16 layer[24] = {
         1,  2,  3,  4,  5,  6,
         7,  8,  9, 10, 11, 12,
        13, 14, 15, 16, 17, 18,
        19, 20, 21, 22, 23, 24
    };
    GbLevelAssets level = { 0 };
    level.world_width_tiles = 6;
    level.world_height_tiles = 4;
    level.translation = translation;
    level.translation_count = 25;

    u16 map[GB_STREAM_MAP_CELLS];
    gb_stream_fill(&level, layer, -1, -1, map);
    if(! require(map[0] == 0x0401, "world 0,0 must land at ring cell 0")) return 1;
    if(! require(map[1] == 0x0802, "translation must preserve vflip")) return 1;
    if(! require(map[2] == 0x0C03, "translation must preserve h/v flip bits")) return 1;
    if(! require(map[31] == 0, "out-of-world left column must be blank")) return 1;
    if(! require(map[31 * 32] == 0, "out-of-world top row must be blank")) return 1;

    for(int i = 0; i < GB_STREAM_MAP_CELLS; ++i) map[i] = 0x7777;
    gb_stream_fill_column(&level, layer, 5, 0, map);
    if(! require(map[5] == 0x0006, "column first cell")) return 1;
    if(! require(map[32 + 5] == 0x000C, "column second cell")) return 1;
    if(! require(map[4] == 0x7777, "column update must not touch neighbor")) return 1;
    if(! require(map[4 * 32 + 5] == 0, "column out-of-world tail must blank")) return 1;

    for(int i = 0; i < GB_STREAM_MAP_CELLS; ++i) map[i] = 0x6666;
    gb_stream_fill_row(&level, layer, 0, 3, map);
    if(! require(map[3 * 32] == 0x0013, "row first cell")) return 1;
    if(! require(map[3 * 32 + 5] == 0x0018, "row sixth cell")) return 1;
    if(! require(map[2 * 32] == 0x6666, "row update must not touch neighbor")) return 1;
    if(! require(map[3 * 32 + 6] == 0, "row out-of-world tail must blank")) return 1;
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
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'stream_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'stream_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/stream.c'),
                str(td / 'stream_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_world_camera_drives_initial_incremental_and_jump_stream_updates(self):
        harness = r"""
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
{
    (void) level; ++full_count; last_a = left; last_b = top;
}
void gb_video_stream_column(const GbLevelAssets* level, s16 world_x, s16 top)
{
    (void) level; ++column_count; last_a = world_x; last_b = top;
}
void gb_video_stream_row(const GbLevelAssets* level, s16 left, s16 world_y)
{
    (void) level; ++row_count; last_a = left; last_b = world_y;
}

static int require(int condition, const char* message)
{
    if(! condition) { fputs(message, stderr); fputc('\n', stderr); return 0; }
    return 1;
}

int main(void)
{
    GbLevelAssets level = { 0 };
    level.world_width_tiles = 100;
    level.world_height_tiles = 100;
    GbWorld world;
    gb_world_load(&world, &level);
    if(! require(world.stream_valid == 0, "load must invalidate stream origin")) return 1;

    gb_world_update_camera(&world, 120, 88);
    if(! require(full_count == 1 && column_count == 0 && row_count == 0, "initial camera must full-fill")) return 1;
    if(! require(world.stream_valid == 1 && world.stream_tile_x == 0 && world.stream_tile_y == 0, "initial origin")) return 1;

    gb_world_update_camera(&world, 128, 88);
    if(! require(full_count == 1 && column_count == 1, "one-tile x crossing must update one column")) return 1;
    if(! require(last_a == 32 && last_b == 0, "right edge column must be new origin + 31")) return 1;
    if(! require(world.stream_tile_x == 1 && world.stream_tile_y == 0, "x origin update")) return 1;

    gb_world_update_camera(&world, 128, 96);
    if(! require(row_count == 1, "one-tile y crossing must update one row")) return 1;
    if(! require(last_a == 1 && last_b == 32, "bottom row must use new origin + 31")) return 1;
    if(! require(world.stream_tile_x == 1 && world.stream_tile_y == 1, "y origin update")) return 1;

    gb_world_update_camera(&world, 160, 96);
    if(! require(full_count == 2, "multi-tile jump must full-fill")) return 1;
    if(! require(last_a == 5 && last_b == 1, "jump full-fill origin")) return 1;
    if(! require(last_camera_x == 40 && last_camera_y == 8, "camera offsets must still apply")) return 1;
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
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'world_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'world_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/world.c'),
                str(td / 'world_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
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

    def test_audio_backend_matches_canonical_fifo_dma_timer_contract(self):
        audio = (ROOT / 'reconstruction/source/engine/audio.c').read_text(encoding='utf-8')
        makefile = (ROOT / 'reconstruction/Makefile').read_text(encoding='utf-8')
        self.assertIn('0x04000082u', audio)
        self.assertIn('0x04000084u', audio)
        self.assertIn('0x040000A0u', audio)
        self.assertIn('0x040000BCu', audio)
        self.assertIn('0x040000C0u', audio)
        self.assertIn('0x040000C6u', audio)
        self.assertIn('0x04000100u', audio)
        self.assertIn('0x04000102u', audio)
        self.assertIn('0x04000104u', audio)
        self.assertIn('0x04000106u', audio)
        self.assertIn('0x0B04', audio)
        self.assertIn('0xB200', audio)
        self.assertIn('0xFC00', audio)
        self.assertIn('0xFF00', audio)
        self.assertIn('GB_AUDIO_BUFFER_SAMPLES', audio)
        self.assertIn('gb_audio_buffers[2][GB_AUDIO_BUFFER_SAMPLES]', audio)
        self.assertIn('irqSet(IRQ_TIMER1, gb_audio_timer1_irq)', audio)
        self.assertIn('irqEnable(IRQ_TIMER1)', audio)
        self.assertIn('irqDisable(IRQ_TIMER1)', audio)
        self.assertIn('SFILES := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))', makefile)
        self.assertTrue((ROOT / 'reconstruction/data/audio_samples.s').is_file())

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
#define IRQ_TIMER1 5
void irqInit(void);
void irqSet(int irq, void (*handler)(void));
void irqEnable(int irq);
void irqDisable(int irq);
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            obj = td / 'audio.o'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                '-c', str(ROOT / 'reconstruction/source/engine/audio.c'), '-o', str(obj),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(obj.is_file())

    def test_audio_pcm_incbin_unit_assembles_for_arm_from_build_like_directory(self):
        source = ROOT / 'reconstruction/data/audio_samples.s'
        self.assertTrue(source.is_file())
        clang = subprocess.run(['bash', '-lc', 'command -v clang'], capture_output=True, text=True, check=True).stdout.strip()
        with tempfile.TemporaryDirectory(dir=ROOT / 'reconstruction') as td:
            td = Path(td)
            obj = td / 'audio_samples.o'
            proc = subprocess.run([
                clang, '--target=arm-none-eabi', '-mcpu=arm7tdmi', '-mthumb',
                '-c', '../data/audio_samples.s', '-o', str(obj),
            ], cwd=td, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(obj.is_file())
            self.assertGreater(obj.stat().st_size, 4_000_000)
            nm = subprocess.run(['nm', '-g', str(obj)], capture_output=True, text=True, check=True).stdout
            for sample_id in range(14):
                self.assertIn(f'gb_audio_sample_{sample_id:02d}_start', nm)
                self.assertIn(f'gb_audio_sample_{sample_id:02d}_end', nm)

    def test_audio_runtime_channel_allocation_looping_and_mix_vector(self):
        harness = r"""
#include <assert.h>
#include <graveblood/audio.h>

static const s8 music0[] = { 32, -32, 64, -64 };
static const s8 music1[] = { 16, -16, 8, -8 };
static const s8 music2[] = { 1, 2, 3, 4 };
static const s8 sfx3[] = { 127, -128, 64, -64 };
static const s8 sfx4[] = { 4, 4, 4, 4 };
static const s8 sfx5[] = { 5, 5, 5, 5 };
static const s8 sfx6[] = { 6, 6, 6, 6 };
static const s8 sfx7[] = { 7, 7, 7, 7 };
static const s8 sfx8[] = { 8, 8, 8, 8 };
static const s8 sfx9[] = { 9, 9, 9, 9 };
static const s8 sfx10[] = { 10, 10, 10, 10 };
static const s8 sfx11[] = { 11, 11, 11, 11 };
static const s8 sfx12[] = { 12, 12, 12, 12 };
static const s8 sfx13[] = { 13, 13, 13, 13 };

const GbAudioSample gb_audio_samples[GB_AUDIO_SAMPLE_COUNT] = {
    { music0, 4, GB_AUDIO_ROLE_MUSIC },
    { music1, 4, GB_AUDIO_ROLE_MUSIC },
    { music2, 4, GB_AUDIO_ROLE_MUSIC },
    { sfx3, 4, GB_AUDIO_ROLE_SFX },
    { sfx4, 4, GB_AUDIO_ROLE_SFX },
    { sfx5, 4, GB_AUDIO_ROLE_SFX },
    { sfx6, 4, GB_AUDIO_ROLE_SFX },
    { sfx7, 4, GB_AUDIO_ROLE_SFX },
    { sfx8, 4, GB_AUDIO_ROLE_SFX },
    { sfx9, 4, GB_AUDIO_ROLE_SFX },
    { sfx10, 4, GB_AUDIO_ROLE_SFX },
    { sfx11, 4, GB_AUDIO_ROLE_SFX },
    { sfx12, 4, GB_AUDIO_ROLE_SFX },
    { sfx13, 4, GB_AUDIO_ROLE_SFX },
};

int main(void)
{
    s8 mixed[8] = { 0 };

    gb_audio_init();
    assert(gb_audio_play_sfx(0) == -1);
    assert(gb_audio_play_music(3) == -1);

    assert(gb_audio_play_music(0) == 0);
    assert(gb_audio_play_sfx(3) == 1);
    gb_audio_mix_block(mixed, 8);
    assert(mixed[0] == 85);
    assert(mixed[1] == -87);
    assert(mixed[2] == 84);
    assert(mixed[3] == -84);
    assert(mixed[4] == 27);
    assert(mixed[5] == -27);
    assert(mixed[6] == 54);
    assert(mixed[7] == -54);

    /* The one-shot retired after its aligned four-byte payload. */
    assert(gb_audio_play_sfx(4) == 1);
    gb_audio_stop_channel(1);

    /* Music replacement reuses the reserved music channel. */
    assert(gb_audio_play_music(1) == 0);
    gb_audio_set_channel_volume(0, 0);
    gb_audio_mix_block(mixed, 4);
    assert(mixed[0] == 0 && mixed[1] == 0 && mixed[2] == 0 && mixed[3] == 0);

    gb_audio_init();
    assert(gb_audio_play_music(0) == 0);
    assert(gb_audio_play_sfx(3) == 1);
    assert(gb_audio_play_sfx(4) == 2);
    assert(gb_audio_play_sfx(5) == 3);
    assert(gb_audio_play_sfx(6) == 4);
    assert(gb_audio_play_sfx(7) == 5);
    assert(gb_audio_play_sfx(8) == 6);
    assert(gb_audio_play_sfx(9) == 7);
    assert(gb_audio_play_sfx(10) == -1);

    gb_audio_stop_music();
    assert(gb_audio_play_sfx(10) == 0);
    gb_audio_shutdown();
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
#endif
"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'audio_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'audio_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-DGB_AUDIO_TESTING=1',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/audio.c'),
                str(td / 'audio_test.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_public_repo_identity_and_no_credits_file(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('Graveblood_RE', readme)
        self.assertFalse((ROOT / 'CREDITS.md').exists())


    def test_game_boots_title_then_hands_off_to_level7_with_sfx6(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('#include <graveblood/scene.h>', game)
        self.assertIn('GbSceneRuntime scene;', game)
        self.assertIn('gb_scene_init(&scene);', game)
        self.assertIn('gb_video_load_title();', game)
        self.assertIn('scene.active == GB_SCENE_TITLE', game)
        self.assertIn('gb_scene_update_title(&scene, &input)', game)
        self.assertIn('tick.play_start_sfx', game)
        self.assertIn('gb_audio_play_sfx(6)', game)
        self.assertIn('tick.enter_gameplay', game)
        self.assertIn('tick.gameplay_level', game)
        self.assertNotIn('gb_enter_level(&world, &player, &actors, &story, GB_START_LEVEL);', game)

    def test_game_pda_scene_opens_on_start_reopens_and_preserves_latent_return_path(self):
        scene_h = (ROOT / 'reconstruction/include/graveblood/scene.h').read_text(encoding='utf-8')
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('GB_SCENE_PDA', scene_h)
        self.assertIn('#include <graveblood/pda.h>', game)
        self.assertIn('GbPdaRuntime pda;', game)
        self.assertIn('gb_pda_reset(&pda);', game)
        self.assertIn('scene.active == GB_SCENE_PDA', game)
        self.assertIn('gb_pda_update(&pda, &story.state, &input)', game)
        self.assertIn('input.pressed & KEY_START', game)
        self.assertIn('gb_audio_stop_channel(0);', game)
        self.assertIn('gb_audio_stop_channel(1);', game)
        self.assertIn('gb_audio_stop_channel(2);', game)
        self.assertIn('gb_audio_play_sfx(6);', game)
        self.assertIn('gb_pda_open(&pda);', game)
        self.assertIn('scene.active = GB_SCENE_PDA;', game)
        self.assertIn('gb_video_load_pda(world.assets, &pda, &story);', game)
        self.assertIn('pda_tick.return_requested', game)
        self.assertIn('scene.active = GB_SCENE_GAMEPLAY;', game)
        self.assertIn('world.stream_valid = 0;', game)
        self.assertIn('gb_audio_play_music(world.assets->level_id == 10 ? 1 : 0);', game)

    def test_title_video_loads_exact_layers_obj_assets_patches_prompt_and_restores_gameplay_display(self):
        header = (ROOT / 'reconstruction/include/graveblood/video.h').read_text(encoding='utf-8')
        for name in (
            'gb_video_load_title',
            'gb_video_title_set_animation',
            'gb_video_title_set_prompt_visible',
        ):
            self.assertIn(name, header)

        harness = r'''
#include <assert.h>
#include <string.h>
#include <graveblood/video.h>

volatile u16 gb_test_vcount;
volatile u16 gb_test_dispcnt;
volatile u16 gb_test_bgctrl[4];
volatile GbTestBgOffset gb_test_bg_offset[4];
volatile u16 gb_test_bg_colors[256];
volatile u16 gb_test_obj_colors[256];
volatile u16 gb_test_oam[512];
volatile u16 gb_test_vram[0x18000 / 2];

const u16 gb_actor_obj_palette[256] = {0};
const u16 gb_player_obj_palette[16] = {0};
const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128] = {0};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {0};

static const u16 gameplay_palette[256] = {0x1234};
static const u16 gameplay_tiles[1] = {0x5678};
static const GbLevelAssets gameplay_level = {
    .level_id = 7,
    .graphics_variant = 0,
    .world_width_tiles = 32,
    .world_height_tiles = 32,
    .fixed_width_tiles = 0,
    .fixed_height_tiles = 0,
    .bg_tile_halfwords = 1,
    .translation_count = 0,
    .bg_palette = gameplay_palette,
    .bg_tiles = gameplay_tiles,
};

int main(void)
{
    for(unsigned i = 0; i < sizeof(gb_test_vram) / sizeof(gb_test_vram[0]); ++i)
        gb_test_vram[i] = 0xBEEF;
    for(unsigned i = 0; i < sizeof(gb_test_oam) / sizeof(gb_test_oam[0]); ++i)
        gb_test_oam[i] = 0;
    for(unsigned i = 0; i < 256; ++i)
    {
        gb_test_bg_colors[i] = 0xA55A;
        gb_test_obj_colors[i] = 0x5AA5;
    }

    gb_video_load_title();

    assert(gb_test_dispcnt == (MODE_0 | BG0_ON | BG1_ON | BG2_ON | BG3_ON | OBJ_ON));
    assert((gb_test_dispcnt & OBJ_1D_MAP) == 0);
    assert(gb_test_bgctrl[0] ==
           (BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(27) | BG_PRIORITY(0)));
    assert(gb_test_bgctrl[1] ==
           (BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(28) | BG_PRIORITY(1)));
    assert(gb_test_bgctrl[2] ==
           (BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(29) | BG_PRIORITY(2)));
    assert(gb_test_bgctrl[3] ==
           (BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(30) | BG_PRIORITY(3)));
    for(int i = 0; i < 4; ++i)
        assert(gb_test_bg_offset[i].x == 0 && gb_test_bg_offset[i].y == 0);

    assert(gb_test_bg_colors[0] == gb_title_bg_palette[0]);
    assert(gb_test_bg_colors[GB_TITLE_BG_PALETTE_COUNT - 1] ==
           gb_title_bg_palette[GB_TITLE_BG_PALETTE_COUNT - 1]);
    assert(gb_test_bg_colors[GB_TITLE_BG_PALETTE_COUNT] == 0xA55A);
    assert(gb_test_obj_colors[0] == gb_title_obj_palette[0]);
    assert(gb_test_obj_colors[GB_TITLE_OBJ_PALETTE_COUNT - 1] ==
           gb_title_obj_palette[GB_TITLE_OBJ_PALETTE_COUNT - 1]);
    assert(gb_test_obj_colors[GB_TITLE_OBJ_PALETTE_COUNT] == 0x5AA5);
    assert(gb_test_obj_colors[223] == 0x5AA5);
    assert(gb_test_obj_colors[224] == gb_title_obj_high_palette[0]);
    assert(gb_test_obj_colors[255] ==
           gb_title_obj_high_palette[GB_TITLE_OBJ_HIGH_PALETTE_COUNT - 1]);

    assert(gb_test_vram[0] == gb_title_bg_tiles[0]);
    volatile u16 *obj_vram = (volatile u16*)SPR_VRAM(0);
    assert(obj_vram[0] == gb_title_obj_tiles[0]);
    assert(obj_vram[GB_TITLE_OBJ_TILE_HALFWORDS - 1] ==
           gb_title_obj_tiles[GB_TITLE_OBJ_TILE_HALFWORDS - 1]);

    volatile u16 *prompt_map = (volatile u16*)MAP_BASE_ADR(27);
    volatile u16 *title_map = (volatile u16*)MAP_BASE_ADR(28);
    volatile u16 *backing_left = (volatile u16*)MAP_BASE_ADR(29);
    volatile u16 *backing_right = (volatile u16*)MAP_BASE_ADR(30);
    assert(title_map[0] == gb_title_map[0]);
    assert(title_map[19 * 32 + 29] == gb_title_map[19 * 30 + 29]);
    assert(title_map[30] == 0);
    assert(title_map[20 * 32] == 0);
    assert(prompt_map[0] == 0);
    for(int y = 0; y < 32; ++y)
    {
        for(int x = 0; x < 32; ++x)
        {
            assert(backing_left[y * 32 + x] == gb_title_underlay_tile);
            assert(backing_right[y * 32 + x] == gb_title_underlay_tile);
        }
    }

    volatile u16 *char_mem = (volatile u16*)CHAR_BASE_ADR(0);
    assert(char_mem[0x2F00 / 2] == gb_title_anim_a[0][0]);
    assert(char_mem[0x2F00 / 2 + GB_TITLE_ANIM_A_HALFWORDS - 1] ==
           gb_title_anim_a[0][GB_TITLE_ANIM_A_HALFWORDS - 1]);
    assert(char_mem[0x3B00 / 2] == gb_title_anim_b[0][0]);
    assert(char_mem[0x3B00 / 2 + GB_TITLE_ANIM_B_HALFWORDS - 1] ==
           gb_title_anim_b[0][GB_TITLE_ANIM_B_HALFWORDS - 1]);

    for(int i = 0; i < GB_TITLE_PROMPT_LENGTH; ++i)
        assert(prompt_map[9 * 32 + 9 + i] == gb_title_prompt_tiles[i]);
    for(int i = 0; i < 128; ++i)
    {
        assert(gb_test_oam[i * 4] == 0x02F0);
        assert(gb_test_oam[i * 4 + 1] == 0x01F0);
        assert(gb_test_oam[i * 4 + 2] == 0x0C00);
        assert(gb_test_oam[i * 4 + 3] == 0);
    }

    gb_video_title_set_animation(2);
    assert(char_mem[0x2F00 / 2] == gb_title_anim_a[2][0]);
    assert(char_mem[0x3B00 / 2] == gb_title_anim_b[2][0]);

    gb_video_title_set_prompt_visible(0);
    for(int i = 0; i < GB_TITLE_PROMPT_LENGTH; ++i)
        assert(prompt_map[9 * 32 + 9 + i] == gb_title_blank_tiles[i]);

    gb_video_load_level(&gameplay_level);
    assert(gb_test_dispcnt ==
           (MODE_0 | BG0_ON | BG1_ON | BG2_ON | BG3_ON | OBJ_ON | OBJ_1D_MAP));
    assert(gb_test_bgctrl[0] ==
           (BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(27) | BG_PRIORITY(0)));
    assert(gb_test_bgctrl[3] ==
           (BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(30) | BG_PRIORITY(3)));
    assert(gb_test_bg_colors[0] == 0x1234);
    assert(gb_test_vram[0] == 0x5678);
    return 0;
}
'''
        gba_h = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
typedef struct { volatile u16 x; volatile u16 y; } GbTestBgOffset;
extern volatile u16 gb_test_vcount;
extern volatile u16 gb_test_dispcnt;
extern volatile u16 gb_test_bgctrl[4];
extern volatile GbTestBgOffset gb_test_bg_offset[4];
extern volatile u16 gb_test_bg_colors[256];
extern volatile u16 gb_test_obj_colors[256];
extern volatile u16 gb_test_oam[512];
extern volatile u16 gb_test_vram[0x18000 / 2];
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
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
'''
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'title_video_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'title_video_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-O0', '-Wall', '-Wextra', '-Werror',
                '-ffunction-sections', '-fdata-sections',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/engine/video.c'),
                str(ROOT / 'reconstruction/data/title_assets.c'),
                str(td / 'title_video_test.c'),
                '-Wl,--gc-sections', '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    def test_title_scene_runtime_matches_recovered_cadence_blink_and_transition(self):
        scene_h = ROOT / 'reconstruction/include/graveblood/scene.h'
        scene_c = ROOT / 'reconstruction/source/game/scene.c'
        self.assertTrue(scene_h.is_file(), scene_h)
        self.assertTrue(scene_c.is_file(), scene_c)
        harness = r'''
#include <assert.h>
#include <graveblood/scene.h>

static GbInput input_with_pressed(u16 pressed)
{
    GbInput input = {0, pressed};
    return input;
}

int main(void)
{
    GbSceneRuntime scene;
    gb_scene_init(&scene);
    assert(scene.active == GB_SCENE_TITLE);
    assert(scene.title_animation_state == 0);
    assert(scene.title_animation_counter == 0);
    assert(scene.transition_delay == 0);

    GbInput none = input_with_pressed(0);
    for(int i = 0; i < 6; ++i)
    {
        GbSceneTick tick = gb_scene_update_title(&scene, &none);
        assert(tick.enter_gameplay == 0);
        assert(scene.title_animation_state == 0);
    }
    gb_scene_update_title(&scene, &none);
    assert(scene.title_animation_state == 1);
    assert(scene.title_animation_counter == 0);

    GbSceneRuntime blink;
    gb_scene_init(&blink);
    for(int i = 0; i < 15; ++i)
        assert(gb_scene_update_title(&blink, &none).prompt_visible == 1);
    assert(gb_scene_update_title(&blink, &none).prompt_visible == 0);
    for(int i = 0; i < 15; ++i)
        assert(gb_scene_update_title(&blink, &none).prompt_visible == 0);
    assert(gb_scene_update_title(&blink, &none).prompt_visible == 1);

    GbSceneRuntime start;
    gb_scene_init(&start);
    GbInput pressed = input_with_pressed(0x0008);
    GbSceneTick first = gb_scene_update_title(&start, &pressed);
    assert(first.play_start_sfx == 1);
    assert(first.enter_gameplay == 0);
    assert(start.pending_gameplay == 1);
    assert(start.pending_level == 7);
    assert(start.transition_delay == 120);

    GbSceneTick repeated = gb_scene_update_title(&start, &pressed);
    assert(repeated.play_start_sfx == 1);
    assert(start.transition_delay == 119);

    for(int i = 0; i < 119; ++i)
    {
        GbSceneTick tick = gb_scene_update_title(&start, &none);
        assert(tick.enter_gameplay == 0);
    }
    assert(start.transition_delay == 0);
    GbSceneTick enter = gb_scene_update_title(&start, &none);
    assert(enter.enter_gameplay == 1);
    assert(enter.gameplay_level == 7);
    assert(start.active == GB_SCENE_GAMEPLAY);
    return 0;
}
'''
        gba_h = r'''
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
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'scene_test.c').write_text(harness, encoding='utf-8')
            exe = td / 'scene_test'
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(scene_c), str(td / 'scene_test.c'), '-o', str(exe),
            ], check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

if __name__ == '__main__':
    unittest.main()
