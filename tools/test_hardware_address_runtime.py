#!/usr/bin/env python3
"""Hardware-address validation for the clean-room GBA runtime.

These tests are intentionally Linux-hosted rather than emulator-backed: each C harness
maps the literal GBA MMIO/VRAM/OAM address ranges into its own process, then runs the
production source against those addresses.  This catches address, width, ordering and
boundary mistakes that array-backed unit fakes can hide.  True mGBA/hardware validation
remains a separate release gate when those tools are available.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "reconstruction"
INCLUDE = RECON / "include"

GBA_FIXED_ADDRESS_HEADER = r"""
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
typedef struct { volatile u16 x; volatile u16 y; } GbTestBgOffset;
#define REG_VCOUNT (*(volatile u16*)0x04000006u)
#define REG_DISPCNT (*(volatile u16*)0x04000000u)
#define REG_KEYINPUT (*(volatile u16*)0x04000130u)
#define BGCTRL ((volatile u16*)0x04000008u)
#define BG_OFFSET ((volatile GbTestBgOffset*)0x04000010u)
#define BG_COLORS ((volatile u16*)0x05000000u)
#define OBJ_COLORS ((volatile u16*)0x05000200u)
#define OAM ((volatile u16*)0x07000000u)
#define MAP_BASE_ADR(n) ((void*)(uintptr_t)(0x06000000u + (unsigned)(n) * 0x800u))
#define CHAR_BASE_ADR(n) ((void*)(uintptr_t)(0x06000000u + (unsigned)(n) * 0x4000u))
#define SPR_VRAM(n) ((void*)(uintptr_t)(0x06010000u + (unsigned)(n) * 32u))
#define MODE_0 0u
#define BG0_ON (1u << 8)
#define BG1_ON (1u << 9)
#define BG2_ON (1u << 10)
#define BG3_ON (1u << 11)
#define OBJ_ON (1u << 12)
#define OBJ_1D_MAP (1u << 6)
#define BG_SIZE_0 0u
#define BG_256_COLOR (1u << 7)
#define CHAR_BASE(n) ((u16)((n) << 2))
#define SCREEN_BASE(n) ((u16)((n) << 8))
#define BG_PRIORITY(n) ((u16)(n))
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_SELECT (1u << 2)
#define KEY_START (1u << 3)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#define KEY_R (1u << 8)
#define KEY_L (1u << 9)
#define IRQ_TIMER1 0x10u
void irqInit(void);
void irqSet(u32 irq, void (*fn)(void));
void irqEnable(u32 irq);
void irqDisable(u32 irq);
#endif
"""

GBA_ARM_COMPILE_HEADER = r"""
#ifndef GBA_H
#define GBA_H
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned int u32;
typedef signed int s32;
typedef struct { volatile u16 x; volatile u16 y; } GbTestBgOffset;
#define REG_VCOUNT (*(volatile u16*)0x04000006u)
#define REG_DISPCNT (*(volatile u16*)0x04000000u)
#define REG_KEYINPUT (*(volatile u16*)0x04000130u)
#define BGCTRL ((volatile u16*)0x04000008u)
#define BG_OFFSET ((volatile GbTestBgOffset*)0x04000010u)
#define BG_COLORS ((volatile u16*)0x05000000u)
#define OBJ_COLORS ((volatile u16*)0x05000200u)
#define OAM ((volatile u16*)0x07000000u)
#define MAP_BASE_ADR(n) ((void*)(0x06000000u + (unsigned)(n) * 0x800u))
#define CHAR_BASE_ADR(n) ((void*)(0x06000000u + (unsigned)(n) * 0x4000u))
#define SPR_VRAM(n) ((void*)(0x06010000u + (unsigned)(n) * 32u))
#define MODE_0 0u
#define BG0_ON (1u << 8)
#define BG1_ON (1u << 9)
#define BG2_ON (1u << 10)
#define BG3_ON (1u << 11)
#define OBJ_ON (1u << 12)
#define OBJ_1D_MAP (1u << 6)
#define BG_SIZE_0 0u
#define BG_256_COLOR (1u << 7)
#define CHAR_BASE(n) ((u16)((n) << 2))
#define SCREEN_BASE(n) ((u16)((n) << 8))
#define BG_PRIORITY(n) ((u16)(n))
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_SELECT (1u << 2)
#define KEY_START (1u << 3)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#define KEY_R (1u << 8)
#define KEY_L (1u << 9)
#define IRQ_TIMER1 0x10u
void irqInit(void);
void irqSet(u32 irq, void (*fn)(void));
void irqEnable(u32 irq);
void irqDisable(u32 irq);
#endif
"""


class HardwareValidationWiringTests(unittest.TestCase):
    def test_workflow_runs_hardware_validation_without_publishing_artifacts(self):
        workflow = (ROOT / ".github/workflows/build-release-rom.yml").read_text(encoding="utf-8")
        self.assertIn("tools.test_hardware_address_runtime", workflow)
        self.assertNotIn("hardware-address-validation:", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("path: reconstruction/Graveblood_RE.gba", workflow)
        self.assertTrue((ROOT / "tools/test_hardware_address_runtime.py").is_file())


@unittest.skipUnless(sys.platform.startswith("linux"), "literal GBA mmap validation requires Linux")
class HardwareAddressRuntimeTests(unittest.TestCase):
    def compile_and_run(self, name: str, harness: str, sources: list[Path], *, pthread: bool = False) -> None:
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / "gba.h").write_text(GBA_FIXED_ADDRESS_HEADER, encoding="utf-8")
            harness_path = td / f"{name}.c"
            harness_path.write_text(harness, encoding="utf-8")
            exe = td / name
            command = [
                "cc", "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror",
                "-ffunction-sections", "-fdata-sections",
                "-I", str(td), "-I", str(INCLUDE),
                *(str(source) for source in sources), str(harness_path),
                "-Wl,--gc-sections", "-o", str(exe),
            ]
            if pthread:
                command.insert(-2, "-pthread")
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            proc = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)

    def test_input_poll_uses_literal_active_low_key_register(self):
        harness = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <sys/mman.h>
#include <graveblood/input.h>

int main(void)
{
    void* mapped = mmap((void*)0x04000000u, 0x2000, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(mapped == (void*)0x04000000u);

    REG_KEYINPUT = 0x03FF;
    gb_input_reset();
    GbInput input = gb_input_poll();
    assert(input.held == 0 && input.pressed == 0);

    REG_KEYINPUT = (u16)(0x03FFu & ~KEY_A);
    input = gb_input_poll();
    assert(input.held == KEY_A && input.pressed == KEY_A);
    input = gb_input_poll();
    assert(input.held == KEY_A && input.pressed == 0);

    REG_KEYINPUT = (u16)(0x03FFu & ~(KEY_A | KEY_RIGHT));
    input = gb_input_poll();
    assert(input.held == (KEY_A | KEY_RIGHT));
    assert(input.pressed == KEY_RIGHT);
    return 0;
}
"""
        self.compile_and_run(
            "mapped_input",
            harness,
            [RECON / "source/engine/input.c"],
        )

    def test_audio_init_shutdown_program_literal_fifo_dma_timer_registers(self):
        harness = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <sys/mman.h>
