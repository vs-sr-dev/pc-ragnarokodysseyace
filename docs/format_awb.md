# The sound banks — `.acb`, `AFS2` and the waveforms

*Read by [`tools/awb.py`](../tools/awb.py).*
**274 banks, 7,756 waveforms, 12 hours 18 minutes of audio, 0 unreadable** —
and every one of them is reached by a cue with a name.

An `.acb` is an `@UTF` table, and [`cpk.py`](../tools/cpk.py) has been able to
open one since session 9. What was never opened is the column called
`AwbFile`, which is not a pointer to an archive but an entire archive carried
inside the row. This document is that archive, the header of the codec inside
it, and the four tables that say which cue plays which sample.

It is the last unread format on the disc, and it closes a chain:
[`.mkc`](format_mkc.md) says *play cue 14 of bank 250 on frame 4*; this says
what cue 14 of bank 250 **is**.

---

## The archive

`AFS2`, little-endian on an otherwise big-endian disc, on 273 of the 274:

    0x00  'AFS2'
    0x04  u8    version           1
    0x05  u8    offset width      2 or 4, and both occur
    0x06  u8    id width          2
    0x07  u8    zero
    0x08  u32   files
    0x0C  u32   alignment         0x20
    0x10  u16   id[files]
    ...   offset[files + 1]      of the declared width

Entry *i* runs from `align(offset[i])` to `offset[i + 1]`, and **the last
offset is the length of the archive** — which is the identity that says the
table was read with the right width. Getting the width wrong is the one way to
fail here, and it fails silently: `fas1.acb` uses two-byte offsets and
`b09/se.acb` four, so a reader that assumes either produces empty entries for
half the disc rather than an error.

The 274th bank is `sound.cpk/en/vprev.acb`, and its `AwbFile` is a **`CPK `
with an `ITOC`** — the older shape of the same idea, holding the 96 ADX
waveforms. `cpk.py` reads it as it stands, out of a column of a table it
opened itself.

One bank streams instead: `bgm.acb` declares all 439 of its waveforms
`Streaming = 1` and its `AwbFile` is empty, because they are in the 1.2 GB
`sound.cpk/bgm.awb` beside it — the same `AFS2`, standing on its own.

---

## HCA

7,659 of the 7,756 waveforms are CRI HCA.

    0x00  'HCA\0'   u16 version   u16 header size
    'fmt\0'   u8 channels, u24 sample rate, u32 frames,
              u16 encoder delay, u16 encoder padding
    'comp'    u16 frame size, then the band and resolution layout
    'ciph'    u16 cipher type
    'loop' 'ath' 'rva' 'vbr' 'dec' 'pad'     optional, in that order
    ...       the frames, each exactly `frame size` bytes

**`header size + frames * frame size == the archive entry's length` on all
7,659.** That is what says the archive was cut where the codec thinks it was,
and it is the check `awb.py check` runs.

Two things worth having found out rather than assumed:

- **`ciph` is 0 on every file.** HCA is routinely shipped encrypted, with a
  64-bit key that is not on the disc, and that would have been the one thing
  capable of making the audio unreachable. It is not used here.
- **`NumSamples` in the `.acb` is not the decoded length.** It is usually the
  length at the 48 kHz the `.acf` mixes at: on 6,295 of the 7,220 embedded
  waveforms, `NumSamples / 48000` equals
  `(frames * 1024 - delay - padding) / sample rate`, and ffmpeg agrees with
  the second number. On the rest the two are the same figure, so the field is
  native there. Nothing on the disc says which rule a file follows; use the
  header.

The codec itself is CRI's and well-trodden, and ffmpeg has decoded it since
4.3. `awb.py wav` drives ffmpeg, the way [`pam.py`](../tools/pam.py) leaves
MPEG-2 alone. **7,755 of the 7,756 decode with no error**, and the 7,756th is
below.

### What is in there

| | waveforms | minutes |
|---|---:|---:|
| `sound.cpk` — music, voice, common SE | 4,701 | 683.2 |
| `monster.cpk` | 1,486 | 34.4 |
| `character.cpk` — the four-cue model banks | 1,284 | 10.3 |
| `stage.cpk` | 177 | 8.6 |
| `job.cpk` — the six classes' weapon SE | 107 | 1.5 |

