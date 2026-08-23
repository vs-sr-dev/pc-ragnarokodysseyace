# `.anmcmd` — the animation command lists

**Status: container solved, the hit record read and its geometry named and
placed, the opcodes partly named.**
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
+0x01  u8        shape          0 to 5; it says what the vectors below are
+0x02  u16       the bone the first vector hangs off
+0x04  u16       the bone the second one hangs off, or zero
+0x06  u16
+0x08  float[3]  an offset from the first bone
+0x14  float[3]  an offset from the second - or an axis, on a cylinder
+0x20  float[3]  a third point - or a radius in `x`, on a cylinder
+0x2C  float     a length, in the actor's own metres
+0x30  float     a ratio, near 1 whatever the actor's size
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
and `+0x30` never are. **Which vector is which is settled below**, and the
answer is that the byte at `+0x01` decides.

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

### The three vectors, and the byte that says which is which

*Session 17.* The question had been asked the wrong way round. There is no
single answer, because **`flag` at `+0x01` is a shape**, and the shape says
what the three vectors are. `python anmcmd.py shapes extract/tree`:

| `flag` | reads as | n | uses `v0` | uses `v1` | uses `v2` | `v1` is a unit vector | `v2` puts it all in `x` | names a second bone |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | a sphere | 3,258 | 2,425 | **0** | **0** | – | – | **0** |
| 1 | a capsule | 2,283 | 1,605 | 1,733 | **0** | 91 | – | 1,778 |
| 2 | a long capsule | 75 | 47 | 73 | **0** | 0 | – | 71 |
| 3 | a cylinder | 114 | 67 | **114** | 111 | **114 of 114** | **111 of 111** | **0** |
| 4 | three points | 445 | 444 | 423 | 437 | 0 | 0 | 404 |
| 5 | a cylinder | 18 | 1 | **17** | 18 | **17 of 17** | **18 of 18** | **0** |

Three things fall out of that table and none of them is fitted.

**A flag never half-uses a vector.** Flags 0, 1 and 2 leave `v2` at zero on
all 5,616 of their records; flag 0 leaves `v1` at zero on all 3,258. A field
that is a payload under one selector value and absent under another is a
field under a selector.

**And `+0x2C` behaves as a radius when something swings it.** Session 22 put
every monster's hit volumes on its own skeleton and measured how far they get
from the body, taking `+0x2C` as the radius the way
[`../engine/hitbox.py`](../engine/hitbox.py) already draws one. The result
correlates at **0.590** with `_act.par`'s declared range for the same action
over 250 actions, against 0.051 for the same pairs reshuffled - which is a
second file agreeing about a distance, and would not happen if the field were
something else. See [`milestone_fight.md`](milestone_fight.md).

**On flags 3 and 5 the second vector is a direction and the third is a bare
number.** All 131 second vectors have length exactly 1, 98 of them on the `y`
axis alone; all 129 third vectors carry a value in `x` and nothing in `y` or
`z`. And the tilted axes give it away completely — 24 records carry

    (-0.5144957304000854, 0.8574929237365723, 0.0)

which is `(-0.6, 1, 0)` normalised, to the last bit of a `float`. Nobody
types that; a tool wrote it. So those two vectors are not points: one is an
**axis** and the other a **radius**, put in a vec3 lane because the record has
nowhere else to keep a loose float. The radii run from 0.1 to 55, and the
files that use them agree —
`ht432act_2_freezing_trap_bullet_active` is a centre, an axis pointing up and
a radius of 4.5 m, `mg433act_1_quag_mire_bullet` is the same with 3.0. A trap
and a mire are a disc on the ground.

**The second bone appears only where the second vector is a point.** Flags 1,
2 and 4 name one on 2,253 records; flags 0, 3 and 5 name one on **none of
their 3,390**. A sphere needs one anchor and a disc needs one anchor; a
capsule needs two.

Flags 2, 4 and 5 are also **monsters only** — one player record in 538 — so
the complicated shapes belong to the bosses. A player gets a sphere or a
capsule.

### Each end of a capsule hangs off its own bone

`+0x04` was down as "a second bone, or zero" and nothing more. It is the
anchor of the *second* vector, and the skeleton says so twice.

**It is a bone of the same limb.** Over the 2,253 records that name one,
**2,194 sit on one chain with the first**: the same node 1,467 times, its
parent 256, its child 201, further up the same chain 270, and something
unrelated only 59. Resolved to names they read as limb segments and nothing
else would:

```
node_r_weapon  -> node_r_weapon   187      node_head      -> node_neck    81
node_head      -> node_head       110      node_neck      -> node_neck2   60
node_r_hand    -> node_r_hand     100      node_r_forearm -> node_r_hand  41
node_l_hand    -> node_l_hand      99      node_l_forearm -> node_l_hand  37
b19_00_shield  -> b19_00_shield    72      node_hara      -> node_spine1  40
```

**And the vectors are far too short to be spanning it themselves.** If both
offsets were in the first bone's space, `|v1 - v0|` would have to be the
capsule's whole length. Over the 786 records that name two *different* nodes
the joint separation is **6.41 m at the median** while `|v1 - v0|` is
**1.00 m** — 16 % of it — under half of it on **614 of 786 (78 %)** and within
30 % of it on 35 (4 %). The limb supplies the length; the vectors are small
local offsets from the two ends of it. Read that way the capsule comes out
7.79 m long at the median against a 6.41 m limb, which is a hitbox a little
longer than the arm it wraps.

So **`v0` is an offset from the bone at `+0x02` and `v1` an offset from the
bone at `+0x04`**, and where `+0x04` is zero both hang off the first — or,
when there is no bone at all, off the actor's own origin, which is what the
sword's charged shockwave does.

