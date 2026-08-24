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
    S3  the mesh descriptors, then the vertex, index and bone-palette blocks
    S4  the locator table, absent on 705 files
    S5  the node names
    S6  the material names
    S7  the texture names, which are `CTEX` names
    S8  pointers into a block of short u16 records, one per texture
    S9  16-byte digests, then the skinning bone names

A name table is `u32 count`, then that many pointers, then the strings.

## The locator table

`S4` is `u32 count`, then that many `(u16 id, u16 node)` pairs: numeric
attachment points, `1000` at the hip, `8199` at a swinging bone, `10000` at
`eff_10000`. The ids are what the `.CTXT` files sitting beside the model are
named after and open with - `collision_8910.CTXT` begins `id 8910`, and that
id is in this table against `node_fas2_sec01`. So the plain-text `.CTXT`
files, hit capsules and spring parameters both, bind to the skeleton through
`S4`.

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
    +0x30  u32   bone palette, on skinned meshes only
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

## Skinning

931 of the 15,833 meshes are skinned - the vertex types with bit 8 or 9 set,
`0x0313`, `0x0317` and `0x0337`. Three pieces put a mesh on a skeleton, and
each of them is stated in the file rather than inferred:

**The vertex carries four weights and four slots.** The first four bytes of a
vertex are `u8` weights and **they sum to exactly 255**, on all 473,193 skinned
vertices with no exception; the last four bytes of the stride are `u8` slot
numbers. Weight `k` goes with slot `k`. The layout bytes at `+0x14` describe
neither: they place the position, the normal and the texture coordinates, and
the two skin fields take the four bytes left over at each end of the stride.

**The palette is the mesh's own bone list.** `+0x30` of the descriptor points
at a block of 80-byte entries - `u16` bone, fourteen zero bytes, then a 4x4
matrix - and the slot numbers index *that*, not the node table. The blocks tile
`S3` after the vertex and index buffers, so a palette runs to the next block or
to the end of the section. A mesh has a palette exactly when it is skinned:
15,833 of 15,833.

**The bone is a name.** The `u16` indexes the name table at the tail of `S9`,
and those are node names, which is how `CNOM` binds too. The palette holds only
the bones a mesh actually uses - 14 of 21 on `fas2`'s first mesh - and lists
them in node order, while the bone ids number the model's bones in the order
the meshes first ask for them.

**The matrix is the inverse bind pose, and it is transposed**: the translation
is the fourth *row*, so the file is written for row vectors. Rebuild it as a
column-vector matrix and it satisfies

    matrix * Rx(90) * bind(node) == identity

on 872 of the 931 skinned meshes, to a thousandth. That `Rx(90)` is the whole
Z-up-to-Y-up question answered: **the vertex buffers are Z-up and the skeleton
is Y-up**, and the conversion is baked into these matrices rather than stored
anywhere as a field. So skinning a vertex,

    v' = sum over k of  weight[k]/255 * world(bone[slot[k]]) * inverse_bind[k] * v

lands in the skeleton's Y-up space, and `world()` is the node hierarchy posed
by a `CNOM` - see [`cnom.py`](cnom.py) - or the bind pose itself.

A rigid mesh is the same expression with one bone, the node its draw call
names, which is what `posed()` does: at rest that reduces to `Rx(-90)`, so
rigid and skinned meshes come out in the same space and can be drawn together.

**`bind()` is the node hierarchy with the node scale left out**, and that is
what closes the identity - keeping the scale closes only 800 of the 931. A
scale on a node is therefore a runtime one, multiplying the skinned result
rather than being baked into it, and `z20_01` says as much in the file: `top`
carries 1.5 and the two weapon nodes carry 2/3 to undo it, so the monster is a
base model wearing a size.

The 59 meshes still left over, across 25 models, are ones whose node table
records a rest transform a few degrees from the one the matrices were baked
against - the shoulders and arms, mostly - and one stage prop, `crystal`, whose
nodes place twelve instances up to 78 units from where the mesh was modelled.
**The matrix is the one to trust** for the bind; nothing on the animated path
goes through the node table's Euler angles at all, since `CNOM` keys
quaternions.

