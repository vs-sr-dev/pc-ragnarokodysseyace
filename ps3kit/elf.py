"""A PS3 executable, decrypted: its segments, function table, imports and process parameters.

    python -m ps3kit.elf GAME.elf [--imports] [--opd]

The input is the PowerPC 64 big-endian ELF that comes out of a SELF
(ps3kit does not decrypt; the port supplies the ELF). What a PS3 ELF has
that a plain one does not, and what this module reads:

- **Function descriptors.** A function pointer is the address of an 8-byte
  `{entry, toc}` pair, not of code: the PS3 runs 64-bit code in a 32-bit
  address space, so the ABI's 24-byte descriptor shrinks to two words.
  `e_entry` is one of them, and the table they sit in is walked from it.
- **The PRX parameters** (program header 0x60000002): where the import
  stubs are. Each imported library has a record naming it, the NIDs of the
  functions it wants and a table of slots the loader fills with descriptor
  addresses; the game's stub code loads a slot and calls through it.
- **The process parameters** (program header 0x60000001): SDK version,
  the primary thread's priority and stack size, malloc's page size.
- **The TLS image** (PT_TLS).
"""
import argparse
import hashlib
import os
import struct

PT_LOAD, PT_TLS = 1, 7
PT_PROC_PARAM, PT_PROC_PRX = 0x60000001, 0x60000002
DESC = 8

# A NID is the first four bytes, little-endian, of SHA-1(name + this suffix).
_NID_SUFFIX = bytes.fromhex("6759659904250490566427499489741A")


def nid(name):
    return struct.unpack("<I", hashlib.sha1(name.encode() + _NID_SUFFIX).digest()[:4])[0]


def load_names(path=None):
    """{nid: name} from ps3kit/nids.txt (one `module name` per line), with
    each NID computed from its name rather than trusted from the file."""
    path = path or os.path.join(os.path.dirname(__file__), "nids.txt")
    names = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].split()
            if len(line) == 2:
                names[nid(line[1])] = line[1]
    return names


class Segment:
    __slots__ = ("type", "flags", "vaddr", "data", "memsz")

    def __init__(self, type_, flags, vaddr, data, memsz):
        self.type, self.flags, self.vaddr, self.data, self.memsz = type_, flags, vaddr, data, memsz

    @property
    def text(self):
        return bool(self.flags & 1)


class Import:
    __slots__ = ("module", "nids", "slots", "vnids", "vslots")

    def __init__(self, module, nids, slots, vnids, vslots):
        self.module, self.nids, self.slots = module, nids, slots
        self.vnids, self.vslots = vnids, vslots


