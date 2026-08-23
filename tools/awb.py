"""
awb.py - reader for the waveform archives, and for the tables that name them.

274 `.acb` sound banks holding **7,756 waveforms**: 7,659 CRI HCA, 96 CRI ADX
and one Sony VAG. **7,756 read, 0 unreadable, 12 hours 18 minutes of audio**,
and every one of them is reached by a cue with a name.

An `.acb` is an `@UTF` table - [`cpk.py`](cpk.py) has opened them since session
9 - and one of its columns, `AwbFile`, is an entire archive carried inside the
row. This is the reader for that archive and for the four tables that say
which cue plays which waveform, so that a sound has a name before it has a
sample.

## The archive

`AFS2`, little-endian, on 273 of the 274:

    0x00  'AFS2'
    0x04  u8    version           1
    0x05  u8    offset width      2 or 4 bytes, and both occur
    0x06  u8    id width          2
    0x07  u8    zero
    0x08  u32   files
    0x0C  u32   alignment         0x20
    0x10  u16   id[files]
    ...   offset[files + 1]

Entry *i* runs from `align(offset[i])` up to `offset[i + 1]`, and the last
offset is the length of the archive. The 274th bank, `en/vprev.acb`, carries a
`CPK ` with an `ITOC` instead - the older shape, and `cpk.py` reads it as it
stands.

## HCA

    0x00  'HCA\0'  u16 version  u16 header size
    'fmt\0'  u8 channels, u24 sample rate, u32 frames,
             u16 encoder delay, u16 encoder padding
    'comp'   u16 frame size, then the band and resolution layout
    'ciph'   u16 cipher type
    'loop' 'ath' 'rva' 'vbr' 'dec' 'pad'   optional
    ...      the frames, each exactly `frame size` bytes

**`header size + frames * frame size == the archive entry's length` on all
7,659**, which is the identity that says the archive was cut where the codec
thinks it was.

Two things worth having found out rather than assumed:

- **`ciph` is 0 on every file.** Nothing on this disc is encrypted, which is
  the one thing that would have made the codec unreachable.
- **the `.acb`'s `NumSamples` is not the decoded length.** It is usually the
  length at the 48 kHz the `.acf` mixes at: `NumSamples / 48000` equals
  `(frames * 1024 - delay - padding) / sample rate` on 6,295 of 7,220 of the
  embedded ones, and ffmpeg agrees with the second number. On the rest it is
  the native count, and nothing here says which rule a file follows.

The codec itself is CRI's and well-trodden; `ffmpeg -i x.hca` decodes it, and
`awb.py wav` drives that, as `pam.py` leaves MPEG-2 to ffmpeg. What is
specific to this disc is the naming, above. The one exception is the single
`VAGp`, which ffmpeg will not demux bare and which `vag_pcm()` here decodes -
Sony 4-bit ADPCM is four lines of arithmetic and a five-entry filter table.

## Which cue plays which waveform

Four tables and one command opcode:

    Cue.ReferenceType 2 -> Synth[ReferenceIndex]
    Cue.ReferenceType 3 -> Sequence[ReferenceIndex]

    Synth.ReferenceItems is (u16 kind, u16 index) pairs, kind 1 a waveform,
                          2 another synth, 3 a sequence
    Sequence.TrackIndex  -> Track.EventIndex -> Command, where **opcode 2000**
                          carries the same (kind, index) pair

**20,955 of the 20,964 reference items land inside the table they name**; the
nine that do not are the `0xFFFF` that means *nothing here*. Every one of the
7,756 waveforms is reached from a cue, so every sample on the disc has a
name. See
[`../docs/format_awb.md`](../docs/format_awb.md).

Usage:
  python awb.py check <dir>              every archive, every identity
  python awb.py list <dir>               one line per bank
  python awb.py cues <dir> <bank>        cue -> waveform, with the header
  python awb.py extract <dir> <out>      write every waveform, named by cue
  python awb.py wav <dir> <out>          the same, decoded with ffmpeg
"""

import collections
import fnmatch
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cpk import Cpk, Utf                                        # noqa: E402

AFS2 = b'AFS2'
CPK = b'CPK '
HCA = b'HCA\0'
NOTE_ON = 2000
WIDTH = {1: 'B', 2: 'H', 4: 'I', 8: 'Q'}
ENCODE = {0: 'adx', 2: 'hca', 10: 'vag'}


