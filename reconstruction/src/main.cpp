#include "bn_bg_palettes.h"
#include "bn_color.h"
#include "bn_core.h"
#include "bn_keypad.h"

// Graveblood clean-room reconstruction development shell.
//
// This intentionally implements only build/runtime plumbing. Recovered game
// behavior is added here incrementally from the documented RE evidence; no
// original ROM bytes are linked into this project.
int main()
{
    bn::core::init();

    const bn::color reconstruction_green(2, 5, 3);
    const bn::color reconstruction_red(7, 2, 2);
    bool alternate_backdrop = false;

    bn::bg_palettes::set_transparent_color(reconstruction_green);

    while(true)
    {
        if(bn::keypad::a_pressed())
        {
            alternate_backdrop = ! alternate_backdrop;
            bn::bg_palettes::set_transparent_color(
                    alternate_backdrop ? reconstruction_red : reconstruction_green);
        }

        bn::core::update();
    }
}
