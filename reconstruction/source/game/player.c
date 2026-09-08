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
    player->facing_x = 0;
    player->facing_y = 1;
    player->facing_right = 0;
    player->animation_state = GB_PLAYER_ANIM_IDLE;
    player->animation_frame = 1;
    player->animation_countdown = 5;
}

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input)
{
    s16 dx = 0;
    s16 dy = 0;

    /* Original update advances the shared frame/countdown before committing
       the direction-selected animation state for this update. */
    gb_player_animation_tick(player);

    if(input->held & KEY_LEFT)
    {
        dx = -1;
        player->facing_x = -1;
        player->facing_y = 0;
        player->facing_right = 0;
    }
    else if(input->held & KEY_RIGHT)
    {
        dx = 1;
        player->facing_x = 1;
        player->facing_y = 0;
        player->facing_right = 1;
    }

    if(input->held & KEY_UP)
    {
        dy = -1;
        player->facing_x = 0;
        player->facing_y = -1;
        player->animation_state = GB_PLAYER_ANIM_WALK_UP;
    }
    else if(input->held & KEY_DOWN)
    {
        dy = 1;
        player->facing_x = 0;
        player->facing_y = 1;
        player->animation_state = GB_PLAYER_ANIM_WALK_REGULAR;
    }
    else if(dx)
    {
        player->animation_state = GB_PLAYER_ANIM_WALK_REGULAR;
    }
    else
    {
        player->animation_state = GB_PLAYER_ANIM_IDLE;
    }

    if(dx && gb_collision_can_stand(level, (s16)(player->x + dx), player->y))
    {
        player->x = (s16)(player->x + dx);
    }
    if(dy && gb_collision_can_stand(level, player->x, (s16)(player->y + dy)))
    {
        player->y = (s16)(player->y + dy);
    }
}
