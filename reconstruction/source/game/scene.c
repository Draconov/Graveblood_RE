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


void gb_scene_request_gameplay(GbSceneRuntime *scene, u8 level, u16 delay)
{
    if(! scene || scene->pending_gameplay)
    {
        return;
    }
    scene->pending_gameplay = 1;
    scene->pending_level = level;
    scene->transition_delay = delay;
}

GbSceneTick gb_scene_update_pending(GbSceneRuntime *scene)
{
    GbSceneTick tick = {0, 0, 0, 0};
    if(! scene || ! scene->pending_gameplay)
    {
        return tick;
    }

    if(scene->transition_delay > 0)
    {
        --scene->transition_delay;
        return tick;
    }

    scene->active = GB_SCENE_GAMEPLAY;
    scene->pending_gameplay = 0;
    tick.enter_gameplay = 1;
    tick.gameplay_level = scene->pending_level;
    return tick;
}

GbSceneTick gb_scene_update_title(GbSceneRuntime *scene, const GbInput *input)
{
    GbSceneTick tick = {0, 0, 0, 0};

    if(scene->pending_gameplay)
    {
        GbSceneTick pending = gb_scene_update_pending(scene);
        if(pending.enter_gameplay)
        {
            return pending;
        }
    }

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
        gb_scene_request_gameplay(scene, GB_TITLE_START_LEVEL, GB_TITLE_TRANSITION_DELAY);
    }

    return tick;
}
