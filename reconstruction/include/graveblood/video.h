#ifndef GRAVEBLOOD_VIDEO_H
#define GRAVEBLOOD_VIDEO_H

#include <graveblood/actor.h>
#include <graveblood/assets.h>

void gb_video_init(void);
void gb_video_wait_vblank(void);
void gb_video_load_level(const GbLevelAssets* level);
void gb_video_set_camera(s16 x, s16 y);
void gb_video_draw_player(const GbPlayer* player, s16 camera_x, s16 camera_y);

#endif