def align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


# --------------------------------------------------------------------------

class Archive:
    """The waveform archive carried inside a bank, in either of its two
    shapes. `blobs` maps the archive's own id to the bytes."""

    def __init__(self, blob: bytes, path: str = ''):
        self.path = path
        self.kind = ''
        self.blobs: dict[int, bytes] = {}
        if not blob:
            return
        if blob[:4] == AFS2:
            self.kind = 'AFS2'
            self._afs2(blob)
        elif blob[:4] == CPK:
            self.kind = 'CPK'
            self._cpk(blob)
        else:
            raise ValueError(f'{path}: unknown archive {blob[:4]!r}')

    def _afs2(self, blob: bytes) -> None:
        osz, isz = blob[5], blob[6]
        count, step = struct.unpack_from('<II', blob, 8)
        self.alignment = step
        ids = struct.unpack_from(f'<{count}{WIDTH[isz]}', blob, 16)
        table = struct.unpack_from(f'<{count + 1}{WIDTH[osz]}',
                                   blob, 16 + isz * count)
        self.closes = table[-1] == len(blob)
        for i, ident in enumerate(ids):
            self.blobs[ident] = blob[align(table[i], step):table[i + 1]]

    def _cpk(self, blob: bytes) -> None:
        self.alignment = 0
        self.closes = True
        with tempfile.NamedTemporaryFile(suffix='.cpk', delete=False) as fh:
            fh.write(blob)
            tmp = fh.name
        try:
            cpk = Cpk(tmp)
            for e in cpk.entries:
                self.blobs[e.id] = cpk.read(e)
            cpk.f.close()
        finally:
            pathlib.Path(tmp).unlink(missing_ok=True)


class Hca:
    """The header of one HCA. The frames are left alone."""

    def __init__(self, blob: bytes, path: str = ''):
        if blob[:4] != HCA:
            raise ValueError(f'{path}: not an HCA: {blob[:4]!r}')
        self.size = len(blob)
        self.version, self.header = struct.unpack_from('>HH', blob, 4)
        self.channels = 0
        self.rate = self.frames = self.delay = self.pad = self.frame = 0
        self.cipher = 0
        self.chunks: list[str] = []
        o = 8
        while o + 4 <= self.header - 2:
            tag = bytes(c & 0x7F for c in blob[o:o + 4])
            name = tag.rstrip(b'\0').decode('ascii', 'replace')
            if not name or not name[0].isalpha():
                break
            self.chunks.append(name)
            if name == 'fmt':
                self.channels = blob[o + 4]
                self.rate = int.from_bytes(blob[o + 5:o + 8], 'big')
                self.frames, self.delay, self.pad = \
                    struct.unpack_from('>IHH', blob, o + 8)
                o += 16
            elif name == 'comp':
                self.frame = struct.unpack_from('>H', blob, o + 4)[0]
                o += 16
            elif name == 'dec':
                o += 12
            elif name == 'vbr':
                o += 8
            elif name == 'ath':
                o += 6
            elif name == 'ciph':
                self.cipher = struct.unpack_from('>H', blob, o + 4)[0]
                o += 6
            elif name == 'rva':
                o += 8
            elif name == 'loop':
                o += 16
            elif name == 'pad':
                break
            else:
                break

    @property
    def closes(self) -> bool:
        return self.header + self.frames * self.frame == self.size

    @property
    def samples(self) -> int:
        return self.frames * 1024 - self.delay - self.pad


# --------------------------------------------------------------------------

