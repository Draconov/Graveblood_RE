#include <graveblood/stream.h>
#include <graveblood/ending.h>
#include <graveblood/video.h>

#define GB_BG0_SCREENBLOCK 27
#define GB_BG1_SCREENBLOCK 28
#define GB_BG2_SCREENBLOCK 29
#define GB_BG3_SCREENBLOCK 30
#define GB_OBJ_TALL (2u << 14)
#define GB_OBJ_SIZE_2 (2u << 14)
#define GB_OBJ_HFLIP (1u << 12)
#define GB_OBJ_256_COLOR (1u << 13)
#define GB_OBJ_SIZE_1 (1u << 14)
#define GB_ACTOR_OAM_FIRST 9
#define GB_ACTOR_OAM_COUNT 48
#define GB_NPC_OBJ_SLOT_COUNT 24
#define GB_PLAYER_TOP_LOGICAL_TILE 0x60
#define GB_PLAYER_BOTTOM_LOGICAL_TILE 0x80
#define GB_PLAYER_INTERACTION_LOGICAL_TILE 0x4E
#define GB_GRASS_LOGICAL_TILE 0x48
#define GB_STORY_UI_COLUMNS 29
#define GB_STORY_UI_ROWS 3
#define GB_STORY_UI_MAP_Y 17
#define GB_STORY_UI_WIDTH (GB_STORY_UI_COLUMNS * 8)
#define GB_STORY_UI_HEIGHT (GB_STORY_UI_ROWS * 8)
#define GB_DIALOGUE_WINDOW_MAP_X 1
#define GB_DIALOGUE_WINDOW_MAP_Y 13
#define GB_SOCIAL_RESPONSE_WINDOW_MAP_X 5
#define GB_SOCIAL_RESPONSE_WINDOW_MAP_Y 13
#define GB_SOCIAL_SELECTOR_MAP_X 1
#define GB_SOCIAL_SELECTOR_MAP_Y 9
#define GB_SOCIAL_TOPIC_CLEAR_X 5
#define GB_SOCIAL_TOPIC_CLEAR_Y 1
#define GB_SOCIAL_TOPIC_CLEAR_WIDTH 14
#define GB_SOCIAL_TOPIC_CLEAR_HEIGHT 12
#define GB_SOCIAL_TEXT_COLUMNS 8
#define GB_SOCIAL_TEXT_WIDTH (GB_SOCIAL_TEXT_COLUMNS * 8)
#define GB_DIALOGUE_WINDOW_COLUMNS 20
#define GB_DIALOGUE_WINDOW_ROWS 6
#define GB_DIALOGUE_TEXT_COLUMNS 18
#define GB_DIALOGUE_TEXT_ROWS 4
#define GB_DIALOGUE_TEXT_MAP_X 2
#define GB_DIALOGUE_TEXT_MAP_Y 14
#define GB_DIALOGUE_TEXT_WIDTH (GB_DIALOGUE_TEXT_COLUMNS * 8)
#define GB_DIALOGUE_TEXT_HEIGHT (GB_DIALOGUE_TEXT_ROWS * 8)
#define GB_DIALOGUE_BORDER_VERTICAL_TILE 3
#define GB_DIALOGUE_BORDER_CORNER_TILE 4
#define GB_DIALOGUE_BORDER_HORIZONTAL_TILE 5
#define GB_BG_MAP_HFLIP (1u << 10)
#define GB_BG_MAP_VFLIP (1u << 11)
#define GB_PDA_TEXT_MAP_Y 1
#define GB_PDA_TEXT_WIDTH (GB_PDA_TEXT_COLUMNS * 8)
#define GB_PDA_TEXT_HEIGHT (GB_PDA_TEXT_ROWS * 8)
#define GB_TEXT_BACKGROUND_INDEX 1
#define GB_TEXT_FOREGROUND_INDEX 2
#define GB_TITLE_ANIM_A_VRAM_OFFSET 0x2F00
#define GB_TITLE_ANIM_B_VRAM_OFFSET 0x3B00
#define GB_TITLE_PROMPT_X 9
#define GB_TITLE_PROMPT_Y 9
#define GB_WARDROBE_BG_VRAM_OFFSET 0x3000
#define GB_WARDROBE_BG_TILE_BASE (GB_WARDROBE_BG_VRAM_OFFSET / 64)
#define GB_WARDROBE_BG_MAP_X 7
#define GB_WARDROBE_BG_MAP_Y 4
#define GB_WARDROBE_BG_MAP_WIDTH 16
#define GB_WARDROBE_BG_MAP_HEIGHT 8
#define GB_WARDROBE_PREVIEW_Y 48
#define GB_WARDROBE_PREVIEW_LOGICAL_BASE 0x62

static const GbLevelAssets* gb_video_level;
static u8 gb_story_ui_pixels[GB_STORY_UI_WIDTH * GB_STORY_UI_HEIGHT];
static u8 gb_dialogue_text_pixels[GB_DIALOGUE_TEXT_WIDTH * GB_DIALOGUE_TEXT_HEIGHT];
static u8 gb_social_text_pixels[GB_SOCIAL_TEXT_WIDTH * 8];
static u8 gb_pda_text_pixels[GB_PDA_TEXT_WIDTH * GB_PDA_TEXT_HEIGHT];
static u8 gb_monster_animation_counter;

/* 0x03000854 is initialized from ROM to 48,000. Player+0x398 starts at
   zero and advances the amortized OBJ-palette refresh by four entries. */
static u32 gb_gameplay_lighting_clock = 48000u;
static u16 gb_gameplay_lighting_cursor;

typedef struct {
    s16 c0;
    s16 c1;
    s16 c2;
    s16 divisor;
    s16 contrast;
} GbGameplayLighting;

static const GbGameplayLighting gb_gameplay_lighting_table[13] = {
    { 1, 2, 20, 2, 12 }, { 0, 1, 17, 2, 9 }, { 1, 2, 24, 2, 10 },
    { 10, 10, 32, 4, 3 }, { 18, 18, 21, 5, 1 }, { 30, 30, 30, 10, 0 },
    { 29, 29, 28, 6, 2 }, { 29, 29, 25, 5, 5 }, { 13, 13, 22, 4, 7 },
    { 21, 16, 2, 3, 10 }, { 5, 0, 8, 2, 8 }, { 2, 0, 16, 2, 11 },
    { 1, 2, 20, 2, 12 },
};

static void gb_story_ui_begin(void);
static void gb_story_ui_text(const char* text, int* x, int* y);
static void gb_story_ui_newline(int* x, int* y);

static void gb_copy_u16(volatile u16* dst, const u16* src, int count)
{
    for(int i = 0; i < count; ++i)
    {
        dst[i] = src[i];
    }
}

static void gb_clear_u16(volatile u16* dst, int count)
{
    for(int i = 0; i < count; ++i)
    {
        dst[i] = 0;
    }
}

typedef struct {
    u16 destination_32;
    u16 source_32;
    u16 count_64;
} GbFgtileTilePatch;

/* 0x03000884 is part of the initialized-IWRAM image copied from
   0x08A8D738 at boot.  Fgtile_update passes treetype / treetype+1 directly
   to 0x08005C6C; each entry is {BG-VRAM offset/32, graphics-source
   offset/32, byte-count/64}. */
static const GbFgtileTilePatch gb_fgtile_tile_patches[GB_FGTILE_PATCH_COUNT] = {
    { 906, 2710, 176 }, { 906, 1680, 176 },
    { 906, 2710, 176 }, { 906, 3060, 176 },
    { 184, 3594, 26 },  { 184, 3412, 26 },
    { 456, 3466, 64 },  { 456, 3648, 64 },
    { 906, 1680, 176 }, { 906, 3774, 176 },
    { 584, 4126, 76 },  { 584, 4430, 76 },
    { 584, 4430, 76 },  { 584, 4278, 76 },
    { 742, 2084, 132 }, { 742, 2354, 132 },
    { 736, 2348, 135 }, { 736, 1814, 135 },
};

void gb_video_apply_fgtile_patch(u8 patch_index)
{
    if(! gb_video_level || ! gb_video_level->bg_patch_source ||
       patch_index >= GB_FGTILE_PATCH_COUNT)
    {
        return;
    }

    const GbFgtileTilePatch* patch = &gb_fgtile_tile_patches[patch_index];
    if(patch->source_32 < GB_FGTILE_PATCH_SOURCE_BASE_32)
    {
        return;
    }
    const u32 source_halfword =
        (u32)(patch->source_32 - GB_FGTILE_PATCH_SOURCE_BASE_32) * 16u;
    const u32 count_halfwords = (u32)patch->count_64 * 32u;
    if(source_halfword + count_halfwords > gb_video_level->bg_patch_source_halfwords)
    {
        return;
    }

    volatile u16* destination = (volatile u16*)CHAR_BASE_ADR(0);
    destination += (u32)patch->destination_32 * 16u;
    gb_copy_u16(destination, gb_video_level->bg_patch_source + source_halfword,
                (int)count_halfwords);
}

static s16 gb_lighting_interpolate(s16 a, s16 b, s16 factor)
{
    return (s16)(a + ((b - a) * factor) / 40);
}

static GbGameplayLighting gb_gameplay_lighting_at(u32 clock)
{
    const u32 hour = (clock / 3600u) % 24u;
    const u32 slot = (hour - (hour & 1u)) / 2u;
    const s16 factor = (s16)(((clock / 60u) % 120u) / 3u);
    const GbGameplayLighting* a = &gb_gameplay_lighting_table[slot];
    const GbGameplayLighting* b = &gb_gameplay_lighting_table[slot + 1u];
    GbGameplayLighting out;
    out.c0 = gb_lighting_interpolate(a->c0, b->c0, factor);
    out.c1 = gb_lighting_interpolate(a->c1, b->c1, factor);
    out.c2 = gb_lighting_interpolate(a->c2, b->c2, factor);
    out.divisor = gb_lighting_interpolate(a->divisor, b->divisor, factor);
    out.contrast = gb_lighting_interpolate(a->contrast, b->contrast, factor);
    return out;
}

