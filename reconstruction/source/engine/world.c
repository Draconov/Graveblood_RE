#include <graveblood/world.h>
#include <graveblood/video.h>

static s16 gb_clamp_s16(s16 value, s16 minimum, s16 maximum)
{
    if(value < minimum)
    {
        return minimum;
    }
    if(value > maximum)
    {
        return maximum;
    }
    return value;
}

static int gb_abs_int(int value)
{
    return value < 0 ? -value : value;
}

void gb_world_load(GbWorld* world, const GbLevelAssets* assets)
{
    world->assets = assets;
    world->camera_x = 0;
    world->camera_y = 0;
    world->stream_tile_x = 0;
    world->stream_tile_y = 0;
    world->stream_valid = 0;
    gb_video_load_level(assets);
    gb_video_set_camera(0, 0);
}

void gb_world_update_camera(GbWorld* world, s16 focus_x, s16 focus_y)
{
    const int world_width_pixels = (int)world->assets->world_width_tiles * 8;
    const int world_height_pixels = (int)world->assets->world_height_tiles * 8;
    const s16 max_x = world_width_pixels > 240 ? (s16)(world_width_pixels - 240) : 0;
    const s16 max_y = world_height_pixels > 160 ? (s16)(world_height_pixels - 160) : 0;

    world->camera_x = gb_clamp_s16((s16)(focus_x - 120), 0, max_x);
    world->camera_y = gb_clamp_s16((s16)(focus_y - 88), 0, max_y);

    const s16 tile_x = (s16)(world->camera_x >> 3);
    const s16 tile_y = (s16)(world->camera_y >> 3);
    if(! world->stream_valid)
    {
        gb_video_stream_full(world->assets, tile_x, tile_y);
    }
    else
    {
        const int dx = (int)tile_x - world->stream_tile_x;
        const int dy = (int)tile_y - world->stream_tile_y;
        if(gb_abs_int(dx) > 1 || gb_abs_int(dy) > 1)
        {
            gb_video_stream_full(world->assets, tile_x, tile_y);
        }
        else
        {
            if(dx > 0)
            {
                gb_video_stream_column(world->assets, (s16)(tile_x + 31), tile_y);
            }
            else if(dx < 0)
            {
                gb_video_stream_column(world->assets, tile_x, tile_y);
            }

            if(dy > 0)
            {
                gb_video_stream_row(world->assets, tile_x, (s16)(tile_y + 31));
            }
            else if(dy < 0)
            {
                gb_video_stream_row(world->assets, tile_x, tile_y);
            }
        }
    }

    world->stream_tile_x = tile_x;
    world->stream_tile_y = tile_y;
    world->stream_valid = 1;
    gb_video_set_camera(world->camera_x, world->camera_y);
}
