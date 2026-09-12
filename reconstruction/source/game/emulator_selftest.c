#include <graveblood/emulator_selftest.h>

#if defined(GB_EMULATOR_SELFTEST) || defined(GB_DEVICE_SELFTEST)

#include <graveblood/actor.h>
#include <graveblood/actors.h>
#include <graveblood/assets.h>
#include <graveblood/audio.h>
#include <graveblood/input.h>
#include <graveblood/scene.h>
#include <graveblood/video.h>

#define GB_SELFTEST_REG16(address) (*(volatile u16*)(address))
#define GB_SELFTEST_REG_IE 0x04000200u
#define GB_SELFTEST_REG_IME 0x04000208u
#define GB_SELFTEST_REG_DMA1CNT_H 0x040000C6u
#define GB_SELFTEST_REG_TM0CNT 0x04000102u
#define GB_SELFTEST_REG_TM1CNT 0x04000106u
#define GB_SELFTEST_OAM_BASE ((volatile u16*)0x07000000u)
#define GB_SELFTEST_VRAM_BASE ((volatile u8*)0x06000000u)
#define GB_SELFTEST_OBJ_VRAM ((volatile u8*)0x06010000u)

enum {
    GB_SELFTEST_PPU_X0 = 100,
    GB_SELFTEST_PPU_Y0 = 64,
    GB_SELFTEST_PPU_X1 = 101,
    GB_SELFTEST_PPU_Y1 = 64,
    GB_SELFTEST_PPU_PLAYER_COLOR = 0x03E0,
    GB_SELFTEST_PPU_NPC_COLOR = 0x001F,

    GB_SELFTEST_DEVICE_BAR_COUNT = 7,
    GB_SELFTEST_DEVICE_PASS_COLOR = 0x03E0,
    GB_SELFTEST_DEVICE_FAIL_COLOR = 0x001F,
    GB_SELFTEST_DEVICE_BG_COLOR = 0x1084,
    GB_SELFTEST_DEVICE_SEPARATOR_COLOR = 0x7FFF,
};

static GbActorSystem gb_selftest_actor_system;
static GbPlayer gb_selftest_player;
static GbSceneRuntime gb_selftest_scene;

void gb_player_update(GbPlayer* player, const GbLevelAssets* level, const GbInput* input);

static volatile GbEmulatorSelftestReport* gb_selftest_report(void)
{
    return (volatile GbEmulatorSelftestReport*)GB_SELFTEST_REPORT_ADDRESS;
}

static void gb_selftest_mark(u32 bit, int passed)
{
    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    if(passed)
    {
        report->pass_mask |= bit;
    }
    else
    {
        report->fail_mask |= bit;
    }
}

static void gb_selftest_clear_report(void)
{
    volatile u32* words = (volatile u32*)GB_SELFTEST_REPORT_ADDRESS;
    for(unsigned i = 0; i < sizeof(GbEmulatorSelftestReport) / sizeof(u32); ++i)
    {
        words[i] = 0;
    }
    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    report->magic = GB_SELFTEST_MAGIC;
    report->version = GB_SELFTEST_VERSION;
    report->expected_mask = GB_SELFTEST_EXPECTED_MASK;
}

static void gb_selftest_oam(void)
{
    GbActorDescriptor descriptor = {0};
    const GbActorVisualSpec* visual = 0;
    for(int i = 0; i < GB_ACTOR_VISUAL_COUNT; ++i)
    {
        if(gb_actor_visuals[i].legs_color != 1)
        {
            visual = &gb_actor_visuals[i];
            break;
        }
    }

    gb_video_init();
    gb_player_spawn(&gb_selftest_player, 100, 80);
    gb_actor_system_init(&gb_selftest_actor_system);

    if(! visual)
    {
        gb_selftest_mark(GB_SELFTEST_OAM, 0);
        return;
    }

    descriptor.actor_class = GB_ACTOR_NPC;
    descriptor.subtype = visual->subtype;
    descriptor.legs_color = visual->legs_color;
    descriptor.num = 1;
    descriptor.setglobal = 0;

    GbActor* actor = &gb_selftest_actor_system.actors[0];
    actor->descriptor = &descriptor;
    actor->fixed_x = 100 << GB_ACTOR_FIXED_SHIFT;
    actor->fixed_y = 80 << GB_ACTOR_FIXED_SHIFT;
    actor->frame = 1;
    actor->frame_countdown = 1;
    actor->visual_legs_color = descriptor.legs_color;
    actor->animation_frame_count = 1;
    actor->active = 1;
    gb_selftest_actor_system.count = 1;

    gb_video_draw_actors(&gb_selftest_actor_system, &gb_selftest_player, 0, 0);
    gb_video_draw_player(&gb_selftest_player, 0, 0);

    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    const u16 player_attr1 = GB_SELFTEST_OAM_BASE[1];
    const u16 player_attr2 = GB_SELFTEST_OAM_BASE[2];
    const u16 npc_attr1 = GB_SELFTEST_OAM_BASE[9 * 4 + 1];
    const u16 npc_attr2 = GB_SELFTEST_OAM_BASE[9 * 4 + 2];
    report->player_oam_attr2 = player_attr2;
    report->npc_oam_attr2 = npc_attr2;

    gb_selftest_mark(
        GB_SELFTEST_OAM,
        (player_attr1 & 0x01FFu) == 100u &&
        (npc_attr1 & 0x01FFu) == 100u &&
        (player_attr2 & 0x0C00u) == 0x0800u &&
        (npc_attr2 & 0x0C00u) == 0x0800u);
}

