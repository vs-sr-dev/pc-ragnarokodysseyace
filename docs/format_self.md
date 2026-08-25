# `SELF` — the EBOOT, and how it opens

*Read by [`self.py`](../tools/self.py). Session 30.*

`PS3_GAME/USRDIR/EBOOT.BIN` is 19,860,160 bytes and it is the last unread
file on the disc. Everything else — 26 formats, 3,011 scripts, 707 parameter
blobs — has been read for thirty sessions around it.
[`STRATEGY.md`](STRATEGY.md)'s phase 3 is opening it and
[`parity.md`](parity.md) says why: **three of the seven stand-ins in the
engine are one function that lives in here**.

```
python tools/self.py check   extract/PS3_GAME/USRDIR/EBOOT.BIN
python tools/self.py header  extract/PS3_GAME/USRDIR/EBOOT.BIN
python tools/self.py meta    extract/PS3_GAME/USRDIR/EBOOT.BIN <keys>
python tools/self.py decrypt extract/PS3_GAME/USRDIR/EBOOT.BIN <keys> eboot.elf
python tools/self.py names   eboot.elf
```

## Half the file is in the clear, and that half is worth having

A `SELF` is an ELF wrapped in Sony's signed container. The wrapper is
plaintext; only the segment payloads are encrypted. So before any key is
involved:

```
$ python tools/self.py header extract/PS3_GAME/USRDIR/EBOOT.BIN
  SCE     version 0x2  key_revision 0x001c  header_type 1
          metadata 0x410  header_len 0x980  data_len 0x12f0140
  SELF    appinfo 0x70  elf 0x90  phdr 0xd0  shdr 0x12f02c0
  APPINFO auth id 0x1010000001000003  vendor 0x1000002  self_type 4 (APP)
  ELF     64-bit big-endian  machine 21  entry 0xfd01e8  8 segments
```

Machine 21 is `EM_PPC64`. The two segments that matter are **16,141,416 bytes
of code at `0x10000`** and **3,652,220 of data at `0xf80000`**; the other six
are empty or a handful of bytes.

`check` is the arithmetic, and it needs no key either:

```
  the header ends where the first payload begins  yes  0x980 against 0x980
  the biggest payload is encrypted, not merely packed  yes  byte entropy 8.000
  and the header above it is not                 yes  byte entropy 1.878
```

**8.000 of a possible 8** settles the one question that could have made the
whole phase unnecessary: the segments are genuinely encrypted and not merely
packed, so there is no way in that does not go through a key.

## The chain, end to end

```
    the key set        (key_revision, self_type) -> erk, riv
      -> METADATA_INFO   AES-256-CBC, 0x40 bytes at metadata + 0x20
      -> a key and an iv of their own
      -> METADATA_HEADERS  AES-128-CTR to the end of the header
      -> a header, N section headers and M sixteen-byte keys
      -> each segment      AES-128-CTR, its own key and iv out of those M
      -> zlib, where the section header says so
      -> an ELF, reassembled at the program table's own offsets
```

Two things about that chain are worth stating because both were open
questions before it ran.

**The container is signed *and* encrypted, and only the second is in the
way.** The ECDSA signature over the header is never checked here: nothing
downstream of a decryption cares whether the file is authentic, and this is a
disc the user already owns.

**The metadata says whether the key is right, without a hash.** `METADATA_INFO`
is a 16-byte key and a 16-byte iv, each followed by **16 bytes of zero**. A
wrong key set produces noise in those pads, so `self.py` refuses rather than
handing on 19 MB of garbage:

```
metadata did not decrypt - the padding either side of the key is not zero,
so this is the wrong key set
```

```
$ python tools/self.py meta ... 
  the metadata decrypted: 7 sections, 52 keys, opt header 48
  section  kind        offset       size  enc  zlib  key iv  prog
    phdr   program 0       0x980  16141416  yes    no    6  7     0
    phdr   program 1    0xf70980   3652220  yes    no   14 15     1
```

Neither of the two real segments is compressed, which is why the decrypted
ELF is the same size as the SELF to within the header.

## What comes out

