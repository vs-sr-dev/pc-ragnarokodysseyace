"""
ppc.py - the decrypted EBOOT as a program: its function table and its names.

[`self.py`](self.py) turns `EBOOT.BIN` into a 19.8 MB PowerPC 64 big-endian
ELF. That ELF is **stripped**: no symbol table, no section names, and the one
thing a disassembler asks for first - where the functions are - is nowhere in
it. This tool answers that from the file's own structure, and then puts the
disc's own vocabulary on top of it.

    python ppc.py segments <elf>
    python ppc.py opd      <elf>
    python ppc.py natives  <elf> <api list>
    python ppc.py plant    <elf> <api list> <out.tsv>
    python ppc.py refs     <elf> <hex address>

`<api list>` is the output of `psq.py api extract/tree` - the names the 3,011
scripts on the disc actually call. That is the join: **the disc says which
names the engine has to provide, and the binary says where each one is.**

## Two things carry this file, and both are in the clear

**The `.opd`.** This is a PowerPC 64 ELF, so a function pointer is not an
address but a pointer to a *descriptor* - and the descriptors are all in one
table. On the ordinary 64-bit ABI a descriptor is three 8-byte fields; on
this build it is **two 4-byte ones**, `{entry, toc}`, because the PS3 runs a
64-bit ELF in a 32-bit address space. That difference is not cosmetic: it is
why Ghidra's own PowerPC64 loader throws on this file rather than reading it.

Walked with nothing but its own arithmetic - the entry inside an executable
segment, the TOC inside a writable one - the table gives **165,596
descriptors over 69,691 distinct functions**, and the TOC values fall into
four runs, which is what a TOC larger than the 64 KB an `r2`-relative offset
can reach has to look like.

**The TOC.** The engine binds its script interface by name, and the
registration calls leave their arguments behind them in the TOC in source
order: a descriptor pointer, the name string, and - when the call passes one
and no earlier call has already needed it - a Squirrel typemask like `.i` or
`.iifffii`. So a descriptor immediately followed by a name that the disc
calls is a registration, and that is the whole join.

It places **274 of the 291** names the scripts call and no `.psq` defines.
The seventeen it does not place are the five that are Squirrel's own standard
library, `prowl_script` - which
[`format_api.md`](../docs/format_api.md) already showed is a dead reference -
and eleven that are class constructors and sample bindings rather than root
natives.

## What this is for

A name planted on a function is worth more than the function: the six items
in [`combat_loop.md`](../docs/combat_loop.md)'s ledger that live in here are
each one function, and the way to find one is to start from a named neighbour
and follow the calls. `plant` writes what a disassembler reads.
"""

import struct
import sys


def load(path) -> bytes:
    with open(path, 'rb') as f:
        blob = f.read()
    if blob[:4] != b'\x7fELF':
        raise ValueError('%s is not an ELF - run `self.py decrypt` first' % path)
    if blob[4] != 2 or blob[5] != 2:
        raise ValueError('not a 64-bit big-endian ELF')
    return blob


def header(blob: bytes) -> dict:
    f = struct.unpack_from('>HHIQQQIHHHHHH', blob, 16)
    return {
        'type': f[0], 'machine': f[1], 'entry': f[3],
        'phoff': f[4], 'shoff': f[5],
        'phentsize': f[8], 'phnum': f[9],
    }


def segments(blob: bytes) -> list:
    """The program table: what is loaded where, and with which rights."""
    h = header(blob)
    out = []
    for i in range(h['phnum']):
        p = struct.unpack_from('>IIQQQQQQ', blob, h['phoff'] + i * h['phentsize'])
        if p[0] != 1 or p[5] == 0:          # PT_LOAD with bytes in the file
            continue
        out.append({
            'off': p[2], 'vaddr': p[3], 'filesz': p[5], 'memsz': p[6],
            'x': bool(p[1] & 1), 'w': bool(p[1] & 2),
        })
    return out


def offset(segs: list, va: int, span: int = 1):
    """A virtual address to a file offset, or None if nothing loads it."""
    for s in segs:
        if s['vaddr'] <= va and va + span <= s['vaddr'] + s['filesz']:
            return s['off'] + (va - s['vaddr'])
    return None


def _in(segs: list, va: int, want_x: bool) -> bool:
    for s in segs:
        if s['x'] == want_x and s['vaddr'] <= va < s['vaddr'] + s['memsz']:
            return True
    return False


DESC = 8                  # {u32 entry, u32 toc} - four bytes each, not eight


def _descriptor(blob: bytes, segs: list, at: int):
    """The descriptor at file offset `at`, if it is one at all."""
    if not 0 <= at <= len(blob) - DESC:
        return None
    entry, toc = struct.unpack_from('>II', blob, at)
    if entry % 4 or not _in(segs, entry, True):
        return None
    if toc % 4 or not _in(segs, toc, False):
        return None
    return entry, toc


