#include <graveblood/stream.h>

static unsigned gb_ring_coord(s16 value)
{
    return ((u16)value) & (GB_STREAM_MAP_SIDE - 1);
}

static unsigned gb_ring_index(s16 world_x, s16 world_y)
{
    return gb_ring_coord(world_y) * GB_STREAM_MAP_SIDE + gb_ring_coord(world_x);
}

u16 gb_stream_entry(const GbLevelAssets* level, const u16* layer, s16 world_x, s16 world_y)
{
    /* 0x0800A330 computes one linear source address as
       layer + (world_y * width + world_x).  It does not independently reject
       x=-1 or x==width, so those coordinates alias an adjacent row whenever
       the resulting linear cell still lies inside the extracted source. */
    const int cell = (int)world_y * (int)level->world_width_tiles + (int)world_x;
    const int cell_count = (int)level->world_width_tiles * (int)level->world_height_tiles;
    if(cell < 0 || cell >= cell_count)
    {
        return 0;
    }

    const u16 source_id = layer[cell];
    if(source_id >= level->translation_count)
    {
        return 0;
    }
    return level->translation[source_id];
}

void gb_stream_fill(const GbLevelAssets* level, const u16* layer, s16 left, s16 top, volatile u16* map)
{
    for(int row = 0; row < GB_STREAM_WINDOW_HEIGHT; ++row)
    {
        const s16 world_y = (s16)(top + row);
        for(int column = 0; column < GB_STREAM_WINDOW_WIDTH; ++column)
        {
            const s16 world_x = (s16)(left + column);
            map[gb_ring_index(world_x, world_y)] = gb_stream_entry(level, layer, world_x, world_y);
        }
    }
}

void gb_stream_fill_column(const GbLevelAssets* level, const u16* layer, s16 world_x, s16 top, volatile u16* map)
{
    for(int row = 0; row < GB_STREAM_WINDOW_HEIGHT; ++row)
    {
        const s16 world_y = (s16)(top + row);
        map[gb_ring_index(world_x, world_y)] = gb_stream_entry(level, layer, world_x, world_y);
    }
}

void gb_stream_fill_row(const GbLevelAssets* level, const u16* layer, s16 left, s16 world_y, volatile u16* map)
{
    for(int column = 0; column < GB_STREAM_WINDOW_WIDTH; ++column)
    {
        const s16 world_x = (s16)(left + column);
        map[gb_ring_index(world_x, world_y)] = gb_stream_entry(level, layer, world_x, world_y);
    }
}
