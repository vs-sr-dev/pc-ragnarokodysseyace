# The combat loop, on paper

*Session 21.* One hit, from the frame it fires to the number that comes off a
health bar, through every file that touches it. Nothing here is a new
container: every format below is already read, and this document exists to put
them in order and to say, at each step, **which numbers the disc gives and
which it does not**.

That was the whole point of writing it. Three sessions running, the TODO said
the loop was describable and nobody had described it; the cost of finding out
what is missing turned out to be one document, and the answer is at the end
under [*The ledger*](#the-ledger). Seven things got settled on the way, and one
earlier claim got corrected, which is the usual return on laying a chain out
end to end.

Every figure below is a join between two things this repository had already
read separately, and [`combat.py`](../tools/combat.py) is those joins —
`hitlevel`, `cues`, `power`, `weapons`, `stop`, `tension`, or `all` — so the
document can be re-derived rather than believed.

---

## The chain

```
  the attacker                              the target
  ------------                              ----------
  a motion plays              CNOM
  a frame fires a volume      .anmcmd op 0/27  ─┐
      shape, bone, vectors                      │
      power  +0x35                              │
      size   +0x30                              │
      cue    +0x48  (monsters only)             │
                                                ▼
                                           col_hit capsules      ELBN objbin
                                           a region owns them    region_data
                                           region_lv picks its   [8] defence
                                             row                 [8] hit points
                                                │
                                                ▼
                        damage  =  f(attack, defence, region, critical)
                                                │
              ┌─────────────────┬───────────────┼──────────────┬──────────────┐
              ▼                 ▼               ▼              ▼              ▼
          health            stagger         hit-stop      the hit level    tension
          hp                stg_p[4]        stop_*        se_hitlevel_tbl  s_tension_
          region hp         stg_{s,l,d}_r   dmg_stop_*    eff_hitlevel_tbl   revise_*
          break hp          react_p         23 bosses     S/M/L (+critical)  4 tables
                            take none
```

Eight files, every one of them already read as a format, and several of them
read differently by the end of this. Taking them in order.

---

## 1. The attacker declares a volume on a frame

[`.anmcmd`](format_anmcmd.md) opcode 0 lists them and opcode 27 updates one:
**6,193 records on the disc**, 116 bytes each. A record is a shape, one or two
bones, up to three vectors in those bones' own frames, a size, and a strength
byte at `+0x35`. [`hitbox.py`](../engine/hitbox.py) already places them on an
animated skeleton, and the offsets are turned by their bone — measured, not
assumed.

For the loop, three fields matter and one of them has been read backwards.

### `+0x48` is the monster's impact sound, and the player has none

Grouping all 6,193 records by which side of the fight authored them:

```
                 records   carry a cue   in 1000..1089
  monster           5439          5245               0
  player             754             7               0
```

**747 of the player's 754 records carry cue 0**, which
[`format_anmcmd.md`](format_anmcmd.md) already showed is a sentinel and not
`SYSTEM_CURSOR`. The monsters carry a real cue on 5,245 of 5,439. And **not one
record on either side reaches into 1000..1089**, which is precisely the range
`se_hitlevel_tbl` allocates — see [§6](#6-the-hit-level-and-two-tables-that-agree-about-it).

So the two sides use different machinery for the same thing, and it is the
right way round: **a monster's claw always sounds the same and is written into
the record; a player's weapon changes every hour, so its impact sound is looked
up at the moment of the hit.** The earlier reading — "`+0x48` is *the* impact
sound" — is true of the monsters and empty on the players, and counting all
6,193 together hid that.

### `+0x35` is the strength, and its scale is per side

```
                 records   min   p25   med   p75   max   zeros
  monster           5439     0    30    80   100   255     561
  player             754     0     2     6    15    95      96
```

Two populations an order of magnitude apart. [`format_anmcmd.md`](format_anmcmd.md)
establishes that the byte rises with the charge level within a class and with
the cue's size suffix across the disc, so it is a strength; **what it is a
strength of is still open**, and §5 gives the two candidate readings and the
measurement that separates them.

---

## 2. The volume meets a body

The target side is [`ELBN`](format_elbn.md) `objbin.bin`, and session 19 read
it end to end:

- **`col_hit`** — a capsule per bone, 1,172 records over 100 files, and every
  one whose actor has a model resolves inside it, 1,148 of 1,148;
- **`region_data`** — 315 records over 83 monsters, a named body part owning
  the capsules it is hit through: `HEAD`, `HARA`, `L_WING_03`. The chain closes
  on itself — a region names capsules, a capsule names a node, and the node's
  name is the region's own on 259 of 266;
- **`region_data_brk`** — the same for the 23 monsters with breakable parts,
  with its own hit-point pool an order of magnitude larger, and indexing
  `it_drop_break` positionally, 23 of 23.

So *where the hit lands* is answered completely. Forty of the 83 monsters have
exactly one region, called `all`; the other 43 have a real part list.

A region carries, by `region_lv` (0 to 7, and the monster's own JSON declares
which level it is at):

```
  +0x9C   f32[8]   a flat modifier — negative on weak points, positive on armour
  +0x100  u32[8]   hit points
  +0xE4   f32[6]   six multipliers, near 1
```

The flat modifier reads as a **defence** on the strength of its signs —
`b11_00`'s belly is −450 while its thorns and legs are +500 — and nothing on
the disc proves it is subtracted rather than added. The six multipliers are six
of something and the six player classes are the disc's only six.

---

## 3. The numbers on each side, and the first real gap

### The monster's are all in its JSON, and they are complete

`hp`, `atk`, `def`, `cri`, `weight`, the `stg_*` family, `react_p`, the
`ab_*` status vectors, the hit-stop windows — **82 of the 83 monsters carry
every one of them** (`b08_00` ships no base record). See
[`params.md`](params.md).

### The player's are not in its JSON at all

`atk`, `def` and `hp` occur in **82 actors, and all 82 are monsters**. The six
player classes carry none of the three. What a class's JSON has instead is the
*shape* of the fight — how it moves, how long it flinches, how much critical
it gets — and the magnitudes come from equipment.

**They are in `it_db_weapon.bin`, and the table partitions exactly.** 450 rows,
pairing positionally with 450 names in `it_db_name_weapon.rmsg`:

| col | what it is | evidence |
|---:|---|---|
| 5 | the weapon kind | 0, 1, 3, 4, 5, 7 — **75 rows each, six values, 450 rows** |
| 3 | the attack | 48, 52, 75, 42, 35, 52 on the six starting weapons; 1..270 overall |
| 27 | a critical rate | `f32` 0..0.1, the same units as the class's `cri` |
| 2 | a tier | 216 / 84 / 84 / 66 |

```
    #  kind  atk   name
    0     0   48   Katar                   the assassin
    1     1   52   War Mace                the cleric
    2     3   75   War Hammer              the hammersmith
    3     4   42   Hunter Bow              the hunter
    4     5   35   Long Staff              the mage
    5     7   52   Two-Handed Sword        the warrior
  440     3  270   Rytha Mjollnir
  443     7  200   Rytha Balmung
```

Six classes, seventy-five weapons apiece, no row left over. The katar tops out
at 123 against the hammer's 270, which is what a two-handed weapon should read
next to a pair of daggers.

**The player's defence and hit points are still not located.**
`it_db_equip.bin` is 146 rows against 146 names and none of its nineteen
columns is named; column 16 (0..117, 68 distinct) is the only candidate shaped
like a defence. This is item 2 of the ledger.

---

## 4. Critical, and a trade the designers made in the open

Two fields, both per class, both differing across the six — which is already
worth noting, since 173 of a class's 225 fields are byte-identical on all six.

```
                          as      cl      hs      ht      mg      sw
  cri                     0.10    0.05    0.05    0.07    0.05    0.03
  dmg_critical_factor     0.10    0.25    0.15    0.10    0.20    0.30
  product               0.0100  0.0125  0.0075  0.0070  0.0100  0.0090
```

**The two run opposite, rank for rank.** The assassin crits most often and
gains least; the warrior crits least often and gains most. The rate varies by
3.3x across the six and the bonus by 3x, and the product varies by 1.8x — so
what the designers held roughly level is the expected contribution, and what
they varied is how it arrives. The weapon's column 27 adds to `cri`, which is
why a bow can carry 0.07 on top of the hunter's 0.07.

---

## 5. What the hit does back

### Stagger

Four fields, closed by [`params.md`](params.md) and unchanged by anything
here:

```
  stg_p     [7, 40, 80, 100]     thresholds, strictly ascending on 1,068 of 1,068
  stg_s_r   [1, 0.8, 0.5, 0]     small flinch
  stg_l_r   [0, 1, 0.5, 0]       large flinch
  stg_d_r   [0, 0, 0.2, 1]       knockdown
  stg_dec_s 0.8                  decay
```

**All six classes share all five exactly**, along with `react_p`, `stun_f`,
`down_f`, `down_stand_f`, `weight`, `guard_r` and the whole `ab_*` block. So
there is **one defensive model for the six classes and a per-class offensive
one** — the same split [`params.md`](params.md) found in locomotion, one step
further in.

`react_p` is a second pool of the same order as `stg_p[3]` and independently
tuned: the ratio between them runs 0.25 to 4.0 with no mode, and `b11_00`
carries **99999** against a `stg_p[3]` of 2,500, which is a designer writing
*never*. The tension tables name its currency —
`s_tension_revise_react_damage_tbl` — so react damage and damage are two
parallel quantities a hit produces, and only one of them is the health bar.

**Which one `+0x35` feeds is the open question of this section**, and there
are exactly two readings:

- **`+0x35` is stagger points, added directly.** It is coherent on the monster
  side: a monster's median 80 against the player's constant `stg_p` of
  `[7, 40, 80, 100]` is a large flinch, which is how this genre plays. It
  breaks on the player side: the player's median 6 would have to reach a
  monster's `stg_p[0]`, which runs from 70 to 3,500 — twelve hits on an Orc
  King and 580 on the largest.
- **`+0x35` is a per-record multiplier on a stagger value derived from damage.**
  This survives both sides, because a monster's `stg_p` tracks its `hp` — the
  log-log correlation over 82 monsters is **r = 0.826**, against 0.721 for
  `atk` — so a threshold that scales with the monster scales with the damage
  the player is doing to it by then.

The second is the one to build; the first is the one the byte's name would
suggest if it had one. Nothing on the disc separates them, and a runtime does:
put a body on the mesh, fire the record, and see whether a level-1 sword takes
twelve hits or one to make a boss flinch.

### Hit-stop, and a split that is exactly the naming convention

Two families, and their multipliers say which is which:

```
  stop_min / stop_max / stop_mul               1..3 / 6..12 / 0.003..0.006
  dmg_stop_min / dmg_stop_max / dmg_stop_mul   1 / 16 / 1
```

`stop_mul` is a thousandth, so its operand is a damage number in the hundreds
or thousands and the result is frames. `dmg_stop_mul` is **1**, so its operand
is already in frames — it is the value the attacker computed, clamped by the
receiver. That is a giver and a taker of the same quantity, and the field names
agree: `dmg_` is the prefix for taking damage everywhere else in the file.

**And the taker's side splits the bestiary perfectly.** `dmg_stop_mul` is zero
on 23 monsters and non-zero on 59:

```
  zero      b01_00 b01_01 b01_02 b02_00 b03_00 b05_00 b05_01 b07_00 b09_00
            b09_01 b10_00 b10_01 b11_00 b12_00 b13_00 b14_00 b15_00 b17_00
            b18_00 b18_01 b18_02 b19_00 b19_01                        23 of 23
  non-zero  z01_00 .. z27_01                                          59 of 59
```

Every `b*` and no `z*`. The disc's own prefix separates bosses from mobs, and
**a boss takes no hit-stop at all** — the frame-freeze that sells an impact is
a courtesy extended only to things that can be staggered. 82 of 82, no
exceptions, and no file says so.

---

## 6. The hit level, and two tables that agree about it

This is the part that came out best, and it started as *"`se_hitlevel_tbl`'s
middle word is a sound id and the disc does not say what the third selects"*.

### `se_hitlevel_tbl` tiles a range of cue ids exactly

The record is `(0, base, selector)` at stride 12. Across the six classes there
are **fifteen entries**, and their bases are:

```
  1000 1006 1012 1018 1024 1030 1036 1042 1048 1054 1060 1066 1072 1078 1084
```

Fifteen bases, six apart, **starting at 1000 and ending at 1084 — so they tile
1000..1089 with no gap and no overlap, and 1090 is where the monsters begin.**
That is a build-time allocation and it is what makes the next line a reading
rather than a guess. Resolving the six against `sound.cpk/common.acb`:

```
  1000  KATAR_DMG_S  KATAR_DMG_M  KATAR_DMG_L  KATAR_DMG_CS  KATAR_DMG_CM  KATAR_DMG_CL
  1006  SOMERSAULT_DMG_S  ..._M  ..._L  ..._CS  ..._CM  ..._CL
  1012  MACE_DMG        1018  SHIELD_DMG      1024  HOLY_DMG      1030  GODFIST_DMG
  1036  DRILL_DMG       1042  SCREW_DMG       1048  ARROW_DMG     1054  STAFF_DMG
  1060  FIRE_DMG        1066  GRAVITY_DMG     1072  THUNDER_DMG   1078  ICE_DMG
  1084  SWORD_DMG
```

**The block of six is three sizes and a critical flag**: `S M L` then
`CS CM CL`. So the impact cue is

```
  cue = base + size + 3 * critical           size in {0, 1, 2}
```

and the fifteen bases are the fifteen weapon kinds the six classes ship —
the assassin's katar and somersault, the cleric's mace, shield, holy and
godfist, the hammersmith's drill and screw, the hunter's arrow, the mage's
staff and four elements, the warrior's sword. The `C` prefix is a sound
designer saying *critical* out loud, which is the third place on the disc it is
named after `cri` and `dmg_critical_factor` — and the first that is not a
number.

### The monsters take a base inside a four-wide ladder

The 59 monster entries all carry selector 0 and a base drawn from the
hand-made group above 1090, where the ladders are `S M L LL` and four wide:

```
  base   n   what base+0..3 names                                  median atk
  1090  15   HIT_DMG_S    _M   _L   _LL                                   230
  1091   9   HIT_DMG_M    _L   _LL  _CS                                   165
  1092   9   HIT_DMG_L    _LL  _CS  _CM                       weight 100  260
  1097   1   SLASH_DMG_S  _M   _L   _LL                                    90
  1098  10   SLASH_DMG_M  _L   _LL  STRIKE_S                              192
  1099   5   SLASH_DMG_L  _LL  STRIKE_S  _M                               215
  1101   8   STRIKE_DMG_S _M   _L   _LL                                   110
  1102   2   STRIKE_DMG_M _L   _LL  FLAME_M                               188
```

A monster picks a **family** — blunt, slash, strike — and a **rung to start
from**, so a heavy monster's small hit sounds like a light monster's large one.
In the two families where the rung moves more than once it moves with the
monster's attack, monotonically (SLASH 90 → 192 → 215, STRIKE 110 → 188); in
HIT it moves with weight instead. The ladders run off the end of their family
by design, which is why `b*`-scale entries reach `HIT_DMG_CS` — and only 59 of
the 83 monsters carry the table at all.

### `eff_hitlevel_tbl` carries the key in the open, and it is the same three

Stride 40: four `(2, id)` pairs, a zero, and one packed word. **48 records over
the six classes, and the four pairs are identical on all 48** — four slots for
an axis this build does not use. The last word is two `u16`:

```
  0x0000_0001   level 0, kind 1
  0x0001_0001   level 1, kind 1
  0x0002_0001   level 2, kind 1
```

**Levels are exactly {0, 1, 2} and kinds are {1,2,3,4,5,7,8,10,13,14,15}.** So
the record is keyed `(level, kind)` and the effect id is just a row in the
class's own [`effect.bin`](format_effect.md) — which corrects the earlier
guess that the id was *"weapon kind × 10 + hit level"*. That formula fits the
hunter's 110/111/112 and is contradicted by the other five classes, whose
kind-1 triple is 101/102/103 under the same key. The ids carry no arithmetic;
the last word does.

Five classes carry three records — one kind, three levels. The hunter carries
33, eleven kinds by three levels, and its eleven kinds are arrow types:
`ht_arrow_tbl` sits in the same file.

**So the sound table and the effect table agree that the hit level has three
values**, S/M/L at effect scales 0.5, 0.8 and 1.0, and the sound table alone
adds the critical flag on top. Two tables written by different people for
different subsystems, meeting on the same enumeration, is the strongest kind of
evidence this disc offers.

**What computes the level is not on the disc.** It is a function of the damage
and it is the last thing in this document that a renderer could not fake.

### The bow's falloff, which is the only per-class version of any of this

Two more `(threshold, multiplier)` curves, in the hunter's file and nobody
else's, both closed by the gap to the next array:

```
  ht_react_revise_tbl   stride 8, 10 pairs
      (0, 1) (60, 0.9) (65, 0.8) (70, 0.7) (75, 0.6)
      (80, 0.5) (85, 0.4) (90, 0.3) (95, 0.2) (100, 0.1)

  ht_atk_revise_tbl     stride 12, 12 triples, third column 1.0 on all twelve
      (0, 1.1) (10, 1.1) (20, 1.1) (30, 1.1) (40, 1.1) (50, 1.0)
      (60, 0.9) (70, 0.8) (80, 0.7) (85, 0.5) (90, 0.3) (100, 0.1)
```

Both hold at or above 1 to half way and then fall to a tenth, on an axis that
runs 0 to 100. The bow being the only class with them says what the axis is:
**a fraction of the arrow's reach**, and the two curves say the reaction falls
off before the damage does. `ht_arrow_tbl` beside them is 42 records at a
stride of 80 — the repeat period says so and the fields read sensibly — and
its columns are not named.

---

## 7. Tension, and what it buys

Four tables, `(threshold, multiplier)` at stride 8. All four now read, and the
first thing to say about them is the thing a single class's file cannot: **the
thresholds are shared and the multipliers are not.** All four tables have the
identical threshold column on all six classes; three of the four have two to
four distinct multiplier profiles. Reading one class and reporting it as *the*
curve is a mistake this document made before `combat.py tension` printed the
six side by side.

```
  s_tension_revise_hp_tbl            4 pairs, one profile
    thresholds   0.1    0.25   0.5    0.75
    all six      2      1.5    1.25   1.1

  s_tension_revise_damage_tbl        13 pairs, four profiles
    thresholds   6     5     4     3     2     1.5   1.2   1     0.7 .. 0
    as           0.15  0.15  0.15  0.15  0.1   0.08  0.03  0     -0.2 .. -0.9
    hs, ht       0.25  0.25  0.25  0.25  0.15  0.12  0.1   0     -0.2 .. -0.9
    mg           0.3   0.3   0.3   0.3   0.2   0.15  0.1   0     -0.2 .. -0.9
    cl, sw       0.4   0.4   0.4   0.3   0.2   0.15  0.1   0     -0.2 .. -0.9

  s_tension_revise_react_damage_tbl  11 pairs, two profiles
    thresholds   1.1   1.3   1.5   1.75  2     3     4     5     6    7    10
    as           0     0.1   0.15  0.2   0.25  0.25  0.3   0.3   0.3  0.3  0.3
    the other 5  0     0.1   0.2   0.3   0.4   0.5   0.6   0.6   0.6  0.6  0.6

  s_tension_revise_tension_tbl       8 pairs, two profiles
    thresholds   2     1.5   1     0.5   0.25  0.1   0     -10
    as           1     1     1     1     0.85  0.75  0.5   3
    the other 5  5     4     1     1     0.85  0.75  0.5   3
```

The first three are *earning*: at a tenth of your health you earn twice as
fast; a hit at six times the expected damage earns between +0.15 and +0.4
depending on the class, and a hit at a tenth loses 0.5; react damage past 1.1
times the target's `react_p` earns up to 0.3 or 0.6. **The hp and damage curves
descend and the react one ascends**, so each is scanned in its own direction —
a thing to get wrong once.

**The class the whole system is tuned against is the assassin.** It earns
0.15 from the big hit where the two shield classes earn 0.4; it takes half the
react-damage rate everyone else does; and it is the only class that gets **no
bonus at all above a full meter** — 1.0 and 1.0 where the other five get 5.0
and 4.0. Three separate tables cut the same class, in the same direction, by
about half. It hits fastest and most often, and the tension economy is where
that is paid for. **The losing side of the damage table is identical on all
six** — from threshold 1.0 down, every class loses the same — so what the
designers varied is earning and not spending.

**And what tension buys is record 1 of the player's JSON.** [`params.md`](params.md) left
*"what records 1 and 2 of a player class are"* open, and a search of all 25,288
messages for *Fever* found nothing. The diff answers it structurally. Record 1,
on all six classes:

```
  run_sp        0.17 -> 0.22        acc      0.035 -> 0.1
  es_spd        0.58 -> 0.65        es_acc     0.4 -> 0.65
  stiff            1 -> 0           stiff_dmg    8 -> 0     stiff_act 8 -> 0
  stun_f    [90, 0] -> 0
  ab_*[0]          7 -> 9
```

Faster, evades harder, **takes no hit-stun and cannot be stunned**, and
resists every status better. That is not a difficulty tier and it is not a
weapon variant: it is an empowered state, and the only empowered state this
class file has any other machinery for is the one its four `s_tension_*`
tables fill the meter of. Written down as the reading it is, not as a proof.

Record 2 is a different animal. It changes **four fields, and the same four
with the same values on all six classes**:

```
  acc      0.035 -> 0.032     gr_brk   0.032 -> 0.029
  run_sp    0.17 -> 0.19      walk_sp   0.05 -> 0.045
```

Locomotion only, no combat field touched, identical across the roster — so it
is a global movement state and not a class ability. Which one, the disc does
not say.

---

## 8. Status

`ab_*`, ten five-element vectors, and their **order is the status id the engine
uses** — settled off `isAbnormal(1, 3)` being the player frozen, see
[`format_api.md`](format_api.md):

```
  0 ab_pss  1 ab_psl  2 ab_prl  3 ab_frz  4 ab_brn
  5 ab_nrv  6 ab_ten  7 ab_tir  8 ab_atd  9 ab_dfd
```

Element 0 is the resistance threshold (7 on a player, 9 under tension); the
other four are unread. What the loop needs beyond them is in the same file as
scalars, and those are plain: `ab_poison_dmg 25`, `ab_dpoison_dmg 40`,
`ab_burn_dmg 60`, `ab_nervous_tension_dmg 0.01` every
`ab_nervous_tension_dmg_interval 30` frames, `ab_freeze_min_f 45`,
`ab_atkdown_factor -0.5`, `ab_defdown_factor -0.5`. So **what a status does is
readable; what applies one is not** — no field in the hit record and no column
in the weapon table carries a status id.

---

## The ledger

What a working combat loop needs and the disc does not give. Nine items, in
the order they would block an implementation.

1. **The damage formula.** Every input is on the disc — the weapon's attack,
   the monster's `def`, the region's flat modifier and six multipliers, `cri`
   and `dmg_critical_factor` — and the expression combining them is not.
   Nothing on the disc constrains it beyond the ranges. **EBOOT.**
2. **The player's defence and hit points.** Absent from all six class JSONs.
   `it_db_equip.bin` is 146 rows against 146 names with nineteen unnamed
   columns; column 16 is the only defence-shaped one. **Readable from the
   disc — an `ECH` column-naming job, the same one §5 of the TODO already
   owns.**
3. **What `+0x35` is a strength of** — stagger points or a multiplier on a
   damage-derived value. §5 gives the measurement that separates them and the
   disc does not contain it. **A runtime settles this; the EBOOT settles it
   sooner.**
4. **What computes the hit level.** Three levels, both consumers agree on
   three, and the function from damage to 0/1/2 is nowhere. **EBOOT.**
5. **The sign convention of a region's flat modifier**, and what its six
   multipliers are six of. **EBOOT, or a runtime with a monster that has one
   weak point.**
6. **What applies a status.** No hit-record field and no weapon column carries
   a status id, and the `ab_*` vectors' four unread elements are the obvious
   place for the resistance side of it. **Readable if the id turns out to be
   one of `it_db_weapon.bin`'s unnamed columns.**
7. **`se_hitlevel_tbl`'s third word** on the player side — 0, 1, 2, 3, 4, 5,
   6, 7, 8 across the fifteen entries, per class rather than global, and it
   must be what a weapon or a skill declares to pick its block. It is not
   `it_db_weapon.bin` column 5, whose six values are a different space.
   **Readable — one more join, against the skill table.**
8. **`react_p`'s currency.** A pool of the same order as `stg_p[3]`,
   independently tuned, named by one tension table and consumed by nothing
   else the disc shows. **EBOOT.**
9. **The eleven arrow kinds and 42 arrow records.** `ht_arrow_tbl`, stride 80,
   columns unnamed; `eff_hitlevel_tbl` says which eleven of them matter.
   **Readable.**

Four of the nine are ordinary disc work and five want the EBOOT — and all five
of those are one function each rather than a subsystem, which is the same
answer [`STRATEGY.md`](STRATEGY.md) has been converging on since session 10:
what is left inside the binary is **the combat loop and the implementations**,
and this document is the list of which ones.

---

## What this settled

Seven things, none of which needed a new format:

- **the player's impact sound is computed and the monster's is authored**, and
  the two never touch each other's cue range — 747 of 754 against 5,245 of
  5,439, and 0 of 6,193 in 1000..1089;
- **`se_hitlevel_tbl` tiles 1000..1089 exactly**, fifteen weapon kinds six cues
  apart, and the six are **three sizes and a critical flag**;
- **`eff_hitlevel_tbl` is keyed `(level, kind)` in its last word**, levels
  {0,1,2}, which corrects the *"kind × 10 + level"* reading of the ids;
- **a boss takes no hit-stop** — `dmg_stop_mul` is zero on exactly the 23 `b*`
  and non-zero on exactly the 59 `z*`;
- **the player's attack is `it_db_weapon.bin` column 3** and its kind is column
  5, which partitions 450 rows into six classes of 75;
- **record 1 of a player class is an empowered state**, plainly: no hit-stun,
  no stun, faster, better resistances — and record 2 is a global locomotion
  variant identical on all six;
- **the tension curves share their thresholds and not their multipliers**, and
  three of the four cut the assassin by about half in the same direction.

The last of those is also the correction, and it is worth saying how it
happened. This document first wrote *"four tables, identical across all six
classes"* — [`format_elbn.md`](format_elbn.md) said so, and one class's file
does read that way. Then `combat.py tension` was written to reproduce the
figure, printed all six, and the claim fell over in its first run. **The tool
was written to confirm the document and it corrected it instead**, which is
the argument for writing the tool.

And one method note, the same one this repository keeps re-learning. Every
finding above came out of **joining two tables that were each already read**.
The cue names had been printed since session 9 and the `se_hitlevel_tbl` bases
since session 19, and nobody had put the two lists side by side; when they went
side by side the answer was a single subtraction. Laying a chain out end to end
is not bookkeeping — it is the cheapest instrument in the box.