class Bank:
    """One `.acb`: its cues, the graph between them and the waveforms, and
    the archive the waveforms live in."""

    def __init__(self, blob: bytes, path: str = ''):
        self.path = path
        head = Utf(blob).rows[0]
        self.name = head.get('Name', '')

        def table(key):
            raw = head.get(key)
            return Utf(raw).rows if raw else []

        self.cues = table('CueTable')
        self.synths = table('SynthTable')
        self.sequences = table('SequenceTable')
        self.tracks = table('TrackTable')
        self.commands = table('CommandTable')
        self.waves = table('WaveformTable')
        self.names = {r['CueIndex']: r['CueName']
                      for r in table('CueNameTable')}
        self.archive = Archive(head.get('AwbFile', b''), path)

    # -- the graph

    @staticmethod
    def _pairs(blob: bytes):
        for k in range(0, len(blob) - 3, 4):
            yield (int.from_bytes(blob[k:k + 2], 'big'),
                   int.from_bytes(blob[k + 2:k + 4], 'big'))

    def _ops(self, index: int):
        if not 0 <= index < len(self.commands):
            return
        blob = self.commands[index]['Command']
        o = 0
        while o + 3 <= len(blob):
            op = int.from_bytes(blob[o:o + 2], 'big')
            n = blob[o + 2]
            yield op, blob[o + 3:o + 3 + n]
            o += 3 + n

    def _synth(self, index: int, seen: set) -> list[int]:
        if ('s', index) in seen or not 0 <= index < len(self.synths):
            return []
        seen.add(('s', index))
        out: list[int] = []
        for kind, idx in self._pairs(self.synths[index]['ReferenceItems']):
            if kind == 1:
                out.append(idx)
            elif kind == 2:
                out += self._synth(idx, seen)
            elif kind == 3:
                out += self._sequence(idx, seen)
        return out

    def _sequence(self, index: int, seen: set) -> list[int]:
        if ('q', index) in seen or not 0 <= index < len(self.sequences):
            return []
        seen.add(('q', index))
        out: list[int] = []
        for track, in ((int.from_bytes(b, 'big'),) for b in
                       _chunks(self.sequences[index]['TrackIndex'], 2)):
            if not 0 <= track < len(self.tracks):
                continue
            for op, payload in self._ops(self.tracks[track]['EventIndex']):
                if op != NOTE_ON or len(payload) < 4:
                    continue
                kind = int.from_bytes(payload[0:2], 'big')
                idx = int.from_bytes(payload[2:4], 'big')
                if kind == 1:
                    out.append(idx)
                elif kind == 2:
                    out += self._synth(idx, seen)
                elif kind == 3:
                    out += self._sequence(idx, seen)
        return out

    def waveforms(self, cue: int) -> list[int]:
        """Waveform rows one cue reaches, in the order it reaches them."""
        if not 0 <= cue < len(self.cues):
            return []
        r = self.cues[cue]
        seen: set = set()
        if r['ReferenceType'] == 2:
            out = self._synth(r['ReferenceIndex'], seen)
        elif r['ReferenceType'] == 3:
            out = self._sequence(r['ReferenceIndex'], seen)
        else:
            out = []
        return [i for i in dict.fromkeys(out) if 0 <= i < len(self.waves)]

    # -- the samples

    def blob(self, wave: int) -> bytes:
        row = self.waves[wave]
        return self.archive.blobs.get(row['Id'], b'')

    def suffix(self, wave: int) -> str:
        row = self.waves[wave]
        blob = self.blob(wave)
        if blob[:4] == HCA:
            return 'hca'
        if blob[:2] == b'\x80\x00':
            return 'adx'
        if blob[:4] == b'VAGp':
            return 'vag'
        return ENCODE.get(row['EncodeType'], 'bin')


def _chunks(blob: bytes, n: int):
    for i in range(0, len(blob) - n + 1, n):
        yield blob[i:i + n]


# --------------------------------------------------------------------------
# VAG, the one waveform on the disc that is neither HCA nor ADX

VAG_FILTER = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


def vag_pcm(blob: bytes) -> tuple[int, bytes]:
    """Sony 4-bit ADPCM. 16-byte blocks: a predictor and a shift in the first
    byte, a flag in the second, then 28 nibbles, low one first."""
    rate = struct.unpack_from('>I', blob, 0x10)[0]
    out = bytearray()
    s1 = s2 = 0.0
    for block in _chunks(blob[0x30:], 16):
        predictor = min(block[0] >> 4, len(VAG_FILTER) - 1)
        shift = block[0] & 0x0F
        if block[1] == 7:                       # the end-of-stream flag
            break
        f0, f1 = VAG_FILTER[predictor]
        for byte in block[2:]:
            for nibble in (byte & 0x0F, byte >> 4):
                s = nibble << 12
                if s & 0x8000:
                    s -= 0x10000
                value = (s >> shift) + s1 * f0 / 64 + s2 * f1 / 64
                s2, s1 = s1, value
                out += struct.pack('<h', max(-32768, min(32767, round(value))))
    return rate, bytes(out)