def opd(blob: bytes) -> dict:
    """The function table, found from the entry point and walked both ways.

    `e_entry` on this ABI is not code - it points at the descriptor of
    `_start`, so the table is located by the one field every ELF has. From
    there it extends as far as the descriptors do.
    """
    segs = segments(blob)
    h = header(blob)
    at = offset(segs, h['entry'], DESC)
    if at is None or _descriptor(blob, segs, at) is None:
        raise ValueError('the entry point does not name a descriptor')
    lo = at
    while _descriptor(blob, segs, lo - DESC) is not None:
        lo -= DESC
    hi = at
    while _descriptor(blob, segs, hi) is not None:
        hi += DESC
    rows, tocs = [], []
    for o in range(lo, hi, DESC):
        entry, toc = struct.unpack_from('>II', blob, o)
        rows.append((entry, toc))
        if not tocs or tocs[-1][0] != toc:
            tocs.append([toc, 0])
        tocs[-1][1] += 1
    seg = next(s for s in segs if s['off'] <= lo < s['off'] + s['filesz'])
    return {
        'vaddr': seg['vaddr'] + (lo - seg['off']),
        'count': len(rows), 'rows': rows,
        'entries': sorted({e for e, _ in rows}),
        'tocs': [tuple(t) for t in tocs],
    }


def api(path) -> tuple:
    """`psq.py api`'s own output: the names, split by who defines them.

    A line ends in `*` when a `.psq` on the disc defines the name, so the
    ones that do not are exactly what the engine has to provide.
    """
    native, scripted = set(), set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            parts = line.split()
            if len(parts) < 3 or not parts[0].isdigit():
                continue
            if not parts[2].startswith('args'):
                continue
            (scripted if line.rstrip().endswith('*') else native).add(parts[1])
    if not native:
        raise ValueError('%s does not read as `psq.py api` output' % path)
    return native, scripted


def _cstr(blob: bytes, at: int, cap: int = 80):
    end = blob.find(b'\0', at, at + cap)
    if end < 0 or end == at:
        return None
    text = blob[at:end]
    return text.decode('ascii') if all(32 <= c < 127 for c in text) else None


def natives(blob: bytes, wanted: set) -> dict:
    """`name -> (toc slot, descriptor, entry)`, out of the TOC's own order.

    A registration call leaves a descriptor pointer and a name pointer in
    adjacent TOC slots. Nothing here assumes where the TOC is: the pair is
    recognised by what it points at, and the name has to be one the disc
    actually calls.
    """
    segs = segments(blob)
    table = opd(blob)
    lo = table['vaddr']
    hi = lo + table['count'] * DESC
    found = {}
    for off in range(0, len(blob) - DESC, 4):
        ptr, name = struct.unpack_from('>II', blob, off)
        if not (lo <= ptr < hi and (ptr - lo) % DESC == 0):
            continue
        at = offset(segs, name, 1)
        if at is None:
            continue
        text = _cstr(blob, at)
        if text is None or text not in wanted or text in found:
            continue
        entry, _ = struct.unpack_from('>II', blob, offset(segs, ptr, DESC))
        seg = next(s for s in segs if s['off'] <= off < s['off'] + s['filesz'])
        found[text] = (seg['vaddr'] + (off - seg['off']), ptr, entry)
    return found


FORMS = {                 # the loads and adds that can materialise a pointer
    14: 'addi', 32: 'lwz', 34: 'lbz', 36: 'stw', 40: 'lhz',
    48: 'lfs', 50: 'lfd', 58: 'ld',
}


def functions(blob: bytes) -> tuple:
    """`(sorted entries, entry -> the TOC values its descriptors give it)`.

    A function's TOC is not a guess here: the descriptor that names the
    function names its `r2` in the same eight bytes. 6,207 of the 69,691 are
    named by descriptors in more than one window, which is what the ABI does
    to a function two windows both need, so an entry can carry more than one.
    """
    table = opd(blob)
    tocs = {}
    for entry, toc in table['rows']:
        tocs.setdefault(entry, set()).add(toc)
    return table['entries'], tocs


def refs(blob: bytes, target: int) -> list:
    """Every instruction that reaches `target` through the TOC.

    Two steps and no heuristics: find the TOC slots that hold the address,
    then find the `r2`-relative instructions whose displacement lands on one
    of them, under the TOC the containing function's own descriptor gives it.
    """
    import bisect
    segs = segments(blob)
    entries, tocs = functions(blob)
    slots = set()
    for off in range(0, len(blob) - 4, 4):
        if struct.unpack_from('>I', blob, off)[0] == target:
            seg = next((s for s in segs
                        if s['off'] <= off < s['off'] + s['filesz']), None)
            if seg is not None and not seg['x']:
                slots.add(seg['vaddr'] + (off - seg['off']))
    if not slots:
        return []
    out = []
    code = next(s for s in segs if s['x'])
    for off in range(code['off'], code['off'] + code['filesz'] - 3, 4):
        word = struct.unpack_from('>I', blob, off)[0]
        if (word >> 16) & 31 != 2:
            continue
        op = word >> 26
        if op not in FORMS:
            continue
        d = word & 0xffff
        d -= 0x10000 if d & 0x8000 else 0
        if op == 58:
            d &= ~3
        va = code['vaddr'] + (off - code['off'])
        i = bisect.bisect_right(entries, va) - 1
        if i < 0:
            continue
        entry = entries[i]
        for toc in tocs.get(entry, ()):
            if toc + d in slots:
                out.append((va, entry, FORMS[op], toc + d))
                break
    return out


