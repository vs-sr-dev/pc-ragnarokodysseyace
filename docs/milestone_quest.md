# Milestone 5 — a quest finishes itself

**Status: reached, session 24.** A quest's own tables put monsters on a stage,
the player kills them, and **the quest's own compiled script counts the kills
and decides the arena is over** — then opens the gate it closed and lets the
run walk on to the next room. Nothing in the engine tells a script how many
monsters it put out. The script knows because the table told it, twice, in two
different files, and the two agree.

Over the disc: **527 of 527 arena locks agree with the constant compiled into
their own kill callback**, and driving all 431 quests, **210 of the 229 arenas
the body reached were closed by the script itself**, on 1,534 kills.

[`milestone_stage.md`](milestone_stage.md) ran a stage.
[`milestone_fight.md`](milestone_fight.md) and
[`milestone_player.md`](milestone_player.md) ran a fight in both directions.
What was between them was **state that changes**: `cfSetEnableEmGen`,
`cfStartPieceLock` and `cfGetCntKillGenPieceLockOnly` were bound to nothing
that moved. They move now.

Code: [`../engine/mission.py`](../engine/mission.py), with nine bindings in
[`../engine/host.py`](../engine/host.py) routed into it and a navigation mesh
added to [`../engine/world.py`](../engine/world.py).

```
python engine/mission.py run    extract/tree q00102 sw
python engine/mission.py runs   extract/tree
python engine/mission.py counts extract/tree
python engine/mission.py area   extract/tree
python engine/mission.py route  extract/tree
```

## The loop, and where each link was read

    a trigger volume        pl_q00102_a              format_stage.md   s8
      -> a quest function   sfEnmGenStart            format_psq.md     s10
      -> a lock             cfStartPieceLock         format_api.md     s12
      -> the lock's row     piecelock.bin            format_quest.md   s22
      -> its fences         lockarea, lock_line      format_stage.md   s8
      -> its generators     +0x1c, newline-separated format_quest.md   s22
      -> a monster each     enemy.bin, 12-bit id     format_quest.md   s22
      -> a fight            both halves              milestone_player  s23
      -> a kill callback    enemy_gen.bin +0x38      format_quest.md   s22
      -> a counter          the script's own local   this session
      -> the arena opens    cfEndPieceLock           this session

Every link but the last two was measured in an earlier session against a
different file. The last two are the point: the counting is the script's and
the number it counts to is the script's.

## The count is written twice and nobody arranged it

A quest's `sfKill_Generator` ends

```
function sfKill_Generator(gen_name) {
    print((('--- generator [' + gen_name) + '] End ---\n'))
    cntGenKill++
    if (cntGenKill >= 8) { sfEnmGenEnd() }
}
```

The `8` is an integer compiled into Squirrel bytecode, recovered by
[`psq.py`](format_psq.md)'s structurer. The number of generators the lock
covers is a newline-separated string in `piecelock.bin` lane `+0x1c`, recovered
by [`ech.py`](format_ech.md). Two files, two readers, no shared assumption —
and if the lane were read wrong the two numbers would simply differ, with no
way to arrange agreement from either side.

```
python engine/mission.py counts extract/tree

567 locks over 431 quests
  528 name a generator with a counting callback
  the script's threshold equals the generators the lock covers
    527 yes, 0 no
  39 locks whose generators name no callback at all
  1 callbacks that count nothing
    q01509 pl_150_02_01 -> BGMStop counts nothing
```

**527 of 527, with nothing left over.** The one exception is a generator whose
callback is named `BGMStop`, which does not count anything and was never going
to.

This is the sharpest check the quest tables have had, and it needs no run at
all. It is also why the arena can close *by itself*: the engine hands the
script a callback per generator and the script already knows how many
generators the room holds.

**Per generator, not per corpse** — which the disc says in its own words. The
callback is named `sfKill_Generator` and the line it prints is `--- generator
[emgen01] End ---`. The measurement agrees: on 36 of the 527 matching locks,
`enemy.bin`'s population byte for the slots those generators use is exactly
*twice* the threshold — the 91 rows where
[`format_quest.md`](format_quest.md) found a generator producing two — and
the script still stops at the number of generators. That sharpens the earlier
reading rather than contradicting it: a generator that ships two monsters
still reports once, when it is exhausted.

## Two more joins that need no run

**`lockarea` is the room and `lock_line` are the doors.** A lock names one
`lockarea` polyline and a list of `lock_line`s, both of them
`borderline.bin` polylines the stage script can enable, and the table does not
say which is which. Point-in-polygon settles it:

```
python engine/mission.py area extract/tree

537 locks with an area polyline, 21 without
  the spawners it covers   2813 of 2817 inside
  the trigger that closes it   572 of 575 inside
```

