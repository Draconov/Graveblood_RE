#include <graveblood/assets.h>

const GbLevelAssets* gb_level_assets(int level_id, int graphics_variant)
{
    switch(level_id)
    {
    case 0:
        switch(graphics_variant)
        {
        case 0: return &gb_level00_assets;
        case 1: return &gb_level00_v1_assets;
        case 2: return &gb_level00_v2_assets;
        default: return 0;
        }
    case 1:
        switch(graphics_variant)
        {
        case 0: return &gb_level01_assets;
        default: return 0;
        }
    case 2:
        switch(graphics_variant)
        {
        case 0: return &gb_level02_assets;
        default: return 0;
        }
    case 3:
        switch(graphics_variant)
        {
        case 0: return &gb_level03_assets;
        default: return 0;
        }
    case 4:
        switch(graphics_variant)
        {
        case 0: return &gb_level04_assets;
        default: return 0;
        }
    case 5:
        switch(graphics_variant)
        {
        case 0: return &gb_level05_assets;
        default: return 0;
        }
    case 6:
        switch(graphics_variant)
        {
        case 0: return &gb_level06_assets;
        default: return 0;
        }
    case 7:
        switch(graphics_variant)
        {
        case 0: return &gb_level07_assets;
        default: return 0;
        }
    case 8:
        switch(graphics_variant)
        {
        case 0: return &gb_level08_assets;
        default: return 0;
        }
    case 9:
        switch(graphics_variant)
        {
        case 0: return &gb_level09_assets;
        default: return 0;
        }
    case 10:
        switch(graphics_variant)
        {
        case 0: return &gb_level10_assets;
        default: return 0;
        }
    default:
        return 0;
    }
}

const GbLevelAssets* gb_level_default_assets(int level_id)
{
    return gb_level_assets(level_id, 0);
}
