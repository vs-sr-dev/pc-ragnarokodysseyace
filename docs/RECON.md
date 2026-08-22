# Ragnarok Odyssey ACE — disc reconnaissance

Reference disc: **Ragnarok Odyssey ACE (USA)**, `NPWR04119_00`, 5.79 GB image,
decrypted. Everything below was derived from the disc itself with the tools in
[`../tools/`](../tools); nothing was taken from an external database.

---

## 1. The medium

A PS3 Blu-ray: UDF 2.50 with a **metadata partition**, plus a shadow ISO9660
filesystem whose names are truncated to 31 characters. Extraction goes through
UDF for the same reason it did on the sister project — names are data, and the
CPK table of contents keys on them.

`tools/iso.py` is the UDF reader, inherited from PC-3Ddot and corrected here
for one real defect (§2).

## 2. The index records every extent

A UDF `long_ad` carries at most `2^30 - 1` bytes, so any file past 1 GiB is
necessarily split across several extents. On this disc `sound.cpk` is 1.24 GB
and is cut at `0x3FFFF800` — the largest 2048-byte multiple below 2^30.

The inherited index format stored one LBA per file. That does not fail loudly:
it reads 1.24 GB contiguously from the first LBA and writes a **silently
corrupt file**. The index now stores the full extent list (`lba:bytes,...`).

On 3D Dot Game Heroes the bug was invisible because no single file crossed the
boundary. It is the kind of defect that only a disc with a bigger file exposes.

## 3. Inventory

**109 files, 5.4 GB.** That is the whole UDF tree — this is not a disc with an
asset directory on it.

| set | files | bytes | contents |
|---|---:|---:|---|
| `archive` | 20 | 1.7 GB | CRI CPK containers — the whole game |
| `patch` | 14 | 141.6 kB | patch CPKs, 10,360-byte stubs |
| `boot` | 2 | 18.9 MB | `EBOOT.BIN`, `PARAM.SFO` |
| `image` | 21 | 2.9 MB | loose PNG icons |
| `audio` | 1 | 266.1 kB | `SND0.AT3`, the XMB jingle |
| `movie` | 46 | 3.4 GB | PAMF video |

Undeclared on purpose: `PS3UPDAT.PUP`, `TROPHY.TRP`, `LICDIR/LIC.DAT`,
`PS3LOGO.DAT`, `PS3_DISC.SFB` — platform infrastructure.

**The `.cpk.patch` files are all exactly 10,360 bytes** and share the first
0x50 bytes with a real CPK: they are empty containers, placeholders for a title
update that overlays entries onto the base archive. There are 14 of them for
20 containers; `loadbg`, `mercenary`, `motif`, `npc`, `sound_add` and
`trophy_title` have none.

## 4. `EBOOT.BIN`

`SCE\0`, header version 2, **`key_revision 0x001C`**, header type 1 (SELF),
metadata at `0x410`, ELF image 19.8 MB. Decrypting it to a PPC64 big-endian ELF
is Phase 3; retail keys for this revision are public.

Note for when it is opened: this is a PS Vita game ported to PS3, and the port
left traces (§7). Structures in the EBOOT should match the ones inferred from
the file formats.

## 5. Four levels of nesting

```
    ISO (UDF)  ->  109 files
      20 x CPK (CRI, @UTF tables, CRILAYLA compression)  ->  2,450 entries
        nested CPK (6, all inside character.cpk)
          1,544+ x ARC  ->  13,820 entries at the first level
            cmp/lzma and cmp/zlib blocks, which may hold any of the above
              32,727 leaves, 2.0 GB
```

`tools/assets.py` walks all four and hands out one path per leaf. Depth runs to
six levels: `character.cpk/motion.cpk/com.pac/com.mkc.pac/com051emo_1.mkc`.

Writing the tree to disk loses 127 of the 32,727, because leaves can share a
path — an ARC may expose one block under several names. The iterator is the
authority; the directory is a convenience.

### 5.1 CPK — solved

Standard CRI CPK: `CPK ` header packet, `TOC ` index, big-endian `@UTF` tables,
`CRILAYLA` LZ for compressed entries. `tools/cpk.py` reads all 20 containers
and all 2,450 entries. See the module docstring for the format.

