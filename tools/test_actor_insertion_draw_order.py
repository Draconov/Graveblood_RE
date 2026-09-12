#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GBA_H = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;
#define KEY_A (1u << 0)
#define KEY_B (1u << 1)
#define KEY_SELECT (1u << 2)
#define KEY_START (1u << 3)
#define KEY_RIGHT (1u << 4)
#define KEY_LEFT (1u << 5)
#define KEY_UP (1u << 6)
#define KEY_DOWN (1u << 7)
#endif
'''

HARNESS = r'''
#include <assert.h>
#include <graveblood/actors.h>
#include <graveblood/assets.h>

static unsigned overlay_count_for_level(unsigned level)
{
    unsigned count = 0;
    for(unsigned i = 0; i < GB_ACTOR_STORY_DESCRIPTOR_COUNT; ++i)
    {
        if(gb_story_actor_descriptors[i].actor.level == level)
            ++count;
    }
    return count;
}

int main(void)
{
    GbActorSystem system;
    GbLevelAssets level = {0};
    gb_actor_system_init(&system);

    for(unsigned level_id = 0; level_id < 11; ++level_id)
    {
        level.level_id = (u8)level_id;
        gb_actor_system_load(&system, &level);
        const unsigned overlays = overlay_count_for_level(level_id);
        const GbActorLevelIndexSpan span = gb_actor_level_spans[level_id];
        assert(system.count == overlays + span.count);

        /* load_level_record_resources inserts the level-gated story list first. */
        unsigned overlay_pos = 0;
        for(unsigned i = 0; i < GB_ACTOR_STORY_DESCRIPTOR_COUNT; ++i)
        {
            if(gb_story_actor_descriptors[i].actor.level != level_id)
                continue;
            assert(overlay_pos < system.count);
            assert(system.actors[overlay_pos].story_overlay_index ==
                   gb_story_actor_descriptors[i].overlay_index);
            assert(system.actors[overlay_pos].descriptor == &gb_story_actor_descriptors[i].actor);
            ++overlay_pos;
        }
        assert(overlay_pos == overlays);

        /* The physical level list follows, preserving its canonical order. */
        for(unsigned i = 0; i < span.count; ++i)
        {
            const unsigned pos = overlays + i;
            const u16 descriptor_index = gb_level_actor_indices[span.offset + i];
            assert(system.actors[pos].story_overlay_index == GB_ACTOR_STORY_NONE);
            assert(system.actors[pos].descriptor == &gb_actor_descriptors[descriptor_index]);
        }
    }
    return 0;
}
'''


class ActorInsertionDrawOrderTests(unittest.TestCase):
    def test_actor_system_load_preserves_rom_overlay_then_physical_insertion_order(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / 'gba.h').write_text(GBA_H, encoding='utf-8')
            (td / 'harness.c').write_text(HARNESS, encoding='utf-8')
            exe = td / 'actor_insertion_test'
            proc = subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(td), '-I', str(ROOT / 'reconstruction/include'),
                str(ROOT / 'reconstruction/source/game/actors.c'),
                str(ROOT / 'reconstruction/source/engine/collision.c'),
                str(ROOT / 'reconstruction/data/actor_data.c'),
                str(ROOT / 'reconstruction/data/actor_routes.c'),
                str(td / 'harness.c'), '-o', str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            run = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)


if __name__ == '__main__':
    unittest.main()
