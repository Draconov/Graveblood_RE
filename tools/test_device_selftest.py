from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "reconstruction"

GBA_HEADER = r'''\
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
#define MODE_3 3u
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
'''


class DeviceSelftestTests(unittest.TestCase):
    def test_main_has_isolated_device_selftest_entry(self):
        text = (RECON / "source/main.c").read_text(encoding="utf-8")
        self.assertIn("GB_DEVICE_SELFTEST", text)
        self.assertIn("gb_device_selftest_run();", text)

    def test_device_selftest_shows_seven_bars_and_plays_recovered_sfx6(self):
        text = (RECON / "source/game/emulator_selftest.c").read_text(encoding="utf-8")
        self.assertIn("void gb_device_selftest_run(void)", text)
        self.assertIn("MODE_3 | BG2_ON", text)
        self.assertIn("GB_SELFTEST_DEVICE_BAR_COUNT = 7", text)
        self.assertIn("gb_audio_play_sfx(6)", text)
        self.assertIn("GB_SELFTEST_EXPECTED_MASK", text)

    def test_audio_irq_instrumentation_is_available_to_device_selftest(self):
        header = (RECON / "include/graveblood/audio.h").read_text(encoding="utf-8")
        source = (RECON / "source/engine/audio.c").read_text(encoding="utf-8")
        self.assertIn("defined(GB_DEVICE_SELFTEST)", header)
        self.assertIn("defined(GB_DEVICE_SELFTEST)", source)

    def test_release_workflow_does_not_build_or_publish_device_test_rom(self):
        workflow = (ROOT / ".github/workflows/build-release-rom.yml").read_text(encoding="utf-8")
        self.assertNotIn("Graveblood_RE_device_test", workflow)
        self.assertNotIn("GB_DEVICE_SELFTEST", workflow)
        self.assertIn("path: reconstruction/Graveblood_RE.gba", workflow)

    def test_device_selftest_source_compiles_for_arm7tdmi_thumb(self):
        clang = shutil.which("clang")
        gcc = shutil.which("arm-none-eabi-gcc")
        if clang:
            compiler = [clang, "--target=arm-none-eabi"]
        elif gcc:
            compiler = [gcc]
        else:
            self.skipTest("no ARM-capable C compiler available")

        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / "gba.h").write_text(GBA_HEADER, encoding="utf-8")
            sources = [
                RECON / "source/main.c",
                RECON / "source/engine/audio.c",
                RECON / "source/game/emulator_selftest.c",
            ]
            for index, source in enumerate(sources):
                obj = td / f"device_{index}.o"
                command = [
                    *compiler,
                    "-mcpu=arm7tdmi", "-mthumb", "-std=c11", "-Os",
                    "-Wall", "-Wextra", "-Werror", "-ffreestanding",
                    "-DGB_DEVICE_SELFTEST",
                    "-I", str(td), "-I", str(RECON / "include"),
                    "-c", str(source),
                    "-o", str(obj),
                ]
                proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(0, proc.returncode, f"{source}:\n{proc.stderr}")
                self.assertTrue(obj.is_file() and obj.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
