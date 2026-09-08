#include <graveblood/input.h>

static u16 gb_previous_keys;

void gb_input_reset(void)
{
    gb_previous_keys = 0;
}

GbInput gb_input_poll(void)
{
    const u16 held = (u16)((~REG_KEYINPUT) & 0x03FF);
    GbInput input;
    input.held = held;
    input.pressed = (u16)(held & (u16)~gb_previous_keys);
    gb_previous_keys = held;
    return input;
}
