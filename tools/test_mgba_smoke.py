#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_mgba_smoke.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-release-rom.yml"


class MgbaSmokeRunnerTests(unittest.TestCase):
    def _fake_emulator(self, td: Path, body: str) -> Path:
        path = td / "fake-mgba"
        path.write_text("#!/bin/sh\n" + textwrap.dedent(body), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def _rom(self, td: Path) -> Path:
        path = td / "Graveblood_RE.gba"
        path.write_bytes(b"GBA" * 128)
        return path

    def test_smoke_passes_only_when_emulator_survives_timeout(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            emulator = self._fake_emulator(
                td,
                """
                test "$SDL_AUDIODRIVER" = dummy || exit 9
                sleep 2
                """,
            )
            rom = self._rom(td)
            proc = subprocess.run(
                [sys.executable, str(RUNNER), str(rom), "--emulator", str(emulator), "--seconds", "0.15"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            self.assertIn("survived", proc.stdout.lower())

    def test_relative_rom_path_remains_valid_after_runner_changes_directory(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td_raw:
            td = Path(td_raw)
            rom_dir = td / "dist"
            rom_dir.mkdir()
            rom = self._rom(rom_dir)
            emulator = self._fake_emulator(
                td,
                """
                test -f "$3" || exit 8
                sleep 2
                """,
            )
            relative_rom = rom.relative_to(ROOT)
            proc = subprocess.run(
                [sys.executable, str(RUNNER), str(relative_rom), "--emulator", str(emulator), "--seconds", "0.15"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)

    def test_smoke_fails_when_emulator_exits_before_window(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            emulator = self._fake_emulator(td, "exit 7\n")
            rom = self._rom(td)
            proc = subprocess.run(
                [sys.executable, str(RUNNER), str(rom), "--emulator", str(emulator), "--seconds", "0.5"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertNotEqual(0, proc.returncode)
            self.assertIn("exited", (proc.stderr + proc.stdout).lower())

    def test_smoke_reports_missing_emulator_without_guessing_success(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            rom = self._rom(td)
            env = os.environ.copy()
            env["PATH"] = str(td)
            proc = subprocess.run(
                [sys.executable, str(RUNNER), str(rom), "--seconds", "0.1"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(2, proc.returncode, proc.stderr + proc.stdout)
            self.assertIn("mGBA", proc.stderr)


class MgbaWorkflowWiringTests(unittest.TestCase):
    def test_release_workflow_has_no_extra_mgba_job_or_screenshot_artifact(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("emulator-smoke:", workflow)
        self.assertNotIn("mgba-sdl", workflow)
        self.assertNotIn("tools/run_mgba_smoke.py", workflow)
        self.assertNotIn("xvfb-run", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)


if __name__ == "__main__":
    unittest.main()
