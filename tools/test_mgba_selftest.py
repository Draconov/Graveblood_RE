#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_mgba_selftest.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-release-rom.yml"
MAKEFILE = ROOT / "reconstruction" / "Makefile"
AUDIO_C = ROOT / "reconstruction" / "source" / "engine" / "audio.c"
INCLUDE = ROOT / "reconstruction" / "include"

REPORT_ADDRESS = 0x0203F000
REPORT_WORDS = 24
MAGIC = 0x54534247
VERSION = 2
EXPECTED_MASK = 0x7F
COMPLETE = 0xC0DEF00D
PPU_PROBE0_X = 100
PPU_PROBE0_Y = 64
PPU_PROBE1_X = 101
PPU_PROBE1_Y = 64
PPU_PROBE_COORDS = (
    PPU_PROBE0_X
    | (PPU_PROBE0_Y << 8)
    | (PPU_PROBE1_X << 16)
    | (PPU_PROBE1_Y << 24)
)
PPU_PLAYER_GREEN = 0x03E0
PPU_NPC_RED = 0x001F
PPU_PROBE_COLORS = PPU_PLAYER_GREEN | (PPU_NPC_RED << 16)


def _checksum(payload: bytes) -> bytes:
    return f"{sum(payload) & 0xFF:02x}".encode("ascii")


def _packet(payload: bytes) -> bytes:
    return b"$" + payload + b"#" + _checksum(payload)


def _recv_packet(conn: socket.socket) -> bytes:
    data = bytearray()
    while True:
        b = conn.recv(1)
        if not b:
            raise EOFError("client disconnected")
        if b == b"+":
            continue
        if b == b"$":
            break
    while True:
        b = conn.recv(1)
        if b == b"#":
            break
        data.extend(b)
    checksum = conn.recv(2)
    if checksum.lower() != _checksum(bytes(data)):
        raise AssertionError("bad client checksum")
    conn.sendall(b"+")
    return bytes(data)


def _send_packet(conn: socket.socket, payload: bytes) -> None:
    conn.sendall(_packet(payload))
    ack = conn.recv(1)
    if ack != b"+":
        raise AssertionError(f"expected client ack, got {ack!r}")


def _report_bytes(
    *,
    pass_mask: int = EXPECTED_MASK,
    fail_mask: int = 0,
    complete: int = COMPLETE,
    ending_guard: int = 0xA55AA55A,
    audio_irq_count: int = 64,
    audio_setup_ok: int = 1,
    audio_ie: int = 0x10,
    audio_ime: int = 1,
) -> bytes:
    words = [
        MAGIC, VERSION, EXPECTED_MASK, pass_mask, fail_mask, complete,
        0x00000800, 0x00000800, 5, 10, 0, 706, 780, 1, 2611, 80,
        ending_guard, audio_irq_count, audio_setup_ok, audio_ie, audio_ime,
        160, PPU_PROBE_COORDS, PPU_PROBE_COLORS,
    ]
    assert len(words) == REPORT_WORDS
    return b"".join((word & 0xFFFFFFFF).to_bytes(4, "little") for word in words)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return (
        struct.pack(">I", len(payload))
        + body
        + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    )


def _write_probe_png(path: Path, *, bad_overlap: bool = False) -> None:
    width, height = 240, 160
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0, 0, 255] * width)
        if y == PPU_PROBE0_Y:
            p0 = PPU_PROBE0_X * 3
            p1 = PPU_PROBE1_X * 3
            row[p0:p0 + 3] = bytes((255, 0, 0) if bad_overlap else (0, 255, 0))
            row[p1:p1 + 3] = bytes((255, 0, 0))
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


