# Milestone 4 — the player fights back

**Status: reached, session 23.** A class presses a button its own graph
accepts, plays the animation that graph names, and the hit records on that
animation **land on a named part of a monster's body** — while on the same
stage, in the same loop, the monster decides out of its tables and lands its
own records on the player's. [`milestone_fight.md`](milestone_fight.md) ended
with *the player does not fight back*. It does now, and the last thing between
here and a working combat loop is the damage expression, which is the EBOOT's.

Nothing here is new data either. Every link was read in an earlier session out
of a different file: the hit record in session 13, its geometry in 17, the
bones that turn it in 19, `col_hit` and `region_data` in 19, the animation in
7. What is new is one table that had never been read — the player's own
decision — and the join that puts a volume on a body part.

Code: [`../engine/player.py`](../engine/player.py), and
[`../tools/elbn.py`](../tools/elbn.py) `combo` for the table.

```
python tools/elbn.py   combo  extract/tree [class]
python engine/player.py combo  extract/tree sw
python engine/player.py swing  extract/tree sw ssssl b01_00
python engine/player.py swings extract/tree [hold]
python engine/player.py parts  extract/tree
python engine/player.py arrows extract/tree
python engine/player.py reach  extract/tree
python engine/player.py duel   extract/tree 010_01_01 AI_B01_OrcKing sw
python engine/player.py duels  extract/tree sw
```

## The chain, the other way round

    a button               s_combo_graph            format_elbn.md  s23
      -> a node            an edge, in its window   format_elbn.md  s23
      -> a motion id       the node's own           format_elbn.md  s23
      -> an animation      f<class><id><verb>.CNOM  format_cnom.md  s7
      -> an event list     <class><id><verb>.anmcmd format_anmcmd.md s13
      -> a hit volume      a flag and three vectors format_anmcmd.md s17
      -> turned by its bone                         format_anmcmd.md s19
      -> a `col_hit` capsule of the target          format_elbn.md  s19
      -> the region that owns that capsule          format_elbn.md  s19

The monster's chain in [`milestone_fight.md`](milestone_fight.md) ends at *a
body on the collision mesh*, because the player was a cylinder there. This one
ends two links further on, at a **named part**, because the target has
`region_data` and the cylinder did not.

## The player decides, and the decision is a table

`s_combo_graph` sits in every class's `objbin.bin` and had never been opened.
It is the player's `ProbList`: **189 nodes and 266 edges over the six
classes**, each node a motion, each edge a button, a target node and the frame
window the input is taken in. The format is in
[`format_elbn.md`](format_elbn.md).

Node 0 is the neutral state, it has exactly six edges on all six classes, and
**those six name the same six motions on all six**: 311, 361, 362, 391,
397/398/399 and 396 — three on the ground and the same three in the air.

Two things check it, and neither is the table checking itself.

**The id arithmetic.** The list for the combo `ssl` is called
`<class>343at_ssl`, and `343` reads as `3AB` with `A = 6 - the leading
squares` and `B = the buttons pressed`. That reading comes off the *names*;
the graph never mentions one. They agree on **112 of 116 edges**, and the four
that do not are the mage's four specials, which occupy a four-id block where
everyone else has one id — so the branch digit is right on 116 of 116 and only
the depth runs one past.

**The just window.** Some edges carry a second, narrower window inside the
first. The disc separately ships `_just` copies of some animation lists.

```
                _just lists   the target of an edge with a second window
  hammersmith             6                                           6
  warrior                 8                                           8
  the other four          0                                           0
```

**14 of 14 in both directions.** The second window is the perfect-timing
input, and the four classes with no `_just` animation have no edge carrying
one.

And the graph says something the names cannot: **it is not a tree**. `at_sl`
on square leads to `at_sss`, not to an `at_sls` that does not exist — the
node's depth is how many hits have landed, so a triangle spent at hit two puts
the next square at hit three. Five separate nodes of the warrior lead into
`at_sssss`.

## Where a blow lands

```
python engine/player.py swing extract/tree sw ssssl b01_00

sw (warrior, two-handed sword) against b01_00: 11 capsules, 4 regions,
   2 breakable
  the player stands 1.90 m away, col_r 0.50 against col_r 1.40, and presses
     s s s s l
  1. sw311at_s     motion [311], 32 frames, window 0..255
      f4   slot 0 sphere r 1.20 -> misses by 0.36 m, nearest body
  2. sw312at_ss    motion [312], 34 frames, window 6..18
      f5   slot 0 sphere r 1.30 -> hits Leg_L   capsule 9 on node_l_calf
  3. sw313at_sss   motion [313], 26 frames, window 6..24
      f6   slot 0 sphere r 1.20 -> hits Leg_R   capsule 7 on node_r_calf
  4. sw314at_ssss  motion [314], 38 frames, window 6..18
      f6   slot 0 sphere r 1.30 -> hits Leg_L   capsule 9 on node_l_calf
  5. sw325at_ssssl motion [325], 46 frames, window 2..18, just 8..14
      f16  slot 1 sphere r 1.00 -> misses by 0.18 m, nearest Leg_R
      f18  slot 0 sphere r 1.30 -> hits Leg_R   capsule 7 on node_r_calf
```

