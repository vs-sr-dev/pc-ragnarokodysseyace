"""
cpk.py - reader for CRI CPK containers, the layer below the disc extractor.

The UDF inventory of this disc stops at 109 files. Twenty of them are `.cpk`
and they hold the entire game, so without this tool `extract/` is not a tree of
assets but a stack of archives. The CPK reader is really part of step 1a.

A CPK is a sequence of *packets* shaped like

    magic(4) | flags u32 LE | size u64 LE | @UTF table

with four possible magics: `CPK ` (the header, always at 0), `TOC ` (index by
name), `ITOC` (index by id, used when there are no names) and `ETOC`
(modification times). The header declares where the others live.

@UTF is CRI's tabular format, **big-endian** even on little-endian consoles,
with one descriptor per column:

    flags u8 -> high nibble = where the value lives (0x10 absent and reads as
                zero, 0x30 constant declared once, 0x50 one per row)
                low nibble = the type (u8..s64, float, double, string, blob)

A constant column stores its value right after the column name, outside the
rows. That is why `row_length` alone is not enough to read a row: the columns
have to be walked in order.

Files inside the container may be compressed with CRILAYLA, an LZ variant with
a **backwards** bit reader - both input and output are traversed from the end
towards the beginning, and the first 0x100 bytes of the original travel
uncompressed at the tail of the block. See `crilayla()`.

Usage:
  python cpk.py list <file.cpk> [glob]      list entries
  python cpk.py info <file.cpk>             header fields
  python cpk.py tree <file.cpk>             directories, with totals
  python cpk.py unpack <file.cpk> <dir>     extract (optional glob as 4th arg)
  python cpk.py magic <file.cpk> [n]        leading bytes per entry, grouped
  python cpk.py survey <dir>                magics and directories of every cpk
"""
from __future__ import annotations

import fnmatch
import pathlib
import struct
import sys
from collections import Counter, defaultdict

# --------------------------------------------------------------------------
# @UTF

# low nibble of the column flags -> (struct format, byte width)
TYPES = {
    0x00: ('>B', 1), 0x01: ('>b', 1),
    0x02: ('>H', 2), 0x03: ('>h', 2),
    0x04: ('>I', 4), 0x05: ('>i', 4),
    0x06: ('>Q', 8), 0x07: ('>q', 8),
    0x08: ('>f', 4), 0x09: ('>d', 8),
    0x0A: ('>I', 4),          # string: offset into the name table
    0x0B: ('>II', 8),         # blob: offset + length into the data area
}

STORAGE_ZERO = 0x10
STORAGE_CONST = 0x30
STORAGE_ROW = 0x50


class Utf:
    """One @UTF table read whole. `rows` is a list of dictionaries."""

    def __init__(self, buf: bytes):
        if buf[:4] != b'@UTF':
            raise ValueError(f'not an @UTF table: {buf[:4]!r}')
        size = struct.unpack_from('>I', buf, 4)[0]
        body = buf[8:8 + size]
        (rows_off, str_off, data_off, name_off,
         n_cols, row_len, n_rows) = struct.unpack_from('>IIIIHHI', body, 0)
        strings = body[str_off:data_off]
        data = body[data_off:]

        def s(off: int) -> str:
            end = strings.index(bytes(1), off)
            # PS3 CPKs mix ASCII and Shift-JIS in names; 'replace' keeps a
            # single Japanese name from taking down the whole index
            return strings[off:end].decode('utf-8', 'replace')

        self.name = s(name_off)
        cols = []
        o = 24
        for _ in range(n_cols):
            flags = body[o]
            cname = s(struct.unpack_from('>I', body, o + 1)[0])
            o += 5
            const = None
            if flags & 0xF0 == STORAGE_CONST:
                const, o = self._value(body, o, flags & 0x0F, strings, data)
            cols.append((cname, flags, const))
        self.columns = [c[0] for c in cols]

        self.rows = []
        for r in range(n_rows):
            o = rows_off + r * row_len
            row = {}
            for cname, flags, const in cols:
                storage = flags & 0xF0
                if storage == STORAGE_ZERO:
                    row[cname] = 0
                elif storage == STORAGE_CONST:
                    row[cname] = const
                else:
                    row[cname], o = self._value(body, o, flags & 0x0F,
                                                strings, data)
            self.rows.append(row)

    @staticmethod
    def _value(body, o, kind, strings, data):
        fmt, n = TYPES[kind]
        if kind == 0x0A:
            off = struct.unpack_from(fmt, body, o)[0]
            end = strings.index(bytes(1), off)
            return strings[off:end].decode('utf-8', 'replace'), o + n
        if kind == 0x0B:
            off, ln = struct.unpack_from(fmt, body, o)
            return data[off:off + ln], o + n
        return struct.unpack_from(fmt, body, o)[0], o + n


