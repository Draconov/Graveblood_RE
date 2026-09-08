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
    u8 level_id;
    u8 graphics_variant;
    u16 world_width_tiles;
    u16 world_height_tiles;
    u16 fixed_width_tiles;
    u16 fixed_height_tiles;
    s16 spawn_x;
    s16 spawn_y;
    u16 bg_tile_halfwords;
    u16 translation_count;
    const u16* bg_palette;
    const u16* bg_tiles;
    const u16* translation;
    const u16* layer_a;
    const u16* layer_b;
    const u16* fixed_map;
    const u16* collision;
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
    GB_ACTOR_VISUAL_COUNT = 32,
    GB_ACTOR_FRAME_HALFWORDS = 256,
};

extern const GbActorDescriptor gb_actor_descriptors[GB_ACTOR_PHYSICAL_DESCRIPTOR_COUNT];
extern const u16 gb_level_actor_indices[GB_ACTOR_LEVEL_REFERENCE_COUNT];
extern const GbActorLevelIndexSpan gb_actor_level_spans[11];
extern const GbStoryActorDescriptor gb_story_actor_descriptors[GB_ACTOR_STORY_DESCRIPTOR_COUNT];
extern const GbRoutePoint gb_actor_routes[GB_ACTOR_ROUTE_COUNT][GB_ACTOR_ROUTE_POINTS];
extern const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT];
extern const u16 gb_actor_obj_palette[256];
extern const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_FRAME_HALFWORDS];

enum { GB_PLAYER_FRAME_COUNT = 16 };

extern const u16 gb_player_obj_palette[16];
extern const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128];

#endif
