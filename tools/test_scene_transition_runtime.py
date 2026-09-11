#!/usr/bin/env python3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GBA_H = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;
#define KEY_START (1u << 3)
#endif
'''
HARNESS = r'''
#include <assert.h>
#include <graveblood/scene.h>
int main(void)
{
    GbSceneRuntime scene;
    gb_scene_init(&scene);
    scene.active = GB_SCENE_GAMEPLAY;
    gb_scene_request_gameplay(&scene, 10, 10);
    assert(scene.pending_gameplay == 1);
    assert(scene.pending_level == 10);
    assert(scene.transition_delay == 10);
    for(int i = 0; i < 10; ++i)
    {
        GbSceneTick t = gb_scene_update_pending(&scene);
        assert(t.enter_gameplay == 0);
    }
    assert(scene.transition_delay == 0);
    GbSceneTick enter = gb_scene_update_pending(&scene);
    assert(enter.enter_gameplay == 1);
    assert(enter.gameplay_level == 10);
    assert(scene.pending_gameplay == 0);
    assert(scene.active == GB_SCENE_GAMEPLAY);

    /* A pending request is not replaced by a repeated trigger. */
    gb_scene_request_gameplay(&scene, 7, 10);
    gb_scene_update_pending(&scene);
    assert(scene.transition_delay == 9);
    gb_scene_request_gameplay(&scene, 3, 10);
    assert(scene.pending_level == 7);
    assert(scene.transition_delay == 9);
    return 0;
}
'''

class SceneTransitionRuntimeTests(unittest.TestCase):
    def test_game_routes_wardrobe_and_portals_through_ten_update_queue(self):
        game = (ROOT / 'reconstruction/source/game/graveblood.c').read_text(encoding='utf-8')
        self.assertIn('gb_scene_request_gameplay(&scene, 7, 10);', game)
        self.assertIn('gb_scene_request_gameplay(&scene, (u8)portal_target, 10);', game)
        self.assertIn('gb_scene_update_pending(&scene)', game)
        self.assertNotIn('gb_enter_level(&world, &player, &actors, &story, portal_target);', game)

    def test_generic_scene_request_uses_exact_countdown_semantics(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td/'gba.h').write_text(GBA_H)
            (td/'h.c').write_text(HARNESS)
            exe=td/'t'
            proc=subprocess.run([
                'cc','-std=c11','-Wall','-Wextra','-Werror',
                '-I',str(td),'-I',str(ROOT/'reconstruction/include'),
                str(ROOT/'reconstruction/source/game/scene.c'),str(td/'h.c'),'-o',str(exe)
            ],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(0,proc.returncode,proc.stderr)
            subprocess.run([str(exe)],cwd=ROOT,check=True)

if __name__=='__main__': unittest.main()
