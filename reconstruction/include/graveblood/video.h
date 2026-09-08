#ifndef GRAVEBLOOD_VIDEO_H
#define GRAVEBLOOD_VIDEO_H

#include <graveblood/actor.h>
#include <graveblood/actors.h>
#include <graveblood/assets.h>

void gb_video_init(void);
void gb_video_wait_vblank(void);
void gb_video_load_level(const GbLevelAssets* level);
void gb_video_stream_full(const GbLevelAssets* level, s16 left, s16 top);
void gb_video_stream_column(const GbLevelAssets* level, s16 world_x, s16 top);
void gb_video_stream_row(const GbLevelAssets* level, s16 left, s16 world_y);
void gb_video_set_camera(s16 x, s16 y);
void gb_video_draw_actors(const GbActorSystem* system, s16 camera_x, s16 camera_y);
void gb_video_draw_player(const GbPlayer* player, s16 camera_x, s16 camera_y);

#endif
