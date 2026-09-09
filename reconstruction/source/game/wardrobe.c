#include <graveblood/wardrobe.h>
void gb_wardrobe_init(GbWardrobeRuntime* wardrobe)
{
    if(wardrobe) wardrobe->selector = 0;
}
GbWardrobeTick gb_wardrobe_update(GbWardrobeRuntime* wardrobe, const GbInput* input)
{
    GbWardrobeTick tick = {0,0,7};
    if(! wardrobe || ! input) return tick;
    if((input->pressed & KEY_LEFT) && wardrobe->selector > 0) {
        --wardrobe->selector; tick.selector_changed = 1;
    } else if((input->pressed & KEY_RIGHT) && wardrobe->selector < 6) {
        ++wardrobe->selector; tick.selector_changed = 1;
    }
    if(input->pressed & KEY_B) tick.exit_gameplay = 1;
    return tick;
}
