# Parity — everything the engine supplies and the disc does not

*The goal of this project is the original game. This document is the list of
every place where what runs is not yet what shipped, so that the list is a
thing to be shortened rather than a set of decisions quietly settled.*

---

## Why this exists

[`actor.py`](../engine/actor.py) opens with a paragraph headed *"What the disc
does not say, and what is assumed instead"*, and every engine file written
since has copied the habit: a constant that came out of the game is cited, a
constant that did not is declared at the site with the reason. That habit is
good and it has one failure mode: the declarations are spread over thirteen
files in [`../engine`](../engine) and nobody can see the set. A stand-in that
is honestly marked in a docstring is still a stand-in, and after eight
milestones it is easy to mistake *"we said so at the time"* for *"this is
fine"*.

So: one page, four classes, and a rule for each about what retires it.

**A stand-in** is wrong by construction. The disc has the thing, this
repository cannot read it, and a number stands where it goes. A stand-in
produces a value the game would not produce. **These are the parity blockers**
and there are seven.

**A reading** is an interpretation of a field the disc really does have,
adopted because it fits, with no second witness yet. It may well be right;
nothing here proves it. Three — it was five when this page was written, and
the EBOOT retired two of them the same day.

**A convention** is a choice the disc does not make at all and an
implementation must. There is no right answer to recover — only a
defensible one — and a wrong one is usually visible. Thirteen.

**Scaffolding** is not wrong. It stands where player input goes and it
disappears the moment there is a pad. Eight, listed only so that they are
never counted among the first three.

Everything under [`../tools`](../tools) is out of scope: a reader either
matches the bytes or does not, and the format documents carry their own
leftovers.

---

## 1. Stand-ins — seven, and three of them are one missing function

| | what | where | what it stands in for |
|---|---|---|---|
| S1 | `BLOWS = 3` | [`mission.py`](../engine/mission.py) | the damage formula |
| S2 | `BREAKS = 2` | [`purse.py`](../engine/purse.py) | the same, for a part |
| S3 | reward kind 0 | [`purse.py`](../engine/purse.py) | what picks between kinds 0, 2 and 3 |
| S4 | `RESUME`'s frame counts | [`host.py`](../engine/host.py) | how long the host holds a blocked script |
| S5 | 214 of 285 script calls return 0 | [`host.py`](../engine/host.py) | their implementations |
| S6 | 28 of 47 AI predicates answer with a default | [`brain.py`](../engine/brain.py) | the state of a fight that tracks damage |
| S7 | `PROGRESS = 11000` | [`purse.py`](../engine/purse.py) | a save file |

### S1, S2 — a monster dies on its third landed volume

The most conspicuous invention in the repository and the one the run prints
every time it finishes:

```
a monster dies on the 3 landed volumes and a part comes off on the 2 -
this run's policy, not the disc's
```

Every input to the real answer is on the disc and read. The weapon's attack is
`it_db_weapon.bin` column 3; the monster's `hp` and `def` are in its own JSON,
now at the right difficulty tier; the region's flat modifier and its six
multipliers are in `region_data`; `cri` and `dmg_critical_factor` are in the
class table. What was missing is the **expression**, which is
[`combat_loop.md`](combat_loop.md) ledger item 1.

**Session 31 read it** — `FUN_00622fe4`, in full, in [`eboot.md`](eboot.md) —
**and then read item 2 as well**: the player's base attack, defence and hit
points are `misc.cpk/ccparamobj.bin`, six tables of fourteen rows, chosen by
story progress, and `python tools/elbn.py levels extract/tree` prints them.
So every input to the expression is now on the disc and read, and the
expression is written down.

The stand-in is still here, because **reading a formula and running one are
different things**. What is left is implementation: the engine has to build
the two structures, apply the listener chain, subtract, and let a monster's
own `hp` come down. That is a session's work and it wants the full sweep
afterwards, since `BLOWS` reaches the kill count, the arena timing and the
pay-out.

Until it is read, a monster's hit points are an *input to the run* rather than
something the run takes down, and the kill count — which is what closes an
arena, and which the script counts for itself — is driven by a threshold this
repository chose. **Everything downstream of a kill inherits the stand-in**:
the arena timing, the pay-out, and the two headline numbers in
[`milestone_walk.md`](milestone_walk.md).

