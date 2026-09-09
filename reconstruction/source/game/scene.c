#include <graveblood/scene.h>

#define GB_TITLE_START_KEY 0x0008u
#define GB_TITLE_START_LEVEL 7u
#define GB_TITLE_TRANSITION_DELAY 120u

void gb_scene_init(GbSceneRuntime *scene)
{
    scene->active = GB_SCENE_TITLE;
    scene->title_animation_state = 0;
    scene->title_animation_counter = 0;
    scene->title_frame_counter = 0;
    scene->transition_delay = 0;
    scene->pending_gameplay = 0;
    scene->pending_level = 0;
}

GbSceneTick gb_scene_update_title(GbSceneRuntime *scene, const GbInput *input)
{
    GbSceneTick tick = {0, 0, 0, 0};

    if(scene->pending_gameplay && scene->transition_delay == 0)
    {
        scene->active = GB_SCENE_GAMEPLAY;
        tick.enter_gameplay = 1;
        tick.gameplay_level = scene->pending_level;
        return tick;
    }

    if(scene->pending_gameplay && scene->transition_delay > 0)
        --scene->transition_delay;

    if(scene->title_animation_counter <= 5)
    {
        ++scene->title_animation_counter;
    }
    else
    {
        scene->title_animation_counter = 0;
        if(scene->title_animation_state <= 2)
            ++scene->title_animation_state;
        else
            scene->title_animation_state = 0;
    }

    ++scene->title_frame_counter;
    tick.prompt_visible = (u8)((scene->title_frame_counter & 0x0010u) == 0u);

    if((input->pressed & GB_TITLE_START_KEY) != 0)
    {
        tick.play_start_sfx = 1;
        if(!scene->pending_gameplay)
        {
            scene->pending_gameplay = 1;
            scene->pending_level = GB_TITLE_START_LEVEL;
            scene->transition_delay = GB_TITLE_TRANSITION_DELAY;
        }
    }

    return tick;
}
