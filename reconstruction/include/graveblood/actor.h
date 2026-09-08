#ifndef GRAVEBLOOD_ACTOR_H
#define GRAVEBLOOD_ACTOR_H

#include <gba.h>

enum {
    GB_PLAYER_ANIM_WALK_REGULAR = 2,
    GB_PLAYER_ANIM_WALK_UP = 7,
    GB_PLAYER_ANIM_IDLE = 8,
};

typedef struct {
    s16 x;
    s16 y;
    s8 facing_x;
    s8 facing_y;
    u8 facing_right;
    u8 animation_state;
    u8 animation_frame;
    u8 animation_countdown;
} GbPlayer;

void gb_player_spawn(GbPlayer* player, s16 x, s16 y);
u8 gb_player_frame_index(const GbPlayer* player);

#endif
