#include <graveblood/actor.h>
#include <graveblood/actors.h>
#include <graveblood/assets.h>
#include <graveblood/game.h>
#include <graveblood/input.h>
#include <graveblood/portal.h>
#include <graveblood/video.h>
#include <graveblood/world.h>

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

enum {
    GB_START_LEVEL = 7,
};

static void gb_enter_level(GbWorld* world, GbPlayer* player, GbActorSystem* actors, int level_id)
{
    const GbLevelAssets* assets = gb_level_default_assets(level_id);
    if(! assets)
    {
        return;
    }

    gb_world_load(world, assets);
    gb_player_spawn(player, assets->spawn_x, assets->spawn_y);
    gb_actor_system_load(actors, assets);
    gb_world_update_camera(world, player->x, player->y);
    gb_video_draw_actors(actors, world->camera_x, world->camera_y);
    gb_video_draw_player(player, world->camera_x, world->camera_y);
}

void gb_game_run(void)
{
    GbWorld world;
    GbPlayer player;
    GbActorSystem actors;
    GbInteractionEvent interaction;

    gb_video_init();
    gb_input_reset();
    gb_enter_level(&world, &player, &actors, GB_START_LEVEL);

    for(;;)
    {
        gb_video_wait_vblank();
        const GbInput input = gb_input_poll();

        gb_player_update(&player, world.assets, &input);
        gb_actor_system_update(&actors, &player, &input, &interaction);

        const int portal_target = gb_portal_try_activate(world.assets, &player, &input);
        if(gb_level_default_assets(portal_target))
        {
            gb_enter_level(&world, &player, &actors, portal_target);
            continue;
        }

        gb_world_update_camera(&world, player.x, player.y);
        gb_video_draw_actors(&actors, world.camera_x, world.camera_y);
        gb_video_draw_player(&player, world.camera_x, world.camera_y);
    }
}
