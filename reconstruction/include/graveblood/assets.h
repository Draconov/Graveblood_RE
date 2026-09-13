#ifndef GRAVEBLOOD_ASSETS_H
#define GRAVEBLOOD_ASSETS_H

#include <gba.h>

typedef struct {
    s16 x;
    s16 y;
    u8 width;
    u8 height;
    u16 target_level;
    u16 num;
    u8 physical_index;
} GbPortal;

typedef enum {
    GB_ACTOR_NPC = 0,
    GB_ACTOR_GRASS = 1,
    GB_ACTOR_FGTILE = 2,
    GB_ACTOR_LEAVES = 3,
} GbActorClass;

typedef struct {
    s16 x;
    s16 y;
    s16 width;
    s16 height;
    u16 rom_order;
    u16 port_to;
    u16 num;
    u8 actor_class;
    u8 subtype;
    u8 legs_color;
    u8 state;
    u8 route;
    u8 dial;
    u8 turn;
    u8 level;
    u8 setglobal;
    u8 visual_index;
} GbActorDescriptor;

typedef struct {
    GbActorDescriptor actor;
    u8 overlay_index;
} GbStoryActorDescriptor;

typedef struct {
    u16 offset;
    u16 count;
} GbActorLevelIndexSpan;

typedef struct {
    s16 x;
    s16 y;
} GbRoutePoint;

typedef struct {
    u8 legs_color;
    u8 subtype;
} GbActorVisualSpec;

typedef struct {
    const char* speaker;
    const char* text;
    s16 opcode;
    s16 argument;
} GbDialogueRecord;

typedef struct {
    const GbDialogueRecord* records;
    u16 count;
} GbDialogueScript;

typedef struct {
    u8 stream_id;
    s8 story_stage;
    const char* title;
    const char* sender;
    const char* body;
} GbMessageRecord;

typedef struct {
    const char* name;
    s8 topic_ratings[9];
} GbSocialProfileData;

typedef struct {
    const char* label;
    u8 node_type;
    u8 field_24;
    u8 field_28;
    u8 child_base;
} GbSocialActionData;

typedef struct {
    u8 quadrant;
    u8 topic_index;
    u8 slot;
    u8 profile_value_class;
    u8 variant;
    const char* text;
} GbSocialResponseData;

typedef struct {
    u8 pixel_width;
    u16 rows[8];
} GbFontGlyph;

typedef enum {
    GB_AUDIO_ROLE_MUSIC = 0,
    GB_AUDIO_ROLE_SFX = 1,
} GbAudioRole;

typedef struct {
    const s8* data;
    u32 byte_length;
    u8 role;
} GbAudioSample;

typedef struct {
    u8 level_id;
    u8 graphics_variant;
    u16 world_width_tiles;
    u16 world_height_tiles;
    u16 fixed_width_tiles;
    u16 fixed_height_tiles;
    s16 spawn_x;
    s16 spawn_y;
    u8 player_idle_selector;
    u16 bg_tile_halfwords;
    u16 translation_count;
    const u16* bg_palette;
    const u16* bg_tiles;
    const u16* translation;
    const u16* layer_a;
    const u16* layer_b;
    const u16* fixed_map;
    const u16* collision;
    const u16* bg0_ui_tiles;
    const GbPortal* portals;
    u8 portal_count;
} GbLevelAssets;

extern const GbLevelAssets gb_level00_assets;
extern const GbLevelAssets gb_level00_v1_assets;
extern const GbLevelAssets gb_level00_v2_assets;
extern const GbLevelAssets gb_level01_assets;
extern const GbLevelAssets gb_level02_assets;
extern const GbLevelAssets gb_level03_assets;
extern const GbLevelAssets gb_level04_assets;
extern const GbLevelAssets gb_level05_assets;
extern const GbLevelAssets gb_level06_assets;
extern const GbLevelAssets gb_level07_assets;
extern const GbLevelAssets gb_level08_assets;
extern const GbLevelAssets gb_level09_assets;
extern const GbLevelAssets gb_level10_assets;

const GbLevelAssets* gb_level_assets(int level_id, int graphics_variant);
const GbLevelAssets* gb_level_default_assets(int level_id);