```
$ python tools/self.py decrypt ... eboot.elf
  19839612 bytes, 8 segments, entry 0xfd01e8
    segment  0       0x10000   16141416 bytes  entropy 5.945
    segment  1      0xf80000    3652220 bytes  entropy 5.405
```

Entropy 8.000 to **5.945** is the answer, and the instruction census is a much
sharper one, because nothing but real code produces it:

```
  and it is PowerPC: mflr r0 49283, mtlr r0 49765, blr 62627, nop 112475
     4035354 words; mflr and mtlr differ by 482
```

`mflr r0` opens a PowerPC function that calls anything and `mtlr r0` closes
it, so **the two counts have to come out close together** — and they do, 49,283
against 49,765 over four million words, with 62,627 `blr` under them. A wrong
key, a wrong counter or an off-by-one in the reassembly gives noise, and noise
does not produce fifty thousand matched prologues. The primary-opcode
histogram is the PowerPC64 one too: 31 (the integer group), 14 (`addi`), 18
(`b`), 58 (`ld`), 32 (`lwz`), 62 (`std`).

The file also names itself: `Squirrel 2.2.4 stable`, `objbin.cpp`,
`se_hitlevel_tbl`, `cfMapJump`, `printAitIdName`, `checkB01Term`. Every one of
those is a string some earlier session inferred the existence of from the
outside.

`Squirrel 2.2.4 stable` in particular is [`format_psq.md`](format_psq.md)'s
central reading, printed by the build itself.

## The keys are not here, and the tool is arranged so they need not be

`erk` and `riv` have exactly the standing the ISO has: not game content, not
derivable from the disc, and not this repository's to hand on. `self.py`
therefore takes **a path to a key file** and reads the two formats anyone
doing this already has — scetool's `data/keys` ini and RPCS3's
`key_vault.cpp`, whose `sk_*_arr.emplace_back(...)` lines carry the same
fields positionally. `self.py keys <file> [revision] [type]` says whether a
given file has what this disc wants.

This disc wants `key_revision 0x001C`, `self_type APP`.

## The AES is in the file

This repository has no third-party dependency in any of its tools and this one
does not add the first. FIPS-197's cipher and inverse cipher, CBC decryption
and CTR are about a hundred and forty lines of
[`self.py`](../tools/self.py), and `self.py check` runs them against the
standard's own vectors before it looks at the disc at all:

```
  AES-128 encrypt matches the published vector   yes
  AES-128 decrypt matches the published vector   yes
  AES-256 encrypt matches the published vector   yes
  AES-256 decrypt matches the published vector   yes
  AES-128 CTR matches the published vector       yes
```

A cipher written from scratch that is not checked against a vector is a
cipher that produces plausible garbage, which is the one failure mode this
whole phase could not afford. It costs 37 seconds of pure Python to decrypt
19.8 MB, which is once.

## What it gave up first, before any disassembler

Two tables, both of which were on the phase-3 list *by name*, and both of
which are plain data rather than code — `self.py names` extracts them from
the decrypted ELF in under half a second.

**The `AIT_*` condition-term enum**, 78 names on a 24-byte stride. This is
the string table `printAitIdName` prints from, and it is what
[`format_ai.md`](format_ai.md) has wanted since session 18. See that document
for what it settled: **65 of the 76 term ids the disc's tables use get the
engine's own name**, every one of them agrees with the reading taken off the
`.cnut`, and the eleven it does not name are the ten the `.cnut` could not
name either, plus one.

**The AI host predicate table**, 75 `(function, name)` pairs — the vocabulary
a monster's rules are written against, including the seven `checkBnnTerm`
escape hatches that nothing on the disc defines, now located as B01, B05,
B09, B11, B15, B18 and B19.

## What is left, and it is the disassembler's

Everything in [`combat_loop.md`](combat_loop.md)'s ledger that says *EBOOT* is
code, not data: the damage expression, what computes the hit level, what
`+0x35` is a strength of, the sign of a region's flat modifier, and what
`react_p` is a pool of. Those want Ghidra with the PowerPC 64 big-endian
language, an image based at `0x10000`, and the 285 `cf*`/`sf*` names as the
first thing to plant — the script interface is the widest labelled surface
this binary has, and [`format_api.md`](format_api.md) already knows what each
of them does from the outside.
