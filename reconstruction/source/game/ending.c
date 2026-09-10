#include <graveblood/assets.h>
#include <graveblood/ending.h>

void gb_ending_apply_argument0(volatile u8* vram)
{
    for(unsigned i = 0; i < GB_ENDING_ARG0_COPY1_BYTES; ++i)
    {
        vram[i] = gb_ending_arg0_copy1[i];
    }

    for(unsigned i = 0; i < GB_ENDING_ARG0_COPY2_BYTES; ++i)
    {
        vram[GB_ENDING_OBJ_VRAM_OFFSET + i] = gb_ending_arg0_copy2[i];
    }
}
