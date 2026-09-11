#ifndef GRAVEBLOOD_ACTOR_H
#define GRAVEBLOOD_ACTOR_H

#include <gba.h>

enum {
    GB_PLAYER_ANIM_WALK_REGULAR = 2,
    GB_PLAYER_ANIM_WALK_UP = 7,
    GB_PLAYER_ANIM_IDLE = 8,
};

typedef struct {
    /* Public pixel anchors used by the clean-room renderer/story layer.
       The original Player object stores the authoritative coordinates at
       +0x08/+0x0C as 24.8 fixed-point; keep both so subpixel motion is not
       lost while the existing high-level systems remain pixel based. */
    s16 x;
    s16 y;
    s32 x_fixed;
    s32 y_fixed;
    s32 request_x_fixed;
    s32 request_y_fixed;
    s32 collision_width_fixed;
    s32 collision_height_fixed;
    u16 collision_status;
    /* Clean-room representation of the controller-owned scripted Player
       mode/counter used by the Level-9 -> Level-10 entrance sequence. */
    u8 script_mode;
    u32 script_counter;
    s8 facing_x;
    s8 facing_y;
    u8 facing_right;
    u8 animation_state;
    u8 animation_frame;
    u8 animation_countdown;
} GbPlayer;

void gb_player_spawn(GbPlayer* player, s16 x, s16 y);
u8 gb_player_try_level10_boundary(GbPlayer* player, u8 current_level);
u8 gb_player_frame_index(const GbPlayer* player);

#endif
