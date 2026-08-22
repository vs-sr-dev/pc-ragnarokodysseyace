"""
arc.py - reader for `ARC` containers, the second level of nesting.

Inside the CPKs nearly everything is a `.pac`, and a `.pac` is an `ARC`: 1,544
containers holding models, animations, AI scripts and textures. Without this
tool the asset tree stops one floor higher up.

    0x00  'ARC' NUL
    0x04  u16   version, 0x0100 across the whole disc
    0x06  u16   number of directory entries
    0x08  u16   number of data blocks
    0x0C  u32   zero
    0x10  0x20 zero bytes
    0x30  u32 x blocks   offset of each block, from the start of the file
    align32              the directory, one entry after another

Directory entry:

    +0x00  char[4]  type tag: 'bin', 'tex', 'nom', 'scn', 'pac', ...
    +0x04  u16      resource id, what the game asks for
    +0x06  u16      data block: index into the offset table
    +0x08  u16      flags
    +0x0A  u8       name length, NUL included
    +0x0B  u8       zero
    +0x0C  u32      zero
    +0x10  char[]   name

Two things cannot be read off the file and have to be known.

**The stride of an entry is not fixed.** It is `align32(16 + name length)`, so
a 15-character name produces a 32-byte entry instead of a 64-byte one.
Assuming 64 slides the index at the first short name - which happens in
`job.cpk::as/animcmd.pac`, where exactly one entry out of 97 is short.

**The two header counts are not the same number**, even though they agree in
1,536 files out of 1,544. In `monster.cpk::pac/*.pac` they do not: several
entries point at the same block under different `rid`s - in `b01.pac` seven
entries are the one animation `b01519at11.CNOM` exposed under seven resource
ids. Assuming they agree computes the directory start from the wrong count and
reads the first name 32 bytes too late.

A block size is not declared: it is the difference between two consecutive
offsets, and for the last one the end of the file. `arc.py check` is exactly
that test, which is why it is worth deriving the size instead of trusting a
field.

A block is not the data itself: it carries 0x20 bytes in front - the payload
size as a big-endian u32, then twenty-eight zeros. `read()` returns the
payload, `raw()` the whole block.

Usage:
  python arc.py list <file>              list entries
  python arc.py check <dir>              verify every ARC inside the CPKs
  python arc.py unpack <file> <dir>      extract
  python arc.py magic <dir>              census of the leaf formats
"""
from __future__ import annotations

import pathlib
import struct
import sys
from collections import Counter

MAGIC = b'ARC' + bytes(1)


class Item:
    __slots__ = ('name', 'tag', 'rid', 'block', 'flags', 'offset', 'size')

    def __init__(self, name, tag, rid, block, flags, offset, size):
        self.name = name
        self.tag = tag
        self.rid = rid
        self.block = block
        self.flags = flags
        self.offset = offset
        self.size = size