static u16 gb_gameplay_lighting_color(u16 source, const GbGameplayLighting* light)
{
    /* 0x080051FC computes the contrast multiplier in double precision, then
       converts it to float before transforming each 5-bit BGR555 component. */
    const float scale = (float)(((double)(light->contrast + 31) * 259.0) /
                                ((double)(259 - light->contrast) * 31.0));
    const s16 targets[3] = { light->c0, light->c1, light->c2 };
    u16 result = 0;
    for(u16 component = 0; component < 3; ++component)
    {
        const u16 shift = (u16)(component * 5u);
        const s16 original = (s16)((source >> shift) & 31u);
        const s16 adjusted = (s16)(original + (targets[component] - original) / light->divisor);
        s16 value = (s16)((float)(adjusted - 16) * scale + 16.0f);
        if(value < 0)
        {
            value = 0;
        }
        else if(value > 31)
        {
            value = 31;
        }
        result |= (u16)((u16)value << shift);
    }
    return result;
}

static void gb_video_transform_gameplay_obj_palette(u16 start, u16 count, u32 clock)
{
    if(! gb_video_level)
    {
        return;
    }
    const GbGameplayLighting light = gb_gameplay_lighting_at(clock);
    const u16 end = (u16)(start + count);
    for(u16 pair = start; pair < end; pair = (u16)(pair + 2u))
    {
        if(pair > 254u)
        {
            break;
        }
        /* 0x08005272..0x08005692 jumps around the OBJ write for pair 4/5
           and for every pair starting above 199.  These entries retain the
           palette contents already staged by the active graphics object. */
        if(pair == 4u || pair > 199u)
        {
            continue;
        }
        OBJ_COLORS[pair] = gb_gameplay_lighting_color(gb_actor_obj_lighting_source[pair], &light);
        if(pair < 255u)
        {
            OBJ_COLORS[pair + 1u] = gb_gameplay_lighting_color(gb_actor_obj_lighting_source[pair + 1u], &light);
        }
    }
}


static volatile u16* gb_obj_logical_tile_ptr(u16 logical_tile)
{
    (void)logical_tile; /* Some host GBA test headers intentionally ignore SPR_VRAM's argument. */
    /* Gameplay uses 8bpp + 2D OBJ mapping. One logical 8bpp tile is two
       32-byte ATTR2 tile units, or 64 bytes in OBJ VRAM. */
    return (volatile u16*)SPR_VRAM((u16)(logical_tile * 2u));
}

static void gb_stage_8bpp_8x8(u16 logical_tile, const u16* src)
{
    gb_copy_u16(gb_obj_logical_tile_ptr(logical_tile), src, 32);
}

static void gb_stage_8bpp_16x16(u16 logical_root, const u16* src)
{
    /* Packed source order is top-left, top-right, bottom-left, bottom-right.
       In 2D mapping the next 8-pixel row is +16 logical 8bpp tiles. */
    gb_copy_u16(gb_obj_logical_tile_ptr(logical_root), src, 64);
    gb_copy_u16(gb_obj_logical_tile_ptr((u16)(logical_root + 16u)), src + 64, 64);
}

static void gb_stage_8bpp_16x32(u16 logical_root, const u16* src)
{
    for(u16 row = 0; row < 4; ++row)
    {
        gb_copy_u16(gb_obj_logical_tile_ptr((u16)(logical_root + row * 16u)),
                    src + row * 64u, 64);
    }
}

static int gb_npc_obj_logical_root(u8 slot, u16* out)
{
    /* Canonical demo visibility never exceeds 19 simultaneous NPC frames.
       Reserve 24 collision-free 16x32 work slots while keeping the original
       Player (rows 6..9), Grass/Leaves (rows 4..5), and special-composite
       rows untouched. */
    static const u16 row_bases[3] = { 0xA0, 0xE0, 0x00 };
    if(slot >= GB_NPC_OBJ_SLOT_COUNT || ! out)
    {
        return 0;
    }
    *out = (u16)(row_bases[slot >> 3] + (slot & 7u) * 2u);
    return 1;
}

static u16 gb_translate_source(const GbLevelAssets* level, u16 source_id)
{
    if(source_id >= level->translation_count)
    {
        return 0;
    }
    return level->translation[source_id];
}

static void gb_load_fixed_maps(const GbLevelAssets* level)
{
    volatile u16* bg2 = (volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK);
    volatile u16* bg3 = (volatile u16*)MAP_BASE_ADR(GB_BG3_SCREENBLOCK);
    gb_clear_u16(bg2, GB_STREAM_MAP_CELLS);
    gb_clear_u16(bg3, GB_STREAM_MAP_CELLS);

    for(unsigned y = 0; y < level->fixed_height_tiles && y < 32; ++y)
    {
        for(unsigned x = 0; x < level->fixed_width_tiles; ++x)
        {
            const u16 entry = gb_translate_source(
                level,
                level->fixed_map[y * level->fixed_width_tiles + x]
            );
            if(x < 32)
            {
                bg2[y * 32 + x] = entry;
            }
            else if(x < 64)
            {
                bg3[y * 32 + (x - 32)] = entry;
            }
        }
    }
}

static void gb_video_configure_gameplay_display(void)
{
    BGCTRL[0] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG0_SCREENBLOCK) | BG_PRIORITY(0);
    BGCTRL[1] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG1_SCREENBLOCK) | BG_PRIORITY(1);
    BGCTRL[2] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG2_SCREENBLOCK) | BG_PRIORITY(2);
    BGCTRL[3] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG3_SCREENBLOCK) | BG_PRIORITY(3);
    REG_DISPCNT = MODE_0 | BG0_ON | BG1_ON | BG2_ON | BG3_ON | OBJ_ON;
}

static void gb_video_configure_title_display(void)
{
    BGCTRL[0] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG0_SCREENBLOCK) | BG_PRIORITY(0);
    BGCTRL[1] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG1_SCREENBLOCK) | BG_PRIORITY(1);
    BGCTRL[2] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG2_SCREENBLOCK) | BG_PRIORITY(2);
    BGCTRL[3] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG3_SCREENBLOCK) | BG_PRIORITY(3);
    REG_DISPCNT = MODE_0 | BG0_ON | BG1_ON | BG2_ON | BG3_ON | OBJ_ON;
}

static void gb_video_configure_pda_display(void)
{
    BGCTRL[0] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG0_SCREENBLOCK) | BG_PRIORITY(0);
    BGCTRL[1] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG1_SCREENBLOCK) | BG_PRIORITY(1);
    REG_DISPCNT = MODE_0 | BG0_ON | BG1_ON;
    gb_video_set_camera(0, 0);
}

static void gb_video_hide_all_oam(void)
{
    volatile u16* oam = (volatile u16*)OAM;
    for(int i = 0; i < 128; ++i)
    {
        oam[i * 4] = 160;
        oam[i * 4 + 1] = 0;
        oam[i * 4 + 2] = 0;
        oam[i * 4 + 3] = 0;
    }
}

static void gb_video_hide_title_oam(void)
{
    volatile u16* oam = (volatile u16*)OAM;
    for(int i = 0; i < 128; ++i)
    {
        oam[i * 4] = 0x02F0;
        oam[i * 4 + 1] = 0x01F0;
        oam[i * 4 + 2] = 0x0C00;
        oam[i * 4 + 3] = 0;
    }
}

static void gb_video_restore_gameplay_obj_assets(void)
{
    static const u16 monster_roots[GB_MONSTER_SPRITE_COUNT] = {
        0x159, 0x178, 0x17A, 0x198, 0x19A,
    };
    static const u16 static_roots[GB_LEVEL_STATIC_SPRITE_COUNT] = {
        0x17C, 0x17E, 0x19C, 0x19E,
    };
    static const u16 leaf_roots[GB_LEAF_FRAME_COUNT] = {
        0x4C, 0x4D, 0x5C, 0x5D,
    };

    /* The canonical level graphics descriptors carry a zero low OBJ-palette
       copy count.  Preserve entries 0..223 across level loads and only apply
       the loader's unconditional 0x40-byte patch at indices 224..255. */
    gb_copy_u16(OBJ_COLORS + 224, gb_actor_obj_high_palette, GB_ACTOR_OBJ_HIGH_PALETTE_COUNT);

    for(u16 i = 0; i < GB_MONSTER_SPRITE_COUNT; ++i)
    {
        gb_stage_8bpp_16x16(monster_roots[i],
                            gb_monster_obj_frames + i * GB_MONSTER_SPRITE_HALFWORDS);
    }
    for(u16 i = 0; i < GB_LEVEL_STATIC_SPRITE_COUNT; ++i)
    {
        gb_stage_8bpp_16x16(static_roots[i],
                            gb_level_static_obj_tiles + i * GB_LEVEL_STATIC_SPRITE_HALFWORDS);
    }
    gb_stage_8bpp_16x16(GB_GRASS_LOGICAL_TILE, gb_grass_obj_tiles);
    for(u16 i = 0; i < GB_LEAF_FRAME_COUNT; ++i)
    {
        gb_stage_8bpp_8x8(leaf_roots[i],
                           gb_leaf_obj_frames + i * GB_LEAF_FRAME_HALFWORDS);
    }
}

void gb_video_wait_vblank(void)
{
    while(REG_VCOUNT >= 160)
    {
    }
    while(REG_VCOUNT < 160)
    {
    }
}

void gb_video_apply_final_effect(void)
{
    gb_ending_apply_argument0((volatile u8*)0x06000000);
}

void gb_video_init(void)
{
    gb_video_configure_gameplay_display();
    gb_video_set_camera(0, 0);

    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG3_SCREENBLOCK), GB_STREAM_MAP_CELLS);

    gb_video_hide_all_oam();

    gb_video_restore_gameplay_obj_assets();
    gb_video_level = 0;
    gb_monster_animation_counter = 0;
    gb_gameplay_lighting_clock = 48000u;
    gb_gameplay_lighting_cursor = 0;
}

void gb_video_title_set_animation(u8 state)
{
    if(state >= GB_TITLE_ANIMATION_STATES)
    {
        state = 0;
    }
    volatile u16* char_mem = (volatile u16*)CHAR_BASE_ADR(0);
    gb_copy_u16(char_mem + GB_TITLE_ANIM_A_VRAM_OFFSET / 2,
                gb_title_anim_a[state], GB_TITLE_ANIM_A_HALFWORDS);
    gb_copy_u16(char_mem + GB_TITLE_ANIM_B_VRAM_OFFSET / 2,
                gb_title_anim_b[state], GB_TITLE_ANIM_B_HALFWORDS);
}

