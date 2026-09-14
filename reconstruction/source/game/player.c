#include <graveblood/actor.h>
#include <graveblood/collision.h>
#include <graveblood/input.h>

static void gb_player_animation_tick(GbPlayer* player)
{
    const u8 max_frame = player->bicycle_mode == 2 ? 6 :
        (player->animation_state == GB_PLAYER_ANIM_IDLE ? 8 : 6);
    if(player->animation_frame < 1 || player->animation_frame > max_frame)
    {
        player->animation_frame = 1;
    }

    if(player->animation_countdown > 0)
    {
        --player->animation_countdown;
    }
    else
    {
        if(player->animation_frame >= max_frame)
        {
            player->animation_frame = 1;
        }
        else
        {
            ++player->animation_frame;
        }
        player->animation_countdown =
            player->animation_state == GB_PLAYER_ANIM_IDLE && player->idle_selector == 0 ? 8 : 5;
    }
}


static const u16 gb_player_music_fade_table[75] = {
    142, 140, 138, 136, 134, 132, 130, 128, 126, 124,
    122, 120, 118, 116, 114, 112, 110, 108, 106, 104,
    102, 100, 98, 96, 94, 92, 90, 88, 86, 84,
    82, 80, 78, 76, 74, 72, 70, 68, 66, 64,
    62, 60, 58, 56, 54, 52, 50, 48, 46, 44,
    42, 40, 38, 36, 34, 32, 30, 28, 26, 24,
    22, 20, 18, 16, 14, 12, 10, 8, 6, 4,
    2, 0, 0, 0, 0,
};

void gb_player_music_reset(GbPlayer* player, u8 selector)
{
    if(! player)
    {
        return;
    }
    player->music_selector_desired = selector;
    player->music_selector_applied = selector;
    player->music_fade_counter = 0;
}

GbPlayerMusicAction gb_player_music_tick(GbPlayer* player)
{
    GbPlayerMusicAction action = {0};
    if(! player)
    {
        return action;
    }

    /* Player_update 0x08008328 compares desired +0x1CC against applied
       +0x1D0.  A mismatch advances the global fade counter and uses the
       recovered 75-word volume table.  If desired returns to applied before
       replacement, the counter is intentionally retained rather than reset. */
    if(player->music_selector_desired != player->music_selector_applied &&
       player->music_fade_counter <= 74)
    {
        ++player->music_fade_counter;
        if(player->music_fade_counter < 75)
        {
            action.set_volume = 1;
            action.volume = gb_player_music_fade_table[player->music_fade_counter];
            return action;
        }
    }

    if(player->music_fade_counter == 75)
    {
        /* The ROM indexes one word past the 75-word table at counter 75, then
           immediately stops/restarts the reserved channel at volume 0x90.
           There is no mixer boundary between those operations, so expose the
           observable replacement without reproducing the invalid transient. */
        action.replace_music = 1;
        action.selector = player->music_selector_desired;
        action.volume = 0x90;
        player->music_selector_applied = player->music_selector_desired;
        player->music_fade_counter = 0;
    }
    return action;
}

u8 gb_player_frame_index(const GbPlayer* player)
{
    const u8 frame = player->animation_frame > 0 ? player->animation_frame : 1;
    if(player->animation_state == GB_PLAYER_ANIM_WALK_UP)
    {
        return (u8)(6 + ((frame - 1) % 6));
    }
    if(player->animation_state == GB_PLAYER_ANIM_IDLE)
    {
        if(player->idle_selector == 1)
        {
            return (u8)(16 + ((frame - 1) % 8));
        }
        static const u8 idle_frames[8] = { 12, 13, 14, 15, 15, 14, 13, 12 };
        return idle_frames[(frame - 1) % 8];
    }
    return (u8)((frame - 1) % 6);
}

