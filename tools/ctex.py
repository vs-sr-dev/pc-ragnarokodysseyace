"""
ctex.py - reader for `CTEX`, the texture format.

11,536 files on the disc, the largest single population, and the wall that
stood in front of any rendered frame. A 16-byte outer header, then a payload
that opens with an 80-byte descriptor and continues with pixels:

    0x00  'CTEX'
    0x04  u32   payload size            size + 16 == file length, on all 11,536
    0x08  u32   0x00010005              constant
    0x0C  u32   zero
    --- payload begins; every offset below is a file offset ---
    0x10  u16   0x1000                  constant
    0x12  u16   width                   power of two, 16..2048
    0x14  u16   height                  power of two, 16..2048
    0x16  u16   pixel format
    0x18  u8    alpha present           0 on every DXT1, 1 on every DXT5
    0x19  u8    mip levels minus one
    0x1A  u16   zero
    0x1C  u8    1                       constant
    0x1D  u8    flags: bit 2 set iff the file carries a mip chain
    0x1E  u16   zero
    0x20  u32   0x50                    where level 0 begins, past the payload
    0x24  u32   palette offset, or zero, on the same origin
    0x28  u16   0x60, 0x64, 0x70 or 0x80
    0x2A  u16   zero
    0x2C  u16   palette entries: 256, 16, or zero
    0x2E  u16   zero
    0x30  char[32]  the source texture's name, NUL padded
    0x50  the pixels

**Width comes before height.** The reconnaissance in session 3 had the two the
other way round, which costs nothing arithmetically - every size formula here
is symmetric in the two - and produces an image sliced into interleaved bands
the moment anything is drawn. The `misc.cpk/logo_lang.pac/ui_logo_xseed`
publisher logo is what settled it: 1024x512 renders the logo, 512x1024 renders
a comb.

The formats, and the arithmetic that identifies them:

    0x109  DXT1, 8 bytes per 4x4 block             9,848 files
    0x10F  DXT5, 16 bytes per 4x4 block              452
    0x100  A8R8G8B8, 4 bytes per texel, swizzled     400
    0x107  8-bit indices, 256-entry palette          832
    0x108  4-bit indices, 16-entry palette             4

**The mip chain is what the format hinged on, and byte `0x19` declares it.**
Levels halve in both axes and are stored back to back with no padding and no
alignment; block formats stop when a level would go under 4x4, linear ones run
to 1x1. Summing that chain and adding `4 * palette entries` reproduces the
payload exactly on **11,530 of 11,536** files.

The six exceptions are `stage.cpk/100_01_01/.../big_temple_*`: each carries one
level more than its header declares, always eight bytes, always a 2x2 DXT1 tail
below the 4x4 the chain should have stopped at. `check` reports them rather
than hiding them; a reader should trust the declared count, since a renderer
reading `0x19` would never sample the extra level either.

**Palettised files put the palette after the indices, not before**, and `0x24`
points at it: `palette offset - 0x50` equals the size of the index chain on
every one of them. Entries are four bytes, A R G B, and 4-bit indices are read
high nibble first. The palette is what makes `0x107` legible - read as a
16-bit format, which is what its bytes-per-texel suggests, the size closes for
six files out of 832 and by coincidence.

**A8R8G8B8 is swizzled and nothing else is.** The 400 uncompressed surfaces
store texel (x, y) at the Morton interleave of x and y - x in the even bit
positions - with the surplus bits of the longer axis stacked above the
interleaved part. This is not announced anywhere in the header; it follows from
the format alone. Scoring every non-DXT file for horizontal roughness both ways
separates them cleanly: 369 of 400 A8R8G8B8 read smoother swizzled and **none**
reads smoother linear, while 833 of 836 palettised files read smoother linear.
The remainder are flat colour and say nothing either way; the one palettised
file on the wrong side is a 64x32 gauge of horizontal bars, where the metric
has nothing to measure and the eye settles it.

The two fields still unexplained are `0x28` and bit 0 of `0x1D`. `0x28` takes
four values and correlates with, without determining, `0x1D`; the pair looks
like a stamp left by successive versions of the exporter rather than anything
the renderer reads. Neither affects the size arithmetic, which closes without
them, and neither predicts the swizzle, which the format does.

Usage:
  python ctex.py check <dir>              size arithmetic over every CTEX
  python ctex.py survey <dir>             every texture, largest first
  python ctex.py info <dir> <name>        one file's header and mip chain
  python ctex.py png <dir> <name> <out> [level]   decode one to PNG
  python ctex.py unpack <dir> <out> [glob]        decode many, mirroring paths
  python ctex.py find <dir> <glob>        locate a texture at any depth
"""
from __future__ import annotations

