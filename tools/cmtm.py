"""
cmtm.py - reader for `CMTM`, the material animation format.

91 files, **231 tracks, 254 channels, 1,388 keys, 0 unreadable.** `CMTM` sits
beside `CNOM` under `*.mot.pac/` and in the same `.pac` as the model it belongs
to, and it is what makes a texture scroll, a surface pulse and a menu icon
flash.

**It is `CNOM` with scalars instead of bones.** Byte for byte the same shell and
the same header - magic, payload size, `0x00010005`, zero; frame count at
`0x10`, name at `0x18`, the track table at `0x30` and the name table at `0x34`,
the constant `1000.0` at `0x4C` - and the same track, channel and key layout
described in [`cnom.py`](cnom.py), so this reader is that reader with one
magic word changed. All 91 files read, the rate is `1000.0` on all 91, and the
name table has one entry per track on all 91.

Three things differ, and all three follow from what it animates:

- **a track names a material, not a bone.** 227 of the 231 track names are
  material names of a `CMDL` sitting beside the file; the four that are not are
  the model's own name. `CNOM` binds to `S5`, the node names; this binds to
  `S6`;
- **a track has one to three channels, not always three.** 208 of the 231 have
  a single one, 17 have two, 4 have three and 2 have none. There is no fixed
  triple to fill because there is no translation, rotation and scale to fill it
  with;
- **every key is four bytes**, all 1,388 of them - one value per key, where
  `CNOM` keys 12 and 16.

Two files key past their own declared length, `menu.cpk/animeicon_00` and
`animeicon_20`, both ending at frame 60 against a header saying 31 and 51.
`CNOM` has no such case in 3,043 files. `check` reports them.

## The five channel kinds

    kind  keys   what
    0x40    64   packed RGBA bytes
    0x41    64   packed RGBA bytes
    0x42  1084   float
    0x43    28   float
    0x44   148   float

`0x40` and `0x41` are not floats. Read as floats their values are around
-4e37, which is the tell; read as four bytes they are `80808000`, `05050b00`,
`00000000` - the same packed RGBA the `CMDL` material table writes at `+0x08`,
where `808080ff` and `000000ff` are the common pair. So two of the five
channels animate the material's colours, and they always carry the same values
as each other on this disc.

The three float kinds run in small ranges - `0x42` over 0 to 1 with 0, 1, 0.3
and 0.5 the commonest values, `0x43` over -1 to 0.75, `0x44` over -0.5 to 2.
Which is alpha and which are texture coordinates is not settled here.

The channel's `+0x04` byte is `0x06` or `0x07` rather than `CNOM`'s `0x0f` and
`0x10`, so whatever that byte encodes, it is not simply the key size - both
kinds of file key four-byte and this one only keys four-byte.

Usage:
  python cmtm.py check <dir>              the whole arithmetic, every file
  python cmtm.py survey <dir>             every file, most keys first
  python cmtm.py info <dir> <name>        header and per-track channels
  python cmtm.py track <dir> <name> <material>
  python cmtm.py find <dir> <glob>        locate one at any depth
"""
from __future__ import annotations

import collections
import fnmatch
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402
from cnom import Cnom                                         # noqa: E402

MAGIC = b'CMTM'
COLOUR = (0x40, 0x41)


class Cmtm(Cnom):
    MAGIC = MAGIC

    def value(self, ch, key: int):
        """One key, as a float or as packed RGBA where the kind says so."""
        o = self.at(ch.values) + key * ch.size
        if ch.kind in COLOUR:
            return tuple(self.buf[o:o + 4])
        return struct.unpack_from('>f', self.buf, o)[0]


# --------------------------------------------------------------------------

def collect(root, want: str = ''):
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*')):
            if not p.is_file():
                continue
            with p.open('rb') as fh:
                if fh.read(4) != MAGIC:
                    continue
            yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    for path, blob in leaves(root, want):
        if blob[:4] == MAGIC:
            yield path, blob


