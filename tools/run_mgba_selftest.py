#!/usr/bin/env python3
"""Run the Graveblood emulator self-test ROM and read its EWRAM report via mGBA GDB."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time
import zlib

REPORT_ADDRESS = 0x0203F000
REPORT_WORDS = 24
REPORT_BYTES = REPORT_WORDS * 4
MAGIC = 0x54534247
VERSION = 2
EXPECTED_MASK = 0x7F
COMPLETE = 0xC0DEF00D

CHECKS = (
    (0x01, "OAM ordering/priority"),
    (0x02, "VBlank timing"),
    (0x04, "Level 9 boundary/scene"),
    (0x08, "Level 10 scripted entrance"),
    (0x10, "Level 9 leaf emission"),
    (0x20, "ending-effect VRAM"),
    (0x40, "Timer1 audio IRQ"),
)

PPU_PROBE_COORDS = 100 | (64 << 8) | (101 << 16) | (64 << 24)
PPU_PROBE_COLORS = 0x03E0 | (0x001F << 16)


def _find_emulator(explicit: str | None) -> str | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_bin = os.environ.get("MGBA_BIN")
    if env_bin:
        candidates.append(env_bin)
    for name in ("mgba", "mgba-sdl"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates.append("/usr/games/mgba")
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def _find_xdotool(explicit: str | None) -> str | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_bin = os.environ.get("XDOTOOL_BIN")
    if env_bin:
        candidates.append(env_bin)
    found = shutil.which("xdotool")
    if found:
        candidates.append(found)
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def _checksum(payload: bytes) -> bytes:
    return f"{sum(payload) & 0xff:02x}".encode("ascii")


def _packet(payload: bytes) -> bytes:
    return b"$" + payload + b"#" + _checksum(payload)


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        part = sock.recv(count - len(chunks))
        if not part:
            raise ConnectionError("mGBA GDB connection closed")
        chunks.extend(part)
    return bytes(chunks)


def _send_command(sock: socket.socket, payload: bytes, *, expect_reply: bool = True) -> bytes | None:
    sock.sendall(_packet(payload))
    ack = _recv_exact(sock, 1)
    if ack != b"+":
        raise RuntimeError(f"mGBA GDB rejected packet {payload!r}: {ack!r}")
    if not expect_reply:
        return None
    return _recv_packet(sock)


def _recv_packet(sock: socket.socket) -> bytes:
    while True:
        marker = _recv_exact(sock, 1)
        if marker == b"$":
            break
        if marker in (b"+", b"-"):
            continue
    payload = bytearray()
    while True:
        b = _recv_exact(sock, 1)
        if b == b"#":
            break
        payload.extend(b)
    checksum = _recv_exact(sock, 2).lower()
    if checksum != _checksum(bytes(payload)):
        sock.sendall(b"-")
        raise RuntimeError("mGBA GDB reply checksum mismatch")
    sock.sendall(b"+")
    return bytes(payload)


def _connect(proc: subprocess.Popen[str], host: str, port: int, timeout: float) -> socket.socket:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=0.2)
            raise RuntimeError(
                f"mGBA exited before GDB connected (code {proc.returncode}).\n"
                f"{(stdout or '')}{(stderr or '')}"
            )
        sock = socket.socket()
        sock.settimeout(min(0.2, max(0.01, deadline - time.monotonic())))
        try:
            sock.connect((host, port))
            sock.settimeout(max(1.0, timeout))
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
            time.sleep(0.02)
    try:
        proc.wait(timeout=0.75)
    except subprocess.TimeoutExpired:
        pass
    if proc.poll() is not None:
        stdout, stderr = proc.communicate(timeout=0.2)
        raise RuntimeError(
            f"mGBA exited before GDB connected (code {proc.returncode}).\n"
            f"{(stdout or '')}{(stderr or '')}"
        )
    raise RuntimeError(f"timed out connecting to mGBA GDB stub on {host}:{port}: {last_error}")


def _stop_process(proc: subprocess.Popen[str]) -> tuple[str, str]:
    if proc.poll() is None:
        proc.terminate()
    try:
        return proc.communicate(timeout=1.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.communicate(timeout=1.0)


def _decode_report(raw: bytes) -> list[int]:
    if len(raw) != REPORT_BYTES:
        raise RuntimeError(f"self-test report has {len(raw)} bytes; expected {REPORT_BYTES}")
    return [int.from_bytes(raw[i:i + 4], "little") for i in range(0, REPORT_BYTES, 4)]


def _validate_report(words: list[int]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if words[0] != MAGIC:
        errors.append(f"bad report magic 0x{words[0]:08x}")
    if words[1] != VERSION:
        errors.append(f"bad report version {words[1]}")
    if words[2] != EXPECTED_MASK:
        errors.append(f"unexpected check mask 0x{words[2]:02x}")
    if words[5] != COMPLETE:
        errors.append(f"self-test incomplete (marker 0x{words[5]:08x})")
    pass_mask, fail_mask = words[3], words[4]
    for bit, label in CHECKS:
        if fail_mask & bit:
            errors.append(f"FAIL: {label}")
        elif not (pass_mask & bit):
            errors.append(f"missing pass bit: {label}")
    if pass_mask & ~EXPECTED_MASK:
        errors.append(f"unknown pass bits 0x{pass_mask & ~EXPECTED_MASK:02x}")
    if fail_mask & ~EXPECTED_MASK:
        errors.append(f"unknown fail bits 0x{fail_mask & ~EXPECTED_MASK:02x}")
    if not (63 <= words[17] <= 66):
        errors.append(f"Timer1 cadence outside 63..66 IRQs/60 frames: {words[17]}")
    if words[22] != PPU_PROBE_COORDS:
        errors.append(f"unexpected PPU probe coordinates 0x{words[22]:08x}")
    if words[23] != PPU_PROBE_COLORS:
        errors.append(f"unexpected PPU probe colors 0x{words[23]:08x}")
    return not errors, errors


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _load_png_rgb(path: Path) -> tuple[int, int, list[bytes]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"mGBA screenshot is not a PNG: {path}")
    pos = 8
    width = height = bit_depth = color_type = None
    compressed = bytearray()
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        if len(payload) != length:
            raise RuntimeError("truncated mGBA screenshot PNG")
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if bit_depth != 8 or color_type not in (2, 6):
                raise RuntimeError(
                    f"unsupported mGBA PNG format: depth={bit_depth} color_type={color_type}"
                )
            if compression != 0 or filtering != 0 or interlace != 0:
                raise RuntimeError("unsupported mGBA PNG compression/filter/interlace mode")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
        pos += 12 + length
    if width is None or height is None or color_type is None:
        raise RuntimeError("mGBA screenshot PNG is missing IHDR")

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise RuntimeError(f"unexpected mGBA PNG payload size {len(raw)}; expected {expected}")

    rows: list[bytes] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        encoded = raw[offset:offset + stride]
        offset += stride
        decoded = bytearray(stride)
        for i, value in enumerate(encoded):
            left = decoded[i - channels] if i >= channels else 0
            up = previous[i]
            up_left = previous[i - channels] if i >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                predictor = _paeth(left, up, up_left)
            else:
                raise RuntimeError(f"unsupported PNG filter {filter_type}")
            decoded[i] = (value + predictor) & 0xFF
        if channels == 3:
            rows.append(bytes(decoded))
        else:
            rgb = bytearray(width * 3)
            for x in range(width):
                rgb[x * 3:x * 3 + 3] = decoded[x * 4:x * 4 + 3]
            rows.append(bytes(rgb))
        previous = decoded
    return width, height, rows


def _bgr555_to_rgb(value: int) -> tuple[int, int, int]:
    def expand(v: int) -> int:
        return (v << 3) | (v >> 2)

    return (
        expand(value & 0x1F),
        expand((value >> 5) & 0x1F),
        expand((value >> 10) & 0x1F),
    )


def _validate_ppu_screenshot(path: Path, words: list[int]) -> None:
    width, height, rows = _load_png_rgb(path)
    if (width, height) != (240, 160):
        raise RuntimeError(f"unexpected mGBA screenshot size {width}x{height}; expected 240x160")
    coords = words[22]
    colors = words[23]
    probes = (
        (coords & 0xFF, (coords >> 8) & 0xFF, colors & 0x7FFF, "Player-over-NPC"),
        ((coords >> 16) & 0xFF, (coords >> 24) & 0xFF, (colors >> 16) & 0x7FFF, "NPC-through-transparency"),
    )
    for x, y, color, label in probes:
        if not (0 <= x < width and 0 <= y < height):
            raise RuntimeError(f"PPU probe {label} lies outside screenshot: ({x},{y})")
        start = x * 3
        actual = tuple(rows[y][start:start + 3])
        expected = _bgr555_to_rgb(color)
        if actual != expected:
            raise RuntimeError(
                f"PPU probe {label} mismatch at ({x},{y}): got {actual}, expected {expected}"
            )


def _capture_ppu_screenshot(
    proc: subprocess.Popen[str],
    sock: socket.socket,
    xdotool: str,
    directory: Path,
    existing: set[Path],
    output: Path,
    words: list[int],
    timeout: float,
) -> None:
    _send_command(sock, b"c", expect_reply=False)

    deadline = time.monotonic() + timeout
    windows: list[str] = []
    while time.monotonic() < deadline and not windows:
        try:
            result = subprocess.run(
                [xdotool, "search", "--pid", str(proc.pid)],
                capture_output=True,
                text=True,
                timeout=max(0.2, min(1.0, timeout)),
            )
        except subprocess.TimeoutExpired:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"mGBA exited while locating PPU screenshot window (code {proc.returncode})"
                )
            continue
        if result.returncode == 0:
            windows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not windows:
            time.sleep(0.05)
    if not windows:
        raise RuntimeError("PPU screenshot check could not find the mGBA SDL window")

    try:
        result = subprocess.run(
            [xdotool, "key", "--window", windows[0], "F12"],
            capture_output=True,
            text=True,
            timeout=max(0.5, timeout),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("xdotool timed out while requesting mGBA PPU screenshot") from exc
    if result.returncode != 0:
        raise RuntimeError(f"xdotool failed to request mGBA screenshot: {result.stderr.strip()}")

    generated: Path | None = None
    while time.monotonic() < deadline:
        candidates = [
            path.resolve()
            for path in directory.glob("*.png")
            if path.resolve() not in existing and path.stat().st_size > 0
        ]
        if candidates:
            generated = max(candidates, key=lambda p: p.stat().st_mtime_ns)
            break
        if proc.poll() is not None:
            raise RuntimeError(f"mGBA exited before writing PPU screenshot (code {proc.returncode})")
        time.sleep(0.05)
    if generated is None:
        raise RuntimeError("timed out waiting for mGBA F12 screenshot")

    _validate_ppu_screenshot(generated, words)
    output.parent.mkdir(parents=True, exist_ok=True)
    if generated != output.resolve():
        shutil.copy2(generated, output)
    print(f"PPU screenshot validated: {output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Graveblood mGBA hardware self-test ROM via GDB.")
    parser.add_argument("rom", type=Path)
    parser.add_argument("--emulator", help="Explicit mGBA executable")
    parser.add_argument("--seconds", type=float, default=1.0,
                        help="CPU run time before reading the report (default: 1s)")
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2345)
    parser.add_argument(
        "--ppu-screenshot",
        type=Path,
        help="Validate mGBA's native F12 PNG against the self-test PPU probes and save it here.",
    )
    parser.add_argument("--xdotool", help="Explicit xdotool executable for --ppu-screenshot")
    parser.add_argument("--screenshot-timeout", type=float, default=3.0)
    args = parser.parse_args(argv)

    if args.seconds <= 0 or args.connect_timeout <= 0 or args.screenshot_timeout <= 0:
        parser.error("--seconds, --connect-timeout and --screenshot-timeout must be greater than zero")
    rom = args.rom.resolve()
    if not rom.is_file() or rom.stat().st_size == 0:
        print(f"ROM is missing or empty: {rom}", file=sys.stderr)
        return 2
    emulator = _find_emulator(args.emulator)
    if emulator is None:
        print("mGBA executable not found; install mgba-sdl/mgba or pass --emulator.", file=sys.stderr)
        return 2
    xdotool: str | None = None
    screenshot_output: Path | None = None
    screenshot_dir: Path | None = None
    existing_screenshots: set[Path] = set()
    if args.ppu_screenshot is not None:
        xdotool = _find_xdotool(args.xdotool)
        if xdotool is None:
            print("xdotool not found; install it or pass --xdotool for --ppu-screenshot.", file=sys.stderr)
            return 2
        screenshot_output = args.ppu_screenshot.resolve()
        screenshot_dir = screenshot_output.parent
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        existing_screenshots = {path.resolve() for path in screenshot_dir.glob("*.png")}

    env = os.environ.copy()
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    command = [emulator, "-g", "-C", "useBios=0"]
    if screenshot_dir is not None:
        command.extend(["-C", f"screenshotPath={screenshot_dir}"])
    command.append(str(rom))
    proc = subprocess.Popen(
        command, cwd=str(rom.parent), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    sock: socket.socket | None = None
    try:
        sock = _connect(proc, args.host, args.port, args.connect_timeout)
        stop = _send_command(sock, b"?")
        if not stop or not stop.startswith((b"S", b"T")):
            raise RuntimeError(f"unexpected initial GDB stop reply: {stop!r}")
        _send_command(sock, b"c", expect_reply=False)

        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=0.2)
                raise RuntimeError(
                    f"mGBA exited before self-test report read (code {proc.returncode}).\n"
                    f"{(stdout or '')}{(stderr or '')}"
                )
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))

        sock.sendall(b"\x03")
        stopped = _recv_packet(sock)
        if not stopped.startswith((b"S", b"T")):
            raise RuntimeError(f"unexpected GDB interrupt reply: {stopped!r}")
        payload = f"m{REPORT_ADDRESS:x},{REPORT_BYTES:x}".encode("ascii")
        response = _send_command(sock, payload)
        assert response is not None
        if response.startswith(b"E"):
            raise RuntimeError(f"mGBA GDB memory read failed: {response.decode('ascii', 'replace')}")
        try:
            raw = bytes.fromhex(response.decode("ascii"))
        except ValueError as exc:
            raise RuntimeError("mGBA GDB returned non-hex report data") from exc
        words = _decode_report(raw)
        ok, errors = _validate_report(words)
        if not ok:
            print("mGBA hardware self-test failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            print(f"pass=0x{words[3]:02x} fail=0x{words[4]:02x} complete=0x{words[5]:08x}", file=sys.stderr)
            print(
                f"ending_guard=0x{words[16]:08x} "
                f"audio_irq_count={words[17]} audio_setup_ok={words[18]} "
                f"audio_ie=0x{words[19]:04x} audio_ime=0x{words[20]:04x}",
                file=sys.stderr,
            )
            return 1
        if screenshot_output is not None:
            assert xdotool is not None and screenshot_dir is not None
            _capture_ppu_screenshot(
                proc,
                sock,
                xdotool,
                screenshot_dir,
                existing_screenshots,
                screenshot_output,
                words,
                args.screenshot_timeout,
            )
        print(f"7/7 mGBA hardware self-test passed: {rom.name}")
        return 0
    except (OSError, RuntimeError, ConnectionError) as exc:
        print(f"mGBA hardware self-test error: {exc}", file=sys.stderr)
        return 1
    finally:
        if sock is not None:
            sock.close()
        _stop_process(proc)


if __name__ == "__main__":
    raise SystemExit(main())
