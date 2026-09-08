#!/usr/bin/env python3
"""Disassemble a Thumb chunk of a GBA ROM.

LLVM is preferred when clang + llvm-objdump are available.  A Python Capstone
fallback keeps the RE helper usable in lighter environments that do not ship
LLVM tooling.

Example:
  python tools/disasm_thumb_chunk.py ROM.gba 0xD870 0x100
"""
from __future__ import annotations

from pathlib import Path
import argparse
import shutil
import subprocess
import tempfile

ROM_BASE = 0x08000000


def disassemble_with_llvm(blob: bytes, base: int) -> str:
    with tempfile.TemporaryDirectory() as td_value:
        td = Path(td_value)
        (td / 'chunk.bin').write_bytes(blob)
        (td / 'wrap.S').write_text(
            '.syntax unified\n.thumb\n.section .text\n.global _start\n_start:\n.incbin "chunk.bin"\n',
            encoding='utf-8',
        )
        subprocess.run(
            ['clang', '--target=arm-none-eabi', '-c', str(td / 'wrap.S'), '-o', str(td / 'wrap.o')],
            cwd=td,
            check=True,
        )
        obj_path = td / 'wrap.o'
        result = subprocess.run(
            [
                'llvm-objdump', '-d', '--triple=thumbv4t-none-eabi',
                f'--adjust-vma=0x{base:X}', str(obj_path),
            ],
            cwd=td,
            check=True,
            text=True,
            capture_output=True,
        )
        return result.stdout.replace(str(obj_path), 'chunk.o')


def disassemble_with_capstone(blob: bytes, base: int, capstone_module=None) -> str:
    if capstone_module is None:
        try:
            import capstone as capstone_module
        except ImportError as exc:
            raise RuntimeError(
                'LLVM tools are unavailable and Python Capstone is not installed; '
                'install the capstone package to use the fallback'
            ) from exc

    engine = capstone_module.Cs(
        capstone_module.CS_ARCH_ARM,
        capstone_module.CS_MODE_THUMB | capstone_module.CS_MODE_LITTLE_ENDIAN,
    )
    lines = [
        'chunk.o: file format binary',
        '',
        'Disassembly of section .text:',
        '',
    ]
    for insn in engine.disasm(blob, base):
        raw = ' '.join(f'{byte:02x}' for byte in insn.bytes)
        operands = f'\t{insn.op_str}' if insn.op_str else ''
        lines.append(f'{insn.address:08x}:\t{raw:<11}\t{insn.mnemonic}{operands}')
    return '\n'.join(lines) + '\n'


def disassemble_thumb_blob(blob: bytes, base: int) -> str:
    if shutil.which('clang') and shutil.which('llvm-objdump'):
        return disassemble_with_llvm(blob, base)
    return disassemble_with_capstone(blob, base)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', type=Path)
    ap.add_argument('offset', type=lambda x: int(x, 0))
    ap.add_argument('size', type=lambda x: int(x, 0))
    args = ap.parse_args()
    blob = args.rom.read_bytes()[args.offset:args.offset + args.size]
    try:
        print(disassemble_thumb_blob(blob, ROM_BASE + args.offset), end='')
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == '__main__':
    main()
