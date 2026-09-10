#include <graveblood/actor.h>
#include <graveblood/actors.h>
#include <graveblood/audio.h>
#include <graveblood/assets.h>
#include <graveblood/game.h>
#include <graveblood/input.h>
#include <graveblood/portal.h>
#include <graveblood/pda.h>
#include <graveblood/scene.h>
#include <graveblood/story.h>
#include <graveblood/video.h>
#include <graveblood/wardrobe.h>
#include <graveblood/world.h>

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

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
    gb_audio_play_music(level_id == 10 ? 1 : 0);
    gb_world_update_camera(world, player->x, player->y);
    gb_video_draw_actors(actors, player, world->camera_x, world->camera_y);
    gb_video_draw_player_state(player, story, world->camera_x, world->camera_y);
    gb_video_draw_story_ui(story);
}

void gb_game_run(void)
{
    GbWorld world;
    GbPlayer player;
    GbActorSystem actors;
    GbStoryRuntime story;
    GbSceneRuntime scene;
    GbWardrobeRuntime wardrobe;
    GbPdaRuntime pda;
    GbInteractionEvent interaction;

    gb_video_init();
    gb_audio_init();
    gb_input_reset();
    gb_story_init(&story);
    gb_actor_system_init(&actors);
    gb_scene_init(&scene);
    gb_wardrobe_init(&wardrobe);
    gb_pda_reset(&pda);
    gb_video_load_title();

    for(;;)
    {
        gb_video_wait_vblank();
        const GbInput input = gb_input_poll();

        if(scene.active == GB_SCENE_TITLE)
        {
            const GbSceneTick tick = gb_scene_update_title(&scene, &input);
            if(tick.play_start_sfx)
            {
                gb_audio_play_sfx(6);
            }
            if(tick.enter_gameplay)
            {
                gb_enter_level(&world, &player, &actors, &story, tick.gameplay_level);
                continue;
            }
            gb_video_title_set_animation(scene.title_animation_state);
            gb_video_title_set_prompt_visible(tick.prompt_visible);
            continue;
        }

        if(scene.active == GB_SCENE_PDA)
        {
            gb_actor_system_update_environment(&actors, world.camera_x, world.camera_y);
            const GbPdaTick pda_tick = gb_pda_update(&pda, &story.state, &input);
            if(pda_tick.stop_reserved_audio)
            {
                gb_audio_stop_channel(0);
                gb_audio_stop_channel(1);
                gb_audio_stop_channel(2);
            }
            if(pda_tick.sfx_id >= 0)
            {
                gb_audio_play_sfx((u8)pda_tick.sfx_id);
            }
            if(pda_tick.return_requested)
            {
                scene.active = GB_SCENE_GAMEPLAY;
                gb_video_load_level(world.assets);
                world.stream_valid = 0;
                gb_world_update_camera(&world, player.x, player.y);
                gb_audio_play_music(world.assets->level_id == 10 ? 1 : 0);
                gb_video_draw_actors(&actors, &player, world.camera_x, world.camera_y);
                gb_video_draw_player_state(&player, &story, world.camera_x, world.camera_y);
                gb_video_draw_story_ui(&story);
                continue;
            }
            if(pda_tick.rerender)
            {
                gb_video_draw_pda(&pda, &story);
            }
            continue;
        }

        if(scene.active == GB_SCENE_WARDROBE)
        {
            const GbWardrobeTick wardrobe_tick = gb_wardrobe_update(&wardrobe, &input);
            if(wardrobe_tick.exit_gameplay)
            {
                scene.active = GB_SCENE_GAMEPLAY;
                gb_enter_level(&world, &player, &actors, &story, 7);
                continue;
            }
            if(wardrobe_tick.selector_changed)
            {
                gb_video_draw_wardrobe(wardrobe.selector);
            }
            continue;
        }

        if(! story.state.final_effect_pending &&
           ! gb_story_ui_active(&story) &&
           (input.pressed & KEY_START))
        {
            gb_audio_stop_channel(0);
            gb_audio_stop_channel(1);
            gb_audio_stop_channel(2);
            gb_audio_play_sfx(6);
            gb_pda_open(&pda);
            scene.active = GB_SCENE_PDA;
            gb_video_load_pda(world.assets, &pda, &story);
            continue;
        }

        if(! story.state.final_effect_pending &&
           ! gb_story_ui_active(&story) &&
           input.held == (KEY_B | KEY_SELECT))
        {
            gb_wardrobe_init(&wardrobe);
            scene.active = GB_SCENE_WARDROBE;
            gb_video_load_wardrobe();
            continue;
        }

        gb_actor_system_update_environment(&actors, world.camera_x, world.camera_y);

        if(story.state.final_effect_pending)
        {
            /* Static RE proves normal zero-seeded execution repeatedly uses
               argument 0.  That exact 96,000 + 16,000 byte blast stays
               inside the GBA's 96 KiB VRAM; larger latent arguments remain
               intentionally unsupported. */
            gb_video_apply_final_effect();
        }
        else if(gb_story_ui_active(&story))
        {
            gb_story_update(&story, &actors, &input);
        }
        else
        {
            gb_actor_system_update(&actors, &player, &input, &interaction);
            GbStoryGateResult gate =
                gb_story_try_level10_gate(&story, world.assets, &player, &input);
            if(gate == GB_STORY_GATE_NONE)
            {
                gate = gb_story_try_level9_treetype20_action(world.assets, &player, &input);
            }

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

        const int pending_sfx = gb_story_take_pending_sfx(&story);
        if(pending_sfx >= 0)
        {
            gb_audio_play_sfx((u8)pending_sfx);
        }

        gb_world_update_camera(&world, player.x, player.y);
        gb_video_draw_actors(&actors, &player, world.camera_x, world.camera_y);
        gb_video_draw_player_state(&player, &story, world.camera_x, world.camera_y);
        gb_video_draw_story_ui(&story);
    }
}
