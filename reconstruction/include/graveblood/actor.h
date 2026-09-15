#ifndef GRAVEBLOOD_ACTOR_H
#define GRAVEBLOOD_ACTOR_H

#include <gba.h>
#include <graveblood/assets.h>
#include <graveblood/input.h>

enum {
    GB_PLAYER_ANIM_WALK_REGULAR = 2,
    GB_PLAYER_ANIM_WALK_UP = 7,
    GB_PLAYER_ANIM_IDLE = 8,
};

typedef struct {
    u16 volume;
    u8 set_volume;
    u8 replace_music;
    u8 selector;
} GbPlayerMusicAction;

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
    /* Shared ROM state 0x030005F4. Value 2 is the recovered bicycle-riding
       mode entered by the Level-9 treetype-20 interaction. The ROM also
       retains dormant value-1 draw/update consumers, but static writer
       closure proves no normal public-demo boot can create value 1. This
       state is separate from script_mode and value 2 survives the 9->10 load. */
    u8 bicycle_mode;
    /* Original Player+0x1CC/+0x1D0 plus global fade counter +0x68.
       Fgtile turn=2 controllers mutate desired; Player_update fades the
       reserved music channel until desired becomes applied. */
    u8 music_selector_desired;
    u8 music_selector_applied;
    u8 music_fade_counter;
    s8 pending_sfx_id;
    u16 pending_sfx_volume;
    s8 facing_x;
    s8 facing_y;
    u8 facing_right;
    /* Original Player+0x1E0. Gameplay-scene activation copies the current
       LevelRecord+0x3C value here before the first active draw/update. */
    u8 idle_selector;
    u8 animation_state;
    u8 animation_frame;
    u8 animation_countdown;
    /* Original Player+0x1C0 contact advertisement consumed by Player_draw. */
    u8 interaction_available;
    /* Original Player+0xF0 indexes the 32-entry vertical prompt bob table. */
    u8 prompt_bob_phase;
} GbPlayer;

void gb_player_spawn(GbPlayer* player, s16 x, s16 y);
void gb_player_music_reset(GbPlayer* player, u8 selector);
GbPlayerMusicAction gb_player_music_tick(GbPlayer* player);
void gb_player_queue_vertical_target(GbPlayer* player, s16 target_y);
void gb_player_queue_social_alignment(GbPlayer* player, s16 anchor_x, s16 anchor_y);
void gb_player_resolve_queued_motion(GbPlayer* player, const GbLevelAssets* level);
u8 gb_player_try_level10_boundary(GbPlayer* player, u8 current_level);
void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);
int gb_player_take_pending_sfx(GbPlayer* player, u16* volume);
u8 gb_player_frame_index(const GbPlayer* player);

#endif