void gb_player_spawn(GbPlayer* player, s16 x, s16 y)
{
    player->x = x;
    player->y = y;
    player->x_fixed = (s32)x << 8;
    player->y_fixed = (s32)y << 8;
    player->request_x_fixed = 0;
    player->request_y_fixed = 0;
    player->collision_width_fixed = 0x1000;
    player->collision_height_fixed = 0x1000;
    player->collision_status = 0;
    player->motion_reset_x = 1;
    player->motion_reset_y = 1;
    player->script_mode = 0;
    player->script_counter = 0;
    player->bicycle_mode = 0;
    gb_player_music_reset(player, 0);
    player->pending_sfx_id = -1;
    player->pending_sfx_volume = 0;
    player->facing_x = 0;
    player->facing_y = 1;
    player->facing_right = 0;
    player->idle_selector = 0;
    player->animation_state = GB_PLAYER_ANIM_IDLE;
    player->animation_frame = 1;
    player->animation_countdown = 5;
}


void gb_player_queue_vertical_target(GbPlayer* player, s16 target_y)
{
    if(! player)
    {
        return;
    }

    /* 0x080080A4 writes targetY-currentY to Player+0x1C, then clears
       Player+0x390/+0x394.  The following normal Player update therefore
       preserves the queued request long enough to pass through collision. */
    player->request_y_fixed = ((s32)target_y << 8) - player->y_fixed;
    player->motion_reset_x = 0;
    player->motion_reset_y = 0;
}

void gb_player_queue_social_alignment(GbPlayer* player, s16 anchor_x, s16 anchor_y)
{
    if(! player)
    {
        return;
    }

    /* Player interaction state 0 (0x0800921A/0x08009552) aligns to the
       NPC's Y and leaves exactly 0x1300 fixed8 (19 px) between Player and
       NPC on the appropriate side before advancing the social selector. */
    const s32 anchor_x_fixed = (s32)anchor_x << 8;
    const s32 anchor_y_fixed = (s32)anchor_y << 8;
    if(anchor_x_fixed >= player->x_fixed)
    {
        player->request_x_fixed = anchor_x_fixed - player->x_fixed - 0x1300;
        player->facing_right = 1;
        player->facing_x = 1;
    }
    else
    {
        player->request_x_fixed = anchor_x_fixed - player->x_fixed + 0x1300;
        player->facing_right = 0;
        player->facing_x = -1;
    }
    player->request_y_fixed = anchor_y_fixed - player->y_fixed;
    player->facing_y = 0;
    player->motion_reset_x = 0;
    player->motion_reset_y = 0;
}

void gb_player_resolve_queued_motion(GbPlayer* player, const GbLevelAssets* level)
{
    if(! player)
    {
        return;
    }

    /* Interaction alignment uses the common 0x08004670 collision tail rather
       than the normal D-pad path.  Re-arm the two normal-reset sentinels so
       the surviving request is cleared on the following gameplay update. */
    player->motion_reset_x = 1;
    player->motion_reset_y = 1;
    gb_collision_apply_player_motion(level, player);
}

u8 gb_player_try_level10_boundary(GbPlayer* player, u8 current_level)
{
    /* Player_update 0x080081E6..0x08008834: when the integer X position
       exceeds 0x9FB (2555), mode is still 0 and the current level is 9,
       request gameplay level 10 and change the controller mode to 5. */
    if(! player || current_level != 9 || player->script_mode != 0)
    {
        return 0;
    }
    if((player->x_fixed >> 8) <= 2555)
    {
        return 0;
    }
    player->script_mode = 5;
    return 1;
}

