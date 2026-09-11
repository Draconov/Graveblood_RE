#ifndef GRAVEBLOOD_ACTORS_H
#define GRAVEBLOOD_ACTORS_H

#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/input.h>

enum {
    GB_ACTOR_CAPACITY = 72,
    GB_ACTOR_FIXED_SHIFT = 8,
    GB_ACTOR_FIXED_ONE = 1 << GB_ACTOR_FIXED_SHIFT,
    GB_ACTOR_ROUTE_SPEED_FIXED = 0x100,
    GB_ACTOR_STORY_NONE = 0xFF,
    GB_LEAF_PARTICLE_CAPACITY = 96,
    GB_LEAF_FIXED_ONE = 256,
};

typedef enum {
    GB_INTERACTION_NONE = 0,
    GB_INTERACTION_SOCIAL = 1,
    GB_INTERACTION_DIALOGUE = 2,
    GB_INTERACTION_COLLECTION = 3,
} GbInteractionType;

typedef struct {
    GbInteractionType type;
    u8 actor_index;
    u8 state;
    u8 dial;
    s16 actor_x;
    s16 actor_y;
} GbInteractionEvent;

typedef struct {
    s32 fixed_x;
    s32 fixed_y;
    s16 velocity_x;
    s16 velocity_y;
    u8 frame;
    u8 frame_countdown;
    u8 active;
} GbLeafParticle;

typedef struct {
    u8 hflip;
    u8 priority;
} GbGrassDrawState;

typedef struct {
    const GbActorDescriptor* descriptor;
    s32 fixed_x;
    s32 fixed_y;
    s32 request_x_fixed;
    s32 request_y_fixed;
    s32 collision_width_fixed;
    s32 collision_height_fixed;
    u16 collision_status;
    u8 frame;
    u8 frame_countdown;
    u8 visual_legs_color;
    u8 animation_frame_count;
    u8 movement_code;
    u8 waypoint_index;
    u8 facing_right;
    u8 active;
    u8 story_overlay_index;
    s16 dialogue_step;
    u8 consumed;
    u8 story_visible;
    u8 special_mover_latched;
} GbActor;

typedef struct {
    GbActor actors[GB_ACTOR_CAPACITY];
    const GbLevelAssets* level;
    GbLeafParticle leaf_particles[GB_LEAF_PARTICLE_CAPACITY];
    u8 count;
    u8 leaf_emitter_cooldown;
    u8 leaf_emitter_cycle;
    s32 npc_special_timer;
    s8 pending_sfx;
} GbActorSystem;

void gb_actor_system_init(GbActorSystem* system);
void gb_actor_system_load(GbActorSystem* system, const GbLevelAssets* level);
void gb_actor_system_update(GbActorSystem* system, const GbPlayer* player,
                            const GbInput* input, GbInteractionEvent* event);
void gb_actor_system_update_environment(GbActorSystem* system, s16 camera_x, s16 camera_y);
int gb_actor_npc_should_draw(const GbActor* actor);
u8 gb_actor_npc_frame_for_draw(GbActor* actor);
int gb_actor_grass_draw_state(const GbActor* actor, s16 player_y, GbGrassDrawState* out);
u8 gb_leaf_particle_frame_for_draw(GbLeafParticle* particle);
s16 gb_leaf_particle_pixel_x(const GbLeafParticle* particle);
s16 gb_leaf_particle_pixel_y(const GbLeafParticle* particle);
s16 gb_actor_pixel_x(const GbActor* actor);
s16 gb_actor_pixel_y(const GbActor* actor);
int gb_actor_system_take_pending_sfx(GbActorSystem* system);

#endif