Usage:
  python cmdl.py check <dir>              the whole arithmetic, every file
  python cmdl.py survey <dir>             every model, largest first
  python cmdl.py info <dir> <name>        header, sections, names
  python cmdl.py nodes <dir> <name>       the node tree
  python cmdl.py meshes <dir> <name>      the mesh descriptors
  python cmdl.py draws <dir> <name>       the draw list, with names
  python cmdl.py skin <dir> <name>        the bone palettes and the weights
  python cmdl.py locators <dir> <name>    the attachment points of S4
  python cmdl.py obj <dir> <name> <out> [motion frame]
                                          export Wavefront OBJ, posed by a
                                          CNOM when one is named
  python cmdl.py gait <dir> <name> <motion>
                                          how fast the planted foot slides
                                          backwards, in units per frame
  python cmdl.py find <dir> <glob>        locate a model at any depth

## The gait, and what it calibrates

`gait` runs the skeleton forward through a locomotion cycle and measures how
fast the **planted foot** travels backwards in model space. In a cycle authored
to be played while the character moves, that rate *is* the locomotion speed,
because any disagreement shows on screen as a sliding foot.

On the twelve player models it comes out at the number the actor parameters
declare, with nothing fitted: `run_sp` is 0.17 and `fas213run` slides at
0.1698. That pins the unit of a `_sp` field to **units per animation frame**,
and it is what [`units.md`](../docs/units.md) builds the frame rate on.
"""
from __future__ import annotations

import fnmatch
import math
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
BONE = 80
NUL = bytes(1)
PLANTED = 0.03            # how close to its lowest an ankle counts as down

Matrix = list                                     # 4x4, row r column c

IDENTITY: Matrix = [[float(r == c) for c in range(4)] for r in range(4)]
RX90: Matrix = [[1., 0., 0., 0.], [0., 0., -1., 0.],
                [0., 1., 0., 0.], [0., 0., 0., 1.]]


def mul(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
            for i in range(4)]


def invert(m: Matrix) -> Matrix:
    """The inverse of an affine matrix. Some nodes scale, so not a transpose."""
    a = [row[:3] for row in m[:3]]
    cof = [[a[(i + 1) % 3][(j + 1) % 3] * a[(i + 2) % 3][(j + 2) % 3]
            - a[(i + 1) % 3][(j + 2) % 3] * a[(i + 2) % 3][(j + 1) % 3]
            for j in range(3)] for i in range(3)]
    det = sum(a[0][j] * cof[0][j] for j in range(3)) or 1.0
    r = [[cof[j][i] / det for j in range(3)] for i in range(3)]
    t = [-sum(r[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [r[i] + [t[i]] for i in range(3)] + [[0., 0., 0., 1.]]


def apply(m: Matrix, v) -> tuple[float, float, float]:
    return tuple(sum(m[r][c] * v[c] for c in range(3)) + m[r][3]
                 for r in range(3))


def _apply3(m: Matrix, v) -> tuple[float, float, float]:
    """The linear part only - what a direction transforms by."""
    return tuple(sum(m[r][c] * v[c] for c in range(3)) for r in range(3))


def _unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-12 else (0.0, 1.0, 0.0)


def normal_matrix(m: Matrix) -> Matrix:
    """The inverse transpose of the linear part, which is what carries a
    normal. Equal to the rotation itself when nothing scales."""
    inv = invert(m)
    rows = [[inv[c][r] for c in range(3)] + [0.0] for r in range(3)]
    return rows + [[0.0, 0.0, 0.0, 1.0]]


def from_euler(r) -> Matrix:
    """The node rotation, which is Rz Ry Rx in radians."""
    cx, sx = math.cos(r[0]), math.sin(r[0])
    cy, sy = math.cos(r[1]), math.sin(r[1])
    cz, sz = math.cos(r[2]), math.sin(r[2])
    return [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx, 0.],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx, 0.],
        [-sy, cy * sx, cy * cx, 0.],
        [0., 0., 0., 1.],
    ]


def from_quaternion(q) -> Matrix:
    """The CNOM rotation, x y z w."""
    x, y, z, w = q
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0.],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0.],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0.],
        [0., 0., 0., 1.],
    ]


def compose(translation, rotation: Matrix, scale) -> Matrix:
    m = [row[:] for row in rotation]
    for r in range(3):
        for c in range(3):
            m[r][c] *= scale[c]
        m[r][3] = translation[r]
    return m


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
                 'vtype', 'layout', 'stride', 'vertex_ptr', 'palette_ptr',
                 'sphere')

    def __init__(self, buf: bytes, o: int, index: int):
        self.index = index
        self.indices, self.prim = struct.unpack_from('>HH', buf, o + 0x08)
        self.index_ptr = struct.unpack_from('>I', buf, o + 0x0C)[0]
        self.vertices, self.vtype = struct.unpack_from('>HH', buf, o + 0x10)
        self.layout = struct.unpack_from('>4B', buf, o + 0x14)
        self.stride = buf[o + 0x19]
        self.vertex_ptr = struct.unpack_from('>I', buf, o + 0x1C)[0]
        self.palette_ptr = struct.unpack_from('>I', buf, o + 0x30)[0]
        self.sphere = struct.unpack_from('>4f', buf, o + 0x40)

    @property
    def position_offset(self) -> int:
        return self.layout[0]

    @property
    def normal_offset(self) -> int | None:
        """Present exactly when the position sits twelve bytes past it."""
        return self.layout[1] if self.layout[0] - self.layout[1] == 12 else None

    @property
    def colour_offset(self) -> int | None:
        """Four bytes of RGBA, present exactly when bit 2 of the vertex type
        is set - `layout[2]` is where they are. See *The vertex colour* above:
        it is the disc's baked lighting, and 13,168 of the 15,833 drawable
        meshes carry it."""
        return self.layout[2] if self.vtype & 0x4 else None

    @property
    def uv_offset(self) -> int | None:
        """Two floats, present when bit 4 of the vertex type is set."""
        return self.layout[3] if self.vtype & 0x10 else None

    @property
    def skinned(self) -> bool:
        """Bits 8 and 9 add the weights and the palette slots."""
        return bool(self.vtype & 0x300)

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
        self._palettes: dict[int, tuple[int, int]] | None = None

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
            'blend': self.buf[o + 4],
        }

    def _names(self, o: int, room: int) -> list[str]:
        """A name table - u32 count, that many pointers, then the strings."""
        n = struct.unpack_from('>I', self.buf, o)[0]
        if n > 4096 or 4 + 4 * n > room:
            return []
        out = []
        for k in range(n):
            p = self.at(struct.unpack_from('>I', self.buf, o + 4 + 4 * k)[0])
            e = self.buf.find(NUL, p, self.end)
            if e < 0:
                return out
            out.append(self.buf[p:e].decode('ascii', 'replace'))
        return out

    def names(self, sec: int) -> list[str]:
        s = self.section(sec)
        return self._names(s[0], s[1]) if s else []

    def bones(self) -> list[str]:
        """The skinning bones, named. A palette entry's u16 indexes this.

        They sit at the tail of S9, past the count and the 16-byte digests.
        """
        s = self.section(9)
        if not s:
            return []
        o = s[0] + 16 + struct.unpack_from('>I', self.buf, s[0])[0] * 16
        return self._names(o, s[0] + s[1] - o) if o + 4 <= s[0] + s[1] else []

    def locators(self) -> list[tuple[int, int]]:
        """S4: (id, node) for every attachment point the .CTXT files name."""
        s = self.section(4)
        if not s:
            return []
        n = struct.unpack_from('>I', self.buf, s[0])[0]
        if 4 + 4 * n > s[1]:
            return []
        return [struct.unpack_from('>HH', self.buf, s[0] + 4 + 4 * k)
                for k in range(n)]

    # -- skinning

    def palettes(self) -> dict[int, tuple[int, int]]:
        """(file offset, entry count) of every mesh's bone palette.

        The blocks tile the tail of S3, so one runs to the next or to the end
        of the section.
        """
        if self._palettes is None:
            s = self.section(3)
            ptr = {}
            if s:
                for i in range(self.meshes):
                    p = self.mesh(i).palette_ptr
                    if p:
                        ptr[i] = self.at(p)
            end = s[0] + s[1] if s else 0
            order = sorted(set(ptr.values()))
            self._palettes = {
                i: (o, (min([q for q in order if q > o], default=end) - o)
                    // BONE)
                for i, o in ptr.items()}
        return self._palettes

    def palette(self, i: int) -> list[tuple[int, Matrix]]:
        """(bone, inverse bind pose) per slot, the matrix un-transposed."""
        where = self.palettes().get(i)
        if not where:
            return []
        o, n = where
        out = []
        for k in range(n):
            b = o + k * BONE
            rows = [struct.unpack_from('>4f', self.buf, b + 16 + 16 * r)
                    for r in range(4)]
            out.append((struct.unpack_from('>H', self.buf, b)[0],
                        [[rows[c][r] for c in range(4)] for r in range(4)]))
        return out

    def skin(self, m: Mesh) -> list[tuple[bytes, bytes]]:
        """(weights, slots) per vertex - four u8 each, the weights over 255."""
        if not m.skinned:
            return []
        o = self.at(m.vertex_ptr)
        return [(self.buf[o + i * m.stride:o + i * m.stride + 4],
                 self.buf[o + (i + 1) * m.stride - 4:o + (i + 1) * m.stride])
                for i in range(m.vertices)]

    def parents(self) -> list[int]:
        """The parent of every node, -1 for the root, read off the depths."""
        out, stack = [], []
        for i in range(self.nodes):
            d = self.node(i)['depth']
            del stack[d - 1:]
            out.append(stack[-1] if stack else -1)
            stack.append(i)
        return out

    def world(self, pose: dict | None = None,
              scale: bool = True) -> list[Matrix]:
        """Every node's world matrix, in the skeleton's own Y-up space.

        With no pose that is the rest skeleton; with one - a CNOM sampled at a
        frame, keyed by bone name - it is the animated one, and a node the
        motion does not name keeps its own transform.
        """
        names = self.names(5)
        chain, out = [], []
        for i in range(self.nodes):
            n = self.node(i)
            p = pose.get(names[i]) if pose and i < len(names) else None
            if p:
                m = compose(p['translation'],
                            from_quaternion(p['rotation']),
                            p['scale'] if scale else (1., 1., 1.))
            else:
                m = compose(n['translation'], from_euler(n['rotation']),
                            n['scale'] if scale else (1., 1., 1.))
            d = n['depth']
            del chain[d - 1:]
            m = mul(chain[-1] if chain else IDENTITY, m)
            chain.append(m)
            out.append(m)
        return out

    def bind(self) -> list[Matrix]:
        """The pose the inverse bind matrices were baked against.

        It is the rest skeleton with the node scale left out - a scale there
        is a runtime one, applied over the skinning rather than into it.
        """
        return self.world(scale=False)

    def skin_matrices(self, i: int, node: int, world: list[Matrix],
                      bind: list[Matrix] | None = None) -> list[Matrix]:
        """What multiplies a vertex of mesh i, one matrix per palette slot.

        A rigid mesh is the same thing with a single bone, the one its draw
        call names, so both kinds come out in the same space.
        """
        names = self.names(5)
        pal = self.palette(i)
        if pal:
            bones = self.bones()
            out = []
            for b, inverse in pal:
                j = names.index(bones[b]) if b < len(bones) \
                    and bones[b] in names else node
                out.append(mul(world[j], inverse))
            return out
        # A rigid mesh's vertices are in **its node's own space**, so the
        # matrix is just that node's world matrix. This used to be
        # `world * inverse(RX90 * bind)`, and no picture had ever been taken
        # of the result - the renders that proved the format were skinned
        # models, which take the branch above. `engine/draw.py convention`
        # measures the three candidates against two files a model does not
        # touch: a rigid mesh's centroid lands a median of **0.055 m** from
        # the node its own draw call names, against 2.2 m either other way,
        # and a stage's visible ground agrees with its collision mesh to
        # **0.034 m** against 0.345 m turned.
        return [world[node]]

    def posed(self, m: Mesh, matrices: list[Matrix]) -> list[tuple]:
        """The mesh's vertices under those matrices, weighted."""
        pos = self.positions(m)
        if not m.skinned:
            return [apply(matrices[0], v) for v in pos]
        out = []
        for v, (w, slot) in zip(pos, self.skin(m)):
            acc = [0.0, 0.0, 0.0]
            for k in range(4):
                if not w[k] or slot[k] >= len(matrices):
                    continue
                q = apply(matrices[slot[k]], v)
                for r in range(3):
                    acc[r] += w[k] / 255.0 * q[r]
            out.append(tuple(acc))
        return out

    # -- geometry

    def positions(self, m: Mesh) -> list[tuple[float, float, float]]:
        o = self.at(m.vertex_ptr) + m.position_offset
        return [struct.unpack_from('>3f', self.buf, o + i * m.stride)
                for i in range(m.vertices)]

    def normals(self, m: Mesh) -> list[tuple[float, float, float]] | None:
        """Three floats, unit length. 28,497 of 28,544 sampled land within
        1e-3 of one, which is what says they are normals and not a second
        position lane."""
        off = m.normal_offset
        if off is None:
            return None
        o = self.at(m.vertex_ptr) + off
        return [struct.unpack_from('>3f', self.buf, o + i * m.stride)
                for i in range(m.vertices)]

    def colours(self, m: Mesh) -> list[tuple[int, int, int, int]] | None:
        """The baked RGBA, one per vertex, bytes as written."""
        off = m.colour_offset
        if off is None:
            return None
        o = self.at(m.vertex_ptr) + off
        return [tuple(self.buf[o + i * m.stride:o + i * m.stride + 4])
                for i in range(m.vertices)]

    def posed_normals(self, m: Mesh, matrices: list[Matrix]) -> list[tuple] | None:
        """The mesh's normals under those matrices, weighted.

        A normal transforms by the **inverse transpose** of the linear part,
        which is the same thing as the rotation when nothing scales and is not
        when something does - and 25 models on this disc scale a node.
        """
        nrm = self.normals(m)
        if nrm is None:
            return None
        it = [normal_matrix(mt) for mt in matrices]
        if not m.skinned:
            return [_unit(_apply3(it[0], v)) for v in nrm]
        out = []
        for v, (w, slot) in zip(nrm, self.skin(m)):
            acc = [0.0, 0.0, 0.0]
            for k in range(4):
                if not w[k] or slot[k] >= len(it):
                    continue
                q = _apply3(it[slot[k]], v)
                for r in range(3):
                    acc[r] += w[k] / 255.0 * q[r]
            out.append(_unit(acc))
        return out

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
        bones, pal_of, names5 = m.bones(), m.palettes(), m.names(5)
        bindw = m.bind() if pal_of else []
        for i in range(m.meshes):
            mesh = m.mesh(i)
            note('mesh descriptor signature',
                 struct.unpack_from('>I', blob, m.section(3)[0] + i * DESC)[0]
                 & 0xFFFF00FF == 0x010F0007, f'{path}: mesh {i} signature')
            note('a bone palette exactly when the mesh is skinned',
                 mesh.skinned == (i in pal_of),
                 f'{path}: mesh {i} type {mesh.vtype:#06x}, '
                 f'palette {mesh.palette_ptr:#x}')
            if i in pal_of:
                where = pal_of[i]
                nxt = min([o for o, _ in pal_of.values() if o > where[0]],
                          default=m.section(3)[0] + m.section(3)[1])
                note('the palette is a whole number of 80-byte entries',
                     (nxt - where[0]) % BONE == 0,
                     f'{path}: mesh {i} palette spans {nxt - where[0]} bytes')
                skin = m.skin(mesh)
                note('the four weights sum to 255',
                     all(sum(w) == 255 for w, _ in skin),
                     f'{path}: mesh {i} weights')
                note('every slot a weight uses is inside the palette',
                     all(s[k] < where[1] for w, s in skin for k in range(4)
                         if w[k]),
                     f'{path}: mesh {i} slot past {where[1]} entries')
                worst, named = 0.0, True
                for b, inverse in m.palette(i):
                    if b >= len(bones) or bones[b] not in names5:
                        named = False
                        continue
                    d = mul(inverse, mul(RX90, bindw[names5.index(bones[b])]))
                    worst = max(worst, max(abs(d[r][c] - IDENTITY[r][c])
                                           for r in range(4)
                                           for c in range(4)))
                note('every bone names a node of this model', named,
                     f'{path}: mesh {i} bone id out of range')
                note('the inverse bind pose inverts Rx(90) x the bind pose',
                     worst < 2e-3,
                     f'{path}: mesh {i} residual {worst:.4f}')
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