*Retired by:* nothing further to read. Ledger 1 and ledger 2 were both read
in session 31; what remains is writing it into
[`fight.py`](../engine/fight.py) and re-running all 431 quests.

### S3 — the pay-out draws kind 0

Byte 7 of a reward entry selects a *variant of one column*: kind 2's and kind
3's items are a subset of kind 0's on 1,510 of 1,527 columns, at 0.40 and 0.60
of kind 0's chance and in equal or bigger stacks. Nothing read so far says
which variant a given run gets. [`purse.py`](../engine/purse.py) draws kind 0,
and kind 4 for the player's own class, which is the one selector the disc
names.

*Retired by:* [`TODO.md`](TODO.md) item 14 — ordinary disc work.

### S4 — how long a talk line stays up

`suspend(n)` is the whole blocking vocabulary of the script layer, and
[`format_api.md`](format_api.md) reads all thirteen numbers. What the host
does *with* them is half read and half invented: the value handed back to the
script is what the disc says it reads back, and the **frame count** is this
file's. A talk line is up for 30 frames because a second is a reasonable
guess.

This one is cosmetic for a headless run and is not cosmetic for a playable
build: it is the pacing of every cutscene in the game.

*Retired by:* the EBOOT, or a UI that has a reason of its own.

### S5 — most of the interface is a stub that returns zero

```
$ python engine/host.py api extract/tree
285 functions in the interface, 285 bound, 71 of them doing something
17872 calls a run of the whole disc would make through the 71 that do
something, of 25699 in total
```

Seventy-one is 70 % of the *traffic* and 25 % of the *vocabulary*. The other
214 are recorded and return 0 — deliberately 0 rather than null, because
nearly all of them answer a question with a number and a null turns the
script's first comparison into an error and hides everything after it. That is
the right stub and it is still a stub: a script that asks the camera where it
is gets zero and believes it.

*Retired by:* one function at a time. Many are ordinary work — the recorded
call sites in [`format_api.md`](format_api.md) say what most of them are for —
and about a dozen have argument roles the disc does not separate.

### S6 — the monster asks 47 questions and gets 19 answers

`State` in [`brain.py`](../engine/brain.py) is one field per host predicate,
which is exactly what the AI's interface is. `State.SOURCE` classifies every
one of them, and the count is the honest summary of how much of a fight this
engine models:

```
world 17, table 2, default 28
```

The nineteen that are answered are the geometric ones — range, angle, height,
who else is alive, how much time has passed. The twenty-eight defaults are
almost all the *consequences of damage*: `damaged`, `stagger`, `downed`,
`angry`, `parts_broken`, `parts_damage`, `react`, and every `target_*` field
that asks what the player is doing. A monster that never learns it was hit
never gets angry, and no rule that mentions anger has ever fired.

*Retired by:* S1 first — most of these are downstream of damage — then the
player-state half, which is ordinary engine work once there is a pad.

### S7 — where the player is in the story

A reward block's head is a story-progress threshold in the same number space
`cfGetMainCounter` returns, and the player takes the last block at or below
where they are. A quest's own requirement out of `chapter.bin` `+0x08` answers
that for a quest that has one; where a quest requires nothing, `PROGRESS =
11000` is the floor and it is this repository's.

This is a small stand-in with a clean shape: it stands in for **save-game
state**, which is not on the disc at all because it is written by the game.

*Retired by:* a save file, or a decision that the floor is part of a new game.

### And one that was retired, in session 30

`TIER = '0'` used to sit in this table. Every monster the engine spawned was
its own base record — the weakest version of itself — because nothing said
which of a monster's difficulty tiers a quest wanted. `enemy.bin` `+0x37`
says, and had been sitting in [`format_quest.md`](format_quest.md) as
*"ten-step values, unread"* since session 24. It moves `hp`, `atk` and
`region_lv`, the drop table and the reward block, so it was a stand-in with a
long reach.

That is what this document is for. The value was two joins away the whole
time; what was missing was a list saying it mattered.

---

## 2. Readings — three the engine acts on

A reading is a claim about what a disc field *means*. It can be wrong without
anything crashing, which is what makes it worth listing separately from a
convention.

