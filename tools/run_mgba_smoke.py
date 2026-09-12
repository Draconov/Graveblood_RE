#!/usr/bin/env python3
"""Boot a built Graveblood_RE ROM under mGBA and require it to stay alive.

This is intentionally a smoke gate, not a scripted gameplay oracle.  A healthy build
runs forever at the Title scene; an emulator process that exits before the requested
window is therefore a boot/runtime failure.  CI runs this under Xvfb with dummy audio.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


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


def _stop_process(proc: subprocess.Popen[str]) -> tuple[str, str]:
    proc.terminate()
    try:
        stdout, stderr = proc.communicate(timeout=1.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=1.0)
    return stdout, stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Boot a GBA ROM under mGBA for a bounded smoke window.")
    parser.add_argument("rom", type=Path, help="Path to the built .gba image")
    parser.add_argument("--emulator", help="Explicit mGBA executable (otherwise MGBA_BIN/PATH is searched)")
    parser.add_argument("--seconds", type=float, default=5.0, help="Required survival window (default: 5s)")
    args = parser.parse_args(argv)

    if args.seconds <= 0:
        parser.error("--seconds must be greater than zero")
    rom = args.rom.resolve()
    if not rom.is_file() or rom.stat().st_size == 0:
        print(f"ROM is missing or empty: {rom}", file=sys.stderr)
        return 2

    emulator = _find_emulator(args.emulator)
    if emulator is None:
        print("mGBA executable not found; install mgba-sdl/mgba or pass --emulator.", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    command = [emulator, "-C", "useBios=0", str(rom)]
    start = time.monotonic()
    proc = subprocess.Popen(
        command,
        cwd=str(rom.parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=args.seconds)
    except subprocess.TimeoutExpired:
        stdout, stderr = _stop_process(proc)
        elapsed = time.monotonic() - start
        print(f"mGBA survived {elapsed:.2f}s smoke window: {rom.name}")
        return 0

    output = (stdout or "") + (stderr or "")
    print(
        f"mGBA exited before the {args.seconds:.2f}s smoke window "
        f"(code {proc.returncode}).\n{output}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
