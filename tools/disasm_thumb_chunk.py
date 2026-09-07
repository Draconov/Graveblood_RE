#!/usr/bin/env python3
"""Disassemble a Thumb chunk of a GBA ROM using the LLVM tools bundled here.

Example:
  python tools/disasm_thumb_chunk.py ROM.gba 0xD870 0x100
"""
from pathlib import Path
import argparse, subprocess, tempfile

ap=argparse.ArgumentParser()
ap.add_argument('rom', type=Path)
ap.add_argument('offset', type=lambda x:int(x,0))
ap.add_argument('size', type=lambda x:int(x,0))
a=ap.parse_args()
blob=a.rom.read_bytes()[a.offset:a.offset+a.size]
with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    (td/'chunk.bin').write_bytes(blob)
    (td/'wrap.S').write_text('.syntax unified\n.thumb\n.section .text\n.global _start\n_start:\n.incbin "chunk.bin"\n')
    subprocess.run(['clang','--target=arm-none-eabi','-c',str(td/'wrap.S'),'-o',str(td/'wrap.o')],cwd=td,check=True)
    obj_path = td / 'wrap.o'
    p=subprocess.run(['llvm-objdump','-d','--triple=thumbv4t-none-eabi',f'--adjust-vma=0x{0x08000000+a.offset:X}',str(obj_path)],cwd=td,check=True,text=True,capture_output=True)
    print(p.stdout.replace(str(obj_path), 'chunk.o'))