def _one(root, name) -> tuple[str, Cmtm]:
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Cmtm(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    files = bad = tracks = channels = keys = 0
    tally: dict[str, int] = {}
    errs: list[str] = []

    def note(k: str, ok: bool, detail: str = '') -> None:
        tally[k] = tally.get(k, 0) + (1 if ok else 0)
        tally[k + ' /n'] = tally.get(k + ' /n', 0) + 1
        if not ok and len(errs) < 12:
            errs.append(f'  {detail}')

    kinds: collections.Counter = collections.Counter()
    for path, blob in collect(root):
        try:
            a = Cmtm(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 12:
                errs.append(f'  {exc}')
            continue
        files += 1
        names = a.names()
        note('one name per track', len(names) == a.tracks,
             f'{path}: {a.tracks} tracks, {len(names)} names')
        note('the rate word is 1000.0', abs(a.rate - 1000.0) < 1e-6,
             f'{path}: rate {a.rate}')
        vspans, tspans, last = [], [], 0
        for t in range(a.tracks):
            tracks += 1
            chs = a.channels(t)
            note('one to three channels per track', 1 <= len(chs) <= 3,
                 f'{path}: track {t} has {len(chs)} channels')
            for c in chs:
                channels += 1
                keys += c.keys
                kinds[c.kind] += c.keys
                note('every key is four bytes', c.size == 4,
                     f'{path}: track {t} keys of {c.size}')
                note('the kind is one of the five', 0x40 <= c.kind <= 0x44,
                     f'{path}: track {t} kind {c.kind:#04x}')
                if not (c.keys and c.size):
                    continue
                ts = struct.unpack_from(f'>{c.keys}H', blob, a.at(c.times))
                note('key times ascending',
                     all(x < y for x, y in zip(ts, ts[1:])),
                     f'{path}: track {t} times {ts[:6]}')
                last = max(last, ts[-1])
                vspans.append((c.values, (c.keys * c.size + 15) // 16 * 16))
                tspans.append((c.times, (c.keys * 2 + 3) // 4 * 4))
        note('last key inside the declared length', last <= a.frames,
             f'{path}: last key {last}, header says {a.frames}')
        vspans.sort()
        tspans.sort()
        note('value blocks tile, aligned to 16',
             all(o + n == p for (o, n), (p, _) in zip(vspans, vspans[1:])),
             f'{path}: value blocks do not tile')
        note('time blocks tile, aligned to 4',
             all(o + n == p for (o, n), (p, _) in zip(tspans, tspans[1:])),
             f'{path}: time blocks do not tile')

    print(f'{files} CMTM, {tracks} tracks, {channels} channels, {keys:,} keys, '
          f'{bad} unreadable')
    for k in sorted(tally):
        if k.endswith(' /n'):
            continue
        print(f'  {tally[k]:>5,} / {tally[k + " /n"]:<5,}  {k}')
    print('  keys by kind: '
          + ', '.join(f'{k:#04x}: {v}' for k, v in sorted(kinds.items())))
    for line in errs:
        print(line)
    return 1 if bad else 0


def cmd_survey(root) -> int:
    out = []
    for path, blob in collect(root):
        try:
            a = Cmtm(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        keys = sum(c.keys for t in range(a.tracks) for c in a.channels(t))
        out.append((keys, a.frames, a.tracks, path))
    out.sort(key=lambda r: -r[0])
    print(f'{len(out)} CMTM, most keys first')
    for keys, frames, tracks, path in out[:40]:
        print(f'  {keys:>5} keys  {frames:>5} frames  {tracks:>3} materials  '
              f'{path}')
    return 0


def cmd_info(root, name) -> int:
    path, a = _one(root, name)
    names = a.names()
    print(path)
    print(f'  name        {a.name}')
    print(f'  length      {a.frames} frames')
    print(f'  materials   {a.tracks}')
    for t in range(a.tracks):
        chs = a.channels(t)
        print('   %-28s %s' % (names[t] if t < len(names) else f'#{t}',
                               ', '.join(f'kind {c.kind:#04x} '
                                         f'{c.keys} keys' for c in chs)))
    return 0


def cmd_track(root, name, material) -> int:
    path, a = _one(root, name)
    names = a.names()
    if material not in names:
        raise SystemExit(f'{path}: no track named {material}; '
                         f'have {", ".join(names[:8])} ...')
    t = names.index(material)
    print(f'{path}  {material}')
    for ch in a.channels(t):
        print(f'  kind {ch.kind:#04x}, {ch.keys} keys')
        ts = struct.unpack_from(f'>{ch.keys}H', a.buf, a.at(ch.times))
        for k in range(ch.keys):
            v = a.value(ch, k)
            print('    %4d  %s' % (ts[k], '%02x %02x %02x %02x' % v
                                   if isinstance(v, tuple) else '%12.6f' % v))
    return 0


def cmd_find(root, pattern) -> int:
    n = 0
    for path, blob in collect(root):
        if fnmatch.fnmatch(path.rsplit('/', 1)[-1], pattern) \
                or fnmatch.fnmatch(path, pattern):
            try:
                a = Cmtm(blob, path)
            except Exception:                                 # noqa: BLE001
                continue
            n += 1
            print(f'  {a.frames:>5} frames {a.tracks:>3} materials  {path}')
    print(f'{n} match')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'survey':
        return cmd_survey(rest[0])
    if cmd == 'info':
        return cmd_info(rest[0], rest[1])
    if cmd == 'track':
        return cmd_track(rest[0], rest[1], rest[2])
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