#include <graveblood/audio.h>

static unsigned init_count;
static unsigned set_count;
static unsigned enable_count;
static unsigned disable_count;
static u32 last_irq;
static void (*last_handler)(void);

void irqInit(void) { ++init_count; }
void irqSet(u32 irq, void (*fn)(void)) { ++set_count; last_irq = irq; last_handler = fn; }
void irqEnable(u32 irq) { ++enable_count; last_irq = irq; }
void irqDisable(u32 irq) { ++disable_count; last_irq = irq; }

int main(void)
{
    void* mapped = mmap((void*)0x04000000u, 0x2000, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(mapped == (void*)0x04000000u);

    gb_audio_init();
    assert(*(volatile u16*)0x04000084u == 0x0080);
    assert(*(volatile u16*)0x04000082u == 0x0B04);
    assert(*(volatile u32*)0x040000C0u == 0x040000A0u);
    assert(*(volatile u16*)0x040000C6u == 0xB200);
    assert(*(volatile u16*)0x04000100u == 0xFC00);
    assert(*(volatile u16*)0x04000104u == 0xFF00);
    assert(*(volatile u16*)0x04000102u == 0x0080);
    assert(*(volatile u16*)0x04000106u == 0x00C4);
    assert(init_count == 1 && set_count == 1 && enable_count == 1);
    assert(disable_count == 0 && last_irq == IRQ_TIMER1 && last_handler != 0);

    gb_audio_shutdown();
    assert(*(volatile u16*)0x04000102u == 0);
    assert(*(volatile u16*)0x04000106u == 0);
    assert(*(volatile u16*)0x040000C6u == 0);
    assert(*(volatile u16*)0x04000082u == 0);
    assert(*(volatile u16*)0x04000084u == 0);
    assert(disable_count == 1 && last_irq == IRQ_TIMER1);
    return 0;
}
"""
        self.compile_and_run(
            "mapped_audio",
            harness,
            [RECON / "source/engine/audio.c"],
        )

    def test_video_init_and_player_oam_use_literal_palette_vram_oam_registers(self):
        harness = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <string.h>
#include <sys/mman.h>
#include <graveblood/video.h>

const u16 gb_actor_obj_palette[GB_ACTOR_OBJ_PALETTE_COUNT] = { [0] = 0x1111, [90] = 0x2222 };
const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT] = { [0] = 0x3333, [31] = 0x4444 };
const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT] = {0};
const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * GB_PLAYER_FRAME_HALFWORDS] = {
    [3 * GB_PLAYER_FRAME_HALFWORDS] = 0x5555,
    [3 * GB_PLAYER_FRAME_HALFWORDS + 64] = 0x6666,
};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {
    [0] = 0x7777,
    [GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS - 1] = 0x8888,
};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {
    [0] = 0x9999,
    [GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS - 1] = 0xAAAA,
};
const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = {0};
const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {0};

u8 gb_player_frame_index(const GbPlayer* player)
{
    (void)player;
    return 3;
}

static void map_region(unsigned long address, unsigned long size)
{
    void* mapped = mmap((void*)address, size, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(mapped == (void*)address);
    memset(mapped, 0, size);
}

int main(void)
{
    map_region(0x04000000u, 0x2000);
    map_region(0x05000000u, 0x1000);
    map_region(0x06000000u, 0x18000);
    map_region(0x07000000u, 0x1000);

    gb_video_init();
    assert(REG_DISPCNT == (BG0_ON | BG1_ON | BG2_ON | BG3_ON | OBJ_ON));
    assert(BGCTRL[0] == (BG_256_COLOR | SCREEN_BASE(27) | BG_PRIORITY(0)));
    assert(BGCTRL[1] == (BG_256_COLOR | SCREEN_BASE(28) | BG_PRIORITY(1)));
    assert(BGCTRL[2] == (BG_256_COLOR | SCREEN_BASE(29) | BG_PRIORITY(2)));
    assert(BGCTRL[3] == (BG_256_COLOR | SCREEN_BASE(30) | BG_PRIORITY(3)));

    /* Normal level setup preserves the low OBJ palette and applies only
       the loader's fixed high-32 patch. */
    assert(OBJ_COLORS[0] == 0);
    assert(OBJ_COLORS[90] == 0);
    assert(OBJ_COLORS[224] == 0x3333);
    assert(OBJ_COLORS[255] == 0x4444);

    volatile u16* sprite_vram = (volatile u16*)0x06010000u;
    /* Special initial-bank composites are staged at their original 2D logical roots. */
    assert(sprite_vram[(0x159 * 64) / 2] == 0x7777);
    assert(sprite_vram[(0x17C * 64) / 2] == 0x9999);

    assert(OAM[0] == 160);
    assert(OAM[127 * 4] == 160);

    GbPlayer player = { 0 };
    player.x = 100;
    player.y = 80;
    player.facing_right = 1;
    gb_video_draw_player(&player, 10, 5);
    assert((OAM[0] & 0x00FF) == 59);
    assert((OAM[0] & (1u << 13)) != 0); /* original Player is 8bpp */
    assert((OAM[1] & 0x01FF) == 90);
    assert((OAM[1] & (1u << 12)) != 0);
    assert((OAM[2] & 0x03FF) == 0x100); /* logical 0x80 -> ATTR2 tile 0x100 */
    assert((OAM[2] & 0x0C00) == (2u << 10));
    assert((OAM[4] & 0x00FF) == 43);
    assert((OAM[4] & (1u << 13)) != 0);
    assert((OAM[6] & 0x03FF) == 0x0C0); /* logical 0x60 -> ATTR2 tile 0x0C0 */
    assert(sprite_vram[(0x060 * 64) / 2] == 0x5555);
    assert(sprite_vram[(0x070 * 64) / 2] == 0x6666);
    return 0;
}
"""
        self.compile_and_run(
            "mapped_video",
            harness,
            [RECON / "source/engine/video.c"],
        )


    def test_actor_grass_and_leaf_submission_use_literal_dynamic_obj_vram_and_oam(self):
        harness = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <string.h>
#include <sys/mman.h>
#include <graveblood/video.h>

const u16 gb_actor_obj_palette[GB_ACTOR_OBJ_PALETTE_COUNT] = {0};
const u16 gb_actor_obj_high_palette[GB_ACTOR_OBJ_HIGH_PALETTE_COUNT] = {0};
const u16 gb_actor_obj_lighting_source[GB_ACTOR_OBJ_LIGHTING_SOURCE_COUNT] = {0};
const u16 gb_player_obj_tiles[GB_PLAYER_FRAME_COUNT * GB_PLAYER_FRAME_HALFWORDS] = {0};
const u16 gb_monster_obj_frames[GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS] = {0};
const u16 gb_level_static_obj_tiles[GB_LEVEL_STATIC_SPRITE_COUNT * GB_LEVEL_STATIC_SPRITE_HALFWORDS] = {0};
const GbActorVisualSpec gb_actor_visuals[GB_ACTOR_VISUAL_COUNT] = { { 24, 0 } };
const u16 gb_actor_obj_frames[GB_ACTOR_VISUAL_COUNT * GB_ACTOR_MAX_FRAMES * GB_ACTOR_FRAME_HALFWORDS] = {
    [0] = 0x1234,
};
const u16 gb_grass_obj_tiles[GB_GRASS_OBJ_HALFWORDS] = { [0] = 0x2345 };
const u16 gb_leaf_obj_frames[GB_LEAF_FRAME_COUNT * GB_LEAF_FRAME_HALFWORDS] = {
    [2 * GB_LEAF_FRAME_HALFWORDS] = 0x3456,
};

int main(void)
{
    void* mmio = mmap((void*)0x04000000u, 0x2000, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    void* palette = mmap((void*)0x05000000u, 0x1000, PROT_READ | PROT_WRITE,
                         MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(mmio == (void*)0x04000000u && palette == (void*)0x05000000u);
    void* vram = mmap((void*)0x06000000u, 0x18000, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    void* oam = mmap((void*)0x07000000u, 0x1000, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(vram == (void*)0x06000000u && oam == (void*)0x07000000u);
    memset(vram, 0, 0x18000);
    memset(oam, 0, 0x1000);
    gb_video_init();

    GbActorDescriptor npc = { 0 };
    npc.actor_class = GB_ACTOR_NPC;
    npc.legs_color = 24;
    npc.num = 1;
    npc.setglobal = 0;

    GbActorDescriptor grass = { 0 };
    grass.actor_class = GB_ACTOR_GRASS;
    grass.legs_color = 24;
    grass.turn = 1;

    GbActorSystem system = { 0 };
    system.count = 2;
    system.actors[0].descriptor = &npc;
    system.actors[0].fixed_x = 100 << 8;
    system.actors[0].fixed_y = 80 << 8;
    system.actors[0].visual_legs_color = 24;
    system.actors[0].frame = 1;
    system.actors[0].frame_countdown = 1;
    system.actors[0].animation_frame_count = 1;
    system.actors[0].facing_right = 1;
    system.actors[0].active = 1;

    system.actors[1].descriptor = &grass;
    system.actors[1].fixed_x = 130 << 8;
    system.actors[1].fixed_y = 90 << 8;
    system.actors[1].active = 1;

    system.leaf_particles[0].fixed_x = 160 << 8;
    system.leaf_particles[0].fixed_y = 100 << 8;
    system.leaf_particles[0].frame = 2;
    system.leaf_particles[0].frame_countdown = 1;
    system.leaf_particles[0].active = 1;

    GbPlayer player = { 0 };
    player.y = 70;
    gb_video_draw_actors(&system, &player, 10, 5);

    const int npc_bottom = 9 * 4;
    const int npc_top = 10 * 4;
    const int grass_oam = 11 * 4;
    const int leaf_oam = 12 * 4;
    assert((OAM[npc_bottom] & 0x00FF) == 59);
    assert((OAM[npc_bottom + 1] & 0x01FF) == 90);
    assert((OAM[npc_bottom + 2] & 0x03FF) == 0x180);
    assert((OAM[npc_bottom + 2] & 0x0C00) == (1u << 10));
    assert((OAM[npc_top] & 0x00FF) == 43);
    assert((OAM[npc_top + 2] & 0x03FF) == 0x140);

    assert((OAM[grass_oam] & 0x00FF) == 69);
    assert((OAM[grass_oam + 1] & 0x01FF) == 120);
    assert((OAM[grass_oam + 1] & (1u << 12)) != 0);
    assert((OAM[grass_oam + 2] & 0x03FF) == 0x090);
    assert((OAM[grass_oam + 2] & 0x0C00) == (1u << 10));

    assert((OAM[leaf_oam] & 0x00FF) == 87);
    assert((OAM[leaf_oam + 1] & 0x01FF) == 146);
    assert((OAM[leaf_oam + 2] & 0x03FF) == 0x0B8);

    /* 2D OBJ staging: NPC slot 0 begins at logical 0xA0, while the
       canonical grass and leaf tiles stay at their original logical roots. */
    volatile u16* obj_vram = (volatile u16*)0x06010000u;
    assert(obj_vram[(0x0A0 * 64) / 2] == 0x1234);
    assert(obj_vram[(0x048 * 64) / 2] == 0x2345);
    assert(obj_vram[(0x05C * 64) / 2] == 0x3456);
    return 0;
}
"""
        self.compile_and_run(
            "mapped_actor_oam",
            harness,
            [
                RECON / "source/engine/video.c",
                RECON / "source/game/actors.c",
            ],
        )

    def test_vblank_wait_observes_leave_then_enter_transition_at_literal_vcount(self):
        harness = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <sys/mman.h>
#include <time.h>
#include <graveblood/video.h>

static atomic_int phase;

static void nap(long nanoseconds)
{
    struct timespec delay = { 0, nanoseconds };
    nanosleep(&delay, 0);
}

static void* vcount_worker(void* unused)
{
    (void)unused;
    nap(5000000);
    atomic_store(&phase, 1);
    REG_VCOUNT = 159;
    nap(5000000);
    atomic_store(&phase, 2);
    REG_VCOUNT = 160;
    return 0;
}

int main(void)
{
    void* mapped = mmap((void*)0x04000000u, 0x2000, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(mapped == (void*)0x04000000u);
    REG_VCOUNT = 160;
    atomic_store(&phase, 0);

    pthread_t worker;
    assert(pthread_create(&worker, 0, vcount_worker, 0) == 0);
    gb_video_wait_vblank();
    assert(atomic_load(&phase) == 2);
    assert(pthread_join(worker, 0) == 0);
    return 0;
}
"""
        self.compile_and_run(
            "mapped_vblank",
            harness,
            [RECON / "source/engine/video.c"],
            pthread=True,
        )

    def test_final_effect_wrapper_writes_literal_vram_without_crossing_vram_end(self):
        harness = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <string.h>
#include <sys/mman.h>
#include <graveblood/video.h>

const u8 gb_ending_arg0_copy1[GB_ENDING_ARG0_COPY1_BYTES] = {
    [0] = 0x11, [1] = 0x12,
    [GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES] = 0x21,
    [GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES + 1] = 0x22,
    [GB_ENDING_ARG0_COPY1_BYTES - 1] = 0x24,
};
const u8 gb_ending_arg0_copy2[GB_ENDING_ARG0_COPY2_BYTES] = {
    [0] = 0x33, [1] = 0x34,
    [GB_ENDING_ARG0_COPY2_BYTES - 2] = 0x43,
    [GB_ENDING_ARG0_COPY2_BYTES - 1] = 0x44,
};

int main(void)
{
    void* mapped = mmap((void*)0x06000000u, GB_ENDING_VRAM_BYTES,
                        PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(mapped == (void*)0x06000000u);
    memset(mapped, 0xA5, GB_ENDING_VRAM_BYTES);

    gb_video_apply_final_effect();
    volatile u8* vram = (volatile u8*)0x06000000u;
    assert(vram[0] == 0x12 && vram[1] == 0x12);
    assert(vram[GB_ENDING_OBJ_VRAM_OFFSET] == 0x33);
    assert(vram[GB_ENDING_OBJ_VRAM_OFFSET + 1] == 0x34);
    assert(vram[GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES - 2] == 0x43);
    assert(vram[GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES - 1] == 0x44);
    assert(vram[GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES] == 0xA5);
    assert(vram[GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES + 1] == 0xA5);
    assert(vram[GB_ENDING_ARG0_COPY1_BYTES - 2] == 0xA5);
    assert(vram[GB_ENDING_ARG0_COPY1_BYTES - 1] == 0xA5);
    assert(vram[GB_ENDING_ARG0_COPY1_BYTES] == 0xA5);
    assert(vram[GB_ENDING_VRAM_BYTES - 1] == 0xA5);
    return 0;
}
"""
        self.compile_and_run(
            "mapped_ending",
            harness,
            [
                RECON / "source/engine/video.c",
                RECON / "source/game/ending.c",
            ],
        )

    def test_all_reconstruction_units_compile_and_reloc_link_for_arm7tdmi_thumb(self):
        clang = shutil.which("clang")
        gcc = shutil.which("arm-none-eabi-gcc")
        if clang:
            compiler = [clang, "--target=arm-none-eabi"]
            linker = [clang, "--target=arm-none-eabi", "-nostdlib", "-Wl,-r"]
        elif gcc:
            compiler = [gcc]
            linker = [gcc, "-nostdlib", "-Wl,-r"]
        else:
            self.skipTest("no ARM-capable C compiler available")

        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / "gba.h").write_text(GBA_ARM_COMPILE_HEADER, encoding="utf-8")
            output = td / "objects"
            output.mkdir()
            env = os.environ.copy()
            env.setdefault("TERM", "xterm")

            objects: list[Path] = []
            sources = sorted(RECON.rglob("*.c"))
            self.assertGreaterEqual(len(sources), 41)
            for index, source in enumerate(sources):
                obj = output / f"c_{index:03d}_{source.stem}.o"
                command = [
                    *compiler,
                    "-mcpu=arm7tdmi", "-mthumb", "-std=c11", "-Os",
                    "-Wall", "-Wextra", "-Werror", "-ffreestanding",
                    "-I", str(td), "-I", str(INCLUDE),
                    "-c", str(source), "-o", str(obj),
                ]
                proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
                self.assertEqual(0, proc.returncode, f"{source}:\n{proc.stderr}")
                self.assertTrue(obj.is_file() and obj.stat().st_size > 0)
                objects.append(obj)

            # The two .incbin assembly units expect to assemble from reconstruction/build.
            # Mirror only that relative directory shape in the temporary tree.
            asm_reconstruction = td / "reconstruction"
            asm_build = asm_reconstruction / "build"
            asm_build.mkdir(parents=True)
            (asm_reconstruction / "data").symlink_to(RECON / "data", target_is_directory=True)
            for index, source in enumerate(sorted((RECON / "data").glob("*.s"))):
                obj = output / f"s_{index:03d}_{source.stem}.o"
                command = [
                    *compiler,
                    "-mcpu=arm7tdmi", "-mthumb",
                    "-c", str(source), "-o", str(obj),
                ]
                proc = subprocess.run(command, cwd=asm_build, env=env, capture_output=True, text=True)
                self.assertEqual(0, proc.returncode, f"{source}:\n{proc.stderr}")
                self.assertTrue(obj.is_file() and obj.stat().st_size > 0)
                objects.append(obj)

            # A relocatable ARM link catches duplicate symbols and incompatible relocations
            # without pretending to replace the unavailable devkitARM/libgba final link.
            combined = td / "graveblood_all_arm.o"
            command = [*linker, *(str(obj) for obj in objects), "-o", str(combined)]
            proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(combined.is_file() and combined.stat().st_size > 0)



if __name__ == "__main__":
    unittest.main()
