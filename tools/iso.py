"""
iso.py - the official extractor: reads the disc over UDF and produces extract/.

Why UDF and not ISO9660. The disc carries both filesystems, but ISO9660 names
are **truncated to 31 characters** and upper-cased. Names are data here - the
CPK table of contents, the ARC directories and the game's own resource lookups
all key on them - so extraction always goes through UDF.

Why a hand-written reader. `pycdlib` rejects this disc
(`UDF File Set Tag identifier not 256`) and it is right in its own way: PS3
Blu-rays use UDF 2.50 with a **metadata partition**, the second partition map
of the Logical Volume Descriptor. The inodes do not live in the physical
partition but inside a metadata file that overlays it. Ignoring that indirection
means reading a File Entry where a File Set Descriptor is expected - exactly
pycdlib's error. It is ~150 lines, and it buys independence from an external
dependency at the very bottom of the stack.

Descriptor chain, for whoever has to touch this again:

  sector 256       Anchor Volume Descriptor Pointer (tag 2) -> VDS extent
  VDS              Partition Descriptor (tag 5)  -> partition start sector
                   Logical Volume Descriptor (6) -> block size, FSD ICB,
                                                    partition map table
  type-2 map       '*UDF Metadata Partition' -> LBA of the metadata file
  File Entry (261) of the metadata file, type 250 -> its extents *are* the
                   blocks of the metadata partition
  File Set Desc.   (tag 256) -> ICB of the root directory
  File Entry       (261) or Extended File Entry (266) -> data extents
  directory        a run of File Identifier Descriptors (tag 257)

File *data* lives in the physical partition; only inodes live in the metadata
partition. Hence the `part` field of the long_ads, which must be honoured.

The index records **every** extent of a file, not just the first: a long_ad
carries at most 2^30-1 bytes, so any file past 1 GiB is necessarily split.
On this disc that is `sound.cpk` (1.24 GB, cut at 0x3FFFF800) and the firmware.
Recording only the first extent does not fail loudly - it reads 1.24 GB
contiguously from the first LBA and writes a silently corrupt file.

Usage:
  python iso.py index                   rewrite tools/iso_index.tsv (UDF names)
  python iso.py sets                    what the manifest declares, with totals
  python iso.py manifest                compute tools/manifest.tsv (sha256)
  python iso.py extract [set ...]       extract into extract/ (default: all)
  python iso.py verify [set ...]        compare extract/ against the manifest
  python iso.py magic <glob> [n]        leading bytes of the matching files

Options: --iso <file>  --out <dir>  --force (re-extract even if present)

The manifest is the fingerprint of the supported disc, not game content: it is
versionable and lives in the repository. `extract/` does not - see the BYOA
policy in README.md.
"""
from __future__ import annotations

import fnmatch
import hashlib
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ISO = ROOT / 'Ragnarok Odyssey ACE (USA).iso'
OUT = ROOT / 'extract'
INDEX = ROOT / 'tools' / 'iso_index.tsv'
MANIFEST = ROOT / 'tools' / 'manifest.tsv'

SECTOR = 2048
EOL = chr(10)
TAB = chr(9)

# The declared sets: name -> (glob over UDF paths, what it is for).
# `extract` with no arguments takes them all; this list *is* the definition
# of what a complete `extract/` means.
SETS: dict[str, tuple[tuple[str, ...], str]] = {
    'archive':  (('*.cpk',),        'CRI CPK containers - the whole game'),
    'patch':    (('*.cpk.patch',),  'patch CPKs, 10,360-byte stubs on the disc'),
    'boot':     (('*/EBOOT.BIN', '*/PARAM.SFO'),
                                    'PPC64 SELF and title metadata'),
    'image':    (('*.PNG', '*.png'), 'loose icons, outside the CPKs'),
    'audio':    (('*.AT3', '*.at3'), 'ATRAC3, the XMB jingle'),
    'movie':    (('*.pam',),        'PAMF, movies and cutscenes'),
}

# Deliberately undeclared: PS3UPDAT.PUP (the firmware, 256 MB), TROPHY.TRP,
# LICDIR/LIC.DAT, PS3LOGO.DAT and PS3_DISC.SFB - platform infrastructure,
# nothing to do with the game.