The `lockarea` contains both the monsters and the volume that seals them in.
The `lock_line`s are two-point segments thrown across corridors, mostly well
outside it: they are the gates.

**The stage list is a graph, not a path.** `piecelist.bin` is written in an
order and the obvious reading is that the order is the route. It is not, quite:

```
python engine/mission.py route extract/tree

428 quests with a stage list, 1280 consecutive pairs in them
  767 pairs where the first carries a jump marker naming the second
  398 lists reachable end to end from their own first stage
```

The thirty that are not are almost all `170_*`, and those stages carry a marker
named **`jump_next`** whose trigger calls a `MapJump()` that branches on
`getQuestName()`. Interchangeable floors: the exit does not name where it goes,
and the script decides. The run therefore walks the list as a graph, which is
also what a player does.

## One quest, end to end

```
python engine/mission.py run extract/tree q00102 sw

    457  trigger  entered jump_010_01_02: MapJumpA();
    457  jump     to 010_01_02 at appear01
    494  trigger  entered pl_q00102_a: callQuestScript("sfEnmGenStart()");
    494  print    --- !! PieceLock Start !! ---
    494  stage    piece lock pl_010_01_02 closes
    603  print    --- generator [emgen01] End ---
    769  print    --- generator [emgen12] End ---
    797  print    --- generator [emgen05] End ---
    843  print    --- generator [emgen03] End ---
    843  print    --- generator [emgen06] End ---
    913  print    --- generator [emgen04] End ---
    984  print    --- generator [emgen11] End ---
   1159  print    --- generator [emgen02] End ---
   1159  print    --- !! PieceLock End !! ---
   1159  stage    piece lock pl_010_01_02 opens
   1861  trigger  entered jump_010_01_03: cfMapJump("010_01_03", "appear01");
   ...
   2530  print    --- !! PieceLock End !! ---
   3241  jump     to 010_03_02 at appear02

  q00102 as the warrior, 3242 frames = 108.1 s
  route wanted   010_01_01 -> 010_01_02 -> 010_01_03 -> 010_03_01 -> 010_03_02
  route walked   010_01_01 -> 010_01_02 -> 010_01_03 -> 010_03_01 -> 010_03_02
  2 locks in the quest, 2 started, 2 the script ended itself
    pl_010_01_02  010_01_02   8 generators, the script stops at 8
    pl_010_01_03  010_01_03   5 generators, the script stops at 5
  13 monsters spawned, 13 killed, the last of them id 1140
  the quest finished
```

Every line beginning `print` is the game's own text, coming out of the game's
own bytecode. `--- generator [emgen01] End ---` is a string in a `.psq`
literal pool, printed because the engine called a function
`enemy_gen.bin` named, with the name that table gave the spawner. The eight
that print are the eight the lock covers, and the ninth line — `PieceLock
End` — is the script deciding for itself.

## The disc

```
python engine/mission.py runs extract/tree

431 quests run, 247 of them finished
  25 of the 131 that arm an arena at all, 222 of the 300 that do not
  252 walked their whole stage list, 1105 of 1708 stages in all
  272 arenas armed by a quest script, 229 started, 210 ended by the
      script's own kill count
  1594 monsters spawned, 1534 killed
  1 calls with the wrong number of arguments, which the host adapts:
      {'cfSetEnableBorderline': 1}
```

The numbers measure different things and are worth keeping apart.

**210 of the 229 arenas the body reached were closed by the script's own kill
count.** That is the state machine, and it is the milestone: it depends on the
tables being read right and on nothing else. The nineteen that did not close
are arenas where a monster ended up somewhere the body could not get to.

**252 quests walked their whole stage list.** That is the navigation, and it is
this repository's steering rather than anything the disc says — a body that
walks into a corner and stops is a bad walker, not a wrong reading. 125 runs
end with *the body stopped walking*, which is the run giving a stage up after
half a minute of going nowhere.

**247 quests finished**, but the split matters: 300 of the 431 arm no arena at
all — 146 of them visit a single stage, which is a conversation at the bar
rather than a hunt — and of the 131 that do put a lock in front of the player,
**25 come out the other end**. The gap between 210 arenas closed and 25 quests
finished is entirely the walk between them: a quest with four arenas needs the
body to cross five rooms without getting stuck, and the odds compound.

`cfSetEnableBorderline` being called with no arguments at all is a one-line
slip in `q01106`'s copy of a stage script. The real game shrugs it off, because
a Squirrel native takes whatever the source wrote; the host now does too, and
counts it.

## The ground mesh is a navigation mesh

