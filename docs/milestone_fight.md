# Milestone 3 — a monster fights

**Status: reached, session 22.** An Orc stands on the spawner `010_01_01`
declares for it, a body with the player class's own parameters runs at it, and
the Orc reads its own decision tables, picks a group, rolls an action out of
that group's weights, closes when the action's own gate says it is too far,
plays the animation the action names, and **fires the hit records on that
animation into a volume that reaches the player**.

Nothing in that sentence is new data. Every link was read in an earlier
session, out of a different file, by a different tool. What is new is that
they are joined end to end and the join is measured.

Code: [`../engine/brain.py`](../engine/brain.py), the decision, and
[`../engine/fight.py`](../engine/fight.py), what it turns into.

```
python engine/brain.py terms  extract/tree [trials]
python engine/brain.py agree  extract/tree [trials]
python engine/brain.py decide extract/tree AI_B01_OrcKing
python engine/brain.py check  extract/tree
python engine/fight.py fight  extract/tree 010_01_01 AI_Z01_Orc
python engine/fight.py fights extract/tree
python engine/fight.py reach  extract/tree
python engine/fight.py chain  extract/tree
```

## The chain

    a rule                 SelectScript.dat         format_ai.md    s11
      -> a group           ProbList.dat             format_ai.md    s11
      -> an action         a weighted roll          format_ai.md    s11
      -> a motion id       action + 200/401/301     format_ai.md    s12
      -> an animation      <prefix><id><name>.CNOM  format_cnom.md  s7
      -> an event list     <kind>_<id>.anmcmd       format_anmcmd.md s13
      -> a hit volume      a flag and three vectors format_anmcmd.md s17
      -> turned by its bone                         format_anmcmd.md s19
      -> a body on the collision mesh               milestone_numbers.md s14

Eight sessions, eight files, one chain. `fight.py chain` walks it over every
monster on the disc:

```
83 monsters, 1419 distinct actions their tables can pick
  1109 name a motion in their own pac
  683 of those have an `.anmcmd`, 545 of which carry a hit record
   432  motion with no event list
   304  action that names no motion
   138  motion with an event list and no hit
```

## One fight

```
python engine/fight.py fight extract/tree 010_01_01 AI_Z01_Orc

AI_Z01_Orc on 010_01_01: the monster stands on emgen_pos01, 12.6 m from appear01
  z01_00: col_r 0.80, run_sp 0.125, rot_y_spd 22.5, 41 groups, 14 actions gated
  the player closes to 2.50 m, the shortest range its `_act.par` gates an
     action at

  900 frames = 30.0 s, 26 decisions, 12 motions played, 6 approaches
  20 actions started inside their own `_act.par` gate, 3 put off because the
     target was beyond it
  17 hit records fired, 12 of them reaching the player; the nearest miss
     passed 0.82 m off the capsule
    frame   56  at1        motion 501 slot 0 at 2.48 m, radius 1.00
    frame  206  at3        motion 503 slot 0 at 2.48 m, radius 1.00
  the actions it chose:
      8x  action 5    motion 205  (none)     gate 8.00 m
      5x  action 100  motion 501  at1        gate 2.50 m
      5x  action 102  motion 503  at3        gate 3.00 m
      2x  action 202  motion 503  at3        gate -
```

**Where the player stands is the monster's own number too.** It closes to the
shortest range that monster's `_act.par` gates an action at - 2.50 m here -
because that is where the tables say its melee lives. Standing further out
than every gate would be a fact about the player and not about the monster.
The Orc's two attacks are gated at 2.50 and 3.00 and it starts them at 2.48,
so both are inside their own range when they fire, and 12 of the 17 records
they fire reach the body. The
`202` in the last row is the `2xx` block that document lists as open: it
resolves to the same `at3`, one hundred lower, and the fight shows the tables
picking both ids for the same animation.

## The measurements

### The disc's own term dispatch, run beside this project's

`check_converted_xml_term` in the six `.cnut` is a switch on the 76 term ids,
byte-identical in all six. With a VM it stops being documentation. `brain.py
terms` binds the same host predicates under both evaluators and compares them
on **every one of the 458 `(term, operand)` pairs the 144 decision files
actually use** — comparing on inputs the disc never presents would be a test
of nothing — in 20 random states, both polarities:

```
458 distinct (term, operand) pairs on the disc over 76 terms
15040 comparisons, 0 disagreements
```

Two outcomes are not agreement or disagreement, and both are findings:

- **term 103 throws.** `check_term_param(isDowned(), param)` compares the flag
  against the operand, and Squirrel refuses to compare a bool with an integer.
  Five instructions on the disc pass a non-zero operand there;
- **term 115 is never true.** `ret = getPartsDamageCount(param)` leaves an
  integer where the next line writes `ret == cond` against a boolean, and
  Squirrel's `==` is false between types. 47 instructions use it.

Both read cleanly if the engine's own `isDowned` and `getPartsDamageCount`
return numbers rather than flags — which is what the names say, and what the
engine here assumes.

### The chance term, settled by making both sides run

The dispatch writes term 8 as `getRand() * 100 < param`. `getRand()` returns 0
to 10,000: `prt_select` normalises its weights to 10,000 and rolls against
them, and [`format_merc.md`](format_merc.md) says the same of the mercenary
side. Under that form a 20% chance fires only on a roll of exactly zero.

The OrcKing's own hand-written branch for the same rule reads `getRand() <=
2000` against a table operand of 20, which is `rand <= param * 100`.

`brain.py agree` drives the table and the script from the same state and the
same roll:

```
                           comparable    include     engine
  AI_B01_OrcKing              300/300    217/300    293/300