# Derived steps: a set whose extraction is not finished until a second
# pass has run. On 3D Dot Game Heroes that was gunzipping the maps; here
# nothing is derived, because `cpk.py` and `arc.py` read the containers
# in place and unpacking 1.7 GB twice would buy nothing.
DERIVED: dict[str, tuple[str, str]] = {}


# --------------------------------------------------------------------------
# lettore UDF

class Node:
    __slots__ = ('path', 'size', 'extents', 'is_dir')

    def __init__(self, path: str, size: int, extents: list, is_dir: bool):
        self.path = path
        self.size = size
        self.extents = extents      # [(physical sector, bytes)]
        self.is_dir = is_dir

    @property
    def lba(self) -> int:
        return self.extents[0][0] if self.extents else 0


class Udf:
    """Read-only UDF reader, just enough to list and extract. It handles
    neither sparse files nor compression: on a pressed game disc there are
    none."""

    def __init__(self, path: pathlib.Path):
        self.f = open(path, 'rb')
        self.parts: dict[int, list] = {}     # ref -> [(physical base, blocks)]
        self._read_volume()

    # -- primitives

    def _sect(self, n: int, count: int = 1) -> bytes:
        self.f.seek(n * SECTOR)
        return self.f.read(SECTOR * count)

    def _map(self, part: int, lba: int) -> int:
        """Logical block of a partition -> physical sector."""
        for base, length in self.parts[part]:
            if lba < length:
                return base + lba
            lba -= length
        raise ValueError(f'blocco {lba} fuori dalla partizione {part}')

    def _read_part(self, part: int, lba: int, size: int) -> bytes:
        """Read `size` bytes from a logical block, following the partition
        extents if the read crosses a boundary."""
        out = bytearray()
        while len(out) < size:
            phys = self._map(part, lba + len(out) // SECTOR)
            need = size - len(out)
            out += self._sect(phys, (need + SECTOR - 1) // SECTOR)[:need]
        return bytes(out)

    # -- descriptors

    def _read_volume(self) -> None:
        anchor = self._sect(256)
        if struct.unpack_from('<H', anchor, 0)[0] != 2:
            raise ValueError('no Anchor Volume Descriptor Pointer at sector 256')
        vds_len, vds_loc = struct.unpack_from('<II', anchor, 16)

        pd_start = lvd = None
        vds = self._sect(vds_loc, vds_len // SECTOR)
        for o in range(0, vds_len, SECTOR):
            tag = struct.unpack_from('<H', vds, o)[0]
            if tag == 5:
                pd_start = struct.unpack_from('<I', vds, o + 188)[0]
            elif tag == 6:
                lvd = vds[o:o + SECTOR]
        if pd_start is None or lvd is None:
            raise ValueError('Partition o Logical Volume Descriptor mancanti')

        if struct.unpack_from('<I', lvd, 212)[0] != SECTOR:
            raise ValueError('logical block size other than 2048, unsupported')

        # The physical partition is always reference 0; the map table that
        # follows at 440 declares further, virtual ones.
        self.parts[0] = [(pd_start, 1 << 62)]
        n_maps = struct.unpack_from('<I', lvd, 268)[0]
        o = 440
        for ref in range(n_maps):
            kind, length = lvd[o], lvd[o + 1]
            if kind == 2 and lvd[o + 5:o + 28] == b'*UDF Metadata Partition':
                meta_lba = struct.unpack_from('<I', lvd, o + 40)[0]
                self.parts[ref] = self._metadata_extents(pd_start, meta_lba)
            o += length

        fsd_lba, fsd_part = struct.unpack_from('<IH', lvd, 252)
        fsd = self._read_part(fsd_part, fsd_lba, SECTOR)
        if struct.unpack_from('<H', fsd, 0)[0] != 256:
            raise ValueError('the File Set Descriptor is not where the LVD says')
        self.root = struct.unpack_from('<IH', fsd, 404)  # (lba, partition)

    def _metadata_extents(self, pd_start: int, meta_lba: int) -> list:
        """The extents of the metadata file (type 250) *are* the blocks of
        the metadata partition."""
        fe = self._sect(pd_start + meta_lba)
        if struct.unpack_from('<H', fe, 0)[0] not in (261, 266):
            raise ValueError('metadata file: unrecognised File Entry')
        return [(pd_start + lba, n // SECTOR)
                for lba, n, part in self._alloc(fe, 0)]

    def _alloc(self, fe: bytes, part: int):
        """Extents declared by a File Entry, as (lba, bytes, partition).
        The descriptor type lives in the ICB tag flags."""
        tag = struct.unpack_from('<H', fe, 0)[0]
        base = 216 if tag == 266 else 176
        l_ea, l_ad = struct.unpack_from('<II', fe, base - 8)
        kind = struct.unpack_from('<H', fe, 16 + 18)[0] & 7
        o, end = base + l_ea, base + l_ea + l_ad
        if kind == 3:                       # immediate data, inside the File Entry
            return [(-1, l_ad, o)]          # (-1, bytes, offset in the File Entry)
        step = 8 if kind == 0 else 16
        out = []
        while o + step <= end:
            n, lba = struct.unpack_from('<II', fe, o)
            p = struct.unpack_from('<H', fe, o + 8)[0] if kind == 1 else part
            length, etype = n & 0x3FFFFFFF, n >> 30
            if etype == 3:                  # continuation: unused here
                raise ValueError('continuation extent, unsupported')
            if length and etype in (0, 1):  # allocated (recorded or not)
                out.append((lba, length, p))
            o += step
        return out

    # -- tree

    def _entry(self, lba: int, part: int) -> tuple[bytes, int, int, list]:
        fe = self._read_part(part, lba, SECTOR)
        tag = struct.unpack_from('<H', fe, 0)[0]
        if tag not in (261, 266):
            raise ValueError(f'File Entry inatteso: tag {tag}')
        ftype = fe[16 + 11]
        size = struct.unpack_from('<Q', fe, 56)[0]
        return fe, ftype, size, self._alloc(fe, part)

    def _fids(self, fe: bytes, size: int, extents: list, part: int):
        """The File Identifier Descriptors of a directory."""
        data = bytearray()
        for lba, n, p in extents:
            data += fe[p:p + n] if lba == -1 else self._read_part(p, lba, n)
        data = bytes(data[:size])
        o = 0
        while o + 38 <= len(data):
            if struct.unpack_from('<H', data, o)[0] != 257:
                break
            chars, l_fi = data[o + 18], data[o + 19]
            child_lba, child_part = struct.unpack_from('<IH', data, o + 24)
            l_iu = struct.unpack_from('<H', data, o + 36)[0]
            raw = data[o + 38 + l_iu:o + 38 + l_iu + l_fi]
            o = (o + 38 + l_iu + l_fi + 3) & ~3
            if chars & 0x08 or not l_fi:        # parent entry
                continue
            name = (raw[1:].decode('utf-16-be') if raw[0] == 16
                    else raw[1:].decode('latin-1'))
            yield name, bool(chars & 0x02), child_lba, child_part

    def walk(self) -> list[Node]:
        """Every file on the disc, in path order."""
        out: list[Node] = []
        stack = [('', self.root[0], self.root[1])]
        while stack:
            prefix, lba, part = stack.pop()
            fe, ftype, size, extents = self._entry(lba, part)
            for name, is_dir, clba, cpart in self._fids(fe, size, extents, part):
                path = f'{prefix}/{name}' if prefix else name
                if is_dir:
                    stack.append((path, clba, cpart))
                    continue
                _, _, csize, cext = self._entry(clba, cpart)
                phys = [(self._map(p, l), n) for l, n, p in cext]
                out.append(Node(path, csize, phys, False))
        out.sort(key=lambda n: n.path)
        return out

    def chunks(self, node: Node, limit: int = 0, size: int = 1 << 22):
        """The contents of a file, in chunks: `sound.cpk` is 1.24 GB and the
        movies are larger still, so nothing is held in memory to copy it
        or hash it."""
        want = min(limit, node.size) if limit else node.size
        done = 0
        for phys, n in node.extents:
            if done >= want:
                return
            self.f.seek(phys * SECTOR)
            left = min(n, want - done)
            while left > 0:
                b = self.f.read(min(size, left))
                if not b:
                    raise ValueError(f'{node.path}: file troncato')
                left -= len(b)
                done += len(b)
                yield b

    def read(self, node: Node, limit: int = 0) -> bytes:
        return b''.join(self.chunks(node, limit))

    def sha(self, node: Node) -> str:
        h = hashlib.sha256()
        for b in self.chunks(node):
            h.update(b)
        return h.hexdigest()


# --------------------------------------------------------------------------
# indice e manifesto

def load_index() -> list[Node]:
    if not INDEX.exists():
        raise SystemExit(f'indice mancante: {INDEX} - esegui prima: iso.py index')
    out = []
    for line in INDEX.read_text(encoding='utf-8').splitlines()[1:]:
        path, size, ext = line.split('\t')
        extents = [tuple(int(v) for v in e.split(':')) for e in ext.split(',')]
        out.append(Node(path, int(size), extents, False))
    return out


def match(node: Node, globs) -> bool:
    return any(fnmatch.fnmatch(node.path, g) for g in globs)


def select(names: list[str]) -> tuple[list[str], list[Node]]:
    """The nodes belonging to the requested sets (all, if the list is empty)."""
    unknown = [n for n in names if n not in SETS]
    if unknown:
        raise SystemExit(f'set sconosciuti: {", ".join(unknown)}\n'
                         f'disponibili: {", ".join(SETS)}')
    wanted = names or list(SETS)
    index = load_index()
    globs = tuple(g for n in wanted for g in SETS[n][0])
    return wanted, [n for n in index if match(n, globs)]


def dest(node: Node, out: pathlib.Path) -> pathlib.Path:
    return out / node.path


def human(n: int) -> str:
    for unit in ('B', 'kB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024
    return ''


def sha_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        while (b := fh.read(1 << 22)):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------
# comandi

def cmd_index(iso: pathlib.Path) -> int:
    udf = Udf(iso)
    nodes = udf.walk()
    with INDEX.open('w', encoding='utf-8', newline='\n') as fh:
        fh.write('path\tsize\textents\n')
        for n in nodes:
            ext = ','.join(f'{lba}:{num}' for lba, num in n.extents)
            fh.write(f'{n.path}\t{n.size}\t{ext}\n')
    total = sum(n.size for n in nodes)
    print(f'{len(nodes)} files, {human(total)} -> {INDEX}')
    return 0


def cmd_sets(iso: pathlib.Path) -> int:
    index = load_index()
    claimed = set()
    print(f'{"set":<11} {"files":>6} {"bytes":>10}  description')
    for name, (globs, desc) in SETS.items():
        hit = [n for n in index if match(n, globs)]
        claimed.update(id(n) for n in hit)
        print(f'{name:<11} {len(hit):>6} {human(sum(n.size for n in hit)):>10}  {desc}')
        if name in DERIVED:
            print(f'{"":<11} {"":>6} {"":>10}  + derived: {DERIVED[name][1]}')
    rest = [n for n in index if id(n) not in claimed]
    print(f'\ndeclared {len(index) - len(rest)} files of {len(index)}; '
          f'{len(rest)} undeclared')
    for n in sorted(rest, key=lambda n: -n.size)[:12]:
        print(f'  - {n.path}  ({human(n.size)})')
    if len(rest) > 12:
        print(f'  ... and {len(rest) - 12} more')
    return 0


def cmd_manifest(iso: pathlib.Path, names: list[str]) -> int:
    wanted, nodes = select(names)
    udf = Udf(iso)
    rows, total = [], 0
    for i, n in enumerate(nodes):
        rows.append((n.path, n.size, udf.sha(n)))
        total += n.size
        if i % 50 == 0:
            print(f'  {i}/{len(nodes)}  {human(total)}...', end='\r')
    with MANIFEST.open('w', encoding='utf-8', newline='\n') as fh:
        fh.write('# PC-ROA - fingerprint of the supported disc.' + EOL
                 + '# Ragnarok Odyssey ACE (USA), NPWR04119_00.' + EOL
                 + f'# {len(rows)} files, {total} bytes. UDF paths.' + EOL
                 + 'path' + TAB + 'size' + TAB + 'sha256' + EOL)
        for path, size, digest in rows:
            fh.write(f'{path}\t{size}\t{digest}\n')
    print(f'{len(rows)} files, {human(total)} -> {MANIFEST}')
    return 0


def load_manifest() -> dict[str, tuple[int, str]]:
    if not MANIFEST.exists():
        raise SystemExit(f'manifesto mancante: {MANIFEST} - '
                         f'esegui prima: iso.py manifest')
    out = {}
    for line in MANIFEST.read_text(encoding='utf-8').splitlines():
        if line.startswith('#') or line.startswith('path\t'):
            continue
        path, size, digest = line.split('\t')
        out[path] = (int(size), digest)
    return out


def cmd_extract(iso: pathlib.Path, out: pathlib.Path, names: list[str],
                force: bool) -> int:
    wanted, nodes = select(names)
    man = load_manifest() if MANIFEST.exists() else {}
    udf = Udf(iso)
    written = skipped = 0
    total = 0
    for n in nodes:
        path = dest(n, out)
        if path.exists() and path.stat().st_size == n.size and not force:
            skipped += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        with path.open('wb') as fh:
            for b in udf.chunks(n):
                h.update(b)
                fh.write(b)
        if n.path in man and h.hexdigest() != man[n.path][1]:
            print(f'  ! {n.path}: hash differs from the manifest')
        written += 1
        total += n.size
    print(f'extracted {written} files ({human(total)}), {skipped} already present')

    for name in wanted:
        if name in DERIVED:
            written += derive(out, name)
    return 0


def derive(out: pathlib.Path, name: str) -> int:
    """Run the derived step of a set. No set declares one on this disc;
    the hook stays because the extractor is the place where a second
    pass belongs, not the caller."""
    raise NotImplementedError(f'set {name} declares no derived step')


def cmd_verify(out: pathlib.Path, names: list[str], deep: bool) -> int:
    man = load_manifest()
    wanted, nodes = select(names)
    missing, wrong, ok = [], [], 0
    for n in nodes:
        path = dest(n, out)
        if not path.exists():
            missing.append(n.path)
            continue
        size, digest = man.get(n.path, (n.size, None))
        if path.stat().st_size != size:
            wrong.append((n.path, 'dimensione'))
        elif deep and digest and sha_file(path) != digest:
            wrong.append((n.path, 'sha256'))
        else:
            ok += 1
    print(f'set: {", ".join(wanted)}')
    print(f'  {ok} files match' + ('' if deep else ' (size only;'
          ' pass --deep for the sha256)'))
    for path in missing[:20]:
        print(f'  missing   {path}')
    if len(missing) > 20:
        print(f'  ... and {len(missing) - 20} more missing')
    for path, why in wrong[:20]:
        print(f'  differs   {path}  ({why})')
    if not missing and not wrong:
        print('  no problems')
    return 1 if (missing or wrong) else 0


def cmd_magic(iso: pathlib.Path, glob: str, take: int) -> int:
    nodes = [n for n in load_index() if fnmatch.fnmatch(n.path, glob)]
    if take:
        nodes = nodes[:take]
    udf = Udf(iso)
    for n in nodes:
        b = udf.read(n, 32)
        asc = ''.join(chr(c) if 32 <= c < 127 else '.' for c in b)
        print(f'{n.path}  ({n.size:,} B)')
        print(f'    {b.hex(" ")}')
        print(f'    |{asc}|')
    return 0


def main() -> int:
    argv = sys.argv[1:]
    iso, out, force, deep = ISO, OUT, False, False
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--iso':
            iso = pathlib.Path(argv[i + 1]); i += 2
        elif a == '--out':
            out = pathlib.Path(argv[i + 1]); i += 2
        elif a == '--force':
            force = True; i += 1
        elif a == '--deep':
            deep = True; i += 1
        else:
            rest.append(a); i += 1

    if not rest:
        print(__doc__)
        return 1
    cmd, args = rest[0], rest[1:]

    if cmd in ('index', 'manifest', 'magic', 'extract') and not iso.exists():
        raise SystemExit(f'ISO not found: {iso}')

    if cmd == 'index':
        return cmd_index(iso)
    if cmd == 'sets':
        return cmd_sets(iso)
    if cmd == 'manifest':
        return cmd_manifest(iso, args)
    if cmd == 'extract':
        return cmd_extract(iso, out, args, force)
    if cmd == 'verify':
        return cmd_verify(out, args, deep)
    if cmd == 'magic':
        return cmd_magic(iso, args[0] if args else '*',
                         int(args[1]) if len(args) > 1 else 5)
    print(__doc__)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
