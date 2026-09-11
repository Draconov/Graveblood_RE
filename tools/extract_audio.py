#!/usr/bin/env python3
"""Extract Graveblood's canonical custom-PCM audio resources and evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from disasm_thumb_chunk import disassemble_thumb_blob  # noqa: E402

ROM_BASE = 0x08000000
CANONICAL_SHA256 = 'e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b'
SOUND_TABLE_OFFSET = 0x65662C
SOUND_COUNT = 14

EXPECTED = (
    (0x088F68C8, 0x18435C),
    (0x087FBE00, 0x0FAAC5),
    (0x08663E00, 0x198000),
    (0x08A82954, 0x0D6D),
    (0x08A83EF4, 0x0248),
    (0x08A8413C, 0x4482),
    (0x08A885C0, 0x3A67),
    (0x08A8222C, 0x0728),
    (0x08A82140, 0x00EC),
    (0x08A7E110, 0x3476),
    (0x08A7AC24, 0x34EC),
    (0x08A81588, 0x0BB6),
    (0x08A836C4, 0x082D),
    (0x0865669C, 0xD762),
)

DISASM_RANGES = (
    ('audio_mixer_08001940.txt', 0x1910, 0x140),
    ('audio_init_08001A6C.txt', 0x1A6C, 0xC0),
    ('audio_play_once_08001B74.txt', 0x1B74, 0x68),
    ('audio_play_loop_08001BDC.txt', 0x1BDC, 0x6C),
    ('audio_channel_controls_08001C48.txt', 0x1C48, 0x90),
    ('audio_gameplay_music_entry_08005A60.txt', 0x5A60, 0x50),
    ('audio_music_selector_fade_08008320.txt', 0x8320, 0x40),
    ('audio_music_replace_08008A70.txt', 0x8A70, 0x48),
    ('audio_music_restore_08009414.txt', 0x9414, 0x30),
    ('audio_iwram_data_copy_08000144.txt', 0x144, 0xC8),
    ('audio_pda_return_080075C8.txt', 0x75C8, 0x70),
    ('audio_pda_open_080084B0.txt', 0x84B0, 0x70),
    ('audio_pda_messages_cursor_080098D0.txt', 0x98D0, 0x110),
    ('audio_interaction_confirm_08009C80.txt', 0x9C80, 0x90),
    ('audio_effect_sfx4_constructor_0800B250.txt', 0xB250, 0x70),
    ('audio_effect_sfx3_constructor_0800B31C.txt', 0xB31C, 0x90),
)

IWRAM_DATA_ROM = 0x08A8D738
IWRAM_DATA_RAM = 0x03000788
IWRAM_DATA_END = 0x03002424
MUSIC_FADE_RAM = 0x030013C0
MUSIC_FADE_ROM = IWRAM_DATA_ROM + (MUSIC_FADE_RAM - IWRAM_DATA_RAM)
MUSIC_FADE_WORDS = 75

@dataclass(frozen=True)
class CallSite:
    address: int
    target: int
    caller: str
    sound_id: str
    play_mode: str
    volume: str
    action: str
    confidence: str


def decode_bl_target(rom: bytes, off: int) -> int | None:
    if off + 4 > len(rom):
        return None
    h1, h2 = struct.unpack_from('<HH', rom, off)
    if (h1 & 0xF800) != 0xF000 or (h2 & 0xF800) != 0xF800:
        return None
    raw = ((h1 & 0x07FF) << 12) | ((h2 & 0x07FF) << 1)
    if raw & 0x400000:
        raw -= 0x800000
    return ROM_BASE + off + 4 + raw


def scan_calls(rom: bytes, target: int, limit: int | None = None) -> list[int]:
    result = []
    stop = len(rom) - 3 if limit is None else min(limit, len(rom) - 3)
    for off in range(0, stop, 2):
        if decode_bl_target(rom, off) == target:
            result.append(ROM_BASE + off)
    return result


def previous_mov_imm(rom: bytes, call_addr: int, reg: int) -> int | None:
    off = call_addr - ROM_BASE
    for distance in range(2, 22, 2):
        pos = off - distance
        if pos < 0:
            break
        hw = struct.unpack_from('<H', rom, pos)[0]
        # MOVS Rd, #imm8 (Thumb-1)
        if (hw & 0xF800) == 0x2000 and ((hw >> 8) & 7) == reg:
            return hw & 0xFF
        # Do not walk across an unconditional B.
        if (hw & 0xF800) == 0xE000:
            break
    return None


def parse_symbols(repo_root: Path) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    sym = repo_root / 'data' / 'graveblood_001152.sym'
    if not sym.is_file():
        return result
    for line in sym.read_text(encoding='utf-8').splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        try:
            addr = int(parts[0], 16)
        except ValueError:
            continue
        if addr >= ROM_BASE:
            result.append((addr, parts[1]))
    return sorted(result)


def nearest_symbol(symbols: list[tuple[int, str]], address: int) -> str:
    best = 'unresolved_function'
    for sym_addr, name in symbols:
        if sym_addr > address:
            break
        best = name
    return best


def format_imm(value: int | None) -> str:
    return 'dynamic' if value is None else str(value)


def build_call_sites(rom: bytes, repo_root: Path) -> list[CallSite]:
    symbols = parse_symbols(repo_root)
    known_one_shot_actions = {
        0x08002E22: ('state-2 dialogue interaction activation', 'high'),
        0x08003078: ('state-4 collection interaction activation', 'high'),
        0x0800368E: ('state4 dialogue opcode -2 terminal', 'high'),
        0x08003748: ('state4 dialogue opcode -1 terminal', 'high'),
        0x0800389A: ('state4 dialogue opcode -3 terminal', 'high'),
        0x0800426C: ('generic scene portal activation', 'high'),
        0x08004B2A: ('fresh START title transition', 'high'),
        0x080084DC: ('fresh START PDA/menu open', 'high'),
        0x080075D2: ('PDA/menu return-to-gameplay transition; consumes 0x03000618 pending flag', 'high'),
        0x0800898E: ('PDA menu tab previous (fresh L; MESSAGES/STATUS/FRIENDS/BACKPACK)', 'high'),
        0x080089F8: ('FRIENDS successful UP navigation', 'high'),
        0x0800904E: ('PDA menu tab next (fresh R; MESSAGES/STATUS/FRIENDS/BACKPACK)', 'high'),
        0x0800909C: ('FRIENDS successful DOWN navigation', 'high'),
        0x08009904: ('PDA MESSAGES cursor previous (fresh LEFT; cursor 0..3)', 'high'),
        0x0800999E: ('PDA MESSAGES cursor next (fresh RIGHT; cursor 0..3)', 'high'),
        0x08009CCA: ('interaction state-2 return/back (fresh B)', 'high'),
        0x0800B2A6: ('effect-object constructor 0x0800B250 (vtable 0x08A8C198)', 'high'),
        0x0800B37E: ('effect-object constructor 0x0800B31C (vtable 0x08A8C1E8; spawned by 0x080026E8/0x080060C4)', 'high'),
        0x08003802: ('final-sketch state4 -5 transition', 'high'),
        0x08003D5C: ('fresh-A generic Fgtile activation for turn != 4/5', 'high'),
        0x08003298: ('legsColor 0x70 NPC proximity latch activation', 'high'),
        0x080032AC: ('alternate state-2 interaction activation when 0x0300062C mode byte is nonzero', 'high'),
        0x080032D2: ('normal dialogue opcode -4 set story/progression stage', 'high'),
        0x080033A2: ('normal dialogue opcode -3 add auxiliary message stream', 'high'),
        0x08003462: ('normal dialogue opcode -2 set primary message stream', 'high'),
        0x08003516: ('normal dialogue opcode -1 set dialogue step', 'high'),
        0x08003668: ('alternate state-4 interaction activation when 0x0300062C mode byte is nonzero', 'high'),
        0x08009AA2: ('FRIENDS DOWN-at-bottom boundary feedback', 'high'),
        0x08009B58: ('FRIENDS UP-at-top boundary feedback', 'high'),
        0x08009C16: ('fresh R Player action/state-reset path', 'high'),
    }
    sites: list[CallSite] = []
    for target, kind in ((0x08001B74, 'one-shot'), (0x08001BDC, 'loop')):
        for address in scan_calls(rom, target):
            sound = previous_mov_imm(rom, address, 0)
            r1 = previous_mov_imm(rom, address, 1)
            r2 = previous_mov_imm(rom, address, 2)
            action = f'{kind} call; gameplay action unresolved'
            confidence = 'medium'
            if address in {0x08002E22, 0x08003078}:
                # These calls are reached through a conditional branch that skips
                # an intervening unconditional B, so the simple linear backwards
                # scanner cannot see the code-proven MOVS r1,#0x50 predecessor.
                sound, r1 = 3, 0x50
            if address in {0x080032AC, 0x08003668}:
                # Both SFX8 branches retain r1=0x50 from the activation gate at
                # 0x08002E18 / 0x0800306E across a long conditional branch.
                sound, r1 = 8, 0x50
            if address == 0x08003298:
                sound, r1 = 9, 0x50
            if address in {0x080032D2, 0x080033A2, 0x08003462, 0x08003516}:
                # Normal-dialogue opcode terminal/effect branches all play
                # SFX7 at 0x50.  The -4 branch carries r1=0x8C into the
                # handler and subtracts 0x3C immediately before the call,
                # which defeats the simple backwards MOV scanner.
                sound, r1 = 7, 0x50
            if address in {0x08009AA2, 0x08009B58}:
                sound, r1 = 12, 0x50
            if address == 0x08009C16:
                sound, r1 = 10, 0x1E
            if address == 0x08003802:
                sound, r1 = 13, 0x50
            if address in {0x0800368E, 0x08003748, 0x0800389A}:
                sound, r1 = 7, 0x50
            if address in known_one_shot_actions:
                action, confidence = known_one_shot_actions[address]
            if target == 0x08001BDC:
                sound = None
                play_mode = format_imm(r1)
                volume = format_imm(r2)
                action = 'dynamic music start/restore via Player+0x1CC selector and Player+0x1D4 ID table'
                confidence = 'high'
            else:
                # 0x08001B74 consumes only r0=sound_id and r1=volume.  The
                # caller's live r2 value is not an audio parameter and must not
                # be promoted into the semantic call-site schema.
                play_mode = 'one-shot'
                volume = format_imm(r1)
            caller = nearest_symbol(symbols, address)
            if address == 0x08003298:
                caller = 'npc_special_proximity_latch'
            sites.append(CallSite(
                address=address,
                target=target,
                caller=caller,
                sound_id=format_imm(sound),
                play_mode=play_mode,
                volume=volume,
                action=action,
                confidence=confidence,
            ))
    for target, action in (
        (0x08001C48, 'channel mode byte update'),
        (0x08001C68, 'channel volume/parameter update'),
        (0x08001CB0, 'reserved channel stop/clear'),
    ):
        for address in scan_calls(rom, target):
            sites.append(CallSite(
                address=address,
                target=target,
                caller=nearest_symbol(symbols, address),
                sound_id='n/a', play_mode='n/a', volume='dynamic',
                action=action, confidence='high',
            ))
    return sorted(sites, key=lambda item: item.address)


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)


def write_audio_data_c(path: Path) -> None:
    lines = [
        '#include <graveblood/assets.h>', '',
    ]
    for i in range(SOUND_COUNT):
        lines.append(f'extern const s8 gb_audio_sample_{i:02d}_start[];')
        lines.append(f'extern const s8 gb_audio_sample_{i:02d}_end[];')
    lines.extend(['', 'const GbAudioSample gb_audio_samples[GB_AUDIO_SAMPLE_COUNT] = {'])
    for i, (_, length) in enumerate(EXPECTED):
        role = 'GB_AUDIO_ROLE_MUSIC' if i < 3 else 'GB_AUDIO_ROLE_SFX'
        lines.append(
            f'    {{ gb_audio_sample_{i:02d}_start, {length}u, {role} }},'
        )
    lines.extend(['};', ''])
    path.write_text('\n'.join(lines), encoding='utf-8')


def write_audio_asm(path: Path) -> None:
    lines = ['.section .rodata', '.balign 4', '']
    for i in range(SOUND_COUNT):
        lines.extend([
            f'.global gb_audio_sample_{i:02d}_start',
            f'.global gb_audio_sample_{i:02d}_end',
            f'gb_audio_sample_{i:02d}_start:',
            f'    .incbin "../data/audio/sample_{i:02d}.pcm"',
            f'gb_audio_sample_{i:02d}_end:',
            '    .balign 4',
            '',
        ])
    path.write_text('\n'.join(lines), encoding='utf-8')


def extract(rom_path: Path, repo_root: Path) -> None:
    rom = rom_path.read_bytes()
    digest = hashlib.sha256(rom).hexdigest()
    if digest != CANONICAL_SHA256:
        raise SystemExit(f'canonical ROM SHA-256 mismatch: {digest}')

    records = tuple(struct.unpack_from('<II', rom, SOUND_TABLE_OFFSET + i * 8) for i in range(SOUND_COUNT))
    if records != EXPECTED:
        raise SystemExit('canonical sound table does not match recovered pointer/length records')

    audio_dir = repo_root / 'reconstruction' / 'data' / 'audio'
    audio_dir.mkdir(parents=True, exist_ok=True)
    sample_rows: list[list[object]] = []
    for sound_id, (pointer, length) in enumerate(records):
        start = pointer - ROM_BASE
        end = start + length
        if start < 0 or end > len(rom):
            raise SystemExit(f'sound {sound_id} points outside ROM')
        payload = rom[start:end]
        (audio_dir / f'sample_{sound_id:02d}.pcm').write_bytes(payload)
        sample_rows.append([
            sound_id, f'0x{pointer:08X}', length, length & ~3,
            'music' if sound_id < 3 else 'sfx',
            f'{(length & ~3) / 16384.0:.6f}', hashlib.sha256(payload).hexdigest(),
        ])

    write_csv(
        repo_root / 'data' / 'audio_samples.csv',
        ['sound_id', 'rom_address', 'byte_length', 'aligned_length', 'role', 'aligned_duration_seconds_16384hz', 'sha256'],
        sample_rows,
    )

    sites = build_call_sites(rom, repo_root)
    write_csv(
        repo_root / 'data' / 'audio_call_sites.csv',
        ['call_address', 'target', 'caller', 'sound_id', 'play_mode', 'volume', 'recovered_action', 'confidence'],
        [[f'0x{s.address:08X}', f'0x{s.target:08X}', s.caller, s.sound_id, s.play_mode, s.volume, s.action, s.confidence] for s in sites],
    )

    one_shot_sites = [s for s in sites if s.target == 0x08001B74]
    one_shot_high = [s for s in one_shot_sites if s.confidence == 'high' and 'unresolved' not in s.action.lower()]
    one_shot_medium = [s for s in one_shot_sites if s not in one_shot_high]
    if len(one_shot_sites) != 30 or len(one_shot_high) != 30 or one_shot_medium:
        raise SystemExit(
            'one-shot call graph closure drifted: '
            f'total={len(one_shot_sites)} high={len(one_shot_high)} '
            f'unresolved={[hex(s.address) for s in one_shot_medium]}'
        )
    reachable_one_shot_ids = sorted({int(s.sound_id) for s in one_shot_sites if s.sound_id.isdigit()})
    write_csv(
        repo_root / 'data' / 'audio_one_shot_closure.csv',
        ['one_shot_call_count', 'high_confidence_count', 'medium_confidence_count',
         'reachable_sound_ids', 'static_one_shot_call_graph_closed', 'evidence'],
        [[len(one_shot_sites), len(one_shot_high), len(one_shot_medium),
          ';'.join(str(v) for v in reachable_one_shot_ids), 'yes',
          'exhaustive full-ROM Thumb BL scan to 0x08001B74; every recovered call has code-bounded action semantics']],
    )

    loop_calls = [s.address for s in sites if s.target == 0x08001BDC]
    if loop_calls != [0x08005A8A, 0x08008AA0, 0x08009428]:
        raise SystemExit(f'unexpected exhaustive loop-player call set: {[hex(a) for a in loop_calls]}')
    if any(s.sound_id == '2' for s in sites if s.target == 0x08001B74):
        raise SystemExit('sample 2 unexpectedly gained a one-shot call')

    write_csv(
        repo_root / 'data' / 'pda_menu_pages.csv',
        ['selector', 'page_name', 'renderer_branch', 'key_policy', 'evidence'],
        [
            [0, 'MESSAGES', '0x08007642', 'L decrements only when selector > 0', '0x080075F8 dispatches selector 0 to MESSAGES branch'],
            [1, 'STATUS', '0x0800795C', 'L/R move within selector bounds 0..3', '0x080075F8 dispatches selector 1 to STATUS branch'],
            [2, 'FRIENDS', '0x0800777A', 'L/R move within selector bounds 0..3', '0x080075F8 dispatches selector 2 to FRIENDS branch'],
            [3, 'BACKPACK', '0x08007A10', 'R increments only when selector <= 2', '0x080075F8 dispatches selector 3 to BACKPACK branch'],
        ],
    )

    write_csv(
        repo_root / 'data' / 'audio_music_routes.csv',
        ['call_address', 'caller', 'route', 'selector_source', 'sound_id', 'confidence', 'evidence'],
        [
            ['0x08005A8A', 'GameplayScene_enter', 'default gameplay entry', 'Player+0x1CC == 0 after Player constructor', 0, 'high', '0x080062F8 initializes Player+0x1CC=0; 0x08005A6E reads it and Player+0x1D4[0] is 0'],
            ['0x08005A8A', 'GameplayScene_enter', 'level 10 forced gameplay entry', 'level id == 10 forces Player+0x1CC=1 at 0x08005BA0', 1, 'high', '0x08005A68 compares level id to 10; 0x08005BA0 stores selector 1; Player+0x1D4[1] is 1'],
            ['0x08008AA0', 'Player_update', 'interaction music restore', 'current Player+0x1CC selector', 'dynamic 0/1', 'high', '0x08008A88 stops reserved channel 0 then reloads Player+0x1D4[Player+0x1CC]'],
            ['0x08009428', 'Player_update', 'interaction music start/restore', 'current Player+0x1CC selector', 'dynamic 0/1', 'high', '0x08009414 loads Player+0x1D4[Player+0x1CC] and calls loop player'],
            ['n/a', 'code-proven unreachable', 'sample 2 unreachable/orphaned in public demo', 'no reachable selector value 2 and no direct play call', 2, 'high', 'exhaustive full-ROM loop-player scan finds exactly three calls; all route through Player+0x1D4 using selector 0/1; exhaustive one-shot scan has no sound ID 2'],
        ],
    )

    fade_values = list(struct.unpack_from(
        f'<{MUSIC_FADE_WORDS}I',
        rom,
        MUSIC_FADE_ROM - ROM_BASE,
    ))
    expected_fade = list(range(142, 0, -2)) + [0, 0, 0, 0]
    if fade_values != expected_fade:
        raise SystemExit(f'music fade table drifted: {fade_values!r}')
    following_word = struct.unpack_from(
        '<I', rom, MUSIC_FADE_ROM - ROM_BASE + MUSIC_FADE_WORDS * 4
    )[0]
    if following_word != 0x03001704:
        raise SystemExit(f'music fade terminal following word drifted: 0x{following_word:08X}')

    write_csv(
        repo_root / 'data' / 'audio_music_fade.csv',
        ['index', 'value'],
        [[i, value] for i, value in enumerate(fade_values)],
    )
    write_csv(
        repo_root / 'data' / 'audio_music_runtime.csv',
        ['fact', 'value', 'evidence'],
        [
            ['sample_format', 'signed 8-bit PCM @ 16384 Hz', 'custom mixer consumes one signed byte per output sample; all payload lengths/durations use 16384 Hz'],
            ['mixer_channels', 8, '0x08001BDC scans eight 0x1C-byte channel records'],
            ['channel_record_bytes', 28, 'channel allocator advances by 0x1C bytes for each of eight records'],
            ['mode_1_end_behavior', 'deactivate at aligned sample end', '0x08001940 mixer clears the channel mode when mode==1 reaches its aligned payload end'],
            ['mode_2_end_behavior', 'loop by resetting sample cursor', '0x08001940 mixer resets the cursor to the sample start when a non-one-shot active mode reaches its aligned payload end'],
            ['loop_reserved_flag', 'channel+0x18=1', '0x08001BDC marks the selected loop channel reserved so ordinary one-shots cannot steal it'],
            ['allocator_policy', 'first channel with mode=0 and reserved=0 among eight records', '0x08001B74/0x08001BDC scan records in canonical order and reject active or reserved slots'],
            ['one_shot_signature', '(sound_id, volume)', '0x08001B74 consumes incoming r0/r1; incoming r2 is overwritten and has no audio semantics'],
            ['loop_player_signature', '(sound_id, mode, volume)', '0x08001BDC consumes r0 sound ID, stores r1 mode byte, stores r2 volume word'],
            ['music_mode', 2, 'all three exhaustive loop-player calls set r1=2'],
            ['music_start_volume', 144, 'all three exhaustive loop-player calls set r2=0x90'],
            ['loop_player_calls', '0x08005A8A 0x08008AA0 0x08009428', 'exhaustive full-ROM Thumb BL scan'],
            ['title_music', 'none', 'no TitleScene loop-player call; title is absent from the exhaustive loop-player call set'],
            ['selector_desired', 'Player+0x1CC', '0x08005A6E/0x08008328/0x08008A92/0x08009414'],
            ['selector_applied', 'Player+0x1D0', '0x08008330 comparison and 0x08008AA8 copy after replacement'],
            ['selector_id_table', 'Player+0x1D4: [0]=0 [1]=1', 'Player constructor initializes the two reachable selector slots; level 10 only forces selector 1'],
            ['sample_2_reachability', 'unreachable/orphaned in public demo', 'selector initialization/writes expose 0/1 only; no direct loop or one-shot call to sound ID 2'],
            ['fade_counter', 'global+0x68 (base used by Player_update)', '0x08008332 tests it; 0x08008A74 increments/stores it'],
            ['fade_table_runtime', f'0x{MUSIC_FADE_RAM:08X}', 'literal used by Player_update music volume update'],
            ['fade_table_rom', f'0x{MUSIC_FADE_ROM:08X}', 'startup copies ROM 0x08A8D738 to IWRAM 0x03000788, giving exact relocation to runtime 0x030013C0'],
            ['fade_table_words', MUSIC_FADE_WORDS, 'values 142,140,...,2,0,0,0,0'],
            ['fade_replace_threshold', 75, 'desired!=applied path increments through counter 75, stops channel 0, starts selected loop, copies desired->applied, resets counter'],
            ['fade_terminal_quirk', 'counter75 indexes one word past the 75-word fade table (0x03001704) before immediate channel0 stop/restart', '0x08008A70 indexes before cmp #0x4B; word following ROM table is 0x03001704'],
            ['interaction_restore_seed', 'byte loaded from 0x0300062C is stored to fade counter before 0x08009428', '0x080084A0 loads r6 from global base byte; 0x08009426 stores r6 to [global+0x68]'],
        ],
    )

    write_audio_data_c(repo_root / 'reconstruction' / 'data' / 'audio_data.c')
    write_audio_asm(repo_root / 'reconstruction' / 'data' / 'audio_samples.s')

    disasm_dir = repo_root / 'disasm'
    disasm_dir.mkdir(parents=True, exist_ok=True)
    for name, offset, size in DISASM_RANGES:
        text = disassemble_thumb_blob(rom[offset:offset + size], ROM_BASE + offset)
        (disasm_dir / name).write_text(text, encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('rom', type=Path)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    extract(args.rom.resolve(), args.repo_root.resolve())


if __name__ == '__main__':
    main()
