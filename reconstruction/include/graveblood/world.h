#ifndef GRAVEBLOOD_WORLD_H
#define GRAVEBLOOD_WORLD_H

#include <graveblood/assets.h>

typedef struct {
    const GbLevelAssets* assets;
    s16 camera_x;
    s16 camera_y;
} GbWorld;

void gb_world_load(GbWorld* world, const GbLevelAssets* assets);
void gb_world_update_camera(GbWorld* world, s16 focus_x, s16 focus_y);

#endif
