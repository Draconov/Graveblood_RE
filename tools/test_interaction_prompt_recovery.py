#!/usr/bin/env python3
from __future__ import annotations
import os, struct, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ROM=Path(os.environ.get('GRAVEBLOOD_ROM','/mnt/data/graveblood_resume/Graveblood 0.0.1.1.5.2 demo.gba'))
GBA_H=r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16; typedef uint32_t u32; typedef int32_t s32;
#define KEY_A 1u
#define KEY_B 2u
#define KEY_SELECT 4u
#define KEY_START 8u
#define KEY_RIGHT 0x10u
#define KEY_LEFT 0x20u
#define KEY_UP 0x40u
#define KEY_DOWN 0x80u
#define KEY_R 0x100u
#define KEY_L 0x200u
#endif
'''

class InteractionPromptRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.rom=ROM.read_bytes()

    def test_rom_prompt_draw_uses_contact_flag_tile_4e_and_exact_bob_table(self):
        def h(addr): return struct.unpack_from('<H',self.rom,addr-0x08000000)[0]
        self.assertEqual((h(0x08006ADA),h(0x08006ADC),h(0x08006ADE)),(0x23E0,0x005B,0x5CE3))
        self.assertEqual(h(0x08006B1C),0x224E)
        self.assertEqual(h(0x08006B18),0x3014) # x + 20
        self.assertEqual(h(0x08006B14),0x3910) # y - 16 after table offset
        table=struct.unpack_from('<32i',self.rom,0x08019820-0x08000000)
        self.assertEqual(table,(0,0,0,0,0,0,1,1,1,2,2,3,4,4,4,4,5,5,5,5,5,4,4,4,4,3,3,2,2,1,1,1))

    def test_npc_proximity_marks_prompt_without_fresh_a(self):
        harness=r'''
#include <assert.h>
#include <graveblood/actors.h>
const GbActorLevelIndexSpan gb_actor_level_spans[11]={[1]={0,1}};
const u8 gb_player_physical_indices[11]={0};
const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS]={{{0}}};
int main(void){
 GbActorDescriptor d={0}; d.actor_class=GB_ACTOR_NPC; d.state=2; d.dial=1;
 GbLevelAssets level={0}; level.level_id=1;
 GbActorSystem sys={0}; sys.level=&level; sys.count=1; sys.actors[0].active=1; sys.actors[0].descriptor=&d; sys.actors[0].story_overlay_index=GB_ACTOR_STORY_NONE; sys.actors[0].fixed_x=100<<8; sys.actors[0].fixed_y=100<<8;
 GbPlayer p={0}; p.x=100; p.y=100; p.x_fixed=100<<8; p.y_fixed=100<<8;
 GbInteractionEvent e={0}; GbInput in={0};
 assert(gb_actor_system_update_physical_npc_at(&sys,&p,&in,&e,1)==1);
 assert(p.interaction_available==1); assert(e.type==GB_INTERACTION_NONE);
 return 0;
}
'''
        self._compile_run(harness,['reconstruction/source/game/actors.c','reconstruction/source/engine/collision.c'])

    def test_generic_portal_contact_marks_prompt_but_only_fresh_a_activates(self):
        harness=r'''
#include <assert.h>
#include <graveblood/portal.h>
void gb_audio_play_sfx(u8 id){ (void)id; }
int main(void){
 GbPortal portal={10,20,16,16,3,0,0}; GbLevelAssets level={0}; level.portals=&portal; level.portal_count=1;
 GbPlayer p={0}; p.x=12; p.y=22; GbInput in={0};
 assert(gb_portal_try_activate(&level,&p,&in)==-1); assert(p.interaction_available==1);
 p.interaction_available=0; in.pressed=KEY_A;
 assert(gb_portal_try_activate(&level,&p,&in)==3); assert(p.interaction_available==1);
 return 0;
}
'''
        self._compile_run(harness,['reconstruction/source/engine/portal.c'])

    def test_special_fgtile_contacts_mark_prompt_before_a(self):
        harness=r'''
#include <assert.h>
#include <graveblood/story.h>
int main(void){
 GbStoryRuntime story; gb_story_init(&story); GbLevelAssets level={0}; GbPlayer p={0}; GbInput in={0};
 level.level_id=9; gb_player_spawn(&p,504,464);
 assert(gb_story_try_level9_treetype20_action(&level,&p,&in)==GB_STORY_GATE_NONE); assert(p.interaction_available==1); assert(p.bicycle_mode==0);
 p.interaction_available=0; level.level_id=10; gb_player_spawn(&p,808,392);
 assert(gb_story_try_level10_gate_physical_index(&story,&level,&p,&in,13)==GB_STORY_GATE_NONE); assert(p.interaction_available==1);
 return 0;
}
'''
        self._compile_run(harness,['reconstruction/source/game/story.c','reconstruction/source/game/player.c','reconstruction/source/engine/collision.c','reconstruction/data/story_data.c'])

    def test_video_submits_prompt_before_player_body_and_frame_resets_latch(self):
        video=(ROOT/'reconstruction/source/engine/video.c').read_text()
        game=(ROOT/'reconstruction/source/game/graveblood.c').read_text()
        self.assertIn('gb_player_prompt_bob[player->prompt_bob_phase & 31u]',video)
        self.assertIn('GB_PLAYER_INTERACTION_LOGICAL_TILE 0x4E',video)
        self.assertIn('(s16)(player->x - camera_x + 20)',video)
        prompt=video.index('gb_video_draw_interaction_prompt(')
        body=video.index('gb_video_draw_player_oam(',prompt)
        self.assertLess(prompt,body)
        draw=game.index('gb_video_draw_story_ui(&story);')
        clear=game.index('player.interaction_available = 0;',draw)
        overlay=game.index('gb_actor_system_update_overlays(',clear)
        self.assertLess(draw,clear); self.assertLess(clear,overlay)

    def _compile_run(self,harness,sources):
        with tempfile.TemporaryDirectory() as td0:
            td=Path(td0); (td/'gba.h').write_text(GBA_H); (td/'h.c').write_text(harness); exe=td/'h'
            cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-I',str(td),'-I',str(ROOT/'reconstruction/include')]+[str(ROOT/s) for s in sources]+[str(td/'h.c'),'-Wl,--gc-sections','-o',str(exe)]
            p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True); self.assertEqual(p.returncode,0,p.stderr)
            r=subprocess.run([str(exe)],cwd=ROOT,text=True,capture_output=True); self.assertEqual(r.returncode,0,r.stderr+r.stdout)

if __name__=='__main__': unittest.main()