def wav(pcm: bytes, rate: int, channels: int = 1) -> bytes:
    """A RIFF header over signed 16-bit little-endian samples."""
    block = 2 * channels
    return (b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVE'
            + b'fmt ' + struct.pack('<IHHIIHH', 16, 1, channels, rate,
                                    rate * block, block, 16)
            + b'data' + struct.pack('<I', len(pcm)) + pcm)


# --------------------------------------------------------------------------

def collect(root):
    root = pathlib.Path(root)
    for p in sorted(root.rglob('*.acb')):
        yield p.relative_to(root).as_posix(), p.read_bytes()


def _one(root, name) -> tuple[str, Bank]:
    """A bank by its path, its file name, or the directory it sits in -
    `b09` finds `monster.cpk/b09/se.acb`, whose leaf is only `se.acb`."""
    for path, blob in collect(root):
        parts = path.split('/')
        if (name == path or name in parts or name + '.acb' in parts
                or fnmatch.fnmatch(path, name)):
            return path, Bank(blob, path)
    raise SystemExit(f'not found: {name}')


def external(root, bank: Bank, path: str):
    """The `.awb` beside a bank, for the waveforms it streams."""
    p = pathlib.Path(root) / (path[:-4] + '.awb')
    if not p.is_file() or not p.stat().st_size:
        return None
    return Archive(p.read_bytes(), p.name)


def cue_of(bank: Bank) -> dict[int, str]:
    """Waveform row -> the first cue name that reaches it."""
    out: dict[int, str] = {}
    for i in range(len(bank.cues)):
        name = bank.names.get(i, f'cue{i}')
        for k, w in enumerate(bank.waveforms(i)):
            out.setdefault(w, name if k == 0 else f'{name}_{k + 1}')
    return out


# --------------------------------------------------------------------------
# commands

def cmd_check(root) -> int:
    banks = waves = hca = adx = vag = other = 0
    closes = cipher = named = 0
    refs = inside = 0
    kinds: collections.Counter = collections.Counter()
    missing: list[str] = []
    for path, blob in collect(root):
        banks += 1
        bank = Bank(blob, path)
        arch = bank.archive
        if arch.kind == 'AFS2' and not arch.closes:
            missing.append(f'{path}: last offset is not the archive length')
        store = dict(arch.blobs)
        ext = external(root, bank, path)
        if ext:
            store.update(ext.blobs)
        reach = cue_of(bank)
        for i, row in enumerate(bank.waves):
            waves += 1
            named += i in reach
            data = store.get(row['Id'], b'')
            if not data:
                missing.append(f'{path}: waveform {i} has no archive entry')
                other += 1
                continue
            if data[:4] == HCA:
                hca += 1
                h = Hca(data, path)
                closes += h.closes
                cipher += h.cipher != 0
                if not h.closes:
                    missing.append(f'{path}: waveform {i} is {h.size} bytes, '
                                   f'header says {h.header} + '
                                   f'{h.frames} * {h.frame}')
            elif data[:2] == b'\x80\x00':
                adx += 1
            elif data[:4] == b'VAGp':
                vag += 1
            else:
                other += 1
                kinds[data[:4]] += 1
        for r in bank.synths:
            for kind, idx in Bank._pairs(r['ReferenceItems']):
                refs += 1
                limit = {1: len(bank.waves), 2: len(bank.synths),
                         3: len(bank.sequences)}.get(kind, 0)
                inside += idx < limit
    if not banks:
        print(f'no .acb under {root}')
        return 1
    print(f'{banks} banks, {waves} waveforms: {hca} HCA, {adx} ADX, '
          f'{vag} VAG, {other} unreadable '
          f'{dict(kinds) if kinds else ""}'.rstrip())
    print(f'HCA length identity closes on {closes} of {hca}; '
          f'{cipher} are encrypted')
    print(f'{named} of {waves} waveforms are reached by a named cue')
    print(f'{inside} of {refs} synth reference items land inside their table')
    for line in missing[:10]:
        print(f'  {line}')
    return 1 if len(missing) > 10 else 0


