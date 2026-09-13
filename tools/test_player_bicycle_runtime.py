#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('GRAVEBLOOD_ROM', ROOT.parent / 'Graveblood 0.0.1.1.5.2 demo.gba'))
ROM_BASE = 0x08000000
OBJ_TILES_SOURCE = 0x08310654


def _u16(data: bytes, addr: int) -> int:
    return struct.unpack_from('<H', data, addr - ROM_BASE)[0]


def _u32(data: bytes, addr: int) -> int:
    return struct.unpack_from('<I', data, addr - ROM_BASE)[0]


def _expected_bicycle_blob(data: bytes) -> bytes:
    frame_offsets = struct.unpack_from('<6I', data, 0x08019968 - ROM_BASE)
    initial = bytearray(data[OBJ_TILES_SOURCE - ROM_BASE:OBJ_TILES_SOURCE - ROM_BASE + 0x8000])
    out = bytearray()
    for frame_offset in frame_offsets:
        vram = bytearray(initial)
        uploads = (
            (0x151, frame_offset + 0x1501, 2),
            (0x160, frame_offset + 0x1510, 4),
            (0x170, frame_offset + 0x1520, 4),
            (0x180, frame_offset + 0x1530, 4),
            (0x190, frame_offset + 0x1540, 4),
        )
        for dst_tile, src_tile, count in uploads:
            src = OBJ_TILES_SOURCE - ROM_BASE + src_tile * 64
            dst = dst_tile * 64
            vram[dst:dst + count * 64] = data[src:src + count * 64]

        # Player_draw submits five enum-3 (16x16) sprites from these 2D roots.
        # Materialize each recovered 2D root as a contiguous asset payload; runtime restages it sparsely.
        for root_tile in (0x151, 0x170, 0x172, 0x190, 0x192):
            for ty in range(2):
                for tx in range(2):
                    tile = root_tile + tx + ty * 16
                    out.extend(vram[tile * 64:(tile + 1) * 64])
    return bytes(out)


class PlayerBicycleRomContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = ROM.read_bytes()

    def test_rom_proves_mode2_draw_r_action_and_clear(self):
        # Player_draw reads the shared mode and suppresses the parked Level-9/10
        # composite when it is exactly 2.
        self.assertEqual(0x030005F4, _u32(self.data, 0x08006960))
        self.assertEqual((0x681B, 0x2B02, 0xD007), tuple(_u16(self.data, a) for a in (0x0800661C, 0x0800661E, 0x08006620)))

        # Fresh R in the mode-2 normal-controller path branches to the one-shot
        # helper with sound 10 and the unusual volume 30 (0x1E).
        self.assertEqual((0x211E, 0x200A), tuple(_u16(self.data, a) for a in (0x08009C12, 0x08009C14)))

        # The Level-10 5->6 transition explicitly clears the same shared mode.
        self.assertEqual(0x030005F4, _u32(self.data, 0x08009480))
        self.assertEqual(0x6007, _u16(self.data, 0x080093AA))

        # The six riding frames index six ROM-side source offsets.
        self.assertEqual((0, 4, 8, 0x50, 0x54, 0x58),
                         struct.unpack_from('<6I', self.data, 0x08019968 - ROM_BASE))

    def test_rom_proves_treetype20_fresh_a_commits_mode2(self):
        self.assertEqual(0x030005F4, _u32(self.data, 0x08004324))
        self.assertEqual((0x23E5, 0x2280, 0x009B, 0x0292, 0x50CA),
                         tuple(_u16(self.data, 0x080041BC + i * 2) for i in range(5)))
        self.assertEqual((0x4B55, 0x601D),
                         tuple(_u16(self.data, a) for a in (0x080041CC, 0x080041CE)))