# --------------------------------------------------------------------------
# CRILAYLA

VLE_LEVELS = (2, 3, 5, 8)


def crilayla(src: bytes) -> bytes:
    """CRI's LZ. The input is read from its last byte backwards and the output
    is written from its last byte backwards; the first 0x100 bytes of the
    original travel uncompressed at the tail of the compressed block."""
    if src[:8] != b'CRILAYLA':
        raise ValueError('not a CRILAYLA block')
    usize, csize = struct.unpack_from('<II', src, 8)
    out = bytearray(0x100 + usize)
    out[:0x100] = src[0x10 + csize:0x10 + csize + 0x100]

    pos = 0x10 + csize - 1        # read walking down from here
    pool = 0
    left = 0
    done = 0
    end = 0x100 + usize - 1

    def bits(count: int) -> int:
        nonlocal pos, pool, left
        val = 0
        got = 0
        while got < count:
            if left == 0:
                pool = src[pos]
                left = 8
                pos -= 1
            take = min(left, count - got)
            val = (val << take) | ((pool >> (left - take)) & ((1 << take) - 1))
            left -= take
            got += take
        return val

    while done < usize:
        if bits(1):
            ref = end - done + bits(13) + 3
            length = 3
            for lv in VLE_LEVELS:
                this = bits(lv)
                length += this
                if this != (1 << lv) - 1:
                    break
            else:
                while True:
                    this = bits(8)
                    length += this
                    if this != 0xFF:
                        break
            for _ in range(length):
                out[end - done] = out[ref]
                ref -= 1
                done += 1
        else:
            out[end - done] = bits(8)
            done += 1
    return bytes(out)


# --------------------------------------------------------------------------
# the container

class Entry:
    __slots__ = ('path', 'offset', 'size', 'extract_size', 'id', 'user')

    def __init__(self, path, offset, size, extract_size, ident, user):
        self.path = path
        self.offset = offset
        self.size = size
        self.extract_size = extract_size
        self.id = ident
        self.user = user

    @property
    def packed(self) -> bool:
        return self.extract_size > self.size


class Cpk:
    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self.f = open(self.path, 'rb')
        self.head = self._packet(0, b'CPK ').rows[0]
        self.entries = self._read_toc()

    # -- packets

    def _packet(self, off: int, magic: bytes) -> Utf:
        self.f.seek(off)
        head = self.f.read(16)
        if head[:4] != magic:
            raise ValueError(f'{self.path.name}: expected {magic!r} at '
                             f'{off:#x}, found {head[:4]!r}')
        size = struct.unpack_from('<Q', head, 8)[0]
        return Utf(self.f.read(size))

    def _read_toc(self) -> list[Entry]:
        h = self.head
        toc_off = h.get('TocOffset', 0)
        content = h.get('ContentOffset', 0)
        if not toc_off:
            return self._read_itoc()
        # an entry offset is relative to the lower of the two: in CPKs without
        # a separate content area TocOffset is the only base available
        base = min(toc_off, content) if content else toc_off
        out = []
        for r in self._packet(toc_off, b'TOC ').rows:
            d = r.get('DirName', '')
            n = r.get('FileName', '')
            out.append(Entry(f'{d}/{n}' if d else n,
                             base + r['FileOffset'], r['FileSize'],
                             r.get('ExtractSize', r['FileSize']),
                             r.get('ID', -1), r.get('UserString', '')))
        return out

    def _read_itoc(self) -> list[Entry]:
        """CPK without names: entries live in two nested tables, one for files
        with a short size (u16) and one for long ones (u32). Positions are
        recovered by stacking them in id order using the alignment the header
        declares."""
        h = self.head
        itoc = self._packet(h['ItocOffset'], b'ITOC').rows[0]
        align = h.get('Align', 1) or 1
        sizes: dict[int, tuple[int, int]] = {}
        for key in ('DataL', 'DataH'):
            blob = itoc.get(key)
            if not blob:
                continue
            for r in Utf(blob).rows:
                sizes[r['ID']] = (r['FileSize'],
                                  r.get('ExtractSize', r['FileSize']))
        pos = h['ContentOffset']
        out = []
        for ident in sorted(sizes):
            size, ext = sizes[ident]
            out.append(Entry(f'{ident:08d}.bin', pos, size, ext, ident, ''))
            pos += size
            if size % align:
                pos += align - (size % align)
        return out

    # -- contents

    def read(self, e: Entry) -> bytes:
        self.f.seek(e.offset)
        blob = self.f.read(e.size)
        if blob[:8] == b'CRILAYLA':
            blob = crilayla(blob)
        return blob

    def head_bytes(self, e: Entry, n: int) -> bytes:
        """The leading *decompressed* bytes without unrolling the whole file:
        in a CRILAYLA block the first 0x100 bytes of the original sit
        uncompressed at the tail, so a magic costs nothing."""
        self.f.seek(e.offset)
        blob = self.f.read(min(e.size, 0x1000))
        if blob[:8] == b'CRILAYLA':
            csize = struct.unpack_from('<I', blob, 12)[0]
            self.f.seek(e.offset + 0x10 + csize)
            return self.f.read(min(n, 0x100))
        return blob[:n]