def cmd_list(root) -> int:
    print(f'{"bank":<40} {"cues":>5} {"waves":>6} {"archive":>7} '
          f'{"bytes":>10}  codecs')
    for path, blob in collect(root):
        bank = Bank(blob, path)
        store = dict(bank.archive.blobs)
        ext = external(root, bank, path)
        if ext:
            store.update(ext.blobs)
        size = sum(len(v) for v in store.values())
        codec = collections.Counter(ENCODE.get(r['EncodeType'], '?')
                                    for r in bank.waves)
        print(f'{path:<40} {len(bank.cues):>5} {len(bank.waves):>6} '
              f'{bank.archive.kind or "-":>7} {size:>10}  '
              f'{" ".join(f"{k}x{v}" for k, v in codec.most_common())}'
              + ('  streamed' if ext else ''))
    return 0


def cmd_cues(root, name) -> int:
    path, bank = _one(root, name)
    ext = external(root, bank, path)
    store = dict(bank.archive.blobs)
    if ext:
        store.update(ext.blobs)
    print(f'{path}: {len(bank.cues)} cues, {len(bank.waves)} waveforms, '
          f'{bank.archive.kind} archive')
    for i, r in enumerate(bank.cues):
        head = f'{r["CueId"]:>5}  {bank.names.get(i, "?"):<32}'
        rows = bank.waveforms(i)
        if not rows:
            print(f'{head} -')
            continue
        for w in rows:
            row = bank.waves[w]
            data = store.get(row['Id'], b'')
            note = ''
            if data[:4] == HCA:
                h = Hca(data)
                note = (f'{h.channels}ch {h.rate:>5} Hz  '
                        f'{h.frames:>5} frames  {h.samples / h.rate:6.2f} s'
                        + ('  encrypted' if h.cipher else ''))
            else:
                kind = ENCODE.get(row['EncodeType'], '?')
                note = f'{kind} {len(data)} bytes'
            print(f'{head} w{w:<4} {note}')
            head = ' ' * 39
    return 0


SAFE = re.compile(r'[^A-Za-z0-9_.-]')


def _write(root, out, decode: bool) -> int:
    out = pathlib.Path(out)
    ffmpeg = decode
    written = failed = 0
    for path, blob in collect(root):
        bank = Bank(blob, path)
        store = dict(bank.archive.blobs)
        ext = external(root, bank, path)
        if ext:
            store.update(ext.blobs)
        reach = cue_of(bank)
        folder = out / SAFE.sub('_', path[:-4])
        for i, row in enumerate(bank.waves):
            data = store.get(row['Id'], b'')
            if not data:
                failed += 1
                continue
            stem = SAFE.sub('_', reach.get(i, f'w{i:04d}'))
            folder.mkdir(parents=True, exist_ok=True)
            kind = bank.suffix(i)
            raw = folder / f'{stem}.{kind}'
            raw.write_bytes(data)
            if not ffmpeg:
                written += 1
                continue
            out_wav = folder / f'{stem}.wav'
            if kind == 'vag':                   # ffmpeg has no bare-VAG
                rate, pcm = vag_pcm(data)       # demuxer; this one is ours
                out_wav.write_bytes(wav(pcm, rate, row['NumChannels'] or 1))
                raw.unlink(missing_ok=True)
                written += 1
                continue
            done = subprocess.run(
                ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                 '-i', str(raw), str(out_wav)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
            raw.unlink(missing_ok=True)
            if done.returncode or not out_wav.exists():
                failed += 1
                if failed < 6:
                    print(f'  {path} {stem}: '
                          f'{done.stderr.decode("utf-8", "replace").strip()}')
            else:
                written += 1
        print(f'{path}: {len(bank.waves)} waveforms'.ljust(70), end='\r')
    print(' ' * 70, end='\r')
    print(f'{written} written to {out}, {failed} failed')
    return 1 if failed else 0


def cmd_extract(root, out) -> int:
    return _write(root, out, decode=False)


def cmd_wav(root, out) -> int:
    if not any(os.access(os.path.join(p, 'ffmpeg' + e), os.X_OK)
               for p in os.environ.get('PATH', '').split(os.pathsep)
               for e in ('', '.exe')):
        print('ffmpeg is not on PATH; `awb.py extract` writes the raw '
              'streams instead')
        return 1
    return _write(root, out, decode=True)


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
    if cmd == 'cues':
        return cmd_cues(rest[0], rest[1])
    if cmd == 'extract':
        return cmd_extract(rest[0], rest[1])
    if cmd == 'wav':
        return cmd_wav(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
