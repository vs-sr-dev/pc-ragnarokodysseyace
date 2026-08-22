"""
cnom.py - reader for `CNOM`, the motion format.

3,043 animations: every walk, attack, stagger and idle on the disc. They key on
the skeletons `CMDL` declares, by name, so a `CNOM` and a `CMDL` fit together
with nothing in between.

The container is the shell the rest of this engine uses, and the identity holds
on all 3,043 files:

    file length == 16 + payload + 16 + POF0 payload + 16

    0x00  'CNOM'
    0x04  u32   payload size
    0x08  u32   0x00010005
    0x0C  u32   zero
    0x10  u16   length in frames    u16 1
    0x18  char[24]  the animation's name
    0x30  u32   pointer to the track table
    0x34  u32   pointer to the name table
    0x4C  float 1000.0              constant on every file
    ...   the tracks, the keys, the names

Every `C___` format on the disc opens this way: magic, payload size,
`0x00010005`, zero. What follows the payload sorts them in two. `CMDL`, `CMTM`,
`CNOM`, `CSCM` and `CSCN` carry a `POF0` relocation table - the encoding is
described in [`cmdl.py`](cmdl.py), with the same catch where the 22-bit delta
is three bytes and not four. `CTEX` ends at its payload and `CCLS` ends with
sixteen zero bytes, both of them having no pointers to relocate.

Offsets are relative to `0x10` here too.

## Tracks, channels, keys

The track table is `u32 count` then that many pointers. The name table has the
same shape and the same count on every file, one name per track, and they are
the node names out of `CMDL`: `node_hip`, `node_r_thigh`, `node_l_clavicle`,
`top`, `trans`, `xrot`. Of 3,043 animations, 3,019 have every track name
present as a node name somewhere on the disc; the 61 names that are not are
`*_PIVOT` helpers and scene props, which have motion but no geometry.

A track is 16 bytes: `u16 channel count`, then a pointer per channel. **Every
track on the disc has exactly three channels**, 77,331 of them, and the three
are always the same three:

    slot 0   kind 0x00   12 bytes per key   translation
    slot 1   kind 0x04   16 bytes per key   rotation, a quaternion
    slot 2   kind 0x05   12 bytes per key   scale

A channel is 16 bytes:

    +0x00  u16   key count
    +0x02  u8    bytes per key, 12 or 16
    +0x03  u8    zero
    +0x04  u8    0x0f for the twelve-byte channels, 0x10 for the sixteen
    +0x05  u8    kind
    +0x06  u16   zero
    +0x08  u32   pointer to the values
    +0x0C  u32   pointer to the key times

Values are floats, `count * size` bytes, and the blocks tile the file **aligned
to sixteen**. Key times are `u16` frame numbers, `count` of them, ascending,
and those blocks tile **aligned to four**. Both hold on all 3,043 files with
no gap and no overlap, which is what makes the layout a reading rather than a
guess.

**The sixteen-byte channel is a rotation, and the file proves it**: of the
77,331 rotation channels on the disc, every key of every one is a unit
quaternion to within a thousandth. Nothing else four floats wide does that.

Frame numbers run from 0 to the `u16` at `0x10`, and no key on the disc lies
past it.

Usage:
  python cnom.py check <dir>              the whole arithmetic, every file
  python cnom.py survey <dir>             every animation, longest first
  python cnom.py info <dir> <name>        header and per-track key counts
  python cnom.py track <dir> <name> <bone>  one track's keys
  python cnom.py pose <dir> <name> <frame>  every bone sampled at one frame
  python cnom.py find <dir> <glob>        locate an animation at any depth
"""
from __future__ import annotations

import fnmatch
import math
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402
from cmdl import decode_pof0                                  # noqa: E402

MAGIC = b'CNOM'
POF0 = b'POF0'
HEADER = 0x10
NUL = bytes(1)

TRANSLATION, ROTATION, SCALE = 0x00, 0x04, 0x05
KIND = {TRANSLATION: 'translation', ROTATION: 'rotation', SCALE: 'scale'}


class Channel:
    __slots__ = ('keys', 'size', 'type', 'kind', 'values', 'times')

    def __init__(self, buf: bytes, o: int):
        self.keys, self.size, _z = struct.unpack_from('>HBB', buf, o)
        self.type, self.kind = buf[o + 4], buf[o + 5]
        self.values, self.times = struct.unpack_from('>II', buf, o + 8)

    @property
    def floats(self) -> int:
        return self.size // 4


