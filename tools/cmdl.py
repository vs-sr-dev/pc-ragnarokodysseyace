"""
cmdl.py - reader for `CMDL`, the geometry format.

1,127 models: characters, monsters, equipment, stage ground and props. With
`CTEX` decoded ([`ctex.py`](ctex.py)) this is what a frame is made of.

A `CMDL` file is three chunks back to back, and the identity holds on all
1,127 files:

    file length == 16 + payload + 16 + POF0 payload + 16

    0x00  'CMDL'
    0x04  u32   payload size
    0x08  u32   0x00010005          the same version word CTEX carries
    0x0C  u32   zero
    0x10  u32   0x10002000          constant
    0x40  float[3] + pad            scale, 1 1 1 on every file
    0x50  float[4]                  bounding sphere: centre x y z, then radius
    0x60  u16[8]                    element counts; see below
    0x70  float                     1.0
    0x74  u32[11]                   the section directory
    0xb0  char[32]                  the model's name, NUL padded
    0xd0  the sections, in directory order

Then a `POF0` chunk with the same 16-byte shell, and sixteen zero bytes.

**`POF0` is a relocation table**, and it is the reason the payload size does
not reach the end of the file. It lists every word in the payload that holds a
pointer, so the loader can turn file offsets into addresses. That makes the
format self-describing in a way guessing never is: *these* words are pointers
and no others. 76,423 of them across the disc, every one landing inside its
payload and holding a valid offset.

The encoding is a stream of deltas in units of four bytes, the top two bits of
the first byte giving the width:

    01xxxxxx                     6-bit delta
    10xxxxxx yyyyyyyy            14-bit
    11xxxxxx yyyyyyyy zzzzzzzz   22-bit
    00                           end

The 22-bit case is three bytes, not four. Reading it as four decodes 751 of
1,127 files and then walks off the end of the rest, which is the sort of error
that looks like a corrupt file rather than a wrong assumption.

**Every offset in the file, including those in the directory, is relative to
`0x10`** - the start of the payload - so a file offset is `0x10 + value`.

## The section directory

Eleven `u32` at `0x74`. The first ten point at sections, in ascending order;
entry 4 is null on 705 files and a few others are null here and there. The
eleventh equals the payload size and is the end marker, which is why it is the
one entry `POF0` does not relocate.

    S0  the draw list           12 bytes per call, counts[1] of them,
                                padded up to a multiple of sixteen
    S1  the node table          96 bytes per node,     == counts[2] exactly
    S2  the material table      48 bytes per material, == counts[3] exactly
    S3  the mesh descriptors, followed by the vertex and index buffers
    S4  usually absent
    S5  the node names
    S6  the material names
    S7  the texture names, which are `CTEX` names
    S8  pointers into a block of short u16 records, one per texture
    S9  16-byte digests, then a further pointer table

A name table is `u32 count`, then that many pointers, then the strings.

## The draw list

This is what ties the model together, and it is three `u16` in a 12-byte
record: **node, material, mesh**, then a trailing 1.

    +0x00  u32   zero
    +0x04  u16   node index      into the node table
    +0x06  u16   material index  into the material table
    +0x08  u16   mesh index      into the mesh descriptors
    +0x0A  u16   1

`counts[1]` of them. On `monster.cpk/b17_00` - Loki - the list reads
`node 14 (b17_white_eye_l3), material 0, mesh 0`, and so on down six eyes, a
body and a pair of wings. Every index on the disc is in range.

## The material

48 bytes. **`u16` at `+0x02` is the index of its texture** in the `S7` name
list, and those names are `CTEX` names: `b17_00_a`, `b17_00_a_spe`, and the
`CTEX` files of exactly those names sit in the same `.pac` as the model. That
is the whole model - material - texture chain, resolved by name inside one
container. The three words at `+0x08` are RGBA colours, `808080ff` and
`000000ff` being the common pair.

The index is in range on 1,119 of the 1,127 files. The eight that are not are
stage grounds where one material of forty-odd points one slot past the end of
`S7`; on those files `S8` declares one entry more than `S7` does, so the index
space is probably `S8`'s and `S7` is a name list that runs one short. `check`
reports them rather than clamping.

## The node table

96 bytes, and the hierarchy is a depth-first walk with the depth in the file:

    +0x00  u32   flags
    +0x04  u8    depth, 1 for the root      then three bytes, 0x000001
    +0x08  u32   0x08000000 when the node carries geometry
    +0x10  float[3] + pad   translation
    +0x20  float[3] + pad   rotation, radians
    +0x30  float[3] + pad   scale
    +0x40  i16, u16, u32
    +0x50  float[4]         bounding sphere, zero unless the node has geometry

The parent of a node is the nearest node before it with a depth one lower.
The names in `S5` line up with this table one for one, and they are legible -
`mzzh_l_hand`, `mzzh_r_leg`, `TopN`, `top`, `trans`.

## The mesh descriptor

80 bytes, `counts[4]` of them, at the head of `S3`:

    +0x00  u32   0x010f__07, the middle byte varying
    +0x04  u32   0x0e250200
    +0x08  u16   index count      +0x0A  u16  primitive type
    +0x0C  u32   index buffer
    +0x10  u16   vertex count     +0x12  u16  vertex type
    +0x14  u8[4] attribute offsets, and see below
    +0x18  u8 0, u8 stride, u8 stride again, u8 0
    +0x1C  u32   vertex buffer
    +0x40  float[4]  bounding sphere

Indices are `u16`, triangle lists. **The vertex block ends exactly where the
index block begins** - `vertex pointer + count * stride == index pointer` on
all 15,833 meshes, with no padding and no alignment between them.

**`+0x14` byte 0 is the position offset**, and the file proves it rather than
the reader assuming it: the mesh's own bounding sphere centre equals the centre
of the decoded vertex bounds. Byte 1 is the normal offset, and a normal is
present exactly when `byte0 - byte1 == 12`. Every vertex type on the disc comes
in two strides twelve apart, the wider one being the same layout with a normal
inserted in front of the position, which is what makes that rule readable off
the census rather than guessed:

    vertex type  strides    position, normal, ...
    0x0003       12, 24     0 / 12, normal at 0
    0x0013       20, 32     8 / 20, normal at 8
    0x0017       24, 36     12 / 24, normal at 12
    0x0037       32, 44     20 / 32, normal at 20
    0x0313       40         24, normal at 12, and byte 3 is 4

**Byte 3 is the offset of texture coordinates**, two floats, present when bit 4
of the vertex type is set. Bits 5 and 6 add a second and third set, eight bytes
each, stacked in front; bits 8 and 9 add the four-byte pair a skinned mesh
needs. Reading the census that way accounts for every stride on the disc.

Positions are three floats. **Vertices are already in model space**, not in
node space: no transform has to be composed to draw a model, and the model's
declared bounding sphere confirms it - which is why a textured render comes out
right with the node hierarchy read but not applied.

Usage:
  python cmdl.py check <dir>              the whole arithmetic, every file
  python cmdl.py survey <dir>             every model, largest first
  python cmdl.py info <dir> <name>        header, sections, names
  python cmdl.py nodes <dir> <name>       the node tree
  python cmdl.py meshes <dir> <name>      the mesh descriptors
  python cmdl.py draws <dir> <name>       the draw list, with names
  python cmdl.py obj <dir> <name> <out>   export Wavefront OBJ
  python cmdl.py find <dir> <glob>        locate a model at any depth
"""
from __future__ import annotations