static void gb_player_sync_external_pixel_position(GbPlayer* player)
{
    /* Story/gate code still works in pixel anchors.  Preserve a legitimate
       fractional remainder when the integer pixel agrees, but adopt an
       external teleport when it does not. */
    if((s16)(player->x_fixed >> 8) != player->x)
    {
        player->x_fixed = (s32)player->x << 8;
    }
    if((s16)(player->y_fixed >> 8) != player->y)
    {
        player->y_fixed = (s32)player->y << 8;
    }
}

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input)
{
    gb_player_sync_external_pixel_position(player);

    if(player->motion_reset_x)
    {
        player->request_x_fixed = 0;
    }
    if(player->motion_reset_y)
    {
        player->request_y_fixed = 0;
    }

    /* Controller mode 5/6 is the recovered Level-10 scripted entrance.
       Mode 5 is inert before Level 10 arrives.  In Level 10 it increments
       the controller counter and requests +370 fixed8 X.  Once the current
       X is >700 and the incremented counter is >350 it snaps Y to 870 and
       enters mode 6.  Mode 6 requests -256 fixed8 Y while Y>780, then clears
       the scripted mode on the following update at/below 780. */
    if(player->script_mode == 5)
    {
        if(level && level->level_id == 10)
        {
            ++player->script_counter;
            player->request_x_fixed = 370;
            if((player->x_fixed >> 8) > 700 && player->script_counter > 350)
            {
                player->y_fixed = 870 << 8;
                player->y = 870;
                player->request_x_fixed = 0;
                player->bicycle_mode = 0;
                player->script_mode = 6;
            }
            gb_collision_apply_player_motion(level, player);
        }
        return;
    }
    if(player->script_mode == 6)
    {
        if(level && level->level_id == 10)
        {
            if((player->y_fixed >> 8) > 780)
            {
                player->request_y_fixed = -256;
                gb_collision_apply_player_motion(level, player);
            }
            else
            {
                player->script_mode = 0;
            }
        }
        return;
    }

    /* The shared ride state at 0x030005F4 is checked only on the normal
       controller path.  Value 2 gates a fresh-R one-shot at 0x08009C10:
       sound 10, volume 0x1E.  Scripted modes returned above, matching the
       ROM gate that requires controller mode 0. */
    if(player->bicycle_mode == 2 && (input->pressed & GB_INPUT_KEY_R))
    {
        player->pending_sfx_id = 10;
        player->pending_sfx_volume = 30;
    }

    /* Normal Player mode at 0x080083A8 clears stale per-axis requests, then
       LEFT/RIGHT and UP/DOWN write exact +/-0x100 fixed8 values.  The distant
       blocks at 0x08009B64/0x08009B80 are compiler long branches, not helper
       calls; LEFT wins over RIGHT and UP wins over DOWN. */
    gb_player_animation_tick(player);

    if(input->held & KEY_LEFT)
    {
        player->request_x_fixed = -0x100;
        player->facing_x = -1;
        player->facing_y = 0;
        player->facing_right = 0;
    }
    else if(input->held & KEY_RIGHT)
    {
        player->request_x_fixed = 0x100;
        player->facing_x = 1;
        player->facing_y = 0;
        player->facing_right = 1;
    }

    if(input->held & KEY_UP)
    {
        player->request_y_fixed = -0x100;
        player->facing_x = 0;
        player->facing_y = -1;
        player->animation_state = GB_PLAYER_ANIM_WALK_UP;
    }
    else if(input->held & KEY_DOWN)
    {
        player->request_y_fixed = 0x100;
        player->facing_x = 0;
        player->facing_y = 1;
        player->animation_state = GB_PLAYER_ANIM_WALK_REGULAR;
    }
    else if(player->request_x_fixed != 0)
    {
        player->animation_state = GB_PLAYER_ANIM_WALK_REGULAR;
    }
    else
    {
        player->animation_state = GB_PLAYER_ANIM_IDLE;
    }

    /* Normal ROM path 0x0800842A..0x08008434 re-arms both +0x390/+0x394
       sentinels before the common collision resolver. */
    player->motion_reset_x = 1;
    player->motion_reset_y = 1;
    gb_collision_apply_player_motion(level, player);
}


int gb_player_take_pending_sfx(GbPlayer* player, u16* volume)
{
    if(! player || player->pending_sfx_id < 0)
    {
        return -1;
    }
    const int sound_id = player->pending_sfx_id;
    if(volume)
    {
        *volume = player->pending_sfx_volume;
    }
    player->pending_sfx_id = -1;
    player->pending_sfx_volume = 0;
    return sound_id;
}
