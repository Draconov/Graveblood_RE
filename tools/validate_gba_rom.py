#!/usr/bin/env python3
"""Validate the built Graveblood_RE GBA cartridge header before release."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

EXPECTED_TITLE = b"GRAVEBLOODRE"
EXPECTED_GAME_CODE = b"GBR0"
EXPECTED_MAKER_CODE = b"00"
HEADER_MIN_BYTES = 0xC0


def header_checksum(header: bytes) -> int:
    return (-sum(header[0xA0:0xBD]) - 0x19) & 0xFF


def validate_rom(path: Path) -> list[str]:
    data = path.read_bytes()
    errors: list[str] = []
    if len(data) < HEADER_MIN_BYTES:
        return [f"ROM is too small for a GBA header: {len(data)} bytes"]

    title = data[0xA0:0xAC]
    game_code = data[0xAC:0xB0]
    maker = data[0xB0:0xB2]
    fixed = data[0xB2]
    checksum = data[0xBD]
    expected_checksum = header_checksum(data)

    if title != EXPECTED_TITLE:
        errors.append(f"unexpected title: {title!r} (expected {EXPECTED_TITLE!r})")
    if game_code != EXPECTED_GAME_CODE:
        errors.append(f"unexpected game code: {game_code!r} (expected {EXPECTED_GAME_CODE!r})")
    if maker != EXPECTED_MAKER_CODE:
        errors.append(f"unexpected maker code: {maker!r} (expected {EXPECTED_MAKER_CODE!r})")
    if fixed != 0x96:
        errors.append(f"invalid fixed header byte: 0x{fixed:02X} (expected 0x96)")
    if checksum != expected_checksum:
        errors.append(
            f"invalid header checksum: 0x{checksum:02X} (expected 0x{expected_checksum:02X})"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a built Graveblood_RE .gba header.")
    parser.add_argument("rom", type=Path)
    args = parser.parse_args(argv)

    if not args.rom.is_file():
        print(f"ROM not found: {args.rom}", file=sys.stderr)
        return 2

    errors = validate_rom(args.rom)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    data = args.rom.read_bytes()
    title = data[0xA0:0xAC].decode("ascii", "replace")
    code = data[0xAC:0xB0].decode("ascii", "replace")
    print(f"valid GBA header: title={title} game_code={code} bytes={len(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