class Cnom:
    MAGIC = MAGIC

    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != self.MAGIC:
            raise ValueError(f'{label}: not a {self.MAGIC.decode()} '
                             f'({buf[:4]!r})')
        self.label = label
        self.buf = buf
        self.size, self.version, spare = struct.unpack_from('>III', buf, 4)
        self.end = HEADER + self.size
        if self.end + 16 > len(buf) or buf[self.end:self.end + 4] != POF0:
            raise ValueError(f'{label}: no POF0 at {self.end:#x}')
        self.pof0_size = struct.unpack_from('>I', buf, self.end + 4)[0]
        if len(buf) != 48 + self.size + self.pof0_size:
            raise ValueError(f'{label}: {len(buf)} bytes, but 48 + {self.size}'
                             f' + {self.pof0_size} is '
                             f'{48 + self.size + self.pof0_size}')
        if spare:
            raise ValueError(f'{label}: word at 0x0C is {spare:#x}, not zero')
        self.frames, self.one = struct.unpack_from('>HH', buf, 0x10)
        self.name = buf[0x18:0x30].split(NUL)[0].decode('ascii', 'replace')
        self.tracks_ptr, self.names_ptr = struct.unpack_from('>II', buf, 0x30)
        self.rate = struct.unpack_from('>f', buf, 0x4C)[0]
        self.tracks = struct.unpack_from('>I', buf, self.at(self.tracks_ptr))[0]

    def at(self, off: int) -> int:
        return HEADER + off

    def relocations(self) -> list[int]:
        o = self.end + 16
        return decode_pof0(self.buf[o:o + self.pof0_size])

    def names(self) -> list[str]:
        o = self.at(self.names_ptr)
        n = struct.unpack_from('>I', self.buf, o)[0]
        out = []
        for k in range(n):
            p = self.at(struct.unpack_from('>I', self.buf, o + 4 + 4 * k)[0])
            e = self.buf.find(NUL, p, self.end)
            if e < 0:
                break
            out.append(self.buf[p:e].decode('ascii', 'replace'))
        return out

    def channels(self, track: int) -> list[Channel]:
        o = self.at(self.tracks_ptr)
        tp = self.at(struct.unpack_from('>I', self.buf, o + 4 + 4 * track)[0])
        n = struct.unpack_from('>H', self.buf, tp)[0]
        return [Channel(self.buf,
                        self.at(struct.unpack_from('>I', self.buf,
                                                   tp + 4 + 4 * c)[0]))
                for c in range(n)]

    def keys(self, ch: Channel) -> list[tuple[int, tuple[float, ...]]]:
        ts = struct.unpack_from(f'>{ch.keys}H', self.buf, self.at(ch.times))
        vo = self.at(ch.values)
        return [(ts[k], struct.unpack_from(f'>{ch.floats}f', self.buf,
                                           vo + k * ch.size))
                for k in range(ch.keys)]

    # -- sampling

    def sample(self, ch: Channel, frame: float) -> tuple[float, ...]:
        """The channel at a frame, interpolated between its two nearest keys.

        Rotations are spherically interpolated, and the shorter arc is taken -
        a quaternion and its negation are the same rotation, so the sign has to
        be chosen rather than trusted.
        """
        ks = self.keys(ch)
        if len(ks) == 1 or frame <= ks[0][0]:
            return ks[0][1]
        if frame >= ks[-1][0]:
            return ks[-1][1]
        i = 0
        while i + 1 < len(ks) and ks[i + 1][0] <= frame:
            i += 1
        (t0, a), (t1, b) = ks[i], ks[i + 1]
        u = (frame - t0) / (t1 - t0) if t1 != t0 else 0.0
        if ch.kind != ROTATION:
            return tuple(x + (y - x) * u for x, y in zip(a, b))
        dot = sum(x * y for x, y in zip(a, b))
        if dot < 0:
            b, dot = tuple(-y for y in b), -dot
        if dot > 0.9995:
            q = tuple(x + (y - x) * u for x, y in zip(a, b))
        else:
            th = math.acos(max(-1.0, min(1.0, dot)))
            s = math.sin(th)
            wa, wb = math.sin((1 - u) * th) / s, math.sin(u * th) / s
            q = tuple(x * wa + y * wb for x, y in zip(a, b))
        n = math.sqrt(sum(v * v for v in q)) or 1.0
        return tuple(v / n for v in q)

    def pose(self, frame: float) -> dict[str, dict]:
        """Every track sampled at one frame, keyed by bone name."""
        out = {}
        for t, name in enumerate(self.names()):
            entry = {}
            for ch in self.channels(t):
                entry[KIND.get(ch.kind, f'kind{ch.kind:#04x}')] = \
                    self.sample(ch, frame)
            out[name] = entry
        return out


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