def cmd_skin(root, name) -> int:
    path, m = _one(root, name)
    nodes, bones = m.names(5), m.bones()
    bindw = m.bind()
    print(f'{path}  {len(bones)} skinning bones')
    for b, bone in enumerate(bones):
        print(f'   {b:>3}  {bone}')
    for i in sorted(m.palettes()):
        x = m.mesh(i)
        skin = m.skin(x)
        n = sum(1 for w, _ in skin for k in range(4) if w[k])
        print(f'  mesh {i}: {x.vertices:,} vertices, type {x.vtype:#06x} '
              f'stride {x.stride}, {n / max(1, x.vertices):.2f} influences '
              f'each')
        for k, (b, inverse) in enumerate(m.palette(i)):
            bone = bones[b] if b < len(bones) else '?'
            j = nodes.index(bone) if bone in nodes else -1
            d = mul(inverse, mul(RX90, bindw[j])) if j >= 0 else None
            res = max(abs(d[r][c] - IDENTITY[r][c])
                      for r in range(4) for c in range(4)) if d else float('nan')
            print(f'    slot {k:>3}  bone {b:>3}  node {j:>3}  {bone:<24}'
                  f' residual {res:.5f}')
    return 0


def cmd_locators(root, name) -> int:
    path, m = _one(root, name)
    nodes = m.names(5)
    loc = m.locators()
    print(f'{path}  {len(loc)} locators')
    for lid, node in loc:
        print(f'   {lid:>6}  node {node:>3}  '
              f'{nodes[node] if node < len(nodes) else "?"}')
    return 0


