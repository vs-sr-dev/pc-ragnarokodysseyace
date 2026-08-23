"""
pam.py - reader for `PAMF`, the movie container.

46 files, 3.4 GB, `PS3_GAME/USRDIR/movie/`. **46 read, 22.7 minutes of video,
0 unreadable.**

There is nothing to reverse here beyond an offset. A `.pam` is a 2 KB-aligned
Sony header followed by an ordinary **MPEG-2 program stream**, and the header
says how long it is:

    0x00  'PAMF' '0041'
    0x08  u32   header length, in 0x800 sectors     1 or 2 on this disc
    0x0C  u32   packs that follow, of 2048 bytes
    ...
    0x58  u32   first presentation time, 90 kHz     90000 on all 46
    0x5E  u32   last presentation time, 90 kHz
    ...   the stream descriptors, then padding to the sector boundary

`file length == 0x800 * header length + 2048 * packs` on **all 46**, which is
what says the two counts are the two counts.

Past that offset ffmpeg does the work, and it needs to be told twice: the
extension collides with Netpbm's PAM image format, so the demuxer has to be
named, and the header has to be skipped.

    ffprobe -f mpeg -skip_initial_bytes 2048 movie/boss_b01_00.pam

Every one of the 46 is the same: **MPEG-2 video, 1280x720, 29.97 fps, BT.709,
4:2:0 progressive**, one elementary stream at `0xE0`, up to 40 Mbit/s.

**There is no audio.** Scanning all 1,778,690 PES packets on the disc finds
`0xE0` video, `0xBB` system headers, `0xBF` private stream 2 and `0xBE`
padding, and no audio stream id at all - no `0xC0..0xDF`, no `0xBD`. The
cutscene soundtrack is not in the movie: it is played by the game beside it,
out of `sound.cpk`.

Usage:
  python pam.py check <dir>              the header identity, every file
  python pam.py list <dir>               one line per movie
  python pam.py mpg <dir> <name> <out>   write the program stream out
"""

import collections
import pathlib
import struct
import sys

MAGIC = b'PAMF'
SECTOR = 0x800
PACK = 2048
CLOCK = 90000.0


class Pam:
    """The header of one `.pam`. The payload is left on disk."""

    def __init__(self, head: bytes, size: int, path: str = ''):
        if head[:4] != MAGIC:
            raise ValueError(f'{path}: not a PAMF: {head[:4]!r}')
        self.path = path
        self.size = size
        self.version = head[4:8].decode('ascii', 'replace')
        self.sectors, self.packs = struct.unpack_from('>II', head, 8)
        self.start, = struct.unpack_from('>I', head, 0x58)
        self.end, = struct.unpack_from('>I', head, 0x5E)

    @property
    def offset(self) -> int:
        return SECTOR * self.sectors

    @property
    def closes(self) -> bool:
        return self.size == self.offset + PACK * self.packs

    @property
    def seconds(self) -> float:
        return (self.end - self.start) / CLOCK


def collect(root):
    for p in sorted(pathlib.Path(root).rglob('*.pam')):
        yield p


def _open(path: pathlib.Path) -> Pam:
    with path.open('rb') as fh:
        head = fh.read(0x100)
    return Pam(head, path.stat().st_size, path.name)


def streams(path: pathlib.Path, pam: Pam, cap: int = 0) -> collections.Counter:
    """Every PES stream id in the program stream, by packet count."""
    ids: collections.Counter = collections.Counter()
    with path.open('rb') as fh:
        fh.seek(pam.offset)
        buf = fh.read()
    i = n = 0
    while i < len(buf) - 6 and (not cap or n < cap):
        if buf[i:i + 4] == b'\x00\x00\x01\xba':          # pack header
            i += 14 + (buf[i + 13] & 7)
            continue
        if buf[i:i + 3] != b'\x00\x00\x01':
            break
        ids[buf[i + 3]] += 1
        n += 1
        i += 6 + int.from_bytes(buf[i + 4:i + 6], 'big')
    return ids


def cmd_check(root) -> int:
    files = ok = 0
    secs = 0.0
    ids: collections.Counter = collections.Counter()
    for path in collect(root):
        files += 1
        pam = _open(path)
        ok += pam.closes
        secs += pam.seconds
        ids.update(streams(path, pam))
        if not pam.closes:
            print(f'  {path.name}: {pam.size} != {pam.offset} + '
                  f'{PACK} * {pam.packs}')
    if not files:
        print(f'no .pam under {root} - '
              f'run `python tools/iso.py extract movie` first')
        return 1
    print(f'{files} files, {secs / 60:.1f} minutes')
    print(f'length == 0x800 * header + 2048 * packs on {ok} of {files}')
    print('PES stream ids: ' +
          ', '.join(f'0x{k:02x} x{v}' for k, v in ids.most_common()))
    audio = [k for k in ids if 0xC0 <= k <= 0xDF or k == 0xBD]
    print(f'audio streams: {audio if audio else "none, on any file"}')
    return 0 if ok == files else 1


def cmd_list(root) -> int:
    print(f'{"file":<26} {"bytes":>11} {"hdr":>4} {"packs":>8} {"seconds":>8}')
    for path in collect(root):
        pam = _open(path)
        print(f'{path.name:<26} {pam.size:>11} {pam.offset:>4} '
              f'{pam.packs:>8} {pam.seconds:>8.2f}'
              + ('' if pam.closes else '   <- length does not close'))
    return 0


def cmd_mpg(root, name, out) -> int:
    for path in collect(root):
        if name in (path.name, path.stem):
            pam = _open(path)
            with path.open('rb') as fh, open(out, 'wb') as w:
                fh.seek(pam.offset)
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    w.write(chunk)
            print(f'{out}: {pam.size - pam.offset} bytes of MPEG-2 program '
                  f'stream, {pam.seconds:.2f} s')
            return 0
    print(f'not found: {name}')
    return 1


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'list':
        return cmd_list(rest[0])
    if cmd == 'mpg':
        return cmd_mpg(rest[0], rest[1], rest[2])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