Five presses, each one an edge the disc's own graph offers, each with its own
input window and — on the fifth — its just window. Four volumes on the
OrcKing's calves, named by `region_data`, addressed through the capsule index
`region_data` lists positionally.

## The measurements

### The parts are where their names say they are

This is the check behind *which capsule a blow lands on*. `region_data` gives
a part an English name and a list of capsules; nothing in the file says a part
called `HEAD` sits near the top of the body. The capsules are geometry, the
names are language, and they were written by different hands.

```
python engine/player.py parts extract/tree

82 monsters, 1136 capsules, 1122 of them owned by a named part
  where each word sits, as a fraction of the body it is on:
    head   112 capsules   mean 0.70   median 0.72
    wing   133 capsules   mean 0.68   median 0.67
    body   248 capsules   mean 0.51   median 0.52
    tail    55 capsules   mean 0.44   median 0.44
    arm    198 capsules   mean 0.38   median 0.41
    leg    199 capsules   mean 0.19   median 0.14
  and within one monster at a time, which is the test:
    head  sits above leg   on 22 of the 22 monsters that have both
    body  sits above leg   on 32 of the 32 monsters that have both
    arm   sits above leg   on 25 of the 28 monsters that have both
    wing  sits above leg   on  8 of the  8 monsters that have both
    head  sits above body  on 20 of the 26 monsters that have both
    head  sits above tail  on 12 of the 12 monsters that have both
```

The comparison is **inside one monster**, so a 35 m boss and a wolf are never
put in one column and what is counted is a sign. Four of the six pairs are
unanimous, and the two that are not are the two pairs that sit next to each
other on the animal - a head against a body, an arm against a leg - which a
creature on four legs can put either way round. The 28 words the reader's table has no family for are equipment —
`SHIELD1`, `HUMAN_SKIRT1`, `R_SWORD`, `LANCE`, `FUR` — which is its own small
finding: a monster's shield is a part you can hit.

### Six classes against every monster on the disc

One posture, one distance, no dodging on either side. The player stands at
`col_r + col_r`, both numbers off the two JSONs, which is as close as two
capsules get.

```
python engine/player.py swings extract/tree

82 monsters with a body, 1136 capsules in all, 1122 of them owned by a region
  as  assassin      28 lists,  100 volumes: reaches 71 of 82, 6725 landings
       misses 11, nearest b09_01 0.07 m, b09_00 0.08 m, b10_00 0.17 m
  cl  cleric        32 lists,   47 volumes: reaches 76 of 82, 3179 landings
  hs  hammersmith   21 lists,   39 volumes: reaches 76 of 82, 1408 landings
  ht  hunter        28 lists,  353 volumes: reaches 82 of 82, 3401 landings
  mg  mage          44 lists,   54 volumes: reaches 76 of 82, 3410 landings
  sw  warrior       28 lists,   45 volumes: reaches 76 of 82, 2918 landings
  457 of 492 class-monster pairs land a blow

  where the blows land, over the whole disc:
     10505  all              3349  body              1295  -
      1103  BODY              782  foot_r             541  foot_l
       498  Leg_R             393  HEAD               268  LEG_R_F  (breaks)
    21041 landings in all, 1002 of them on a part that breaks off,
    1295 on a capsule no region owns
```

**457 of 492**, and the misses are the same population the monster side
missed from the other direction: `b18` at `col_r 15.0`, `b14` at 35 m tall,
`b17` at 9.7 m. Standing at `col_r + col_r` from a boss whose `col_r` is a
push radius and not a reach puts the player outside its limbs. Halving the
standoff moves it to **486 of 492**, and the only two left are the two forms
of `b18`, missed by 0.42 to 0.95 m; doubling it gives 422. That is the whole
sensitivity, and it behaves the way a geometric reading should.

The assassin's eleven misses are the other end of the same story: the shortest
weapon on the disc, missing by 0.07 m.

### The reach is the weapon's

`fight.py reach` put `_act.par`'s range beside the reach of the hit volumes on
the same action's motion, because nothing on the disc said what that range
measured. The player has no `_act.par`, so the question turns around: **the
volumes are the known quantity, and what they can be checked against is the
object the class is holding.**

A melee volume hangs off `node_r_weapon`; so does the weapon model. The volume
is an `.anmcmd` under `job.cpk`, the weapon a `CMDL` under `character.cpk`,
and the only thing they share is the bone.

```
python engine/player.py reach extract/tree

     class        weapon            off the weapon bone   the weapon itself
as   assassin     katar              89 vols, med 1.82    26 models, med 0.77
cl   cleric       mace               39 vols, med 2.11    25 models, med 1.09
hs   hammersmith  hammer             34 vols, med 2.35    26 models, med 1.44
ht   hunter       bow               none                  25 models, med 1.22
mg   mage         staff              18 vols, med 2.51    26 models, med 1.32
sw   warrior      two-handed sword   37 vols, med 2.43    26 models, med 2.08

  correlation 0.772 over the 5 classes that have both, and 5 of the 120 ways
  the classes could have been paired with the weapons do as well or better
```

