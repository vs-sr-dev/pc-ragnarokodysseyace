# `.anmcmd` — the animation command lists

**Status: container solved, the hit record read, the opcodes partly named.**
2,053 files, **6,802 blocks, 10,175 commands, 0 unreadable**, and every
arithmetic check closing on every file. Reader:
[`../tools/anmcmd.py`](../tools/anmcmd.py).

This is what turns an animation into an event. A [`CNOM`](format_cnom.md) moves
the bones; one of these says what happens on which frame of it — and the two
commonest opcodes turn out to be **the hitbox**, bound to the skeleton through
the same locator table the `collision_*.CTXT` capsules use.

## Three nested tables and nothing else

No magic word, no `POF0`, no version. The file is a table of blocks, a block is
a table of commands, and a command declares its own size.

```
0x00  u32   block count
0x04  (u32 frame, u32 offset) per block
      then the blocks, in table order, the first at 4 + 8 * count
```

```
block   +0x00  u16   the frame again
        +0x02  u16   command count
        +0x04  the commands, end to end

command +0x00  u16   opcode
        +0x02  u16   size, this header included
        +0x04  the payload
```

The identities, all of them over the whole disc:

| | |
|---|---:|
| the first block follows the table | 2,053 / 2,053 |
| block offsets ascend and stay inside the file | 2,053 / 2,053 |
| the block repeats the frame the table gave it | 6,802 / 6,802 |
| the commands fill the block exactly | 6,802 / 6,802 |
| frames ascend | 2,041 / 2,053 |

**The last-but-one is the one that matters.** Nothing else in this file
declares a length, so a block could be read as any number of things; walking
`count` commands from `+0x04` and landing exactly on the next block's offset is
what says the reading is right rather than merely possible. The twelve files
whose frames step backwards once are all monster lists — something a
hand-authored event track may do and a corrupt table may not.

## The name is the link to the motion

Nothing inside the file identifies its animation. The name does: a class prefix
and a three-digit motion id.

```
as213run.anmcmd        ->  fas213run.CNOM  and  mas213run.CNOM
b01_00_501.anmcmd      ->  b01501*.CNOM
as220escape_f_st_quick ->  fas220escape_f_st.CNOM, played faster
```

**1,499 of the 2,053 resolve to a `CNOM` that way, and on 1,473 of those every
command frame lies inside the motion's declared length.** That second number is
the check: it says the pairing is real and that these frame numbers are `CNOM`
frames — 1/30 of a second each, per [`units.md`](units.md).

## Opcode 0 and opcode 27 carry the same record, and it is the hit

**Opcode 27's payload is 116 bytes**, which is exactly one of opcode 0's
records. So the two are a list and a single of the same thing, and there are
6,193 of them: 4,989 inside opcode 0 and 1,204 standing alone.

Opcode 0's twelve-byte head says how many follow:

```
+0x00  u16   opcode 0
+0x02  u16   size == 12 + 116 * n
+0x04  u32   a small number, or 1000
+0x08  u16   n                       == (size - 12) / 116 on all 2,508
+0x0A  u16   zero                    on all 2,508
```

Two independent fields agreeing on the count, on every command, is what closes
this: the size and the head are written by different parts of an exporter and
they never disagree.

**Opcode 0 declares the set and opcode 27 updates one of it.** Of the 185 files
carrying both, the first opcode 0 precedes the first opcode 27 on **all 185**,
and 1,176 of the 1,204 opcode-27 records name a slot an opcode 0 had already
declared. Four files use opcode 27 with no opcode 0 anywhere.

### The record

