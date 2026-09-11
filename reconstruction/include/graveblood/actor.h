#ifndef GRAVEBLOOD_ACTOR_H
#define GRAVEBLOOD_ACTOR_H

#include <gba.h>
#include <graveblood/assets.h>

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
    /* ROM Player+0x390/+0x394 are dual-purpose target/reset fields.  The
       normal path stores 1 in both; 0x080080A4 clears both after queuing a
       forced vertical request so that request survives one normal update. */
    u8 motion_reset_x;
    u8 motion_reset_y;
    /* Clean-room representation of the controller-owned scripted Player
       mode/counter used by the Level-9 -> Level-10 entrance sequence. */
    u8 script_mode;
    u32 script_counter;
    s8 facing_x;
    s8 facing_y;
    u8 facing_right;
    /* Original Player+0x1E0. Gameplay-scene activation copies the current
       LevelRecord+0x3C value here before the first active draw/update. */
    u8 idle_selector;
    u8 animation_state;
    u8 animation_frame;
    u8 animation_countdown;
} GbPlayer;

void gb_player_spawn(GbPlayer* player, s16 x, s16 y);
void gb_player_queue_vertical_target(GbPlayer* player, s16 target_y);
void gb_player_queue_social_alignment(GbPlayer* player, s16 anchor_x, s16 anchor_y);
void gb_player_resolve_queued_motion(GbPlayer* player, const GbLevelAssets* level);
u8 gb_player_try_level10_boundary(GbPlayer* player, u8 current_level);
u8 gb_player_frame_index(const GbPlayer* player);

#endif
