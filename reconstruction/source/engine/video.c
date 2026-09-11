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
#define GB_PLAYER_PALETTE_BANK 15
#define GB_MONSTER_OBJ_TILE_BASE (GB_PLAYER_FRAME_COUNT * 8)
#define GB_ACTOR_OAM_FIRST 5
#define GB_ACTOR_OAM_COUNT 52
#define GB_ACTOR_OBJ_TILE_BASE (GB_MONSTER_OBJ_TILE_BASE + GB_MONSTER_SPRITE_COUNT * 8)
#define GB_STORY_UI_COLUMNS 29
#define GB_STORY_UI_ROWS 3
#define GB_STORY_UI_MAP_Y 17
#define GB_STORY_UI_WIDTH (GB_STORY_UI_COLUMNS * 8)
#define GB_STORY_UI_HEIGHT (GB_STORY_UI_ROWS * 8)
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

static const GbLevelAssets* gb_video_level;
static u8 gb_story_ui_pixels[GB_STORY_UI_WIDTH * GB_STORY_UI_HEIGHT];
static u8 gb_pda_text_pixels[GB_PDA_TEXT_WIDTH * GB_PDA_TEXT_HEIGHT];
static u8 gb_monster_animation_counter;

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
    REG_DISPCNT = MODE_0 | BG0_ON | BG1_ON | BG2_ON | BG3_ON | OBJ_ON | OBJ_1D_MAP;
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
    gb_copy_u16(OBJ_COLORS, gb_actor_obj_palette, 256);
    gb_copy_u16(OBJ_COLORS + GB_PLAYER_PALETTE_BANK * 16, gb_player_obj_palette, 16);
    gb_copy_u16((volatile u16*)SPR_VRAM(0), gb_player_obj_tiles, GB_PLAYER_FRAME_COUNT * 128);
    gb_copy_u16((volatile u16*)SPR_VRAM(0) + GB_PLAYER_FRAME_COUNT * 128,
                gb_monster_obj_frames,
                GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS);
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
        gb_copy_u16((volatile u16*)SPR_VRAM(0) + i * GB_WARDROBE_PREVIEW_HALFWORDS,
                    gb_wardrobe_preview_tiles[i], GB_WARDROBE_PREVIEW_HALFWORDS);
        const int x = 16 + i * 16;
        oam[i * 4] = (u16)GB_WARDROBE_PREVIEW_Y | GB_OBJ_TALL | GB_OBJ_256_COLOR;
        oam[i * 4 + 1] = (u16)x | GB_OBJ_SIZE_2;
        oam[i * 4 + 2] = (u16)(i * 16);
        oam[i * 4 + 3] = 0;
    }
}

void gb_video_load_wardrobe(void)
{
    gb_video_level = &gb_level07_assets;
    gb_video_set_camera(0, 0);
    BGCTRL[0] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) |
                SCREEN_BASE(GB_BG0_SCREENBLOCK) | BG_PRIORITY(0);
    REG_DISPCNT = MODE_0 | BG0_ON | OBJ_ON | OBJ_1D_MAP;
    gb_copy_u16(BG_COLORS, gb_level07_assets.bg_palette, 256);
    gb_copy_u16(OBJ_COLORS, gb_actor_obj_palette, 256);
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
    gb_copy_u16((volatile u16*)CHAR_BASE_ADR(0), level->bg_tiles, level->bg_tile_halfwords);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_load_fixed_maps(level);
}

void gb_video_stream_full(const GbLevelAssets* level, s16 left, s16 top)
{
    gb_stream_fill(level, level->layer_a, left, top, (volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK));
    gb_stream_fill(level, level->layer_b, left, top, (volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK));
}

void gb_video_stream_column(const GbLevelAssets* level, s16 world_x, s16 top)
{
    gb_stream_fill_column(level, level->layer_a, world_x, top, (volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK));
    gb_stream_fill_column(level, level->layer_b, world_x, top, (volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK));
}

