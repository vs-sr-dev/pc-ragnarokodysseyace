"""
assets.py - one addressable path per leaf, across every layer of nesting.

The disc buries its content four containers deep, and each layer has its own
reader. This module puts them behind one iterator, so that everything above it
can say "give me this file" without knowing which archive it fell out of.

    ISO (UDF)               tools/iso.py, already unpacked into extract/
      *.cpk                 tools/cpk.py, may contain further *.cpk
        *.pac  = ARC        tools/arc.py, may contain further ARCs
          cmp/lzma|zlib     unwrapped here, may contain anything above
            leaf            ECH, CTEX, CMDL, CNOM, psq, json, rmsg, ...

A path looks like

    item.cpk/it_db.pac/it_db_wpatk.pac/wpatk_00.bin

with `/` between layers exactly as it is between directories, because from the
consumer's side the distinction does not matter.

The `cmp` wrapper names its own codec, and there are two of them on the disc -
see `uncmp()`. Neither is announced by a file extension: a `.pac` may be an ARC,
a compressed ARC, or neither, so containers are recognised by magic only.

Usage:
  python assets.py tree <dir>            every leaf, with its size
  python assets.py census <dir>          leaves grouped by magic and extension
  python assets.py find <dir> <glob>     leaves whose path matches
  python assets.py cat <dir> <path>      hex dump of one leaf
  python assets.py unpack <dir> <out>    write the whole tree to disk
"""
from __future__ import annotations

import fnmatch
import lzma
import pathlib
import struct
import sys
import zlib
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from arc import MAGIC as ARC_MAGIC, Arc                       # noqa: E402
from cpk import Cpk                                           # noqa: E402

CMP_MAGIC = b'cmp' + bytes(1)
CPK_MAGIC = b'CPK '

MAX_DEPTH = 8


def uncmp(blob: bytes) -> bytes:
    """Unwrap a `cmp` block. Two codecs appear on the disc, named in the magic
    itself: `cmp NUL lzma` and `cmp NUL zlib`.

        +0x00  'cmp' NUL, then the codec name
        +0x08  u32 BE   compressed size, the rest of the block
        +0x0C  u32 BE   uncompressed size
        +0x10           the stream

    The zlib stream is ordinary. The LZMA one is LZMA1 carrying its five
    property bytes but not the size field the 'alone' container expects, so
    the declared size is spliced back in."""
    codec = blob[4:8]
    _, usize = struct.unpack_from('>II', blob, 8)
    if codec == b'zlib':
        out = zlib.decompress(blob[0x10:])
    elif codec == b'lzma':
        alone = blob[0x10:0x15] + struct.pack('<Q', usize) + blob[0x15:]
        out = lzma.decompress(alone, format=lzma.FORMAT_ALONE)
    else:
        raise ValueError(f'unknown cmp codec {codec!r}')
    if len(out) != usize:
        raise ValueError(f'{codec.decode()}: declared {usize} bytes, '
                         f'produced {len(out)}')
    return out


def walk(blob: bytes, path: str, depth: int = 0):
    """Yield `(path, bytes)` for every leaf reachable from a blob.

    A container is recognised by its magic, never by its extension: on this
    disc a `.pac` may be an ARC, a compressed ARC, or neither, and a `.bin`
    may be either a table or a compressed one."""
    if depth > MAX_DEPTH:
        raise RecursionError(f'{path}: nesting deeper than {MAX_DEPTH}')

    if blob[:4] == CMP_MAGIC:
        yield from walk(uncmp(blob), path, depth + 1)
        return

    if blob[:4] == ARC_MAGIC:
        arc = Arc(blob, path)
        for it in arc.items:
            yield from walk(arc.read(it), f'{path}/{it.name}', depth + 1)
        return

    yield path, blob


def leaves(root: pathlib.Path, want: str = ''):
    """Every leaf under a directory of `.cpk` files. Nested CPKs are opened
    from a temporary file because the CPK reader seeks, and CRILAYLA gives us
    the inner container as bytes."""
    import tempfile                                            # noqa: PLC0415

    def from_cpk(cpk: Cpk, prefix: str):
        for e in cpk.entries:
            blob = cpk.read(e)
            path = f'{prefix}/{e.path}'
            if blob[:4] == CPK_MAGIC:
                with tempfile.NamedTemporaryFile(suffix='.cpk',
                                                 delete=False) as fh:
                    fh.write(blob)
                    tmp = fh.name
                try:
                    yield from from_cpk(Cpk(tmp), path)
                finally:
                    pathlib.Path(tmp).unlink(missing_ok=True)
                continue
            yield from walk(blob, path)

    for p in sorted(pathlib.Path(root).glob('*.cpk')):
        if want and not fnmatch.fnmatch(p.name, want):
            continue
        yield from from_cpk(Cpk(p), p.name)