### They are lengths in the actor's own units

Group every record by its actor, take the median magnitude, and set it beside
the actor's standing height off the rest pose. **`|v0|` rises with the actor
over 80 actors (r = 0.61)**, and so does the size at `+0x2C` (r = 0.75 over
88). A 1.9 m `z05` puts its hits 0.5 m from the bone; a 35 m `b11` puts them
3.7 m away.

**The size at `+0x30` does not** — r = −0.04, a median of 1.00 on nearly every
actor from the smallest to the largest, and 5,160 of 6,193 values inside
[0.5, 2.0]. Whatever it is, it is a **ratio and not a length**, and calling
both fields "a size" was hiding that.

### A worked pair

`b11_00_506` — a 35 m monster's head attack — declares two shapes at frame 63
and repeats them at frame 107 with **every `x` negated and nothing else
changed**:

```
f63   three points  node_head  node_neck   v0 ( 1.00  0.80  0.50)  v1 ( 1.50  2.40  2.30)  v2 ( 2.50 -3.50  2.00)
f107  three points  node_head  node_neck   v0 (-1.00  0.80  0.50)  v1 (-1.50  2.40  2.30)  v2 (-2.50 -3.50  2.00)
```

That is the same sweep to the other side, and it is worth reading twice: all
three vectors mirror together, by the same rule, in the same lane. Whatever
the third one bounds on flag 4, it is the same kind of quantity as the first
two — and a rotation is not.

### The offset is turned by its bone — settled on an animated frame

*Session 19.* This was down as open, with a note that the two attempts made on
it had failed and that **"an animated frame with a bent elbow would"** separate
the readings. It does, and [`hitbox.py`](../engine/hitbox.py) is the file that
runs it: `pose.py` gained a `matrix()` so a bone arrives with its orientation
and not only its origin, and every hit record on the disc is then placed twice
on the frame it actually fires, over the `CNOM` it belongs to.

    turned    p = M_bone * v          the offset is in the bone's own frame
    carried   p = origin(M_bone) + v  the offset is in the actor's frame

**The measurement.** For every record whose bone has a child, take the angle
between the offset and the world direction from that bone to its child. The
child direction is a quantity the record never mentions and neither reading was
fitted to. `python engine/hitbox.py turned extract/tree`, restricted to the
1,435 placements where the two readings differ by more than a degree:

| reading | n | median | within 26° | z | within 60° | z |
|---|---:|---:|---:|---:|---:|---:|
| turned | 1,435 | 90.0° | **13.5 %** | **+14.6** | **33.9 %** | **+7.8** |
| carried | 1,435 | 88.6° | 5.6 % | +1.0 | 27.7 % | +2.4 |
| chance | | 90.0° | 5.1 % | | 25.0 % | |

The baseline matters more than the difference. A uniformly random direction
falls within 26° of a fixed one **5.1 %** of the time, and the *carried*
reading scores 5.6 % — it finds nothing at all, at one standard deviation.
The *turned* reading scores 13.5 %, fourteen standard deviations above chance
on the same sample of the same records. **The offsets are written in the bone's
own frame**, and the earlier rest-pose measurement (29.3 % against 15.2 %) was
pointing the right way with a weaker instrument.

Two things worth carrying out of the negative half of this:

- **the median is 90° under both readings**, which says a hit offset is
  usually *perpendicular* to its own bone rather than along it — a swing arc,
  not a reach. That is why the test needs the chance baseline to be readable
  at all: the signal is in the tail, not the middle;
- **the capsule-axis test does not work.** Measuring the capsule's axis
  against the limb between its two bones scores 53 % and 56 % within 26° for
  the two readings — both far above chance, and indistinguishable from each
  other, because both readings share the limb term and it dominates. Nor does
  a floor test: 7.2 % of turned offsets and 6.1 % of carried ones land below
  `y = 0`, and the deepest is 13 m under either, because a monster in the air
  has no floor to be under. Both are in `hitbox.py` and both are printed, so
  the next reader can see they were tried.

**`col_hit` says the same thing without an animation.** The `ELBN` body
capsule — see [`format_elbn.md`](format_elbn.md) — is the same idea in the
same engine, and its numbers are large enough to read straight off: a player's
body is two capsules on `node_hip` running to `(0, 0, ±0.6)`, and `node_hip`'s
own `z` axis points down, so turned they stand the body up from `y = 0.07` to
`y = 1.87` and carried they lie flat through the hips over 0.60 m. Two records,
two methods, one answer.

### What is still open about them

**What flag 4's three points bound** — a wedge, a triangle, a box — and what
separates flag 2 from flag 1 beyond `|v1|` running to 18.9 m at the median
against 4.0.

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

**It is a monster's field, and session 21 measured that.** Split the 6,193
records by which side of the fight authored them and the two populations are
complementary:

```
                 records   carry a cue   in 1000..1089
  monster           5439          5245               0
  player             754             7               0
```

**747 of the player's 754 records carry the sentinel.** The player's impact
sound is not in the record at all: it is looked up at the moment of the hit
from `se_hitlevel_tbl`, which allocates exactly the range 1000..1089 that no
record on either side ever reaches. A monster's claw always sounds the same
and a player's weapon does not. See [`combat_loop.md`](combat_loop.md) §1 and
[`format_elbn.md`](format_elbn.md).

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

- **What flag 4's three points bound** - a wedge, a triangle, a box. Under
  *The three vectors* above. **Whether a hit offset is turned by its bone is
  settled**: it is, on an animated frame, fourteen standard deviations above
  chance while the other reading is at one. See the same section and
  [`hitbox.py`](../engine/hitbox.py).
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
