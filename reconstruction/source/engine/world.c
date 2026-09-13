#include <graveblood/world.h>
#include <graveblood/stream.h>
#include <graveblood/video.h>

static int gb_abs_int(int value)
{
    return value < 0 ? -value : value;
}

void gb_world_load(GbWorld* world, const GbLevelAssets* assets)
{
    world->assets = assets;
    world->stream_tile_x = 0;
    world->stream_tile_y = 0;
    world->stream_valid = 0;
    gb_video_load_level(assets);
    gb_video_set_camera(world->camera_x, world->camera_y);
}

void gb_world_track_camera(GbWorld* world, s16 focus_x, s16 focus_y)
{
    /* Player+0x08/+0x10 and +0x0C/+0x14 form the ROM's body-center
       camera target.  The public-demo Player body is 16x16, so the
       integer anchor maps to center=(x+8,y-8).  0x08006550 keeps that
       center inside a 48x26 dead-zone instead of recentering every frame. */
    const int center_x = (int)focus_x + 8;
    const int center_y = (int)focus_y - 8;
    int camera_x = world->camera_x;
    int camera_y = world->camera_y;

    if(camera_x < center_x - 144)
    {
        camera_x = center_x - 144;
    }
    if(camera_x > center_x - 96)
    {
        camera_x = center_x - 96;
    }
    if(camera_y < center_y - 93)
    {
        camera_y = center_y - 93;
    }
    if(camera_y > center_y - 67)
    {
        camera_y = center_y - 67;
    }

    world->camera_x = (s16)camera_x;
    world->camera_y = (s16)camera_y;
}

void gb_world_publish_camera(GbWorld* world)
{
    /* 0x0800A2D4 applies these as two ordered clamps, not a conventional
       clamp with a normalized range: first >= 0, then <= (size-view)*8.
       Level 7 is 29 tiles wide, so its signed maximum is deliberately -8. */
    const s16 max_x = (s16)(((int)world->assets->world_width_tiles - GB_STREAM_VIEWPORT_WIDTH) * 8);
    const s16 max_y = (s16)(((int)world->assets->world_height_tiles - GB_STREAM_VIEWPORT_HEIGHT) * 8);

    if(world->camera_x < 0)
    {
        world->camera_x = 0;
    }
    if(world->camera_x > max_x)
    {
        world->camera_x = max_x;
    }
    if(world->camera_y < 0)
    {
        world->camera_y = 0;
    }
    if(world->camera_y > max_y)
    {
        world->camera_y = max_y;
    }

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
        const int abs_dx = gb_abs_int(dx);
        const int abs_dy = gb_abs_int(dy);
        if(abs_dx > GB_STREAM_VIEWPORT_WIDTH ||
           abs_dy > GB_STREAM_VIEWPORT_HEIGHT ||
           abs_dx * abs_dy > 150)
        {
            gb_video_stream_full(world->assets, tile_x, tile_y);
        }
        else
        {
            if(dx > 0)
            {
                const int first_x = world->stream_tile_x + GB_STREAM_WINDOW_WIDTH;
                const int last_x = tile_x + GB_STREAM_VIEWPORT_WIDTH;
                for(int x = first_x; x <= last_x; ++x)
                {
                    gb_video_stream_column(world->assets, (s16)x, tile_y);
                }
            }
            else if(dx < 0)
            {
                for(int x = tile_x; x < world->stream_tile_x; ++x)
                {
                    gb_video_stream_column(world->assets, (s16)x, tile_y);
                }
            }

            if(dy > 0)
            {
                const int first_y = world->stream_tile_y + GB_STREAM_WINDOW_HEIGHT;
                const int last_y = tile_y + GB_STREAM_VIEWPORT_HEIGHT;
                for(int y = first_y; y <= last_y; ++y)
                {
                    gb_video_stream_row(world->assets, tile_x, (s16)y);
                }
            }
            else if(dy < 0)
            {
                for(int y = tile_y; y < world->stream_tile_y; ++y)
                {
                    gb_video_stream_row(world->assets, tile_x, (s16)y);
                }
            }
        }
    }

    world->stream_tile_x = tile_x;
    world->stream_tile_y = tile_y;
    world->stream_valid = 1;
    gb_video_set_camera(world->camera_x, world->camera_y);
}

void gb_world_update_camera(GbWorld* world, s16 focus_x, s16 focus_y)
{
    gb_world_track_camera(world, focus_x, focus_y);
    gb_world_publish_camera(world);
}
