#ifndef GRAVEBLOOD_INPUT_H
#define GRAVEBLOOD_INPUT_H

#include <gba.h>

typedef struct {
    u16 held;
    u16 pressed;
} GbInput;

void gb_input_reset(void);
GbInput gb_input_poll(void);

#endif
