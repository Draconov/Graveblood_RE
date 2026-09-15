#!/usr/bin/env python3
import subprocess, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
GBA_H = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16; typedef uint32_t u32; typedef int32_t s32;
#define KEY_A (1u<<0)
#define KEY_B (1u<<1)
#define KEY_SELECT (1u<<2)
#define KEY_START (1u<<3)
#define KEY_RIGHT (1u<<4)
#define KEY_LEFT (1u<<5)
#define KEY_UP (1u<<6)
#define KEY_DOWN (1u<<7)
#define KEY_R (1u<<8)
#define KEY_L (1u<<9)
#endif
'''
HARNESS = r'''
#include <assert.h>
#include <graveblood/story.h>
int main(void) {
    GbStoryRuntime s; GbActorSystem a = {0}; GbInput in = {0};
    gb_story_init(&s);
    /* observable depth lifecycle */
    s.social.state = GB_SOCIAL_ROOT_SELECTOR;
    s.social.profile_selector = 0;
    s.social.page_base = 4;
    s.social.selected_quadrant = 1; /* Ask about */
    in.pressed = KEY_A; gb_story_update(&s,&a,&in);
    assert(s.social.state == GB_SOCIAL_SECONDARY);
    assert(s.social.depth == 1);
    /* secondary cursor is mechanical 0..8, independent of visible count 5 */
    in.pressed = KEY_DOWN;
    for(int i=0;i<8;i++) gb_story_update(&s,&a,&in);
    assert(s.social.topic_index == 8);
    gb_story_update(&s,&a,&in);
    assert(s.social.topic_index == 8);
    /* B returns to root and clears depth. */
    in.pressed = KEY_B; gb_story_update(&s,&a,&in);
    assert(s.social.state == GB_SOCIAL_ROOT_SELECTOR && s.social.depth == 0);

    /* malformed leaf with depth zero cannot commit TALK. */
    s.social.state=GB_SOCIAL_SECONDARY; s.social.page_base=4; s.social.depth=0;
    s.social.selected_quadrant=0; s.social.topic_index=0;
    in.pressed=KEY_A; gb_story_update(&s,&a,&in);
    assert(s.social.state == GB_SOCIAL_SECONDARY);

    /* valid leaf commit enters invisible 150-frame delay. */
    s.social.depth=1; in.pressed=KEY_A; gb_story_update(&s,&a,&in);
    assert(s.social.state == GB_SOCIAL_POST_DELAY);
    assert(s.social.post_countdown == 150);
    assert(gb_story_ui_active(&s) == 0);
    assert(gb_story_player_controls_locked(&s) == 1);
    assert(gb_story_world_traversal_continues(&s) == 1);

    in.pressed=0;
    for(int i=0;i<150;i++) gb_story_update(&s,&a,&in);
    assert(s.social.post_countdown == 0);
    gb_story_update(&s,&a,&in); /* dispatcher */
    assert(s.social.state == GB_SOCIAL_RESPONSE);
    assert(s.social.followup_armed == 1); /* SUBJECT also reaches +0x382 setter */
    assert(gb_story_ui_active(&s) == 1);
    assert(gb_story_player_controls_locked(&s) == 1);
    assert(gb_story_world_traversal_continues(&s) == 1);

    /* fresh A consumes response handshake and clears interaction. */
    in.pressed=KEY_A; gb_story_update(&s,&a,&in);
    assert(s.social.state == GB_SOCIAL_INACTIVE);
    assert(gb_story_player_controls_locked(&s) == 0);
    return 0;
}
'''
class SocialSchedulerRecoveryTests(unittest.TestCase):
    def test_story_runtime_contract(self):
        with tempfile.TemporaryDirectory() as td0:
            td=Path(td0); (td/'gba.h').write_text(GBA_H); (td/'h.c').write_text(HARNESS)
            exe=td/'h'
            cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-I',str(td),'-I',str(ROOT/'reconstruction/include'),
                 str(ROOT/'reconstruction/source/game/story.c'),str(ROOT/'reconstruction/data/story_data.c'),str(td/'h.c'),'-Wl,--gc-sections','-o',str(exe)]
            p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            r=subprocess.run([str(exe)],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr+r.stdout)
    def test_gameplay_object_update_traversal_is_unconditional_in_reference(self):
        import os
        rom=Path(os.environ['GRAVEBLOOD_ROM']).read_bytes()
        # Active GameplayScene tail: OAM begin, draw traversal, OAM end, update traversal.
        import struct
        def h(addr): return struct.unpack_from('<H',rom,addr-0x08000000)[0]
        self.assertEqual(h(0x08004BCE),0x0020) # mov r0,r4 immediately before update call
        self.assertEqual(h(0x08004BD0),0xF7FC) # first half of unconditional BL 0x08001428
        self.assertEqual(h(0x08004BD2),0xFC2A)

    def test_game_loop_separates_player_lock_from_world_traversal(self):
        game=(ROOT/'reconstruction/source/game/graveblood.c').read_text()
        self.assertIn('int player_locked = gb_story_player_controls_locked(&story);', game)
        self.assertIn('&actors, &player, player_locked ? 0 : &input, &interaction);', game)
        self.assertIn('if(player_locked)', game)
        self.assertNotIn('if(gb_story_ui_active(&story))\n        {', game)

if __name__=='__main__': unittest.main()
