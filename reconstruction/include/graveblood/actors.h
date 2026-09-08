#ifndef GRAVEBLOOD_ACTORS_H
#define GRAVEBLOOD_ACTORS_H

#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/input.h>

enum {
    GB_ACTOR_CAPACITY = 72,
    GB_ACTOR_FIXED_SHIFT = 11,
    GB_ACTOR_FIXED_ONE = 1 << GB_ACTOR_FIXED_SHIFT,
    GB_ACTOR_ROUTE_SPEED_FIXED = 0x100,
    GB_ACTOR_STORY_NONE = 0xFF,
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
    const GbActorDescriptor* descriptor;
    s32 fixed_x;
    s32 fixed_y;
    u8 frame;
    u8 waypoint_index;
    u8 facing_right;
    u8 active;
    u8 story_overlay_index;
} GbActor;

typedef struct {
    GbActor actors[GB_ACTOR_CAPACITY];
    u8 count;
} GbActorSystem;

void gb_actor_system_load(GbActorSystem* system, const GbLevelAssets* level);
void gb_actor_system_update(GbActorSystem* system, const GbPlayer* player,
                            const GbInput* input, GbInteractionEvent* event);
s16 gb_actor_pixel_x(const GbActor* actor);
s16 gb_actor_pixel_y(const GbActor* actor);

#endif
