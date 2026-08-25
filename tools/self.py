"""
self.py - the EBOOT, decrypted: `SCE`/`SELF` to a PowerPC ELF.

Every byte of logic this game does not ship as script is inside
`PS3_GAME/USRDIR/EBOOT.BIN`, and that file is a **SELF** - an ELF wrapped in
Sony's signed container with its segments encrypted.
[`STRATEGY.md`](../docs/STRATEGY.md)'s phase 3 is opening it, and
[`parity.md`](../docs/parity.md) says why: three of the seven stand-ins in the
engine are one function that lives in here.

    python self.py header  <EBOOT.BIN>
    python self.py check   <EBOOT.BIN>
    python self.py keys    <key file> [revision] [self type]
    python self.py meta    <EBOOT.BIN> <key file>
    python self.py decrypt <EBOOT.BIN> <key file> <out.elf>
    python self.py names   <out.elf>

`header` and `check` need no key at all: the container's own arithmetic, the
ELF header and the program table are **in the clear**, and only the segment
payloads are not. That is worth having on its own - it is what says which
file is worth a key.

## What is in the clear and what is not

```
$ python tools/self.py check extract/PS3_GAME/USRDIR/EBOOT.BIN
```

The `SCE` header names a `key_revision`, a `header_type` and the offsets of
five sub-headers; the `SELF` header at `0x20` points at an `APP_INFO` whose
`self_type` picks the key set. Past those sits an ordinary 64-bit
big-endian ELF header and its program table, both unencrypted, so the
segment count, their virtual addresses and their sizes are readable before
anything is decrypted. The payloads are not: their byte entropy is 7.99 of a
possible 8.

## The chain, and where each key comes from

    the key set        (key_revision, self_type) -> erk, riv
      -> METADATA_INFO   AES-256-CBC over 0x40 bytes at metadata + 0x20
      -> a key and an iv of their own
      -> METADATA_HEADERS  AES-128-CTR over the rest of the header
      -> a header, N section headers and M sixteen-byte keys
      -> each segment      AES-128-CTR, its own key and iv out of those M
      -> zlib, where the section header says so
      -> an ELF, reassembled at the program table's own offsets

Nothing above needs a signature check: the container is *signed* with ECDSA
and *encrypted* with AES, and only the second stands between here and the
code.

## And what falls out first

`names` is the whole of the disassembler-free half. This build ships two
tables the AI needs and the disc does not carry: the **`AIT_*` condition-term
enum**, 78 names on a 24-byte stride, and the **AI host predicate table**,
75 `(function, name)` pairs. Both were on
[`STRATEGY.md`](../docs/STRATEGY.md)'s phase-3 list by name.
See [`format_ai.md`](../docs/format_ai.md) for what they settled.

## The keys are not in this repository, and the tool does not want them to be

`erk` and `riv` are a local input with exactly the standing the disc has -
not game content, not derivable from the disc, and not ours to hand on. So
this file takes the **path to a key file** and reads two formats, both of
which are what somebody already has if they are doing this at all:

- **scetool's `data/keys`**, the `[name] type= revision= self_type= erk= riv=`
  ini that `keys.cpp` documents at the top of its own source;
- **RPCS3's `key_vault.cpp`**, whose `sk_*_arr.emplace_back(...)` lines carry
  the same fields positionally.

`self.py keys <file>` lists what it found, which is the cheap way to find out
whether a given file has the revision this disc wants.

## The AES is here, in about a hundred and forty lines

This repository has no third-party dependency in any of its 26 tools and this
one does not introduce one. FIPS-197's cipher and inverse cipher, CBC
decryption and CTR, are written out below and checked against the standard's
own vectors by `self.py check`, which is the only way a from-scratch cipher
should ever be believed.
"""
from __future__ import annotations

import collections
import math
import pathlib
import re
import struct
import sys
import zlib

# --------------------------------------------------------------------------
# AES-128/192/256, FIPS-197. Encrypt for CTR, decrypt for CBC.

SBOX = bytes.fromhex(
    '637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0'
    'b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275'
    '09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf'
    'd0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2'
    'cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb'
    'e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08'
    'ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e'
    'e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16')
INV = bytearray(256)
for _i, _v in enumerate(SBOX):
    INV[_v] = _i
RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
        0x6C, 0xD8, 0xAB, 0x4D)


