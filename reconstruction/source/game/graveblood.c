#include <graveblood/actor.h>
#include <graveblood/actors.h>
#include <graveblood/assets.h>
#include <graveblood/game.h>
#include <graveblood/input.h>
#include <graveblood/portal.h>
#include <graveblood/story.h>
#include <graveblood/video.h>
#include <graveblood/world.h>

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

enum {
    GB_START_LEVEL = 7,
};

static void gb_enter_level(GbWorld* world, GbPlayer* player, GbActorSystem* actors,
                           GbStoryRuntime* story, int level_id)
{
    const GbLevelAssets* assets = gb_level_default_assets(level_id);
    if(! assets)
    {
        return;
    }

    gb_world_load(world, assets);
    gb_player_spawn(player, assets->spawn_x, assets->spawn_y);
    gb_actor_system_load(actors, assets);
    gb_story_on_level_load(story, actors);
    gb_world_update_camera(world, player->x, player->y);
    gb_video_draw_actors(actors, world->camera_x, world->camera_y);
    gb_video_draw_player_state(player, story, world->camera_x, world->camera_y);
    gb_video_draw_story_ui(story);
}

void gb_game_run(void)
{
    GbWorld world;
    GbPlayer player;
    GbActorSystem actors;
    GbStoryRuntime story;
    GbInteractionEvent interaction;

    gb_video_init();
    gb_input_reset();
    gb_story_init(&story);
    gb_enter_level(&world, &player, &actors, &story, GB_START_LEVEL);

    for(;;)
    {
        gb_video_wait_vblank();
        const GbInput input = gb_input_poll();

        if(story.state.final_effect_pending)
        {
            /* Safe terminal boundary for the unimplemented canonical
               0x08004FE0 expanding-VRAM effect. */
        }
        else if(gb_story_ui_active(&story))
        {
            gb_story_update(&story, &actors, &input);
        }
        else
        {
            gb_actor_system_update(&actors, &player, &input, &interaction);
            const GbStoryGateResult gate =
                gb_story_try_level10_gate(&story, world.assets, &player, &input);

            if(gate == GB_STORY_GATE_NONE)
            {
                gb_story_handle_interaction(&story, &actors, &interaction);
            }

            if(! gb_story_ui_active(&story) && gate != GB_STORY_GATE_TRAVERSED)
            {
                gb_player_update(&player, world.assets, &input);
            }

            if(! gb_story_ui_active(&story) && gate == GB_STORY_GATE_NONE)
            {
                const int portal_target = gb_portal_try_activate(world.assets, &player, &input);
                if(gb_level_default_assets(portal_target))
                {
                    gb_enter_level(&world, &player, &actors, &story, portal_target);
                    continue;
                }
            }
        }

        gb_world_update_camera(&world, player.x, player.y);
        gb_video_draw_actors(&actors, world.camera_x, world.camera_y);
        gb_video_draw_player_state(&player, &story, world.camera_x, world.camera_y);
        gb_video_draw_story_ui(&story);
    }
}
