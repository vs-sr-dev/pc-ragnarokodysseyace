# `CTEX` — the texture format

**Status: solved.** 11,536 files, 11,530 closing exactly, 0 unreadable, five
pixel formats decoded and eyeballed. Reader:
[`../tools/ctex.py`](../tools/ctex.py).

The largest population on the disc and the thing standing in front of any
rendered frame. Session 3 reconnoitred the header and identified the pixel
formats from file sizes alone; this is the rest.

## Layout

```
0x00  'CTEX'
0x04  u32   payload size          size + 16 == file length, on all 11,536
0x08  u32   0x00010005            constant
0x0C  u32   zero
--- payload; the offsets below are file offsets ---
0x10  u16   0x1000                constant
0x12  u16   width                 power of two, 16..2048
0x14  u16   height                power of two, 16..2048
0x16  u16   pixel format
0x18  u8    alpha present         0 on every DXT1, 1 on every DXT5
0x19  u8    mip levels minus one
0x1A  u16   zero
0x1C  u8    1                     constant
0x1D  u8    flags; bit 2 set iff there is a mip chain
0x1E  u16   zero
0x20  u32   0x50                  where level 0 begins, past the payload start
0x24  u32   palette offset, or zero, on the same origin
0x28  u16   0x60, 0x64, 0x70 or 0x80
0x2A  u16   zero
0x2C  u16   palette entries: 256, 16, or zero
0x2E  u16   zero
0x30  char[32]  the source texture's name, NUL padded
0x50  the pixels
```

Big-endian throughout, as everything else on this disc is.

## Width comes before height

The session 3 write-up had the two the other way round. Nothing in the size
arithmetic notices — every formula here is symmetric in width and height, so
`check` closes either way — and the error only surfaces the moment a pixel is
drawn, as an image sliced into interleaved bands.

`misc.cpk/logo_lang.pac/ui_logo_xseed` settled it. Read as 512x1024 it is a
comb of half-rows; read as 1024x512 it is the publisher's logo, edge for edge.
This is the case for the rule that a decoder is not finished until something
recognisable comes out of it: the arithmetic had been closing on 11,530 files
with the axes swapped.

## The formats

| format | encoding | files |
|---|---|---:|
| `0x109` | DXT1, 8 bytes per 4x4 block | 9,848 |
| `0x10F` | DXT5, 16 bytes per 4x4 block | 452 |
| `0x100` | A8R8G8B8, 4 bytes per texel, **swizzled** | 400 |
| `0x107` | 8-bit indices, 256-entry palette | 832 |
| `0x108` | 4-bit indices, 16-entry palette | 4 |

DXT blocks are little-endian, exactly as they are in a DDS file: the exporter
did not byte-swap them on the way to a big-endian machine.

Byte `0x18` is 0 on all 9,848 DXT1 and 1 on all 452 DXT5, which is what an
alpha flag would do, and is mixed on the three formats that can go either way.

## The mip chain

This was the open question, and byte `0x19` answers it: it holds **levels minus
one**. Levels halve in both axes and are stored back to back — no padding, no
alignment, no pitch. Block formats stop when a level would go under 4x4, linear
ones would run to 1x1.

```
levels  1    2      3      4      5    6
files   3152 1289   5039   1244   786  26
```

Summing that chain and adding `4 * palette entries` reproduces the payload
exactly on **11,530 of 11,536** files.

The six exceptions are all in one directory,
`stage.cpk/100_01_01/model.pac/ground.pac/big_temple_*`. Each is eight bytes
long — one extra DXT1 block, a 2x2 level below the 4x4 where the chain should
have stopped. The header undercounts what the file holds rather than
overcounting it, so a reader that trusts `0x19` is safe; a renderer would never
sample the extra level either. `check` prints them rather than absorbing them.

## Palettised files put the palette last

Not first. `0x24` points at it, and `palette offset - 0x50` equals the size of
the index chain on every one of the 836 palettised files — 836 checked, none
off by a byte. Entries are four bytes, `A R G B`; 4-bit indices are read high
nibble first.