def _xt(a: int) -> int:
    """Multiply by x in GF(2^8) with the AES polynomial."""
    a <<= 1
    return (a ^ 0x11B) if a & 0x100 else a


def _mul(a: int, b: int) -> int:
    out = 0
    while b:
        if b & 1:
            out ^= a
        a, b = _xt(a), b >> 1
    return out


_MUL = {c: bytes(_mul(x, c) for x in range(256))
        for c in (2, 3, 9, 11, 13, 14)}


def expand(key: bytes) -> list:
    """The round keys, as a list of 16-byte blocks."""
    nk, nr = len(key) // 4, len(key) // 4 + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [SBOX[x] for x in t]
            t[0] ^= RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [SBOX[x] for x in t]
        w.append([a ^ b for a, b in zip(w[i - nk], t)])
    return [bytes(b for word in w[4 * r:4 * r + 4] for b in word)
            for r in range(nr + 1)]


def _add(s: list, k: bytes) -> None:
    for i in range(16):
        s[i] ^= k[i]


def encrypt_block(rk: list, block: bytes) -> bytes:
    """One 16-byte block, forward. Column-major, as the standard is."""
    s = list(block)
    _add(s, rk[0])
    for r in range(1, len(rk)):
        s = [SBOX[x] for x in s]
        s = [s[0], s[5], s[10], s[15], s[4], s[9], s[14], s[3],
             s[8], s[13], s[2], s[7], s[12], s[1], s[6], s[11]]
        if r != len(rk) - 1:
            out = []
            for c in range(4):
                a, b, cc, d = s[4 * c:4 * c + 4]
                m2, m3 = _MUL[2], _MUL[3]
                out += [m2[a] ^ m3[b] ^ cc ^ d,
                        a ^ m2[b] ^ m3[cc] ^ d,
                        a ^ b ^ m2[cc] ^ m3[d],
                        m3[a] ^ b ^ cc ^ m2[d]]
            s = out
        _add(s, rk[r])
    return bytes(s)


def decrypt_block(rk: list, block: bytes) -> bytes:
    """One 16-byte block, backward - the equivalent inverse cipher."""
    s = list(block)
    _add(s, rk[-1])
    for r in range(len(rk) - 2, -1, -1):
        s = [s[0], s[13], s[10], s[7], s[4], s[1], s[14], s[11],
             s[8], s[5], s[2], s[15], s[12], s[9], s[6], s[3]]
        s = [INV[x] for x in s]
        _add(s, rk[r])
        if r:
            out = []
            for c in range(4):
                a, b, cc, d = s[4 * c:4 * c + 4]
                m9, mb, md, me = _MUL[9], _MUL[11], _MUL[13], _MUL[14]
                out += [me[a] ^ mb[b] ^ md[cc] ^ m9[d],
                        m9[a] ^ me[b] ^ mb[cc] ^ md[d],
                        md[a] ^ m9[b] ^ me[cc] ^ mb[d],
                        mb[a] ^ md[b] ^ m9[cc] ^ me[d]]
            s = out
    return bytes(s)


def cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    rk, prev, out = expand(key), iv, bytearray()
    for o in range(0, len(data) - len(data) % 16, 16):
        block = data[o:o + 16]
        out += bytes(a ^ b for a, b in zip(decrypt_block(rk, block), prev))
        prev = block
    return bytes(out)


def ctr_crypt(key: bytes, ctr: bytes, data: bytes) -> bytes:
    """AES-CTR, big-endian counter over the whole 16 bytes - which is what
    PolarSSL's `aes_crypt_ctr` does and therefore what the container uses."""
    rk = expand(key)
    n = int.from_bytes(ctr, 'big')
    out = bytearray(len(data))
    for o in range(0, len(data), 16):
        pad = encrypt_block(rk, n.to_bytes(16, 'big'))
        n = (n + 1) & ((1 << 128) - 1)
        chunk = data[o:o + 16]
        out[o:o + len(chunk)] = bytes(a ^ b for a, b in zip(chunk, pad))
    return bytes(out)


# FIPS-197 C.1 and C.3, and SP 800-38A F.5.1. `check` runs these.
VECTORS = (
    ('000102030405060708090a0b0c0d0e0f',
     '00112233445566778899aabbccddeeff',
     '69c4e0d86a7b0430d8cdb78070b4c55a'),
    ('000102030405060708090a0b0c0d0e0f1011121314151617'
     '18191a1b1c1d1e1f',
     '00112233445566778899aabbccddeeff',
     '8ea2b7ca516745bfeafc49904b496089'),
)


