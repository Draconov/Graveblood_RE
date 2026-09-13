#include <graveblood/actors.h>
#include <graveblood/collision.h>

static const s16 gb_leaf_x_offsets[6] = { 350, 250, 170, 0, 340, 290 };
static const s16 gb_leaf_y_offsets[6] = { 40, 60, 80, 30, 20, 50 };

static s32 gb_leaf_fixed_to_pixel(s32 value)
{
    if(value >= 0)
    {
        return value / GB_LEAF_FIXED_ONE;
    }
    return -((-value + GB_LEAF_FIXED_ONE - 1) / GB_LEAF_FIXED_ONE);
}

static void gb_actor_clear_leaf_particles(GbActorSystem* system)
{
    for(int i = 0; i < GB_LEAF_PARTICLE_CAPACITY; ++i)
    {
        system->leaf_particles[i].active = 0;
    }
}

void gb_actor_system_init(GbActorSystem* system)
{
    system->count = 0;
    system->level = 0;
    system->leaf_emitter_cooldown = 12;
    system->leaf_emitter_cycle = 0;
    system->npc_special_timer = 15;
    system->pending_sfx = -1;
    gb_actor_clear_leaf_particles(system);
}

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
    actor->request_x_fixed = 0;
    actor->request_y_fixed = 0;
    /* NPC constructor 0x08003A3E..0x08003A44 uses a 16x32 collision body. */
    actor->collision_width_fixed = 0x1000;
    actor->collision_height_fixed = 0x2000;
    actor->collision_status = 0;
    actor->frame = 1;
    actor->frame_countdown = 0;
    actor->visual_legs_color = descriptor->legs_color;
    actor->animation_frame_count = (u8)descriptor->num;
    actor->movement_code = 8;
    actor->waypoint_index = 0;
    actor->facing_right = descriptor->turn != 0;
    actor->active = 1;
    actor->story_overlay_index = overlay_index;
    actor->dialogue_step = -1;
    actor->consumed = 0;
    actor->story_visible = 1;
    actor->special_mover_latched = descriptor->port_to != 0;
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
    system->level = level;
    gb_actor_clear_leaf_particles(system);
    if(! level || level->level_id >= 11)
    {
        return;
    }

    /* load_level_record_resources submits the level-gated story-overlay list
       to the object manager before LevelRecord+0x38 physical actors.  Keep the
       same insertion order because update traversal and OAM allocation both
       consume the object vector in registration order. */
    for(u8 i = 0; i < GB_ACTOR_STORY_DESCRIPTOR_COUNT; ++i)
    {
        const GbStoryActorDescriptor* story = &gb_story_actor_descriptors[i];
        if(story->actor.level == level->level_id)
        {
            gb_actor_append(system, &story->actor, story->overlay_index);
        }
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
    /* NPC_update state 3 compares actor positions as 8-pixel cells (>>11),
       then queues +/- actor+0xF0 (0x100 fixed8) into +0x18/+0x1C. */
    const s32 cell_x = actor->fixed_x >> 11;
    const s32 cell_y = actor->fixed_y >> 11;

    if(target->x > cell_x)
    {
        actor->request_x_fixed = GB_ACTOR_ROUTE_SPEED_FIXED;
    }
    else if(target->x < cell_x)
    {
        actor->request_x_fixed = -GB_ACTOR_ROUTE_SPEED_FIXED;
    }
    else
    {
        actor->request_x_fixed = 0;
    }

    if(target->y > cell_y)
    {
        actor->request_y_fixed = GB_ACTOR_ROUTE_SPEED_FIXED;
    }
    else if(target->y < cell_y)
    {
        actor->request_y_fixed = -GB_ACTOR_ROUTE_SPEED_FIXED;
    }
    else
    {
        actor->request_y_fixed = 0;
    }

    if(actor->request_y_fixed < 0)
    {
        actor->visual_legs_color = (u8)(descriptor->legs_color + 16);
        actor->animation_frame_count = 6;
        actor->movement_code = actor->request_x_fixed < 0 ? 5 :
                               actor->request_x_fixed > 0 ? 3 : 4;
    }
    else if(actor->request_y_fixed > 0 || actor->request_x_fixed != 0)
    {
        actor->visual_legs_color = (u8)(descriptor->legs_color + 8);
        actor->animation_frame_count = 6;
        if(actor->request_y_fixed > 0)
        {
            actor->movement_code = actor->request_x_fixed < 0 ? 7 :
                                   actor->request_x_fixed > 0 ? 1 : 0;
        }
        else
        {
            actor->movement_code = actor->request_x_fixed < 0 ? 6 : 2;
        }
    }
    else
    {
        actor->visual_legs_color = descriptor->legs_color;
        actor->animation_frame_count = 8;
        actor->movement_code = 8;
    }

    if(actor->request_x_fixed > 0)
    {
        actor->facing_right = 1;
    }
    else if(actor->request_x_fixed < 0)
    {
        actor->facing_right = 0;
    }

    if(cell_x == target->x && cell_y == target->y)
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

    /* The ROM subtracts 0x1000 fixed units (16 px), then shifts both actor
       and Player coordinates by 11.  With 24.8 storage that is an 8-pixel
       interaction grid, not a literal 4/5-pixel rectangle. */
    const s32 actor_left_cell = (actor->fixed_x - 0x1000) >> 11;
    const s32 actor_top_cell = (actor->fixed_y - 0x1000) >> 11;
    const s32 player_x_cell = ((s32)player->x * GB_ACTOR_FIXED_ONE) >> 11;
    const s32 player_y_cell = ((s32)player->y * GB_ACTOR_FIXED_ONE) >> 11;
    return player_x_cell >= actor_left_cell && player_x_cell < actor_left_cell + size &&
           player_y_cell >= actor_top_cell && player_y_cell < actor_top_cell + size;
}

