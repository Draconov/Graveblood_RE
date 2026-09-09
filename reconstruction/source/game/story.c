#include <graveblood/story.h>

#define GB_STORY_COLLECTION_SELECTOR_COUNT 6

static const s8 gb_collection_script_selector[GB_STORY_COLLECTION_SELECTOR_COUNT] = {
    4, -1, -1, 5, 6, 0
};

static void gb_story_clear_dialogue(GbStoryRuntime* story)
{
    story->dialogue.active = 0;
    story->dialogue.context = GB_DIALOGUE_CONTEXT_NORMAL;
    story->dialogue.actor_index = 0;
    story->dialogue.script_index = -1;
    story->dialogue.step = -1;
    story->dialogue.awaiting_advance = 0;
}

static void gb_story_clear_social(GbStoryRuntime* story)
{
    story->social.state = GB_SOCIAL_INACTIVE;
    story->social.profile_selector = 0;
    story->social.page_base = 0;
    story->social.selected_quadrant = 0;
    story->social.action_index = 0;
    story->social.topic_index = 0;
    story->social.topic_count = 0;
    story->social.followup_armed = 0;
    story->social.response_text = 0;
}

void gb_story_init(GbStoryRuntime* story)
{
    story->state.collection_progress = 0;
    story->state.primary_message_stream = -1;
    story->state.auxiliary_message_streams[0] = -1;
    story->state.auxiliary_message_streams[1] = -1;
    story->state.auxiliary_message_streams[2] = -1;
    story->state.story_stage = 0;
    story->state.monster_render_enabled = 0;
    story->state.final_effect_pending = 0;
    story->state.consumed_story_overlays = 0;
    story->state.social_score_mirror = 0;

    for(u8 profile = 0; profile < GB_SOCIAL_PROFILE_COUNT; ++profile)
    {
        story->state.social_profiles[profile].score = 0;
        for(u8 topic = 0; topic < 9; ++topic)
        {
            story->state.social_profiles[profile].topic_class[topic] =
                gb_social_profiles[profile].topic_ratings[topic];
        }
    }

    gb_story_clear_dialogue(story);
    gb_story_clear_social(story);
    story->generic_record_action_pending = 0;
    story->generic_record_action_argument = 0;
    story->pending_sfx = -1;
}

void gb_story_on_level_load(GbStoryRuntime* story, GbActorSystem* actors)
{
    for(u8 i = 0; i < actors->count; ++i)
    {
        GbActor* actor = &actors->actors[i];
        actor->story_visible = 1;
        actor->consumed = 0;
        if(actor->story_overlay_index < GB_ACTOR_STORY_NONE &&
           actor->story_overlay_index < 16 &&
           (story->state.consumed_story_overlays & (u16)(1u << actor->story_overlay_index)))
        {
            actor->story_visible = 0;
            actor->consumed = 1;
            actor->active = 0;
        }
    }
}

static void gb_story_insert_auxiliary(GbStoryRuntime* story, s16 value)
{
    if(value < -1 || value > 127)
    {
        return;
    }
    for(u8 i = 0; i < 3; ++i)
    {
        if(story->state.auxiliary_message_streams[i] < 0)
        {
            story->state.auxiliary_message_streams[i] = (s8)value;
            return;
        }
    }
}

static void gb_story_consume_actor(GbStoryRuntime* story, GbActorSystem* actors, u8 actor_index)
{
    if(actor_index >= actors->count)
    {
        return;
    }
    GbActor* actor = &actors->actors[actor_index];
    actor->consumed = 1;
    actor->story_visible = 0;
    actor->active = 0;
    if(actor->story_overlay_index < 16)
    {
        story->state.consumed_story_overlays |= (u16)(1u << actor->story_overlay_index);
    }
}