def self_test() -> list:
    out = []
    for k, p, c in VECTORS:
        rk = expand(bytes.fromhex(k))
        got = encrypt_block(rk, bytes.fromhex(p)).hex()
        out.append(('AES-%d encrypt' % (len(k) * 4), got == c))
        back = decrypt_block(rk, bytes.fromhex(c)).hex()
        out.append(('AES-%d decrypt' % (len(k) * 4), back == p))
    key = bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
    ctr = bytes.fromhex('f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff')
    txt = bytes.fromhex('6bc1bee22e409f96e93d7e117393172a')
    want = '874d6191b620e3261bef6864990db6ce'
    out.append(('AES-128 CTR', ctr_crypt(key, ctr, txt).hex() == want))
    return out


# --------------------------------------------------------------------------
# the container

MAGIC = b'SCE\0'
SCE = 0x20                      # the SCE header's own length
META_INFO = 0x40
SELF_TYPES = {1: 'LV0', 2: 'LV1', 3: 'LV2', 4: 'APP', 5: 'ISO', 6: 'LDR',
              7: 'UNK_7', 8: 'NPDRM'}
SECTION_KIND = {1: 'shdr', 2: 'phdr', 3: 'sceversion'}
ENCRYPTED, COMPRESSED = 3, 2


class Sce:
    """The headers a SELF carries in the clear."""

    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != MAGIC:
            raise ValueError('%s: not a SCE file (%r)' % (label, buf[:4]))
        self.buf, self.label = buf, label
        (self.version, self.key_revision, self.header_type) = \
            struct.unpack_from('>IHH', buf, 4)
        (self.meta, self.header_len, self.data_len) = \
            struct.unpack_from('>IQQ', buf, 0x0C)
        if self.header_type != 1:
            raise ValueError('%s: header type %d is not a SELF'
                             % (label, self.header_type))
        (self.htype, self.appinfo, self.elf, self.phdr, self.shdr,
         self.sinfo, self.scever, self.ctrl, self.ctrl_size,
         _pad) = struct.unpack_from('>10Q', buf, SCE)
        (self.authid, self.vendor, self.self_type, self.app_version,
         _p) = struct.unpack_from('>QIIQQ', buf, self.appinfo)

    # -- the ELF underneath, which is not encrypted -------------------------

    @property
    def elf64(self) -> bool:
        return self.buf[self.elf + 4] == 2

    def ehdr(self) -> dict:
        o = self.elf
        if self.buf[o:o + 4] != b'\x7fELF':
            raise ValueError('%s: no ELF at %#x' % (self.label, o))
        f = '>HHIQQQIHHHHHH' if self.elf64 else '>HHIIIIIHHHHHH'
        (kind, machine, ver, entry, phoff, shoff, flags, ehsize, phentsize,
         phnum, shentsize, shnum, shstrndx) = struct.unpack_from(f, self.buf,
                                                                 o + 16)
        return dict(kind=kind, machine=machine, entry=entry, phoff=phoff,
                    shoff=shoff, flags=flags, ehsize=ehsize,
                    phentsize=phentsize, phnum=phnum, shentsize=shentsize,
                    shnum=shnum, shstrndx=shstrndx, big=self.buf[o + 5] == 2)

    def phdrs(self) -> list:
        """The program table, read out of the SELF's own copy of it."""
        out, e = [], self.ehdr()
        for i in range(e['phnum']):
            o = self.phdr + i * e['phentsize']
            if self.elf64:
                (kind, flags, off, vaddr, paddr, filesz, memsz, align) = \
                    struct.unpack_from('>IIQQQQQQ', self.buf, o)
            else:
                (kind, off, vaddr, paddr, filesz, memsz, flags, align) = \
                    struct.unpack_from('>IIIIIIII', self.buf, o)
            out.append(dict(kind=kind, flags=flags, offset=off, vaddr=vaddr,
                            paddr=paddr, filesz=filesz, memsz=memsz,
                            align=align))
        return out

    def segment_infos(self) -> list:
        """`section_info`, one per program header: where the payload is in
        *this* file, and whether it is compressed."""
        out = []
        for i in range(self.ehdr()['phnum']):
            (off, size, comp, _a, unc, _b) = struct.unpack_from(
                '>QQIIII', self.buf, self.sinfo + i * 0x20)
            out.append(dict(offset=off, size=size, compressed=comp == 2,
                            unknown=unc))
        return out

    # -- and the part that is not -------------------------------------------

    def metadata(self, erk: bytes, riv: bytes) -> dict:
        """The metadata, decrypted: a header, the section table and the keys.

        Two steps and two ciphers. `METADATA_INFO` is 0x40 bytes of
        AES-256-CBC under the key set's own `erk`/`riv`, and it holds nothing
        but a key and an iv; those then run AES-128-CTR over everything from
        there to the end of the header.
        """
        at = self.meta + SCE
        info = cbc_decrypt(erk, riv, self.buf[at:at + META_INFO])
        key, iv = info[0:0x10], info[0x20:0x30]
        if info[0x10:0x20] != b'\0' * 16 or info[0x30:0x40] != b'\0' * 16:
            raise ValueError('%s: metadata did not decrypt - the padding '
                             'either side of the key is not zero, so this is '
                             'the wrong key set' % self.label)
        start = at + META_INFO
        body = ctr_crypt(key, iv, self.buf[start:self.header_len])
        (siglen, _u0, count, keys, opt, _u1, _u2) = struct.unpack_from(
            '>QIIIIII', body, 0)
        sections, o = [], 0x20
        for _ in range(count):
            (off, size, kind, idx, hashed, sha, enc, kidx, ividx,
             comp) = struct.unpack_from('>QQIIIIIIII', body, o)
            sections.append(dict(offset=off, size=size, kind=kind,
                                 program=idx, hashed=hashed, sha=sha,
                                 encrypted=enc, key=kidx, iv=ividx,
                                 compressed=comp))
            o += 0x30
        pool = [body[o + 0x10 * i:o + 0x10 * (i + 1)] for i in range(keys)]
        return dict(signature_input=siglen, section_count=count,
                    key_count=keys, opt_header_size=opt,
                    sections=sections, keys=pool, key=key, iv=iv, body=body)

    def sections(self, meta: dict):
        """Each metadata section's bytes, decrypted and decompressed."""
        for s in meta['sections']:
            raw = self.buf[s['offset']:s['offset'] + s['size']]
            if s['encrypted'] == ENCRYPTED:
                pool = meta['keys']
                if s['key'] >= len(pool) or s['iv'] >= len(pool):
                    raise ValueError('%s: section names key %d of %d'
                                     % (self.label, s['key'], len(pool)))
                raw = ctr_crypt(pool[s['key']], pool[s['iv']], raw)
            if s['compressed'] == COMPRESSED:
                raw = zlib.decompress(raw)
            yield s, raw

    def elf_bytes(self, meta: dict) -> bytes:
        """The ELF, rebuilt: the header and the program table out of the
        clear part of this file, and each segment at the offset its own
        program header names."""
        e = self.ehdr()
        phdrs = self.phdrs()
        end = max([e['ehsize'], e['phoff'] + e['phnum'] * e['phentsize']]
                  + [p['offset'] + p['filesz'] for p in phdrs])
        out = bytearray(end)
        out[0:e['ehsize']] = self.buf[self.elf:self.elf + e['ehsize']]
        n = e['phnum'] * e['phentsize']
        out[e['phoff']:e['phoff'] + n] = self.buf[self.phdr:self.phdr + n]
        for s, raw in self.sections(meta):
            if s['kind'] != 2 or s['program'] >= len(phdrs):
                continue
            p = phdrs[s['program']]
            out[p['offset']:p['offset'] + len(raw)] = raw
        return bytes(out)


