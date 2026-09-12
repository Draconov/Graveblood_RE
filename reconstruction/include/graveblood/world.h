#ifndef GRAVEBLOOD_WORLD_H
#define GRAVEBLOOD_WORLD_H

#include <graveblood/assets.h>

typedef struct {
    const GbLevelAssets* assets;
    s16 camera_x;
    s16 camera_y;
    s16 stream_tile_x;
    s16 stream_tile_y;
    u8 stream_valid;
} GbWorld;

void gb_world_load(GbWorld* world, const GbLevelAssets* assets);
void gb_world_track_camera(GbWorld* world, s16 focus_x, s16 focus_y);
void gb_world_publish_camera(GbWorld* world);
void gb_world_update_camera(GbWorld* world, s16 focus_x, s16 focus_y);

#endif
