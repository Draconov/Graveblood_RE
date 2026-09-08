#ifndef GRAVEBLOOD_ASSETS_H
#define GRAVEBLOOD_ASSETS_H

#include <gba.h>

typedef struct {
    s16 x;
    s16 y;
    u8 width;
    u8 height;
    u8 target_level;
    u16 num;
} GbPortal;

typedef struct {
    u8 level_id;
    u8 world_width_tiles;
    u8 world_height_tiles;
    s16 spawn_x;
    s16 spawn_y;
    u16 tile_count;
    u16 palette_count;
    const u16* palette;
    const u16* tiles;
    const u16* map;
    const u16* collision;
    const GbPortal* portals;
    u8 portal_count;
} GbLevelAssets;

extern const GbLevelAssets gb_level07_assets;
extern const GbLevelAssets gb_level08_assets;
enum { GB_PLAYER_FRAME_COUNT = 16 };

extern const u16 gb_player_obj_palette[16];
extern const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * 128];

#endif