7,358 are mono and 301 stereo; the sample rates are 22,050 (4,412), 24,000
(2,026), 20,000 (590) and 48,000 (437) with a long tail. The 48 kHz stereo
band is the music.

### ADX and the one VAG

96 waveforms are CRI ADX, all of them in `vprev.acb`, and ffmpeg reads those
too.

One waveform is a Sony `VAGp` — 4-bit ADPCM, `stage.cpk/900/sound.acb`, cue
`BRIDGE_01`, and its internal name is `dummy_Enc_24000_`, so it is a
placeholder. ffmpeg will not demux a bare VAG, so `vag_pcm()` decodes it here:
16-byte blocks, a predictor index and a shift in the first byte, a flag in the
second, then 28 nibbles low-one-first, run through a five-entry second-order
filter. Forty lines, and it takes the count to **7,756 of 7,756**:
`awb.py wav extract/tree out/` writes 7,756 WAV files and reports 0 failures,
7.1 GB of them.

---

## Which cue plays which waveform

This is the part that is specific to this disc, and it is why the tool exists.
A cue does not name a waveform; it names a node in a small graph.

    Cue.ReferenceType 2  ->  Synth[ReferenceIndex]
    Cue.ReferenceType 3  ->  Sequence[ReferenceIndex]

    Synth.ReferenceItems   (u16 kind, u16 index) pairs
                           kind 1 a waveform, 2 another synth, 3 a sequence
    Sequence.TrackIndex    u16 per track  ->  Track.EventIndex
                           ->  Command, a stream of (u16 op, u8 size, payload)
                           where **op 2000** carries the same (kind, index)

6,111 of the 6,984 cues go the first way and 873 the second. **20,955 of the
20,964 reference items land inside the table they name**; the nine that do not
are `0xFFFF`, which is how the format says *nothing here*. Recursing through
both, **every one of the 7,756 waveforms is reached by a cue**, so there is no
sample on this disc without a name.

A cue reaching several waveforms is a variation set, and it is common:
`HRSV_RUN_1` on Hraesvelgr resolves to three, of 32, 31 and 30 frames.

---

## The chain, end to end

    python mkc.py  list extract/tree mht361at_l
       4  7ff9 (250, 14, 0)   job.cpk/ht/se.acb   DRAW_L

    python awb.py  cues extract/tree ht
      14  DRAW_L    w16   1ch 24000 Hz   19 frames   0.76 s

    python awb.py  wav  extract/tree/job.cpk out/
      out/ht_se/DRAW_L.wav

From the frame of an animation to a PCM sample, with nothing guessed in
between. Over the whole disc, **7,524 of the 7,608 sound references in the
2,690 `.mkc` files reach a waveform that exists**. The 84 that do not are 68
in banks 1140 and 1170, which name no `.acb` in the tree
([`format_mkc.md`](format_mkc.md) has the detail), and 16 cue ids that are
absent from the bank they name.

---

## Still open

- **The waveform's own `ExtensionData`**, empty on every row here.
- **`Track` and `Command` beyond opcode 2000.** The command streams carry
  volume, pitch, panning, delay and AISAC references, and a reimplementation
  that only plays a cue at full volume does not need them. Opcode 2001 is a
  second note-on with a four-byte payload whose second half is too large to be
  a synth index; it is not read.
- **Which of a variation set the game picks**, and with what weights. The
  `Synth.TrackValues` blob is the obvious place.
- **Banks 1140 and 1170**, which [`.mkc`](format_mkc.md) names and no `.acb`
  on the disc answers to.
- **The `.acf`'s 16 mixer categories and 40 buses** are read as an `@UTF`
  table and not described. Nothing plays yet, so nothing needs them.

---

## Reading one

    python awb.py check   extract/tree            every archive, every identity
    python awb.py list    extract/tree            one line per bank
    python awb.py cues    extract/tree b09        cue -> waveform, with headers
    python awb.py extract extract/tree out/       the raw streams, named by cue
    python awb.py wav     extract/tree out/       the same, decoded

`cues` takes a bank by its path, its file name, or the directory it sits in,
so `b09` finds `monster.cpk/b09/se.acb` whose leaf is only `se.acb`.
