#include <graveblood/assets.h>
#include <graveblood/ending.h>

void gb_ending_apply_argument0(volatile u8* vram)
{
    _Static_assert(GB_ENDING_ARG0_COPY1_BYTES > GB_ENDING_OBJ_VRAM_OFFSET,
                   "ending copy 1 must reach OBJ VRAM");
    /*
     * The original 0x08010C54 helper selects its byte-copy path for copy 1
     * because the canonical source address (0x08641361) is unaligned.  In BG
     * VRAM, an 8-bit CPU store is mirrored across the addressed halfword, so
     * sequential byte stores leave the odd source byte replicated into both
     * bytes of each destination halfword.  OBJ VRAM starts at 0x06010000 and
     * ignores 8-bit CPU stores entirely.  Reproduce that bus-visible result
     * explicitly so host tests and GBA/mGBA agree.
     */
    volatile u16* copy1_dst = (volatile u16*)vram;
    for(unsigned i = 0; i < GB_ENDING_OBJ_VRAM_OFFSET; i += 2)
    {
        const u16 byte = gb_ending_arg0_copy1[i + 1];
        copy1_dst[i >> 1] = (u16)(byte | (u16)(byte << 8));
    }

    /* Copy 2 is aligned in the original helper and takes its wide-copy path. */
    volatile u32* copy2_dst = (volatile u32*)(vram + GB_ENDING_OBJ_VRAM_OFFSET);
    for(unsigned i = 0; i < GB_ENDING_ARG0_COPY2_BYTES; i += 4)
    {
        const u32 value =
            (u32)gb_ending_arg0_copy2[i] |
            ((u32)gb_ending_arg0_copy2[i + 1] << 8) |
            ((u32)gb_ending_arg0_copy2[i + 2] << 16) |
            ((u32)gb_ending_arg0_copy2[i + 3] << 24);
        copy2_dst[i >> 2] = value;
    }
}
