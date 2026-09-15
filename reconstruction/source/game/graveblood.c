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

static void gb_enter_level(GbWorld* world, GbPlayer* player, GbActorSystem* actors,
                           GbStoryRuntime* story, int level_id)
{
    const GbLevelAssets* assets = gb_level_default_assets(level_id);
    if(! assets)
    {
        return;
    }

    const u8 saved_script_mode = player->script_mode;
    const u32 saved_script_counter = player->script_counter;
    const u8 saved_bicycle_mode = player->bicycle_mode;

    gb_world_load(world, assets);
    gb_player_spawn(player, assets->spawn_x, assets->spawn_y);
    gb_player_music_reset(player, level_id == 10 ? 1 : 0);
    gb_video_gameplay_lighting_reset_cursor();
    /* GameplayScene's activation path (0x08005CFC..0x08005D06) copies
       current LevelRecord+0x3C to Player+0x1E0 before active rendering. */
    player->idle_selector = assets->player_idle_selector;
    if(level_id == 10 && saved_script_mode == 5)
    {
        player->script_mode = saved_script_mode;
        player->script_counter = saved_script_counter;
        player->bicycle_mode = saved_bicycle_mode;
    }
    gb_actor_system_load(actors, assets);
    gb_story_on_level_load(story, actors);
    gb_audio_play_music(player->music_selector_desired);
    gb_world_update_camera(world, player->x, player->y);
    gb_video_draw_gameplay_objects(actors, player, story, world->camera_x, world->camera_y);
    gb_video_draw_story_ui(story);
}