static int gb_actor_special_mover_near_player(const GbActor* actor, const GbPlayer* player)
{
    const s32 actor_x = actor->fixed_x >> GB_ACTOR_FIXED_SHIFT;
    const s32 actor_y = actor->fixed_y >> GB_ACTOR_FIXED_SHIFT;
    const s32 player_x = (s32)player->x + 8;
    const s32 player_y = (s32)player->y + 16;
    const s32 dx = actor_x - player_x;
    const s32 dy = actor_y - player_y;
    return dx * dx + dy * dy < 1024;
}

static void gb_actor_update_npc_special(GbActorSystem* system, GbActor* actor, const GbPlayer* player)
{
    const GbActorDescriptor* descriptor = actor->descriptor;
    if(descriptor->legs_color == 40)
    {
        actor->fixed_x -= 150;
        return;
    }
    if(descriptor->legs_color != 112)
    {
        return;
    }

    if(! actor->special_mover_latched)
    {
        if(system->npc_special_timer <= 0)
        {
            system->npc_special_timer = 5;
            if(gb_actor_special_mover_near_player(actor, player))
            {
                actor->special_mover_latched = 1;
                if(system->pending_sfx < 0)
                {
                    system->pending_sfx = 9;
                }
            }
        }
        --system->npc_special_timer;
    }

    if(actor->special_mover_latched)
    {
        actor->fixed_x += 600 * (s32)descriptor->turn - 300;
        actor->fixed_y -= 250;
    }
}

int gb_actor_system_take_pending_sfx(GbActorSystem* system)
{
    const int result = system->pending_sfx;
    system->pending_sfx = -1;
    return result;
}

static GbLeafParticle* gb_actor_allocate_leaf_particle(GbActorSystem* system)
{
    for(int i = 0; i < GB_LEAF_PARTICLE_CAPACITY; ++i)
    {
        if(! system->leaf_particles[i].active)
        {
            return &system->leaf_particles[i];
        }
    }
    return 0;
}

static int gb_actor_system_has_leaves(const GbActorSystem* system)
{
    for(u8 i = 0; i < system->count; ++i)
    {
        const GbActor* actor = &system->actors[i];
        if(actor->active && actor->descriptor && actor->descriptor->actor_class == GB_ACTOR_LEAVES)
        {
            return 1;
        }
    }
    return 0;
}

