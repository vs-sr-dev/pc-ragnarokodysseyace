"""
elbn.py - reader for `ELBN`, the named-parameter container.

**707 files, 318 distinct parameter names, 0 unreadable.** `ELBN` was on the
deferred list as "unidentified, no consumer waiting". It turns out to be the
one format on this disc that names its own contents: a blob whose top level is
a **sorted table of `(name, offset, size)`**, so that every value in it arrives
with the identifier the engine's C++ used for it.

That makes it the counterpart of the `.json` actor parameters in
[`params.md`](../docs/params.md) - the same job, done in binary, for everything
the JSON does not cover. The vocabulary is the point:
`character_clipping_distance`, `shadow_offset`, `field_camera_data`,
`lockon_camera_data`, `region_data`, `motionDataHeader`, `se_hitlevel_tbl`,
`jostle_data`, `bowstring_data`, `clip_distance`. And 13 of the files are
called `objbin.cpp`, which is a build system that forgot to rename its output
and is as good as a comment.

## The shell

The same 16-byte shell as `CMDL`, `CNOM`, `CMTM` and `CTEX`, and - like the
first three and unlike `CTEX` - a `POF0` relocation table after the payload.
That is the fifth format in the family and the trick from
[`format_cmdl.md`](../docs/format_cmdl.md) works unchanged: *these* words hold
pointers and no others.

    file length == 16 + payload + 16 + POF0 payload + 16

    0x00  'ELBN'
    0x04  u32   payload size
    0x08  u32   0x00010000          not the 0x00010005 the others carry
    0x0C  u32   zero
    --- the payload begins here, and every offset below is relative to it ---
    0x00  u32   entry count
    0x04  count * 12 bytes:
          +0x00  u32   name offset
          +0x04  u32   data offset
          +0x08  u32   data size
    then the names and the data, and then POF0

Every one of the 707 files passes all of it: the count is sane, every name
offset lands on a NUL-terminated string, every data region lies inside the
payload, no two data regions overlap, and every relocation names a word inside
the payload holding an offset that is also inside the payload. 13,437
relocations in all.

**The entries are sorted by name**, on all 707 files, which is what a table
meant to be looked up by name looks like rather than one written in the order
somebody declared things.

## The values

`ELBN` says how big a value is and what it is called. It does not say what type
it is, and there is no type field anywhere - so a reader can only do what
[`ech.py`](ech.py) does with its columns, which is infer. Three things are
knowable without guessing:

- **which words are pointers**, because `POF0` says so;
- **which words are plausible floats**, on the usual exponent test;
- **what a pointer points at**, by following it.

That is enough to render a value as structure, and `dump` does. What it is not
enough for is naming the fields inside a record, which stays open.

The shapes that recur are worth knowing, because they are how the engine writes
an array:

- **a count and a pointer**, sometimes with a stride. `mot_param.bin` holds
  exactly two entries: `motionDataHeader`, twelve bytes reading
  `(87, ptr, 16)`, and `_dataA`, whose size is `87 * 16` to the byte. The
  header describes the array and the array is a second entry beside it, and
  `count * stride == size` on all 19 of them.

  **That one is the motion table**, and the disc proves it. Each 16-byte row
  begins with a motion id, and for the twelve player classes every id in the
  table is a `CNOM` animation sitting in the same `.pac` - 87 of 87 for `fas`,
  91 of 91 for `fcl`, 115 of 115 for `fmg`, with no id left over on either
  side. `fas` row 211 is `fas211walk`, the walk cycle sessions 6 and 7 posed a
  character with. The rest of the row is a `u16` of flags, four zero bytes and
  then five bytes that are all 100, which is a per-motion percentage of
  something the disc does not name;
- **a pointer to a name**, which is how `stage_param` reaches its lights.
  `stage.cpk/010_01_01`'s copy is 48 bytes of counts and pointers that lead to
  a fog record ending in a pointer to the string `st_fog_0`, and to four and
  six more ending in `ch_amb_1`, `mc_dir_2`, `bm_dir_1` - ambient and
  directional lights, named the way an artist names them;
- **four bytes that are four bytes**, not a float. `shadow_param` is
  `0a 14 28 c8`; read as a float that is 1.4e-32.

**And packed RGBA is the trap here that it was in `CMTM`.** A stage's six
directional lights carry their colour as a word - `0xfaebc8ff` is a warm sun,
`0x82d7afff` a green bounce - and most of those words fall outside the float
range, so the inference calls them integers and the eye catches them. One does
not: `ch_dir_2` on `010_01_01` is `0x46d7b4ff`, a perfectly plausible 27610.5.
`dump` therefore prints the RGBA reading of **any** word ending in `ff`
alongside whatever it inferred, and leaves the choice to the reader.

## Where it is used

    trace_par.bin       207   ref_tbl, par_tbl
    stageparam.bin      154   the stage's own parameters; see stage.py
    objbin.bin           89   clip_distance, col_hit, jostle_data
    stobjbin.bin         89
    mot_param.bin        60   motionDataHeader and _dataA, per character class
    bowstring.bin        25
    objbin.cpp           13
    command_data.bin     12   with select_action, select_target, target_data
    ...                       and 55 more names, one to a handful of files each

`command_data.bin`, `select_action.bin`, `select_target.bin` and
`target_data.bin` sit in `ai.pac` beside the `AI_B17_Loki.par` files that
[`RECON.md` section 7b](../docs/RECON.md) already used to name the monsters, so
that is where the AI's own tables are.

## Reading order

    check    the shell arithmetic, on every file
    survey   every name on the disc, with the files that carry it
    names    the entries of one file
    dump     one file, or one entry, rendered word by word
    field    where a name occurs, and what sizes it takes
"""