static void gb_selftest_vblank(void)
{
    gb_video_wait_vblank();
    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    report->vblank_vcount = REG_VCOUNT;
    gb_selftest_mark(GB_SELFTEST_VBLANK, report->vblank_vcount >= 160u);
}

static void gb_selftest_level9_boundary(void)
{
    gb_player_spawn(&gb_selftest_player, 2556, 400);
    const int crossed = gb_player_try_level10_boundary(&gb_selftest_player, 9) != 0;

    gb_scene_init(&gb_selftest_scene);
    gb_scene_request_gameplay(&gb_selftest_scene, 10, 10);
    GbSceneTick tick = {0, 0, 0, 0};
    for(int i = 0; i < 11; ++i)
    {
        tick = gb_scene_update_pending(&gb_selftest_scene);
    }

    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    report->boundary_mode = gb_selftest_player.script_mode;
    report->scene_level = tick.gameplay_level;
    gb_selftest_mark(
        GB_SELFTEST_LEVEL9_BOUNDARY,
        crossed && report->boundary_mode == 5u && tick.enter_gameplay &&
        tick.gameplay_level == 10u && gb_selftest_scene.active == GB_SCENE_GAMEPLAY);
}

static void gb_selftest_level10_entrance(void)
{
    const GbLevelAssets* level = gb_level_default_assets(10);
    const GbInput idle = {0, 0};
    if(! level)
    {
        gb_selftest_mark(GB_SELFTEST_LEVEL10_ENTRANCE, 0);
        return;
    }

    gb_player_spawn(&gb_selftest_player, level->spawn_x, level->spawn_y);
    gb_selftest_player.script_mode = 5;
    for(int i = 0; i < 800 && gb_selftest_player.script_mode != 0; ++i)
    {
        gb_player_update(&gb_selftest_player, level, &idle);
    }

    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    report->entrance_mode = gb_selftest_player.script_mode;
    report->entrance_x = gb_selftest_player.x;
    report->entrance_y = gb_selftest_player.y;
    gb_selftest_mark(
        GB_SELFTEST_LEVEL10_ENTRANCE,
        report->entrance_mode == 0u && report->entrance_x == 730 && report->entrance_y == 780);
}

static void gb_selftest_leaves(void)
{
    const GbLevelAssets* level = gb_level_default_assets(9);
    gb_actor_system_init(&gb_selftest_actor_system);
    gb_actor_system_load(&gb_selftest_actor_system, level);
    for(int i = 0; i < 13; ++i)
    {
        gb_actor_system_update_environment(&gb_selftest_actor_system, 2101, 100);
    }

    u32 count = 0;
    s16 first_x = 0;
    s16 first_y = 0;
    for(int i = 0; i < GB_LEAF_PARTICLE_CAPACITY; ++i)
    {
        const GbLeafParticle* particle = &gb_selftest_actor_system.leaf_particles[i];
        if(particle->active)
        {
            if(count == 0)
            {
                first_x = gb_leaf_particle_pixel_x(particle);
                first_y = gb_leaf_particle_pixel_y(particle);
            }
            ++count;
        }
    }

    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    report->leaf_count = count;
    report->leaf_x = first_x;
    report->leaf_y = first_y;
    gb_selftest_mark(GB_SELFTEST_LEAVES, count == 1u && first_x == 2611 && first_y == 80);
}

