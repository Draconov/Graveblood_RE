#include <graveblood/portal.h>

int gb_portal_try_activate(const GbLevelAssets* level, const GbPlayer* player, const GbInput* input)
{
    if(! level || ! player || ! input || ! (input->pressed & KEY_A))
    {
        return -1;
    }

    for(u8 i = 0; i < level->portal_count; ++i)
    {
        const GbPortal* portal = &level->portals[i];
        if(player->x >= portal->x && player->x < portal->x + portal->width &&
           player->y >= portal->y && player->y < portal->y + portal->height)
        {
            return portal->target_level;
        }
    }

    return -1;
}
