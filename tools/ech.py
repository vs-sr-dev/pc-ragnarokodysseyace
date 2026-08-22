"""
ech.py - reader for `ECH` tables, the game's database format.

4,941 of these hold the disc's structured data: items, weapons, skills,
monsters, quests, rewards, stages, the endless dungeon, the encyclopedia,
shop recipes. If the reimplementation is going to be data-driven, this is the
data.

    0x00  'ECH' NUL
    0x04  u32   header size, which is also where row 0 begins
    0x08  u32   zero on every file on the disc
    0x0C  u32   0x92, the format version
    0x10  u32   number of rows
    0x14  u32   row size in bytes
    0x18  byte[row size]   the default row
    ...   the rows
    ...   a string pool, NUL-separated, when the table needs text

`header size` is always exactly `0x18 + row size`, so the header ends with one
full-width row. It is usually all zeros; where it is not, the non-zero fields
are sensible defaults (`it_db_ability.bin` defaults its last word to -150.0).
Reading it as a row is what makes the layout close.

**The rows do not have to reach the end of the file.** 2,730 tables carry a
string pool after them; it opens with a NUL so that offset 0 reads as the empty
string, and the rows reference it **by byte offset**. That makes a text column
recognisable without guessing: a lane whose every value lands just past a NUL
inside the pool is a string, and the chance of a numeric column doing that by
accident collapses after a handful of rows.

**There is no type descriptor.** The format declares how wide a row is and
nothing about what is in it - the consuming code in the EBOOT knows the struct.
Types therefore have to be inferred, which is what `classify()` does, and its
answers are hypotheses that the tool labels rather than facts it asserts.

The one inference that is easy to get wrong: **a 4-byte lane is often not one
field.** Plenty of columns are four `u8`s or two `u16`s packed together, and
read as `u32` they produce impressive nonsense - `chapter.bin` column 0 reads
as 0, 33554431, 65793, 33554431 until you look at the bytes and find
`00 00 00 00`, `01 FF FF FF`, `00 01 01 01`, which is a variant record keyed
on its first byte. So the classifier looks down each byte column as well as
each word column, and prefers the narrower reading when the wide one only
looks busy because the narrow fields underneath it are moving.

Usage:
  python ech.py check <dir>            header arithmetic over every ECH found
  python ech.py info <dir> <name>      header and inferred column profile
  python ech.py dump <dir> <name> [n]  first n rows, typed by the profile
  python ech.py strings <dir> <name>   the string pool of one table
  python ech.py survey <dir>           every table, largest first
  python ech.py grep <dir> <text>      tables whose pool contains a string
"""
from __future__ import annotations

import math
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

MAGIC = b'ECH' + bytes(1)
VERSION = 0x92
FIXED = 0x18
NUL = bytes(1)


class Ech:
    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != MAGIC:
            raise ValueError(f'{label}: not an ECH ({buf[:4]!r})')
        self.label = label
        self.buf = buf
        (self.header_size, self.spare, self.version,
         self.rows, self.row_size) = struct.unpack_from('>IIIII', buf, 4)
        if self.header_size != FIXED + self.row_size:
            raise ValueError(f'{label}: header {self.header_size} is not '
                             f'0x18 + row size {self.row_size}')
        self.data_end = self.header_size + self.rows * self.row_size
        if self.data_end > len(buf):
            raise ValueError(f'{label}: declares {self.data_end} bytes, '
                             f'file is {len(buf)}')
        self.pool = buf[self.data_end:]
        if self.pool and self.pool[0] != 0:
            raise ValueError(f'{label}: string pool does not start with NUL')
        self.lanes = self.row_size // 4

    @property
    def default(self) -> bytes:
        return self.buf[FIXED:FIXED + self.row_size]

    def row(self, i: int) -> bytes:
        o = self.header_size + i * self.row_size
        return self.buf[o:o + self.row_size]

    def lane(self, k: int) -> list[int]:
        """Column k read as one big-endian u32, down every row."""
        o = self.header_size + k * 4
        return [struct.unpack_from('>I', self.buf, o + i * self.row_size)[0]
                for i in range(self.rows)]

    # -- the string pool

    def text(self, off: int) -> str:
        end = self.pool.index(NUL, off)
        return self.pool[off:end].decode('utf-8', 'replace')

    def strings(self) -> list[tuple[int, str]]:
        out = []
        off = 1
        while off < len(self.pool):
            end = self.pool.index(NUL, off)
            if end > off:
                out.append((off, self.pool[off:end].decode('utf-8',
                                                           'replace')))
            off = end + 1
        return out

    def is_pool_offset(self, v: int) -> bool:
        """A value that addresses a string: inside the pool, and either the
        empty string at 0 or the byte right after a NUL."""
        return v < len(self.pool) and (v == 0 or self.pool[v - 1] == 0)

    def profile(self) -> list[dict]:
        out = []
        for k in range(self.lanes):
            vals = self.lane(k)
            distinct = len(set(vals))
            if (self.pool and distinct > 1
                    and all(self.is_pool_offset(v) for v in vals)):
                out.append({'type': 'str', 'n': len(vals), 'distinct': distinct,
                            'note': f'{distinct} offsets into the pool',
                            'sample': sorted({self.text(v) for v in vals})[:3]})
            else:
                out.append(classify(vals))
        return out


