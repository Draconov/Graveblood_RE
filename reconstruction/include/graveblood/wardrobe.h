#ifndef GRAVEBLOOD_WARDROBE_H
#define GRAVEBLOOD_WARDROBE_H
#include <gba.h>
#include <graveblood/input.h>
typedef struct { u8 selector; } GbWardrobeRuntime;
typedef struct { u8 selector_changed; u8 exit_gameplay; u8 gameplay_level; } GbWardrobeTick;
void gb_wardrobe_init(GbWardrobeRuntime* wardrobe);
GbWardrobeTick gb_wardrobe_update(GbWardrobeRuntime* wardrobe, const GbInput* input);
#endif
