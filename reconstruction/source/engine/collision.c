#include <graveblood/collision.h>

bool gb_collision_point_walkable(const GbLevelAssets* level, s16 x, s16 y)
{
    if(! level || x < 0 || y < 0)
    {
        return false;
    }

    const int tx = x >> 3;
    const int ty = y >> 3;
    if(tx < 0 || ty < 0 || tx >= level->world_width_tiles || ty >= level->world_height_tiles)
    {
        return false;
    }

    return level->collision[ty * level->world_width_tiles + tx] == 0;
}

bool gb_collision_can_stand(const GbLevelAssets* level, s16 x, s16 y)
{
    // The recovered Player coordinates behave as a bottom/foot anchor. Keep
    // collision compact around the feet instead of testing the 16x32 artwork.
    return gb_collision_point_walkable(level, (s16)(x - 5), (s16)(y - 4)) &&
           gb_collision_point_walkable(level, (s16)(x + 5), (s16)(y - 4)) &&
           gb_collision_point_walkable(level, (s16)(x - 5), y) &&
           gb_collision_point_walkable(level, (s16)(x + 5), y);
}