# --------------------------------------------------------------------------
# type inference

def as_float(bits: int) -> float:
    return struct.unpack('>f', struct.pack('>I', bits))[0]


def _plausible_float(bits: int) -> bool:
    """A bit pattern a designer would plausibly have typed. Zero counts, and
    so does any magnitude game data actually lives in. Denormals and
    astronomically large values do not."""
    if bits in (0, 0x80000000):
        return True
    v = as_float(bits)
    if not math.isfinite(v):
        return False
    return 1e-4 <= abs(v) <= 1e7


def _byte_columns(vals: list[int]) -> list[set]:
    return [{(v >> s) & 0xFF for v in vals} for s in (24, 16, 8, 0)]


def classify(vals: list[int]) -> dict:
    """What a column of big-endian words can be. Returns a hypothesis with the
    evidence behind it, never a bare verdict. The order of the tests is the
    argument: the cheap certainties first, the byte-level reading before the
    word-level fallback."""
    n = len(vals)
    distinct = len(set(vals))
    out = {'n': n, 'distinct': distinct}

    if not vals or distinct == 1:
        out['type'] = 'const'
        if not vals:
            out['note'] = 'empty'
        elif _plausible_float(vals[0]) and vals[0] > 0xFFFF:
            # a constant wide enough to be a float usually is one:
            # 0x42700000 in the fever table is 60.0, the duration in seconds
            out['note'] = (f'always {vals[0]:#x}, which reads as '
                           f'{as_float(vals[0]):g} as a float')
        else:
            out['note'] = f'always {vals[0]:#x}'
        return out

    if all(v < 0x10000 for v in vals):
        out['type'] = 'u32'
        out['note'] = f'0..{max(vals)}'
        return out

    sentinel = sum(1 for v in vals if v in (0xFFFFFFFF, 0x7FFFFFFF))
    floaty = sum(1 for v in vals if _plausible_float(v))
    if floaty == n:
        fs = [as_float(v) for v in vals]
        fractional = sum(1 for f in fs if f != int(f))
        if fractional:
            out['type'] = 'f32'
            out['note'] = (f'{min(fs):g}..{max(fs):g}, {fractional} of {n} '
                           f'not whole')
            return out

    if sentinel >= max(2, n // 20):
        signed = [v - (1 << 32) if v >> 31 else v for v in vals]
        out['type'] = 'i32'
        out['note'] = (f'{sentinel} sentinels (-1 / INT_MAX), otherwise '
                       f'{min(signed)}..{max(v for v in signed if v > -1 << 30)}')
        return out

    cols = _byte_columns(vals)
    widest = max(len(c) for c in cols)
    if widest * 2 <= distinct and widest <= 24:
        out['type'] = 'u8 x4'
        out['note'] = ('distinct per byte: '
                       + '/'.join(str(len(c)) for c in cols))
        return out

    halves_hi = {v >> 16 for v in vals}
    halves_lo = {v & 0xFFFF for v in vals}
    if max(len(halves_hi), len(halves_lo)) * 2 <= distinct:
        out['type'] = 'u16 x2'
        out['note'] = f'distinct per half: {len(halves_hi)}/{len(halves_lo)}'
        return out

    if floaty == n:
        out['type'] = 'f32?'
        out['note'] = 'plausible as floats, but every value is whole'
        return out

    out['type'] = 'u32'
    out['note'] = f'{min(vals):#x}..{max(vals):#x}'
    return out


def cell(word: int, kind: str, table=None) -> str:
    if kind == 'str' and table is not None:
        s = table.text(word)
        return repr(s) if s else "''"
    if kind in ('f32', 'f32?'):
        return f'{as_float(word):g}'
    if kind == 'i32':
        return str(word - (1 << 32) if word >> 31 else word)
    if kind == 'u16 x2':
        return f'{word >> 16}:{word & 0xFFFF}'
    if kind == 'u8 x4':
        return '.'.join(str((word >> s) & 0xFF) for s in (24, 16, 8, 0))
    return str(word)


def render(row: bytes, prof: list[dict], table=None) -> str:
    return ' '.join(
        f'{cell(struct.unpack_from(">I", row, k * 4)[0], p["type"], table):>13}'
        for k, p in enumerate(prof))


# --------------------------------------------------------------------------

def collect(root, want: str = ''):
    """Every ECH leaf under a directory. The directory may hold the `.cpk`
    containers themselves, or the tree `assets.py unpack` writes - which has
    directories *named* `card.cpk`, so the test is whether a `.cpk` there is a
    file, not whether the name matches."""
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*')):
            if not p.is_file():
                continue
            blob = p.read_bytes()
            if blob[:4] == MAGIC:
                yield p.relative_to(root).as_posix(), blob
        return
    for path, blob in leaves(root, want):
        if blob[:4] == MAGIC:
            yield path, blob


def _one(root, name) -> tuple[str, Ech]:
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Ech(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    ok = bad = rows = pooled = 0
    widths: dict[int, int] = {}
    spares: dict[int, int] = {}
    versions: dict[int, int] = {}
    errs: list[str] = []
    for path, blob in collect(root):
        try:
            e = Ech(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 10:
                errs.append(f'  {exc}')
            continue
        ok += 1
        rows += e.rows
        pooled += bool(e.pool)
        widths[e.row_size] = widths.get(e.row_size, 0) + 1
        spares[e.spare] = spares.get(e.spare, 0) + 1
        versions[e.version] = versions.get(e.version, 0) + 1
    for m in errs:
        print(m)
    print(f'{ok} ECH tables consistent, {bad} failed, {rows:,} rows')
    print('  field @0x08: '
          + ', '.join(f'{k:#x} x{v}' for k, v in sorted(spares.items())))
    print('  version    : '
          + ', '.join(f'{k:#x} x{v}' for k, v in sorted(versions.items())))
    print(f'  {pooled} tables carry a string pool, {ok - pooled} end on the '
          f'last row')
    print(f'  {len(widths)} distinct row widths, {min(widths)}..{max(widths)} '
          f'bytes')
    return 0 if not bad else 1


def cmd_info(root, name) -> int:
    path, e = _one(root, name)
    print(path)
    print(f'  {e.rows} rows of {e.row_size} bytes ({e.lanes} words), '
          f'version {e.version:#x}')
    d = e.default
    nz = [f'{k}={struct.unpack_from(">I", d, k * 4)[0]:#x}'
          for k in range(e.lanes)
          if struct.unpack_from('>I', d, k * 4)[0]]
    print(f'  default row: {"all zero" if not nz else " ".join(nz)}')
    if e.pool:
        print(f'  string pool: {len(e.pool):,} bytes, '
              f'{len(e.strings())} strings')
    print()
    print(f'  {"col":>3} {"off":>4}  {"type":<8} {"distinct":>8}  evidence')
    for k, p in enumerate(e.profile()):
        note = p.get('note', '')
        if p.get('sample'):
            note += '  e.g. ' + ', '.join(repr(s) for s in p['sample'])
        print(f'  {k:>3} {k * 4:>4}  {p["type"]:<8} {p["distinct"]:>8}  {note}')
    return 0


def cmd_dump(root, name, n=12) -> int:
    path, e = _one(root, name)
    prof = e.profile()
    print(f'{path}  {e.rows} rows x {e.lanes} words')
    print('     ' + ' '.join(f'{p["type"]:>13}' for p in prof))
    for i in range(min(int(n), e.rows)):
        print(f'{i:>4} ' + render(e.row(i), prof, e))
    return 0


def cmd_strings(root, name) -> int:
    path, e = _one(root, name)
    if not e.pool:
        print(f'{path}: no string pool')
        return 0
    print(f'{path}: {len(e.pool):,} bytes')
    for off, s in e.strings():
        print(f'  {off:>6}  {s}')
    return 0


def cmd_grep(root, text) -> int:
    needle = text.encode()
    n = 0
    for path, blob in collect(root):
        try:
            e = Ech(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        if needle in e.pool:
            hits = [s for _, s in e.strings() if text in s]
            print(f'{path}  ({len(hits)} hits)  '
                  + ', '.join(hits[:4]))
            n += 1
    print(f'{n} tables')
    return 0


def cmd_survey(root) -> int:
    items = []
    for path, blob in collect(root):
        try:
            e = Ech(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        items.append((e.rows * e.row_size, e.rows, e.lanes,
                      len(e.strings()) if e.pool else 0, path))
    print(f'{"rows":>6} {"words":>6} {"strings":>8} {"bytes":>9}  table')
    for size, rows, lanes, strs, path in sorted(items, reverse=True):
        print(f'{rows:>6} {lanes:>6} {strs:>8} {size:>9,}  {path}')
    print(f'{len(items)} tables')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'info':
        return cmd_info(rest[0], rest[1])
    if cmd == 'dump':
        return cmd_dump(rest[0], rest[1], rest[2] if len(rest) > 2 else 12)
    if cmd == 'strings':
        return cmd_strings(rest[0], rest[1])
    if cmd == 'grep':
        return cmd_grep(rest[0], rest[1])
    if cmd == 'survey':
        return cmd_survey(rest[0])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