void gb_video_title_set_prompt_visible(int visible)
{
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    const u16* tiles = visible ? gb_title_prompt_tiles : gb_title_blank_tiles;
    for(int i = 0; i < GB_TITLE_PROMPT_LENGTH; ++i)
    {
        map[GB_TITLE_PROMPT_Y * 32 + GB_TITLE_PROMPT_X + i] = tiles[i];
    }
}

void gb_video_load_title(void)
{
    gb_video_level = 0;
    gb_video_set_camera(0, 0);
    gb_video_configure_title_display();
    gb_video_hide_title_oam();

    gb_copy_u16(BG_COLORS, gb_title_bg_palette, GB_TITLE_BG_PALETTE_COUNT);
    gb_copy_u16((volatile u16*)CHAR_BASE_ADR(0), gb_title_bg_tiles, 0xD800 / 2);
    gb_copy_u16((volatile u16*)SPR_VRAM(0), gb_title_obj_tiles, GB_TITLE_OBJ_TILE_HALFWORDS);
    gb_copy_u16(OBJ_COLORS, gb_title_obj_palette, GB_TITLE_OBJ_PALETTE_COUNT);
    gb_copy_u16(OBJ_COLORS + 224, gb_title_obj_high_palette, GB_TITLE_OBJ_HIGH_PALETTE_COUNT);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG3_SCREENBLOCK), GB_STREAM_MAP_CELLS);

    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK);
    for(int y = 0; y < GB_TITLE_MAP_HEIGHT; ++y)
    {
        for(int x = 0; x < GB_TITLE_MAP_WIDTH; ++x)
        {
            map[y * 32 + x] = gb_title_map[y * GB_TITLE_MAP_WIDTH + x];
        }
    }

    volatile u16* backing_left = (volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK);
    volatile u16* backing_right = (volatile u16*)MAP_BASE_ADR(GB_BG3_SCREENBLOCK);
    for(int i = 0; i < GB_STREAM_MAP_CELLS; ++i)
    {
        backing_left[i] = gb_title_underlay_tile;
        backing_right[i] = gb_title_underlay_tile;
    }

    gb_video_title_set_animation(0);
    gb_video_title_set_prompt_visible(1);
}

static void gb_wardrobe_ui_upload(void)
{
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    for(int row = 0; row < GB_STORY_UI_ROWS; ++row)
    {
        for(int col = 0; col < GB_STORY_UI_COLUMNS; ++col)
        {
            const int slot = row * GB_STORY_UI_COLUMNS + col;
            const u16 tile_id = (u16)(1 + slot);
            volatile u16* tile = (volatile u16*)CHAR_BASE_ADR(0) + tile_id * 32;
            map[row * 32 + col] = tile_id;
            for(int py = 0; py < 8; ++py)
            {
                for(int pair = 0; pair < 4; ++pair)
                {
                    const int px = col * 8 + pair * 2;
                    const int source_y = row * 8 + py;
                    const u8 lo = gb_story_ui_pixels[source_y * GB_STORY_UI_WIDTH + px];
                    const u8 hi = gb_story_ui_pixels[source_y * GB_STORY_UI_WIDTH + px + 1];
                    tile[py * 4 + pair] = (u16)(lo | ((u16)hi << 8));
                }
            }
        }
    }
}

void gb_video_draw_wardrobe(u8 selector)
{
    if(selector >= GB_WARDROBE_CHOICE_COUNT)
    {
        selector = 0;
    }

    volatile u16* char_mem = (volatile u16*)CHAR_BASE_ADR(0);
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    volatile u16* oam = (volatile u16*)OAM;

    gb_copy_u16(char_mem + GB_WARDROBE_BG_VRAM_OFFSET / 2,
                gb_wardrobe_bg_pages[selector], GB_WARDROBE_BG_PAGE_HALFWORDS);

    for(int y = 0; y < GB_WARDROBE_BG_MAP_HEIGHT; ++y)
    {
        for(int x = 0; x < GB_WARDROBE_BG_MAP_WIDTH; ++x)
        {
            map[(GB_WARDROBE_BG_MAP_Y + y) * 32 + GB_WARDROBE_BG_MAP_X + x] =
                (u16)(GB_WARDROBE_BG_TILE_BASE + y * GB_WARDROBE_BG_MAP_WIDTH + x);
        }
    }

    gb_story_ui_begin();
    int tx = 0;
    int ty = 0;
    gb_story_ui_text("Wardrobe", &tx, &ty);
    gb_story_ui_newline(&tx, &ty);
    gb_story_ui_text(gb_wardrobe_labels[selector], &tx, &ty);
    gb_story_ui_newline(&tx, &ty);
    gb_story_ui_text("(B) to exit", &tx, &ty);
    gb_wardrobe_ui_upload();

    gb_video_hide_all_oam();
    for(int i = 0; i < GB_WARDROBE_CHOICE_COUNT; ++i)
    {
        const u16 logical_root = (u16)(GB_WARDROBE_PREVIEW_LOGICAL_BASE + i * 2u);
        const int x = 16 + i * 16;
        gb_stage_8bpp_16x32(logical_root, gb_wardrobe_preview_tiles[i]);

        /* 0x08008F26..0x08008F4E submits each 16x32 preview as two
           16x16 8bpp sprites in the gameplay 2D OBJ grid. */
        const int top_oam = i * 2;
        const int bottom_oam = top_oam + 1;
        oam[top_oam * 4] = (u16)GB_WARDROBE_PREVIEW_Y | GB_OBJ_256_COLOR;
        oam[top_oam * 4 + 1] = (u16)x | GB_OBJ_SIZE_1;
        oam[top_oam * 4 + 2] = (u16)(logical_root * 2u);
        oam[top_oam * 4 + 3] = 0;
        oam[bottom_oam * 4] = (u16)(GB_WARDROBE_PREVIEW_Y + 16) | GB_OBJ_256_COLOR;
        oam[bottom_oam * 4 + 1] = (u16)x | GB_OBJ_SIZE_1;
        oam[bottom_oam * 4 + 2] = (u16)((logical_root + 32u) * 2u);
        oam[bottom_oam * 4 + 3] = 0;
    }
}

void gb_video_load_wardrobe(void)
{
    /* The hidden Wardrobe is modal inside Player_update.  Its UI uses the
       Level-7 backdrop palette, but the active gameplay graphics descriptor
       remains the source for the continuing OBJ-lighting pass. */
    gb_video_set_camera(0, 0);
    BGCTRL[0] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) |
                SCREEN_BASE(GB_BG0_SCREENBLOCK) | BG_PRIORITY(0);
    gb_copy_u16(BG_COLORS, gb_level07_assets.bg_palette, 256);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG3_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_video_hide_all_oam();
    gb_video_draw_wardrobe(0);
}

static void gb_pda_text_clear(void)
{
    for(int i = 0; i < GB_PDA_TEXT_WIDTH * GB_PDA_TEXT_HEIGHT; ++i)
    {
        gb_pda_text_pixels[i] = 0;
    }
}

static void gb_pda_text_put_glyph(int x, int y, unsigned code)
{
    if(code >= GB_FONT_GLYPH_COUNT)
    {
        code = '?';
    }
    const GbFontGlyph* glyph = &gb_font_glyphs[code];
    for(int py = 0; py < 8 && y + py < GB_PDA_TEXT_HEIGHT; ++py)
    {
        const u16 row = glyph->rows[py];
        for(int px = 0; px < glyph->pixel_width && x + px < GB_PDA_TEXT_WIDTH; ++px)
        {
            if(row & (1u << px))
            {
                gb_pda_text_pixels[(y + py) * GB_PDA_TEXT_WIDTH + x + px] = GB_TEXT_FOREGROUND_INDEX;
            }
        }
    }
}

static int gb_pda_text_glyph_width(unsigned code)
{
    if(code >= GB_FONT_GLYPH_COUNT)
    {
        code = '?';
    }
    return gb_font_glyphs[code].pixel_width + 1;
}

static void gb_pda_text_newline(int* x, int* y)
{
    *x = 0;
    *y += 8;
}

static void gb_pda_text_write(const char* text, int* x, int* y)
{
    if(! text)
    {
        return;
    }
    while(*text && *y < GB_PDA_TEXT_HEIGHT)
    {
        unsigned code = (unsigned char)*text++;
        if(code == '\n')
        {
            gb_pda_text_newline(x, y);
            continue;
        }
        const int width = gb_pda_text_glyph_width(code);
        if(*x + width > GB_PDA_TEXT_WIDTH)
        {
            gb_pda_text_newline(x, y);
            if(*y >= GB_PDA_TEXT_HEIGHT)
            {
                break;
            }
        }
        gb_pda_text_put_glyph(*x, *y, code);
        *x += width;
    }
}

static void gb_pda_text_upload(void)
{
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    for(int row = 0; row < GB_PDA_TEXT_ROWS; ++row)
    {
        for(int col = 0; col < GB_PDA_TEXT_COLUMNS; ++col)
        {
            const int slot = row * GB_PDA_TEXT_COLUMNS + col;
            const u16 tile_id = gb_pda_text_tile_ids[slot];
            volatile u16* tile = (volatile u16*)CHAR_BASE_ADR(0) + tile_id * 32;
            map[(GB_PDA_TEXT_MAP_Y + row) * 32 + col] = tile_id;
            for(int py = 0; py < 8; ++py)
            {
                for(int pair = 0; pair < 4; ++pair)
                {
                    const int px = col * 8 + pair * 2;
                    const int source_y = row * 8 + py;
                    const u8 lo = gb_pda_text_pixels[source_y * GB_PDA_TEXT_WIDTH + px];
                    const u8 hi = gb_pda_text_pixels[source_y * GB_PDA_TEXT_WIDTH + px + 1];
                    tile[py * 4 + pair] = (u16)(lo | ((u16)hi << 8));
                }
            }
        }
    }
}

static const char* gb_pda_page_name(u8 page)
{
    switch(page)
    {
        case GB_PDA_MESSAGES: return "MESSAGES";
        case GB_PDA_STATUS: return "STATUS";
        case GB_PDA_FRIENDS: return "FRIENDS";
        case GB_PDA_BACKPACK: return "BACKPACK";
        default: return "MESSAGES";
    }
}