class MgbaSelftestRunnerTests(unittest.TestCase):
    def _rom(self, td: Path) -> Path:
        path = td / "Graveblood_RE_selftest.gba"
        path.write_bytes(b"GBA" * 128)
        return path

    def _fake_emulator(self, td: Path, report: bytes, *, early_exit: int | None = None) -> Path:
        path = td / "fake-mgba"
        if early_exit is not None:
            path.write_text(f"#!/bin/sh\nexit {early_exit}\n", encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
            return path
        report_hex = report.hex()
        body = f'''\
#!/usr/bin/env python3
import socket, sys, time
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 2345))
s.listen(1)
conn, _ = s.accept()

def checksum(payload):
    return f"{{sum(payload) & 0xff:02x}}".encode()

def recv_packet():
    while True:
        b = conn.recv(1)
        if not b: raise SystemExit(20)
        if b == b'$': break
    data = bytearray()
    while True:
        b = conn.recv(1)
        if b == b'#': break
        data.extend(b)
    conn.recv(2)
    conn.sendall(b'+')
    return bytes(data)

def send_packet(payload):
    conn.sendall(b'$' + payload + b'#' + checksum(payload))
    if conn.recv(1) != b'+': raise SystemExit(21)

if recv_packet() != b'?': raise SystemExit(22)
send_packet(b'S02')
if recv_packet() != b'c': raise SystemExit(23)
while True:
    b = conn.recv(1)
    if not b: raise SystemExit(24)
    if b == b'\\x03': break
send_packet(b'S02')
request = recv_packet()
expected = b"m203f000,60"
if request != expected: raise SystemExit(25)
send_packet(bytes.fromhex("{report_hex}").hex().encode())
try:
    if recv_packet() != b'c': raise SystemExit(26)
except EOFError:
    pass
time.sleep(30)
'''
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def _fake_xdotool(self, td: Path, *, delayed_search_once: bool = False) -> Path:
        path = td / "fake-xdotool"
        marker = td / "xdotool-search-delayed"
        delay = "1" if delayed_search_once else "0"
        body = f'''#!/bin/sh
set -eu
if [ "${{1:-}}" = "search" ]; then
    if [ "{delay}" = "1" ] && [ ! -e "{marker}" ]; then
        : > "{marker}"
        sleep 1.2
    fi
    echo 12345
    exit 0
fi
if [ "${{1:-}}" = "key" ]; then
    cp "$GB_FAKE_SCREENSHOT_SOURCE" "$GB_FAKE_SCREENSHOT_DIR/fake-mgba-shot.png"
    exit 0
fi
exit 9
'''
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_selftest_runner_accepts_complete_passing_report(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            rom = self._rom(td)
            emulator = self._fake_emulator(td, _report_bytes())
            proc = subprocess.run(
                [sys.executable, str(RUNNER), str(rom), "--emulator", str(emulator), "--seconds", "0.05"],
                cwd=ROOT, capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            self.assertIn("7/7", proc.stdout)
            self.assertIn("mGBA hardware self-test passed", proc.stdout)

    def test_selftest_runner_validates_native_ppu_screenshot(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            rom = self._rom(td)
            emulator = self._fake_emulator(td, _report_bytes())
            xdotool = self._fake_xdotool(td)
            source_png = td / "probe-source.png"
            _write_probe_png(source_png)
            output_png = td / "validated-ppu.png"
            env = os.environ.copy()
            env["GB_FAKE_SCREENSHOT_SOURCE"] = str(source_png)
            env["GB_FAKE_SCREENSHOT_DIR"] = str(td)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(rom),
                    "--emulator",
                    str(emulator),
                    "--seconds",
                    "0.05",
                    "--ppu-screenshot",
                    str(output_png),
                    "--xdotool",
                    str(xdotool),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            self.assertTrue(output_png.is_file())
            self.assertIn("PPU screenshot", proc.stdout)

    def test_selftest_runner_retries_timed_out_xdotool_window_search(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            rom = self._rom(td)
            emulator = self._fake_emulator(td, _report_bytes())
            xdotool = self._fake_xdotool(td, delayed_search_once=True)
            source_png = td / "probe-source.png"
            _write_probe_png(source_png)
            output_png = td / "validated-ppu.png"
            env = os.environ.copy()
            env["GB_FAKE_SCREENSHOT_SOURCE"] = str(source_png)
            env["GB_FAKE_SCREENSHOT_DIR"] = str(td)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(rom),
                    "--emulator",
                    str(emulator),
                    "--seconds",
                    "0.05",
                    "--ppu-screenshot",
                    str(output_png),
                    "--xdotool",
                    str(xdotool),
                    "--screenshot-timeout",
                    "3",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=7,
                env=env,
            )
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            self.assertTrue(output_png.is_file())

    def test_selftest_runner_rejects_wrong_ppu_overlap_pixel(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            rom = self._rom(td)
            emulator = self._fake_emulator(td, _report_bytes())
            xdotool = self._fake_xdotool(td)
            source_png = td / "probe-source.png"
            _write_probe_png(source_png, bad_overlap=True)
            output_png = td / "validated-ppu.png"
            env = os.environ.copy()
            env["GB_FAKE_SCREENSHOT_SOURCE"] = str(source_png)
            env["GB_FAKE_SCREENSHOT_DIR"] = str(td)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(rom),
                    "--emulator",
                    str(emulator),
                    "--seconds",
                    "0.05",
                    "--ppu-screenshot",
                    str(output_png),
                    "--xdotool",
                    str(xdotool),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            self.assertNotEqual(0, proc.returncode)
            self.assertIn("PPU", proc.stderr + proc.stdout)

    def test_selftest_runner_rejects_reported_failure(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            rom = self._rom(td)
            emulator = self._fake_emulator(td, _report_bytes(pass_mask=EXPECTED_MASK & ~0x20, fail_mask=0x20))
            proc = subprocess.run(
                [sys.executable, str(RUNNER), str(rom), "--emulator", str(emulator), "--seconds", "0.05"],
                cwd=ROOT, capture_output=True, text=True, timeout=5,
            )
            self.assertNotEqual(0, proc.returncode)
            self.assertIn("fail", (proc.stderr + proc.stdout).lower())

    def test_selftest_runner_failure_prints_hardware_diagnostics(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            rom = self._rom(td)
            emulator = self._fake_emulator(
                td,
                _report_bytes(
                    pass_mask=EXPECTED_MASK & ~(0x20 | 0x40),
                    fail_mask=0x20 | 0x40,
                    ending_guard=0x00125A34,
                    audio_irq_count=0,
                    audio_setup_ok=0,
                    audio_ie=0x0010,
                    audio_ime=1,
                ),
            )
            proc = subprocess.run(
                [sys.executable, str(RUNNER), str(rom), "--emulator", str(emulator), "--seconds", "0.05"],
                cwd=ROOT, capture_output=True, text=True, timeout=5,
            )
            output = proc.stderr + proc.stdout
            self.assertNotEqual(0, proc.returncode)
            self.assertIn("ending_guard=0x00125a34", output.lower())
            self.assertIn("audio_irq_count=0", output)
            self.assertIn("audio_setup_ok=0", output)
            self.assertIn("audio_ie=0x0010", output.lower())
            self.assertIn("audio_ime=0x0001", output.lower())

    def test_selftest_runner_rejects_early_emulator_exit(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            rom = self._rom(td)
            emulator = self._fake_emulator(td, _report_bytes(), early_exit=7)
            proc = subprocess.run(
                [sys.executable, str(RUNNER), str(rom), "--emulator", str(emulator), "--seconds", "0.05", "--connect-timeout", "0.3"],
                cwd=ROOT, capture_output=True, text=True, timeout=5,
            )
            self.assertNotEqual(0, proc.returncode)
            self.assertIn("exited", (proc.stderr + proc.stdout).lower())


class EmulatorSelftestBuildWiringTests(unittest.TestCase):
    def test_release_workflow_does_not_build_or_publish_dedicated_selftest_rom(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("Graveblood_RE_selftest", workflow)
        self.assertNotIn("GB_EMULATOR_SELFTEST", workflow)
        self.assertNotIn("tools/run_mgba_selftest.py", workflow)
        self.assertNotIn("--ppu-screenshot", workflow)
        self.assertNotIn("mgba-selftest-ppu.png", workflow)
        self.assertIn("-g", (ROOT / "tools" / "run_mgba_selftest.py").read_text(encoding="utf-8"))

    def test_makefile_accepts_extra_compile_flags_for_isolated_selftest_build(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("EXTRA_CFLAGS", makefile)
        self.assertRegex(makefile, r"CFLAGS\s*\+=.*\$\(EXTRA_CFLAGS\)")

    def test_selftest_rom_source_defines_fixed_report_and_all_seven_checks(self):
        header = ROOT / "reconstruction" / "include" / "graveblood" / "emulator_selftest.h"
        source = ROOT / "reconstruction" / "source" / "game" / "emulator_selftest.c"
        self.assertTrue(header.is_file())
        self.assertTrue(source.is_file())
        header_text = header.read_text(encoding="utf-8")
        source_text = source.read_text(encoding="utf-8")
        self.assertIn("GB_SELFTEST_VERSION = 2", header_text)
        self.assertIn("ppu_probe_coords", header_text)
        self.assertIn("ppu_probe_colors", header_text)
        self.assertIn("0x0203F000", header_text)
        self.assertIn("0x54534247", header_text)
        self.assertIn("0xC0DEF00D", header_text)
        for name in (
            "GB_SELFTEST_OAM", "GB_SELFTEST_VBLANK", "GB_SELFTEST_LEVEL9_BOUNDARY",
            "GB_SELFTEST_LEVEL10_ENTRANCE", "GB_SELFTEST_LEAVES",
            "GB_SELFTEST_ENDING", "GB_SELFTEST_AUDIO_IRQ",
        ):
            self.assertIn(name, header_text)
        for call in (
            "gb_video_draw_actors", "gb_video_draw_player", "gb_video_wait_vblank",
            "gb_player_try_level10_boundary", "gb_scene_request_gameplay",
            "gb_player_update", "gb_actor_system_update_environment",
            "gb_video_apply_final_effect", "gb_audio_init",
        ):
            self.assertIn(call, source_text)
        self.assertIn("frame < 60", source_text)
        self.assertIn("gb_audio_selftest_irq_count >= 63u", source_text)
        self.assertIn("gb_audio_selftest_irq_count <= 66u", source_text)
        self.assertIn("gb_selftest_prepare_ppu_fixture", source_text)

    def test_main_uses_compile_time_selftest_entry_without_changing_normal_entry(self):
        main_text = (ROOT / "reconstruction" / "source" / "main.c").read_text(encoding="utf-8")
        self.assertIn("#ifdef GB_EMULATOR_SELFTEST", main_text)
        self.assertIn("gb_emulator_selftest_run();", main_text)
        self.assertIn("gb_game_run();", main_text)

    def test_ending_selftest_matches_gba_bg_and_obj_vram_byte_store_rules(self):
        source_text = (ROOT / "reconstruction" / "source" / "game" / "emulator_selftest.c").read_text(encoding="utf-8")
        self.assertIn("vram[0] == gb_ending_arg0_copy1[1]", source_text)
        self.assertIn("vram[1] == gb_ending_arg0_copy1[1]", source_text)
        self.assertIn("*copy2_after_guard = 0xA55Au", source_text)
        self.assertIn("*copy1_obj_tail_guard = 0x5AA5u", source_text)
        self.assertIn("*vram_end_guard = 0xC33Cu", source_text)
        self.assertIn("*copy2_after_guard == 0xA55Au", source_text)
        self.assertIn("*copy1_obj_tail_guard == 0x5AA5u", source_text)
        self.assertIn("*vram_end_guard == 0xC33Cu", source_text)
        self.assertNotIn("vram[copy2_after] == gb_ending_arg0_copy1[copy2_after + 1u]", source_text)
        self.assertNotIn("vram[0] == gb_ending_arg0_copy1[0]", source_text)

    def test_ppu_fixture_uses_legal_halfword_writes_for_obj_vram_probe_pixels(self):
        source_text = (ROOT / "reconstruction" / "source" / "game" / "emulator_selftest.c").read_text(encoding="utf-8")
        self.assertIn("#define GB_SELFTEST_OBJ_VRAM ((volatile u16*)0x06010000u)", source_text)
        self.assertIn("GB_SELFTEST_OBJ_VRAM[(u32)player_tile * 16u] = 0x0001u;", source_text)
        self.assertIn("GB_SELFTEST_OBJ_VRAM[(u32)npc_tile * 16u] = 0x0202u;", source_text)
        self.assertNotIn("GB_SELFTEST_OBJ_VRAM[(u32)player_tile * 32u]", source_text)

    def test_audio_selftest_accepts_mgba_fifo_dma_normalized_readback(self):
        source_text = (ROOT / "reconstruction" / "source" / "game" / "emulator_selftest.c").read_text(encoding="utf-8")
        self.assertIn("const u16 dma_control = GB_SELFTEST_REG16(GB_SELFTEST_REG_DMA1CNT_H);", source_text)
        self.assertIn("dma_control == 0xB200u || dma_control == 0xB640u", source_text)
        self.assertNotIn("GB_SELFTEST_REG16(GB_SELFTEST_REG_DMA1CNT_H) == 0xB200u &&", source_text)

    def test_audio_selftest_irq_counter_is_driven_by_timer1_handler(self):
        gba_header = r'''
#ifndef GBA_H
#define GBA_H
#include <stdint.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;
#define IRQ_TIMER1 0x10u
void irqInit(void); void irqSet(u32, void (*)(void)); void irqEnable(u32); void irqDisable(u32);
#endif
'''
        harness = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <sys/mman.h>
#include <graveblood/audio.h>
#include <graveblood/assets.h>

const GbAudioSample gb_audio_samples[GB_AUDIO_SAMPLE_COUNT] = {0};
static void (*handler)(void);
void irqInit(void) {}
void irqSet(u32 irq, void (*fn)(void)) { assert(irq == IRQ_TIMER1); handler = fn; }
void irqEnable(u32 irq) { assert(irq == IRQ_TIMER1); }
void irqDisable(u32 irq) { assert(irq == IRQ_TIMER1); }

int main(void) {
    void* p = mmap((void*)0x04000000u, 0x3000, PROT_READ|PROT_WRITE,
                   MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED, -1, 0);
    assert(p == (void*)0x04000000u);
    gb_audio_init();
    assert(handler != 0);
    assert(gb_audio_selftest_irq_count == 0);
    handler();
    assert(gb_audio_selftest_irq_count == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            (td / "gba.h").write_text(gba_header, encoding="utf-8")
            hp = td / "harness.c"
            hp.write_text(harness, encoding="utf-8")
            exe = td / "audio-selftest"
            proc = subprocess.run([
                "cc", "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror",
                "-DGB_EMULATOR_SELFTEST", "-I", str(td), "-I", str(INCLUDE),
                str(AUDIO_C), str(hp), "-o", str(exe),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            proc = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, timeout=5)
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
