#ifndef GRAVEBLOOD_STREAM_H
#define GRAVEBLOOD_STREAM_H

#include <graveblood/assets.h>

enum {
    /* Hardware tilemap ring is 32x32, but the public demo's world streamer
       writes one guard column/row around the 30x20 visible viewport. */
    GB_STREAM_MAP_SIDE = 32,
    GB_STREAM_MAP_CELLS = GB_STREAM_MAP_SIDE * GB_STREAM_MAP_SIDE,
    GB_STREAM_VIEWPORT_WIDTH = 30,
    GB_STREAM_VIEWPORT_HEIGHT = 20,
    GB_STREAM_WINDOW_WIDTH = GB_STREAM_VIEWPORT_WIDTH + 1,
    GB_STREAM_WINDOW_HEIGHT = GB_STREAM_VIEWPORT_HEIGHT + 1,
};

u16 gb_stream_entry(const GbLevelAssets* level, const u16* layer, s16 world_x, s16 world_y);
void gb_stream_fill(const GbLevelAssets* level, const u16* layer, s16 left, s16 top, volatile u16* map);
void gb_stream_fill_column(const GbLevelAssets* level, const u16* layer, s16 world_x, s16 top, volatile u16* map);
void gb_stream_fill_row(const GbLevelAssets* level, const u16* layer, s16 left, s16 world_y, volatile u16* map);

#endif