```
+0x00  u8        slot           0 to 15
+0x01  u8        flag           0 to 5
+0x02  u16       the bone
+0x04  u16       a second bone, or zero
+0x06  u16
+0x08  float[3]  \
+0x14  float[3]   > three vectors; every one of the nine goes negative
+0x20  float[3]  /
+0x2C  float     a size    never negative, set on 6,145 of 6,193
+0x30  float     a size    never negative, set on 5,926
+0x34  u8[4]     the second byte scales with the strength of the hit
+0x38  u8, 0xFF, 0, 0
+0x3C  float
+0x40  float     1.0       on 6,181, zero on the rest
+0x44  float     usually 0.01
+0x48  u16       a CRI Atom cue id, then zero - the impact sound
+0x4C  u16, u16  the second an id around 361..370
+0x50  float
+0x54  float     -1.0      on all 6,193
+0x58  float
+0x5C  float
+0x60  u32
+0x64  u32
+0x68  zero      on all 6,193
+0x6C  float
+0x70  float
```

The nine floats at `+0x08` are three vectors rather than the
`offset / size / rol` of a `.CTXT` capsule: a size is never negative and all
nine of these are, between a fifth and a half of the time. The two at `+0x2C`
and `+0x30` never are, and those are the sizes. Which vector is an offset,
which an end point and which a direction is not settled here.

### The bone, and every one of them resolves

`+0x02` addresses two spaces at once, and the value says which. **Locator ids
on this disc start at 1000 and no model has more than 149 nodes**, so a number
below a thousand is a node index and one above it is a locator id, with no case
that could be either. Checked against the model that owns each animation —
`anmcmd.py bones` does this:

| | locator ids | present in the model | node indices | in range |
|---|---:|---:|---:|---:|
| player classes | 433 | **433** | 3 | **3** |
| monsters | 349 | **349** | 3,983 | **3,983** |

**4,768 of 4,768**, with 1,425 further records naming no bone at all. The
locator route is the `S4` table of [`CMDL`](format_cmdl.md), the same one the
`collision_*.CTXT` hurt capsules bind through — so a hit and a hurt reach the
skeleton by the same door.

Resolved to names, the node indices read as a hitbox set and nothing else
would:

```
node_head      429      node_l_toe      94
node_r_weapon  266      weapon          81
node_r_hand    236      node_r_toe      76
node_l_hand    202      b19_00_shield   72
node_jaw       201      node_l_finger00 70
node_r_forearm 162      node_hara       67
```

A monster's hitboxes are on its jaw, its head, its hands, its weapon and its
toes. That is what an attack is, and it is what identifies the record. Read one
out and it says so plainly:

```
$ python tools/anmcmd.py hits extract/tree b01_00_507.anmcmd
  f46  op0  slot 0  locator 1100 (node_l_hand)  ... size 1.60 0.60
  f54  op0  slot 0  locator 1200 (node_r_hand)  ... size 1.60 0.55
```

The sixth attack of the first monster in the game is a one-two. And the sword's
charged swing hangs its hit on `locator 4000`, which is `node_r_weapon` — on
the sword.

### The byte at `+0x35` scales with the strength of the hit

Two things say so, and neither needs the value's unit to be known.

**Within one attack it decays.** `sw383cge_l3` is the sword's fully charged
swing: opcode 0 declares two slots at frame 13, then three opcode 27s update
slot 1 at frames 14, 16 and 17, and across them the byte falls **95, 45, 15**
while the size at `+0x30` falls 2.70, 2.00, 1.50 and the second vector's `y`
falls 4.50, 3.50, 2.50. A shockwave travelling out and running down.

**Across charge levels it rises.** The sword is the only class with all three
on the disc:

| | records | `+0x35` | size |
|---|---:|---:|---:|
| `sw381cge_l1` | 1 | 50 | 1.12 |
| `sw382cge_l2` | 1 | 70 | 1.33 |
| `sw383cge_l3` | 5 | **95** | **2.70** |

Both the byte and the capsule grow with the charge. The hammer has two levels
and goes 80 against 40 on the largest single value while rising 80 to 86 on the
sum, because its level 2 is four hits where level 1 is one — which is what a
charged multi-hit does to a per-hit number.