# --------------------------------------------------------------------------
# the key file

Keyset = collections.namedtuple('Keyset',
                                'name kind revision self_type erk riv')
RPCS3 = re.compile(
    r'sk_(\w+?)_arr\.emplace_back\(\s*([0-9A-Fa-fx]+)\s*,\s*'
    r'([0-9A-Fa-fx]+)\s*,\s*([0-9A-Fa-fx]+)\s*,\s*KEY_(\w+)\s*,\s*'
    r'"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]*)"')
KINDS = {v: k for k, v in SELF_TYPES.items()}


def keysets(path) -> list:
    """Every key set a file offers, in either of the two formats."""
    text = pathlib.Path(path).read_text(encoding='utf-8', errors='replace')
    out = [Keyset('rpcs3 %s' % m.group(1), 'SELF', int(m.group(4), 16),
                  KINDS.get(m.group(5).replace('UNK7', 'UNK_7'), 0),
                  bytes.fromhex(m.group(6)), bytes.fromhex(m.group(7)))
           for m in RPCS3.finditer(text)]
    if out:
        return out
    name, cur = '', {}
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if line.startswith('[') and line.endswith(']'):
            if cur.get('erk'):
                out.append(_ini(name, cur))
            name, cur = line[1:-1], {}
        elif '=' in line:
            k, v = line.split('=', 1)
            cur[k.strip().lower()] = v.strip()
    if cur.get('erk'):
        out.append(_ini(name, cur))
    return out