static const GbMessageRecord* gb_pda_message(const GbPdaRuntime* pda, const GbStoryRuntime* story)
{
    if(! pda || ! story)
    {
        return 0;
    }
    if(pda->message_slot == 0)
    {
        return gb_story_message_primary(story);
    }
    if(pda->message_slot <= 3)
    {
        return gb_story_message_auxiliary(story, (u8)(pda->message_slot - 1));
    }
    return 0;
}

void gb_video_draw_pda(const GbPdaRuntime* pda, const GbStoryRuntime* story)
{
    if(! pda)
    {
        return;
    }
    u8 page = pda->page;
    if(page >= GB_PDA_PAGE_COUNT)
    {
        page = GB_PDA_MESSAGES;
    }

    volatile u16* text_map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    volatile u16* chrome = (volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK);
    gb_clear_u16(text_map, GB_STREAM_MAP_CELLS);
    gb_clear_u16(chrome, GB_STREAM_MAP_CELLS);
    for(int y = 0; y < GB_PDA_MAP_HEIGHT; ++y)
    {
        for(int x = 0; x < GB_PDA_MAP_WIDTH; ++x)
        {
            chrome[y * 32 + x] = gb_pda_page_maps[page][y * GB_PDA_MAP_WIDTH + x];
        }
    }

    gb_pda_text_clear();
    int x = 0;
    int y = 0;
    gb_pda_text_write(gb_pda_page_name(page), &x, &y);

    if(page == GB_PDA_MESSAGES)
    {
        const GbMessageRecord* message = gb_pda_message(pda, story);
        if(message)
        {
            gb_pda_text_newline(&x, &y);
            gb_pda_text_write(message->title, &x, &y);
            gb_pda_text_newline(&x, &y);
            gb_pda_text_write("FROM: ", &x, &y);
            gb_pda_text_write(message->sender, &x, &y);
            gb_pda_text_newline(&x, &y);
            gb_pda_text_write(message->body, &x, &y);
        }
    }
    else if(page == GB_PDA_FRIENDS)
    {
        for(u8 row = 0; row < 3; ++row)
        {
            gb_pda_text_newline(&x, &y);
            gb_pda_text_write(row == pda->friends_cursor ? "> " : "  ", &x, &y);
            const u8 friend_index = gb_pda_friend_index(pda, row);
            if(friend_index < GB_PDA_FRIEND_COUNT)
            {
                gb_pda_text_write(gb_pda_friend_names[friend_index], &x, &y);
            }
        }
    }
    gb_pda_text_upload();
}

void gb_video_load_pda(const GbLevelAssets* level, const GbPdaRuntime* pda, const GbStoryRuntime* story)
{
    gb_video_level = level;
    gb_video_configure_pda_display();
    gb_video_hide_all_oam();
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG3_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_video_draw_pda(pda, story);
}

void gb_video_load_level(const GbLevelAssets* level)
{
    gb_video_configure_gameplay_display();
    gb_video_set_camera(0, 0);
    gb_video_restore_gameplay_obj_assets();
    gb_video_level = level;
    gb_copy_u16(BG_COLORS, level->bg_palette, 256);
    /* 0x08005A2C applies a full 0..247 lighting pass after the level
       graphics loader has installed its fixed high-32 OBJ patch. */
    gb_video_transform_gameplay_obj_palette(0, 247, gb_gameplay_lighting_clock);
    gb_copy_u16((volatile u16*)CHAR_BASE_ADR(0), level->bg_tiles, level->bg_tile_halfwords);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_load_fixed_maps(level);
}

void gb_video_gameplay_lighting_reset_cursor(void)
{
    /* Player_constructor zeroes Player+0x398.  Keep the global day/night
       clock intact; only the Player-owned amortized palette cursor restarts. */
    gb_gameplay_lighting_cursor = 0;
}

void gb_video_gameplay_lighting_tick(int advance_clock)
{
    if(! gb_video_level)
    {
        return;
    }

    /* Player_update always advances the amortized palette cursor, but the
       day/night clock pauses while 0x03000610 (interaction-active) is set.
       When it does advance, the original permits 86,400 for one update; only
       values >86,399 at the start of the following update wrap to zero first. */
    if(advance_clock)
    {
        if(gb_gameplay_lighting_clock > 86399u)
        {
            gb_gameplay_lighting_clock = 0;
        }
        ++gb_gameplay_lighting_clock;
    }

    u16 start;
    if(gb_gameplay_lighting_cursor > 246u)
    {
        gb_gameplay_lighting_cursor = 0;
        start = 0;
    }
    else
    {
        gb_gameplay_lighting_cursor = (u16)(gb_gameplay_lighting_cursor + 4u);
        start = gb_gameplay_lighting_cursor;
    }
    gb_video_transform_gameplay_obj_palette(start, 4, gb_gameplay_lighting_clock);
}

void gb_video_stream_full(const GbLevelAssets* level, s16 left, s16 top)
{
    gb_stream_fill(level, level->layer_a, left, top, (volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK));
    gb_stream_fill(level, level->layer_b, left, top, (volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK));
}

void gb_video_stream_column(const GbLevelAssets* level, s16 world_x, s16 top)
{
    gb_stream_fill_column(level, level->layer_a, world_x, top, (volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK));
    gb_stream_fill_column(level, level->layer_b, world_x, top, (volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK));
}

void gb_video_stream_row(const GbLevelAssets* level, s16 left, s16 world_y)
{
    gb_stream_fill_row(level, level->layer_a, left, world_y, (volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK));
    gb_stream_fill_row(level, level->layer_b, left, world_y, (volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK));
}

void gb_video_set_camera(s16 x, s16 y)
{
    BG_OFFSET[0].x = 0;
    BG_OFFSET[0].y = 0;
    BG_OFFSET[1].x = (u16)x;
    BG_OFFSET[1].y = (u16)y;
    BG_OFFSET[2].x = (u16)x;
    BG_OFFSET[2].y = (u16)y;
    BG_OFFSET[3].x = (u16)(x / 4);
    BG_OFFSET[3].y = (u16)(y / 4);
}

static int gb_actor_npc_visual_index(const GbActor* actor)
{
    if(! actor || ! actor->descriptor)
    {
        return -1;
    }
    for(int i = 0; i < GB_ACTOR_VISUAL_COUNT; ++i)
    {
        if(gb_actor_visuals[i].legs_color == actor->visual_legs_color &&
           gb_actor_visuals[i].subtype == actor->descriptor->subtype)
        {
            return i;
        }
    }
    return -1;
}

static int gb_video_sprite_visible_16(s16 x, s16 y)
{
    return x >= -16 && x < 240 && y >= -16 && y < 160;
}

static void gb_video_hide_oam_entry(volatile u16* oam, int index)
{
    oam[index * 4] = 160;
    oam[index * 4 + 1] = 0;
    oam[index * 4 + 2] = 0;
    oam[index * 4 + 3] = 0;
}

static int gb_video_npc_draw_dispatched(const GbActor* actor, s16 camera_x, s16 camera_y)
{
    if(actor->descriptor->setglobal == 0)
    {
        return 1;
    }

    /* Inherited object-manager culling at 0x08001642 uses the NPC's
       constructor-proven 16x32 fixed8 body.  +0x31 bypasses this path; the
       common actor parser sets +0x31 only for explicit setglobal == 0. */
    const s16 left = gb_actor_pixel_x(actor);
    const s16 right = (s16)(left + 16);
    const s16 bottom = gb_actor_pixel_y(actor);
    const s16 top = (s16)(bottom - 32);
    return right >= camera_x && left <= (s16)(camera_x + 240) &&
           bottom >= camera_y && top <= (s16)(camera_y + 160);
}

typedef struct {
    int oam_cursor;
    u8 actor_oam_used;
    u8 slots_used;
} GbGameplayOamCursor;