def cmd_obj(root, name, out, motion='', frame='0') -> int:
    path, m = _one(root, name)
    nodes, texs = m.names(5), m.names(7)
    pose = None
    if motion:
        from cnom import _one as _cnom                         # noqa: PLC0415
        apath, a = _cnom(root, motion)
        pose = a.pose(float(frame))
        print(f'{apath}  frame {frame} of {a.frames}, {a.tracks} tracks')
    world = m.world(pose)
    bind = m.bind()
    lines, base, tbase = [], 1, 1
    lines.append(f'# {path}')
    lines.append(f'# {m.name}: {m.meshes} meshes, {m.nodes} nodes, '
                 f'{m.counts[1]} draw calls')
    if motion:
        lines.append(f'# posed by {motion} at frame {frame}')
    for call, (n, mat, me) in enumerate(m.draws()):
        x = m.mesh(me)
        if not x.drawable:
            continue
        pos = m.posed(x, m.skin_matrices(me, n, world, bind))
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


def cmd_lanes(root, samples: str = '8') -> int:
    """The two lanes a renderer lights with, checked against the disc.

    **The normal.** `layout[1]` is a normal exactly when the position sits
    twelve bytes past it, and three floats read there should be a unit vector.
    Nothing forces that but the file being what it is called.

    **The colour.** Bit 2 of the vertex type declares a four-byte attribute at
    `layout[2]`, and the claim here is that it is a baked RGBA - the light the
    artist put there, since a stage has no runtime directional to light it
    with. Two things say so and both have a control: the fourth byte is 0xff
    on almost every vertex while the first three range freely, and the
    luminance **steps less across a triangle edge than between two vertices
    of the same mesh picked at random** - a bake is smooth in space and a
    tint or an index would not be.
    """
    import random                                              # noqa: PLC0415
    import statistics                                          # noqa: PLC0415

    rng = random.Random(20260824)
    step = max(1, int(samples))
    meshes = withn = withc = mismatch = 0
    lens: list[float] = []
    alpha = [0, 0]
    edge: list[float] = []
    rand: list[float] = []
    wins = [0, 0]
    for path, blob in collect(root):
        try:
            m = Cmdl(blob, path)
        except Exception:                                      # noqa: BLE001
            continue
        fe: list[float] = []
        fr: list[float] = []
        for i in range(m.meshes):
            me = m.mesh(i)
            if not me.drawable:
                continue
            meshes += 1
            # bit 2 of the vertex type and the layout byte must agree: the
            # attribute is at layout[2] exactly when that is neither the
            # position nor the normal
            base = me.normal_offset
            base = base if base is not None else me.layout[0]
            if bool(me.vtype & 0x4) != (me.layout[2] != base):
                mismatch += 1
            if me.normal_offset is not None:
                withn += 1
                o = m.at(me.vertex_ptr) + me.normal_offset
                for k in range(0, me.vertices, max(1, me.vertices // step)):
                    n = struct.unpack_from('>3f', m.buf, o + k * me.stride)
                    lens.append(math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2))
            if me.colour_offset is None:
                continue
            withc += 1
            c = m.colours(me)
            for v in c:
                alpha[0] += v[3] == 255
                alpha[1] += 1
            lum = [(v[0] + v[1] + v[2]) / 3 for v in c]
            if len(lum) < 32 or max(lum) - min(lum) < 8:
                continue
            tris = m.triangles(me)
            if not tris:
                continue
            if len(tris) > 200:
                tris = rng.sample(tris, 200)
            for a, b, d in tris:
                if max(a, b, d) >= len(lum):
                    continue
                fe += [abs(lum[a] - lum[b]), abs(lum[b] - lum[d]),
                       abs(lum[a] - lum[d])]
            n = len(lum)
            for _ in range(3 * len(tris)):
                fr.append(abs(lum[rng.randrange(n)] - lum[rng.randrange(n)]))
        if fe and fr:
            wins[0] += statistics.fmean(fe) < statistics.fmean(fr)
            wins[1] += 1
            edge += fe
            rand += fr
    lens.sort()
    print(f'{meshes} drawable meshes: {withn} carry a normal lane, '
          f'{withc} a colour lane')
    print(f'  bit 2 of the vertex type and layout byte 2 agree on '
          f'{meshes - mismatch} of {meshes}')
    if lens:
        unit = sum(1 for v in lens if abs(v - 1.0) < 1e-3)
        print(f'  {len(lens)} sampled normals: median '
              f'{lens[len(lens) // 2]:.6f}, within 1e-3 of unit on '
              f'{unit} of {len(lens)}')
    if alpha[1]:
        print(f'  the colour lane fourth byte is 0xff on {alpha[0]} of '
              f'{alpha[1]} vertices')
    if edge and rand:
        e, r = statistics.fmean(edge), statistics.fmean(rand)
        print(f'  mean luminance step across a triangle edge {e:.2f} against '
              f'{r:.2f} between two vertices of the same mesh at random, '
              f'a ratio of {e / r:.3f}')
        print(f'  and the edge is the smaller of the two on {wins[0]} of '
              f'{wins[1]} models')
    return 0


def cmd_shading(root, want: str = '*', n: str = '12') -> int:
    """Is a skinned normal in the right place? Ask the skinned geometry.

    `posed_normals` carries a normal by the **inverse transpose** of the same
    matrices the positions take, and nothing in the file says whether that is
    right. The posed triangles do: put a model in a pose its own `CNOM`
    names, and the mean of a triangle's three vertex normals should point the
    way the triangle now faces. Leaving the normals in the rest pose is the
    control, and it is the thing a reader would do by accident.
    """
    import random                                              # noqa: PLC0415
    import statistics                                          # noqa: PLC0415

    from cnom import Cnom                                      # noqa: PLC0415

    def unit(v):
        k = math.sqrt(sum(c * c for c in v)) or 1.0
        return tuple(c / k for c in v)

    def acute(a, b):
        d = max(-1.0, min(1.0, sum(a[k] * b[k] for k in range(3))))
        d = math.degrees(math.acos(d))
        return min(d, 180.0 - d)

    rng = random.Random(3)
    root = pathlib.Path(root)
    files = [q for q in root.rglob('*.CMDL') if fnmatch.fnmatch(q.name, want)]
    rng.shuffle(files)
    posed: list[float] = []
    rest: list[float] = []
    used = 0
    for q in files:
        if used >= int(n):
            break
        try:
            m = Cmdl(q.read_bytes(), q.name)
        except Exception:                                      # noqa: BLE001
            continue
        want_mesh = [i for i in range(m.meshes)
                     if m.mesh(i).drawable and m.mesh(i).skinned
                     and m.mesh(i).normal_offset is not None]
        if not want_mesh:
            continue
        names = set(m.names(5))
        motion = None
        for a in list(q.parent.parent.rglob('*.CNOM'))[:40]:
            try:
                c = Cnom(a.read_bytes(), a.name)
                if sum(1 for t in c.pose(5.0) if t in names) > 3:
                    motion = c
                    break
            except Exception:                                  # noqa: BLE001
                continue
        if motion is None:
            continue
        used += 1
        pose = motion.pose(7.0)
        world, bind = m.world(pose), m.bind()
        for node, _, i in m.draws():
            me = m.mesh(i)
            if i not in want_mesh:
                continue
            mats = m.skin_matrices(i, node, world, bind)
            pos = m.posed(me, mats)
            pn = m.posed_normals(me, mats)
            rn = m.normals(me)
            tris = m.triangles(me)
            if len(tris) > 60:
                tris = rng.sample(tris, 60)
            for a, b, c in tris:
                if max(a, b, c) >= len(pos):
                    continue
                u = [pos[b][k] - pos[a][k] for k in range(3)]
                v = [pos[c][k] - pos[a][k] for k in range(3)]
                f = unit((u[1] * v[2] - u[2] * v[1],
                          u[2] * v[0] - u[0] * v[2],
                          u[0] * v[1] - u[1] * v[0]))
                for src, out in ((pn, posed), (rn, rest)):
                    g = unit([sum(src[j][k] for j in (a, b, c)) / 3
                              for k in range(3)])
                    out.append(acute(f, g))
    if not posed:
        print('no skinned model with a motion beside it matched')
        return 1
    print(f'{used} skinned models, each posed by a CNOM that names its bones,'
          f' {len(posed)} triangles')
    for label, v in (('skinned by the inverse transpose', posed),
                     ('left in the rest pose', rest)):
        v.sort()
        print(f'  {label:<34s} median {v[len(v) // 2]:6.2f} deg from the '
              f'posed face, within 30 deg on '
              f'{sum(1 for x in v if x < 30) / len(v):.3f}')
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


def cmd_gait(root, name: str, motion: str) -> int:
    """The backward speed of the planted foot, in units per frame.

    A locomotion cycle is authored against a translation speed: while a foot
    is on the ground it must travel backwards at exactly the rate the
    character advances, or it slides. Sampling that rate reads the speed the
    animator was given, in the animation's own units.
    """
    from cnom import _one as _cnom                             # noqa: PLC0415

    path, m = _one(root, name)
    apath, a = _cnom(root, motion)
    names = m.names(5)
    index = {n: i for i, n in enumerate(names)}
    feet = [n for n in names if n.endswith('_foot')]
    if len(feet) < 2:
        print(f'{path}: no pair of *_foot nodes')
        return 1

    track = []
    for f in range(a.frames + 1):
        w = m.world(a.pose(float(f)))
        track.append({n: (w[index[n]][1][3], w[index[n]][2][3]) for n in feet})

    floor = min(min(r[n][0] for n in feet) for r in track)
    planted = [(n, f) for n in feet for f in range(1, a.frames + 1)
               if max(track[f - 1][n][0], track[f][n][0]) < floor + PLANTED
               and track[f][n][1] < track[f - 1][n][1]]
    if not planted:
        print(f'{apath}: {a.frames} frames, no frame with a foot on the floor')
        return 1
    v = sorted(track[f - 1][n][1] - track[f][n][1] for n, f in planted)
    med = v[len(v) // 2]
    print(path)
    print(f'{apath}   {a.frames} frames, {len(v)} planted samples')
    print(f'  ankle floor          {floor:.3f}')
    print(f'  slide per frame      {med:.4f}   '
          f'(p10 {v[len(v) // 10]:.4f}, p90 {v[len(v) * 9 // 10]:.4f})')
    print(f'  distance per cycle   {med * a.frames:.3f}')
    for fps in (30, 60):
        print(f'  at {fps} fps           {med * fps:6.2f} units/s, '
              f'{2 * fps / a.frames * 60:5.0f} steps/min, '
              f'step {med * a.frames / 2:.2f}')
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
    if cmd == 'skin':
        return cmd_skin(rest[0], rest[1])
    if cmd == 'locators':
        return cmd_locators(rest[0], rest[1])
    if cmd == 'obj':
        return cmd_obj(rest[0], rest[1], rest[2], *rest[3:5])
    if cmd == 'gait':
        return cmd_gait(rest[0], rest[1], rest[2])
    if cmd == 'lanes':
        return cmd_lanes(*rest)
    if cmd == 'shading':
        return cmd_shading(*rest)
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