from __future__ import annotations

import collections
import fnmatch
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402
from cmdl import decode_pof0                                  # noqa: E402

MAGIC = b'ELBN'
POF0 = b'POF0'
HEADER = 0x10
ENTRY = 12
VERSION = 0x00010000


def looks_float(w: int) -> bool:
    """The usual exponent test: a normal float of a magnitude a game uses."""
    e = (w >> 23) & 0xFF
    return w == 0 or (0x68 <= e <= 0x98)          # about 1e-7 to 1e7


class Entry:
    __slots__ = ('name', 'offset', 'size')

    def __init__(self, name: str, offset: int, size: int):
        self.name, self.offset, self.size = name, offset, size


class Elbn:
    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != MAGIC:
            raise ValueError(f'{label}: not an ELBN ({buf[:4]!r})')
        self.label = label
        self.buf = buf
        self.size, self.version, spare = struct.unpack_from('>III', buf, 4)
        self.end = HEADER + self.size
        if self.end + 16 > len(buf) or buf[self.end:self.end + 4] != POF0:
            raise ValueError(f'{label}: no POF0 at {self.end:#x}')
        self.pof0_size = struct.unpack_from('>I', buf, self.end + 4)[0]
        self.relocations = decode_pof0(
            buf[self.end + HEADER:self.end + HEADER + self.pof0_size])
        self.reloc = set(self.relocations)
        self.count = struct.unpack_from('>I', buf, HEADER)[0]
        self.entries: list[Entry] = []
        for i in range(self.count):
            no, do, sz = struct.unpack_from('>3I', buf, HEADER + 4 + ENTRY * i)
            self.entries.append(Entry(self.cstr(no), do, sz))

    # -- payload access; every offset here is payload-relative ---------------

    def word(self, o: int) -> int:
        return struct.unpack_from('>I', self.buf, HEADER + o)[0]

    def data(self, o: int, n: int) -> bytes:
        return self.buf[HEADER + o:HEADER + o + n]

    def cstr(self, o: int) -> str:
        b = self.buf
        return b[HEADER + o:b.index(b'\0', HEADER + o)].decode('ascii',
                                                              'replace')

    def by_name(self) -> dict[str, Entry]:
        return {e.name: e for e in self.entries}

    def get(self, name: str) -> bytes | None:
        e = self.by_name().get(name)
        return None if e is None else self.data(e.offset, e.size)

    # -- what a word is ------------------------------------------------------

    def kind(self, o: int) -> str:
        if o in self.reloc:
            return 'ptr'
        w = self.word(o)
        if w and looks_float(w):
            return 'f32'
        return 'u32'

    def render(self, o: int) -> str:
        w = self.word(o)
        k = self.kind(o)
        if k == 'ptr':
            t = w
            s = self.string_at(t)
            return f'-> {t:#x}' + (f'  "{s}"' if s else '')
        rgba = (f'   rgba {w >> 24} {(w >> 16) & 255} {(w >> 8) & 255} 255'
                if w & 0xFF == 0xFF else '')
        if k == 'f32':
            v = struct.unpack('>f', struct.pack('>I', w))[0]
            return f'{v:g}{rgba}'
        if w < 0x10000:
            return str(w)
        return f'{w:#x}{rgba}'

    def string_at(self, o: int) -> str | None:
        """A pointer target that is printable ASCII up to a NUL."""
        b = self.buf
        i = HEADER + o
        if not (HEADER <= i < HEADER + self.size):
            return None
        j = b.find(b'\0', i, HEADER + self.size)
        if j < i + 1 or j - i > 64:
            return None
        s = b[i:j]
        return s.decode() if all(32 <= c < 127 for c in s) else None


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