static const GbDialogueRecord* gb_story_dialogue_record_mutable(const GbStoryRuntime* story)
{
    if(! story->dialogue.active || story->dialogue.script_index < 0 ||
       story->dialogue.script_index >= GB_DIALOGUE_SCRIPT_COUNT)
    {
        return 0;
    }
    const GbDialogueScript* script = &gb_dialogue_scripts[story->dialogue.script_index];
    if(story->dialogue.step < 0 || story->dialogue.step >= (s16)script->count)
    {
        return 0;
    }
    return &script->records[story->dialogue.step];
}

const GbDialogueRecord* gb_story_dialogue_record(const GbStoryRuntime* story)
{
    return gb_story_dialogue_record_mutable(story);
}

static void gb_story_process_dialogue(GbStoryRuntime* story, GbActorSystem* actors)
{
    while(story->dialogue.active)
    {
        const GbDialogueRecord* record = gb_story_dialogue_record_mutable(story);
        if(! record)
        {
            gb_story_clear_dialogue(story);
            return;
        }
        if(record->opcode == 0)
        {
            story->dialogue.awaiting_advance = 1;
            return;
        }

        story->dialogue.awaiting_advance = 0;
        if(story->dialogue.context == GB_DIALOGUE_CONTEXT_NORMAL)
        {
            if(record->opcode == -1)
            {
                if(story->dialogue.actor_index < actors->count)
                {
                    actors->actors[story->dialogue.actor_index].dialogue_step = record->argument;
                }
                gb_story_clear_dialogue(story);
                return;
            }
            if(record->opcode == -2)
            {
                story->state.primary_message_stream = (s8)record->argument;
                ++story->dialogue.step;
                continue;
            }
            if(record->opcode == -3)
            {
                gb_story_insert_auxiliary(story, record->argument);
                ++story->dialogue.step;
                continue;
            }
            if(record->opcode == -4)
            {
                story->state.story_stage = record->argument;
                ++story->dialogue.step;
                continue;
            }
            if(record->opcode == -5)
            {
                story->generic_record_action_pending = 1;
                story->generic_record_action_argument = record->argument;
                gb_story_clear_dialogue(story);
                return;
            }
            gb_story_clear_dialogue(story);
            return;
        }

        if(record->opcode == -1)
        {
            if(story->dialogue.actor_index < actors->count)
            {
                actors->actors[story->dialogue.actor_index].dialogue_step = record->argument;
            }
            story->pending_sfx = 7;
            ++story->state.collection_progress;
            gb_story_consume_actor(story, actors, story->dialogue.actor_index);
            gb_story_clear_dialogue(story);
            return;
        }
        if(record->opcode == -2)
        {
            story->state.primary_message_stream = (s8)record->argument;
            story->pending_sfx = 7;
            ++story->state.collection_progress;
            gb_story_consume_actor(story, actors, story->dialogue.actor_index);
            gb_story_clear_dialogue(story);
            return;
        }
        if(record->opcode == -3)
        {
            gb_story_insert_auxiliary(story, record->argument);
            story->pending_sfx = 7;
            ++story->state.collection_progress;
            gb_story_consume_actor(story, actors, story->dialogue.actor_index);
            gb_story_clear_dialogue(story);
            return;
        }
        if(record->opcode == -4)
        {
            story->state.monster_render_enabled = 1;
            ++story->dialogue.step;
            continue;
        }
        if(record->opcode == -5)
        {
            story->pending_sfx = 13;
            story->state.final_effect_pending = 1;
            ++story->state.collection_progress;
            gb_story_consume_actor(story, actors, story->dialogue.actor_index);
            gb_story_clear_dialogue(story);
            return;
        }
        gb_story_clear_dialogue(story);
        return;
    }
}