# --------------------------------------------------------------------------

def magic_of(blob: bytes, n: int = 8) -> str:
    return ''.join(chr(c) if 32 <= c < 127 else '.' for c in blob[:n])


def ext_of(path: str) -> str:
    base = path.rsplit('/', 1)[-1]
    return '.' + base.rsplit('.', 1)[-1] if '.' in base else '(none)'


def human(n: float) -> str:
    for unit in ('B', 'kB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{int(n)} B'
        n /= 1024
    return ''


def cmd_tree(root) -> int:
    n = tot = 0
    for path, blob in leaves(root):
        print(f'{len(blob):>10,}  {path}')
        n += 1
        tot += len(blob)
    print(f'{n:,} leaves, {human(tot)}')
    return 0


def cmd_census(root) -> int:
    by_magic = Counter()
    by_ext = Counter()
    size = Counter()
    sample: dict[str, str] = {}
    depth = Counter()
    n = tot = 0
    for path, blob in leaves(root):
        m = magic_of(blob)
        by_magic[m] += 1
        size[m] += len(blob)
        sample.setdefault(m, path)
        by_ext[ext_of(path)] += 1
        depth[path.count('/')] += 1
        n += 1
        tot += len(blob)
    print(f'{n:,} leaves, {human(tot)}')
    print()
    print(f'{"magic":<14} {"n":>6} {"bytes":>10}   example')
    for m, c in by_magic.most_common(40):
        print(f'{m!r:<14} {c:>6} {human(size[m]):>10}   {sample[m]}')
    print()
    print('-- by extension --')
    for e, c in by_ext.most_common(24):
        print(f'  {e:<12} {c:>6}')
    print()
    print('-- by nesting depth --')
    for d in sorted(depth):
        print(f'  {d} levels  {depth[d]:>6}')
    return 0


def cmd_find(root, glob: str) -> int:
    n = 0
    for path, blob in leaves(root):
        if fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(
                path.rsplit('/', 1)[-1], glob):
            print(f'{len(blob):>10,}  {magic_of(blob)!r:<12}  {path}')
            n += 1
    print(f'{n} matches')
    return 0


def cmd_cat(root, want: str, take: int = 256) -> int:
    for path, blob in leaves(root):
        if path != want and path.rsplit('/', 1)[-1] != want:
            continue
        print(f'{path}  ({len(blob):,} B)')
        for off in range(0, min(take, len(blob)), 16):
            row = blob[off:off + 16]
            asc = ''.join(chr(c) if 32 <= c < 127 else '.' for c in row)
            print(f'  {off:06x}  {row.hex(" "):<47}  {asc}')
        return 0
    print(f'not found: {want}')
    return 1


def cmd_unpack(root, out) -> int:
    """Write the tree to disk. A filesystem cannot hold two files at one path,
    and the disc has leaves that share one: an ARC may expose the same block
    under several names, and `b01.pac` names the same animation seven times.
    Those collisions are counted and reported rather than passed over, because
    a directory that is quietly 127 files short of the iterator is a bad thing
    to build later work on."""
    out = pathlib.Path(out)
    n = tot = clash = 0
    seen: set[str] = set()
    for path, blob in leaves(root):
        n += 1
        tot += len(blob)
        if path in seen:
            clash += 1
            continue
        seen.add(path)
        dst = out / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(blob)
    print(f'{n:,} leaves, {human(tot)} -> {out}')
    if clash:
        print(f'  {clash} share a path with an earlier leaf and were not '
              f'written; {len(seen):,} files on disk')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'tree':
        return cmd_tree(rest[0])
    if cmd == 'census':
        return cmd_census(rest[0])
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    if cmd == 'cat':
        return cmd_cat(rest[0], rest[1],
                       int(rest[2]) if len(rest) > 2 else 256)
    if cmd == 'unpack':
        return cmd_unpack(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