def _ini(name: str, cur: dict) -> Keyset:
    return Keyset(name, cur.get('type', '').upper(),
                  int(cur.get('revision', '0'), 16),
                  KINDS.get(cur.get('self_type', '').upper(), 0),
                  bytes.fromhex(cur['erk']), bytes.fromhex(cur['riv']))


def pick(sets: list, revision: int, self_type: int) -> Keyset:
    got = [k for k in sets
           if k.revision == revision and k.self_type == self_type]
    if not got:
        raise SystemExit(
            'no key set for revision %#06x, self type %s (%d). The file '
            'offers: %s' % (revision, SELF_TYPES.get(self_type, '?'),
                            self_type,
                            ', '.join(sorted({'%#06x/%s' % (
                                k.revision, SELF_TYPES.get(k.self_type, '?'))
                                for k in sets})) or 'nothing'))
    return got[0]


def load(path) -> bytes:
    return pathlib.Path(path).read_bytes()


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    n = collections.Counter(data)
    return -sum(c / len(data) * math.log2(c / len(data)) for c in n.values())


# --------------------------------------------------------------------------
# the commands

def cmd_header(path) -> int:
    s = Sce(load(path), str(path))
    print('%s  %d bytes' % (path, len(s.buf)))
    print('  SCE     version %#x  key_revision %#06x  header_type %d'
          % (s.version, s.key_revision, s.header_type))
    print('          metadata %#x  header_len %#x  data_len %#x'
          % (s.meta, s.header_len, s.data_len))
    print('  SELF    appinfo %#x  elf %#x  phdr %#x  shdr %#x'
          % (s.appinfo, s.elf, s.phdr, s.shdr))
    print('          section_info %#x  sceversion %#x  control %#x (%#x)'
          % (s.sinfo, s.scever, s.ctrl, s.ctrl_size))
    print('  APPINFO auth id %#x  vendor %#x  self_type %d (%s)  version %#x'
          % (s.authid, s.vendor, s.self_type,
             SELF_TYPES.get(s.self_type, '?'), s.app_version))
    e = s.ehdr()
    print('  ELF     %d-bit %s-endian  machine %d  entry %#x  %d segments'
          % (64 if s.elf64 else 32, 'big' if e['big'] else 'little',
             e['machine'], e['entry'], e['phnum']))
    infos = s.segment_infos()
    print('  segment   type   vaddr        filesz     memsz    in this file')
    for i, (p, si) in enumerate(zip(s.phdrs(), infos)):
        print('    %2d      %4d   %#12x  %9d %9d   %#x %s'
              % (i, p['kind'], p['vaddr'], p['filesz'], p['memsz'],
                 si['offset'], 'zlib' if si['compressed'] else ''))
    return 0


