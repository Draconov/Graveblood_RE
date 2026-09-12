#!/usr/bin/env python3
import importlib.util
import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_PATH = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))
SPEC = importlib.util.spec_from_file_location('extract_structure', ROOT / 'tools' / 'extract_structure.py')
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
DISASM_SPEC = importlib.util.spec_from_file_location('disasm_thumb_chunk', ROOT / 'tools' / 'disasm_thumb_chunk.py')
disasm = importlib.util.module_from_spec(DISASM_SPEC)
DISASM_SPEC.loader.exec_module(disasm)

class LevelStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM_PATH.read_bytes()

    def test_level_table_uses_true_record_base(self):
        self.assertEqual(mod.LEVEL_DESC_OFF, 0x00A8D9C0)
        vals = struct.unpack_from('<16I', self.data, mod.LEVEL_DESC_OFF)
        self.assertEqual(vals[0x38 // 4], 0x0853B05C)

    def test_runtime_dimensions_match_constructor_values(self):
        expected = [
            (256,256,64,32), (64,64,64,32), (256,200,64,32),
            (256,160,64,32), (192,160,64,32), (320,200,64,32),
            (30,20,30,20), (29,24,64,32), (37,43,64,32),
            (782,128,64,32), (168,128,64,32),
        ]
        self.assertEqual(mod.reconstruct_level_dimensions(self.data), expected)

    def test_graphics_descriptor_is_mapped_from_iwram(self):
        vals = struct.unpack_from('<16I', self.data, mod.LEVEL_DESC_OFF)
        row = mod.parse_graphics_descriptor(self.data, vals[0x24 // 4])
        self.assertEqual(row['bg_tiles_source'], 0x0863A5D8)
        self.assertEqual(row['tile_translation_table'], 0x0864825C)
        self.assertEqual(row['obj_tiles_source'], 0x08310654)

    def test_level_graphics_variants_are_contiguous_descriptor_slots(self):
        level0 = struct.unpack_from('<16I', self.data, mod.LEVEL_DESC_OFF)
        level1 = struct.unpack_from('<16I', self.data, mod.LEVEL_DESC_OFF + mod.LEVEL_DESC_SIZE)
        self.assertEqual(
            mod.level_graphics_variant_ptrs(level0),
            [0x03000CD0, 0x03000CF4, 0x03000D3C],
        )
        self.assertEqual(mod.level_graphics_variant_ptrs(level1), [0x03000D18])

    def test_level6_collision_visual_b_alias_is_intentional_and_runtime_separated(self):
        row = mod.level6_collision_visual_alias_closure(self.data)
        self.assertEqual(row['level_index'], 6)
        self.assertEqual(row['shared_rom_addr'], '0x08655CC4')
        self.assertEqual(row['collision_record_offset'], '+0x0C')
        self.assertEqual(row['visual_b_record_offset'], '+0x10')
        self.assertEqual(row['collision_runtime_global'], '0x03000550')
        self.assertEqual(row['visual_b_runtime_global'], '0x03000564')
        self.assertEqual(row['collision_consumer'], '0x08004670')
        self.assertEqual(row['visual_b_consumer'], '0x0800A330')
        self.assertEqual(row['runtime_roles_separated'], 'yes')
        self.assertEqual(row['classification'], 'intentional source-data alias')

    def test_disasm_helper_normalizes_temporary_object_path(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'tools' / 'disasm_thumb_chunk.py'), str(ROM_PATH), '0xD870', '0x20'],
            check=True, text=True, capture_output=True,
        )
        self.assertNotIn('/tmp/', result.stdout)
        self.assertIn('chunk.o:', result.stdout)

    def test_disasm_helper_has_capstone_fallback_formatter(self):
        class FakeInsn:
            address = 0x0800D870
            mnemonic = 'movs'
            op_str = 'r0, #1'
            bytes = b'\x01\x20'

        class FakeCs:
            def __init__(self, arch, mode):
                self.arch = arch
                self.mode = mode

            def disasm(self, blob, base):
                self.blob = blob
                self.base = base
                return [FakeInsn()]

        class FakeCapstone:
            CS_ARCH_ARM = 1
            CS_MODE_THUMB = 2
            CS_MODE_LITTLE_ENDIAN = 4
            Cs = FakeCs

        text = disasm.disassemble_with_capstone(b'\x01\x20', 0x0800D870, FakeCapstone)
        self.assertIn('0800d870', text.lower())
        self.assertIn('movs', text)
        self.assertIn('r0, #1', text)

if __name__ == '__main__':
    unittest.main()
