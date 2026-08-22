# `TXT` / `.rmsg` — the message format

**Status: solved.** 76 files, 25,288 messages, 7,125 attributes, 0 failures.
Reader: [`../tools/rmsg.py`](../tools/rmsg.py).

Every string the player reads: item and monster names, item descriptions,
quest text, the encyclopedia. The `ECH` tables hold no display text, so these
are what give a table row a name — see [`format_ech.md`](format_ech.md).

## Layout

```
0x00  'TXT' NUL
0x04  u32   0x00010217, the format version, on all 76 files
0x08  u32   number of messages
0x0C  u32   zero
0x10        the message records
...         the string block, NUL-separated UTF-8
```

Big-endian throughout.

## The record is variable length

```
+0x00  u32   index, always the record's own position
+0x04  u32   offset of the text, counted from 0x10
+0x08  u32   0, 1 or 2 — see below
+0x0C  u32   number of attributes that follow
then, per attribute:
  +0x00  u32   attribute id
  +0x04  u32   value type
  +0x08  u32   the value
```

Most records are 16 bytes; those carrying one attribute are 28. This is the
only part of the format that has to be worked out rather than read, and
**getting it wrong is quiet rather than loud**. A fixed 16-byte stride reads
`it_db_name_material.rmsg` correctly for three hundred names —

```
Orc Claw / Broken Helmet / Cracked Staff / Chief's Helm / ...
```

— and then drifts, because record 300 is the first with an attribute. What you
see at that point looks like a corrupt tail rather than a wrong assumption at
the head, which is the failure mode worth remembering: 300 correct answers is
not evidence that a stride is right.

Of the 25,288 messages on the disc, 7,125 carry attributes.

`check` proves the walk instead of trusting it: the records must end at exactly
the byte where the first string begins, and the file must end on a NUL. Both
hold only if every record length was read correctly.

The offsets are counted from `0x10`, not from the start of the file — which is
also why the first message's offset doubles as the address of the string block.

### Word 2

A small number, the same for every record within a file: 0 in 37 files, 1 in
55, 2 in 30, and `0x10001` / `0x10002` in three more (so it is really two
`u16`s, the high one almost always zero). Because it never varies *within* a
file it is a property of the message set rather than of the message —
plausibly a font or text-box selector. Not identified.

## The attributes are text markup

The tool does not assert this; the value distribution does. Across the whole
disc:

| id | type | value | as float | count |
|---:|---:|---|---:|---:|
| 0 | 3 | `0x3f51745d` | 0.818182 | 4877 |
| 0 | 3 | `0x4051745c` | 3.27273 | 97 |
| 0 | 3 | `0x3fd17460` | 1.63636 | 82 |
| 0 | 0 | `0x969696ff` | — | 72 |
| 0 | 0 | `0xff0000ff` | — | 39 |
| various | 6 | `0x0` | — | ~300 |

Type 3 values are floats and they are all multiples of `1/11`: 9/11, 18/11,
36/11, each double the last. A horizontal scale factor.

Type 0 values are not floats at all — `0xff0000ff` is pure red at full alpha
and `0x969696ff` is neutral grey at full alpha. **RGBA colours.** Two
independent values both landing exactly on canonical colours is the kind of
coincidence that does not happen.

Type 6 always carries the value 0 across seven different attribute ids, so it
reads as a toggle.

So a message is text plus optional presentation: scale it, colour it, set a
flag. In `it_db_name_material.rmsg` every name from index 300 onward carries
scale 9/11 — the English names outgrew the box the Japanese ones were sized
for, and the localisation pipeline squeezed them.

## Reading one

```
$ python tools/rmsg.py list extract/tree it_db_name_material.rmsg
    297  Pigeon Blood Brooch
    298  Bloody Shield Fragment
    299  Bloody Shield Handle
    300  Orc King's Claw   [0/3=0.818182]
    301  Giant Herb   [0/3=0.818182]
```

## Open

- What word 2 selects.
- The attribute id space: id 0 carries both scale and colour, so the id is not
  the property — the type is, or the pair is. Ids 4, 5, 7, 9, 11 and 40 also
  occur, all with type 6 and value 0.
- Whether the Japanese files (the ones without `.en.` in the name) use the same
  attributes. They were validated but not compared.