def cmd_refs(path, target) -> int:
    blob = load(path)
    va = int(target, 16)
    hits = refs(blob, va)
    print('%d instructions reach %#010x through the TOC' % (len(hits), va))
    seen = {}
    for at, entry, form, slot in hits:
        seen.setdefault(entry, []).append((at, form, slot))
    for entry in sorted(seen):
        print('  in the function at %#010x:' % entry)
        for at, form, slot in seen[entry]:
            print('    %#010x  %-4s  from slot %#010x' % (at, form, slot))
    return 0


def cmd_segments(path) -> int:
    blob = load(path)
    h = header(blob)
    print('entry %#010x  %d segments with bytes in the file' % (
        h['entry'], len(segments(blob))))
    for s in segments(blob):
        print('  %s%s  vaddr %#010x  file %#010x  %10d bytes  %10d in memory' % (
            'r', ('w' if s['w'] else '-') + ('x' if s['x'] else '-'),
            s['vaddr'], s['off'], s['filesz'], s['memsz']))
    return 0


def cmd_opd(path) -> int:
    blob = load(path)
    table = opd(blob)
    print('the function table is at %#010x' % table['vaddr'])
    print('  %d descriptors of %d bytes, %d distinct functions' % (
        table['count'], DESC, len(table['entries'])))
    print('  %d TOC runs, which is a TOC wider than one r2 offset reaches:' %
          len(table['tocs']))
    for toc, n in table['tocs']:
        print('    %#010x  %6d descriptors' % (toc, n))
    ent = table['entries']
    print('  entries run %#010x to %#010x' % (ent[0], ent[-1]))
    segs = segments(blob)
    kinds = {}
    for e in ent:
        word = struct.unpack_from('>I', blob, offset(segs, e, 4))[0]
        kinds[word] = kinds.get(word, 0) + 1
    print('  the five commonest first instructions:')
    for word, n in sorted(kinds.items(), key=lambda kv: -kv[1])[:5]:
        note = ' stdu r1,-%d(r1)' % (0x10000 - (word & 0xfffc)) \
            if word >> 26 == 62 and word & 3 == 1 else ''
        print('    %08x  %6d%s' % (word, n, note))
    return 0


def cmd_natives(path, apipath) -> int:
    blob = load(path)
    wanted, scripted = api(apipath)
    print('%d names the disc calls and no .psq defines, %d it does' % (
        len(wanted), len(scripted)))
    found = natives(blob, wanted)
    print('%d of them are a descriptor and a name in adjacent TOC slots' %
          len(found))
    for name in sorted(found):
        slot, desc, entry = found[name]
        print('  %#010x  %-38s  descriptor %#010x  slot %#010x' % (
            entry, name, desc, slot))
    missing = sorted(wanted - set(found))
    print('%d not placed:' % len(missing))
    for name in missing:
        print('  %s' % name)
    return 0


def cmd_plant(path, apipath, out) -> int:
    """Every function, and a name on the ones the disc can name."""
    blob = load(path)
    wanted, _ = api(apipath)
    found = natives(blob, wanted)
    named = {entry: name for name, (_, _, entry) in found.items()}
    table = opd(blob)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        for entry in table['entries']:
            f.write('%08x\t%s\n' % (entry, named.get(entry, '')))
    print('%s: %d functions, %d of them named' % (
        out, len(table['entries']), sum(1 for e in table['entries'] if e in named)))
    hit = sum(1 for e in named if e in set(table['entries']))
    print('  every named entry is one of the table\'s own: %s' %
          ('yes' if hit == len(named) else 'no, %d of %d' % (hit, len(named))))
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    try:
        if cmd == 'segments' and len(rest) == 1:
            return cmd_segments(*rest)
        if cmd == 'opd' and len(rest) == 1:
            return cmd_opd(*rest)
        if cmd == 'natives' and len(rest) == 2:
            return cmd_natives(*rest)
        if cmd == 'plant' and len(rest) == 3:
            return cmd_plant(*rest)
        if cmd == 'refs' and len(rest) == 2:
            return cmd_refs(*rest)
    except ValueError as exc:
        print('error: %s' % exc)
        return 1
    print(__doc__)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