class PlayerBicycleRuntimeTests(unittest.TestCase):
    def test_runtime_reproduces_contact_state_r_sfx_animation_and_clear(self):
        harness = r'''
#include <assert.h>
#include <graveblood/story.h>

int main(void)
{
    GbLevelAssets level = {0};
    GbPlayer player = {0};
    GbInput input = {0};
    u16 volume = 0;

    level.level_id = 9;
    input.held = KEY_A;
    input.pressed = KEY_A;

    /* Exact ROM cell math: ((x-8)>>3) in {62,63} and
       ((y-24)>>3) in {55,56}.  These are the inclusive pixel bounds. */
    gb_player_spawn(&player, 504, 464);
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_TRAVERSED);
    assert(player.bicycle_mode == 2);
    assert(player.request_y_fixed == (512 - 464) * 256);

    gb_player_spawn(&player, 519, 479);
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_TRAVERSED);
    assert(player.bicycle_mode == 2);

    gb_player_spawn(&player, 503, 464);
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_NONE);
    gb_player_spawn(&player, 520, 479);
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_NONE);
    gb_player_spawn(&player, 504, 463);
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_NONE);
    gb_player_spawn(&player, 519, 480);
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_NONE);

    /* Fresh A is mandatory. */
    gb_player_spawn(&player, 504, 464);
    input.pressed = 0;
    assert(gb_story_try_level9_treetype20_action(&level, &player, &input) == GB_STORY_GATE_NONE);
    assert(player.bicycle_mode == 0);

    /* Mode 2 uses a six-frame animation even if the ordinary state is idle. */
    player.bicycle_mode = 2;
    player.animation_state = GB_PLAYER_ANIM_IDLE;
    player.animation_frame = 6;
    player.animation_countdown = 0;
    input.held = 0;
    input.pressed = 0;
    gb_player_update(&player, &level, &input);
    assert(player.animation_frame == 1);

    /* Fresh R queues exactly SFX10 at ROM volume 30; held R alone is silent. */
    input.held = KEY_R;
    input.pressed = KEY_R;
    gb_player_update(&player, &level, &input);
    assert(gb_player_take_pending_sfx(&player, &volume) == 10);
    assert(volume == 30);
    assert(gb_player_take_pending_sfx(&player, &volume) == -1);

    input.held = KEY_R;
    input.pressed = 0;
    gb_player_update(&player, &level, &input);
    assert(gb_player_take_pending_sfx(&player, &volume) == -1);

    /* The boundary changes controller mode but preserves the separate bicycle mode. */
    player.x_fixed = 2556 << 8;
    player.x = 2556;
    assert(gb_player_try_level10_boundary(&player, 9) == 1);
    assert(player.script_mode == 5 && player.bicycle_mode == 2);

    /* ROM clears bicycle mode exactly as Level-10 mode 5 switches to mode 6. */
    level.level_id = 10;
    player.x_fixed = 701 << 8;
    player.x = 701;
    player.script_counter = 350;
    input.held = input.pressed = 0;
    gb_player_update(&player, &level, &input);
    assert(player.script_mode == 6);
    assert(player.bicycle_mode == 0);
    return 0;
}
'''
        gba_h = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_SELECT (1u << 2)
#define KEY_START (1u << 3)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#define KEY_R (1u << 8)
#define KEY_L (1u << 9)
#endif
'''
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(gba_h, encoding='utf-8')
            (td / 'bike_runtime.c').write_text(harness, encoding='utf-8')
            exe = td / 'bike_runtime'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/game/story.c'),
                str(ROOT / 'reconstruction/source/game/player.c'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/data/story_data.c'),
                str(td / 'bike_runtime.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr + run.stdout)

    def test_generated_bicycle_pixels_match_rom_composition(self):
        data = ROM.read_bytes()
        expected = _expected_bicycle_blob(data)
        self.assertEqual(7680, len(expected))
        self.assertEqual('d860cd3f58c7df767c264d7145f0691df546b263b983b29745cfeee6dfaf39d9',
                         hashlib.sha256(expected).hexdigest())

        source = ROOT / 'reconstruction/data/player_bicycle_sprite.c'
        self.assertTrue(source.exists(), 'missing generated bicycle sprite bank')
        text = source.read_text(encoding='utf-8')
        match = re.search(r'gb_player_bicycle_obj_frames\s*\[[^]]+\]\s*=\s*\{(.*?)\};', text, re.S)
        self.assertIsNotNone(match, 'missing gb_player_bicycle_obj_frames array')
        values = [int(token, 16) for token in re.findall(r'0x([0-9A-Fa-f]{1,4})', match.group(1))]
        actual = b''.join(struct.pack('<H', value) for value in values)
        self.assertEqual(expected, actual)

    def test_game_and_video_are_wired_for_bicycle_state(self):
        actor_h = (ROOT / 'reconstruction/include/graveblood/actor.h').read_text(encoding='utf-8')
        assets_h = (ROOT / 'reconstruction/include/graveblood/assets.h').read_text(encoding='utf-8')
        video = (ROOT / 'reconstruction/source/engine/video.c').read_text(encoding='utf-8')
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        audio_h = (ROOT / 'reconstruction/include/graveblood/audio.h').read_text(encoding='utf-8')

        self.assertIn('bicycle_mode', actor_h)
        self.assertIn('GB_PLAYER_BICYCLE_FRAME_COUNT = 6', assets_h)
        self.assertIn('GB_PLAYER_BICYCLE_SPRITE_COUNT = 5', assets_h)
        self.assertIn('gb_player_bicycle_obj_frames', assets_h)
        self.assertIn('player->bicycle_mode == 2', video)
        self.assertIn('gb_video_draw_player_bicycle', video)
        self.assertIn('saved_bicycle_mode', game)
        self.assertIn('gb_player_take_pending_sfx', game)
        self.assertIn('gb_audio_play_sfx_volume', game)
        self.assertIn('gb_audio_play_sfx_volume', audio_h)


if __name__ == '__main__':
    unittest.main()