static void gb_video_draw_actor_range(GbActorSystem* system, const GbPlayer* player,
                                      s16 camera_x, s16 camera_y, u8 begin, u8 end,
                                      GbGameplayOamCursor* cursor)
{
    volatile u16* oam = (volatile u16*)OAM;

    if(end > system->count)
    {
        end = system->count;
    }
    for(u8 i = begin;
        i < end && cursor->actor_oam_used < GB_ACTOR_OAM_COUNT &&
        cursor->oam_cursor < GB_ACTOR_OAM_FIRST + GB_ACTOR_OAM_COUNT;
        ++i)
    {
        GbActor* actor = &system->actors[i];
        if(! actor->active || ! actor->descriptor)
        {
            continue;
        }

        if(actor->descriptor->actor_class == GB_ACTOR_NPC)
        {
            if(! gb_video_npc_draw_dispatched(actor, camera_x, camera_y) ||
               ! gb_actor_npc_should_draw(actor))
            {
                continue;
            }
            const int visual = gb_actor_npc_visual_index(actor);
            if(visual < 0)
            {
                continue;
            }
            const u8 frame = gb_actor_npc_frame_for_draw(actor);
            const s16 sx = (s16)(gb_actor_pixel_x(actor) - camera_x);
            const s16 bottom_y = (s16)(gb_actor_pixel_y(actor) - camera_y - 16);
            const s16 top_y = (s16)(bottom_y - 16);
            const int bottom_visible = gb_video_sprite_visible_16(sx, bottom_y);
            const int top_visible = gb_video_sprite_visible_16(sx, top_y);
            if(! bottom_visible && ! top_visible)
            {
                continue;
            }
            u16 logical_root;
            if(! gb_npc_obj_logical_root(cursor->slots_used, &logical_root))
            {
                continue;
            }
            const u32 frame_index = (u32)visual * GB_ACTOR_MAX_FRAMES + (frame - 1);
            const u16 tile_base = (u16)(logical_root * 2u);
            const u16 priority = (u16)((gb_actor_pixel_y(actor) > player->y ? 1u : 2u) << 10);
            const u16 hflip = actor->facing_right ? GB_OBJ_HFLIP : 0;
            gb_stage_8bpp_16x32(logical_root,
                                gb_actor_obj_frames + frame_index * GB_ACTOR_FRAME_HALFWORDS);
            if(bottom_visible && cursor->actor_oam_used < GB_ACTOR_OAM_COUNT &&
               cursor->oam_cursor < GB_ACTOR_OAM_FIRST + GB_ACTOR_OAM_COUNT)
            {
                const int oam_index = cursor->oam_cursor++;
                ++cursor->actor_oam_used;
                oam[oam_index * 4] = (u16)(bottom_y & 0x00FF) | GB_OBJ_256_COLOR;
                oam[oam_index * 4 + 1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_1 | hflip;
                oam[oam_index * 4 + 2] = (u16)(tile_base + 64u) | priority;
                oam[oam_index * 4 + 3] = 0;
            }
            if(top_visible && cursor->actor_oam_used < GB_ACTOR_OAM_COUNT &&
               cursor->oam_cursor < GB_ACTOR_OAM_FIRST + GB_ACTOR_OAM_COUNT)
            {
                const int oam_index = cursor->oam_cursor++;
                ++cursor->actor_oam_used;
                oam[oam_index * 4] = (u16)(top_y & 0x00FF) | GB_OBJ_256_COLOR;
                oam[oam_index * 4 + 1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_1 | hflip;
                oam[oam_index * 4 + 2] = tile_base | priority;
                oam[oam_index * 4 + 3] = 0;
            }
            ++cursor->slots_used;
        }
        else if(actor->descriptor->actor_class == GB_ACTOR_GRASS && player)
        {
            GbGrassDrawState draw;
            if(! gb_actor_grass_draw_state(actor, player->y, &draw))
            {
                continue;
            }
            const s16 sx = (s16)(gb_actor_pixel_x(actor) - camera_x);
            const s16 sy = (s16)(gb_actor_pixel_y(actor) - 16 - camera_y);
            if(! gb_video_sprite_visible_16(sx, sy))
            {
                continue;
            }
            const int oam_index = cursor->oam_cursor++;
            oam[oam_index * 4] = (u16)(sy & 0x00FF) | GB_OBJ_256_COLOR;
            oam[oam_index * 4 + 1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_1 |
                                     (draw.hflip ? GB_OBJ_HFLIP : 0);
            oam[oam_index * 4 + 2] = (u16)(GB_GRASS_LOGICAL_TILE * 2u) |
                                     ((u16)draw.priority << 10);
            oam[oam_index * 4 + 3] = 0;
            ++cursor->actor_oam_used;
        }
    }
}

static void gb_video_draw_leaf_particles(GbActorSystem* system, s16 camera_x, s16 camera_y,
                                         GbGameplayOamCursor* cursor)
{
    volatile u16* oam = (volatile u16*)OAM;
    for(int i = 0;
        i < GB_LEAF_PARTICLE_CAPACITY && cursor->actor_oam_used < GB_ACTOR_OAM_COUNT &&
        cursor->oam_cursor < GB_ACTOR_OAM_FIRST + GB_ACTOR_OAM_COUNT;
        ++i)
    {
        GbLeafParticle* particle = &system->leaf_particles[i];
        if(! particle->active)
        {
            continue;
        }
        const u8 frame = gb_leaf_particle_frame_for_draw(particle);
        const s16 sx = (s16)(gb_leaf_particle_pixel_x(particle) - 4 - camera_x);
        const s16 sy = (s16)(gb_leaf_particle_pixel_y(particle) - 8 - camera_y);
        if(sx < -8 || sx >= 240 || sy < -8 || sy >= 160)
        {
            continue;
        }
        static const u16 leaf_roots[GB_LEAF_FRAME_COUNT] = { 0x4C, 0x4D, 0x5C, 0x5D };
        const int oam_index = cursor->oam_cursor++;
        oam[oam_index * 4] = (u16)(sy & 0x00FF) | GB_OBJ_256_COLOR;
        oam[oam_index * 4 + 1] = (u16)(sx & 0x01FF);
        oam[oam_index * 4 + 2] = (u16)(leaf_roots[frame] * 2u);
        oam[oam_index * 4 + 3] = 0;
        ++cursor->actor_oam_used;
    }
}

void gb_video_draw_actors(GbActorSystem* system, const GbPlayer* player, s16 camera_x, s16 camera_y)
{
    volatile u16* oam = (volatile u16*)OAM;
    GbGameplayOamCursor cursor = { GB_ACTOR_OAM_FIRST, 0, 0 };
    for(int i = 0; i < GB_ACTOR_OAM_COUNT; ++i)
    {
        gb_video_hide_oam_entry(oam, GB_ACTOR_OAM_FIRST + i);
    }
    gb_video_draw_actor_range(system, player, camera_x, camera_y, 0, system->count, &cursor);
    gb_video_draw_leaf_particles(system, camera_x, camera_y, &cursor);
}

static const s8 gb_player_prompt_bob[32] = {
    0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 4, 4, 4, 4,
    5, 5, 5, 5, 5, 4, 4, 4, 4, 3, 3, 2, 2, 1, 1, 1,
};

static int gb_video_story_suppresses_prompt(const GbStoryRuntime* story)
{
    return story && (story->dialogue.active || story->social.state != GB_SOCIAL_INACTIVE);
}

static int gb_video_draw_interaction_prompt(const GbPlayer* player, const GbStoryRuntime* story,
                                            s16 camera_x, s16 camera_y, int first_oam)
{
    if(! player || ! player->interaction_available || gb_video_story_suppresses_prompt(story))
    {
        return 0;
    }
    const s16 sx = (s16)(player->x - camera_x + 20);
    const s16 sy = (s16)(player->y - camera_y - 32 +
                         gb_player_prompt_bob[player->prompt_bob_phase & 31u]);
    volatile u16* oam = (volatile u16*)OAM;
    if(gb_video_sprite_visible_16(sx, sy))
    {
        const int o = first_oam * 4;
        oam[o] = (u16)(sy & 0x00FF) | GB_OBJ_256_COLOR;
        oam[o + 1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_1;
        oam[o + 2] = (u16)(GB_PLAYER_INTERACTION_LOGICAL_TILE * 2u);
        oam[o + 3] = 0;
    }
    else
    {
        gb_video_hide_oam_entry(oam, first_oam);
    }
    return 1;
}

static void gb_video_draw_player_oam(const GbPlayer* player, s16 camera_x, s16 camera_y, int first_oam)
{
    const s16 sx = (s16)(player->x - camera_x);
    const s16 bottom_y = (s16)(player->y - camera_y - 16);
    const s16 top_y = (s16)(bottom_y - 16);
    const u8 frame_index = gb_player_frame_index(player);
    const u16 attr1 = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_1 |
                      (player->facing_right ? GB_OBJ_HFLIP : 0);
    const u16 priority = (u16)(2u << 10);
    volatile u16* oam = (volatile u16*)OAM;
    gb_stage_8bpp_16x32(GB_PLAYER_TOP_LOGICAL_TILE,
                        gb_player_obj_tiles + (u32)frame_index * GB_PLAYER_FRAME_HALFWORDS);

    if(gb_video_sprite_visible_16(sx, bottom_y))
    {
        const int o = first_oam * 4;
        oam[o] = (u16)(bottom_y & 0x00FF) | GB_OBJ_256_COLOR;
        oam[o + 1] = attr1;
        oam[o + 2] = (u16)(GB_PLAYER_BOTTOM_LOGICAL_TILE * 2u) | priority;
        oam[o + 3] = 0;
    }
    else
    {
        gb_video_hide_oam_entry(oam, first_oam);
    }

    if(gb_video_sprite_visible_16(sx, top_y))
    {
        const int o = (first_oam + 1) * 4;
        oam[o] = (u16)(top_y & 0x00FF) | GB_OBJ_256_COLOR;
        oam[o + 1] = attr1;
        oam[o + 2] = (u16)(GB_PLAYER_TOP_LOGICAL_TILE * 2u) | priority;
        oam[o + 3] = 0;
    }
    else
    {
        gb_video_hide_oam_entry(oam, first_oam + 1);
    }
}

void gb_video_draw_player(const GbPlayer* player, s16 camera_x, s16 camera_y)
{
    gb_video_draw_player_oam(player, camera_x, camera_y, 0);
}

static void gb_story_ui_fill(u8 value)
{
    for(int i = 0; i < GB_STORY_UI_WIDTH * GB_STORY_UI_HEIGHT; ++i)
    {
        gb_story_ui_pixels[i] = value;
    }
}

static void gb_story_ui_put_glyph(int x, int y, unsigned code)
{
    if(code >= GB_FONT_GLYPH_COUNT || y < 0 || y + 8 > GB_STORY_UI_HEIGHT)
    {
        return;
    }
    const GbFontGlyph* glyph = &gb_font_glyphs[code];
    for(int py = 0; py < 8; ++py)
    {
        const u16 mask = glyph->rows[py];
        for(int px = 0; px < glyph->pixel_width; ++px)
        {
            const int dx = x + px;
            if(dx >= 0 && dx < GB_STORY_UI_WIDTH)
            {
                gb_story_ui_pixels[(y + py) * GB_STORY_UI_WIDTH + dx] =
                    (mask & (u16)(1u << px)) ? GB_TEXT_FOREGROUND_INDEX : GB_TEXT_BACKGROUND_INDEX;
            }
        }
    }
}

static int gb_story_ui_glyph_width(unsigned code)
{
    if(code >= GB_FONT_GLYPH_COUNT || gb_font_glyphs[code].pixel_width == 0)
    {
        return 4;
    }
    return gb_font_glyphs[code].pixel_width;
}

static void gb_story_ui_newline(int* x, int* y)
{
    *x = 0;
    *y += 8;
}

static void gb_story_ui_text(const char* text, int* x, int* y)
{
    if(! text)
    {
        return;
    }
    while(*text && *y < GB_STORY_UI_HEIGHT)
    {
        const unsigned code = (unsigned char)*text++;
        if(code == '\n')
        {
            gb_story_ui_newline(x, y);
            continue;
        }
        const int width = gb_story_ui_glyph_width(code);
        if(*x + width > GB_STORY_UI_WIDTH)
        {
            gb_story_ui_newline(x, y);
            if(*y >= GB_STORY_UI_HEIGHT)
            {
                break;
            }
        }
        gb_story_ui_put_glyph(*x, *y, code);
        *x += width;
    }
}

static void gb_dialogue_ui_fill(u8 value)
{
    for(int i = 0; i < GB_DIALOGUE_TEXT_WIDTH * GB_DIALOGUE_TEXT_HEIGHT; ++i)
    {
        gb_dialogue_text_pixels[i] = value;
    }
}

static void gb_dialogue_ui_put_glyph(int x, int y, unsigned code)
{
    if(code >= GB_FONT_GLYPH_COUNT || y < 0 || y + 8 > GB_DIALOGUE_TEXT_HEIGHT)
    {
        return;
    }
    const GbFontGlyph* glyph = &gb_font_glyphs[code];
    for(int py = 0; py < 8; ++py)
    {
        const u16 mask = glyph->rows[py];
        for(int px = 0; px < glyph->pixel_width; ++px)
        {
            const int dx = x + px;
            if(dx >= 0 && dx < GB_DIALOGUE_TEXT_WIDTH)
            {
                gb_dialogue_text_pixels[(y + py) * GB_DIALOGUE_TEXT_WIDTH + dx] =
                    (mask & (u16)(1u << px)) ? GB_TEXT_FOREGROUND_INDEX : GB_TEXT_BACKGROUND_INDEX;
            }
        }
    }
}

static void gb_dialogue_ui_newline(int* x, int* y)
{
    *x = 0;
    *y += 8;
}

static int gb_dialogue_ui_word_width(const char* text)
{
    int width = 0;
    while(text && *text && *text != ' ' && *text != '\n')
    {
        width += gb_story_ui_glyph_width((unsigned char)*text++);
    }
    return width;
}

static void gb_dialogue_ui_text(const char* text, int* x, int* y)
{
    if(! text)
    {
        return;
    }
    int at_word_start = 1;
    while(*text && *y < GB_DIALOGUE_TEXT_HEIGHT)
    {
        /* The ROM's TextObject writer measures the complete upcoming word at
           its first glyph.  If it cannot fit, move the whole word before any
           pixels are emitted; a space that would lead the new row is dropped. */
        if(at_word_start && *text != ' ' && *text != '\n')
        {
            const int word_width = gb_dialogue_ui_word_width(text);
            if(*x > 0 && *x + word_width > GB_DIALOGUE_TEXT_WIDTH)
            {
                gb_dialogue_ui_newline(x, y);
                if(*y >= GB_DIALOGUE_TEXT_HEIGHT)
                {
                    break;
                }
            }
        }

        const unsigned code = (unsigned char)*text++;
        if(code == '\n')
        {
            gb_dialogue_ui_newline(x, y);
            at_word_start = 1;
            continue;
        }
        if(code == ' ')
        {
            at_word_start = 1;
            if(*x == 0)
            {
                continue;
            }
        }
        else
        {
            at_word_start = 0;
        }
        const int width = gb_story_ui_glyph_width(code);
        if(*x + width > GB_DIALOGUE_TEXT_WIDTH)
        {
            gb_dialogue_ui_newline(x, y);
            if(*y >= GB_DIALOGUE_TEXT_HEIGHT)
            {
                break;
            }
        }
        gb_dialogue_ui_put_glyph(*x, *y, code);
        *x += width;
    }
}

static void gb_dialogue_ui_upload_at(int window_x, int window_y)
{
    if(! gb_video_level || ! gb_video_level->bg0_ui_tiles)
    {
        return;
    }
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);

    /* Window 0x08009Cxx: (1,13), 20x6. Tiles 3/4/5 are the original
       vertical edge, corner and horizontal edge artwork. */
    map[window_y * 32 + window_x] = GB_DIALOGUE_BORDER_CORNER_TILE;
    map[window_y * 32 + window_x + GB_DIALOGUE_WINDOW_COLUMNS - 1] =
        GB_DIALOGUE_BORDER_CORNER_TILE | GB_BG_MAP_HFLIP;
    map[(window_y + GB_DIALOGUE_WINDOW_ROWS - 1) * 32 + window_x] =
        GB_DIALOGUE_BORDER_CORNER_TILE | GB_BG_MAP_VFLIP;
    map[(window_y + GB_DIALOGUE_WINDOW_ROWS - 1) * 32 +
        window_x + GB_DIALOGUE_WINDOW_COLUMNS - 1] =
        GB_DIALOGUE_BORDER_CORNER_TILE | GB_BG_MAP_HFLIP | GB_BG_MAP_VFLIP;

    for(int col = 1; col < GB_DIALOGUE_WINDOW_COLUMNS - 1; ++col)
    {
        map[window_y * 32 + window_x + col] =
            GB_DIALOGUE_BORDER_HORIZONTAL_TILE;
        map[(window_y + GB_DIALOGUE_WINDOW_ROWS - 1) * 32 +
            window_x + col] = GB_DIALOGUE_BORDER_HORIZONTAL_TILE | GB_BG_MAP_VFLIP;
    }
    for(int row = 1; row < GB_DIALOGUE_WINDOW_ROWS - 1; ++row)
    {
        map[(window_y + row) * 32 + window_x] =
            GB_DIALOGUE_BORDER_VERTICAL_TILE;
        map[(window_y + row) * 32 +
            window_x + GB_DIALOGUE_WINDOW_COLUMNS - 1] =
            GB_DIALOGUE_BORDER_VERTICAL_TILE | GB_BG_MAP_HFLIP;
    }

    for(int row = 0; row < GB_DIALOGUE_TEXT_ROWS; ++row)
    {
        for(int col = 0; col < GB_DIALOGUE_TEXT_COLUMNS; ++col)
        {
            const int slot = row * GB_DIALOGUE_TEXT_COLUMNS + col;
            const u16 tile_id = gb_video_level->bg0_ui_tiles[slot];
            volatile u16* tile = (volatile u16*)CHAR_BASE_ADR(0) + tile_id * 32;
            map[((window_y + 1) + row) * 32 + (window_x + 1) + col] = tile_id;
            for(int py = 0; py < 8; ++py)
            {
                for(int pair = 0; pair < 4; ++pair)
                {
                    const int px = col * 8 + pair * 2;
                    const int source_y = row * 8 + py;
                    const u8 lo = gb_dialogue_text_pixels[source_y * GB_DIALOGUE_TEXT_WIDTH + px];
                    const u8 hi = gb_dialogue_text_pixels[source_y * GB_DIALOGUE_TEXT_WIDTH + px + 1];
                    tile[py * 4 + pair] = (u16)(lo | ((u16)hi << 8));
                }
            }
        }
    }
}

static void gb_dialogue_ui_upload(void)
{
    gb_dialogue_ui_upload_at(GB_DIALOGUE_WINDOW_MAP_X, GB_DIALOGUE_WINDOW_MAP_Y);
}

static void gb_story_ui_upload(void)
{
    if(! gb_video_level || ! gb_video_level->bg0_ui_tiles)
    {
        return;
    }
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    for(int row = 0; row < GB_STORY_UI_ROWS; ++row)
    {
        for(int col = 0; col < GB_STORY_UI_COLUMNS; ++col)
        {
            const int slot = row * GB_STORY_UI_COLUMNS + col;
            const u16 tile_id = gb_video_level->bg0_ui_tiles[slot];
            volatile u16* tile = (volatile u16*)CHAR_BASE_ADR(0) + tile_id * 32;
            map[(GB_STORY_UI_MAP_Y + row) * 32 + col] = tile_id;
            for(int py = 0; py < 8; ++py)
            {
                for(int pair = 0; pair < 4; ++pair)
                {
                    const int px = col * 8 + pair * 2;
                    const int source_y = row * 8 + py;
                    const u8 lo = gb_story_ui_pixels[source_y * GB_STORY_UI_WIDTH + px];
                    const u8 hi = gb_story_ui_pixels[source_y * GB_STORY_UI_WIDTH + px + 1];
                    tile[py * 4 + pair] = (u16)(lo | ((u16)hi << 8));
                }
            }
        }
    }
}

void gb_video_clear_story_ui(void)
{
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    for(int row = 0; row < GB_STORY_UI_ROWS; ++row)
    {
        for(int col = 0; col < GB_STORY_UI_COLUMNS; ++col)
        {
            map[(GB_STORY_UI_MAP_Y + row) * 32 + col] = 0;
        }
    }
    for(int row = 0; row < GB_SOCIAL_SELECTOR_MAP_HEIGHT; ++row)
    {
        for(int col = 0; col < GB_SOCIAL_SELECTOR_MAP_WIDTH; ++col)
        {
            map[(GB_SOCIAL_SELECTOR_MAP_Y + row) * 32 +
                GB_SOCIAL_SELECTOR_MAP_X + col] = 0;
        }
    }
    for(int row = 0; row < GB_SOCIAL_TOPIC_CLEAR_HEIGHT; ++row)
    {
        for(int col = 0; col < GB_SOCIAL_TOPIC_CLEAR_WIDTH; ++col)
        {
            map[(GB_SOCIAL_TOPIC_CLEAR_Y + row) * 32 +
                GB_SOCIAL_TOPIC_CLEAR_X + col] = 0;
        }
    }
    for(int row = 0; row < GB_DIALOGUE_WINDOW_ROWS; ++row)
    {
        for(int col = 0; col < GB_DIALOGUE_WINDOW_COLUMNS; ++col)
        {
            map[(GB_DIALOGUE_WINDOW_MAP_Y + row) * 32 + GB_DIALOGUE_WINDOW_MAP_X + col] = 0;
            map[(GB_SOCIAL_RESPONSE_WINDOW_MAP_Y + row) * 32 +
                GB_SOCIAL_RESPONSE_WINDOW_MAP_X + col] = 0;
        }
    }
}

static void gb_story_ui_begin(void)
{
    gb_story_ui_fill(GB_TEXT_BACKGROUND_INDEX);
}

static void gb_story_ui_draw_dialogue(const GbStoryRuntime* story)
{
    const GbDialogueRecord* record = gb_story_dialogue_record(story);
    if(! record)
    {
        gb_video_clear_story_ui();
        return;
    }
    int x = 0;
    int y = 0;
    gb_dialogue_ui_fill(GB_TEXT_BACKGROUND_INDEX);
    if(record->speaker && record->speaker[0])
    {
        gb_dialogue_ui_text(record->speaker, &x, &y);
        gb_dialogue_ui_text(":                              ", &x, &y);
    }
    gb_dialogue_ui_text(record->text, &x, &y);
    gb_dialogue_ui_upload();
}

static void gb_story_ui_draw_social_response(const GbStoryRuntime* story)
{
    int x = 0;
    int y = 0;
    gb_dialogue_ui_fill(GB_TEXT_BACKGROUND_INDEX);
    const char* profile = gb_story_social_profile_name(story);
    if(profile)
    {
        gb_dialogue_ui_text(profile, &x, &y);
        gb_dialogue_ui_text(":                              ", &x, &y);
    }
    if(story->social.response_text)
    {
        gb_dialogue_ui_text(story->social.response_text, &x, &y);
    }
    gb_dialogue_ui_upload_at(GB_SOCIAL_RESPONSE_WINDOW_MAP_X,
                             GB_SOCIAL_RESPONSE_WINDOW_MAP_Y);
}

static void gb_social_text_upload_row(const char* text, s16 map_x, s16 map_y,
                                      u8 background, u8 foreground, u16 slot_base)
{
    if(! gb_video_level || ! gb_video_level->bg0_ui_tiles ||
       slot_base + GB_SOCIAL_TEXT_COLUMNS > GB_BG0_UI_TILE_COUNT)
    {
        return;
    }
    for(int i = 0; i < GB_SOCIAL_TEXT_WIDTH * 8; ++i)
    {
        gb_social_text_pixels[i] = background;
    }
    int cursor_x = 0;
    while(text && *text && cursor_x < GB_SOCIAL_TEXT_WIDTH)
    {
        const unsigned code = (unsigned char)*text++;
        const int width = gb_story_ui_glyph_width(code);
        if(code >= GB_FONT_GLYPH_COUNT || cursor_x + width > GB_SOCIAL_TEXT_WIDTH)
        {
            break;
        }
        const GbFontGlyph* glyph = &gb_font_glyphs[code];
        for(int py = 0; py < 8; ++py)
        {
            const u16 mask = glyph->rows[py];
            for(int px = 0; px < glyph->pixel_width; ++px)
            {
                gb_social_text_pixels[py * GB_SOCIAL_TEXT_WIDTH + cursor_x + px] =
                    (mask & (u16)(1u << px)) ? foreground : background;
            }
        }
        cursor_x += width;
    }

    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    for(u16 col = 0; col < GB_SOCIAL_TEXT_COLUMNS; ++col)
    {
        const u16 tile_id = gb_video_level->bg0_ui_tiles[slot_base + col];
        volatile u16* tile = (volatile u16*)CHAR_BASE_ADR(0) + tile_id * 32;
        map[map_y * 32 + map_x + col] = tile_id;
        for(int py = 0; py < 8; ++py)
        {
            for(int pair = 0; pair < 4; ++pair)
            {
                const int px = col * 8 + pair * 2;
                const u8 lo = gb_social_text_pixels[py * GB_SOCIAL_TEXT_WIDTH + px];
                const u8 hi = gb_social_text_pixels[py * GB_SOCIAL_TEXT_WIDTH + px + 1];
                tile[py * 4 + pair] = (u16)(lo | ((u16)hi << 8));
            }
        }
    }
}

static void gb_social_selector_upload_map(const GbStoryRuntime* story)
{
    if(! story || story->social.selected_quadrant >= GB_SOCIAL_SELECTOR_STATE_COUNT)
    {
        return;
    }
    volatile u16* map = (volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK);
    const u16* source = gb_social_selector_maps +
                        (u32)story->social.selected_quadrant * GB_SOCIAL_SELECTOR_MAP_CELLS;
    for(u16 y = 0; y < GB_SOCIAL_SELECTOR_MAP_HEIGHT; ++y)
    {
        for(u16 x = 0; x < GB_SOCIAL_SELECTOR_MAP_WIDTH; ++x)
        {
            map[(GB_SOCIAL_SELECTOR_MAP_Y + y) * 32 + GB_SOCIAL_SELECTOR_MAP_X + x] =
                source[y * GB_SOCIAL_SELECTOR_MAP_WIDTH + x];
        }
    }
}

static void gb_social_selector_upload_label(const GbStoryRuntime* story)
{
    if(! story || story->social.selected_quadrant >= 4)
    {
        return;
    }
    const u8 action_index = (u8)(story->social.page_base + story->social.selected_quadrant);
    if(action_index >= GB_SOCIAL_ACTION_COUNT)
    {
        return;
    }
    static const s16 label_x[4] = { 8, 11, 8, 5 };
    static const s16 label_y[4] = { 10, 13, 16, 13 };
    gb_social_text_upload_row(gb_social_actions[action_index].label,
                              label_x[story->social.selected_quadrant],
                              label_y[story->social.selected_quadrant],
                              9, 2, 0);
}

static const char* gb_social_selector_topic_text(u8 action_index, u8 topic_index)
{
    if(action_index == 4 && topic_index < GB_SOCIAL_SUBJECT_TOPIC_COUNT)
    {
        return gb_social_subject_topics[topic_index];
    }
    if(action_index == 5 && topic_index < GB_SOCIAL_ASK_TOPIC_COUNT)
    {
        return gb_social_ask_topics[topic_index];
    }
    if(action_index == 7 && topic_index < GB_SOCIAL_CRITICIZE_TOPIC_COUNT)
    {
        return gb_social_criticize_topics[topic_index];
    }
    return 0;
}

static void gb_social_selector_upload_topics(const GbStoryRuntime* story)
{
    if(! story || story->social.selected_quadrant >= 4)
    {
        return;
    }
    const u8 quadrant = story->social.selected_quadrant;
    const u8 action_index = (u8)(story->social.page_base + quadrant);
    if(action_index >= GB_SOCIAL_ACTION_COUNT)
    {
        return;
    }
    u8 topic_count = story->social.topic_count;
    if(topic_count > 9)
    {
        topic_count = 9;
    }
    static const s16 label_x[4] = { 8, 11, 8, 5 };
    static const s16 label_y[4] = { 10, 13, 16, 13 };
    for(u8 i = 0; i < topic_count; ++i)
    {
        const char* text = gb_social_selector_topic_text(action_index, i);
        if(! text)
        {
            continue;
        }
        const s16 map_y = (s16)(label_y[quadrant] - topic_count + i);
        const int selected = i == story->social.topic_index;
        gb_social_text_upload_row(text, label_x[quadrant], map_y,
                                  selected ? 7 : 9, selected ? 6 : 2,
                                  8u + (u16)i * GB_SOCIAL_TEXT_COLUMNS);
    }
}

static int gb_video_draw_social_reaction(const GbPlayer* player,
                                         const GbStoryRuntime* story,
                                         s16 camera_x, s16 camera_y, int first_oam)
{
    if(! player || ! story || story->social.state != GB_SOCIAL_POST_DELAY ||
       (story->social.selected_quadrant != 0 && story->social.selected_quadrant != 3) ||
       story->social.profile_selector >= GB_SOCIAL_PROFILE_COUNT ||
       story->social.topic_index >= 9)
    {
        return 0;
    }

    s16 reaction_class = story->state.social_profiles[story->social.profile_selector]
                             .topic_class[story->social.topic_index];
    if(reaction_class < 0 || reaction_class >= GB_SOCIAL_REACTION_FACE_COUNT)
    {
        return 0;
    }
    if(story->social.selected_quadrant == 3)
    {
        reaction_class = (s16)(4 - reaction_class);
    }

    const u16 logical_root = (u16)reaction_class * 2u;
    gb_stage_8bpp_16x16(
        logical_root,
        gb_social_reaction_obj_faces + (u32)reaction_class * GB_SOCIAL_REACTION_FACE_HALFWORDS
    );

    const s16 sx = (s16)((player->x_fixed >> 8) - camera_x - 20 +
                         (player->facing_right ? 40 : 0));
    const s16 sy = (s16)(((player->y_fixed - player->collision_height_fixed + 1) >> 8) -
                         camera_y - 37);
    volatile u16* oam = (volatile u16*)OAM;
    if(gb_video_sprite_visible_16(sx, sy))
    {
        const int o = first_oam * 4;
        oam[o] = (u16)(sy & 0x00FF) | GB_OBJ_256_COLOR;
        oam[o + 1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_1;
        oam[o + 2] = (u16)(logical_root * 2u); /* priority 0 */
        oam[o + 3] = 0;
    }
    else
    {
        gb_video_hide_oam_entry(oam, first_oam);
    }
    return 1;
}

static void gb_social_selector_stage_icons(const GbStoryRuntime* story)
{
    if(! story || (story->social.state != GB_SOCIAL_ROOT_SELECTOR &&
                   story->social.state != GB_SOCIAL_SECONDARY))
    {
        return;
    }
    const u8 base = story->social.page_base;
    if((u16)base + 3u >= GB_SOCIAL_ACTION_COUNT)
    {
        return;
    }
    static const u16 roots[4] = { 0, 2, 4, 6 };
    for(u16 i = 0; i < 4; ++i)
    {
        const u8 action_index = (u8)(base + i);
        gb_stage_8bpp_16x16(
            roots[i],
            gb_social_action_obj_icons + (u32)action_index * GB_SOCIAL_ACTION_ICON_HALFWORDS
        );
    }
}

static int gb_video_draw_social_action_icons(const GbStoryRuntime* story, int first_oam)
{
    if(! story || (story->social.state != GB_SOCIAL_ROOT_SELECTOR &&
                   story->social.state != GB_SOCIAL_SECONDARY))
    {
        return 0;
    }
    gb_social_selector_stage_icons(story);
    static const s16 xs[4] = { 40, 64, 40, 16 };
    static const s16 ys[4] = { 80, 104, 128, 104 };
    static const u16 roots[4] = { 0, 2, 4, 6 };
    volatile u16* oam = (volatile u16*)OAM;
    int used = 0;
    for(int i = 0; i < 4; ++i)
    {
        /* Player_draw helper 0x080065A8 suppresses the Right cell when the
           selected quadrant is Left (Player+0x1E4 == 3). */
        if(i == 1 && story->social.selected_quadrant == 3)
        {
            continue;
        }
        const int index = first_oam + used++;
        oam[index * 4] = (u16)(ys[i] & 0x00FF) | GB_OBJ_256_COLOR;
        oam[index * 4 + 1] = (u16)(xs[i] & 0x01FF) | GB_OBJ_SIZE_1;
        oam[index * 4 + 2] = (u16)(roots[i] * 2u);
        oam[index * 4 + 3] = 0;
    }
    return used;
}

static void gb_story_ui_draw_social(const GbStoryRuntime* story)
{
    if(story->social.state == GB_SOCIAL_RESPONSE)
    {
        gb_story_ui_draw_social_response(story);
        return;
    }
    if(story->social.state == GB_SOCIAL_ROOT_SELECTOR ||
       story->social.state == GB_SOCIAL_SECONDARY)
    {
        gb_social_selector_upload_map(story);
        gb_social_selector_upload_label(story);
        if(story->social.state == GB_SOCIAL_SECONDARY)
        {
            gb_social_selector_upload_topics(story);
        }
        return;
    }
    gb_video_clear_story_ui();
}

void gb_video_draw_story_ui(const GbStoryRuntime* story)
{
    if(! story)
    {
        gb_video_clear_story_ui();
        return;
    }
    if(story->dialogue.active)
    {
        gb_story_ui_draw_dialogue(story);
        return;
    }
    if(story->social.state != GB_SOCIAL_INACTIVE)
    {
        if(story->social.state == GB_SOCIAL_POST_DELAY)
        {
            gb_video_clear_story_ui();
        }
        else
        {
            gb_story_ui_draw_social(story);
        }
        return;
    }
    gb_video_clear_story_ui();
}

void gb_video_draw_message(const GbMessageRecord* message)
{
    if(! message)
    {
        gb_video_clear_story_ui();
        return;
    }
    int x = 0;
    int y = 0;
    gb_story_ui_begin();
    gb_story_ui_text(message->title, &x, &y);
    gb_story_ui_text(" - ", &x, &y);
    gb_story_ui_text(message->sender, &x, &y);
    gb_story_ui_newline(&x, &y);
    gb_story_ui_text(message->body, &x, &y);
    gb_story_ui_upload();
}

static void gb_video_hide_player_oam(void)
{
    volatile u16* oam = (volatile u16*)OAM;
    for(int i = 0; i < GB_ACTOR_OAM_FIRST; ++i)
    {
        oam[i * 4] = 160;
        oam[i * 4 + 1] = 0;
        oam[i * 4 + 2] = 0;
        oam[i * 4 + 3] = 0;
    }
}

static int gb_video_draw_monster(const GbPlayer* player, s16 camera_x, int first_oam)
{
    volatile u16* oam = (volatile u16*)OAM;
    if(gb_monster_animation_counter <= 24)
    {
        ++gb_monster_animation_counter;
    }
    const int animation_counter = gb_monster_animation_counter;
    const s16 center_x = (s16)(player->x - camera_x);
    const s16 xs[5] = { center_x, (s16)(center_x - 8), (s16)(center_x + 8),
                        (s16)(center_x - 8), (s16)(center_x + 8) };
    const s16 ys[5] = { (s16)(animation_counter - 20),
                        (s16)(animation_counter - 4), (s16)(animation_counter - 4),
                        (s16)(animation_counter + 12), (s16)(animation_counter + 12) };
    static const u16 monster_roots[5] = { 0x159, 0x178, 0x17A, 0x198, 0x19A };
    for(int i = 0; i < 5; ++i)
    {
        const int index = first_oam + i;
        oam[index * 4] = (u16)(ys[i] & 0x00FF) | GB_OBJ_256_COLOR;
        oam[index * 4 + 1] = (u16)(xs[i] & 0x01FF) | GB_OBJ_SIZE_1;
        oam[index * 4 + 2] = (u16)(monster_roots[i] * 2u) | (2u << 10);
        oam[index * 4 + 3] = 0;
    }
    return 5;
}

static int gb_video_draw_player_bicycle(const GbPlayer* player, s16 camera_x, s16 camera_y, int first_oam)
{
    volatile u16* oam = (volatile u16*)OAM;
    u8 frame = player->animation_frame;
    if(frame < 1 || frame > GB_PLAYER_BICYCLE_FRAME_COUNT)
    {
        frame = 1;
    }

    static const u16 bicycle_roots[GB_PLAYER_BICYCLE_SPRITE_COUNT] = {
        0x151, 0x170, 0x172, 0x190, 0x192,
    };
    const u16* frame_data = gb_player_bicycle_obj_frames +
                            (u32)(frame - 1) * GB_PLAYER_BICYCLE_FRAME_HALFWORDS;
    for(u16 i = 0; i < GB_PLAYER_BICYCLE_SPRITE_COUNT; ++i)
    {
        gb_stage_8bpp_16x16(bicycle_roots[i],
                            frame_data + i * GB_PLAYER_BICYCLE_SPRITE_HALFWORDS);
    }

    const s16 center_x = (s16)(player->x - camera_x);
    const s16 base_y = (s16)(player->y - camera_y - 16);
    const s16 xs[GB_PLAYER_BICYCLE_SPRITE_COUNT] = {
        center_x, (s16)(center_x - 8), (s16)(center_x + 8),
        (s16)(center_x - 8), (s16)(center_x + 8),
    };
    const s16 ys[GB_PLAYER_BICYCLE_SPRITE_COUNT] = {
        (s16)(base_y - 20), (s16)(base_y - 4), (s16)(base_y - 4),
        (s16)(base_y + 12), (s16)(base_y + 12),
    };

    for(int i = 0; i < GB_PLAYER_BICYCLE_SPRITE_COUNT; ++i)
    {
        const int index = first_oam + i;
        if(gb_video_sprite_visible_16(xs[i], ys[i]))
        {
            oam[index * 4] = (u16)(ys[i] & 0x00FF) | GB_OBJ_256_COLOR;
            oam[index * 4 + 1] = (u16)(xs[i] & 0x01FF) | GB_OBJ_SIZE_1;
            oam[index * 4 + 2] = (u16)(bicycle_roots[i] * 2u) | (2u << 10);
            oam[index * 4 + 3] = 0;
        }
        else
        {
            gb_video_hide_oam_entry(oam, index);
        }
    }
    return GB_PLAYER_BICYCLE_SPRITE_COUNT;
}

static int gb_video_draw_level_static_composite(s16 camera_x, s16 camera_y, int first_oam)
{
    if(! gb_video_level || (gb_video_level->level_id != 9 && gb_video_level->level_id != 10))
    {
        return 0;
    }

    const s16 world_x = gb_video_level->level_id == 9 ? 504 : 706;
    const s16 world_y = gb_video_level->level_id == 9 ? 476 : 884;
    const s16 sx[4] = {
        (s16)(world_x - camera_x), (s16)(world_x + 16 - camera_x),
        (s16)(world_x - camera_x), (s16)(world_x + 16 - camera_x),
    };
    const s16 sy[4] = {
        (s16)(world_y - camera_y), (s16)(world_y - camera_y),
        (s16)(world_y + 16 - camera_y), (s16)(world_y + 16 - camera_y),
    };
    static const u16 static_roots[4] = { 0x17C, 0x17E, 0x19C, 0x19E };
    volatile u16* oam = (volatile u16*)OAM;
    for(int i = 0; i < 4; ++i)
    {
        const int index = first_oam + i;
        if(gb_video_sprite_visible_16(sx[i], sy[i]))
        {
            oam[index * 4] = (u16)(sy[i] & 0x00FF) | GB_OBJ_256_COLOR;
            oam[index * 4 + 1] = (u16)(sx[i] & 0x01FF) | GB_OBJ_SIZE_1;
            oam[index * 4 + 2] = (u16)(static_roots[i] * 2u) | (2u << 10);
            oam[index * 4 + 3] = 0;
        }
        else
        {
            gb_video_hide_oam_entry(oam, index);
        }
    }
    return 4;
}

static int gb_video_draw_player_state_at(const GbPlayer* player, const GbStoryRuntime* story,
                                         s16 camera_x, s16 camera_y, int first_oam)
{
    if(story && story->state.monster_render_enabled)
    {
        /* Player_draw checks the fifth-sketch monster branch before the
           Level-9/10 parked-bicycle branches, so the special monster
           composite is exclusive of those static bicycle cells. */
        return gb_video_draw_monster(player, camera_x, first_oam);
    }
    gb_monster_animation_counter = 0;
    if(player && player->bicycle_mode == 2)
    {
        return gb_video_draw_player_bicycle(player, camera_x, camera_y, first_oam);
    }
    const int static_count = gb_video_draw_level_static_composite(camera_x, camera_y, first_oam);
    const int social_count = gb_video_draw_social_action_icons(story, first_oam + static_count);
    const int reaction_count = gb_video_draw_social_reaction(
        player, story, camera_x, camera_y, first_oam + static_count + social_count);
    const int prompt_count = gb_video_draw_interaction_prompt(
        player, story, camera_x, camera_y,
        first_oam + static_count + social_count + reaction_count);
    gb_video_draw_player_oam(
        player, camera_x, camera_y,
        first_oam + static_count + social_count + reaction_count + prompt_count);
    return static_count + social_count + reaction_count + prompt_count + 2;
}

void gb_video_draw_player_state(const GbPlayer* player, const GbStoryRuntime* story,
                                s16 camera_x, s16 camera_y)
{
    gb_video_hide_player_oam();
    (void)gb_video_draw_player_state_at(player, story, camera_x, camera_y, 0);
}

void gb_video_draw_gameplay_objects(GbActorSystem* system, const GbPlayer* player,
                                    const GbStoryRuntime* story, s16 camera_x, s16 camera_y)
{
    volatile u16* oam = (volatile u16*)OAM;
    const int gameplay_oam_count = GB_ACTOR_OAM_FIRST + GB_ACTOR_OAM_COUNT;
    for(int i = 0; i < gameplay_oam_count; ++i)
    {
        gb_video_hide_oam_entry(oam, i);
    }

    u8 overlay_count = 0;
    while(overlay_count < system->count &&
          system->actors[overlay_count].story_overlay_index != GB_ACTOR_STORY_NONE)
    {
        ++overlay_count;
    }

    u8 player_insert = overlay_count;
    if(system->level && system->level->level_id < 11)
    {
        player_insert = (u8)(player_insert + gb_player_physical_indices[system->level->level_id]);
    }
    if(player_insert > system->count)
    {
        player_insert = system->count;
    }

    GbGameplayOamCursor cursor = { 0, 0, 0 };
    gb_video_draw_actor_range(system, player, camera_x, camera_y, 0, player_insert, &cursor);
    cursor.oam_cursor += gb_video_draw_player_state_at(
        player, story, camera_x, camera_y, cursor.oam_cursor
    );
    gb_video_draw_actor_range(system, player, camera_x, camera_y, player_insert,
                              system->count, &cursor);
    gb_video_draw_leaf_particles(system, camera_x, camera_y, &cursor);
}