import fnmatch
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

MAGIC = b'CMDL'
POF0 = b'POF0'
HEADER = 0x10
NODE = 96
MATERIAL = 48
DESC = 80
NUL = bytes(1)


def decode_pof0(data: bytes) -> list[int]:
    """Payload-relative offsets of every word that holds a pointer."""
    out: list[int] = []
    off = i = 0
    while i < len(data):
        b = data[i]
        tag = b >> 6
        if tag == 0:
            break
        if tag == 1:
            v, i = b & 0x3F, i + 1
        elif tag == 2:
            v, i = ((b & 0x3F) << 8) | data[i + 1], i + 2
        else:
            v = ((b & 0x3F) << 16) | (data[i + 1] << 8) | data[i + 2]
            i += 3
        off += v * 4
        out.append(off)
    return out


class Mesh:
    __slots__ = ('index', 'indices', 'index_ptr', 'prim', 'vertices',
                 'vtype', 'layout', 'stride', 'vertex_ptr', 'sphere')

    def __init__(self, buf: bytes, o: int, index: int):
        self.index = index
        self.indices, self.prim = struct.unpack_from('>HH', buf, o + 0x08)
        self.index_ptr = struct.unpack_from('>I', buf, o + 0x0C)[0]
        self.vertices, self.vtype = struct.unpack_from('>HH', buf, o + 0x10)
        self.layout = struct.unpack_from('>4B', buf, o + 0x14)
        self.stride = buf[o + 0x19]
        self.vertex_ptr = struct.unpack_from('>I', buf, o + 0x1C)[0]
        self.sphere = struct.unpack_from('>4f', buf, o + 0x40)

    @property
    def position_offset(self) -> int:
        return self.layout[0]

    @property
    def normal_offset(self) -> int | None:
        """Present exactly when the position sits twelve bytes past it."""
        return self.layout[1] if self.layout[0] - self.layout[1] == 12 else None

    @property
    def uv_offset(self) -> int | None:
        """Two floats, present when bit 4 of the vertex type is set."""
        return self.layout[3] if self.vtype & 0x10 else None

    @property
    def drawable(self) -> bool:
        return bool(self.index_ptr and self.vertex_ptr and self.stride
                    and self.vertices and self.indices)