import fnmatch
import pathlib
import struct
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

MAGIC = b'CTEX'
HEADER = 0x10              # the outer header
DESC = 0x50                # the descriptor, measured from the payload start

DXT1, DXT5, ARGB8, PAL8, PAL4 = 0x109, 0x10F, 0x100, 0x107, 0x108

BLOCK = {DXT1: 8, DXT5: 16}                 # bytes per 4x4 block
BITS = {ARGB8: 32, PAL8: 8, PAL4: 4}        # bits per texel
NAMES = {DXT1: 'DXT1', DXT5: 'DXT5', ARGB8: 'A8R8G8B8',
         PAL8: 'P8', PAL4: 'P4'}


def level_bytes(w: int, h: int, fmt: int) -> int:
    if fmt in BLOCK:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BLOCK[fmt]
    return w * h * BITS[fmt] // 8


_MORTON: dict[tuple[int, int], list[int]] = {}


def morton_order(w: int, h: int) -> list[int]:
    """Where texel (x, y) of a swizzled surface actually lives: the bits of x
    and y interleaved, x in the even positions, and the surplus bits of the
    longer axis stacked above the interleaved part."""
    key = (w, h)
    if key in _MORTON:
        return _MORTON[key]
    lw, lh = w.bit_length() - 1, h.bit_length() - 1
    n = min(lw, lh)
    idx = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            o = 0
            for i in range(n):
                o |= ((x >> i) & 1) << (2 * i)
                o |= ((y >> i) & 1) << (2 * i + 1)
            if lw > n:
                o |= (x >> n) << (2 * n)
            elif lh > n:
                o |= (y >> n) << (2 * n)
            idx[y * w + x] = o
    _MORTON[key] = idx
    return idx


class Ctex:
    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != MAGIC:
            raise ValueError(f'{label}: not a CTEX ({buf[:4]!r})')
        self.label = label
        self.buf = buf
        payload, self.version, spare = struct.unpack_from('>III', buf, 4)
        if payload + HEADER != len(buf):
            raise ValueError(f'{label}: declares {payload + HEADER} bytes, '
                             f'file is {len(buf)}')
        if spare:
            raise ValueError(f'{label}: word at 0x0C is {spare:#x}, not zero')
        (self.tag, self.width, self.height,
         self.format) = struct.unpack_from('>HHHH', buf, 0x10)
        self.alpha = buf[0x18]
        self.levels = buf[0x19] + 1
        self.flags = buf[0x1D]
        (self.data_off, self.pal_off) = struct.unpack_from('>II', buf, 0x20)
        self.stamp = struct.unpack_from('>H', buf, 0x28)[0]
        self.pal_entries = struct.unpack_from('>H', buf, 0x2C)[0]
        self.name = buf[0x30:0x50].split(bytes(1))[0].decode('ascii', 'replace')
        if self.format not in NAMES:
            raise ValueError(f'{label}: unknown format {self.format:#x}')
        if self.data_off != DESC:
            raise ValueError(f'{label}: level 0 at {self.data_off:#x}, '
                             f'not {DESC:#x}')

    # -- the mip chain

    def chain(self) -> list[tuple[int, int, int, int]]:
        """(level, width, height, file offset) for every declared level."""
        out = []
        off = HEADER + DESC
        for i in range(self.levels):
            w, h = max(1, self.width >> i), max(1, self.height >> i)
            out.append((i, w, h, off))
            off += level_bytes(w, h, self.format)
        return out

    @property
    def pixel_bytes(self) -> int:
        return sum(level_bytes(w, h, self.format) for _, w, h, _ in self.chain())

    @property
    def declared(self) -> int:
        """What the header says the payload holds, past the descriptor."""
        return self.pixel_bytes + 4 * self.pal_entries

    @property
    def actual(self) -> int:
        return len(self.buf) - HEADER - DESC

    def palette(self) -> list[tuple[int, int, int, int]]:
        if not self.pal_entries:
            return []
        o = HEADER + self.pal_off
        return [tuple(self.buf[o + 4 * i:o + 4 * i + 4])
                for i in range(self.pal_entries)]

    # -- decoding

    def rgba(self, level: int = 0) -> tuple[int, int, bytes]:
        """One level as (width, height, RGBA8888)."""
        _, w, h, off = self.chain()[level]
        n = level_bytes(w, h, self.format)
        src = self.buf[off:off + n]
        if self.format == DXT1:
            return w, h, _dxt(src, w, h, alpha=False)
        if self.format == DXT5:
            return w, h, _dxt(src, w, h, alpha=True)
        if self.format == ARGB8:
            out = bytearray(w * h * 4)
            order = morton_order(w, h)
            for i in range(w * h):
                s = 4 * order[i]
                a, r, g, b = src[s:s + 4]
                out[4 * i:4 * i + 4] = bytes((r, g, b, a))
            return w, h, bytes(out)
        pal = self.palette()
        out = bytearray(w * h * 4)
        for i in range(w * h):
            if self.format == PAL8:
                k = src[i]
            else:
                byte = src[i >> 1]
                k = (byte >> 4) if not (i & 1) else (byte & 0xF)
            a, r, g, b = pal[k]
            out[4 * i:4 * i + 4] = bytes((r, g, b, a))
        return w, h, bytes(out)