def _one(root, name: str) -> tuple[str, Elbn]:
    hits = [(p, b) for p, b in collect(root)
            if p == name or p.rsplit('/', 1)[-1] == name
            or fnmatch.fnmatch(p, f'*{name}*')]
    if not hits:
        raise SystemExit(f'not found: {name}')
    if len(hits) > 1:
        print(f'{len(hits)} matches, using the first:')
        for p, _ in hits[:8]:
            print(f'  {p}')
    return hits[0][0], Elbn(hits[0][1], hits[0][0])


def cmd_check(root) -> int:
    tally: dict[str, int] = {}
    errs: list[str] = []
    files = bad = entries = relocs = 0

    def note(k: str, ok: bool, detail: str = '') -> None:
        tally[k] = tally.get(k, 0) + (1 if ok else 0)
        tally[k + ' /n'] = tally.get(k + ' /n', 0) + 1
        if not ok and len(errs) < 12:
            errs.append(f'  {detail}')

    for path, blob in collect(root):
        files += 1
        try:
            f = Elbn(blob, path)
        except ValueError as e:
            bad += 1
            if len(errs) < 12:
                errs.append(f'  {e}')
            continue
        entries += f.count
        relocs += len(f.relocations)
        note('version is 0x00010000', f.version == VERSION,
             f'{path}: version {f.version:#x}')
        note('file length closes',
             len(blob) == f.end + HEADER + f.pof0_size + HEADER,
             f'{path}: {len(blob)} bytes, expected '
             f'{f.end + HEADER + f.pof0_size + HEADER}')
        note('table fits the payload', 4 + ENTRY * f.count <= f.size,
             f'{path}: {f.count} entries do not fit {f.size} bytes')
        note('data regions inside the payload',
             all(0 <= e.offset and e.offset + e.size <= f.size
                 for e in f.entries), f'{path}: an entry runs past the payload')
        rs = sorted((e.offset, e.size) for e in f.entries)
        note('data regions do not overlap',
             all(rs[i][0] + rs[i][1] <= rs[i + 1][0]
                 for i in range(len(rs) - 1)),
             f'{path}: two entries overlap')
        names = [e.name for e in f.entries]
        note('entries sorted by name', names == sorted(names),
             f'{path}: names out of order')
        note('relocations inside the payload',
             all(0 <= r < f.size for r in f.relocations),
             f'{path}: a relocation is outside the payload')
        note('relocation targets inside the payload',
             all(f.word(r) < f.size for r in f.relocations),
             f'{path}: a pointer leaves the payload')

    print(f'{files} files, {entries} entries, {relocs} relocations, '
          f'{bad} unreadable')
    for k in sorted(tally):
        if k.endswith(' /n'):
            continue
        print(f'  {tally[k]:6d} / {tally[k + " /n"]:<6d} {k}')
    if errs:
        print('\nfirst failures:')
        print('\n'.join(errs))
    return 0