class Cmdl:
    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != MAGIC:
            raise ValueError(f'{label}: not a CMDL ({buf[:4]!r})')
        self.label = label
        self.buf = buf
        self.size, self.version, spare = struct.unpack_from('>III', buf, 4)
        self.end = HEADER + self.size
        if self.end + 16 > len(buf) or buf[self.end:self.end + 4] != POF0:
            raise ValueError(f'{label}: no POF0 at {self.end:#x}')
        self.pof0_size = struct.unpack_from('>I', buf, self.end + 4)[0]
        if len(buf) != 48 + self.size + self.pof0_size:
            raise ValueError(f'{label}: {len(buf)} bytes, but 48 + {self.size}'
                             f' + {self.pof0_size} is '
                             f'{48 + self.size + self.pof0_size}')
        if spare:
            raise ValueError(f'{label}: word at 0x0C is {spare:#x}, not zero')
        self.scale = struct.unpack_from('>3f', buf, 0x40)
        self.sphere = struct.unpack_from('>4f', buf, 0x50)
        self.counts = struct.unpack_from('>8H', buf, 0x60)
        self.dir = struct.unpack_from('>11I', buf, 0x74)
        self.name = buf[0xB0:0xD0].split(NUL)[0].decode('ascii', 'replace')

    # -- the pieces

    @property
    def nodes(self) -> int:
        return self.counts[2]

    @property
    def materials(self) -> int:
        return self.counts[3]

    @property
    def meshes(self) -> int:
        return self.counts[4]

    def at(self, off: int) -> int:
        """A payload-relative offset as a file offset."""
        return HEADER + off

    def relocations(self) -> list[int]:
        o = self.end + 16
        return decode_pof0(self.buf[o:o + self.pof0_size])

    def section(self, i: int) -> tuple[int, int] | None:
        """(file offset, length) of section i, or None when it is absent."""
        start = self.dir[i]
        if not start:
            return None
        end = next((v for v in self.dir[i + 1:11] if v), self.size)
        return self.at(start), end - start

    def node(self, i: int) -> dict:
        s = self.section(1)
        o = s[0] + i * NODE
        b = self.buf
        return {
            'flags': struct.unpack_from('>I', b, o)[0],
            'depth': b[o + 4],
            'geometry': bool(struct.unpack_from('>I', b, o + 8)[0] & 0x08000000),
            'translation': struct.unpack_from('>3f', b, o + 0x10),
            'rotation': struct.unpack_from('>3f', b, o + 0x20),
            'scale': struct.unpack_from('>3f', b, o + 0x30),
            'sphere': struct.unpack_from('>4f', b, o + 0x50),
        }

    def mesh(self, i: int) -> Mesh:
        s = self.section(3)
        return Mesh(self.buf, s[0] + i * DESC, i)

    def draws(self) -> list[tuple[int, int, int]]:
        """(node, material, mesh) for every call, in the order to draw them."""
        s = self.section(0)
        if not s:
            return []
        return [struct.unpack_from('>HHH', self.buf, s[0] + i * 12 + 4)
                for i in range(self.counts[1])]

    def material(self, i: int) -> dict:
        s = self.section(2)
        o = s[0] + i * MATERIAL
        return {
            'texture': struct.unpack_from('>H', self.buf, o + 2)[0],
            'colours': struct.unpack_from('>3I', self.buf, o + 8),
        }

    def names(self, sec: int) -> list[str]:
        s = self.section(sec)
        if not s:
            return []
        o = s[0]
        n = struct.unpack_from('>I', self.buf, o)[0]
        if n > 4096 or 4 + 4 * n > s[1]:
            return []
        out = []
        for k in range(n):
            p = self.at(struct.unpack_from('>I', self.buf, o + 4 + 4 * k)[0])
            e = self.buf.find(NUL, p, self.end)
            if e < 0:
                return out
            out.append(self.buf[p:e].decode('ascii', 'replace'))
        return out

    # -- geometry

    def positions(self, m: Mesh) -> list[tuple[float, float, float]]:
        o = self.at(m.vertex_ptr) + m.position_offset
        return [struct.unpack_from('>3f', self.buf, o + i * m.stride)
                for i in range(m.vertices)]

    def uvs(self, m: Mesh) -> list[tuple[float, float]] | None:
        off = m.uv_offset
        if off is None:
            return None
        o = self.at(m.vertex_ptr) + off
        return [struct.unpack_from('>2f', self.buf, o + i * m.stride)
                for i in range(m.vertices)]

    def triangles(self, m: Mesh) -> list[tuple[int, int, int]]:
        o = self.at(m.index_ptr)
        idx = struct.unpack_from(f'>{m.indices}H', self.buf, o)
        return [(idx[k], idx[k + 1], idx[k + 2])
                for k in range(0, m.indices - 2, 3)]


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


