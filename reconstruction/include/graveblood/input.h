#ifndef GRAVEBLOOD_INPUT_H
#define GRAVEBLOOD_INPUT_H

#include <gba.h>

enum {
    GB_INPUT_KEY_R = 1u << 8,
};

typedef struct {
    u16 held;
    u16 pressed;
} GbInput;

void gb_input_reset(void);
GbInput gb_input_poll(void);

#endif