static void gb_selftest_ending(void)
{
    volatile u8* vram = GB_SELFTEST_VRAM_BASE;
    vram[GB_ENDING_ARG0_COPY1_BYTES] = 0xA5;
    vram[GB_ENDING_VRAM_BYTES - 1] = 0x5A;

    gb_video_apply_final_effect();

    const u32 copy2_last = GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES - 1u;
    const u32 copy2_after = GB_ENDING_OBJ_VRAM_OFFSET + GB_ENDING_ARG0_COPY2_BYTES;
    const int ok =
        vram[0] == gb_ending_arg0_copy1[0] &&
        vram[GB_ENDING_OBJ_VRAM_OFFSET] == gb_ending_arg0_copy2[0] &&
        vram[copy2_last] == gb_ending_arg0_copy2[GB_ENDING_ARG0_COPY2_BYTES - 1] &&
        vram[copy2_after] == gb_ending_arg0_copy1[copy2_after] &&
        vram[GB_ENDING_ARG0_COPY1_BYTES] == 0xA5 &&
        vram[GB_ENDING_VRAM_BYTES - 1] == 0x5A;

    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    report->ending_guard = ok ? 0xA55AA55Au :
        ((u32)vram[GB_ENDING_ARG0_COPY1_BYTES] << 8) | vram[GB_ENDING_VRAM_BYTES - 1];
    gb_selftest_mark(GB_SELFTEST_ENDING, ok);
}

static void gb_selftest_audio(void)
{
    gb_audio_init();
    const u32 setup_ok =
        GB_SELFTEST_REG16(GB_SELFTEST_REG_DMA1CNT_H) == 0xB200u &&
        GB_SELFTEST_REG16(GB_SELFTEST_REG_TM0CNT) == 0x0080u &&
        GB_SELFTEST_REG16(GB_SELFTEST_REG_TM1CNT) == 0x00C4u &&
        (GB_SELFTEST_REG16(GB_SELFTEST_REG_IE) & IRQ_TIMER1) != 0u &&
        GB_SELFTEST_REG16(GB_SELFTEST_REG_IME) != 0u;

    for(int frame = 0; frame < 60; ++frame)
    {
        gb_video_wait_vblank();
    }

    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    report->audio_irq_count = gb_audio_selftest_irq_count;
    report->audio_setup_ok = setup_ok;
    report->audio_ie = GB_SELFTEST_REG16(GB_SELFTEST_REG_IE);
    report->audio_ime = GB_SELFTEST_REG16(GB_SELFTEST_REG_IME);
    gb_selftest_mark(
        GB_SELFTEST_AUDIO_IRQ,
        setup_ok && gb_audio_selftest_irq_count >= 63u && gb_audio_selftest_irq_count <= 66u);
    gb_audio_shutdown();
}

static void gb_selftest_prepare_ppu_fixture(void)
{
    GbActorDescriptor descriptor = {0};
    const GbActorVisualSpec* visual = 0;
    for(int i = 0; i < GB_ACTOR_VISUAL_COUNT; ++i)
    {
        if(gb_actor_visuals[i].legs_color != 1)
        {
            visual = &gb_actor_visuals[i];
            break;
        }
    }
    if(! visual)
    {
        return;
    }

    gb_video_init();
    gb_player_spawn(&gb_selftest_player, 100, 80);
    gb_actor_system_init(&gb_selftest_actor_system);

    descriptor.actor_class = GB_ACTOR_NPC;
    descriptor.subtype = visual->subtype;
    descriptor.legs_color = visual->legs_color;
    descriptor.num = 1;
    descriptor.setglobal = 0;

    GbActor* actor = &gb_selftest_actor_system.actors[0];
    actor->descriptor = &descriptor;
    actor->fixed_x = 100 << GB_ACTOR_FIXED_SHIFT;
    actor->fixed_y = 80 << GB_ACTOR_FIXED_SHIFT;
    actor->frame = 1;
    actor->frame_countdown = 1;
    actor->visual_legs_color = descriptor.legs_color;
    actor->animation_frame_count = 1;
    actor->active = 1;
    gb_selftest_actor_system.count = 1;

    gb_video_draw_actors(&gb_selftest_actor_system, &gb_selftest_player, 0, 0);
    gb_video_draw_player(&gb_selftest_player, 0, 0);

    /* Keep the production OAM layout but replace two probe pixels with
       primary colors.  At equal priority, OAM 0 (Player) must win over
       OAM 9 (NPC); the next transparent Player pixel must reveal the NPC. */
    const u16 player_attr2 = GB_SELFTEST_OAM_BASE[2];
    const u16 npc_attr2 = GB_SELFTEST_OAM_BASE[9 * 4 + 2];
    const u16 player_tile = player_attr2 & 0x03FFu;
    const u16 npc_tile = npc_attr2 & 0x03FFu;
    const u16 player_palette = (player_attr2 >> 12) & 0x000Fu;
    GB_SELFTEST_OBJ_VRAM[(u32)player_tile * 32u] = 0x01u;
    GB_SELFTEST_OBJ_VRAM[(u32)npc_tile * 32u] = 0x01u;
    GB_SELFTEST_OBJ_VRAM[(u32)npc_tile * 32u + 1u] = 0x01u;
    OBJ_COLORS[player_palette * 16u + 1u] = GB_SELFTEST_PPU_PLAYER_COLOR;
    OBJ_COLORS[1] = GB_SELFTEST_PPU_NPC_COLOR;
    BG_COLORS[0] = 0x7C00u;
    REG_DISPCNT = MODE_0 | OBJ_ON | OBJ_1D_MAP;

    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    report->ppu_probe_coords =
        (u32)GB_SELFTEST_PPU_X0 |
        ((u32)GB_SELFTEST_PPU_Y0 << 8) |
        ((u32)GB_SELFTEST_PPU_X1 << 16) |
        ((u32)GB_SELFTEST_PPU_Y1 << 24);
    report->ppu_probe_colors =
        (u32)GB_SELFTEST_PPU_PLAYER_COLOR |
        ((u32)GB_SELFTEST_PPU_NPC_COLOR << 16);

    gb_video_wait_vblank();
}

