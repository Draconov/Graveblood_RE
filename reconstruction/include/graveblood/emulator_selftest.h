#ifndef GRAVEBLOOD_EMULATOR_SELFTEST_H
#define GRAVEBLOOD_EMULATOR_SELFTEST_H

#include <gba.h>

#if defined(GB_EMULATOR_SELFTEST) || defined(GB_DEVICE_SELFTEST)

enum {
    GB_SELFTEST_REPORT_ADDRESS = 0x0203F000,
    GB_SELFTEST_MAGIC = 0x54534247,
    GB_SELFTEST_COMPLETE = 0xC0DEF00D,
    GB_SELFTEST_VERSION = 2,

    GB_SELFTEST_OAM = 0x01,
    GB_SELFTEST_VBLANK = 0x02,
    GB_SELFTEST_LEVEL9_BOUNDARY = 0x04,
    GB_SELFTEST_LEVEL10_ENTRANCE = 0x08,
    GB_SELFTEST_LEAVES = 0x10,
    GB_SELFTEST_ENDING = 0x20,
    GB_SELFTEST_AUDIO_IRQ = 0x40,
    GB_SELFTEST_EXPECTED_MASK = 0x7F,
};

typedef struct {
    u32 magic;
    u32 version;
    u32 expected_mask;
    u32 pass_mask;
    u32 fail_mask;
    u32 complete;
    u32 player_oam_attr2;
    u32 npc_oam_attr2;
    u32 boundary_mode;
    u32 scene_level;
    u32 entrance_mode;
    s32 entrance_x;
    s32 entrance_y;
    u32 leaf_count;
    s32 leaf_x;
    s32 leaf_y;
    u32 ending_guard;
    u32 audio_irq_count;
    u32 audio_setup_ok;
    u32 audio_ie;
    u32 audio_ime;
    u32 vblank_vcount;
    u32 ppu_probe_coords;
    u32 ppu_probe_colors;
} GbEmulatorSelftestReport;

void gb_emulator_selftest_run(void);
void gb_device_selftest_run(void);

#endif

#endif