def cmd_check(path) -> int:
    """Everything that can be established without a key."""
    ok = True

    def note(what, good, detail=''):
        nonlocal ok
        ok = ok and good
        print('  %-46s %s %s' % (what, 'yes' if good else 'NO', detail))

    for what, good in self_test():
        note(what + ' matches the published vector', good)
    s = Sce(load(path), str(path))
    note('the file is a SELF', s.header_type == 1)
    note('its key set is named', True, 'revision %#06x, self type %s'
         % (s.key_revision, SELF_TYPES.get(s.self_type, '?')))
    e = s.ehdr()
    note('an ELF header sits in the clear at %#x' % s.elf,
         e['ehsize'] in (52, 64),
         '%d-bit %s-endian, machine %d'
         % (64 if s.elf64 else 32, 'big' if e['big'] else 'little',
            e['machine']))
    phdrs, infos = s.phdrs(), s.segment_infos()
    note('the program table is in the clear too', len(phdrs) == e['phnum'],
         '%d segments' % len(phdrs))
    # the metadata starts where the header says and the first payload starts
    # where the metadata ends - which is the arithmetic that says the offsets
    # are being read in the right order.
    first = min((i['offset'] for i in infos if i['size']), default=0)
    note('the header ends where the first payload begins',
         s.header_len == first, '%#x against %#x' % (s.header_len, first))
    note('every payload lies inside the file',
         all(i['offset'] + i['size'] <= len(s.buf) for i in infos))
    note('the payloads account for data_len',
         sum(i['size'] for i in infos) <= s.data_len,
         '%d of %d bytes' % (sum(i['size'] for i in infos), s.data_len))
    biggest = max(infos, key=lambda i: i['size'])
    sample = s.buf[biggest['offset']:biggest['offset'] + 0x100000]
    h = entropy(sample)
    note('the biggest payload is encrypted, not merely packed', h > 7.9,
         'byte entropy %.3f of 8' % h)
    head = s.buf[s.elf:s.elf + 0x100]
    note('and the header above it is not', entropy(head) < 6.0,
         'byte entropy %.3f' % entropy(head))
    print('%s' % ('all of it holds' if ok else 'something above is wrong'))
    return 0 if ok else 1


def cmd_keys(path, revision='', self_type='') -> int:
    sets = keysets(path)
    print('%d key sets in %s' % (len(sets), path))
    want_r = int(revision, 16) if revision else None
    want_t = (int(self_type) if self_type.isdigit()
              else KINDS.get(self_type.upper())) if self_type else None
    for k in sets:
        if want_r is not None and k.revision != want_r:
            continue
        if want_t is not None and k.self_type != want_t:
            continue
        print('  %-14s revision %#06x  self type %-6s  erk %d bytes  '
              'riv %d' % (k.name, k.revision,
                          SELF_TYPES.get(k.self_type, '?'),
                          len(k.erk), len(k.riv)))
    return 0


def cmd_meta(path, keyfile) -> int:
    s = Sce(load(path), str(path))
    k = pick(keysets(keyfile), s.key_revision, s.self_type)
    m = s.metadata(k.erk, k.riv)
    print('%s, with %s' % (path, k.name))
    print('  the metadata decrypted: %d sections, %d keys, opt header %d'
          % (m['section_count'], m['key_count'], m['opt_header_size']))
    print('  signature input length %#x' % m['signature_input'])
    print('  section  kind        offset       size  enc  zlib  key iv  prog')
    for sec in m['sections']:
        print('    %-6s %-10s %#10x %9d  %3s %5s  %3d %2d %5d'
              % (SECTION_KIND.get(sec['kind'], sec['kind']),
                 'program %d' % sec['program'] if sec['kind'] == 2 else '',
                 sec['offset'], sec['size'],
                 'yes' if sec['encrypted'] == ENCRYPTED else 'no',
                 'yes' if sec['compressed'] == COMPRESSED else 'no',
                 sec['key'], sec['iv'], sec['program']))
    return 0


def cmd_decrypt(path, keyfile, out) -> int:
    s = Sce(load(path), str(path))
    k = pick(keysets(keyfile), s.key_revision, s.self_type)
    m = s.metadata(k.erk, k.riv)
    blob = s.elf_bytes(m)
    pathlib.Path(out).write_bytes(blob)
    e = s.ehdr()
    print('%s -> %s' % (path, out))
    print('  %d bytes, %d segments, entry %#x' % (len(blob), e['phnum'],
                                                  e['entry']))
    for i, p in enumerate(s.phdrs()):
        got = blob[p['offset']:p['offset'] + min(p['filesz'], 0x100000)]
        print('    segment %2d  %#12x  %9d bytes  entropy %.3f'
              % (i, p['vaddr'], p['filesz'], entropy(got)))
    print('  it is an ELF: %r, machine %d'
          % (blob[:4], e['machine']))
    return 0


AIT = b'AIT_'
AIT_STRIDE = 24
PAIR = 8                  # the predicate table's record: two big-endian u32