class Image:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.blob = b = f.read()
        if b[:4] != b"\x7fELF" or b[4] != 2 or b[5] != 2:
            raise ValueError(f"{path}: not a 64-bit big-endian ELF (decrypt the SELF first)")
        self.entry = struct.unpack_from(">Q", b, 24)[0]
        phoff = struct.unpack_from(">Q", b, 32)[0]
        phentsize, phnum = struct.unpack_from(">HH", b, 54)
        self.phdrs = []
        for i in range(phnum):
            t, fl, off, va, pa, fs, ms, al = struct.unpack_from(">IIQQQQQQ", b, phoff + i * phentsize)
            self.phdrs.append((t, fl, off, va, fs, ms))
        self.segments = [Segment(t, fl, va, b[off:off + fs], ms)
                         for t, fl, off, va, fs, ms in self.phdrs if t == PT_LOAD and fs]

    # --- reading -----------------------------------------------------------------

    def segment_at(self, a):
        for s in self.segments:
            if s.vaddr <= a < s.vaddr + len(s.data):
                return s
        return None

    def read(self, a, n):
        s = self.segment_at(a)
        if s is None:
            raise KeyError(f"{a:08X} is in no loaded segment")
        o = a - s.vaddr
        return s.data[o:o + n]

    def u32(self, a):
        return struct.unpack(">I", self.read(a, 4))[0]

    def u16(self, a):
        return struct.unpack(">H", self.read(a, 2))[0]

    def cstr(self, a):
        s = self.segment_at(a)
        o = a - s.vaddr
        return s.data[o:s.data.index(b"\0", o)].decode("latin1")

    def text_segments(self):
        return [s for s in self.segments if s.text]

    def _phdr(self, t):
        return next((p for p in self.phdrs if p[0] == t), None)

    # --- the function table --------------------------------------------------------

    def _descriptor(self, a):
        try:
            entry, toc = struct.unpack(">II", self.read(a, 8))
        except (KeyError, struct.error):
            return None
        es, ts = self.segment_at(entry), self.segment_at(toc)
        if entry % 4 or es is None or not es.text or toc % 4 or ts is None or ts.text:
            return None
        return entry, toc

    def opd(self):
        """[(entry, toc)]: the descriptor table, walked both ways from e_entry."""
        if self._descriptor(self.entry) is None:
            raise ValueError("e_entry does not name a descriptor")
        lo = self.entry
        while self._descriptor(lo - DESC):
            lo -= DESC
        hi = self.entry
        while self._descriptor(hi):
            hi += DESC
        return [self._descriptor(a) for a in range(lo, hi, DESC)]

    # --- what the loader reads ------------------------------------------------------

    def imports(self):
        """[Import] from the PRX parameters' stub records."""
        p = self._phdr(PT_PROC_PRX)
        if p is None:
            return []
        head = self.read(p[3], 0x20)
        magic, _, _, ent_s, ent_e, stub_s, stub_e = struct.unpack_from(">7I", head, 4)
        if magic != 0x1B434CEC:
            raise ValueError(f"PRX parameters magic {magic:08X}")
        out = []
        a = stub_s
        while a < stub_e:
            size = self.read(a, 1)[0]
            nf, nv = struct.unpack(">HH", self.read(a + 6, 4))
            name_p, nids_p, slots_p, vnids_p, vslots_p = struct.unpack(">5I", self.read(a + 0x10, 20))
            nids = [self.u32(nids_p + 4 * i) for i in range(nf)]
            slots = [slots_p + 4 * i for i in range(nf)]
            vnids = [self.u32(vnids_p + 4 * i) for i in range(nv)]
            vslots = [self.u32(vslots_p + 4 * i) for i in range(nv)]
            out.append(Import(self.cstr(name_p), nids, slots, vnids, vslots))
            a += size
        return out

    def process_param(self):
        """The process parameters as a dict, or None."""
        p = self._phdr(PT_PROC_PARAM)
        if p is None or p[4] < 0x24:
            return None
        f = struct.unpack(">9I", self.read(p[3], 0x24))
        keys = ("size", "magic", "version", "sdk_version", "primary_prio", "primary_stacksize",
                "malloc_pagesize", "ppc_seg", "crash_dump_param_addr")
        return dict(zip(keys, f))

    def tls(self):
        """(vaddr, file size, memory size) of the TLS image, or None."""
        p = self._phdr(PT_TLS)
        return (p[3], p[4], p[5]) if p else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("elf")
    ap.add_argument("--imports", action="store_true")
    ap.add_argument("--opd", action="store_true")
    a = ap.parse_args()
    img = Image(a.elf)
    print(f"entry descriptor {img.entry:08X}")
    for s in img.segments:
        kind = "r-x" if s.text else "rw-"
        print(f"  {kind}  {s.vaddr:08X}  {len(s.data):10d} bytes  {s.memsz:10d} in memory")
    print(f"process parameters {img.process_param()}")
    print(f"TLS {img.tls()}")
    if a.opd:
        rows = img.opd()
        print(f"descriptors {len(rows)}, functions {len({e for e, _ in rows})}")
    if a.imports:
        names = load_names()
        imps = img.imports()
        known = sum(1 for m in imps for n in m.nids if n in names)
        print(f"imports: {len(imps)} libraries, {sum(len(m.nids) for m in imps)} functions, "
              f"{known} named")
        for m in imps:
            print(f"  {m.module:22s} {len(m.nids):3d}  " +
                  " ".join(names.get(n, f"?{n:08X}") for n in m.nids))


if __name__ == "__main__":
    main()
