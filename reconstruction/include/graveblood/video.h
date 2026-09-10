#ifndef GRAVEBLOOD_VIDEO_H
#define GRAVEBLOOD_VIDEO_H

#include <graveblood/actor.h>
#include <graveblood/actors.h>
#include <graveblood/assets.h>
#include <graveblood/pda.h>
#include <graveblood/story.h>

void gb_video_init(void);
void gb_video_wait_vblank(void);
void gb_video_apply_final_effect(void);
void gb_video_load_title(void);
void gb_video_title_set_animation(u8 state);
void gb_video_title_set_prompt_visible(int visible);
void gb_video_load_wardrobe(void);
void gb_video_load_pda(const GbLevelAssets* level, const GbPdaRuntime* pda, const GbStoryRuntime* story);
void gb_video_draw_pda(const GbPdaRuntime* pda, const GbStoryRuntime* story);
void gb_video_draw_wardrobe(u8 selector);
void gb_video_load_level(const GbLevelAssets* level);
void gb_video_stream_full(const GbLevelAssets* level, s16 left, s16 top);
void gb_video_stream_column(const GbLevelAssets* level, s16 world_x, s16 top);
void gb_video_stream_row(const GbLevelAssets* level, s16 left, s16 world_y);
void gb_video_set_camera(s16 x, s16 y);
void gb_video_draw_actors(GbActorSystem* system, const GbPlayer* player, s16 camera_x, s16 camera_y);
void gb_video_draw_player(const GbPlayer* player, s16 camera_x, s16 camera_y);
void gb_video_clear_story_ui(void);
void gb_video_draw_story_ui(const GbStoryRuntime* story);
void gb_video_draw_message(const GbMessageRecord* message);
void gb_video_draw_player_state(const GbPlayer* player, const GbStoryRuntime* story,
                                s16 camera_x, s16 camera_y);

#endif