static int gb_story_start_dialogue(GbStoryRuntime* story, GbActorSystem* actors,
                                   u8 actor_index, s16 script_index,
                                   GbDialogueContext context, s16 step)
{
    if(actor_index >= actors->count || script_index < 0 || script_index >= GB_DIALOGUE_SCRIPT_COUNT)
    {
        return 0;
    }
    const GbDialogueScript* script = &gb_dialogue_scripts[script_index];
    if(step < 0 || step >= (s16)script->count)
    {
        return 0;
    }
    story->dialogue.active = 1;
    story->dialogue.context = context;
    story->dialogue.actor_index = actor_index;
    story->dialogue.script_index = script_index;
    story->dialogue.step = step;
    story->dialogue.awaiting_advance = 0;
    gb_story_process_dialogue(story, actors);
    return 1;
}

static void gb_story_start_social(GbStoryRuntime* story, u8 selector)
{
    if(selector >= GB_SOCIAL_PROFILE_COUNT)
    {
        return;
    }
    gb_story_clear_social(story);
    story->social.state = GB_SOCIAL_ROOT_SELECTOR;
    story->social.profile_selector = selector;
    story->social.page_base = 0;
}

void gb_story_handle_interaction(GbStoryRuntime* story, GbActorSystem* actors,
                                 const GbInteractionEvent* event)
{
    if(! event || gb_story_ui_active(story) || event->actor_index >= actors->count)
    {
        return;
    }
    if(event->type == GB_INTERACTION_DIALOGUE)
    {
        const GbActor* actor = &actors->actors[event->actor_index];
        const s16 step = (s16)(actor->dialogue_step + 1);
        if(gb_story_start_dialogue(story, actors, event->actor_index, event->dial,
                                   GB_DIALOGUE_CONTEXT_NORMAL, step))
        {
            story->pending_sfx = 3;
        }
        return;
    }
    if(event->type == GB_INTERACTION_COLLECTION)
    {
        if(story->state.collection_progress >= GB_STORY_COLLECTION_SELECTOR_COUNT)
        {
            return;
        }
        const s8 selector = gb_collection_script_selector[story->state.collection_progress];
        if(selector < 0)
        {
            story->pending_sfx = 3;
            ++story->state.collection_progress;
            gb_story_consume_actor(story, actors, event->actor_index);
            return;
        }
        if(gb_story_start_dialogue(story, actors, event->actor_index, selector,
                                   GB_DIALOGUE_CONTEXT_STATE4_PICKUP, 0))
        {
            story->pending_sfx = 3;
        }
        return;
    }
    if(event->type == GB_INTERACTION_SOCIAL)
    {
        gb_story_start_social(story, event->dial);
    }
}

int gb_story_take_pending_sfx(GbStoryRuntime* story)
{
    const int pending = story->pending_sfx;
    story->pending_sfx = -1;
    return pending;
}

static const GbMessageRecord* gb_story_message_for_stream(const GbStoryRuntime* story, s8 stream)
{
    if(stream < 0)
    {
        return 0;
    }
    for(u8 i = 0; i < GB_MESSAGE_RECORD_COUNT; ++i)
    {
        const GbMessageRecord* message = &gb_message_records[i];
        if(message->stream_id == (u8)stream && message->story_stage == story->state.story_stage)
        {
            return message;
        }
    }
    return 0;
}

const GbMessageRecord* gb_story_message_primary(const GbStoryRuntime* story)
{
    return gb_story_message_for_stream(story, story->state.primary_message_stream);
}

const GbMessageRecord* gb_story_message_auxiliary(const GbStoryRuntime* story, u8 slot)
{
    if(slot >= 3)
    {
        return 0;
    }
    return gb_story_message_for_stream(story, story->state.auxiliary_message_streams[slot]);
}

const char* gb_story_lookup_social_response(u8 quadrant, u8 topic_index,
                                            s8 profile_value_class, u8 variant)
{
    if((quadrant != 0 && quadrant != 3) || topic_index >= 9 ||
       profile_value_class < 0 || profile_value_class > 4)
    {
        return 0;
    }
    if(profile_value_class == 2)
    {
        return "I don't really care";
    }
    for(u16 i = 0; i < GB_SOCIAL_RESPONSE_COUNT; ++i)
    {
        const GbSocialResponseData* response = &gb_social_responses[i];
        if(response->quadrant == quadrant && response->topic_index == topic_index &&
           response->profile_value_class == (u8)profile_value_class &&
           response->variant == variant)
        {
            return response->text;
        }
    }
    return 0;
}