enum {
    GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT = 241,
    GB_ACTOR_LEVEL_REFERENCE_COUNT = 290,
    GB_ACTOR_STORY_DESCRIPTOR_COUNT = 16,
    GB_ACTOR_ROUTE_COUNT = 5,
    GB_ACTOR_ROUTE_POINTS = 6,
    GB_ACTOR_VISUAL_COUNT = 34,
    GB_ACTOR_OBJ_PALETTE_COUNT = 91,
    GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT = 200,
    GB_ACTOR_OBJ_HIGH_PALETTE_COUNT = 32,
    GB_ACTOR_MAX_FRAMES = 8,
    GB_ACTOR_FRAME_HALFWORDS = 256,
    GB_GRASS_OBJ_HALFWORDS = 128,
    GB_LEAF_FRAME_COUNT = 4,
    GB_LEAF_FRAME_HALFWORDS = 32,
    GB_DIALOGUE_SCRIPT_COUNT = 7,
    GB_DIALOGUE_RECORD_COUNT = 58,
    GB_MESSAGE_RECORD_COUNT = 6,
    GB_SOCIAL_PROFILE_COUNT = 2,
    GB_SOCIAL_ACTION_COUNT = 20,
    GB_SOCIAL_SUBJECT_TOPIC_COUNT = 9,
    GB_SOCIAL_ASK_TOPIC_COUNT = 5,
    GB_SOCIAL_CRITICIZE_TOPIC_COUNT = 9,
    GB_SOCIAL_RESPONSE_COUNT = 216,
    GB_FONT_GLYPH_COUNT = 127,
    GB_MONSTER_SPRITE_COUNT = 5,
    GB_MONSTER_SPRITE_HALFWORDS = 128,
    GB_LEVEL_STATIC_SPRITE_COUNT = 4,
    GB_LEVEL_STATIC_SPRITE_HALFWORDS = 128,
    GB_BG0_UI_TILE_COUNT = 87,
    GB_TITLE_MAP_WIDTH = 30,
    GB_TITLE_MAP_HEIGHT = 20,
    GB_TITLE_MAP_CELLS = 600,
    GB_TITLE_ANIMATION_STATES = 4,
    GB_TITLE_ANIM_A_HALFWORDS = 1536,
    GB_TITLE_ANIM_B_HALFWORDS = 768,
    GB_TITLE_PROMPT_LENGTH = 14,
    GB_TITLE_BG_PALETTE_COUNT = 223,
    GB_TITLE_OBJ_TILE_HALFWORDS = 0x8000 / 2,
    GB_TITLE_OBJ_PALETTE_COUNT = 91,
    GB_TITLE_OBJ_HIGH_PALETTE_COUNT = 32,
    GB_PDA_PAGE_COUNT = 4,
    GB_PDA_MAP_WIDTH = 30,
    GB_PDA_MAP_HEIGHT = 20,
    GB_PDA_MAP_CELLS = 600,
    GB_PDA_FRIEND_COUNT = 6,
    GB_PDA_TEXT_COLUMNS = 29,
    GB_PDA_TEXT_ROWS = 5,
    GB_PDA_TEXT_TILE_COUNT = 145,
    GB_WARDROBE_CHOICE_COUNT = 7,
    GB_WARDROBE_BG_PAGE_HALFWORDS = 4096,
    GB_WARDROBE_PREVIEW_HALFWORDS = 256,
    GB_AUDIO_SAMPLE_COUNT = 14,
    GB_AUDIO_MUSIC_SAMPLE_COUNT = 3,
    GB_ENDING_ARG0_COPY1_BYTES = 96000,
    GB_ENDING_ARG0_COPY2_BYTES = 16000,
    GB_ENDING_VRAM_BYTES = 0x18000,
    GB_ENDING_OBJ_VRAM_OFFSET = 0x10000,
};