Monster records put 100 or 150 there far more often than players do, so the two
are on different scales; what the number *is* — damage, a percentage, a level —
is not established.

## The other opcodes, as far as position says

52 opcodes, and **51 have one fixed size wherever they appear**, from 4 bytes —
no payload at all — up to 120. Naming one needs a correlation; where there is
one it is given, and where there is none the entry says so.

- **Opcode 13 opens a window and opcode 5 closes it.** Both carry no payload,
  both occur exactly once in a file, they appear together in 315 files, and 13
  comes strictly before 5 on **356 of the 366** files with both. 13 falls at
  44% of the way through the list at the median; 5 is the last command in the
  file on 288 of 393.
- **Opcodes 24, 50, 41, 52 and 39 are exclusive terminators.** Each occurs at
  most once per file, at the last frame, as the last command — 63 of 63 for
  opcode 24, 39 of 39 for opcode 50, 6 of 6 for opcode 41 — and a file that
  carries one does not carry another. So a list ends with a statement of what
  kind of ending it is.
- **Opcode 10 emits, and never appears in what it emits.** 288 files carry it
  and **not one of the 229 named `*bullet*` does**, while 197 of those carry a
  hit record instead. So the firing animation spawns and the projectile's own
  animation does the hitting. Among the player classes the bow carries it most,
  65 files, and `ht383cge_l3` — the fully charged shot — issues it ten times in
  one list. The ranged classes' charged attacks carry no hit record at all,
  which is the same fact from the other side.
- **Opcode 17 is a boolean**, 242 payloads of `0` against 239 of `1`. Opcodes
  8, 9, 11 and 14 are the same four bytes but almost always `1`.
- **Opcodes 1, 2 and 35 carry a small index** in their first byte, from zero up.
- **Opcode 22 places something and rotates it.** 448 uses, 82% at frame 0, and
  its 44 bytes hold a scale (1.0 on 322 of them, then 1.5, 2.0, 0.8), an offset
  and three angles that read as **degrees** — the only values ever seen there
  are 90, 180 and −15. Its second word is an id of 10300, 10301 or 10302.
- **Opcode 40 is frame-0 setup**, 87% of its 317 uses, and pairs a flag with a
  small id. **Opcode 53 is frame-0 setup on all 231 of its uses**, which no
  other opcode manages.

The numbering runs 0 to 62 and then jumps to 1000, 1002, 1004 and 10000. Those
four read like locator ids — `1000` and `10000` *are* locator ids, on 251 and
247 models — but 1002 and 1004 are locator ids on no model on the disc, so they
are opcodes in a high range and not addresses. Checking cost a minute and would
have been a plausible wrong answer.

## `+0x48` is the impact sound, and it names itself

The field is a **CRI Atom cue id in `sound.cpk/common.acb`**, which
[`cpk.py`](../tools/cpk.py)'s `@UTF` reader already opens - an `.acb` is an
`@UTF` table, so no new format had to be read to settle this.

941 of the 6,193 records carry 0 and 5,252 carry an id. **26 distinct ids are
used and 25 of them name a cue**; the exception is 347, four times, in one
monster's `z24_01_511`. Zero is a sentinel rather than a cue, and the disc says
so: cue 0 of `common.acb` is `SYSTEM_CURSOR`, a menu blip that no sword swing
would play.

The names say what the record is:

    1090..1093  HIT_DMG_S     HIT_DMG_M     HIT_DMG_L     HIT_DMG_LL
    1097..1100  SLASH_DMG_S   SLASH_DMG_M   SLASH_DMG_L   SLASH_DMG_LL
    1101..1104  STRIKE_DMG_S  STRIKE_DMG_M  STRIKE_DMG_L  STRIKE_DMG_LL
    1105..1106  FLAME_DMG_M   FLAME_DMG_L
    1107..1108  STORM_DMG_M   STORM_DMG_L
    260..347    FIRE_EXPLOSION_S/L, BURNING_ATTACK, SAND_GET and six others,
                39 uses at most and usually one

