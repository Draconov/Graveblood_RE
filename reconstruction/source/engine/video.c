#include <graveblood/video.h>

#define GB_SCREENBLOCK_BASE 28
#define GB_OBJ_TALL (2u << 14)
#define GB_OBJ_SIZE_2 (2u << 14)
#define GB_OBJ_HFLIP (1u << 12)

static void gb_copy_u16(volatile u16* dst, const u16* src, int count)
{
    for(int i = 0; i < count; ++i)
    {
        dst[i] = src[i];
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
    BGCTRL[0] = BG_SIZE_3 | BG_256_COLOR | CHAR_BASE(0) | SCREEN_BASE(GB_SCREENBLOCK_BASE) | BG_PRIORITY(1);
    BG_OFFSET[0].x = 0;
    BG_OFFSET[0].y = 0;
    REG_DISPCNT = MODE_0 | BG0_ON | OBJ_ON | OBJ_1D_MAP;

    volatile u16* oam = (volatile u16*)OAM;
    for(int i = 0; i < 128; ++i)
    {
        oam[i * 4] = 160;
        oam[i * 4 + 1] = 0;
        oam[i * 4 + 2] = 0;
        oam[i * 4 + 3] = 0;
    }

    gb_copy_u16(OBJ_COLORS, gb_player_obj_palette, 16);
    gb_copy_u16((volatile u16*)SPR_VRAM(0), gb_player_obj_tiles, GB_PLAYER_FRAME_COUNT * 128);
}

void gb_video_load_level(const GbLevelAssets* level)
{
    gb_copy_u16(BG_COLORS, level->palette, 256);
    gb_copy_u16((volatile u16*)CHAR_BASE_ADR(0), level->tiles, 8192);
    gb_copy_u16((volatile u16*)MAP_BASE_ADR(GB_SCREENBLOCK_BASE), level->map, 4096);
}

void gb_video_set_camera(s16 x, s16 y)
{
    BG_OFFSET[0].x = (u16)x;
    BG_OFFSET[0].y = (u16)y;
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
    oam[2] = (u16)(gb_player_frame_index(player) * 8);
    oam[3] = 0;
}