Five classes is few, so the control is **every one of the 120 pairings** and
not an approximation to one. It is also the right shape: the volume is
consistently longer than the weapon, because a hit volume is generous and an
arm is in front of the grip.

Beside it, `cmb_hmg_search_angle` — how wide a cone the class looks for a
target in — against the angle its volumes actually sit at:

```
    30 deg -> 0.0 0.0 5.2;   90 deg -> 26.6 35.8;   120 deg -> 77.1
```

**The three bands do not overlap.** Spearman 0.939, and 12 of the 720
pairings do as well or better — which is exactly the floor the ties in the
JSON put there, so no pairing does better than the disc's own. Dropping every
volume within half a metre of the body leaves it unchanged.

### The hunter's damage leaves the bow

The hunter is the class that does not fit, and it fails in a way that explains
itself. Its combo nodes carry almost no hit record and it fires nothing off a
weapon bone at all. Its damage is in lists named with a bare number, and the
number is `1` + the motion + an optional variant digit: `ht1311` and `ht13110`
to `ht13114` for motion 311. Of the **28 graph nodes that name a motion, 25
resolve to an arrow list by that rule** and the other three carry a list of
their own, so all 28 fire something.

How those move is `ht_arrow_tbl`, 42 records at a stride of 80, whose columns
[`format_elbn.md`](format_elbn.md) said were not named. They are now:

```
python engine/player.py arrows extract/tree

ht_arrow_tbl: 42 records of 80 bytes, 15 distinct flights
  rows  life   speed     gravity   pitch    it covers
  18    13     1.64      -0.060    0.0      21.3 m
  4     30     0.00      0.000     -90.0    0.0 m
  3     9      1.56      -0.070    0.0      14.0 m
  ...
  37 of the 42 rows move: they cover 6.0 to 96.0 m, median 21.3
    and the class asks for a target inside `cmb_hmg_search_radius` = 20.0 m
  4 of the 5 that do not move carry pitch -90 - straight down
```

**A speed times a life is a distance**, and the hunter's own JSON asks for
targets inside 20 m. The rows that do not move point straight down, and the
hunter is the class whose skill list holds `landMineBuleltParam`,
`claymoreTrapBuleltParam`, `freezingTrapBuleltParam` and `flasherParam`.

Which of the 42 rows a given list uses is not joined — the id is presumably in
one of the thirty unread `.anmcmd` opcodes. What that costs here is nothing,
because every moving row passes a body 1.5 m away within three frames, so the
choice cannot change which capsule an arrow lands on. Under it the hunter
reaches **82 of 82**.

### Both halves at once

```
python engine/player.py duel extract/tree 010_01_01 AI_B01_OrcKing sw

sw (warrior) against AI_B01_OrcKing on 010_01_01
  the player closes to 1.90 m - col_r 0.50 and col_r 1.40 - and runs its
     combo graph from node 0
  the monster has 11 capsules over 4 regions and 2 breakable parts

  900 frames = 30.0 s
  the player started 26 attacks, fired 26 volumes and landed 26
       10x  Leg_L      10x  Leg_R      6x  body  (breakable)
  the monster fired 16 hit records at the player and landed 8, on its 2
     capsules
        8x  node_hip
```

Both directions use the same function on the same record: `col_hit`, placed by
the bone it names, tested against a volume by the distance between two
segments. The player's body is the two capsules on `node_hip` that
[`hitbox.py`](../engine/hitbox.py) used to settle the turned-versus-carried
reading — the upright cylinder `milestone_fight.md` stood in for is gone.

Over the whole disc:

```
python engine/player.py duels extract/tree sw

sw (warrior) duelled 83 monsters on 010_01_01 for 900 frames each, 0 skipped
  the player landed on 71 of them, the monster landed on the player in 44,
     and **both landed in 38**
  2138 volumes fired by the player, 1662 landed; 1868 fired by the monsters,
     492 landed
  1662 landings on 22 distinct parts, 76 of them on a part that breaks off
```

**38 of 83 fights have a hit landing both ways** in the same thirty seconds,
on a real stage, with each side reading only its own tables.

## What this does not do

**There is no damage.** [`combat_loop.md`](combat_loop.md)'s ledger still owns
the expression and it is one of the five items that needs the EBOOT, so a hit
is a connection and not a number — on either side now, rather than on one.

**The player presses a fixed string.** It walks its graph from node 0 pressing
square five times and starting again. That exercises the table; it is not a
policy, and nothing here chooses between `sssss` and `ssl` for a reason.

**Neither body is animated while it is being hit.** Attacks are posed by their
own `CNOM`; the `col_hit` capsules being hit are the rest pose on both sides,
which is what `hitbox.py body` settled as body-sized and upright. A monster
that ducks is not modelled, and neither is a player who does.

**No guard, no evade, no hit-stun.** The class JSONs have `guard`, `guard_r`,
`es_*` and `stiff*` and none of them is read here. A landed hit changes
nothing about what either side does next.

**The input windows are not enforced.** Each edge says which frames its press
is taken in, and the loop presses when the previous motion ends. Enforcing
them needs a controller, and a controller needs a reason to press.
