#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/game.h>
#include <graveblood/input.h>
#include <graveblood/portal.h>
#include <graveblood/video.h>
#include <graveblood/world.h>

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

enum {
    GB_LEVEL_07 = 7,
    GB_LEVEL_08 = 8,
};

static const GbLevelAssets* gb_level_by_id(int level_id)
{
    switch(level_id)
    {
    case GB_LEVEL_07:
        return &gb_level07_assets;
    case GB_LEVEL_08:
        return &gb_level08_assets;
    default:
        return 0;
    }
}

static void gb_enter_level(GbWorld* world, GbPlayer* player, int level_id)
{
    const GbLevelAssets* assets = gb_level_by_id(level_id);
    if(! assets)
    {
        return;
    }

    gb_world_load(world, assets);
    gb_player_spawn(player, assets->spawn_x, assets->spawn_y);
    gb_world_update_camera(world, player->x, player->y);
    gb_video_draw_player(player, world->camera_x, world->camera_y);
}

void gb_game_run(void)
{
    GbWorld world;
    GbPlayer player;

    gb_video_init();
    gb_input_reset();
    gb_enter_level(&world, &player, GB_LEVEL_07);

    for(;;)
    {
        gb_video_wait_vblank();
        const GbInput input = gb_input_poll();

        gb_player_update(&player, world.assets, &input);

        const int portal_target = gb_portal_try_activate(world.assets, &player, &input);
        if(gb_level_by_id(portal_target))
        {
            gb_enter_level(&world, &player, portal_target);
            continue;
        }

        gb_world_update_camera(&world, player.x, player.y);
        gb_video_draw_player(&player, world.camera_x, world.camera_y);
    }
}