| | the field | read as | what says so |
|---|---|---|---|
| R1 | `ry_r_walk/run/fast/fall` | the radius a body looks for ground within | four radii, four locomotion states, all six classes, no monster |
| R2 | a heading of zero | faces `+Z` | `010_01_01`'s spawn then faces its exit and not the wall |
| R3 | model space | is stage space, `+Z` forward | a run cycle then carries the body forwards |

R1 is session 29's and it is the newest. `ry_r` abbreviates something the disc
never spells out; that a per-gait length growing with speed is a ground probe
is the reading, and it is the only per-gait length the player's table has.

R2 and R3 are the same claim twice and they are checked rather than assumed —
`run.py` prints the spawn-faces-its-exit test and `pose.py track` prints the
slide a locomotion cycle produces, so both can be argued with from the output.

**And two came off this table on the day it was written**, which is the best
argument for having it. [`brain.py`](../engine/brain.py) had declared two
readings of its own: that `getAngleTypeToTarget`'s two bands are *where the
target sits in my frame* while `getAngleTypeAtTarget`'s four are *where I sit
in the target's*, and that `checkRangeParam`'s three distinct values are three
ordered range bands. The EBOOT's own `AIT_*` enum names them
`AIT_TGT_FRONT`/`AIT_TGT_REAR` against
`AIT_FRONT_TGT`/`REAR_TGT`/`LEFT_TGT`/`RIGHT_TGT`, and `AIT_RANGE_S`/`_M`/`_L`
— the reading, in the engine's own words, including the word order. See
[`format_ai.md`](format_ai.md) and [`format_self.md`](format_self.md).

One half of the second is still a reading and is marked as one at the site:
S, M and L say the bands are ordered and do not say the far one ends at twice
the action's range, which is still this repository's number.

Two more readings sat in [`combat_loop.md`](combat_loop.md) — the unit of the
hit record's `+0x35` and the sign of a region's flat modifier — and neither is
listed here, because **nothing in the engine consumes them yet**. They become
readings the moment damage exists. **One of the two will never have to
become one**: session 31 read the damage expression and the defence term is
subtracted, clamped to zero first, so the sign is now the binary's and not
anybody's reading. See [`eboot.md`](eboot.md).

---

## 3. Conventions — thirteen choices the disc does not make

| | the choice | where |
|---|---|---|
| C1 | ground steeper than `WALKABLE_COS = 0.34` is a wall, not a floor | [`world.py`](../engine/world.py) |
| C2 | a step is `col_r`, for the walker and for the navigation graph alike | [`world.py`](../engine/world.py), [`actor.py`](../engine/actor.py) |
| C3 | a body decelerates at `acc`, the rate it accelerates | [`actor.py`](../engine/actor.py) |
| C4 | a turn brakes on the textbook `w² / 2a` | [`actor.py`](../engine/actor.py) |
| C5 | a blocked step slides along the fence | [`actor.py`](../engine/actor.py) |
| C6 | a *walking* body stops at the edge of the ground; a pushed one falls | [`mission.py`](../engine/mission.py) |
| C7 | a body that has fallen out of the world goes back where it stood | [`mission.py`](../engine/mission.py) |
| C8 | triangles are drawn two-sided | [`draw.py`](../engine/draw.py) |
| C9 | the draw order is per call, blended calls furthest first | [`draw.py`](../engine/draw.py) |
| C10 | an opaque material whose texture has holes takes an alpha test at 96 | [`draw.py`](../engine/draw.py) |
| C11 | contact has a tolerance of `TOUCH = 0.03` m | [`pose.py`](../engine/pose.py) |
| C12 | an animation is in place, and root translation is added on top | [`pose.py`](../engine/pose.py) |
| C13 | a hit record with no radius gets `MIN_RADIUS = 0.05` | [`fight.py`](../engine/fight.py) |

Three of these deserve a note because they were tested rather than picked.

**C1 has no candidate on the disc.** A maximum walkable slope is the sort of
thing a level format usually declares and this one does not. `CCLS` was the
obvious place: it carries a surface code per triangle, thirteen of them. In
session 29 all thirteen turned out to have a median slope under four degrees,
which rules them out as a walkability flag and leaves 0.34 as a number this
repository chose.

