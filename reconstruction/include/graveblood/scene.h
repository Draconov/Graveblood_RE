#ifndef GRAVEBLOOD_SCENE_H
#define GRAVEBLOOD_SCENE_H

#include <gba.h>
#include <graveblood/input.h>

typedef enum {
    GB_SCENE_TITLE = 0,
    GB_SCENE_GAMEPLAY = 1,
    GB_SCENE_WARDROBE = 2
} GbSceneKind;

typedef struct {
    GbSceneKind active;
    u8 title_animation_state;
    u8 title_animation_counter;
    u16 title_frame_counter;
    u16 transition_delay;
    u8 pending_gameplay;
    u8 pending_level;
} GbSceneRuntime;

typedef struct {
    u8 prompt_visible;
    u8 play_start_sfx;
    u8 enter_gameplay;
    u8 gameplay_level;
} GbSceneTick;

void gb_scene_init(GbSceneRuntime *scene);
GbSceneTick gb_scene_update_title(GbSceneRuntime *scene, const GbInput *input);

#endif