def cmd_survey(root) -> int:
    names: collections.Counter = collections.Counter()
    basenames: collections.Counter = collections.Counter()
    sizes: dict[str, set] = collections.defaultdict(set)
    n = 0
    for path, blob in collect(root):
        n += 1
        basenames[path.rsplit('/', 1)[-1]] += 1
        for e in Elbn(blob, path).entries:
            names[e.name] += 1
            sizes[e.name].add(e.size)
    print(f'{n} files, {len(names)} distinct parameter names\n')
    print(f'{"file":<28s} {"n":>5s}')
    for k, v in basenames.most_common(24):
        print(f'  {k:<26s} {v:5d}')
    print(f'\n{"parameter":<34s} {"files":>6s}  sizes')
    for k, v in names.most_common():
        s = sorted(sizes[k])
        shown = ' '.join(str(x) for x in s[:6]) + (' ...' if len(s) > 6 else '')
        print(f'  {k:<32s} {v:6d}  {shown}')
    return 0


def cmd_names(root, name: str) -> int:
    path, f = _one(root, name)
    print(f'{path}\n  {f.count} entries, payload {f.size} bytes, '
          f'{len(f.relocations)} relocations')
    for e in f.entries:
        print(f'  {e.name:<34s} {e.offset:#08x}  {e.size:6d} bytes')
    return 0


def cmd_dump(root, name: str, entry: str = '') -> int:
    path, f = _one(root, name)
    print(path)
    seen: set = set()

    def block(o: int, n: int, indent: str) -> list[int]:
        """Render n bytes as words, and collect the pointers found."""
        out = []
        for k in range(0, n & ~3, 4):
            w = o + k
            print(f'{indent}{w:#08x}  +{k:<4d} {f.kind(w):<4s} {f.render(w)}')
            if f.kind(w) == 'ptr':
                out.append(f.word(w))
        if n & 3:
            print(f'{indent}{o + (n & ~3):#08x}  +{n & ~3:<4d} raw  '
                  f'{f.data(o + (n & ~3), n & 3).hex(" ")}')
        return out

    for e in f.entries:
        if entry and not fnmatch.fnmatch(e.name, entry):
            continue
        print(f'\n{e.name}   {e.offset:#08x}  {e.size} bytes')
        follow = block(e.offset, e.size, '    ')
        for t in follow:
            if t in seen or f.string_at(t):
                continue
            seen.add(t)
            nxt = min([o for o in
                       sorted({x.offset for x in f.entries}
                              | {f.word(r) for r in f.relocations}
                              | {f.size}) if o > t], default=f.size)
            span = min(nxt - t, 256)
            if span <= 0:
                continue
            print(f'      -> {t:#08x}  {span} bytes')
            block(t, span, '        ')
    return 0


def cmd_field(root, want: str) -> int:
    rows = []
    for path, blob in collect(root):
        f = Elbn(blob, path)
        for e in f.entries:
            if fnmatch.fnmatch(e.name, want) or want in e.name:
                rows.append((e.name, e.size, path))
    if not rows:
        print(f'no entry matches {want!r}')
        return 1
    print(f'{len(rows)} occurrences')
    for name, size, path in sorted(rows):
        print(f'  {name:<32s} {size:6d} bytes   {path}')
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
    if cmd == 'names':
        return cmd_names(rest[0], rest[1])
    if cmd == 'dump':
        return cmd_dump(rest[0], rest[1], *rest[2:3])
    if cmd == 'field':
        return cmd_field(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
