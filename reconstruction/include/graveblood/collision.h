#ifndef GRAVEBLOOD_COLLISION_H
#define GRAVEBLOOD_COLLISION_H

#include <stdbool.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>

bool gb_collision_point_walkable(const GbLevelAssets* level, s16 x, s16 y);
bool gb_collision_can_stand(const GbLevelAssets* level, s16 x, s16 y);
void gb_collision_apply_fixed_motion(const GbLevelAssets* level,
                                     s32* x_fixed, s32* y_fixed,
                                     s32* request_x_fixed, s32* request_y_fixed,
                                     s32 width_fixed, s32 height_fixed,
                                     u16* collision_status);
void gb_collision_apply_player_motion(const GbLevelAssets* level, GbPlayer* player);

#endif