void gb_game_run(void)
{
    GbWorld world = {0};
    GbPlayer player = {0};
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

        {
            const GbSceneTick pending_scene = gb_scene_update_pending(&scene);
            if(pending_scene.enter_gameplay)
            {
                gb_enter_level(&world, &player, &actors, &story, pending_scene.gameplay_level);
                continue;
            }
        }

        if(scene.active == GB_SCENE_PDA)
        {
            (void)gb_actor_system_update_physical_leaves_at(
                &actors, 0, world.camera_x, world.camera_y);
            gb_actor_system_update_leaf_particles(&actors, world.camera_x, world.camera_y);
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
                gb_audio_play_music(player.music_selector_desired);
                gb_video_draw_gameplay_objects(&actors, &player, &story,
                                               world.camera_x, world.camera_y);
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
            /* Player_update applies the four-entry OBJ lighting pass at
               0x08008312 before entering the hidden Wardrobe branch. */
            gb_video_gameplay_lighting_tick(1);
            const GbWardrobeTick wardrobe_tick = gb_wardrobe_update(&wardrobe, &input);
            if(wardrobe_tick.exit_gameplay)
            {
                gb_scene_request_gameplay(&scene, 7, 10);
                continue;
            }
            if(wardrobe_tick.selector_changed)
            {
                gb_video_draw_wardrobe(wardrobe.selector);
            }
            continue;
        }

        /* GameplayScene_update publishes/streams the camera and completes the
           object draw traversal before the generic object-update traversal.
           Player_update may then track a new dead-zone camera position, but
           that pending position is not published until the next gameplay frame. */
        gb_world_publish_camera(&world);
        gb_video_draw_gameplay_objects(&actors, &player, &story,
                                       world.camera_x, world.camera_y);
        gb_video_draw_story_ui(&story);

        /* Player_draw consumes the previous update traversal's contact flag.
           Clear it once before this frame's object updates; every interactable
           writer that still overlaps Player will advertise itself again. */
        player.interaction_available = 0;

        /* The original GameplayScene always reaches ObjectManager::update.
           Interaction state locks Player controls, but it does not remove the
           remaining objects from the serialized update traversal. */
        int player_locked = gb_story_player_controls_locked(&story);
        int suppress_interactions = player_locked;

        /* Story-overlay objects are inserted before the physical level vector.
           Keep their motion/routes alive while suppressing new fresh-A events
           when Player is already inside an interaction. */
        gb_actor_system_update_overlays(
            &actors, &player, player_locked ? 0 : &input, &interaction);
        const int overlay_sfx = gb_actor_system_take_pending_sfx(&actors);
        if(overlay_sfx >= 0)
        {
            gb_audio_play_sfx((u8)overlay_sfx);
        }
        if(! player_locked && interaction.type != GB_INTERACTION_NONE)
        {
            if(interaction.type == GB_INTERACTION_SOCIAL)
            {
                gb_player_queue_social_alignment(&player, interaction.actor_x, interaction.actor_y);
                gb_player_resolve_queued_motion(&player, world.assets);
            }
            else if(interaction.type == GB_INTERACTION_DIALOGUE &&
                    interaction.actor_index < actors.count &&
                    actors.actors[interaction.actor_index].descriptor &&
                    actors.actors[interaction.actor_index].descriptor->legs_color != 1)
            {
                gb_player_queue_vertical_target(&player, interaction.actor_y);
                gb_player_resolve_queued_motion(&player, world.assets);
            }
            gb_story_handle_interaction(&story, &actors, &interaction);
            player_locked = gb_story_player_controls_locked(&story);
            suppress_interactions = player_locked;
        }

        const u8 level_id = world.assets->level_id;
        const u8 player_physical_index = gb_player_physical_indices[level_id];
        const GbActorLevelIndexSpan physical_span = gb_actor_level_spans[level_id];

        /* Physical objects before Player always run, matching ObjectManager's
           unconditional vtable traversal.  Only fresh-A activation is masked
           while an interaction owns Player input. */
        for(u8 physical_index = 0; physical_index < player_physical_index; ++physical_index)
        {
            (void)gb_actor_system_update_physical_leaves_at(
                &actors, physical_index, world.camera_x, world.camera_y);
            (void)gb_actor_system_update_physical_fgtile_music_at(
                &actors, &player, physical_index);
            u8 fgtile_patch = 0;
            if(gb_actor_system_update_physical_fgtile_at(
                   &actors, &player, physical_index, &fgtile_patch))
            {
                gb_video_apply_fgtile_patch(fgtile_patch);
            }
            if(! suppress_interactions)
            {
                const int pre_portal_target = gb_portal_try_activate_physical_index(
                    world.assets, &player, &input, physical_index);
                if(gb_level_default_assets(pre_portal_target))
                {
                    gb_scene_request_gameplay(&scene, (u8)pre_portal_target, 10);
                }
            }
        }

        /* Player_update checks the ending latch at the Player's physical slot. */
        const int final_effect_was_pending = story.state.final_effect_pending;
        if(final_effect_was_pending)
        {
            gb_video_apply_final_effect();
        }

        /* 0x03000610 pauses the day/night clock only while the immediate
           dialogue/root/secondary interaction state is active.  The delayed
           and response-handshake phases run with that global cleared. */
        const int interaction_clock_paused = story.dialogue.active ||
            story.social.state == GB_SOCIAL_ROOT_SELECTOR ||
            story.social.state == GB_SOCIAL_SECONDARY;
        gb_video_gameplay_lighting_tick(interaction_clock_paused ? 0 : 1);

        if(! player_locked && input.held == (KEY_B | KEY_SELECT))
        {
            gb_wardrobe_init(&wardrobe);
            scene.active = GB_SCENE_WARDROBE;
            gb_video_load_wardrobe();
            continue;
        }

        {
            const GbPlayerMusicAction music_action = gb_player_music_tick(&player);
            if(music_action.set_volume)
            {
                gb_audio_set_music_volume(music_action.volume);
            }
            if(music_action.replace_music)
            {
                gb_audio_play_music(music_action.selector);
            }
        }

        if(player_locked)
        {
            /* Interaction state belongs to Player_update in the ROM.  Advance
               it here, at Player's exact serialized slot, instead of pausing
               the whole object manager.  Keep fresh-A masked for the rest of
               this frame even if this update dismisses the interaction. */
            suppress_interactions = 1;
            gb_story_update(&story, &actors, &input);
            if(! final_effect_was_pending && story.state.final_effect_pending)
            {
                gb_video_apply_final_effect();
            }
        }
        else
        {
            if(input.pressed & KEY_START)
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

            if(gb_player_try_level10_boundary(&player, world.assets->level_id))
            {
                gb_scene_request_gameplay(&scene, 10, 10);
            }
            gb_player_update(&player, world.assets, &input);
            gb_world_track_camera(&world, player.x, player.y);
            u16 player_sfx_volume = 0;
            const int player_sfx = gb_player_take_pending_sfx(&player, &player_sfx_volume);
            if(player_sfx >= 0)
            {
                gb_audio_play_sfx_volume((u8)player_sfx, player_sfx_volume);
            }
        }

        /* Resume the serialized physical vector after Player regardless of
           interaction state.  Motion/routes/music/tile controllers continue;
           fresh-A interactions remain masked while Player input is owned. */
        for(u16 index = (u16)player_physical_index + 1; index <= physical_span.count; ++index)
        {
            const u8 physical_index = (u8)index;
            (void)gb_actor_system_update_physical_fgtile_music_at(
                &actors, &player, physical_index);
            u8 fgtile_patch = 0;
            if(gb_actor_system_update_physical_fgtile_at(
                   &actors, &player, physical_index, &fgtile_patch))
            {
                gb_video_apply_fgtile_patch(fgtile_patch);
            }
            gb_actor_system_update_physical_npc_at(
                &actors, &player, suppress_interactions ? 0 : &input, &interaction, physical_index);
            if(! suppress_interactions && interaction.type != GB_INTERACTION_NONE)
            {
                if(interaction.type == GB_INTERACTION_SOCIAL)
                {
                    gb_player_queue_social_alignment(&player, interaction.actor_x, interaction.actor_y);
                    gb_player_resolve_queued_motion(&player, world.assets);
                }
                else if(interaction.type == GB_INTERACTION_DIALOGUE &&
                        interaction.actor_index < actors.count &&
                        actors.actors[interaction.actor_index].descriptor &&
                        actors.actors[interaction.actor_index].descriptor->legs_color != 1)
                {
                    gb_player_queue_vertical_target(&player, interaction.actor_y);
                    gb_player_resolve_queued_motion(&player, world.assets);
                }
                gb_story_handle_interaction(&story, &actors, &interaction);
                suppress_interactions = 1;
            }
            const int actor_sfx = gb_actor_system_take_pending_sfx(&actors);
            if(actor_sfx >= 0)
            {
                gb_audio_play_sfx((u8)actor_sfx);
            }

            if(! suppress_interactions)
            {
                (void)gb_story_try_level10_gate_physical_index(
                    &story, world.assets, &player, &input, physical_index);
                if(level_id == 9 && physical_index == 11)
                {
                    (void)gb_story_try_level9_treetype20_action(
                        world.assets, &player, &input);
                }

                const int portal_target = gb_portal_try_activate_physical_index(
                    world.assets, &player, &input, physical_index);
                if(gb_level_default_assets(portal_target))
                {
                    gb_scene_request_gameplay(&scene, (u8)portal_target, 10);
                }
            }
        }

        /* LeafParticle objects are appended to the object manager's live active
           vector by Leaves_update.  The ROM reloads vector end after each object,
           so newborn particles receive their first velocity step in this same
           traversal, after the serialized object stream. */
        gb_actor_system_update_leaf_particles(&actors, world.camera_x, world.camera_y);

        for(;;)
        {
            const int pending_sfx = gb_story_take_pending_sfx(&story);
            if(pending_sfx < 0)
            {
                break;
            }
            gb_audio_play_sfx((u8)pending_sfx);
        }

    }
}