void gb_video_stream_row(const GbLevelAssets* level, s16 left, s16 world_y)
{
    gb_stream_fill_row(level, level->layer_a, left, world_y, (volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK));
    gb_stream_fill_row(level, level->layer_b, left, world_y, (volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK));
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

void gb_video_draw_actors(GbActorSystem* system, const GbPlayer* player, s16 camera_x, s16 camera_y)
{
    volatile u16* oam = (volatile u16*)OAM;
    volatile u16* actor_vram = (volatile u16*)SPR_VRAM(0) + GB_PLAYER_FRAME_COUNT * 128 +
                               GB_MONSTER_SPRITE_COUNT * GB_MONSTER_SPRITE_HALFWORDS;
    u8 visible = 0;

    for(int i = 0; i < GB_ACTOR_OAM_COUNT; ++i)
    {
        const int oam_index = GB_ACTOR_OAM_FIRST + i;
        oam[oam_index * 4] = 160;
        oam[oam_index * 4 + 1] = 0;
        oam[oam_index * 4 + 2] = 0;
        oam[oam_index * 4 + 3] = 0;
    }

    for(u8 i = 0; i < system->count && visible < GB_ACTOR_OAM_COUNT; ++i)
    {
        const GbActor* actor = &system->actors[i];
        if(! actor->active || ! actor->descriptor)
        {
            continue;
        }

        const int oam_index = GB_ACTOR_OAM_FIRST + visible;
        volatile u16* slot = actor_vram + visible * GB_ACTOR_FRAME_HALFWORDS;
        if(actor->descriptor->actor_class == GB_ACTOR_NPC)
        {
            if(actor->descriptor->visual_index >= GB_ACTOR_VISUAL_COUNT)
            {
                continue;
            }
            const s16 sx = (s16)(gb_actor_pixel_x(actor) - camera_x - 8);
            const s16 sy = (s16)(gb_actor_pixel_y(actor) - camera_y - 32);
            if(sx < -16 || sx >= 240 || sy < -32 || sy >= 160)
            {
                continue;
            }
            const u8 visual = actor->descriptor->visual_index;
            gb_copy_u16(slot,
                        gb_actor_obj_frames + visual * GB_ACTOR_FRAME_HALFWORDS,
                        GB_ACTOR_FRAME_HALFWORDS);
            oam[oam_index * 4] = (u16)(sy & 0x00FF) | GB_OBJ_TALL | GB_OBJ_256_COLOR;
            oam[oam_index * 4 + 1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_2 |
                                     (actor->facing_right ? GB_OBJ_HFLIP : 0);
            oam[oam_index * 4 + 2] = (u16)(GB_ACTOR_OBJ_TILE_BASE + visible * 16);
            oam[oam_index * 4 + 3] = 0;
            ++visible;
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
            if(sx < -16 || sx >= 240 || sy < -16 || sy >= 160)
            {
                continue;
            }
            gb_copy_u16(slot, gb_grass_obj_tiles, GB_GRASS_OBJ_HALFWORDS);
            oam[oam_index * 4] = (u16)(sy & 0x00FF) | GB_OBJ_256_COLOR;
            oam[oam_index * 4 + 1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_1 |
                                     (draw.hflip ? GB_OBJ_HFLIP : 0);
            oam[oam_index * 4 + 2] = (u16)((GB_ACTOR_OBJ_TILE_BASE + visible * 16) |
                                           ((u16)draw.priority << 10));
            oam[oam_index * 4 + 3] = 0;
            ++visible;
        }
    }

    for(int i = 0; i < GB_LEAF_PARTICLE_CAPACITY && visible < GB_ACTOR_OAM_COUNT; ++i)
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
        const int oam_index = GB_ACTOR_OAM_FIRST + visible;
        volatile u16* slot = actor_vram + visible * GB_ACTOR_FRAME_HALFWORDS;
        gb_copy_u16(slot,
                    gb_leaf_obj_frames + frame * GB_LEAF_FRAME_HALFWORDS,
                    GB_LEAF_FRAME_HALFWORDS);
        oam[oam_index * 4] = (u16)(sy & 0x00FF) | GB_OBJ_256_COLOR;
        oam[oam_index * 4 + 1] = (u16)(sx & 0x01FF);
        oam[oam_index * 4 + 2] = (u16)(GB_ACTOR_OBJ_TILE_BASE + visible * 16);
        oam[oam_index * 4 + 3] = 0;
        ++visible;
    }
}

void gb_video_draw_player(const GbPlayer* player, s16 camera_x, s16 camera_y)
{
    const s16 sx = (s16)(player->x - camera_x - 8);
    const s16 sy = (s16)(player->y - camera_y - 32);
    volatile u16* oam = (volatile u16*)OAM;

    if(sx < -16 || sx >= 240 || sy < -32 || sy >= 160)
    {
        oam[0] = 160;
        return;
    }

    oam[0] = (u16)(sy & 0x00FF) | GB_OBJ_TALL;
    oam[1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_2 | (player->facing_right ? GB_OBJ_HFLIP : 0);
    oam[2] = (u16)(gb_player_frame_index(player) * 8) | (GB_PLAYER_PALETTE_BANK << 12);
    oam[3] = 0;
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
    gb_story_ui_begin();
    if(record->speaker && record->speaker[0])
    {
        gb_story_ui_text(record->speaker, &x, &y);
        gb_story_ui_text(": ", &x, &y);
    }
    gb_story_ui_text(record->text, &x, &y);
    gb_story_ui_upload();
}

static const char* gb_story_ui_topic(const GbStoryRuntime* story)
{
    const u8 action = story->social.action_index;
    const u8 topic = story->social.topic_index;
    if(action == 4 && topic < GB_SOCIAL_SUBJECT_TOPIC_COUNT)
    {
        return gb_social_subject_topics[topic];
    }
    if(action == 5 && topic < GB_SOCIAL_ASK_TOPIC_COUNT)
    {
        return gb_social_ask_topics[topic];
    }
    if(action == 7 && topic < GB_SOCIAL_CRITICIZE_TOPIC_COUNT)
    {
        return gb_social_criticize_topics[topic];
    }
    return 0;
}

static void gb_story_ui_draw_social(const GbStoryRuntime* story)
{
    int x = 0;
    int y = 0;
    gb_story_ui_begin();
    const char* profile = gb_story_social_profile_name(story);
    if(profile)
    {
        gb_story_ui_text(profile, &x, &y);
        gb_story_ui_newline(&x, &y);
    }

    if(story->social.state == GB_SOCIAL_ROOT_SELECTOR)
    {
        const u8 base = story->social.page_base;
        if(base + 3 < GB_SOCIAL_ACTION_COUNT)
        {
            gb_story_ui_text("^", &x, &y);
            gb_story_ui_text(gb_social_actions[base].label, &x, &y);
            gb_story_ui_text("  >", &x, &y);
            gb_story_ui_text(gb_social_actions[base + 1].label, &x, &y);
            gb_story_ui_newline(&x, &y);
            gb_story_ui_text("v", &x, &y);
            gb_story_ui_text(gb_social_actions[base + 2].label, &x, &y);
            gb_story_ui_text("  <", &x, &y);
            gb_story_ui_text(gb_social_actions[base + 3].label, &x, &y);
        }
    }
    else if(story->social.state == GB_SOCIAL_SECONDARY)
    {
        if(story->social.action_index < GB_SOCIAL_ACTION_COUNT)
        {
            gb_story_ui_text(gb_social_actions[story->social.action_index].label, &x, &y);
            gb_story_ui_newline(&x, &y);
        }
        gb_story_ui_text(gb_story_ui_topic(story), &x, &y);
    }
    else if(story->social.state == GB_SOCIAL_RESPONSE)
    {
        gb_story_ui_text(story->social.response_text, &x, &y);
    }
    gb_story_ui_upload();
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
    for(int i = 0; i < 5; ++i)
    {
        oam[i * 4] = 160;
        oam[i * 4 + 1] = 0;
        oam[i * 4 + 2] = 0;
        oam[i * 4 + 3] = 0;
    }
}

static void gb_video_draw_monster(const GbPlayer* player, s16 camera_x)
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
    for(int i = 0; i < 5; ++i)
    {
        oam[i * 4] = (u16)(ys[i] & 0x00FF) | GB_OBJ_256_COLOR;
        oam[i * 4 + 1] = (u16)(xs[i] & 0x01FF) | GB_OBJ_SIZE_1;
        oam[i * 4 + 2] = (u16)(GB_MONSTER_OBJ_TILE_BASE + i * 8);
        oam[i * 4 + 3] = 0;
    }
}

void gb_video_draw_player_state(const GbPlayer* player, const GbStoryRuntime* story,
                                s16 camera_x, s16 camera_y)
{
    gb_video_hide_player_oam();
    if(story && story->state.monster_render_enabled)
    {
        gb_video_draw_monster(player, camera_x);
        return;
    }
    gb_monster_animation_counter = 0;
    gb_video_draw_player(player, camera_x, camera_y);
}