static void gb_selftest_run_checks(void)
{
    gb_selftest_clear_report();
    gb_selftest_oam();
    gb_selftest_vblank();
    gb_selftest_level9_boundary();
    gb_selftest_level10_entrance();
    gb_selftest_leaves();
    gb_selftest_ending();
    gb_selftest_audio();
}

static void gb_selftest_mode3_fill_rect(int x0, int y0, int x1, int y1, u16 color)
{
    volatile u16* framebuffer = (volatile u16*)0x06000000u;
    for(int y = y0; y < y1; ++y)
    {
        for(int x = x0; x < x1; ++x)
        {
            framebuffer[y * 240 + x] = color;
        }
    }
}

static void gb_selftest_show_device_summary(void)
{
    volatile GbEmulatorSelftestReport* report = gb_selftest_report();
    const u32 bits[GB_SELFTEST_DEVICE_BAR_COUNT] = {
        GB_SELFTEST_OAM,
        GB_SELFTEST_VBLANK,
        GB_SELFTEST_LEVEL9_BOUNDARY,
        GB_SELFTEST_LEVEL10_ENTRANCE,
        GB_SELFTEST_LEAVES,
        GB_SELFTEST_ENDING,
        GB_SELFTEST_AUDIO_IRQ,
    };
    const int all_passed =
        report->fail_mask == 0u &&
        (report->pass_mask & GB_SELFTEST_EXPECTED_MASK) == GB_SELFTEST_EXPECTED_MASK;

    REG_DISPCNT = MODE_3 | BG2_ON;
    gb_selftest_mode3_fill_rect(0, 0, 240, 160, GB_SELFTEST_DEVICE_BG_COLOR);
    gb_selftest_mode3_fill_rect(
        0, 0, 240, 18,
        all_passed ? GB_SELFTEST_DEVICE_PASS_COLOR : GB_SELFTEST_DEVICE_FAIL_COLOR);
    gb_selftest_mode3_fill_rect(0, 19, 240, 21, GB_SELFTEST_DEVICE_SEPARATOR_COLOR);

    for(int i = 0; i < GB_SELFTEST_DEVICE_BAR_COUNT; ++i)
    {
        const int y0 = 28 + i * 18;
        const u16 color = (report->pass_mask & bits[i]) != 0u
            ? GB_SELFTEST_DEVICE_PASS_COLOR
            : GB_SELFTEST_DEVICE_FAIL_COLOR;
        gb_selftest_mode3_fill_rect(20, y0, 220, y0 + 12, color);
    }
}

void gb_emulator_selftest_run(void)
{
    gb_selftest_run_checks();
    gb_selftest_prepare_ppu_fixture();
    gb_selftest_report()->complete = GB_SELFTEST_COMPLETE;

    for(;;)
    {
    }
}

void gb_device_selftest_run(void)
{
    gb_selftest_run_checks();
    gb_selftest_report()->complete = GB_SELFTEST_COMPLETE;
    gb_selftest_show_device_summary();

    /* SFX6 is the recovered Title START cue.  Reusing the production
       mixer/DMA/timer path gives a simple audible flash-cart check. */
    gb_audio_init();
    (void)gb_audio_play_sfx(6);

    for(;;)
    {
        gb_video_wait_vblank();
    }
}

#endif
