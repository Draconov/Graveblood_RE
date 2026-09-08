#include <graveblood/actors.h>

static s32 gb_actor_to_fixed(s16 value)
{
    return (s32)value * GB_ACTOR_FIXED_ONE;
}

s16 gb_actor_pixel_x(const GbActor* actor)
{
    return (s16)(actor->fixed_x / GB_ACTOR_FIXED_ONE);
}

s16 gb_actor_pixel_y(const GbActor* actor)
{
    return (s16)(actor->fixed_y / GB_ACTOR_FIXED_ONE);
}

static void gb_actor_init(GbActor* actor, const GbActorDescriptor* descriptor, u8 overlay_index)
{
    actor->descriptor = descriptor;
    actor->fixed_x = gb_actor_to_fixed(descriptor->x);
    actor->fixed_y = gb_actor_to_fixed(descriptor->y);
    actor->frame = 1;
    actor->waypoint_index = 0;
    actor->facing_right = 0;
    actor->active = 1;
    actor->story_overlay_index = overlay_index;
}

static void gb_actor_append(GbActorSystem* system, const GbActorDescriptor* descriptor, u8 overlay_index)
{
    if(system->count >= GB_ACTOR_CAPACITY)
    {
        return;
    }
    gb_actor_init(&system->actors[system->count], descriptor, overlay_index);
    ++system->count;
}

void gb_actor_system_load(GbActorSystem* system, const GbLevelAssets* level)
{
    system->count = 0;
    if(! level || level->level_id >= 11)
    {
        return;
    }

    const GbActorLevelIndexSpan span = gb_actor_level_spans[level->level_id];
    for(u16 i = 0; i < span.count; ++i)
    {
        const u16 descriptor_index = gb_level_actor_indices[span.offset + i];
        if(descriptor_index < GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT)
        {
            gb_actor_append(system, &gb_actor_descriptors[descriptor_index], GB_ACTOR_STORY_NONE);
        }
    }

    for(u8 i = 0; i < GB_ACTOR_STORY_DESCRIPTOR_COUNT; ++i)
    {
        const GbStoryActorDescriptor* story = &gb_story_actor_descriptors[i];
        if(story->actor.level == level->level_id)
        {
            gb_actor_append(system, &story->actor, story->overlay_index);
        }
    }
}

static s32 gb_actor_step_axis(s32 current, s32 target)
{
    if(current < target)
    {
        current += GB_ACTOR_ROUTE_SPEED_FIXED;
        return current > target ? target : current;
    }
    if(current > target)
    {
        current -= GB_ACTOR_ROUTE_SPEED_FIXED;
        return current < target ? target : current;
    }
    return current;
}

static void gb_actor_update_route(GbActor* actor)
{
    const GbActorDescriptor* descriptor = actor->descriptor;
    if(descriptor->route >= GB_ACTOR_ROUTE_COUNT)
    {
        return;
    }

    if(actor->waypoint_index >= GB_ACTOR_ROUTE_POINTS)
    {
        actor->waypoint_index = 0;
    }

    const GbRoutePoint* target = &gb_actor_routes[descriptor->route][actor->waypoint_index];
    const s32 target_x = (s32)target->x * GB_ACTOR_FIXED_ONE;
    const s32 target_y = (s32)target->y * GB_ACTOR_FIXED_ONE;
    const s32 old_x = actor->fixed_x;

    actor->fixed_x = gb_actor_step_axis(actor->fixed_x, target_x);
    actor->fixed_y = gb_actor_step_axis(actor->fixed_y, target_y);
    if(actor->fixed_x > old_x)
    {
        actor->facing_right = 1;
    }
    else if(actor->fixed_x < old_x)
    {
        actor->facing_right = 0;
    }

    if(actor->fixed_x == target_x && actor->fixed_y == target_y)
    {
        actor->waypoint_index = (u8)((actor->waypoint_index + 1) % GB_ACTOR_ROUTE_POINTS);
    }
}

static int gb_actor_interaction_size(const GbActorDescriptor* descriptor)
{
    if(descriptor->state == 1)
    {
        return 5;
    }
    if(descriptor->state == 2)
    {
        return descriptor->legs_color == 1 ? 4 : 5;
    }
    if(descriptor->state == 4)
    {
        return 4;
    }
    return 0;
}

static GbInteractionType gb_actor_interaction_type(u8 state)
{
    if(state == 1)
    {
        return GB_INTERACTION_SOCIAL;
    }
    if(state == 2)
    {
        return GB_INTERACTION_DIALOGUE;
    }
    if(state == 4)
    {
        return GB_INTERACTION_COLLECTION;
    }
    return GB_INTERACTION_NONE;
}

static int gb_actor_player_in_interaction(const GbActor* actor, const GbPlayer* player)
{
    const int size = gb_actor_interaction_size(actor->descriptor);
    if(size == 0)
    {
        return 0;
    }

    const s16 actor_x = gb_actor_pixel_x(actor);
    const s16 actor_y = gb_actor_pixel_y(actor);
    const s16 left = (s16)(actor_x - 2);
    const s16 top = (s16)(actor_y - 2);
    return player->x >= left && player->x < left + size &&
           player->y >= top && player->y < top + size;
}

void gb_actor_system_update(GbActorSystem* system, const GbPlayer* player,
                            const GbInput* input, GbInteractionEvent* event)
{
    event->type = GB_INTERACTION_NONE;
    event->actor_index = 0;
    event->state = 0;
    event->dial = 0;
    event->actor_x = 0;
    event->actor_y = 0;

    for(u8 i = 0; i < system->count; ++i)
    {
        GbActor* actor = &system->actors[i];
        if(! actor->active || ! actor->descriptor)
        {
            continue;
        }
        if(actor->descriptor->state == 3)
        {
            gb_actor_update_route(actor);
        }
    }

    if(! (input->pressed & KEY_A))
    {
        return;
    }

    for(u8 i = 0; i < system->count; ++i)
    {
        const GbActor* actor = &system->actors[i];
        if(! actor->active || ! actor->descriptor || ! gb_actor_player_in_interaction(actor, player))
        {
            continue;
        }
        const GbInteractionType type = gb_actor_interaction_type(actor->descriptor->state);
        if(type == GB_INTERACTION_NONE)
        {
            continue;
        }
        event->type = type;
        event->actor_index = i;
        event->state = actor->descriptor->state;
        event->dial = actor->descriptor->dial;
        event->actor_x = gb_actor_pixel_x(actor);
        event->actor_y = gb_actor_pixel_y(actor);
        return;
    }
}