# --------------------------------------------------------------------------
# commands

def human(n: float) -> str:
    for unit in ('B', 'kB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{int(n)} B'
        n /= 1024
    return ''


def ascii_magic(b: bytes, n: int = 8) -> str:
    return ''.join(chr(c) if 32 <= c < 127 else '.' for c in b[:n])


def cmd_info(path) -> int:
    c = Cpk(path)
    for k, v in c.head.items():
        if isinstance(v, bytes):
            v = f'<{len(v)} bytes>'
        if v in (0, '', None):
            continue
        print(f'  {k:<22} {v}')
    print(f'  {"(entries read)":<22} {len(c.entries)}')
    return 0


def cmd_list(path, glob: str = '') -> int:
    c = Cpk(path)
    tot = 0
    for e in c.entries:
        if glob and not fnmatch.fnmatch(e.path, glob):
            continue
        flag = 'Z' if e.packed else ' '
        print(f'{e.extract_size:>10,} {flag} {e.path}')
        tot += e.extract_size
    print(f'{tot:>10,}   TOTAL')
    return 0


def cmd_tree(path) -> int:
    c = Cpk(path)
    per = defaultdict(lambda: [0, 0])
    for e in c.entries:
        d = e.path.rsplit('/', 1)[0] if '/' in e.path else '.'
        per[d][0] += 1
        per[d][1] += e.extract_size
    print(f'{"dir":<44} {"n":>6} {"bytes":>12}')
    for d in sorted(per):
        n, b = per[d]
        print(f'{d:<44} {n:>6} {human(b):>12}')
    return 0


def cmd_magic(path, take: int = 40) -> int:
    """Group entries by magic: it answers, in one screen, how many distinct
    formats a container holds - which is the session-1 question."""
    c = Cpk(path)
    groups = Counter()
    sample: dict[str, str] = {}
    for e in c.entries:
        m = ascii_magic(c.head_bytes(e, 8))
        groups[m] += 1
        sample.setdefault(m, e.path)
    for m, n in groups.most_common(take):
        print(f'  {m!r:<14} {n:>6}   e.g. {sample[m]}')
    return 0


def cmd_unpack(path, out, glob: str = '') -> int:
    c = Cpk(path)
    out = pathlib.Path(out)
    n = 0
    tot = 0
    for e in c.entries:
        if glob and not fnmatch.fnmatch(e.path, glob):
            continue
        dst = out / e.path
        dst.parent.mkdir(parents=True, exist_ok=True)
        blob = c.read(e)
        dst.write_bytes(blob)
        n += 1
        tot += len(blob)
    print(f'{n} entries, {human(tot)} -> {out}')
    return 0


def cmd_survey(root) -> int:
    """The opening overview: for every container, how many entries, which
    extensions and which magics. This is the census the recon starts from."""
    files = sorted(pathlib.Path(root).glob('*.cpk'))
    if not files:
        return print(f'no .cpk under {root}') or 1
    for p in files:
        try:
            c = Cpk(p)
        except Exception as exc:                        # noqa: BLE001
            print(f'{p.name:<20} ERROR {exc}')
            continue
        exts = Counter(('.' + e.path.rsplit('.', 1)[-1]) if '.' in
                       e.path.rsplit('/', 1)[-1] else '(none)'
                       for e in c.entries)
        packed = sum(1 for e in c.entries if e.packed)
        size = sum(e.extract_size for e in c.entries)
        top = ' '.join(f'{k}:{v}' for k, v in exts.most_common(6))
        print(f'{p.name:<20} {len(c.entries):>6} entries  {human(size):>9}  '
              f'{packed:>5} packed   {top}')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'info':
        return cmd_info(rest[0])
    if cmd == 'list':
        return cmd_list(rest[0], rest[1] if len(rest) > 1 else '')
    if cmd == 'tree':
        return cmd_tree(rest[0])
    if cmd == 'magic':
        return cmd_magic(rest[0], int(rest[1]) if len(rest) > 1 else 40)
    if cmd == 'unpack':
        return cmd_unpack(rest[0], rest[1], rest[2] if len(rest) > 2 else '')
    if cmd == 'survey':
        return cmd_survey(rest[0])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