def _one(root, name) -> tuple[str, Cnom]:
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Cnom(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    files = bad = 0
    tally: dict[str, int] = {}
    errs: list[str] = []

    def note(k: str, ok: bool, detail: str = '') -> None:
        tally[k] = tally.get(k, 0) + (1 if ok else 0)
        tally[k + ' /n'] = tally.get(k + ' /n', 0) + 1
        if not ok and len(errs) < 12:
            errs.append(f'  {detail}')

    for path, blob in collect(root):
        try:
            a = Cnom(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 12:
                errs.append(f'  {exc}')
            continue
        files += 1
        names = a.names()
        note('one name per track', len(names) == a.tracks,
             f'{path}: {a.tracks} tracks, {len(names)} names')
        vspans, tspans, last = [], [], 0
        for t in range(a.tracks):
            chs = a.channels(t)
            note('three channels per track', len(chs) == 3,
                 f'{path}: track {t} has {len(chs)} channels')
            note('the three channels are translation, rotation, scale',
                 [c.kind for c in chs] == [TRANSLATION, ROTATION, SCALE],
                 f'{path}: track {t} kinds {[c.kind for c in chs]}')
            for c in chs:
                note('key count and key size are non-zero',
                     c.keys > 0 and c.size in (12, 16),
                     f'{path}: track {t} {c.keys} keys of {c.size}')
                if not (c.keys and c.size):
                    continue
                ts = struct.unpack_from(f'>{c.keys}H', blob, a.at(c.times))
                note('key times ascending',
                     all(x < y for x, y in zip(ts, ts[1:])),
                     f'{path}: track {t} times {ts[:6]}')
                last = max(last, ts[-1])
                vspans.append((c.values, (c.keys * c.size + 15) // 16 * 16))
                tspans.append((c.times, (c.keys * 2 + 3) // 4 * 4))
                if c.kind == ROTATION:
                    off = max(abs(math.sqrt(sum(v * v for v in q)) - 1.0)
                              for _, q in a.keys(c))
                    note('rotation keys are unit quaternions', off < 1e-3,
                         f'{path}: track {t} quaternion off by {off:.4f}')
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

    print(f'{files} CNOM, {bad} unreadable')
    for k in sorted(tally):
        if k.endswith(' /n'):
            continue
        print(f'  {tally[k]:>8,} / {tally[k + " /n"]:<8,}  {k}')
    for line in errs:
        print(line)
    return 1 if bad else 0


def cmd_survey(root) -> int:
    out = []
    for path, blob in collect(root):
        try:
            a = Cnom(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        keys = sum(c.keys for t in range(a.tracks) for c in a.channels(t))
        out.append((a.frames, a.tracks, keys, a.name, path))
    out.sort(key=lambda r: -r[0])
    print(f'{len(out)} CNOM, longest first')
    for frames, tracks, keys, name, path in out[:40]:
        print(f'  {frames:>5} frames  {tracks:>4} bones  {keys:>7,} keys  '
              f'{path}')
    return 0


def cmd_info(root, name) -> int:
    path, a = _one(root, name)
    names = a.names()
    print(path)
    print(f'  name        {a.name}')
    print(f'  length      {a.frames} frames')
    print(f'  tracks      {a.tracks}')
    print(f'  payload     {a.size:,} bytes, POF0 {a.pof0_size:,}, '
          f'{len(a.relocations()):,} relocations')
    print('   bone                       trans   rot  scale')
    for t in range(a.tracks):
        chs = a.channels(t)
        print('   %-24s %6d %5d %6d'
              % (names[t] if t < len(names) else f'#{t}',
                 *[c.keys for c in chs]))
    return 0


def cmd_track(root, name, bone) -> int:
    path, a = _one(root, name)
    names = a.names()
    if bone not in names:
        raise SystemExit(f'{path}: no track named {bone}; '
                         f'have {", ".join(names[:8])} ...')
    t = names.index(bone)
    print(f'{path}  {bone}')
    for ch in a.channels(t):
        print(f'  {KIND.get(ch.kind, hex(ch.kind))}, {ch.keys} keys')
        for frame, v in a.keys(ch)[:16]:
            print('    %4d  %s' % (frame, ' '.join('%9.5f' % x for x in v)))
        if ch.keys > 16:
            print(f'    ... {ch.keys - 16} more')
    return 0


def cmd_pose(root, name, frame) -> int:
    path, a = _one(root, name)
    frame = float(frame)
    print(f'{path}  frame {frame:g} of {a.frames}')
    print('   bone                     translation                  '
          'rotation')
    for bone, ch in a.pose(frame).items():
        t = ch.get('translation', (0, 0, 0))
        r = ch.get('rotation', (0, 0, 0, 1))
        print('   %-24s %8.3f %8.3f %8.3f    %6.3f %6.3f %6.3f %6.3f'
              % (bone, t[0], t[1], t[2], r[0], r[1], r[2], r[3]))
    return 0


def cmd_find(root, pattern) -> int:
    n = 0
    for path, blob in collect(root):
        if fnmatch.fnmatch(path.rsplit('/', 1)[-1], pattern) \
                or fnmatch.fnmatch(path, pattern):
            try:
                a = Cnom(blob, path)
            except Exception:                                 # noqa: BLE001
                continue
            n += 1
            print(f'  {a.frames:>5} frames {a.tracks:>4} bones  {path}')
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
    if cmd == 'pose':
        return cmd_pose(rest[0], rest[1], rest[2])
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