So a hit declares its **damage family** - blunt, slash, strike, flame, storm -
and its **size**, S through LL, in one number, and the sound and the family are
the same field.

**That corroborates `+0x35` independently.** Session 9 read the byte at `+0x35`
as the strength of the hit from two small series inside single files. Group all
5,252 records by the cue's family and size suffix instead and the median rises
with the suffix in **all five families**:

    FLAME    M=18  L=30
    HIT      S=12  M=65  L=90   LL=100
    SLASH    S=30  M=30  L=100  LL=100
    STORM    M=28  L=90
    STRIKE   S=4   M=55  L=100  LL=100

Two fields written by different tools - a sound designer picking a cue, an
animator setting a number - agreeing about which hits are big.

The families also fall where the monster does. `b02_00` and `b07_00` reach for
`FLAME_DMG` more than anything else, `b03_00` is 57 `SLASH_DMG_LL` against
11 of anything else, and `b01_00`, the Orc King with a club, leads on
`STRIKE_DMG_L`.

`hits` prints the cue name in the last column.

## Still open

- **Which vector is which** in the hit record. Three vec3s, all signed; the
  natural readings are an offset, a second end point and a direction, and
  nothing here distinguishes them. Posing the skeleton and drawing the capsule
  would settle it in an afternoon.
- **Opcode 10's effect id is a catalogue number and it does not resolve on the
  disc.** The payload is twelve bytes and reads

        +0x00  u8    an effect slot on the actor, 0 to 12
        +0x01  u8    zero              on all 915
        +0x02  u16   the effect id, 10001 to 39547
        +0x04  u32   zero              on 909 of 915
        +0x08  u32   a parameter - an angle in degrees, an index, or -1

  Session 9 called the id *global* because 10502, 10505 and 10510 are each used
  by half a dozen unrelated monsters. **That inference was wrong, and the
  reason is that the number is derived from the animation.** Of the 385 distinct
  (animation, effect id) pairs on the disc, 66 are exactly `10000 + the motion
  id` — `z03_00_502`, `z11_00_502`, `b02_00_502` and `z21_02_502` all fire
  10502 — and 67 more are `(1000 + the motion id) * 10 + a one-digit variant`,
  which is what `ht311at_s` → 13110 and `b14_00_502` → 15020 are. Monsters
  share motion numbering, so they collide on effect ids without sharing an
  effect. The rest are fixed per-actor effects reused across every animation:
  the Lord of Death's 10901 on all 24 of its lists, the sword's 10001..10006 on
  every combo.

  **No table on the disc maps that number to anything.** All 32,600 leaves were
  scanned for the 187 ids used, as aligned big-endian `u32` and `u16`, and
  nothing but float noise came back; the ids do not appear inside the `.PTP`
  either, in any width or byte order. What the disc *does* declare is a
  different addressing — a `(category, slot)` pair — and it declares it three
  times over; see [`format_ptp.md`](format_ptp.md). So the bridge from the
  catalogue number to a `PTB` slot is a static table inside the SELF, and this
  is the first item on the list that actually needs the EBOOT.
- **Thirty-odd opcodes with no correlation yet**, most of them rare: 7, 15, 16,
  18, 20, 23, 25, 26, 28, 31, 32, 34, 36, 37, 42 to 49, 51, 54, 55, 57, 60, 62.
- Why 554 files name no motion. Some are plainly not animations at all
  (`stick_bullet`, `soul_breaker_bullet`). **`.mkc` is not the key**: session
  15 read it, and it is named by its motion the way a `CNOM` is - 2,170 of its
  2,556 stems are a `CNOM` and exactly three are an `.anmcmd`. See
  [`format_mkc.md`](format_mkc.md).
- `+0x35`'s unit, and why players and monsters use different ranges of it.