void gb_actor_system_update_environment(GbActorSystem* system, s16 camera_x, s16 camera_y)
{
    for(int i = 0; i < GB_LEAF_PARTICLE_CAPACITY; ++i)
    {
        GbLeafParticle* particle = &system->leaf_particles[i];
        if(! particle->active)
        {
            continue;
        }
        particle->fixed_x += particle->velocity_x;
        particle->fixed_y += particle->velocity_y;
        if(particle->velocity_y > 0x400)
        {
            particle->velocity_y = 0x400;
        }
        const s32 x = gb_leaf_fixed_to_pixel(particle->fixed_x);
        const s32 y = gb_leaf_fixed_to_pixel(particle->fixed_y);
        if(x < (s32)camera_x - 30 || y > (s32)camera_y + 180)
        {
            particle->active = 0;
        }
    }

    if(! gb_actor_system_has_leaves(system))
    {
        return;
    }
    if(system->leaf_emitter_cooldown > 0)
    {
        --system->leaf_emitter_cooldown;
        return;
    }

    if(system->leaf_emitter_cycle > 4)
    {
        system->leaf_emitter_cycle = 0;
    }
    else
    {
        ++system->leaf_emitter_cycle;
    }

    if(camera_x > 2000)
    {
        GbLeafParticle* particle = gb_actor_allocate_leaf_particle(system);
        if(particle)
        {
            const int index = system->leaf_emitter_cycle;
            particle->fixed_x = ((s32)camera_x + 260 + gb_leaf_x_offsets[index]) * GB_LEAF_FIXED_ONE;
            particle->fixed_y = ((s32)camera_y - 80 + gb_leaf_y_offsets[index]) * GB_LEAF_FIXED_ONE;
            particle->velocity_x = -150;
            particle->velocity_y = 150;
            particle->frame = 0;
            particle->frame_countdown = 10;
            particle->active = 1;
        }
    }
    system->leaf_emitter_cooldown = 23;
}

int gb_actor_npc_should_draw(const GbActor* actor)
{
    return actor && actor->active && actor->descriptor &&
           actor->descriptor->actor_class == GB_ACTOR_NPC &&
           actor->visual_legs_color != 1;
}

u8 gb_actor_npc_frame_for_draw(GbActor* actor)
{
    if(! gb_actor_npc_should_draw(actor))
    {
        return 0;
    }

    u8 count = actor->animation_frame_count;
    if(count == 0)
    {
        count = (u8)actor->descriptor->num;
    }
    if(count < 1)
    {
        count = 1;
    }
    if(count > GB_ACTOR_MAX_FRAMES)
    {
        count = GB_ACTOR_MAX_FRAMES;
    }
    if(actor->frame < 1 || actor->frame > count)
    {
        actor->frame = 1;
    }

    if(actor->frame_countdown > 0)
    {
        --actor->frame_countdown;
    }
    else
    {
        actor->frame = actor->frame < count ? (u8)(actor->frame + 1) : 1;
        actor->frame_countdown = (u8)(5 * (8 / count));
    }
    return actor->frame;
}

int gb_actor_grass_draw_state(const GbActor* actor, s16 player_y, GbGrassDrawState* out)
{
    if(! actor || ! actor->active || ! actor->descriptor || ! out ||
       actor->descriptor->actor_class != GB_ACTOR_GRASS || actor->descriptor->legs_color == 1)
    {
        return 0;
    }
    out->hflip = (u8)(actor->descriptor->turn & 1);
    out->priority = (u8)(gb_actor_pixel_y(actor) > player_y ? 1 : 2);
    return 1;
}

u8 gb_leaf_particle_frame_for_draw(GbLeafParticle* particle)
{
    if(particle->frame_countdown > 0)
    {
        --particle->frame_countdown;
    }
    else
    {
        particle->frame = (u8)(particle->frame > 2 ? 0 : particle->frame + 1);
        particle->frame_countdown = 10;
    }
    return particle->frame;
}

