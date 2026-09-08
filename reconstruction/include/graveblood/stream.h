#ifndef GRAVEBLOOD_STREAM_H
#define GRAVEBLOOD_STREAM_H

#include <graveblood/assets.h>

enum {
    GB_STREAM_MAP_SIDE = 32,
    GB_STREAM_MAP_CELLS = GB_STREAM_MAP_SIDE * GB_STREAM_MAP_SIDE,
};

u16 gb_stream_entry(const GbLevelAssets* level, const u16* layer, s16 world_x, s16 world_y);
void gb_stream_fill(const GbLevelAssets* level, const u16* layer, s16 left, s16 top, volatile u16* map);
void gb_stream_fill_column(const GbLevelAssets* level, const u16* layer, s16 world_x, s16 top, volatile u16* map);
void gb_stream_fill_row(const GbLevelAssets* level, const u16* layer, s16 left, s16 world_y, volatile u16* map);

#endif