static int gb_story_direction_quadrant(const GbInput* input)
{
    if(input->pressed & KEY_UP)
    {
        return 0;
    }
    if(input->pressed & KEY_RIGHT)
    {
        return 1;
    }
    if(input->pressed & KEY_DOWN)
    {
        return 2;
    }
    if(input->pressed & KEY_LEFT)
    {
        return 3;
    }
    return -1;
}

static void gb_story_social_dispatch(GbStoryRuntime* story)
{
    const u8 selector = story->social.profile_selector;
    const u8 quadrant = story->social.selected_quadrant;
    const u8 topic = story->social.topic_index;
    if(selector >= GB_SOCIAL_PROFILE_COUNT || topic >= 9)
    {
        gb_story_clear_social(story);
        return;
    }

    GbSocialProfile* profile = &story->state.social_profiles[selector];
    const s8 topic_class = profile->topic_class[topic];
    story->state.social_score_mirror = (s16)(10 * profile->score);
    story->social.response_text = 0;
    story->social.followup_armed = 0;

    if(quadrant == 0)
    {
        story->social.response_text = gb_story_lookup_social_response(0, topic, topic_class, 0);
        profile->score = (s16)(profile->score + 2 * (topic_class - 2));
    }
    else if(quadrant == 3)
    {
        story->social.response_text = gb_story_lookup_social_response(3, topic, topic_class, 0);
    }
    else
    {
        story->social.followup_armed = 1;
    }
    story->social.state = GB_SOCIAL_RESPONSE;
}

static void gb_story_update_social(GbStoryRuntime* story, const GbInput* input)
{
    if(story->social.state == GB_SOCIAL_ROOT_SELECTOR)
    {
        if(input->pressed & KEY_B)
        {
            gb_story_clear_social(story);
            return;
        }
        const int quadrant = gb_story_direction_quadrant(input);
        if(quadrant < 0)
        {
            return;
        }
        const u8 action_index = (u8)(story->social.page_base + quadrant);
        if(action_index >= GB_SOCIAL_ACTION_COUNT)
        {
            gb_story_clear_social(story);
            return;
        }
        const GbSocialActionData* action = &gb_social_actions[action_index];
        story->social.selected_quadrant = (u8)quadrant;
        story->social.action_index = action_index;
        if(action->node_type == 0)
        {
            if(action->child_base >= GB_SOCIAL_ACTION_COUNT)
            {
                gb_story_clear_social(story);
                return;
            }
            story->social.page_base = action->child_base;
            return;
        }
        story->social.topic_index = 0;
        story->social.topic_count = action->field_28;
        if(story->social.topic_count > 0)
        {
            if(story->social.topic_count > 9)
            {
                story->social.topic_count = 9;
            }
            story->social.state = GB_SOCIAL_SECONDARY;
            return;
        }
        gb_story_social_dispatch(story);
        return;
    }

    if(story->social.state == GB_SOCIAL_SECONDARY)
    {
        if(input->pressed & KEY_B)
        {
            story->social.state = GB_SOCIAL_ROOT_SELECTOR;
            story->social.topic_index = 0;
            story->social.topic_count = 0;
            return;
        }
        if((input->pressed & KEY_UP) && story->social.topic_index > 0)
        {
            --story->social.topic_index;
            story->pending_sfx = 4;
            return;
        }
        if((input->pressed & KEY_DOWN) && story->social.topic_index + 1 < story->social.topic_count)
        {
            ++story->social.topic_index;
            story->pending_sfx = 4;
            return;
        }
        if(input->pressed & KEY_A)
        {
            gb_story_social_dispatch(story);
        }
        return;
    }

    if(story->social.state == GB_SOCIAL_RESPONSE && (input->pressed & KEY_A))
    {
        if(story->social.followup_armed && story->social.profile_selector < GB_SOCIAL_PROFILE_COUNT)
        {
            const s16 target = (s16)(10 * story->state.social_profiles[story->social.profile_selector].score);
            if(story->state.social_score_mirror < target)
            {
                ++story->state.social_score_mirror;
            }
            else if(story->state.social_score_mirror > target)
            {
                --story->state.social_score_mirror;
            }
        }
        story->social.state = GB_SOCIAL_TEARDOWN;
        gb_story_clear_social(story);
    }
}

