#include <graveblood/stream.h>
#include <graveblood/video.h>

#define GB_BG0_SCREENBLOCK 27
#define GB_BG1_SCREENBLOCK 28
#define GB_BG2_SCREENBLOCK 29
#define GB_BG3_SCREENBLOCK 30
#define GB_OBJ_TALL (2u << 14)
#define GB_OBJ_SIZE_2 (2u << 14)
#define GB_OBJ_HFLIP (1u << 12)
#define GB_OBJ_256_COLOR (1u << 13)
#define GB_PLAYER_PALETTE_BANK 15
#define GB_ACTOR_OAM_FIRST 1
#define GB_ACTOR_OAM_COUNT 56
#define GB_ACTOR_OBJ_TILE_BASE (GB_PLAYER_FRAME_COUNT * 8)

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

void gb_video_wait_vblank(void)
{
    while(REG_VCOUNT >= 160)
    {
    }
    while(REG_VCOUNT < 160)
    {
    }
}

void gb_video_init(void)
{
    BGCTRL[0] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG0_SCREENBLOCK) | BG_PRIORITY(0);
    BGCTRL[1] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG1_SCREENBLOCK) | BG_PRIORITY(1);
    BGCTRL[2] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG2_SCREENBLOCK) | BG_PRIORITY(2);
    BGCTRL[3] = BG_SIZE_0 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_BG3_SCREENBLOCK) | BG_PRIORITY(3);
    gb_video_set_camera(0, 0);
    REG_DISPCNT = MODE_0 | BG0_ON | BG1_ON | BG2_ON | BG3_ON | OBJ_ON | OBJ_1D_MAP;

    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG0_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG1_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG2_SCREENBLOCK), GB_STREAM_MAP_CELLS);
    gb_clear_u16((volatile u16*)MAP_BASE_ADR(GB_BG3_SCREENBLOCK), GB_STREAM_MAP_CELLS);

    volatile u16* oam = (volatile u16*)OAM;
    for(int i = 0; i < 128; ++i)
    {
        oam[i * 4] = 160;
        oam[i * 4 + 1] = 0;
        oam[i * 4 + 2] = 0;
        oam[i * 4 + 3] = 0;
    }

    gb_copy_u16(OBJ_COLORS, gb_actor_obj_palette, 256);
    gb_copy_u16(OBJ_COLORS + GB_PLAYER_PALETTE_BANK * 16, gb_player_obj_palette, 16);
    gb_copy_u16((volatile u16*)SPR_VRAM(0), gb_player_obj_tiles, GB_PLAYER_FRAME_COUNT * 128);
}

void gb_video_load_level(const GbLevelAssets* level)
{
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

void gb_video_draw_actors(const GbActorSystem* system, s16 camera_x, s16 camera_y)
{
    volatile u16* oam = (volatile u16*)OAM;
    volatile u16* actor_vram = (volatile u16*)SPR_VRAM(0) + GB_PLAYER_FRAME_COUNT * 128;
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
        if(! actor->active || ! actor->descriptor ||
           actor->descriptor->actor_class != GB_ACTOR_NPC ||
           actor->descriptor->visual_index >= GB_ACTOR_VISUAL_COUNT)
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
        gb_copy_u16(
            actor_vram + visible * GB_ACTOR_FRAME_HALFWORDS,
            gb_actor_obj_frames + visual * GB_ACTOR_FRAME_HALFWORDS,
            GB_ACTOR_FRAME_HALFWORDS
        );

        const int oam_index = GB_ACTOR_OAM_FIRST + visible;
        oam[oam_index * 4] = (u16)(sy & 0x00FF) | GB_OBJ_TALL | GB_OBJ_256_COLOR;
        oam[oam_index * 4 + 1] = (u16)(sx & 0x01FF) | GB_OBJ_SIZE_2 |
                                 (actor->facing_right ? GB_OBJ_HFLIP : 0);
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