def _cstr(blob: bytes, o: int, cap: int = 64) -> str:
    end = blob.find(b'\0', o, o + cap)
    if end < 0:
        return ''
    text = blob[o:end]
    return text.decode('ascii') if all(32 <= c < 127 for c in text) else ''


def ait_table(blob: bytes) -> list:
    """The `AIT_*` condition-term enum: fixed-width slots, one run of them.

    The names are padded to a 24-byte slot, so the table is found by its
    first entry and walked until a slot stops being one.
    """
    at = blob.find(AIT)
    if at < 0:
        return []
    while at >= AIT_STRIDE and blob[at - AIT_STRIDE:].startswith(AIT):
        at -= AIT_STRIDE
    out, o = [], at
    while True:
        slot = blob[o:o + AIT_STRIDE]
        if not slot.startswith(AIT):
            break
        out.append(slot.split(b'\0')[0].decode('ascii', 'replace').strip())
        o += AIT_STRIDE
    return out


def pointer_table(blob: bytes, base: int, anchor: bytes) -> list:
    """A run of `(u32, u32)` records whose second word points at a name.

    `anchor` is a name known to be in the pool, which is how the pool is
    located without a symbol table. The stride falls out of the data.
    """
    at = blob.find(anchor)
    if at < 0:
        return []
    lo = at
    while lo > 0 and (blob[lo - 1] == 0 or 32 <= blob[lo - 1] < 127):
        lo -= 1
    hi = at + len(anchor)
    while hi < len(blob) and (blob[hi] == 0 or 32 <= blob[hi] < 127):
        hi += 1
    pool = range(lo + base, hi + base)

    def named(o: int) -> bool:
        """Does the record at `o` point its second word into the pool?"""
        if not 0 <= o <= len(blob) - PAIR:
            return False
        return struct.unpack_from('>I', blob, o + 4)[0] in pool

    # Find the word that points at the anchor, aligned, and step back to the
    # start of its own record - the anchor is the *second* word of one.
    want = struct.pack('>I', at + base)
    o = -1
    for k in range(0, len(blob) - 4, 4):
        if blob[k:k + 4] == want and named(k - 4):
            o = k - 4
            break
    if o < 0:
        return []
    while named(o - PAIR):
        o -= PAIR
    out = []
    while named(o):
        fn, name = struct.unpack_from('>II', blob, o)
        out.append((fn, _cstr(blob, name - base)))
        o += PAIR
    return out


def cmd_names(path) -> int:
    """The two AI tables, out of a decrypted ELF."""
    blob = load(path)
    if blob[:4] != b'\x7fELF':
        raise SystemExit('%s is not an ELF - run `decrypt` first' % path)
    # segment 0 of this build is loaded at 0x10000 from file offset 0, and
    # `header` prints that pairing for any other.
    base = 0x10000
    ait = ait_table(blob)
    print('%d AIT_* condition-term names' % len(ait))
    # The disc numbers its terms in bands - 1.., 101.., 201.., 1001.. - and
    # the enum is those bands end to end. The band sizes are the disc's, and
    # that the three lower ones are 21, 19 and 25 on both sides is the join.
    bands, k = [(1, 21), (101, 19), (201, 25)], 0
    for start, n in bands:
        for i in range(n):
            if k < len(ait):
                print('  %#05x  %s' % (start + i, ait[k]))
            k += 1
    for name in ait[k:]:
        print('  %-5s  %s' % ('boss', name))
    table = pointer_table(blob, base, b'getAngleTypeToTarget\0')
    print('%d AI host predicates, as (function, name) pairs' % len(table))
    for fn, name in table:
        print('  %#010x  %s' % (fn, name))
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    try:
        if cmd == 'header' and len(rest) == 1:
            return cmd_header(*rest)
        if cmd == 'check' and len(rest) == 1:
            return cmd_check(*rest)
        if cmd == 'keys' and 1 <= len(rest) <= 3:
            return cmd_keys(*rest)
        if cmd == 'meta' and len(rest) == 2:
            return cmd_meta(*rest)
        if cmd == 'decrypt' and len(rest) == 3:
            return cmd_decrypt(*rest)
        if cmd == 'names' and len(rest) == 1:
            return cmd_names(*rest)
    except ValueError as exc:
        print('error: %s' % exc)
        return 1
    print(__doc__)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