void gb_story_update(GbStoryRuntime* story, GbActorSystem* actors, const GbInput* input)
{
    if(story->dialogue.active)
    {
        if(story->dialogue.awaiting_advance && (input->pressed & KEY_A))
        {
            story->dialogue.awaiting_advance = 0;
            ++story->dialogue.step;
            gb_story_process_dialogue(story, actors);
        }
        return;
    }
    if(story->social.state != GB_SOCIAL_INACTIVE)
    {
        gb_story_update_social(story, input);
    }
}

typedef struct {
    s16 x;
    s16 y;
    s16 target_y;
} GbStoryLevel10Gate;

static const GbStoryLevel10Gate gb_story_level10_gates[4] = {
    { 808, 384, 360 },
    { 824, 384, 360 },
    { 808, 352, 410 },
    { 824, 352, 410 },
};

static int gb_story_level10_gate_grid_contact(const GbPlayer* player,
                                              const GbStoryLevel10Gate* gate)
{
    const int px = ((int)player->x - 8) >> 3;
    const int py = ((int)player->y - 24) >> 3;
    const int ax = ((int)gate->x - 8) >> 3;
    const int ay = ((int)gate->y - 16) >> 3;
    return (px == ax || px == ax + 1) && (py == ay || py == ay + 1);
}

static int gb_story_level10_gate_portal_rect(const GbPlayer* player,
                                             const GbStoryLevel10Gate* gate)
{
    return player->x >= gate->x && player->x < gate->x + 16 &&
           player->y >= gate->y && player->y < gate->y + 16;
}

GbStoryGateResult gb_story_try_level10_gate(const GbStoryRuntime* story,
                                               const GbLevelAssets* level,
                                               GbPlayer* player, const GbInput* input)
{
    if(! story || ! level || ! player || ! input || level->level_id != 10 ||
       ! (input->pressed & KEY_A))
    {
        return GB_STORY_GATE_NONE;
    }

    for(u8 i = 0; i < 4; ++i)
    {
        const GbStoryLevel10Gate* gate = &gb_story_level10_gates[i];
        const int grid_contact = gb_story_level10_gate_grid_contact(player, gate);
        const int portal_rect = gb_story_level10_gate_portal_rect(player, gate);
        if(! grid_contact && ! portal_rect)
        {
            continue;
        }

        /* These turn-4/5 records are never generic portTo=8 portals. Before
           the rusty-key threshold they are inert; afterwards only the exact
           recovered 2x2 contact grid dispatches the vertical traversal. */
        if(story->state.collection_progress > 3 && grid_contact)
        {
            player->y = gate->target_y;
            return GB_STORY_GATE_TRAVERSED;
        }
        return GB_STORY_GATE_BLOCKED;
    }

    return GB_STORY_GATE_NONE;
}

int gb_story_ui_active(const GbStoryRuntime* story)
{
    return story->dialogue.active || story->social.state != GB_SOCIAL_INACTIVE;
}

const char* gb_story_social_profile_name(const GbStoryRuntime* story)
{
    if(story->social.state == GB_SOCIAL_INACTIVE || story->social.profile_selector >= GB_SOCIAL_PROFILE_COUNT)
    {
        return 0;
    }
    return gb_social_profiles[story->social.profile_selector].name;
}

const char* gb_story_social_response(const GbStoryRuntime* story)
{
    return story->social.response_text;
}
