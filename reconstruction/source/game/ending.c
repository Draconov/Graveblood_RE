#include <graveblood/assets.h>
#include <graveblood/ending.h>

void gb_ending_apply_argument0(volatile u8* vram)
{
    /*
     * The original 0x08010C54 helper selects its byte-copy path for copy 1
     * because the canonical source address (0x08641361) is unaligned.  GBA
     * VRAM is a 16-bit bus: an 8-bit CPU store is mirrored across the
     * addressed halfword.  Sequential byte stores therefore leave the odd
     * source byte replicated into both bytes of each destination halfword.
     * Express the final hardware result directly so host tests and GBA/mGBA
     * execute the same semantics instead of depending on the host RAM bus.
     */
    volatile u16* copy1_dst = (volatile u16*)vram;
    for(unsigned i = 0; i < GB_ENDING_ARG0_COPY1_BYTES; i += 2)
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