| container | entries | size | notes |
|---|---:|---:|---|
| `sound.cpk` | 64 | 1.2 GB | CRI Atom: 62 `.acb`, 1 `.awb`, 1 `.acf` |
| `stage.cpk` | 595 | 314.4 MB | 577 `.pac`, 18 `.acb` |
| `monster.cpk` | 689 | 136.0 MB | 83 `.json`, 358 `.pac`, 41 `.acb` |
| `character.cpk` | 6 | 102.5 MB | **six nested CPKs** |
| `card.cpk` | 185 | 33.8 MB | all CTEX under numeric names |
| `menu.cpk` | 78 | 30.0 MB | 47 CTEX, 28 `.pac` |
| `motif.cpk` | 125 | 10.9 MB | 124 CTEX + 1 ECH table |
| `sound_add.cpk` | 2 | 9.6 MB | one Atom pair |
| `job.cpk` | 36 | 7.8 MB | **6 player classes**, 6 `.json` |
| `misc.cpk` | 15 | 5.4 MB | includes `rh_font_en.otf` |
| `npc.cpk` | 26 | 5.6 MB | |
| `quest.cpk` | 432 | 5.4 MB | one `.pac` per quest |
| `demo.cpk` | 135 | 4.8 MB | cutscenes: 69 `.pac`, 42 CTEX, 20 `.psq` |
| `loadbg.cpk` | 21 | 1.1 MB | loading screens |
| `item.cpk` | 4 | 1.2 MB | the item database |
| `mercenary.cpk` | 13 | 371.9 kB | |
| `yggdrasill.cpk` | 20 | 419.4 kB | the endless-dungeon tables |
| `dictionary.cpk` | 2 | 81.8 kB | the in-game encyclopedia |
| `tmline.cpk` | 1 | 6.7 kB | |
| `trophy_title.cpk` | 1 | 15.4 kB | |

### 5.2 ARC — solved

`tools/arc.py`: **1,544 files out of 1,544 read consistently**, 13,820 entries.
Two things had to be worked out rather than read:

- the stride of a directory entry is `align32(16 + name length)`, so a short
  name produces a 32-byte entry instead of 64;
- the two counts in the header are **entries** and **blocks**, not the same
  number: several entries may alias one block under different resource ids.
  22 such aliases exist on the disc, all in `monster.cpk::pac/*.pac` — in
  `b01.pac` the animation `b01519at11.CNOM` is exposed under seven ids.

### 5.3 The block header

Every ARC block carries 0x20 bytes in front: the payload size as a big-endian
`u32`, then twenty-eight zeros. Across **13,798 blocks out of 13,798**,
`align32(0x20 + size)` equals the block length exactly. The format declares its
own size and the declaration is consistent everywhere — nothing to guess.

## 6. Leaf formats

By type tag on the ARC directory entries:

| tag | n | what |
|---|---:|---|
| `bin` | 7,621 | mostly `ECH` tables and `ELBN` |
| `psq` | 2,973 | sequences (§6.2) |
| `nom` | 1,576 | `CNOM`, motion |
| `tex` | 518 | `CTEX`, texture |
| `pac` | 348 | nested `ARC` |
| `trg` | 164 | triggers |
| `col` | 156 | `CCLS`, collision |
| `map` | 138 | |
| `mdl` | 130 | model |
| `scn` / `scm` | 81 / 78 | `CSCN` / `CSCM`, camera scenes |
| `PTP` | 18 | effects |
| `mtm` / `mkc` / `txt` | 12 / 6 / 1 | |

Magic naming follows a `C` + three-letter convention: `CTEX` texture, `CNOM`
motion, `CSCN` scene, `CSCM` scene motion, `CCLS` collision.

### 6.1 `ECH` — the game database  ⟵ solved

4,941 files, 58,534 rows, 0 failures. Full write-up in
[`format_ech.md`](format_ech.md). It is the item, weapon, card, skill, quest,
reward, stage, shop and encyclopedia data, and it is now readable.

Two things make it work. The header ends with a **full-width default row**
(`header size` is always `0x18 + row size`), and 2,730 of the tables carry a
NUL-separated **string pool** after the last row that the rows address by byte
offset — which is where quest data keeps its room names, spawn markers and
script hooks.

There is no type descriptor, so column types have to be inferred. The trap is
that a four-byte lane is frequently four packed `u8`s: `chapter.bin` column 0
reads as 0, 33554431, 65793, 33554431 until you look at the bytes and find a
variant record keyed on its first one.

### 6.2 `.psq` — the cutscene language

Payload begins `FA FA 'SQIR'`, then `PART` chunks, and carries its own source
filename: `010_01_01.psq.**ppcut**`. 2,973 of them. This is the compiled form
of a sequence/cutscene script — functionally the same role Lua plays on
3D Dot Game Heroes, except compiled rather than in source.

### 6.3 `.json` — plain, pretty-printed, and central

**89 JSON files**: 6 in `job.cpk` (one per player class) and 83 in
`monster.cpk` (one per monster). They are the character physics and combat
parameters, uncompressed and human-readable:

