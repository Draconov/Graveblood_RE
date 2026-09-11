#include <graveblood/actor.h>
#include <graveblood/collision.h>
#include <graveblood/input.h>

static void gb_player_animation_tick(GbPlayer* player)
{
    const u8 max_frame = player->animation_state == GB_PLAYER_ANIM_IDLE ? 8 : 6;
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
        player->animation_countdown = player->animation_state == GB_PLAYER_ANIM_IDLE ? 8 : 5;
    }
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
    player->script_mode = 0;
    player->script_counter = 0;
    player->facing_x = 0;
    player->facing_y = 1;
    player->facing_right = 0;
    player->animation_state = GB_PLAYER_ANIM_IDLE;
    player->animation_frame = 1;
    player->animation_countdown = 5;
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

    player->request_x_fixed = 0;
    player->request_y_fixed = 0;

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

    gb_collision_apply_player_motion(level, player);
}

