#ifndef GRAVEBLOOD_STORY_H
#define GRAVEBLOOD_STORY_H

#include <graveblood/actors.h>

typedef enum {
    GB_DIALOGUE_CONTEXT_NORMAL = 0,
    GB_DIALOGUE_CONTEXT_STATE4_PICKUP = 1,
} GbDialogueContext;

typedef enum {
    GB_STORY_GATE_NONE = 0,
    GB_STORY_GATE_BLOCKED = 1,
    GB_STORY_GATE_TRAVERSED = 2,
} GbStoryGateResult;

typedef enum {
    GB_SOCIAL_INACTIVE = 0,
    GB_SOCIAL_ROOT_SELECTOR = 1,
    GB_SOCIAL_SECONDARY = 2,
    GB_SOCIAL_POST_DELAY = 3,
    GB_SOCIAL_RESPONSE = 4,
    GB_SOCIAL_TEARDOWN = 5,
} GbSocialState;

typedef struct {
    s16 score;
    s8 topic_class[9];
} GbSocialProfile;

typedef struct {
    u8 collection_progress;
    s8 primary_message_stream;
    s8 auxiliary_message_streams[3];
    s16 story_stage;
    u8 monster_render_enabled;
    u8 final_effect_pending;
    u16 consumed_story_overlays;
    s16 social_score_mirror;
    GbSocialProfile social_profiles[GB_SOCIAL_PROFILE_COUNT];
} GbStoryState;

typedef struct {
    u8 active;
    GbDialogueContext context;
    u8 actor_index;
    s16 script_index;
    s16 step;
    u8 awaiting_advance;
} GbDialogueRuntime;

typedef struct {
    GbSocialState state;
    u8 profile_selector;
    u8 page_base;
    u8 selected_quadrant;
    u8 action_index;
    u8 topic_index;
    u8 topic_count;
    u8 followup_armed;
    u16 post_countdown;
    const char* response_text;
} GbSocialRuntime;

#define GB_STORY_SFX_QUEUE_CAPACITY 8

typedef struct {
    GbStoryState state;
    GbDialogueRuntime dialogue;
    GbSocialRuntime social;
    u8 generic_record_action_pending;
    s16 generic_record_action_argument;
    s8 pending_sfx[GB_STORY_SFX_QUEUE_CAPACITY];
    u8 pending_sfx_head;
    u8 pending_sfx_count;
    unsigned long long response_rng_state;
} GbStoryRuntime;

void gb_story_init(GbStoryRuntime* story);
void gb_story_on_level_load(GbStoryRuntime* story, GbActorSystem* actors);
void gb_story_handle_interaction(GbStoryRuntime* story, GbActorSystem* actors,
                                 const GbInteractionEvent* event);
void gb_story_update(GbStoryRuntime* story, GbActorSystem* actors, const GbInput* input);

GbStoryGateResult gb_story_try_level10_gate(const GbStoryRuntime* story,
                                               const GbLevelAssets* level,
                                               GbPlayer* player, const GbInput* input);
GbStoryGateResult gb_story_try_level10_gate_physical_index(const GbStoryRuntime* story,
                                                            const GbLevelAssets* level,
                                                            GbPlayer* player, const GbInput* input,
                                                            u8 physical_index);
GbStoryGateResult gb_story_try_level9_treetype20_action(const GbLevelAssets* level,
                                                        GbPlayer* player,
                                                        const GbInput* input);

int gb_story_ui_active(const GbStoryRuntime* story);
const GbDialogueRecord* gb_story_dialogue_record(const GbStoryRuntime* story);
const GbMessageRecord* gb_story_message_primary(const GbStoryRuntime* story);
const GbMessageRecord* gb_story_message_auxiliary(const GbStoryRuntime* story, u8 slot);
const char* gb_story_social_profile_name(const GbStoryRuntime* story);
const char* gb_story_social_response(const GbStoryRuntime* story);
int gb_story_take_pending_sfx(GbStoryRuntime* story);
const char* gb_story_lookup_social_response(u8 quadrant, u8 topic_index,
                                            s8 profile_value_class, u8 variant);

#endif
