#!/usr/bin/env python3
"""Find exact code/data fingerprints shared by the Graveblood latest demo and alpha.

The latest demo remains authoritative. This tool uses the alpha only to locate
unchanged inherited regions. It never copies content from the alpha into the
latest-ROM extraction.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import defaultdict
from pathlib import Path

LATEST_SHA256 = "e0d7878d2f41dcdeedcc306585bdaf18f39abc2ae42a4bc338514d49feb9449b"
ALPHA_SHA256 = "f63e1604c3887a9f018961cadca6365fe621f006b83f458702c68b079e0b0f0a"
ROM_BASE = 0x08000000

SEMANTIC_ANCHORS = [
    (0x08000384, 0x08000384, "actor_property_int_lookup", "high", "same named-integer property lookup helper"),
    (0x080043AC, 0x08002950, "actor_level_global_policy_vs_alpha_noop", "high", "alpha homolog is bx lr; latest adds level/setglobal policy before unchanged following actor methods"),
    (0x080043E0, 0x08002954, "actor_following_method", "high", "homologous method immediately after policy slot"),
    (0x080043F8, 0x0800296C, "actor_common_property_parser", "high", "shared base parser; alpha ends after portTo while latest continues with level/setglobal/state/dial/route"),
    (0x08003B98, 0x08002560, "portal_fgtile_actor_family", "medium", "homologous actor/update family; latest is substantially expanded"),
    (0x0801061C, 0x08008B20, "cpp_runtime_init_candidate", "medium", "homologous startup/runtime initializer region; address delta +0x7afc"),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_windows(data: bytes, start: int, end: int, width: int, step: int = 2):
    """Return window->offset only when the window occurs exactly once."""
    seen: dict[bytes, int | None] = {}
    end = min(end, len(data))
    for off in range(start, max(start, end - width + 1), step):
        w = data[off:off+width]
        if not any(w):
            continue
        if w in seen:
            seen[w] = None
        else:
            seen[w] = off
    return {w: off for w, off in seen.items() if off is not None}


def build_matches(latest: bytes, alpha: bytes, latest_start: int, latest_end: int,
                  alpha_start: int, alpha_end: int, width: int, min_size: int):
    a = unique_windows(alpha, alpha_start, alpha_end, width)
    l = unique_windows(latest, latest_start, latest_end, width)
    anchors = []
    for w, loff in l.items():
        aoff = a.get(w)
        if aoff is not None:
            anchors.append((loff, aoff))
    anchors.sort()

    # Consecutive 2-byte-aligned unique windows with an identical delta form
    # one exact shared block. Because the windows overlap, span grows by 2.
    runs = []
    if anchors:
        run_l, run_a = anchors[0]
        prev_l, prev_a = anchors[0]
        delta = run_l - run_a
        for loff, aoff in anchors[1:]:
            if loff == prev_l + 2 and aoff == prev_a + 2 and loff - aoff == delta:
                prev_l, prev_a = loff, aoff
                continue
            size = (prev_l - run_l) + width
            if size >= min_size:
                runs.append((run_l, run_a, size))
            run_l, run_a = loff, aoff
            prev_l, prev_a = loff, aoff
            delta = loff - aoff
        size = (prev_l - run_l) + width
        if size >= min_size:
            runs.append((run_l, run_a, size))

    # Extend each run byte-for-byte to a maximal exact block, then deduplicate.
    maximal = set()
    for loff, aoff, size in runs:
        l0, a0 = loff, aoff
        while l0 > latest_start and a0 > alpha_start and latest[l0-1] == alpha[a0-1]:
            l0 -= 1; a0 -= 1; size += 1
        while (l0 + size < min(latest_end, len(latest)) and
               a0 + size < min(alpha_end, len(alpha)) and
               latest[l0+size] == alpha[a0+size]):
            size += 1
        maximal.add((l0, a0, size))

    # Drop contained duplicates on the same delta.
    out = []
    for m in sorted(maximal, key=lambda x: (-x[2], x[0], x[1])):
        loff, aoff, size = m
        delta = loff - aoff
        contained = False
        for L, A, S in out:
            if L - A == delta and L <= loff and A <= aoff and L + S >= loff + size and A + S >= aoff + size:
                contained = True
                break
        if not contained:
            out.append(m)
    out.sort()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('latest')
    ap.add_argument('alpha')
    ap.add_argument('--out', default='data')
    ap.add_argument('--latest-start', type=lambda x:int(x,0), default=0x100)
    ap.add_argument('--latest-end', type=lambda x:int(x,0), default=0x18000)
    ap.add_argument('--alpha-start', type=lambda x:int(x,0), default=0x100)
    ap.add_argument('--alpha-end', type=lambda x:int(x,0), default=0x18000)
    ap.add_argument('--window', type=int, default=32)
    ap.add_argument('--min-size', type=int, default=48)
    args = ap.parse_args()

    latest = Path(args.latest).read_bytes(); alpha = Path(args.alpha).read_bytes()
    lsha, asha = sha256(latest), sha256(alpha)
    if lsha != LATEST_SHA256:
        raise SystemExit(f'Latest ROM hash mismatch: {lsha}')
    if asha != ALPHA_SHA256:
        raise SystemExit(f'Alpha ROM hash mismatch: {asha}')

    matches = build_matches(latest, alpha, args.latest_start, args.latest_end,
                            args.alpha_start, args.alpha_end, args.window, args.min_size)
    outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)
    with (outdir/'crossbuild_matches.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['latest_address','alpha_address','size_bytes','latest_minus_alpha','sha1'])
        for loff,aoff,size in matches:
            w.writerow([f'0x{ROM_BASE+loff:08X}', f'0x{ROM_BASE+aoff:08X}', size,
                        f'{loff-aoff:+#x}', hashlib.sha1(latest[loff:loff+size]).hexdigest()])

    by_delta = defaultdict(lambda: {'blocks':0,'bytes':0,'max_block':0})
    for loff,aoff,size in matches:
        d=loff-aoff; s=by_delta[d]; s['blocks']+=1; s['bytes']+=size; s['max_block']=max(s['max_block'],size)
    clusters = [dict(delta=f'{d:+#x}', **stats) for d,stats in sorted(by_delta.items(), key=lambda kv:(-kv[1]['bytes'],kv[0]))]
    summary = {
        'latest_sha256': lsha, 'alpha_sha256': asha,
        'latest_search_range': [hex(args.latest_start), hex(args.latest_end)],
        'alpha_search_range': [hex(args.alpha_start), hex(args.alpha_end)],
        'window_bytes': args.window, 'minimum_block_bytes': args.min_size,
        'match_blocks': len(matches), 'matched_bytes_sum_nonexclusive': sum(x[2] for x in matches),
        'largest_block_bytes': max((x[2] for x in matches), default=0),
        'delta_clusters': clusters,
        'note': 'Exact-byte fingerprints only; relocated branch/literal instructions can split otherwise homologous functions.'
    }
    (outdir/'crossbuild_summary.json').write_text(json.dumps(summary,indent=2)+'\n', encoding='utf-8')
    with (outdir/'crossbuild_anchors.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['latest_address','alpha_address','working_name','confidence','evidence'])
        for latest_addr, alpha_addr, name, confidence, evidence in SEMANTIC_ANCHORS:
            w.writerow([f'0x{latest_addr:08X}', f'0x{alpha_addr:08X}', name, confidence, evidence])
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
