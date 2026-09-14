import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GBA_H = r'''
#ifndef GBA_H
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
'''

class InteractiveRuntimeParityTests(unittest.TestCase):
    def test_start_closes_pda_through_gameplay_return_path(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / 'gba.h').write_text(GBA_H)
            harness = td / 'pda.c'
            harness.write_text(r'''
#include <assert.h>
#include <graveblood/pda.h>
int main(void) {
    GbPdaRuntime pda; GbStoryState story = {0};
    gb_pda_reset(&pda); gb_pda_open(&pda);
    GbInput in = { KEY_START, KEY_START };
    GbPdaTick tick = gb_pda_update(&pda, &story, &in);
    assert(pda.active == 0);
    assert(tick.return_requested == 1);
    assert(tick.rerender == 0);
    assert(tick.sfx_id == 7);
    return 0;
}
''')
            exe = td / 'pda'
            proc = subprocess.run([
                'cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(td),
                '-I',str(ROOT/'reconstruction/include'),
                str(ROOT/'reconstruction/source/game/pda.c'),str(harness),'-o',str(exe)
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_normal_dialogue_uses_recovered_20x6_window_and_border_tiles(self):
        video = (ROOT/'reconstruction/source/engine/video.c').read_text()
        self.assertIn('#define GB_DIALOGUE_WINDOW_MAP_X 1', video)
        self.assertIn('#define GB_DIALOGUE_WINDOW_MAP_Y 13', video)
        self.assertIn('#define GB_DIALOGUE_WINDOW_COLUMNS 20', video)
        self.assertIn('#define GB_DIALOGUE_WINDOW_ROWS 6', video)
        self.assertIn('#define GB_DIALOGUE_TEXT_COLUMNS 18', video)
        self.assertIn('#define GB_DIALOGUE_TEXT_ROWS 4', video)
        self.assertIn('GB_DIALOGUE_BORDER_VERTICAL_TILE 3', video)
        self.assertIn('GB_DIALOGUE_BORDER_CORNER_TILE 4', video)
        self.assertIn('GB_DIALOGUE_BORDER_HORIZONTAL_TILE 5', video)
        self.assertIn('gb_dialogue_ui_upload', video)

    def test_gameplay_lighting_preserves_reference_skipped_obj_pairs(self):
        video = (ROOT/'reconstruction/source/engine/video.c').read_text()
        compact = ' '.join(video.split())
        self.assertIn('if(pair == 4u || pair > 199u) { continue; }', compact)
        self.assertNotIn('pair_index == 4u || pair_index > 199u', compact)

    def test_physical_npc_fresh_a_emits_dialogue_event_at_its_slot(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td/'gba.h').write_text(GBA_H)
            harness = td/'npc.c'
            harness.write_text(r'''
#include <assert.h>
#include <graveblood/actors.h>
const GbActorLevelIndexSpan gb_actor_level_spans[11] = { [1] = { 0, 1 } };
const u8 gb_player_physical_indices[11] = { [1] = 0 };
const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS] = {{{0}}};
int main(void) {
    GbActorDescriptor desc = {0};
    desc.actor_class = GB_ACTOR_NPC; desc.state = 2; desc.dial = 7; desc.legs_color = 0;
    GbLevelAssets level = {0}; level.level_id = 1;
    GbActorSystem sys = {0}; sys.level = &level; sys.count = 1; sys.actors[0].active = 1;
    sys.actors[0].descriptor = &desc; sys.actors[0].story_overlay_index = GB_ACTOR_STORY_NONE;
    sys.actors[0].fixed_x = 100 << 8; sys.actors[0].fixed_y = 100 << 8;
    GbPlayer player = {0}; player.x = 100; player.y = 100;
    GbInteractionEvent event = {0}; GbInput input = { KEY_A, KEY_A };
    int updated = gb_actor_system_update_physical_npc_at(&sys, &player, &input, &event, 1);
    assert(updated == 1); assert(event.type == GB_INTERACTION_DIALOGUE);
    assert(event.actor_index == 0); assert(event.state == 2); assert(event.dial == 7);
    event.type = GB_INTERACTION_NONE; input.pressed = 0; input.held = KEY_A;
    gb_actor_system_update_physical_npc_at(&sys, &player, &input, &event, 1);
    assert(event.type == GB_INTERACTION_NONE);
    return 0;
}
''')
            exe = td/'npc'
            proc = subprocess.run([
                'cc','-std=c11','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',
                '-I',str(td),'-I',str(ROOT/'reconstruction/include'),
                str(ROOT/'reconstruction/source/game/actors.c'),
                str(ROOT/'reconstruction/source/engine/collision.c'),
                str(harness),'-Wl,--gc-sections','-o',str(exe)
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

if __name__ == '__main__':
    unittest.main()