```
"col_r": 0.5, "weight": 50, "acc": 0.035, "run_sp": 0.17,
"rot_y_acc": 8, "rot_y_spd": 32, "aerial_deg": 112,
"stg_p": [7, 40, 80, 100], "stun_f": [90, 0], ...
```

Movement acceleration, run speed, turn rate, hit-stop windows, stagger
thresholds. On a reimplementation these are the numbers that decide whether the
game *feels* right, and they are handed over in plain text.

### 6.4 Text  ⟵ solved

`.rmsg` carries a `TXT` magic: 76 files, 25,288 messages, 0 failures. Full
write-up in [`format_rmsg.md`](format_rmsg.md).

Records are **variable length** — 16 bytes plus 12 per optional attribute — and
a fixed stride reads three hundred names correctly before drifting, which is
the quiet kind of wrong. The attributes are presentation markup: type 0 holds
RGBA colours (`0xff0000ff` pure red, `0x969696ff` neutral grey), type 3 holds
horizontal scale factors that are all multiples of 1/11.

They pair positionally with the `ECH` tables — `it_db_weapon.bin` has 450 rows
and `it_db_name_weapon.rmsg` 450 messages, row *n* to message *n*, on all seven
pairs checked. That is how a table row gets a name.

### 6.5 `CTEX` — reconnoitred, not yet solved

11,536 files, the largest population on the disc. A 16-byte header, then the
payload:

```
0x00  'CTEX'
0x04  u32   payload size          w1 + 16 == file length on 11,536 of 11,536
0x08  u32   0x00010005            constant
0x0C  u32   zero
--- payload ---
0x10  u16   0x1000  |  u16 height     powers of two, 32..1024
0x14  u16   width   |  u16 format     powers of two, 16..512
0x18  u32   flags
0x1C  u32   mip / flags   0x1010000, 0x1040000, 0x1050000, 0
0x20  ...   48 more bytes of sub-header, then the pixels
```

The pixel formats fall out of the arithmetic. Where a texture has no mip chain,
`payload - 80` equals `width * height * bpp` **exactly**:

| format | bpp | exact matches |
|---|---|---:|
| `0x109` | 0.5 | 1,809 — DXT1 |
| `0x10F` | 1.0 | 141 — DXT5 |
| `0x100` | 4.0 | 400 — uncompressed 32-bit, and *all* 400 files of this format match |
| `0x107` | 2.0 | 6 — 16-bit |

The remaining 9,180 carry mip chains, and the chain layout is the open
question: a 128x32 DXT1 with `w7 = 0x1050000` occupies 2,560 bytes, which is
the base level plus exactly one more, not the full chain a renderer would
normally expect.


### 6.6 Other layers

- `cmp` — a compression wrapper that names its own codec in the magic:
  `cmp NUL lzma` (154 blocks) and `cmp NUL zlib` (3,077 blocks, 282 MB). Both
  sit *under* CRILAYLA, so a file can be compressed twice. The header is
  `magic, u32 compressed size, u32 uncompressed size, stream`; the LZMA stream
  is LZMA1 carrying its properties but not the size field the "alone"
  container expects, so the declared size is spliced back in.
- `ELBN` — 244 blocks, `objbin.bin` / `stobjbin.bin` / `dc_demo_data.bin`.
  Header is `magic, u32, u32 0x00010000` then a table of `u32` triples.
  Unresolved.
- `ATIH` — `hta.bin` in the stage parameter archives. Read as a little-endian
  FourCC this is `HITA`, most likely hit-area data.
- `rh_font_en.otf` — an **ordinary OpenType font**, no work needed.
- CRI Atom (`.acb` / `.awb` / `.acf`) for all audio; these are `@UTF` tables
  too, so `cpk.py`'s reader already parses their structure.
- PAMF video: MPEG-4 AVC in a Sony container.

## 7. The Vita port shows

Ragnarok Odyssey ACE is the PS3 edition of a PS Vita game, and the port kept
little-endian conventions in places: FourCCs like `ATIH` and `ELBN` read
backwards on a big-endian read, while the CPK header packets keep their sizes
in little-endian even though the `@UTF` payloads are big-endian. Worth
remembering before declaring a field "wrong".

## 8. Open questions

- `ECH` column descriptors: the per-column bytes read as zero in both samples,
  so the field types are not obviously declared. Row widths are exact, so the
  layout is recoverable — but by inference, not by reading.
- `ELBN` — unidentified.
- `.psq` opcode set — the `SQIR` chunk language.
- `.PTP` effects, `.trg` triggers, `.mtm`, `.mkc`.
- Whether the six nested CPKs in `character.cpk` are per-class or per-gender.
- `CTEX` pixel formats — PS3 RSX texture layouts, possibly swizzled.
