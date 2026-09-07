#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUTANO_COMMIT = '77dcbcb3d8783596a9f333c64eedbccec77b05dc'
DEVKIT_IMAGE = 'devkitpro/devkitarm:20260610'
ROM_NAME = 'Graveblood_RE.gba'
DEV_TAG = 'Graveblood_RE_v0.0.1-dev'
DEV_RELEASE_ROM = 'Graveblood_RE_v0.0.1.gba'


class ReconstructionBuildScaffoldTests(unittest.TestCase):
    def test_reconstruction_project_files_exist(self):
        for rel in (
            'reconstruction/Makefile',
            'reconstruction/src/main.cpp',
            'reconstruction/README.md',
            'DEVELOPING_AND_BUILDING.md',
            '.github/workflows/build-release-rom.yml',
        ):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_makefile_has_stable_butano_build_contract(self):
        text = (ROOT / 'reconstruction/Makefile').read_text(encoding='utf-8')
        self.assertIn('TARGET', text)
        self.assertIn('Graveblood_RE', text)
        self.assertNotIn('graveblood_reconstruction', text)
        self.assertIn('LIBBUTANO', text)
        self.assertIn('?=', text)
        self.assertIn('../vendor/butano/butano', text)
        self.assertIn('ROMTITLE', text)
        self.assertIn('GRAVEBLOOD', text)
        self.assertIn('ROMCODE', text)
        self.assertIn('GBR0', text)
        self.assertIn('AUDIOBACKEND', text)
        self.assertIn('null', text)
        self.assertIn('butano.mak', text)

    def test_main_is_visible_minimal_butano_dev_shell(self):
        text = (ROOT / 'reconstruction/src/main.cpp').read_text(encoding='utf-8')
        self.assertIn('#include "bn_core.h"', text)
        self.assertIn('#include "bn_bg_palettes.h"', text)
        self.assertIn('#include "bn_keypad.h"', text)
        self.assertIn('bn::core::init()', text)
        self.assertIn('bn::bg_palettes::set_transparent_color', text)
        self.assertIn('bn::keypad::a_pressed()', text)
        self.assertIn('bn::core::update()', text)
        self.assertIn('reconstruction', text.lower())

    def test_development_guide_pins_butano_and_exact_build_commands(self):
        text = (ROOT / 'DEVELOPING_AND_BUILDING.md').read_text(encoding='utf-8')
        self.assertIn(BUTANO_COMMIT, text)
        self.assertIn('git clone https://github.com/GValiente/butano.git vendor/butano', text)
        self.assertIn('make -C reconstruction LIBBUTANO=../vendor/butano/butano -j4', text)
        self.assertIn('make -C reconstruction LIBBUTANO=../vendor/butano/butano clean', text)
        self.assertIn(ROM_NAME, text)
        self.assertIn(DEV_TAG, text)
        self.assertIn(DEV_RELEASE_ROM, text)
        self.assertIn('mGBA', text)
        self.assertIn('git tag', text)
        self.assertIn('git push origin', text)
        self.assertIn('New-Item -ItemType Directory -Force vendor', text)

    def test_workspace_docs_link_to_development_guide(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        butano = (ROOT / 'BUTANO_REBUILD_NOTES.md').read_text(encoding='utf-8')
        self.assertIn('DEVELOPING_AND_BUILDING.md', readme)
        self.assertIn('reconstruction/', readme)
        self.assertIn('DEVELOPING_AND_BUILDING.md', butano)
        self.assertIn(BUTANO_COMMIT, butano)

    def test_workflow_builds_with_pinned_toolchain_and_butano(self):
        path = ROOT / '.github/workflows/build-release-rom.yml'
        text = path.read_text(encoding='utf-8')
        try:
            import yaml
        except ModuleNotFoundError:
            yaml = None
        if yaml is not None:
            data = yaml.load(text, Loader=yaml.BaseLoader)
            self.assertIsInstance(data, dict)
            self.assertIn('jobs', data)
            self.assertIn('build', data['jobs'])
            self.assertIn('release', data['jobs'])
        self.assertIn(DEVKIT_IMAGE, text)
        self.assertIn(BUTANO_COMMIT, text)
        self.assertIn('repository: GValiente/butano', text)
        self.assertIn('path: vendor/butano', text)
        self.assertIn('make -C reconstruction LIBBUTANO=../vendor/butano/butano', text)
        self.assertIn(ROM_NAME, text)
        self.assertIn('name: Graveblood_RE-rom', text)
        self.assertIn('actions/upload-artifact@v4', text)
        self.assertIn('actions/download-artifact@v4', text)

    def test_workflow_releases_only_version_tags(self):
        text = (ROOT / '.github/workflows/build-release-rom.yml').read_text(encoding='utf-8')
        self.assertIn("startsWith(github.ref, 'refs/tags/Graveblood_RE_v')", text)
        self.assertIn("endsWith(github.ref, '-dev')", text)
        self.assertIn('Graveblood_RE_v${VERSION}.gba', text)
        self.assertIn('--title "$GITHUB_REF_NAME"', text)
        self.assertIn('contents: write', text)
        self.assertIn('GH_REPO: ${{ github.repository }}', text)
        self.assertIn('gh release create', text)
        self.assertIn('gh release upload', text)
        self.assertIn('--clobber', text)

    def test_public_repo_identity_and_no_credits_file(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('Graveblood_RE', readme)
        self.assertFalse((ROOT / 'CREDITS.md').exists())

    def test_generated_roms_and_build_outputs_are_gitignored(self):
        text = (ROOT / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('reconstruction/build/', text)
        self.assertIn('reconstruction/*.gba', text)
        self.assertIn('reconstruction/*.elf', text)


if __name__ == '__main__':
    unittest.main()