# --------------------------------------------------------------------------
# DXT. The blocks are little-endian, as they are in DDS: the RSX consumes the
# same bytes a PC does, and the exporter did not swap them.

def _c565(v: int) -> tuple[int, int, int]:
    r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def _dxt(src: bytes, w: int, h: int, alpha: bool) -> bytes:
    out = bytearray(w * h * 4)
    stride = 16 if alpha else 8
    bw = max(1, (w + 3) // 4)
    for bi in range(len(src) // stride):
        blk = src[bi * stride:(bi + 1) * stride]
        bx, by = (bi % bw) * 4, (bi // bw) * 4
        if alpha:
            a0, a1 = blk[0], blk[1]
            abits = int.from_bytes(blk[2:8], 'little')
            if a0 > a1:
                atab = [a0, a1] + [((7 - i) * a0 + i * a1) // 7
                                   for i in range(1, 7)]
            else:
                atab = ([a0, a1] + [((5 - i) * a0 + i * a1) // 5
                                    for i in range(1, 5)] + [0, 255])
            blk = blk[8:]
        c0, c1 = struct.unpack_from('<HH', blk, 0)
        bits = struct.unpack_from('<I', blk, 4)[0]
        r0, g0, b0 = _c565(c0)
        r1, g1, b1 = _c565(c1)
        if c0 > c1 or alpha:
            tab = [(r0, g0, b0), (r1, g1, b1),
                   ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3),
                   ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3)]
            trans = 4
        else:
            tab = [(r0, g0, b0), (r1, g1, b1),
                   ((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2),
                   (0, 0, 0)]
            trans = 3
        for py in range(4):
            y = by + py
            if y >= h:
                break
            for px in range(4):
                x = bx + px
                if x >= w:
                    continue
                k = (bits >> (2 * (4 * py + px))) & 3
                r, g, b = tab[k]
                if alpha:
                    ak = (abits >> (3 * (4 * py + px))) & 7
                    a = atab[ak]
                else:
                    a = 0 if k == trans else 255
                o = 4 * (y * w + x)
                out[o:o + 4] = bytes((r, g, b, a))
    return bytes(out)


# --------------------------------------------------------------------------

def write_png(path, w: int, h: int, rgba: bytes) -> None:
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[4 * y * w:4 * (y + 1) * w]

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack('>I', len(body)) + tag + body
                + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF))

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(bytes(raw), 9))
           + chunk(b'IEND', b''))
    pathlib.Path(path).write_bytes(png)


# --------------------------------------------------------------------------

def collect(root, want: str = ''):
    """Every CTEX leaf under a directory. The directory may hold the `.cpk`
    containers themselves, or the tree `assets.py unpack` writes."""
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


