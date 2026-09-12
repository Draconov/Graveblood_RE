#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_gba_rom.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-release-rom.yml"


def make_rom() -> bytearray:
    rom = bytearray(0x200)
    rom[0xA0:0xAC] = b"GRAVEBLOODRE"
    rom[0xAC:0xB0] = b"GBR0"
    rom[0xB0:0xB2] = b"00"
    rom[0xB2] = 0x96
    rom[0xBC] = 0
    rom[0xBD] = (-sum(rom[0xA0:0xBD]) - 0x19) & 0xFF
    return rom


class GbaRomValidationTests(unittest.TestCase):
    def run_validator(self, payload: bytes) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as td_raw:
            path = Path(td_raw) / "Graveblood_RE.gba"
            path.write_bytes(payload)
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
            )

    def test_accepts_expected_graveblood_header_and_checksum(self):
        proc = self.run_validator(make_rom())
        self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
        self.assertIn("GRAVEBLOODRE", proc.stdout)
        self.assertIn("GBR0", proc.stdout)

    def test_rejects_wrong_game_identity(self):
        rom = make_rom()
        rom[0xA0:0xAC] = b"WRONGTITLE!!"
        rom[0xBD] = (-sum(rom[0xA0:0xBD]) - 0x19) & 0xFF
        proc = self.run_validator(rom)
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("title", proc.stderr.lower())

    def test_rejects_bad_header_complement(self):
        rom = make_rom()
        rom[0xBD] ^= 0x01
        proc = self.run_validator(rom)
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("checksum", proc.stderr.lower())

    def test_rejects_truncated_rom(self):
        proc = self.run_validator(b"tiny")
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("small", proc.stderr.lower())

    def test_build_workflow_validates_rom_before_upload(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        validator_pos = workflow.find("tools/validate_gba_rom.py")
        artifact_pos = workflow.find("actions/upload-artifact@v4")
        release_upload_pos = workflow.find("gh release upload")
        self.assertGreaterEqual(validator_pos, 0)
        self.assertGreater(artifact_pos, validator_pos)
        self.assertGreater(release_upload_pos, artifact_pos)
        self.assertIn("path: reconstruction/Graveblood_RE.gba", workflow)


if __name__ == "__main__":
    unittest.main()