**C2 was measured against the alternative.** The disc has no step height, and
it does not imply one either: slab risers decay smoothly to 0.9 m over 67
stages and then spike at exactly 1.0 m, which is the tower's modular kit on 35
`170_*` floors. Moving the threshold from 0.5 to 1.5 m buys **no extra
reachable exit anywhere**, so the parameter is not carrying the result. Using
`col_r` for it is reuse rather than invention — but that the two are the same
number is still a choice.

**C11 prints its own sensitivity.** `pose.py footfall` reports what the answer
does at one centimetre and at five as well as at three, which is the shape
every convention on this list ought to have and only some do.

**C6 and C7 are the two rules that keep a run alive**, and both are counted
where they happen — `stopped at the edge of the ground` and `fell out of the
world` appear in the run's own log. That is deliberate: a convention that
fires often is a convention that is deciding the outcome.

---

## 4. Scaffolding — eight things that are not wrong

Every one of these stands where **player input** goes. None of them is a claim
about the game, and none needs retiring — they are replaced by a pad.

- `_goal` — where the body is trying to get to on a stage;
- `steer` — following an A\* route over the collision mesh to get there;
- `COMBO = 'sssss'` — the button string the run presses at a monster;
- the stick as four discrete targets — 0, `walk_sp`, `run_sp`, `fast_sp`,
  rather than a magnitude;
- `RESUME`'s **return values** — the host picks the first choice, cancels the
  shop, and says yes to the quest-start dialog;
- `STAGE_FRAMES = 7200` — four minutes, after which a run gives a stage up;
- `LONG = 20.0` and `NEAR = 2.0` in [`run.py`](../engine/run.py) — how long a
  crossing must be to count and how close counts as arriving, both properties
  of the instrument;
- `BACKGROUND`, `CLEARANCE` and the fallback `LIGHT`/`AMBIENT` in
  [`draw.py`](../engine/draw.py) — a clear colour and a camera, used only when
  no stage has been named to light the shot.

The distinction matters in one direction in particular. `_goal` and `steer`
are the two places a run most often goes wrong — 66 of the 431 quests end with
*the body stopped walking* — and it is tempting to file that under *the engine
is wrong*. It is not: **it is a robot playing with no hands**, and the fix is
either a better robot or a player.

---

## How to keep this honest

Three rules, all of which this repository already follows somewhere and none
of which it follows everywhere.

1. **Declare at the site and list here.** A new constant that did not come out
   of the disc gets a comment saying so and a row in one of the four tables
   above. The four classes are the whole taxonomy: if a new thing does not fit
   one, that is a signal about the thing.
2. **Print the policy in the output.** `mission.py` prints `BLOWS` and
   `BREAKS` with every run and `purse.py` prints which block it drew from.
   Nobody reading that output can mistake the number for the game's. `RESUME`
   and `WALKABLE_COS` do not do this and should.
3. **Ablate before keeping.** Session 29's method: change the thing, measure,
   change it back, measure again. Three of its four survived and the fourth is
   a comment in [`mission.py`](../engine/mission.py) explaining why a rule that
   sounded obviously right lost. A convention that has never been measured
   against its alternative is a guess wearing a comment.

And one about the shape of the list itself. The seven stand-ins do not divide
evenly, and the way they *do* divide is the finding. **Three of them are the
damage expression**: S1 and S2 are it directly and S6 is everything
downstream of it, so one function out of the EBOOT retires nearly half the
list and unfreezes the AI as well. One (S3) is ordinary disc work. One (S7)
is a save file and is not on the disc at all. The two that are genuinely
diffuse are S4 and S5, and they are the same thing seen twice — the script
interface, 214 stubs and thirteen suspend delays, which is a long tail of
small work rather than a locked door.

That is the same conclusion [`STRATEGY.md`](STRATEGY.md) has been converging
on since session 10 and [`combat_loop.md`](combat_loop.md) reached from the
other end — what is left inside the binary is the combat loop and the
implementations — but it is worth arriving at it this way too, because this
route starts from *what is wrong with what runs* rather than from *what has
not been read*. The two lists agree, which is the useful part.