class Arc:
    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != MAGIC:
            raise ValueError(f'{label}: not an ARC ({buf[:4]!r})')
        self.buf = buf
        self.label = label
        ver, n, blocks = struct.unpack_from('>HHH', buf, 4)
        if ver != 0x0100:
            raise ValueError(f'{label}: unexpected ARC version {ver:#06x}')
        self.count = n
        self.blocks = blocks
        self.offsets = (struct.unpack_from(f'>{blocks}I', buf, 0x30)
                        if blocks else ())

        self.items: list[Item] = []
        o = -(-(0x30 + blocks * 4) // 32) * 32          # align32
        self.dir_start = o
        for i in range(n):
            tag = buf[o:o + 4].rstrip(bytes(1)).decode('ascii', 'replace')
            rid, block, flags = struct.unpack_from('>HHH', buf, o + 4)
            nlen = buf[o + 10]
            if block >= blocks:
                raise ValueError(f'{label}: entry {i} asks for block {block} '
                                 f'of {blocks}')
            name = buf[o + 16:o + 16 + nlen - 1].decode('ascii', 'replace')
            start = self.offsets[block]
            end = self.offsets[block + 1] if block + 1 < blocks else len(buf)
            self.items.append(Item(name, tag, rid, block, flags,
                                   start, end - start))
            o += -(-(16 + nlen) // 32) * 32             # align32(16 + nlen)
        self.dir_end = o

    def raw(self, it: Item) -> bytes:
        return self.buf[it.offset:it.offset + it.size]

    def read(self, it: Item) -> bytes:
        """The real contents of an entry. Every block carries 0x20 bytes of
        header - the payload size as a u32, then twenty-eight zeros - followed
        by the payload and padding up to the next multiple of 32. Across all
        13,798 blocks on the disc `align32(0x20 + size)` equals the block
        length, so the field can be trusted."""
        b = self.raw(it)
        if len(b) < 0x20:
            return b
        n = struct.unpack_from('>I', b, 0)[0]
        if -(-(0x20 + n) // 32) * 32 != len(b):
            raise ValueError(f'{self.label}/{it.name}: block declares {n} '
                             f'bytes but occupies {len(b)}')
        return b[0x20:0x20 + n]

    def covers(self) -> bool:
        """The directory ends before the first block, the offsets ascend, and
        the last one lies inside the file. If the format were read wrong, one
        of the three would not hold."""
        if not self.offsets:
            return self.dir_end == len(self.buf)
        return (self.dir_end <= self.offsets[0]
                and self.offsets[-1] < len(self.buf)
                and list(self.offsets) == sorted(self.offsets))


# --------------------------------------------------------------------------

def _cpk_arcs(root: pathlib.Path):
    """Every `ARC` entry inside every `.cpk` of a directory, decompressed."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from cpk import Cpk                                       # noqa: PLC0415
    for p in sorted(root.glob('*.cpk')):
        c = Cpk(p)
        for e in c.entries:
            blob = c.read(e)
            if blob[:4] == MAGIC:
                yield f'{p.name}::{e.path}', blob


def cmd_list(path) -> int:
    a = Arc(pathlib.Path(path).read_bytes(), str(path))
    for it in a.items:
        print(f'{it.size:>10,}  {it.tag:<4} rid={it.rid:<6} blk={it.block:<4} '
              f'fl={it.flags:#06x}  {it.name}')
    print(f'{a.count} entries over {a.blocks} blocks; directory '
          f'{a.dir_start:#x}..{a.dir_end:#x}; '
          f'coverage {"ok" if a.covers() else "NO"}')
    return 0


def cmd_check(root) -> int:
    ok = bad = items = alias = 0
    errs: list[str] = []
    for label, blob in _cpk_arcs(pathlib.Path(root)):
        try:
            a = Arc(blob, label)
            if not a.covers():
                raise ValueError('offsets do not cover the file')
            ok += 1
            items += a.count
            alias += a.count - len({i.block for i in a.items})
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 12:
                errs.append(f'  {label}: {exc}')
    for e in errs:
        print(e)
    print(f'{ok} ARC consistent, {bad} failed, {items:,} inner entries '
          f'({alias} aliases onto already-seen blocks)')
    return 0 if not bad else 1


def cmd_magic(root) -> int:
    tags = Counter()
    magics = Counter()
    sample: dict[str, str] = {}
    for label, blob in _cpk_arcs(pathlib.Path(root)):
        a = Arc(blob, label)
        for it in a.items:
            tags[it.tag] += 1
            d = a.read(it)
            m = ''.join(chr(c) if 32 <= c < 127 else '.' for c in d[:8])
            magics[m] += 1
            sample.setdefault(m, f'{label}/{it.name}')
    print('-- type tags --')
    for t, n in tags.most_common():
        print(f'  {t:<6} {n:>7,}')
    print('-- payload magics --')
    for m, n in magics.most_common(30):
        print(f'  {m!r:<12} {n:>7,}   e.g. {sample[m]}')
    return 0


def cmd_unpack(path, out) -> int:
    a = Arc(pathlib.Path(path).read_bytes(), str(path))
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for it in a.items:
        (out / it.name).write_bytes(a.read(it))
    print(f'{a.count} entries -> {out}')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'list':
        return cmd_list(rest[0])
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'magic':
        return cmd_magic(rest[0])
    if cmd == 'unpack':
        return cmd_unpack(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
