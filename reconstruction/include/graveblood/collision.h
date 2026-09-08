#ifndef GRAVEBLOOD_COLLISION_H
#define GRAVEBLOOD_COLLISION_H

#include <stdbool.h>
#include <graveblood/actor.h>
#include <graveblood/assets.h>

bool gb_collision_point_walkable(const GbLevelAssets* level, s16 x, s16 y);
bool gb_collision_can_stand(const GbLevelAssets* level, s16 x, s16 y);

#endif