A straight line at the goal walks into the first wall a room has, and
`010_01_02` has one twenty-five metres short of its own exit. What replaces it
comes out of a conclusion [`format_ccls.md`](format_ccls.md) had already
reached and nothing had used: the collision mesh is **welded** — 150,236 of the
disc's edges are shared by exactly two triangles under exact vertex equality,
with no T-junctions anywhere — and **the edge of the walkable region is the
fence**, because there are not enough vertical triangles on the disc to wall a
level.

Those two together make the ground a navigation mesh with no extra data at
all. [`world.py`](../engine/world.py) builds the adjacency, refuses a crossing
whose two triangle centres are separated by a fence, and runs A\* over it; the
waypoints are the shared edges' own midpoints. Nothing new is decoded — it is
[`ccls.py`](../tools/ccls.py)'s triangles and
[`stage.py`](../tools/stage.py)'s polylines, read as a graph.

The mesh boundary is also what stops a walking body, for the same documented
reason. [`actor.py`](../engine/actor.py) drops a body that steps off the
ground and keeps dropping it, which is right for a body that has been pushed;
a body that is *walking* stops at the edge instead.

## What the quest layer answers that a duel could not

`brain.py`'s `State` marks `other_zako`, `other_boss`, `same_kind` and
`players` as *world* — quantities a running fight is supposed to supply — and
until now every fight had exactly one monster in it, so all four were zero.
An arena puts eight bodies of two kinds on the floor at once, and
`getOtherZakoCount`, `getOtherBossCount` and `getActiveSameKindCount` finally
answer with a number that is not.

Four host functions also stop being stubs: `cfGetCntKillGenPieceLockOnly`,
`getLatestKilled`, `getNumOfEnemy` and `getNumOfBoss`. `host.py api` is now
**70 of the 285 doing something**, carrying 17,862 of the disc's 25,699 calls.

## What is the disc's here and what is not

The disc's, to the byte: the spawner list and the marker each one stands on,
the monster in each `enemy.bin` slot, the fences a lock raises, the hit area
that trips it, the function that runs on a kill, the number the script counts
to, and the map jump at every door.

The run's own, and stated so it can be argued with:

- **A monster dies on its third landed volume.** The monster's hit points are
  on the disc — `hp` in its own JSON — and what a blow takes off is not:
  that is [`combat_loop.md`](combat_loop.md) ledger item 1 and it is the
  EBOOT's. The run declares a count, prints it with every result, and takes it
  as an argument. Nothing else in the loop depends on the number.
- **Where the body walks.** There is no pad, so the run steers: at the arena
  the quest armed, then at the exit that leads to a stage still on the list.
  The route across the room is the mesh's; choosing the destination is not.
- **A cleared arena does not close again on the same visit.** The disc never
  turns a `pl_q` hit area off and `sfEnmGenStart` sets its own counter back to
  zero, so walking back into the volume genuinely does re-arm an arena. An
  arena still *running* may be re-entered here, exactly as on the disc; one
  the script has already finished may not, because the run's step lets a body
  wander out of a room the game's geometry would have kept it in. Per visit,
  because a route may cross the same room twice.
- **A lock never fences the body away from its own monsters.** Three of the
  575 triggers that close an arena sit outside the `lockarea` they arm, and a
  body that trips one of those from the near side would be sealed *out* of the
  room it was walking into. After the fences go up the run checks that a route
  to the first monster still exists, and lowers the area, then the gates, until
  one does.
- **A body that is walking stops at the edge of the ground**, and one that has
  fallen out of the world goes back to the last square metre it stood on. The
  first is [`format_ccls.md`](format_ccls.md)'s own conclusion applied; the
  second is a crutch, and it is counted where it fires.
- **A host function called with the wrong number of arguments is adapted.**
  Squirrel natives take whatever the source wrote; Python raises. One call on
  the disc needs it — `cfSetEnableBorderline()` with no arguments, in
  `q01106`'s copy of a stage script — and it is reported rather than hidden.

## What this does not do

**There is still no damage.** A kill is a count of landed volumes, not a number
of hit points taken off. Everything the quest scripts ask — how many are dead,
which one was last, how many are alive — is answered exactly; nothing about
*how much* is.

**No rewards.** `item_reward{,_multi,_region}.bin`, `weapon_decost.bin` and the
`q<NNNNN>.bin` header are still unread, so a finished quest hands back nothing.
The quest completes; it does not pay.

**No respawn and no waves.** `enemy_gen.bin`'s `+0x28` carries what reads as a
respawn delay and `+0x2c`..`+0x30` two more counters, none of them named by a
consumer. A generator here produces one monster and is done.

**`changeEnemySet` swaps nothing.** The call runs its script argument and logs
the table name; `enemy02..04.bin` are not loaded.

**The player never dies.** The monsters land blows and they are counted, and
nothing happens as a result — the same gap
[`milestone_player.md`](milestone_player.md) leaves, seen from the other end.
