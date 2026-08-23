# `.mkc` — the presentation track of a motion

*Read by [`tools/mkc.py`](../tools/mkc.py).*
**2,690 files, 19,724 records, 0 unreadable**, every one of them landing
exactly on its terminator.

A [`CNOM`](format_cnom.md) moves the bones. An [`.anmcmd`](format_anmcmd.md)
says what the motion *does* — where the hit capsule is, when the actor may be
cancelled. This third sidecar says what the motion *sounds and looks like*:
which sound cue fires on which frame, which line the actor grunts, when a foot
touches the ground, which effect is spawned and when the camera shakes.

It is named after its motion — `com051emo_1.mkc` beside `com051emo_1.CNOM` —
and lives in the pac's own `<name>.mkc.pac`, one directory below the `CNOM`
and beside the `effect.bin` it indexes.

---

## The stream

There is no magic word, no header, no count. A file is a flat list of records,
big-endian `u16` throughout, closed by a lone `0xffff`:

    u16   frame
    u16   opcode
    u16   argument count
    u16   arguments[count]
    ...
    0xffff

The argument count is **explicit**, which is why the records are not a fixed
width: the same opcode takes one argument in one file and three in another,
and 24 distinct `(opcode, count)` pairs occur over 21 opcodes. Nothing else in
the file declares a size, so walking the stream by that count and landing
exactly on the terminator is the whole proof — and it does, on **2,690 of
2,690**. 256 files are the terminator and nothing else; the largest is 1,076
bytes.