s16 gb_leaf_particle_pixel_x(const GbLeafParticle* particle)
{
    return (s16)gb_leaf_fixed_to_pixel(particle->fixed_x);
}

s16 gb_leaf_particle_pixel_y(const GbLeafParticle* particle)
{
    return (s16)gb_leaf_fixed_to_pixel(particle->fixed_y);
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
        if(actor->descriptor->actor_class == GB_ACTOR_NPC)
        {
            /* NPC_update 0x0800298C calls the shared 0x08004670 solver before
               state dispatch, consuming the request queued on the prior frame. */
            gb_collision_apply_fixed_motion(system->level,
                                            &actor->fixed_x, &actor->fixed_y,
                                            &actor->request_x_fixed, &actor->request_y_fixed,
                                            actor->collision_width_fixed,
                                            actor->collision_height_fixed,
                                            &actor->collision_status);
            gb_actor_update_npc_special(system, actor, player);
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

void gb_actor_system_update_overlays(GbActorSystem* system, const GbPlayer* player,
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
        if(! actor->active || ! actor->descriptor ||
           actor->story_overlay_index == GB_ACTOR_STORY_NONE)
        {
            continue;
        }
        if(actor->descriptor->actor_class == GB_ACTOR_NPC)
        {
            gb_collision_apply_fixed_motion(system->level,
                                            &actor->fixed_x, &actor->fixed_y,
                                            &actor->request_x_fixed, &actor->request_y_fixed,
                                            actor->collision_width_fixed,
                                            actor->collision_height_fixed,
                                            &actor->collision_status);
            gb_actor_update_npc_special(system, actor, player);
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
        if(! actor->active || ! actor->descriptor ||
           actor->story_overlay_index == GB_ACTOR_STORY_NONE ||
           ! gb_actor_player_in_interaction(actor, player))
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

static GbActor* gb_actor_system_physical_actor_at(GbActorSystem* system, u8 physical_index)
{
    if(! system || ! system->level || system->level->level_id >= 11)
    {
        return 0;
    }

    const u8 level_id = system->level->level_id;
    const u8 player_index = gb_player_physical_indices[level_id];
    if(physical_index == player_index)
    {
        return 0;
    }

    const GbActorLevelIndexSpan span = gb_actor_level_spans[level_id];
    const u16 nonplayer_index = physical_index < player_index ?
                                physical_index : (u16)(physical_index - 1);
    if(nonplayer_index >= span.count)
    {
        return 0;
    }

    u8 physical_start = 0;
    while(physical_start < system->count &&
          system->actors[physical_start].story_overlay_index != GB_ACTOR_STORY_NONE)
    {
        ++physical_start;
    }
    const u16 actor_index = (u16)physical_start + nonplayer_index;
    if(actor_index >= system->count)
    {
        return 0;
    }
    return &system->actors[actor_index];
}

int gb_actor_system_update_physical_npc_at(GbActorSystem* system, const GbPlayer* player,
                                           u8 physical_index)
{
    GbActor* actor = gb_actor_system_physical_actor_at(system, physical_index);
    if(! actor || ! actor->active || ! actor->descriptor ||
       actor->descriptor->actor_class != GB_ACTOR_NPC)
    {
        return 0;
    }

    gb_collision_apply_fixed_motion(system->level,
                                    &actor->fixed_x, &actor->fixed_y,
                                    &actor->request_x_fixed, &actor->request_y_fixed,
                                    actor->collision_width_fixed,
                                    actor->collision_height_fixed,
                                    &actor->collision_status);
    gb_actor_update_npc_special(system, actor, player);
    if(actor->descriptor->state == 3)
    {
        gb_actor_update_route(actor);
    }
    return 1;
}

void gb_actor_system_update_physical_npcs(GbActorSystem* system, const GbPlayer* player)
{
    if(! system || ! system->level || system->level->level_id >= 11)
    {
        return;
    }
    const GbActorLevelIndexSpan span = gb_actor_level_spans[system->level->level_id];
    for(u16 physical_index = 0; physical_index <= span.count; ++physical_index)
    {
        gb_actor_system_update_physical_npc_at(system, player, (u8)physical_index);
    }
}

