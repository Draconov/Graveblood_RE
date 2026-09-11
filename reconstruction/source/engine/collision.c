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

/* The original 0x08004670 solver works directly in 24.8 fixed-point and
   samples an 8-pixel collision grid.  This routine is intentionally built
   up from ROM-proven branches; unsupported higher-level Player modes stay
   outside this low-level solver. */
static bool gb_collision_cell_in_bounds(const GbLevelAssets* level, s32 tx, s32 ty)
{
    return level && level->collision && tx >= 0 && ty >= 0 &&
           tx < level->world_width_tiles && ty < level->world_height_tiles;
}

static u16 gb_collision_cell(const GbLevelAssets* level, s32 tx, s32 ty)
{
    if(! gb_collision_cell_in_bounds(level, tx, ty))
    {
        return 0xFFFFu;
    }
    return level->collision[ty * level->world_width_tiles + tx];
}

static bool gb_collision_cell_solid(const GbLevelAssets* level, s32 tx, s32 ty)
{
    return gb_collision_cell(level, tx, ty) != 0;
}

static void gb_player_sync_pixel_anchor(GbPlayer* player)
{
    player->x = (s16)(player->x_fixed >> 8);
    player->y = (s16)(player->y_fixed >> 8);
}

void gb_collision_apply_fixed_motion(const GbLevelAssets* level,
                                     s32* x_fixed, s32* y_fixed,
                                     s32* request_x_fixed, s32* request_y_fixed,
                                     s32 width, s32 height,
                                     u16* collision_status)
{
    if(! level || ! level->collision || ! x_fixed || ! y_fixed ||
       ! request_x_fixed || ! request_y_fixed || ! collision_status)
    {
        return;
    }

    s32 dx = *request_x_fixed;
    s32 dy = *request_y_fixed;
    *collision_status = 0;

    /* 0x08004684..0x08004A42 resolves X first.  A horizontal request is
       cancelled only by an out-of-range mid-body probe or collision value
       14.  Top/bottom probes are corner-correction geometry: they can move Y
       by exactly one pixel but do not themselves cancel the primary X axis. */
    if(dx != 0)
    {
        const bool right = dx > 0;
        const s32 target_tx = right ?
            (*x_fixed + width - 1 + dx) >> 11 :
            (*x_fixed + dx) >> 11;
        const s32 mid_ty = (*y_fixed - (height >> 1) + 0x100) >> 11;
        const s32 top_ty = (*y_fixed - height + 1) >> 11;
        const s32 bottom_ty = *y_fixed >> 11;
        s32 probe_tx = target_tx;

        if(! gb_collision_cell_in_bounds(level, target_tx, mid_ty) ||
           gb_collision_cell(level, target_tx, mid_ty) == 14)
        {
            dx = 0;
            *request_x_fixed = 0;
            *collision_status = right ? 7 : 11;
            probe_tx = right ?
                (*x_fixed + width - 1) >> 11 :
                *x_fixed >> 11;
        }

        if(gb_collision_cell_solid(level, probe_tx, top_ty))
        {
            if(dy == 0)
            {
                *y_fixed += 0x100;
                const s32 validation_ty = *y_fixed >> 11;
                if(! gb_collision_cell_in_bounds(level, probe_tx, validation_ty) ||
                   gb_collision_cell_solid(level, probe_tx, validation_ty))
                {
                    *y_fixed -= 0x100;
                }
            }
        }
        else if(gb_collision_cell_solid(level, probe_tx, bottom_ty))
        {
            if(dy == 0)
            {
                *y_fixed -= 0x100;
            }
        }

        *x_fixed += dx;
    }

    /* The Y phase always runs after X.  Even when the center probe blocks and
       zeros requested Y, the original continues through its side-corner
       correction phase before committing the (possibly zero) Y component. */
    if(dy > 0)
    {
        const s32 target_ty = (*y_fixed + dy) >> 11;
        const s32 center_tx = (*x_fixed + (width >> 1)) >> 11;
        if(gb_collision_cell_solid(level, center_tx, target_ty))
        {
            dy = 0;
            *request_y_fixed = 0;
            *collision_status |= 0x31;
        }

        const s32 corner_ty = *y_fixed >> 11;
        const s32 right_tx = (*x_fixed + width - 1) >> 11;
        const s32 left_tx = *x_fixed >> 11;
        if(gb_collision_cell_solid(level, right_tx, corner_ty))
        {
            if(*request_x_fixed == 0)
            {
                *x_fixed -= 0x100;
                const s32 validation_tx = *x_fixed >> 11;
                if(! gb_collision_cell_in_bounds(level, validation_tx, corner_ty) ||
                   gb_collision_cell_solid(level, validation_tx, corner_ty))
                {
                    *x_fixed += 0x100;
                }
            }
        }
        else if(gb_collision_cell_solid(level, left_tx, corner_ty) &&
                *request_x_fixed == 0)
        {
            *x_fixed += 0x100;
        }

        *y_fixed += dy;
    }
    else if(dy < 0)
    {
        /* 0x080048C0..0x08004916: the destination center probe includes the
           request, while side-corner probes use the pre-motion top edge. */
        const s32 target_ty = (*y_fixed - height - dy - 0x1FF) >> 11;
        const s32 center_tx = (*x_fixed + (width >> 1)) >> 11;
        if(gb_collision_cell_solid(level, center_tx, target_ty))
        {
            dy = 0;
            *request_y_fixed = 0;
            *collision_status |= 0x51;
        }

        const s32 corner_ty = (*y_fixed - height - 0x1FF) >> 11;
        const s32 right_tx = (*x_fixed + width - 1) >> 11;
        const s32 left_tx = *x_fixed >> 11;
        if(gb_collision_cell_solid(level, right_tx, corner_ty))
        {
            if(*request_x_fixed == 0)
            {
                *x_fixed -= 0x100;
                const s32 validation_tx = *x_fixed >> 11;
                if(! gb_collision_cell_in_bounds(level, validation_tx, corner_ty) ||
                   gb_collision_cell_solid(level, validation_tx, corner_ty))
                {
                    *x_fixed += 0x100;
                }
            }
        }
        else if(gb_collision_cell_solid(level, left_tx, corner_ty) &&
                *request_x_fixed == 0)
        {
            *x_fixed += 0x100;
        }

        *y_fixed += dy;
    }
}

void gb_collision_apply_player_motion(const GbLevelAssets* level, GbPlayer* player)
{
    if(! level || ! player || ! level->collision)
    {
        return;
    }
    gb_collision_apply_fixed_motion(level,
                                    &player->x_fixed, &player->y_fixed,
                                    &player->request_x_fixed, &player->request_y_fixed,
                                    player->collision_width_fixed,
                                    player->collision_height_fixed,
                                    &player->collision_status);
    gb_player_sync_pixel_anchor(player);
}