**The frame is absolute, and the disc says which.** Frames never step backwards
on any of the 2,690. Of the 2,085 non-empty files that share a stem with a
`CNOM`, reading the first word as an absolute frame stays inside that
animation's declared length on **2,077**; reading it as a delta from the
previous record overruns on **1,471**. The eight that overrun as absolutes are
listed under [Still open](#still-open).

---

## The opcodes

`python mkc.py census extract/tree`, with the actor kind the pac belongs to:

| op | args | total | player | monster | small | reading |
|---|---:|---:|---:|---:|---:|---|
| `7ff9` | 3 | 6,250 | 702 | 3,575 | 1,923 | **play a sound cue** |
| `7ffd` | 1/2/3 | 735 | 524 | 49 | 117 | the same, second form |
| `7ffc` | 1 | 659 | 650 | 0 | 0 | **play the actor's voice** |
| `7ffa` | 1 | 979 | 901 | 0 | 0 | **ground contact** |
| `7ffb` | 1 | 1,575 | 766 | 145 | 614 | ground contact, second event |
| `0801` | 1 | 3,926 | 478 | 2,482 | 958 | **spawn an effect** |
| `080e` | 2 | 264 | 88 | 162 | 14 | the same, second form |
| `0802` | 4 | 1,275 | 64 | 1,207 | 4 | camera shake — see below |
| `0404` | 2 | 971 | 440 | 350 | 181 | open a bracket |
| `0405` | 2 | 948 | 426 | 348 | 174 | close it |
| `0400` | 2 | 936 | 895 | 0 | 1 | a flag and an id |
| `0803` | 1 | 300 | 300 | 0 | 0 | a bracket, players only |
| `0806` | 1 | 441 | 24 | 37 | 380 | unread |
| `080f` | 4 | 193 | 0 | 193 | 0 | unread, monsters only |
| `0807` | 1 | 66 | 28 | 0 | 38 | unread |
| `0800` | 4 | 63 | 48 | 12 | 3 | unread |
| `0406` | 1 | 45 | 0 | 12 | 33 | unread |
| `0805` | 1 | 36 | 36 | 0 | 0 | unread, argument always 14 |
| `080c` | 1 | 35 | 11 | 0 | 0 | unread, argument always 0 |
| `0804` | 0 | 24 | 24 | 0 | 0 | unread, no arguments |
| `080d` | 2 | 2 | 2 | 0 | 0 | unread |

The three families are visible in the numbering — `04xx`, `08xx`, `7ffx` — and
they split by what they touch: `7ffx` is sound, `08xx` is everything spawned
or shaken, `04xx` is state.

---

## Sound

    7ff9 (bank, cue, emitter)
    7ffd (bank, cue, emitter)
    7ffc (cue)

### The bank is an `.acb`, and the id says which one

`python mkc.py banks extract/tree`. The rule is arithmetic:

| bank | `.acb` |
|---|---|
| `100` | `sound.cpk/common.acb` |
| `200 + 10k` | `job.cpk/<class>/se.acb`, *k* over `as cl cm hs ht mg nn sw` |
| `3000 + 10n` | `monster.cpk/b<nn>/se.acb` |
| `4000 + 10n` | `monster.cpk/z<nn>/se.acb` |

Every player motion set uses exactly one class bank and every monster set
exactly its own, which is what fixes the mapping: `fas`/`mas` use 210 and
nothing else, `fht`/`mht` use 250, `b09` uses 3090, `z26` uses 4260. The two
gaps in the class series — 230 and 270, which would be `cm` and `nn` — are
never used, and those are the two classes with no directory in `job.cpk`.

### The cue is a `CueId`, not a row number

An `.acb` is an `@UTF` table and [`cpk.py`](../tools/cpk.py) opens it; the cue
names live in `CueNameTable`, keyed by row, and the number a `.mkc` carries is
the `CueId` of that row. The distinction matters: **225 of `common.acb`'s 529
rows carry an id that is not their index**, and the ids run to 3104.

Resolved that way, **6,881 of 6,949 references land on a named cue** — the 68
that do not are all in the two banks named below under *Still open*.

And what comes back is the game in plain words:

    mht361at_l          the hunter's strong attack
       0  0400 (1, 4000)          open
       0  0803 (0)                open
       4  7ff9 (250, 14, 0)       job.cpk/ht/se.acb   DRAW_L
      18  0400 (0, 4000)          close
      18  0803 (1)                close
      18  7ffc (25)               the player voice     ATK_L
      19  7ff9 (250, 17, 0)       job.cpk/ht/se.acb   STRONG_REACTION_S
      20  7ff9 (100, 3004, 0)     common.acb          ARROW_DUMMY_L
      35  7ffa (0)                a footstep
      47  7ffa (0)                a footstep

which is a bow drawn over four frames, released on eighteen with a grunt, and
stepped away from. `mht301jump` fires `JUMP`, `mht220escape_f_st` fires
`AVOID`, `mht311at_s` fires `ARROW_DUMMY_S` and `mht325at_ssssl` the `_L`,
`com060emo_10` claps four times on `EMOTION_CLAP`, and `b09552die` plays
`HRSV_V_DEAD`.

### The voice bank

`7ffc`'s single argument is a cue of `sound.cpk/<lang>/v{m,f}NN.acb`, the
57-cue player voice bank — sixty files with one name list between them.
**All 659 uses name a cue**, 47 distinct, and the histogram is a combat game:

    23 ATK_S  114     27 FINISH_S  44     15 DASH  28
    25 ATK_L   86     17 DMG_S     32     22 JUMP  28
    24 ATK_M   69     29 CHARGE    30

It is used by the player motion sets and by the shared emote set `com`, and by
nothing else, which is what a player voice is. `mht204wait_4` — the low-health
idle — plays `DYING_1` then `DYING_2`.

### The emitter

The third argument is 0 on 4,233 of the 6,949 references, and the 2,716 that
name something are **all on the sixteen big monsters** — no player motion, no
small monster and no prop ever uses one. Where it is named it says **where on
the body the sound comes from**, and the disc proves it by naming the cues:

| emitter | cue on `b09` |
|---|---|
| 1100 | `HRSV_BLAST_L`, `HRSV_SWOOPED_L` |
| 1200 | `HRSV_BLAST_R`, `HRSV_SWOOPED_R` |
| 1300 | 16 of the 17 `_V_` voice cues, plus `DIG_1`, `DIG_2`, `RIPPLE_CHARGE` |
| 1700 / 1800 | `HRSV_STEP`, `HRSV_STEP_S`, `KICK_RUSH` |
| 10100 | `HRSV_TAIL_UPPER`, `HRSV_TALE_MOVE`, `HRSV_TAIL_HIT_GND` |

Left goes to one number and right to the other — 1100 and 1200 are otherwise
the same set, and so are 1700 and 1800. The voice has a channel of its own,
shared only with the sounds a beak makes, and the three tail sounds have a
fifth. The vocabulary is 23 values wide across the disc:

    0  1100 1200 1300 1600 1601 1700 1800 4000 6200
    10100 10201 10300 10302 10303 10400 10503 10508 10600
    31100 31200 31300 31700 31800

The `31xxx` band is the `1xxx` band plus 30000 and is used by `b19` alone,
which is what a second body on the same actor would look like. All 1,196 of
the players' references leave the field at 0, because a player's sounds come
from the player.

**It is not the `.anmcmd` effect catalogue.** Two of the 23 values (10503,
10508) also occur as opcode 10 effect ids and the other 21 do not, which is
too little to be the same namespace and is written down here so the next
reader does not spend the afternoon on it a second time.

---

## Ground contact

    7ffa (kind)     7ffb (kind)

`kind` runs 0 to 3 for `7ffa` and 0 to 2 for `7ffb`, and it selects a cue from
the character model's own four-cue `.acb` — `character.cpk/model.cpk/
<name>.pac/<name>.acb`. **All 146 of those files hold the same four cues and
nothing else:**

    0 WALK   1 RUN   2 LANDING   3 DRESS

The correlation with the motion name is exact. Over the whole disc, `kind = 0`
is what walks fire, `kind = 1` is what runs and dashes fire, `kind = 2` never
appears in a walk or a run and does appear in landings, and `kind = 3` appears
in no walk, run, dash or landing at all — it is the emote set's, which is what
a `DRESS` rustle would be.

A walk cycle fires the pair one frame apart at each step:

    mht211walk    15 7ffa(0)   16 7ffb(0)   35 7ffa(0)   36 7ffb(0)

`7ffa` reaches the fourth cue and `7ffb` never does, so the two are not the
same event under two names. Which of them is the character's own sound and
which is the ground's is not settled here; the ground has a surface code in
[`CCLS`](format_ccls.md) and nothing on the disc joins the two yet.

---

## Effects

    0801 (index)
    080e (index, 0)

The index is **1-based into the `effect.bin` sitting beside the `.mkc.pac`** —
an `ECH` table of 60-byte rows, one row per effect that motion set can spawn.
69 of these exist, one per pac.

The evidence is the ceiling. `python mkc.py effects extract/tree`: on **29 of
the 54 pacs** that use the opcode the largest index is *exactly* the table's
row count — `b01` 49/49, `b05` 104/104, `b09` 89/89, `b10` 255/255, `b11`
143/143, `b18` 101/101, `z01` 25/25 — 11 more stay under it, and the index is
**never 0 on any of the 2,690 files**. Hitting the row count on the nose,
repeatedly, is not something a number does to an unrelated table.

The 14 pacs that overshoot are listed under *Still open*.

The `effect.bin` row itself is not read here. It is 60 bytes of which the last
44 are usually zero, opening on two `u16` ids, a `u32` that is 0 or 10000, four
bytes of which one is `0x40` and one `0xff`, and **a float at `+0x0C`** that is
1.0, 0.8 or 0.7 — a scale, in all likelihood. That is an `ECH` column-naming
job, which is [its own open item](format_ech.md).

---

## Camera shake

`0802` takes four arguments and is **monsters' 1,207 times out of 1,275**. The
64 player uses are the interesting half, because they are not spread over the
move list at all — every one of them is the impact frame of a big skill:

    fas434act_3_back_stab          fmg433act_1_en_fire_ball
    fhs439act_3_en_hammer_fall     fmg439act_3_en_frost_wave
    fhs446act_6_en_drill_cannon    fht442act_8_en_sharp_shooting

and on a monster it fires on the footsteps. A thing that happens when a giant
takes a step and when a hammer lands, and never when a dagger does, is the
camera shaking. The arguments are `(kind 1..12, a, b, 0..4)` with `a` and `b`
small — a duration and an amplitude in some order — and are not read.

---

## Brackets

`0404` and `0405` are an on/off pair keyed on the first argument: counting
opens against closes, per file and per key, balances on **853 of 878 pairs**.
`b09` turns four of them on at once at frame 25 of `at5`, off again at 150.

`0400` carries `(flag, id)` where the id is one of six values — 1200, 4000,
10200, 10300, 25000, 25100 — and the flag is 0 or 1. It brackets cleanly where
it is used inside a move (`mht361at_l` opens `(1, 4000)` at frame 0 and closes
`(0, 4000)` at 18, around exactly the frames the bow is drawn), but the emote
set opens every file with a lone `(0, 25100)` at frame 0 and never closes it,
so the flag is not only a bracket. `0803` is the players' own 0/1 pair and
runs alongside `0400` in every attack that has one.

---

## What this closes

Three things that were open before this file was read:

- **`effect.bin` has a consumer.** 69 `ECH` tables nobody had a reason to open
  turn out to be the per-motion-set effect list, addressed by index from here.
- **A motion set can be shared.** `z18`, `z19`, `z20` and `z27` all ship the
  *same* `z19.mkc.pac`, and all four fire bank 4190 — one animation set and
  one sound bank across four palette swaps.
- **The sound layer is addressable end to end.** A motion id now reaches a cue
  name through `.mkc` → bank id → `.acb`, and 7,540 of 7,608 references
  (6,881 sound + 659 voice) resolve. Later the same session
  [`awb.py`](../tools/awb.py) took it the rest of the way to a sample:
  **7,524 of the 7,608 reach a waveform that exists**. See
  [`format_awb.md`](format_awb.md).

---

## Still open

- **Banks 1140 and 1170** name no `.acb` in the extracted tree — 66 and 2
  references, from the NPC motion sets (`n03`, `n08`, `n15`, `n26`, `n28`,
  `bird_a`, `recycle_box`) and from `treasure_big`. Resolved against
  `common.acb` they give `BARREL_BOMB`, `BOX_BOMB` and `DAGGER_SWISH_L`, which
  is plausible for a prop and not for a dance, so the reading is not asserted.
  They do not follow the `200 + 10k` / `3000 + 10n` rule either.
- **The emitter namespace.** 23 values, paired left and right, provably a
  place on the body, and not tied to any table on the disc. The `CMDL` node
  lists are the obvious place to look next.
- **Fourteen pacs address an effect past the end of their `effect.bin`** —
  `b02` 79 against 73 rows, `b15` 67 against 48, `z09` 20 against 16, and
  `fht`/`mht` a lone 253 against 43, used twice, at frame 0 of
  `act_8_en_sharp_shooting` and plainly a sentinel. Either a second table is
  concatenated at load or the high ids are shared, and the disc does not say.
- **Eight files whose last frame is past the paired `CNOM`'s length**:
  `fht398a_at_l` and `mht398a_at_l` (31 against 9), `fsw315at_sssss` (37/28),
  `b09511at5` (211/166), `z03274dam_wall` (36/21), `z04211walk` (37/26),
  `z26505at5` (135/61), `bird_a.mot` (771/601). Every one of them is a motion
  that loops or blends into a successor, so the track outliving the clip is a
  reading rather than a defect — but it is not shown here.
- **Ten opcodes with no reading**: `0800`, `0804`..`0807`, `080c`, `080d`,
  `080f`, `0406`, and the argument roles of `0802`. Between them they are
  1,105 of the 19,724 records. `080f` is monsters only and `0803`, `0804`,
  `0805`, `080d` are players only, which is where a correlation would start.
- **Whether `7ff9` and `7ffd` differ at all**, and likewise `0801` and `080e`.
  Each pair takes the same arguments and appears in the same places; the
  second of each is roughly a tenth as common. A one-shot against a looping
  play is the obvious guess and nothing here tests it.

---

## Reading one

    python mkc.py check   extract/tree           the grammar, every file
    python mkc.py census  extract/tree           every opcode, by actor kind
    python mkc.py list    extract/tree b09502at2 one file, with its cue names
    python mkc.py banks   extract/tree           bank ids, and what they name
    python mkc.py cues    extract/tree 250       one bank's cue list
    python mkc.py effects extract/tree           indices against effect.bin

`b09502at2` — Hraesvelgr's second attack — reads:

        3  7ff9 (3090, 34, 1300)   HRSV_V_ATTACK_L
       12  7ff9 (3090,  2, 1800)   HRSV_STEP
       12  0802 (8, 2, 5, 3)       the camera shakes
       13  0801 (4)                effect row 4
       25  7ff9 (3090,  2, 1700)   HRSV_STEP        the other foot
       25  0802 (8, 2, 5, 3)
       26  0801 (5)
       29  7ff9 (3090,  8, 0)      HRSV_AT2
       30  0404 (0, 0)             open
       40  7ff9 (3090,  2, 1700)   HRSV_STEP
       44  7ff9 (3090, 11, 10100)  HRSV_TALE_MOVE   from the tail
       50  0405 (0, 0)             close
       52  0801 (6)
       90  0801 (34)

A cry, six paces with the ground shaking and dust under each one, a swipe, and
the tail dragging behind it.