def _one(root, name) -> tuple[str, Ctex]:
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Ctex(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    ok = bad = short = 0
    fmts: dict[int, int] = {}
    mips: dict[int, int] = {}
    stamps: dict[int, int] = {}
    flags: dict[int, int] = {}
    errs: list[str] = []
    odd: list[str] = []
    for path, blob in collect(root):
        try:
            t = Ctex(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 10:
                errs.append(f'  {exc}')
            continue
        fmts[t.format] = fmts.get(t.format, 0) + 1
        mips[t.levels] = mips.get(t.levels, 0) + 1
        stamps[t.stamp] = stamps.get(t.stamp, 0) + 1
        flags[t.flags] = flags.get(t.flags, 0) + 1
        if t.declared == t.actual:
            ok += 1
        else:
            short += 1
            if len(odd) < 10:
                odd.append(f'  {path}: {t.width}x{t.height} {NAMES[t.format]} '
                           f'{t.levels} levels, header {t.declared} bytes, '
                           f'file {t.actual} ({t.actual - t.declared:+d})')
    total = ok + short + bad
    print(f'{total} CTEX')
    print(f'  {ok} close exactly, {short} do not, {bad} unreadable')
    print('  formats: ' + ', '.join(
        f'{NAMES[f]} {n}' for f, n in sorted(fmts.items(), key=lambda kv: -kv[1])))
    print('  levels:  ' + ', '.join(
        f'{k}:{v}' for k, v in sorted(mips.items())))
    print('  0x1D:    ' + ', '.join(
        f'{k}:{v}' for k, v in sorted(flags.items())))
    print('  0x28:    ' + ', '.join(
        f'{k:#x}:{v}' for k, v in sorted(stamps.items())))
    for line in odd:
        print(line)
    for line in errs:
        print(line)
    return 1 if bad else 0


def cmd_survey(root) -> int:
    out = []
    for path, blob in collect(root):
        try:
            t = Ctex(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        out.append((len(blob), path, t))
    out.sort(key=lambda r: -r[0])
    print(f'{len(out)} CTEX, largest first')
    for size, path, t in out[:40]:
        print(f'  {size:>9,}  {t.width:>4}x{t.height:<4} {NAMES[t.format]:<9} '
              f'{t.levels} lv  {path}')
    return 0


def cmd_info(root, name) -> int:
    path, t = _one(root, name)
    print(path)
    print(f'  name        {t.name}')
    print(f'  size        {t.width} x {t.height}')
    print(f'  format      {t.format:#x}  {NAMES[t.format]}')
    print(f'  alpha       {t.alpha}')
    print(f'  levels      {t.levels}')
    print(f'  flags 0x1D  {t.flags:#04x}')
    print(f'  stamp 0x28  {t.stamp:#x}')
    if t.pal_entries:
        print(f'  palette     {t.pal_entries} entries at {t.pal_off:#x}')
    print(f'  payload     {t.actual} bytes, header accounts for {t.declared}'
          + ('' if t.actual == t.declared else '  <-- mismatch'))
    for i, w, h, off in t.chain():
        print(f'    level {i}  {w:>4}x{h:<4}  {level_bytes(w, h, t.format):>9,} '
              f'bytes at {off:#x}')
    return 0


def cmd_png(root, name, out, level=0) -> int:
    path, t = _one(root, name)
    w, h, rgba = t.rgba(int(level))
    write_png(out, w, h, rgba)
    print(f'{path}  level {level}  {w}x{h}  {NAMES[t.format]}  ->  {out}')
    return 0


def cmd_unpack(root, out, pattern='*') -> int:
    """Every matching texture as a PNG, level 0, under the same relative path
    the container tree uses. Slow: this is a pure-Python DXT decoder."""
    out = pathlib.Path(out)
    done = failed = 0
    for path, blob in collect(root):
        if not (fnmatch.fnmatch(path, pattern)
                or fnmatch.fnmatch(path.rsplit('/', 1)[-1], pattern)):
            continue
        try:
            t = Ctex(blob, path)
            w, h, rgba = t.rgba(0)
        except Exception as exc:                              # noqa: BLE001
            failed += 1
            print(f'  {path}: {exc}')
            continue
        dst = out / (path + '.png')
        dst.parent.mkdir(parents=True, exist_ok=True)
        write_png(dst, w, h, rgba)
        done += 1
        if done % 100 == 0:
            print(f'  {done}...')
    print(f'{done} written to {out}, {failed} failed')
    return 1 if failed else 0


def cmd_find(root, pattern) -> int:
    n = 0
    for path, blob in collect(root):
        if fnmatch.fnmatch(path.rsplit('/', 1)[-1], pattern) \
                or fnmatch.fnmatch(path, pattern):
            try:
                t = Ctex(blob, path)
            except Exception:                                 # noqa: BLE001
                continue
            n += 1
            print(f'  {t.width:>4}x{t.height:<4} {NAMES[t.format]:<9} '
                  f'{t.levels} lv  {path}')
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
    if cmd == 'png':
        return cmd_png(rest[0], rest[1], rest[2],
                       rest[3] if len(rest) > 3 else 0)
    if cmd == 'unpack':
        return cmd_unpack(rest[0], rest[1],
                          rest[2] if len(rest) > 2 else '*')
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
