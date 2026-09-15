#!/usr/bin/env python3
from __future__ import annotations
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
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
HARNESS=r'''
#include <assert.h>
#include <graveblood/actors.h>
const GbActorLevelIndexSpan gb_actor_level_spans[11]={[1]={0,1}};
const u8 gb_player_physical_indices[11]={[1]=0};
const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS]={{{0}}};
static void setup(GbActorSystem* s,GbActorDescriptor* d,u8 state,u8 overlay,s16 ax,s16 px){
 *s=(GbActorSystem){0}; *d=(GbActorDescriptor){0}; d->actor_class=GB_ACTOR_NPC; d->state=state;
 static GbLevelAssets level; level=(GbLevelAssets){0}; level.level_id=1; s->level=&level; s->count=1; s->actors[0].active=1; s->actors[0].descriptor=d; s->actors[0].story_overlay_index=overlay; s->actors[0].fixed_x=ax<<8; s->actors[0].fixed_y=100<<8; s->actors[0].facing_right=0; (void)px;
}
int main(void){
 GbActorSystem s; GbActorDescriptor d; GbPlayer p={0}; GbInteractionEvent e={0}; GbInput in={0};
 p.x=100; p.y=100; p.x_fixed=100<<8; p.y_fixed=100<<8;
 /* physical social left of Vika: proximity advertises but does not turn */
 setup(&s,&d,1,GB_ACTOR_STORY_NONE,96,100); gb_actor_system_update_physical_npc_at(&s,&p,&in,&e,1); assert(s.actors[0].facing_right==0); assert(p.interaction_available==1);
 in.pressed=KEY_A; gb_actor_system_update_physical_npc_at(&s,&p,&in,&e,1); assert(e.type==GB_INTERACTION_SOCIAL); assert(s.actors[0].facing_right==1);
 /* physical dialogue right/equal faces left */
 e.type=GB_INTERACTION_NONE; in.pressed=KEY_A; setup(&s,&d,2,GB_ACTOR_STORY_NONE,104,100); s.actors[0].facing_right=1; gb_actor_system_update_physical_npc_at(&s,&p,&in,&e,1); assert(e.type==GB_INTERACTION_DIALOGUE); assert(s.actors[0].facing_right==0);
 /* state4 pickup never rotates */
 e.type=GB_INTERACTION_NONE; setup(&s,&d,4,GB_ACTOR_STORY_NONE,96,100); s.actors[0].facing_right=0; gb_actor_system_update_physical_npc_at(&s,&p,&in,&e,1); assert(e.type==GB_INTERACTION_COLLECTION); assert(s.actors[0].facing_right==0);
 /* overlay social follows same fresh-A facing rule */
 e.type=GB_INTERACTION_NONE; setup(&s,&d,1,0,96,100); s.actors[0].facing_right=0; gb_actor_system_update_overlays(&s,&p,&in,&e); assert(e.type==GB_INTERACTION_SOCIAL); assert(s.actors[0].facing_right==1);
 return 0;
}
'''
class NpcInteractionFacingRecoveryTests(unittest.TestCase):
 def test_fresh_a_turns_social_and_dialogue_npcs_only(self):
  with tempfile.TemporaryDirectory() as td0:
   td=Path(td0); (td/'gba.h').write_text(GBA_H); (td/'h.c').write_text(HARNESS); exe=td/'h'
   cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-I',str(td),'-I',str(ROOT/'reconstruction/include'),str(ROOT/'reconstruction/source/game/actors.c'),str(ROOT/'reconstruction/source/engine/collision.c'),str(td/'h.c'),'-Wl,--gc-sections','-o',str(exe)]
   p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True); self.assertEqual(p.returncode,0,p.stderr)
   r=subprocess.run([str(exe)],cwd=ROOT,text=True,capture_output=True); self.assertEqual(r.returncode,0,r.stderr+r.stdout)
if __name__=='__main__': unittest.main()
