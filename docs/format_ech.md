# `ECH` — the table format

**Status: solved.** 4,941 files, 58,534 rows, 0 failures. Reader:
[`../tools/ech.py`](../tools/ech.py).

This is the game's database. Items, weapons, cards, skills, monsters, quests,
rewards, stages, shop recipes, the endless dungeon, the encyclopedia — all of
it is `ECH`, and all of it is now readable.

## Layout

```
0x00  'ECH' NUL
0x04  u32   header size
0x08  u32   zero, on every file on the disc
0x0C  u32   0x92, the format version, on every file on the disc
0x10  u32   number of rows
0x14  u32   row size in bytes
0x18  byte[row size]   the default row
...   the rows
...   the string pool, when there is one
```

Everything is big-endian.

`header size` is always exactly `0x18 + row size`, so the fixed part of the
header is 24 bytes and what follows is **one full-width row**. It is usually
all zeros; where it is not, the non-zero fields read as sensible defaults —
`it_db_ability.bin` defaults its last word to `-150.0`. Treating it as a row
rather than as a block of column descriptors is what makes the arithmetic
close.

## The rows need not reach the end of the file

2,730 of the 4,941 tables carry a **string pool** after the last row; the other
2,211 end on it. The pool opens with a NUL so that offset 0 reads as the empty
string, and rows address it **by byte offset from the start of the pool**.

This is what makes text columns identifiable without guessing. A lane whose
every value lands either on 0 or immediately after a NUL inside the pool is a
string column, and the probability that a numeric column satisfies that by
accident falls off a cliff after a handful of rows. `ech.py` uses exactly that
test.

Reading the pool is also what turns quest data into something you can look at:

```
$ python tools/ech.py info extract/tree quest.cpk/q01005.pac/enemy_gen.bin
  97 rows of 60 bytes (15 words)
  string pool: 346 bytes, 33 strings

  col  off  type     distinct  evidence
    0    0  str             8  e.g. '040_01_01', '040_01_02'
    1    4  str            13  e.g. 'emgen_pos01', 'emgen_pos02'
    2    8  str            13  e.g. 'emgen01', 'emgen02'
   14   56  str             3  e.g. 'sfKill_Generator', 'sfKill_GeneratorB'
```

A room, a spawn marker, a generator name, and the script hook that fires when
it dies.

## There is no type descriptor

The format declares how wide a row is and nothing whatsoever about what is in
it. The consuming code in the EBOOT knows the struct; the file does not carry
it. So field types have to be **inferred**, and `ech.py` labels its answers as
hypotheses rather than asserting them.

### The inference that is easy to get wrong

**A four-byte lane is often not one field.** Many columns are four `u8`s or two
`u16`s packed together, and read as `u32` they produce impressive nonsense.
`quest.cpk/common.pac/chapter.bin` column 0 reads as

```
0, 33554431, 65793, 33554431, 66049, ...
```

until you look at the bytes:

```
00 00 00 00
01 FF FF FF
00 01 01 01
01 FF FF FF
00 01 02 01
```

which is a variant record keyed on its first byte, alternating between two
kinds of row. Nothing about the `u32` reading is *wrong* — the bytes are those
bytes — but it hides the structure completely.

So the classifier looks down each byte column as well as each word column, and
prefers the narrower reading when the wide one only looks busy because narrow
fields underneath it are moving independently. The rule it uses: if the widest
byte column has at most half as many distinct values as the word column does,
the word is four bytes and not one number.

### The tests, in order

1. one distinct value → `const`
2. every value lands in the string pool → `str`
3. every value below 65536 → `u32`, safely small
4. every value a plausible float **and at least one not whole** → `f32`
   (requiring a fractional value matters: small integers are also valid float
   bit patterns, and a column of 1, 2, 3 is not a column of denormals)
5. `-1` or `INT_MAX` appearing as a sentinel → `i32`
6. the byte-column test above → `u8 x4`
7. the same test on halves → `u16 x2`
8. otherwise `u32`

Where the evidence is thin the tool says so. A column with four distinct values
cannot be told apart from four packed bytes with one distinct value each, and
`ech.py` reports the distinct counts so a reader can see that for themselves.

## Names come from elsewhere

`ECH` holds no display text. The names live in the paired `TXT` files — see
[`format_rmsg.md`](format_rmsg.md) — and the pairing is positional:

| table | rows | message file | messages |
|---|---:|---|---:|
| `it_db_weapon.bin` | 450 | `it_db_name_weapon.rmsg` | 450 |
| `it_db_material.bin` | 411 | `it_db_name_material.rmsg` | 411 |
| `it_db_card.bin` | 1471 | `it_db_name_card.rmsg` | 1471 |
| `it_db_skill.bin` | 1091 | `it_db_name_skill.rmsg` | 1091 |
| `it_db_equip.bin` | 146 | `it_db_name_equip.rmsg` | 146 |
| `it_db_hg.bin` | 118 | `it_db_name_hg.rmsg` | 118 |
| `it_db_bgm.bin` | 237 | `it_db_name_bgm.rmsg` | 237 |

Row *n* of the table is message *n* of the file, on all seven checked. Put
together:

```
it_db_weapon.bin, first columns beside the name

  [  0]   10001    1   0   48   0   0     -1     -1     -1   'Katar'
  [  1]   10002    2   0   52   0   1     -1     -1     -1   'War Mace'
  [120]   10127   17   1   63   0   0 110294     -1     -1   'Eoh Bloody Roar'
  [449]   11204  112   0  155   0   7 111087 110266    609   'Fake Pole-Axe F'
```

Column 0 is the item id, and the six-figure values in columns 6–7 are ids into
`it_db_skill.bin`.

## Open

- What column 2 of the fixed header is for. It is zero on all 4,941 files, so
  the disc gives no evidence either way.
- The 33 distinct row widths run from 1 to 584 bytes. A one-byte row is a
  legitimate table of flags, but it has not been looked at.
- Field *semantics*. The types are inferable; the meanings are not, and this is
  where the EBOOT will eventually earn its keep — or where a careful reading of
  the names, as with `enemy_gen.bin` above, will make it unnecessary.

  The 69 `effect.bin` are the first tables whose columns are named end to end,
  and neither the EBOOT nor the type inference did it: the *consumers* did.
  `.mkc` addresses a row, a `.PTP` bank has to accept the pair the row holds,
  a `CMDL` locator table has to accept the id at `+0x04`, and a stage script
  declares the whole record in the clear. See
  [`format_effect.md`](format_effect.md). It is also a warning about the
  inference: `ech.py` reads the first four bytes of a motion row as one `u32`
  and they are four separate one-byte fields, two of which are an address.

  **And a field can be narrower than a byte.** `enemy.bin`'s monster slot is
  `01 hh h0 00`: a 12-bit id between a leading 1 and a trailing 0. The tell is
  free — the low nibble of the third byte is zero on all 2,503 filled slots —
  and it is what a byte histogram shows and a lane classifier cannot. Read as
  a `u32` the column is 82 numbers in the tens of millions; read as twelve bits
  it is 83 ids that name 83 `monster.cpk` directories exactly, with nothing
  left over on either side. See [`format_quest.md`](format_quest.md).

  The same file has two lanes at `+0x2c` that are **eight independent bytes**,
  one per monster slot, holding 99 where the slot is empty. Neither the width
  nor the sentinel is declared; both fall out of making the field agree with a
  column it has to agree with.