def _one(root, name) -> tuple[str, Cmdl]:
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Cmdl(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    files = bad = 0
    tally: dict[str, int] = {}
    errs: list[str] = []

    def note(k: str, ok: bool, detail: str = '') -> None:
        tally[k] = tally.get(k, 0) + (1 if ok else 0)
        tally[k + ' /total'] = tally.get(k + ' /total', 0) + 1
        if not ok and len(errs) < 12:
            errs.append(f'  {detail}')

    for path, blob in collect(root):
        try:
            m = Cmdl(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 12:
                errs.append(f'  {exc}')
            continue
        files += 1
        rel = m.relocations()
        ok = all(m.at(o) + 4 <= m.end for o in rel)
        note('POF0 words inside the payload', ok, f'{path}: relocation past the end')
        ok = True
        for o in rel:
            v = struct.unpack_from('>I', blob, m.at(o))[0]
            if v and m.at(v) > m.end:
                ok = False
                break
        note('POF0 targets inside the payload', ok, f'{path}: pointer past the end')
        present = [v for v in m.dir[:10] if v]
        note('directory ascending',
             all(a < b for a, b in zip(present, present[1:])), f'{path}: directory')
        note('directory ends on the payload size', m.dir[10] == m.size,
             f'{path}: last entry {m.dir[10]:#x}, payload {m.size:#x}')
        s = m.section(1)
        note('node table is counts[2] x 96',
             (s[1] if s else 0) == m.nodes * NODE,
             f'{path}: node section {s[1] if s else 0} for {m.nodes} nodes')
        s = m.section(2)
        note('material table is counts[3] x 48',
             (s[1] if s else 0) == m.materials * MATERIAL,
             f'{path}: material section {s[1] if s else 0} '
             f'for {m.materials} materials')
        depths = [m.node(i)['depth'] for i in range(m.nodes)]
        note('node depths form a tree',
             bool(depths) and depths[0] == 1
             and all(d <= p + 1 for p, d in zip(depths, depths[1:])),
             f'{path}: depths {depths[:8]}')
        note('node names match the node count',
             len(m.names(5)) == m.nodes,
             f'{path}: {len(m.names(5))} names for {m.nodes} nodes')
        note('material names match the material count',
             len(m.names(6)) == m.materials,
             f'{path}: {len(m.names(6))} names for {m.materials} materials')
        s = m.section(0)
        note('draw list is counts[1] x 12, padded to 16',
             0 <= (s[1] if s else 0) - m.counts[1] * 12 < 16,
             f'{path}: draw section {s[1] if s else 0} for {m.counts[1]} calls')
        draws = m.draws()
        note('draw list indices in range',
             all(n < m.nodes and mat < m.materials and me < m.meshes
                 for n, mat, me in draws),
             f'{path}: draw list out of range')
        note('material texture index in range',
             all(m.material(i)['texture'] < max(1, len(m.names(7)))
                 for i in range(m.materials)),
             f'{path}: texture index out of range')
        if not m.section(3):
            continue
        for i in range(m.meshes):
            mesh = m.mesh(i)
            note('mesh descriptor signature',
                 struct.unpack_from('>I', blob, m.section(3)[0] + i * DESC)[0]
                 & 0xFFFF00FF == 0x010F0007, f'{path}: mesh {i} signature')
            if not mesh.drawable:
                continue
            vend = mesh.vertex_ptr + mesh.vertices * mesh.stride
            note('vertex block ends on the index block',
                 vend == mesh.index_ptr,
                 f'{path}: mesh {i} vertices end {vend:#x}, indices at '
                 f'{mesh.index_ptr:#x}')
            idx = struct.unpack_from(f'>{mesh.indices}H', blob,
                                     m.at(mesh.index_ptr))
            note('indices inside the vertex buffer',
                 max(idx) < mesh.vertices,
                 f'{path}: mesh {i} index {max(idx)} of {mesh.vertices}')
            pos = m.positions(mesh)
            lo = [min(p[k] for p in pos) for k in range(3)]
            hi = [max(p[k] for p in pos) for k in range(3)]
            span = max(hi[k] - lo[k] for k in range(3)) or 1.0
            off = max(abs((lo[k] + hi[k]) / 2 - mesh.sphere[k])
                      for k in range(3))
            note('positions centred on the declared sphere',
                 off <= span * 0.02 + 1e-4,
                 f'{path}: mesh {i} centre off by {off:.4f} of span {span:.3f}')

    print(f'{files} CMDL, {bad} unreadable')
    for k in sorted(tally):
        if k.endswith(' /total'):
            continue
        print(f'  {tally[k]:>7,} / {tally[k + " /total"]:<7,}  {k}')
    for line in errs:
        print(line)
    return 1 if bad else 0


def cmd_survey(root) -> int:
    out = []
    for path, blob in collect(root):
        try:
            m = Cmdl(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        tris = sum(m.mesh(i).indices // 3 for i in range(m.meshes)) \
            if m.section(3) else 0
        out.append((len(blob), tris, m, path))
    out.sort(key=lambda r: -r[0])
    print(f'{len(out)} CMDL, largest first')
    for size, tris, m, path in out[:40]:
        print(f'  {size:>10,}  {m.meshes:>4} meshes {m.nodes:>4} nodes '
              f'{tris:>8,} tris  {path}')
    return 0


def cmd_info(root, name) -> int:
    path, m = _one(root, name)
    print(path)
    print(f'  name        {m.name}')
    print(f'  payload     {m.size:,} bytes, POF0 {m.pof0_size:,}, '
          f'{len(m.relocations()):,} relocations')
    print(f'  sphere      centre {m.sphere[0]:.3f} {m.sphere[1]:.3f} '
          f'{m.sphere[2]:.3f}, radius {m.sphere[3]:.3f}')
    print(f'  counts      {m.counts}')
    print(f'              {m.nodes} nodes, {m.materials} materials, '
          f'{m.meshes} meshes')
    print('  sections')
    for i in range(10):
        s = m.section(i)
        print(f'    S{i}  ' + (f'{s[0]:#08x}  {s[1]:>9,} bytes'
                               if s else 'absent'))
    for sec, what in ((5, 'node names'), (6, 'material names'),
                      (7, 'texture names')):
        names = m.names(sec)
        if names:
            print(f'  S{sec} {what}: ' + ', '.join(names[:8])
                  + (' ...' if len(names) > 8 else ''))
    return 0


def cmd_nodes(root, name) -> int:
    path, m = _one(root, name)
    names = m.names(5)
    print(f'{path}  {m.nodes} nodes')
    for i in range(m.nodes):
        n = m.node(i)
        t, r = n['translation'], n['rotation']
        print('  %s%-24s %s t %7.3f %7.3f %7.3f  r %7.3f %7.3f %7.3f'
              % ('  ' * (n['depth'] - 1),
                 names[i] if i < len(names) else f'#{i}',
                 'G' if n['geometry'] else ' ',
                 t[0], t[1], t[2], r[0], r[1], r[2]))
    return 0


def cmd_meshes(root, name) -> int:
    path, m = _one(root, name)
    print(f'{path}  {m.meshes} meshes')
    for i in range(m.meshes):
        x = m.mesh(i)
        nrm = x.normal_offset
        print(f'  {i:>3}  {x.vertices:>6,} verts  {x.indices // 3:>7,} tris  '
              f'type {x.vtype:#06x} stride {x.stride:>3}  pos@{x.position_offset}'
              + (f' nrm@{nrm}' if nrm is not None else ' no normal')
              + f'  layout {x.layout}')
    return 0


def cmd_draws(root, name) -> int:
    path, m = _one(root, name)
    nodes, mats, texs = m.names(5), m.names(6), m.names(7)
    print(f'{path}  {m.counts[1]} draw calls')
    for i, (n, mat, me) in enumerate(m.draws()):
        t = m.material(mat)['texture'] if mat < m.materials else -1
        print('  %3d  node %-3d %-24s mat %-3d %-18s tex %-2d %-16s mesh %d'
              % (i, n, nodes[n] if n < len(nodes) else '?',
                 mat, mats[mat] if mat < len(mats) else '?',
                 t, texs[t] if 0 <= t < len(texs) else '?', me))
    return 0


def cmd_obj(root, name, out) -> int:
    path, m = _one(root, name)
    nodes, texs = m.names(5), m.names(7)
    lines, base, tbase = [], 1, 1
    lines.append(f'# {path}')
    lines.append(f'# {m.name}: {m.meshes} meshes, {m.nodes} nodes, '
                 f'{m.counts[1]} draw calls')
    for call, (n, mat, me) in enumerate(m.draws()):
        x = m.mesh(me)
        if not x.drawable:
            continue
        pos = m.positions(x)
        uv = m.uvs(x)
        t = m.material(mat)['texture'] if mat < m.materials else -1
        lines.append(f'o {call:03d}_{nodes[n] if n < len(nodes) else me}')
        lines.append('# texture: '
                     + (texs[t] if 0 <= t < len(texs) else 'none'))
        for p in pos:
            lines.append('v %.6f %.6f %.6f' % p)
        for q in uv or ():
            lines.append('vt %.6f %.6f' % q)
        for a, b, c in m.triangles(x):
            if max(a, b, c) >= x.vertices:
                continue
            if uv:
                lines.append('f %d/%d %d/%d %d/%d'
                             % (base + a, tbase + a, base + b, tbase + b,
                                base + c, tbase + c))
            else:
                lines.append(f'f {base + a} {base + b} {base + c}')
        base += len(pos)
        tbase += len(uv or ())
    pathlib.Path(out).write_text('\n'.join(lines) + '\n', encoding='ascii')
    print(f'{path}  ->  {out}  ({base - 1:,} vertices)')
    return 0


def cmd_find(root, pattern) -> int:
    n = 0
    for path, blob in collect(root):
        if fnmatch.fnmatch(path.rsplit('/', 1)[-1], pattern) \
                or fnmatch.fnmatch(path, pattern):
            try:
                m = Cmdl(blob, path)
            except Exception:                                 # noqa: BLE001
                continue
            n += 1
            print(f'  {m.meshes:>4} meshes {m.nodes:>4} nodes  {path}')
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
    if cmd == 'nodes':
        return cmd_nodes(rest[0], rest[1])
    if cmd == 'meshes':
        return cmd_meshes(rest[0], rest[1])
    if cmd == 'draws':
        return cmd_draws(rest[0], rest[1])
    if cmd == 'obj':
        return cmd_obj(rest[0], rest[1], rest[2])
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
