#include <graveblood/portal.h>
#include <graveblood/audio.h>

static u8 gb_portal_pre_player_count(const GbLevelAssets* level)
{
    if(! level)
    {
        return 0;
    }

    /* Direct actor-stream ordinals: Level 1 has generic portal Fgtiles at
       indices 0/1 before Player index 2; Level 8 has four generic portals at
       indices 0..3 before Player index 4.  Every other generic portal is
       post-Player.  Generated portal arrays retain canonical actor order. */
    if(level->level_id == 1)
    {
        return 2;
    }
    if(level->level_id == 8)
    {
        return 4;
    }
    return 0;
}

static int gb_portal_try_activate_range(const GbLevelAssets* level,
                                        GbPlayer* player,
                                        const GbInput* input,
                                        u8 begin, u8 end)
{
    if(! level || ! player || ! input)
    {
        return -1;
    }

    if(end > level->portal_count)
    {
        end = level->portal_count;
    }
    for(u8 i = begin; i < end; ++i)
    {
        const GbPortal* portal = &level->portals[i];
        if(player->x >= portal->x && player->x < portal->x + portal->width &&
           player->y >= portal->y && player->y < portal->y + portal->height)
        {
            player->interaction_available = 1;
            if(input->pressed & KEY_A)
            {
                gb_audio_play_sfx(5);
                return portal->target_level;
            }
        }
    }

    return -1;
}


int gb_portal_try_activate_physical_index(const GbLevelAssets* level, GbPlayer* player,
                                          const GbInput* input, u8 physical_index)
{
    if(! level)
    {
        return -1;
    }
    for(u8 i = 0; i < level->portal_count; ++i)
    {
        if(level->portals[i].physical_index == physical_index)
        {
            return gb_portal_try_activate_range(level, player, input, i, (u8)(i + 1));
        }
    }
    return -1;
}

int gb_portal_try_activate_phase(const GbLevelAssets* level, GbPlayer* player,
                                 const GbInput* input, GbPortalPhase phase)
{
    if(! level)
    {
        return -1;
    }
    const u8 split = gb_portal_pre_player_count(level);
    if(phase == GB_PORTAL_PHASE_PRE_PLAYER)
    {
        return gb_portal_try_activate_range(level, player, input, 0, split);
    }
    return gb_portal_try_activate_range(level, player, input, split, level->portal_count);
}

int gb_portal_try_activate(const GbLevelAssets* level, GbPlayer* player, const GbInput* input)
{
    if(! level)
    {
        return -1;
    }
    return gb_portal_try_activate_range(level, player, input, 0, level->portal_count);
}