This is what makes `0x107` legible. Two bytes per texel is what its file sizes
suggest, and read that way the arithmetic closes for six files out of 832 — by
coincidence, since a 256-entry palette is 1,024 bytes and a great many
textures are large enough to absorb that without the sum looking absurd. Read
as indices plus a trailing palette it closes for all 832.

## A8R8G8B8 is swizzled, and nothing else is

The 400 uncompressed surfaces store texel `(x, y)` at the Morton interleave of
`x` and `y`, `x` in the even bit positions, with the surplus bits of the longer
axis stacked above the interleaved part. Nothing in the header announces this:
it follows from the pixel format alone.

It is not guesswork. Scoring every non-DXT file for horizontal roughness in
both readings separates the population cleanly:

| format | reads smoother swizzled | smoother linear | flat, says nothing |
|---|---:|---:|---:|
| A8R8G8B8 | 369 | 0 | 31 |
| P8 | 1 | 830 | 1 |
| P4 | 0 | 3 | 1 |

Not one A8R8G8B8 reads smoother linear. The single P8 on the wrong side is
`menu.cpk/.../ui_hp_gauge`, 64x32, and it is a metric artefact rather than a
counter-example: the texture is horizontal bars of flat colour, so its
horizontal roughness is near zero read either way, and the eye settles it in a
second — linear draws the gauge, swizzled does not.

`menu.cpk/.../ui_dictionary_success01` — 512x256, the word "Success!" twice —
confirms the swizzle by eye, and with it the bit order: interleaving `y` into
the even positions instead of `x` produces the transpose, which is also smooth
and also wrong.

## The 137 `.map` files are minimaps

Not every `CTEX` is called `.CTEX`. Each stage directory carries one
`<stage>.map` in its `param.pac`, and all 137 of them begin `CTEX`: 256x256,
format `0x107`, one level, no mip chain, the palette after the indices like
every other P8 file on the disc.

Decoded, each one draws the silhouette of its stage — a lilac blob on white
with a grey outline — and that silhouette is visibly the same shape as the
stage's own collision mesh seen from above. `.map` is the **minimap**.

This is worth recording because the file extension sent a session looking for a
world layout. The layout is in [`format_stage.md`](format_stage.md), three
files along in the same directory. The rule that would have saved the detour is
the one this project already follows for containers: **recognise a file by its
magic, never by its extension**.

```
$ python tools/ctex.py png extract/tree 010_01_01.map map.png
```

What is *not* known is the transform: nothing has been fitted from stage
coordinates to the 256x256 image, so the minimap can be drawn but not yet
registered against anything.

## Still open

- **`0x28`** takes four values: `0x80` (8,796), `0x70` (2,557), `0x60` (153),
  `0x64` (30).
- **Bit 0 of `0x1D`.** Bit 2 is the mip flag and is fully explained. Bit 0 is
  set on 5,708 files and covaries with `0x28` without either determining the
  other: `0x70` is always paired with bit 0 set, `0x80` with it clear whenever
  there are mips, and `0x60` goes both ways.

Neither affects the size arithmetic, which closes without them, and neither
predicts the swizzle, which the pixel format does. Together they read like a
stamp left by successive versions of the exporter rather than something the
renderer consumes. They are the kind of field that will be named in a minute
once the EBOOT is readable and is not worth an hour before then.

## Reading one

```
$ python tools/ctex.py info extract/tree ui_logo_xseed.CTEX
misc.cpk/logo_lang.pac/ui_logo_xseed.CTEX
  name        ui_logo_xseed
  size        1024 x 512
  format      0x107  P8
  alpha       0
  levels      1
  flags 0x1D  0x01
  stamp 0x28  0x80
  palette     256 entries at 0x80050
  payload     525312 bytes, header accounts for 525312
    level 0   1024x512      524,288 bytes at 0x60

$ python tools/ctex.py png extract/tree ui_logo_xseed.CTEX out.png
$ python tools/ctex.py unpack extract/tree png/ 'menu.cpk/*'
```

`unpack` is a pure-Python DXT decoder and is slow; it exists to eyeball a
directory at a time, not to convert the disc.
