#ifndef GRAVEBLOOD_PORTAL_H
#define GRAVEBLOOD_PORTAL_H

#include <graveblood/actor.h>
#include <graveblood/assets.h>
#include <graveblood/input.h>

typedef enum {
    GB_PORTAL_PHASE_PRE_PLAYER = 0,
    GB_PORTAL_PHASE_POST_PLAYER = 1,
} GbPortalPhase;

int gb_portal_try_activate(const GbLevelAssets* level, GbPlayer* player, const GbInput* input);
int gb_portal_try_activate_physical_index(const GbLevelAssets* level, GbPlayer* player,
                                          const GbInput* input, u8 physical_index);
int gb_portal_try_activate_phase(const GbLevelAssets* level, GbPlayer* player,
                                 const GbInput* input, GbPortalPhase phase);

#endif
