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

    check     the shell arithmetic, on every file
    survey    every name on the disc, with the files that carry it
    names     the entries of one file
    dump      one file, or one entry, rendered word by word
    field     where a name occurs, and what sizes it takes
    records   one name's records, profiled column by column over the disc
    capsules  `col_hit`, `jostle_data` and `pgs_data` with their bones named
    regions   a monster's body regions, joined to the bones and the drops
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



# --------------------------------------------------------------------------
# the records inside the values


def _bounds(f: Elbn) -> list[int]:
    """Every offset something is known to start at, sorted."""
    return sorted({e.offset for e in f.entries}
                  | {f.word(r) for r in f.relocations} | {f.size})


def is_header(f: Elbn, e: Entry) -> tuple[int, int] | None:
    """`(count, pointer)` when the entry is one, else None."""
    if e.size != 8 or e.offset in f.reloc or (e.offset + 4) not in f.reloc:
        return None
    n = f.word(e.offset)
    return (n, f.word(e.offset + 4)) if 0 < n <= 4096 else None


def strides(files) -> dict[str, int]:
    """A stride for every `(count, pointer)` name, from where the array ends.

    An array is packed against whatever is allocated after it, so
    `(next allocation - pointer) / count` is the stride whenever the array is
    the last thing before that boundary. It is not always - padding and the
    payload tail both stretch the gap - so the answer is the **mode** over
    every file carrying the name, not any single file's arithmetic.
    """
    cand: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for _, f in files:
        b = _bounds(f)
        for e in f.entries:
            h = is_header(f, e)
            if h is None:
                continue
            n, ptr = h
            nxt = next((x for x in b if x > ptr), f.size)
            if nxt > ptr and (nxt - ptr) % n == 0:
                cand[e.name][(nxt - ptr) // n] += 1
    return {k: c.most_common(1)[0][0] for k, c in cand.items()}


class Column:
    """One word position, seen down every record of one name on the disc."""

    __slots__ = ('kinds', 'values', 'n')

    def __init__(self):
        self.kinds: collections.Counter = collections.Counter()
        self.values: collections.Counter = collections.Counter()
        self.n = 0

    def add(self, f: Elbn, o: int) -> None:
        self.n += 1
        k = f.kind(o)
        self.kinds[k] += 1
        w = f.word(o)
        if k == 'ptr':
            s = f.string_at(w)
            self.values[f'"{s}"' if s else '->'] += 1
        elif k == 'f32':
            self.values[f'{struct.unpack(">f", struct.pack(">I", w))[0]:g}'] \
                += 1
        else:
            self.values[str(w) if w < 0x10000 else hex(w)] += 1

    def line(self) -> str:
        kinds = '/'.join(k for k, _ in self.kinds.most_common())
        top = ' '.join(v + (f'*{c}' if c > 1 else '')
                       for v, c in self.values.most_common(8))
        return f'{kinds:<9s} {len(self.values):4d}u  {top}'


def cmd_records(root, want: str = '*', stride: str = '') -> int:
    """Every record of a name, profiled column by column across the disc.

    This is what `dump` cannot do. `dump` renders one file; a field only
    becomes readable when the same word is seen down every file that carries
    the record, because that is what separates a constant from a payload and
    an index from a measurement.
    """
    files = [(p, Elbn(b, p)) for p, b in collect(root)]
    st = strides(files)
    fixed = int(stride) if stride else 0
    names = sorted({e.name for _, f in files for e in f.entries
                    if fnmatch.fnmatch(e.name, want) or want in e.name})
    if not names:
        print(f'no entry matches {want!r}')
        return 1
    for name in names:
        cols: dict[int, Column] = collections.defaultdict(Column)
        sizes: collections.Counter = collections.Counter()
        counts: collections.Counter = collections.Counter()
        seen = 0
        s = fixed or st.get(name, 0)
        for _, f in files:
            for e in f.entries:
                if e.name != name:
                    continue
                seen += 1
                sizes[e.size] += 1
                h = is_header(f, e)
                if h is not None:
                    n, ptr = h
                    counts[n] += 1
                    if not s:
                        continue
                    span = range(n)
                    base = ptr
                else:
                    base = e.offset
                    if not fixed:
                        s = e.size
                    span = range(max(1, e.size // s))
                for i in span:
                    o = base + i * s
                    if o + s > f.size:
                        break
                    for j in range(0, s & ~3, 4):
                        cols[j].add(f, o + j)
        head = f'== {name}   {seen} files   sizes ' \
               f'{" ".join(f"{k}x{v}" for k, v in sorted(sizes.items()))}'
        if counts:
            head += f'   count ' \
                    + ' '.join(f'{k}x{v}'
                               for k, v in sorted(counts.items()))
        n_rec = max((c.n for c in cols.values()), default=0)
        print(f'{head}   stride {s}   {n_rec} records')
        for j in sorted(cols):
            print(f'  +{j:<4d} {cols[j].line()}')
        print()
    return 0


# --------------------------------------------------------------------------
# the two records that are geometry

CAPSULE = {'col_hit': 32, 'jostle_data': 56, 'pgs_data': 28}


def capsules(f: Elbn, name: str) -> list[tuple]:
    """`col_hit` / `jostle_data` / `pgs_data`, as `(bone, a, b, r0, r1)`.

    All three begin with a bone and hold their geometry in that bone's own
    space; they differ in how much of it they carry. `pgs_data` stops after
    one point and one radius, which is a sphere.
    """
    e = f.by_name().get(name)
    if e is None:
        return []
    stride = CAPSULE[name]
    out = []
    for i in range(e.size // stride):
        o = e.offset + i * stride
        v = struct.unpack_from('>7f', f.buf, HEADER + o + 4)
        bone = f.word(o)
        if name == 'pgs_data':
            out.append((bone, v[:3], v[:3], v[3], v[3]))
        else:
            r1 = v[6] if name == 'col_hit' else struct.unpack_from(
                '>f', f.buf, HEADER + o + 32)[0]
            out.append((bone, v[:3], v[3:6], v[6], r1))
    return out


def _node_names(actor: pathlib.Path) -> tuple[list[str], dict[int, str]]:
    """A model's node names, and its `S4` locator ids resolved to them."""
    from cmdl import Cmdl                                   # noqa: PLC0415
    for p in sorted(actor.rglob('*.CMDL')):
        try:
            m = Cmdl(p.read_bytes(), p.name)
            names = m.names(5)
        except (ValueError, struct.error):
            continue
        loc = {i: (names[n] if n < len(names) else f'node {n}')
               for i, n in m.locators()}
        return names, loc
    return [], {}


def bone_name(v: int, names: list[str], loc: dict[int, str]) -> str:
    """A bone word is a node index below 1000 and a locator id above it."""
    if v >= 1000:
        return loc.get(v, '?') + f' [{v}]'
    return names[v] if v < len(names) else f'node {v}'


def cmd_capsules(root, actor: str) -> int:
    d = pathlib.Path(root) / actor if not pathlib.Path(actor).is_dir() \
        else pathlib.Path(actor)
    if not d.is_dir():
        hits = [p.parent for p in pathlib.Path(root).rglob('objbin.bin')
                if fnmatch.fnmatch(p.parent.name, actor)]
        if not hits:
            raise SystemExit(f'not found: {actor}')
        d = hits[0]
    ob = d / 'objbin.bin'
    if not ob.is_file():
        raise SystemExit(f'{d}: no objbin.bin')
    f = Elbn(ob.read_bytes(), str(ob))
    names, loc = _node_names(d)
    print(f'{d.as_posix()}   {len(names)} nodes, {len(loc)} locators')
    for kind in ('col_hit', 'jostle_data', 'pgs_data'):
        rows = capsules(f, kind)
        if not rows:
            continue
        print(f'\n  {kind}   {len(rows)} records')
        for i, (b, a, c, r0, r1) in enumerate(rows):
            r = f'r {r0:.2f}' if abs(r0 - r1) < 1e-6 else \
                f'r {r0:.2f}..{r1:.2f}'
            print(f'    [{i:3d}] {bone_name(b, names, loc):<20s} '
                  f'a ({a[0]:6.2f} {a[1]:6.2f} {a[2]:6.2f})  '
                  f'b ({c[0]:6.2f} {c[1]:6.2f} {c[2]:6.2f})  {r}')
    return 0


# --------------------------------------------------------------------------
# the monster body regions

REGION = 336
REGION_BRK = 752


def region_rows(f: Elbn, name: str = 'region_data') -> list[dict]:
    e = f.by_name().get(name)
    if e is None:
        return []
    stride = REGION if name == 'region_data' else REGION_BRK
    out = []
    for i in range(e.size // stride):
        o = e.offset + i * stride
        w = [f.word(o + 4 * j) for j in range(stride // 4)]
        g = lambda j: struct.unpack('>f', struct.pack('>I', w[j]))[0]  # noqa
        keep = lambda a: [x for x in a if x != 0xFFFFFFFF]             # noqa
        out.append({
            'name': f.string_at(w[0]),
            'hit': keep(w[2:2 + w[1]]),
            'push': keep(w[23:23 + w[22]]),
            'jostle': keep(w[28:28 + w[27]]),
            'group': None if w[36] == 0xFFFFFFFF else w[36],
            'defence': [g(40 + j) for j in range(8)],
            'scale': g(56),
            'byclass': [g(58 + j) for j in range(6)],
            'hp': w[65:73],
            'se': None if w[81] == 0xFFFFFFFF else w[81],
        })
        if name != 'region_data':
            out[-1].update({
                'brk_hp': [g(119 + j) for j in range(8)],
                'brk_defence': [g(153 + j) for j in range(8)],
                'node': w[184],
                'brk_se': None if w[186] == 0xFFFFFFFF else w[186],
            })
    return out


# A reader's synonym table, not the disc's: which node names an artist's
# region name would be satisfied by. It exists so the join can be counted
# rather than eyeballed, and every miss it produces is printed, so a table
# that is too strict shows up as a miss and not as a silent pass.
SYNONYM = {
    'hara': 'hara|spine', 'toge': 'spine', 'weak': 'spine',
    'chest': 'spine', 'body': 'spine|hip', 'hip': 'hip|spine',
    'waist': 'hip|spine|waist', 'head': 'head|jaw|neck',
    'neck': 'neck|head', 'shoulder': 'spine|arm|neck',
    'arm': 'arm|hand|finger', 'hand': 'hand|finger|arm',
    'wrist': 'hand|arm|wrist', 'leg': 'thigh|calf|foot|toe|leg',
    'foot': 'foot|toe|calf|thigh', 'tail': 'tail', 'wing': 'wing|arm',
    'horn': 'horn|head', 'eye': 'head|eye', 'skirt': 'skirt|hip',
    'shield': 'shield', 'weapon': 'weapon',
}


def name_agrees(region: str, bones: list[str]) -> bool | None:
    """Whether a region's own name is a name one of its bones carries.

    None when the reader's table has nothing to say about the word, which is
    a different answer from *no* and is counted separately.
    """
    import re                                                 # noqa: PLC0415
    key = re.sub(r'[^a-z]', '', region.lower())
    for k, pat in SYNONYM.items():
        if k in key:
            return any(re.search(pat, b.lower()) for b in bones)
    return None


def cmd_regions(root, want: str = '*') -> int:
    """Every monster's body regions, joined to the bones they hang off.

    The chain closes on itself: a region names its `col_hit` capsules, a
    capsule names a node, and the node's name is the region's own. Nothing in
    the file says they should agree.
    """
    import json                                             # noqa: PLC0415
    root = pathlib.Path(root)
    agree = 0
    differ: list = []
    unsure: list = []
    for ob in sorted(root.rglob('objbin.bin')):
        d = ob.parent
        if not fnmatch.fnmatch(d.name, want):
            continue
        f = Elbn(ob.read_bytes(), str(ob))
        rows = region_rows(f)
        if not rows:
            continue
        names, loc = _node_names(d)
        hits = capsules(f, 'col_hit')
        js = d / f'{d.name}.json'
        drops: list = []
        if js.is_file():
            try:
                doc = json.loads(js.read_text(encoding='utf-8',
                                              errors='replace'))
                for v in doc.values():
                    if 'it_drop_break' in v:
                        drops = v['it_drop_break']
                        break
            except ValueError:
                pass
        brk = region_rows(f, 'region_data_brk')
        print(f'{d.name}   {len(rows)} regions, {len(brk)} breakable, '
              f'{len(hits)} capsules')
        for r in rows:
            bones = ' '.join(dict.fromkeys(
                bone_name(hits[k][0], names, loc)
                for k in r['hit'] if k < len(hits)))
            print(f'    {r["name"]:<16s} hit {str(r["hit"]):<20s} {bones}')
            if any(r['defence']) or any(r['hp']):
                print(f'    {"":<16s} defence {r["defence"]}  hp {r["hp"]}')
        for r in rows:
            bones = [bone_name(hits[k][0], names, loc)
                     for k in r['hit'] if k < len(hits)]
            got = name_agrees(r['name'], bones) if bones else None
            if got is None:
                unsure.append((d.name, r['name'], bones))
            elif got:
                agree += 1
            else:
                differ.append((d.name, r['name'], bones))
        for i, r in enumerate(brk):
            item = (f'   it_drop_break[{i}] = {drops[i]}'
                    if i < len(drops) else '')
            node = bone_name(r['node'], names, loc)
            print(f'    break {r["name"]:<14s} {node:<18s}{item}')
            print(f'    {"":<20s} hp {[int(x) for x in r["brk_hp"]]}')
        print()
    total = agree + len(differ) + len(unsure)
    if total:
        print(f'{agree} of {total} regions hang their capsules off a bone '
              f'whose name is the region\'s own')
        for label, rows in (('the name and the bone disagree', differ),
                            ('the reader\'s table has no word for it',
                             unsure)):
            if rows:
                print(f'  {label}: {len(rows)}')
                for m, n, b in rows:
                    print(f'    {m:<10s} {n:<14s} {" ".join(b)}')
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
    if cmd == 'records':
        return cmd_records(rest[0], *rest[1:3])
    if cmd == 'capsules':
        return cmd_capsules(rest[0], rest[1])
    if cmd == 'regions':
        return cmd_regions(rest[0], *rest[1:2])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
