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

void gb_world_load(GbWorld* world, const GbLevelAssets* assets)
{
    world->assets = assets;
    world->camera_x = 0;
    world->camera_y = 0;
    gb_video_load_level(assets);
    gb_video_set_camera(0, 0);
}

void gb_world_update_camera(GbWorld* world, s16 focus_x, s16 focus_y)
{
    const s16 world_width_pixels = (s16)(world->assets->world_width_tiles * 8);
    const s16 world_height_pixels = (s16)(world->assets->world_height_tiles * 8);
    const s16 max_x = world_width_pixels > 240 ? (s16)(world_width_pixels - 240) : 0;
    const s16 max_y = world_height_pixels > 160 ? (s16)(world_height_pixels - 160) : 0;

    world->camera_x = gb_clamp_s16((s16)(focus_x - 120), 0, max_x);
    world->camera_y = gb_clamp_s16((s16)(focus_y - 88), 0, max_y);
    BG_OFFSET[0].x = (u16)world->camera_x;
    BG_OFFSET[0].y = (u16)world->camera_y;
}