```

**217 against 293.** The include is the converted artefact and the branch is
what a person wrote, so the engine uses the second and the difference is the
argument.

The other five do not give the same check, and the disc says why. `b18`'s two
variants **share a `SelectScript` and a `ProbList` byte for byte and ship
different `.cnut`**, so at most one of them can match; and those scripts pick
three-digit `prt_N` — `prt_150`, `prt_158`, `prt_164` — that their own
`ProbList` has no group for at all, on 180 of 300 states.
[`format_ai.md`](format_ai.md) said the tables are the newer artefact; this is
what that looks like from the running side.

### `_act.par`'s range is a range to the target, and the swing says so

This is the join the milestone is really about. `_act.par` gives every action
one distance and **nothing on the disc says what it measures**. The `.anmcmd`
of the motion that same action names says how far its hit volumes get from the
body — a different file, read by a different tool, in the same metres.

```
python engine/fight.py reach extract/tree

83 monsters, 250 actions with a real range in `_act.par` and a hit record
             on their motion
  the gate runs 1.20 to 99.00 m, median 7.50; the reach 0.71 to 76.71,
             median 4.39
  correlation 0.590 over 250 pairs
  the same pairs reshuffled 200 times: 0.051 on average, 0.231 at the best
```

**0.590 against a shuffled control of 0.051**, and the control matters: two
columns of distances will correlate a little whatever happens, and 200
reshuffles say how much. So the range is a distance to the target in the same
units as the blow that follows it.

It is also systematically the longer of the two — the reach is shorter than
the gate on 171 of the 250 — which is what a gate on *starting* an attack
should be. The monster commits at a distance where the wind-up will still be
worth it.

### Every monster, on one stage

```
python engine/fight.py fights extract/tree
```

One stage and one player class, so the only thing that varies is the monster:
its tables, its motions, its hit records and its JSON.

```
83 monsters fought on 010_01_01 for 900 frames each, the player closing to
1.0 of the shortest range that monster gates an action at, 0 skipped
  73 played a motion, 61 fired a hit record, **37 reached the player**
  46 never landed one, 8 of which came within a metre:
    AI_Z16_Leshy             11 motions,  13 hit records, nearest 0.02 m
    AI_Z12_Raydric           15 motions,  27 hit records, nearest 0.14 m
    AI_Z04_ScorpionFish      14 motions,  15 hit records, nearest 0.19 m
    AI_B15_Surt               3 motions,  16 hit records, nearest 0.34 m
    AI_Z24_Gagapu_1          13 motions,  36 hit records, nearest 0.49 m
    AI_Z05_Wolf              11 motions,   1 hit records, nearest 0.55 m
    AI_B19_LordOfDeath        7 motions, 103 hit records, nearest 0.67 m
```

**37 of 83 land a blow on a capsule that does not dodge, does not block and
is not animated**, and eight more pass within a metre of it — two of them
within a fifth. That distribution is the point. A reading that were wrong
anywhere along the chain would not produce near misses; it would produce
volumes somewhere else entirely, and the nearest-miss column would be tens of
metres rather than 0.02.

The remaining misses are mostly the largest bosses, and the reason is the
player and not the monster: `AI_B19_LordOfDeath` has `col_r 15.0` and puts its
volumes between 9 and 25 metres off the ground with radii up to 14, so what it
swings at is a body far bigger than a 1.6 m cylinder standing still. Pressing
the capsule in to 0.6 of the gate instead of 1.0 moves the count from **37 to
42** and changes nothing else, which is the sensitivity to where the player
stands and is exactly what one would expect it to be.

Ten monsters never play a motion at all in thirty seconds: their tables pick
actions whose motion has no `.CNOM` under that monster's prefix. That is the
`chain` count above showing up as behaviour.

## What the AI asks, and how much of it the engine now answers

The monster interface is 51 host functions, 50 of them inside the 285 that
[`format_api.md`](format_api.md) enumerates. [`brain.py`](../engine/brain.py)
answers all 50 out of one `State` object, because that is what the interface
is: forty-odd questions about a fight.

With [`host.py`](../engine/host.py)'s 66, **115 of the 285 now do the work
rather than record the call — 18,435 of the 25,699 calls the disc makes.**

Where each answer comes from is written down rather than blurred, in
`State.SOURCE`: `world` where the engine computes it from geometry or the
clock, `table` where it comes off a file, and `default` where nothing here
knows yet. Two of the readings are this engine's rather than the disc's and
are marked in the source:

- **`getAngleTypeToTarget` returns 213 or 214 and `getAngleTypeAtTarget`
  returns 215 to 218**, because the dispatch compares each against the term's
  own id — two bands and four. That *to* is the target in my frame and *at* is
  me in the target's is the names' reading, and the disc does not declare it;
- **`checkRangeParam` returns 0, 1 or 2** and `_act.par` gives every action
  one range: inside it, beyond it, beyond twice it. The disc says only that
  the three values are distinct, because `AI_B12_Fenia` ORs 0 with 2.

## What this does not do

**There is no damage.** [`combat_loop.md`](combat_loop.md) ends in a ledger of
nine and the damage expression is one of the five that needs the EBOOT, so a
hit here is a **connection** and not a number, and the monster's hit points
are an input to the run rather than something the run takes down. The AI's
`hp_rate` ladder therefore only runs at whatever level the run is given.

**The player does not fight back.** It runs at the monster and holds at arm's
length, which is enough to put a target in front of the tables and no more.

**The ten unnamed terms are still unnamed** — 1,094 instructions — and the
seven per-boss escape hatches (`checkB01Term` and its six siblings, 458
instructions across nine tables) are host functions that nothing on the disc
defines, which is the same shape of hole as `prowl_script`. A rule that needs
one of them fails here rather than guessing.