extern const GbActorDescriptor gb_actor_descriptors[GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT];
extern const u16 gb_level_actor_indices[GB_ACTOR_LEVEL_REFERENCE_COUNT];
extern const GbActorLevelIndexSpan gb_actor_level_spans[11];
extern const u8 gb_player_physical_indices[11];
extern const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT];
extern const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS];
extern const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT];
extern const u16 gb_actor_obj_palette[GB_ACTOR_OBJ_PALETTE_COUNT];
extern const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT];
extern const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT];
extern const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_MAX_FRAMES * GB_ACTOR_FRAME_HALFWORDS];
extern const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS];
extern const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS];
extern const GbDialogueScript gb_dialogue_scripts[GB_DIALOGUE_SCRIPT_COUNT];
extern const GbMessageRecord gb_message_records[GB_MESSAGE_RECORD_COUNT];
extern const GbSocialProfileData gb_social_profiles[GB_SOCIAL_PROFILE_COUNT];
extern const GbSocialActionData gb_social_actions[GB_SOCIAL_ACTION_COUNT];
extern const char* const gb_social_subject_topics[GB_SOCIAL_SUBJECT_TOPIC_COUNT];
extern const char* const gb_social_ask_topics[GB_SOCIAL_ASK_TOPIC_COUNT];
extern const char* const gb_social_criticize_topics[GB_SOCIAL_CRITICIZE_TOPIC_COUNT];
extern const GbSocialResponseData gb_social_responses[GB_SOCIAL_RESPONSE_COUNT];
extern const GbFontGlyph gb_font_glyphs[GB_FONT_GLYPH_COUNT];
extern const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS];
extern const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS];
extern const u16 gb_title_bg_tiles[0xD800 / 2];
extern const u16 gb_title_bg_palette[GB_TITLE_BG_PALETTE_COUNT];
extern const u16 gb_title_obj_tiles[GB_TITLE_OBJ_TILE_HALFWORDS];
extern const u16 gb_title_obj_palette[GB_TITLE_OBJ_PALETTE_COUNT];
extern const u16 gb_title_obj_high_palette[GB_TITLE_OBJ_HIGH_PALETTE_COUNT];
extern const u16 gb_title_underlay_tile;
extern const u16 gb_title_map[GB_TITLE_MAP_CELLS];
extern const u16 gb_title_anim_a[GB_TITLE_ANIMATION_STATES][GB_TITLE_ANIM_A_HALFWORDS];
extern const u16 gb_title_anim_b[GB_TITLE_ANIMATION_STATES][GB_TITLE_ANIM_B_HALFWORDS];
extern const u16 gb_title_prompt_tiles[GB_TITLE_PROMPT_LENGTH];
extern const u16 gb_title_blank_tiles[GB_TITLE_PROMPT_LENGTH];
extern const u16 gb_pda_page_maps[GB_PDA_PAGE_COUNT][GB_PDA_MAP_CELLS];
extern const char* const gb_pda_friend_names[GB_PDA_FRIEND_COUNT];
extern const u16 gb_pda_text_tile_ids[GB_PDA_TEXT_TILE_COUNT];
extern const u8 gb_wardrobe_bg_page_indices[GB_WARDROBE_CHOICE_COUNT];
extern const u8 gb_wardrobe_obj_banks[GB_WARDROBE_CHOICE_COUNT];
extern const char* const gb_wardrobe_labels[GB_WARDROBE_CHOICE_COUNT];
extern const u16 gb_wardrobe_bg_pages[GB_WARDROBE_CHOICE_COUNT][GB_WARDROBE_BG_PAGE_HALFWORDS];
extern const u16 gb_wardrobe_preview_tiles[GB_WARDROBE_CHOICE_COUNT][GB_WARDROBE_PREVIEW_HALFWORDS];
extern const GbAudioSample gb_audio_samples[GB_AUDIO_SAMPLE_COUNT];
extern const u8 gb_ending_arg0_copy1[GB_ENDING_ARG0_COPY1_BYTES];
extern const u8 gb_ending_arg0_copy2[GB_ENDING_ARG0_COPY2_BYTES];

enum {
    GB_PLAYER_FRAME_COUNT = 24,
    GB_PLAYER_FRAME_HALFWORDS = 256,
    GB_PLAYER_BICYCLE_FRAME_COUNT = 6,
    GB_PLAYER_BICYCLE_SPRITE_COUNT = 5,
    GB_PLAYER_BICYCLE_SPRITE_HALFWORDS = 128,
    GB_PLAYER_BICYCLE_FRAME_HALFWORDS = GB_PLAYER_BICYCLE_SPRITE_COUNT * GB_PLAYER_BICYCLE_SPRITE_HALFWORDS,
};

extern const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * GB_PLAYER_FRAME_HALFWORDS];
extern const u16 gb_player_bicycle_obj_frames[GB_PLAYER_BICYCLE_FRAME_COUNT * GB_PLAYER_BICYCLE_FRAME_HALFWORDS];

#endif
