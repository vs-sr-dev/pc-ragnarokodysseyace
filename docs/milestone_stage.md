# Milestone 2 — a stage runs

**Status: reached, session 22.** The game's own compiled Squirrel executes.
`010_01_01` initialises itself, a body with the game's own parameters crosses
it, the trigger volume at the far end fires the function `trigger.trg` names,
and the `cfMapJump` inside that function loads `010_01_02` and starts *its*
script and *its* quest script. Two more things run on the same machinery: a
cutscene drives itself to its own end, and a conversation with an NPC comes
out in English.

Code: [`../engine/squirrel.py`](../engine/squirrel.py), the virtual machine,
and [`../engine/host.py`](../engine/host.py), the interface it calls out to.

```
python engine/host.py stage  extract/tree 010_01_01 q00101 job.cpk/sw/sw.json
python engine/host.py demo   extract/tree 010_01_01
python engine/host.py talk   extract/tree No13800.psq
python engine/host.py stages extract/tree
python engine/host.py api    extract/tree
python engine/squirrel.py sweep extract/tree
python engine/squirrel.py run   extract/tree <psq> [function]
```

## What was in front of it, and what it turned out to need

For eleven sessions this milestone was "a Squirrel VM, the 285 native
functions stubbed, and nothing else that is not already read". That was
right. The VM is 48 opcodes and about 1,200 lines, the host is the 285 names
with 66 of them doing something, and **nothing had to be read off the disc
that [`format_psq.md`](format_psq.md) and [`format_api.md`](format_api.md)
had not already read** — with one exception, which is in its own section
below because it came out of running the thing rather than reading it.

The VM is written here rather than linked because the disc's own reader is
already in Python and complete: [`psq.py`](../tools/psq.py) parses all 11,232
functions to the byte, so an interpreter over its output is the second half of
a file that exists, while the C library would need a build, a binding, and a
byte-swapping patch to read a big-endian stream on a little-endian host.

## Three things that run

### The stage

```
      0  stage    entered 010_01_01 at appear01 (70 markers, 2 triggers)
      0  stage    fence lock_line01 off
      0  stage    fence lockarea01 off
      0  stage    hit area pl_q01106 off
      0  print    ★★ 図鑑用のフラグ立てる ★★
      0  walk     from appear01 towards jump_010_01_02, 73.0 m away
    460  trigger  entered jump_010_01_02: MapJumpA();
    460  jump     to 010_01_02 at appear01
    460  stage    entered 010_01_02 at appear01 (104 markers, 8 triggers)
    460  print    --- 010_01_02 StagetInit ---
    460  print    --- q00101 010_01_02 QuestInit ---
```

Every line of that is the disc's. `sfStageInit` turning off two fences and a
hit area is the stage's own script; the Japanese line is the quest script's
own debug output, on the flag it sets for the monster dictionary; the walk is
milestone 1's capsule under `sw.json`, **460 frames with 0 frames off the
collision mesh**; the trigger and its script text are `trigger.trg`; and
`010_01_02` arriving with its own quest script is `cfMapJump` doing what the
name says.

The one thing on that trace that is *not* the disc's is which trigger fires:
`pl_q01106` was switched off by `sfStageInit` before the body ever reached it,
so the only volume left to enter is the exit. That is the script deciding, and
it is the first time on this project that a script decision has changed what
the engine does.

### The cutscene, and a number nobody had looked for

A cutscene is driven by the host: `demoInitBGM`, `demoInit`, then `demoUpdate`
once a frame, then `demoEnd` ([`format_api.md`](format_api.md)). The script is
a phase machine that counts frames and compares them against
`getDemoFrame()`, which returns *now* and *the end*. Nothing in the script
says what the end is — so the host has to know, and nothing on the disc had
been read that says.

It is the `u16` at **`0x10` of the cutscene's own `.CSCM` camera track**, the
same offset at which [`format_cnom.md`](format_cnom.md) reads a motion's
length. Over the 78 tracks it runs **226 to 1,081 frames**, which at 30 Hz is
7.5 to 36 seconds, and that is the right range for a cutscene.

The check is behavioural and it is the sharpest one in this document:

```
68 cutscenes driven by their own camera track, 68 reached setDemoEnd
  010_01_01.pac                ended at  331 of  301
  020_01_02.pac                ended at  301 of  271
  z25_00_appear.pac            ended at  613 of  571
  b12_99_appear.pac            ended at  312 of  241
```

**All 68 cutscene scripts on the disc reach `setDemoEnd()` when driven by the
length their own camera track declares, and not one of them ends before the
track does.** The overshoot is the script's own tail: `010_01_01` waits for
`frameA[0] >= frameA[1]`, then counts `demoCount = 30` down and ends — and
331 is 301 plus 30, exactly. Nothing about that was arranged. The thresholds
are the author's, the length is the camera track's, and they are read from two
different files by two different tools.

### The conversation

`talk(speaker, message)` is `cfTalk(speaker, message); suspend(101)`. The
script stops on every line and the host resumes it, which makes a conversation
the shortest complete test of the suspend protocol:

```
    127  talk     Norn: So whenever you have free time, why don't
                        you stop by, and we can talk?♪
    129  print    *** talkNornThanks(): feeling_rank:0, voice:-1, message:5964
    129  talk     Norn: Thank you.
    129  suspend  No13800 waits on 101 (a talk line is on screen), 30 frames
    159  print    --- talk_end ---
```

**13 lines, 928 instructions, 27 of the 285 reached, 0 threads left waiting.**
The speaker and the text are the two tables
[`format_api.md`](format_api.md) joined the arguments to, and message 5964 at
`feeling_rank 0` is the first row of the affection table that document ends
on. The script computes the rank, picks the id, and the id lands on the line
the table says it should.

## What the VM had to decide, and what the disc decided for it

Three decisions are not in [`format_psq.md`](format_psq.md), because none of
them shows up until something executes. Each is settled by a count.

### An unqualified name falls back to the root table

Squirrel 2.2's `SQVM::Get` takes the *register index* of the receiver and,
when it is 0 — which is `this` — retries the lookup against the root table
before failing. That is what lets a stage script call `cfMapJump` it never
imported, and it is what makes **one shared root table** enough.

The disc says the table really is shared, twice:

- `room_select`, in the resident library `common.psq`, calls
  **`mapjump_140_02_01`**, and the only file that defines it is
  `stage.cpk/140_01_01/param.pac/140_01_01.psq`. A shared library calling a
  function that one stage script defines only works if they are on the same
  table;
- and the sharing does not collide. Loading the resident library and then
  each stage's own scripts, over all 155 stages that have a collision mesh,
  produces **three** names defined twice: `Vec3` in `050_02_03`, which
  declares its own copy of the class, and `checkQuestClearByIDFlag` in
  `140_02_01` and `140_03_01`, which redefine a library helper. Three in 155
  is a design, not an accident.

**The five files of `misc.cpk/psq_common.pac` are that library** — `common`,
`class`, `stage`, `quest` and `test`, 85 functions — and they define no name
twice between them, which is what says they are meant to be resident
together.

**The town's conversations are not resident.** The 460 scripts under
`stage.cpk/140_02_01` collide on **147** names: seventeen of them define
`talkNornThanks`, `updateNornFeeling`, `checkNo_BillingOpen` and
`canBilling`, thirteen define the four `No_common_*`. So the host loads one
when a conversation starts, and that is why `talk` takes a script name.

### A `suspend` keeps its frames, and the number says who is waiting

`suspend(n)` is `sq_suspendvm`: the call stack stays where it is, the host
gets `n`, and a later resume writes a value into the register the call was
going to fill. [`format_api.md`](format_api.md)'s thirteen numbers become a
scheduler — `RESUME` in [`host.py`](../engine/host.py) — and only one entry
in it is not policy: `wait(n)` is `setWaitCount(n); suspend(1000)`, and the
host owes the script exactly `n` frames. How long a talk line stays on screen
is this repository's guess and is marked as one.

Over the whole disc, **1,464 of the 8,085 functions that run reach a
`suspend`**, which is the interface working rather than a fault.

### A vararg function keeps all its declared parameters

This one the disc settles outright, and it separates two versions of Squirrel
that are otherwise identical here. `function prt_select(rand, ...)` compiles
with `_parameters = ['this', 'rand']` and `_varparams = 1`. Squirrel's later
versions add a third parameter named `vargv` and step back over it; if this
build did the same, `rand` itself would become the first vararg and every
index in the function would slide by one.

The AI's own weight tables say which reading is right. `prt_44` calls

```
prt_select(rand, 1, 0, 100, 0, 101, 0, 102, 0, 103, 0, 104,
           5000, 105, 5000, 106, 0, 107, 0, 108, 0, 109, 0)
```

and the function reads `vargv[2i]` as an action id and `vargv[2i+1]` as its
weight, normalising by 10,000. Under the reading adopted here the eleven
weights are 0, 0, 0, 0, 0, 5000, 5000, 0, 0, 0, 0 — **10,000 exactly**, with
the two halves on actions 104 and 105. Under the other reading the pairs
straddle the boundary, the total is 0, and the function divides by zero.
That was **447 failures across the six bosses** before the boundary was moved,
and 0 after.

And with the boundary in the right place the selector does what
[`format_ai.md`](format_ai.md) says it does. Given a real `getRand()`, the Orc
King's `prt_44` returns 104 and 105 in equal numbers, which is its two 5,000
weights; `prt_45`, whose weights are 3,000, 5,500 and 1,500 on actions 104,
105 and 107, returns those three. **The boss picks its next action, out of its
own table, through this interpreter.**

## The measurements

### The interpreter, over every script on the disc

```
python engine/squirrel.py sweep extract/tree

3011 files, 8167 functions on the table, 8085 ran to a stop,
1464 of them into a suspend
387884 instructions retired, 39 of the 41 opcodes the disc contains
0 VM faults, 82 script errors
```

Every `.psq` is loaded — which means its `main()` runs, and `main()` is what
puts a script's functions on the table — and then every function it defined is
called with zero arguments against a stubbed host. The disc holds 11,232
functions: 3,011 are `main`, 8,221 are their children and nothing is nested
deeper, and 8,167 names survive to the table because 54 are written twice by
their own `main`.

**A `VMError` is a hole in the interpreter and there are none.** The 82
failures are `SquirrelError` — the script objecting to what a stub handed it —
and they are five classes and no others: 68 are `getDemoFrame()[0]` on a stub
that returned a number instead of an array, 5 are a method call on the same,
6 are the constants below, and 3 are the `Vec3` test scaffolding. Under the
real host every one of the 68 goes away, which is what the `demo` command
shows.

Two opcodes are never reached: `_OP_JNZ`, which the disc emits four times, and
`_OP_POSTFOREACH`, which is emitted after each of the eleven `foreach` and is
stepped over unless the container is a generator — and `_bgenerator` is 0 on
all 11,232 functions, so it is dead code on this disc by construction.

### The host, over every stage

```
python engine/host.py stages extract/tree

163 stages: 155 loaded and initialised, 154 with a script of their own, 8 failed
507 trigger lines, 507 of them read as calls with constant arguments
3 names defined twice over a stage and the resident library
1 names called that nothing binds: mapjump_140_02_01
```

The eight failures are the eight stage directories with no collision mesh,
which is milestone 1's number and not a script problem. **154 of the 155
stages that exist have their own `.psq`, and all 154 initialise.**

**All 507 trigger lines parse as a sequence of calls with constant
arguments** — which is what [`format_stage.md`](format_stage.md) said they
were, now checked by something that has to execute them. 147 of them are
`callQuestScript("<something>()")`, a line of source inside a string, and the
bracket that closes the call has to be found with the quotes respected.

### The interface

```
python engine/host.py api extract/tree

285 functions in the interface, 285 bound, 66 of them doing something
17635 calls a run of the whole disc would make through the 66 that do
something, of 25699 in total
```

**The 66 that do something carry 69% of the interface's traffic.** They are
the flag banks, the marker table, the fences and the spawners, the stage jump,
the character handles, the cutscene slots, the talk tables, the random
numbers and the wait counter. The other 219 record the call and return 0,
which is a stub and is reported as one every time a count is printed.

Returning **0** rather than null is a decision worth stating: nearly every one
of these answers a question with a number, and a null turns the script's first
comparison into an error and hides everything downstream. It is the difference
between 1,263 script errors and 82.

## Six names the engine holds that are not functions

Running the scripts turned up a small hole of the same shape as
`prowl_script`. Six names are *read* off the root table, never called, and
defined by no `.psq`:

```
DEMO_S174_A  DEMO_S175_A  DEMO_S176_A  DEMO_S177_A  DEMO_S178_A
MONS_KIND_ORGA
```

The five `DEMO_*` are cutscene ids: `setDemoID(DEMO_S177_A, 0)` in
`quest.cpk/q07607.pac/010_01_01.psq`, where every other quest script on the
disc writes the number. `MONS_KIND_ORGA` is a monster kind, in a mercenary
debug function. So **the engine's root table carries named constants as well
as functions**, and these six are the only ones the scripts still reach for.
They are cheap for the EBOOT phase to answer and nothing else on the disc
does.

## What this does not do

The host is a scheduler and a set of bindings, not a game. There is no
renderer, no combat, no monster, and no player input: the body walks toward
the exit because `stage` tells it to, and a choice is always the first one.
The 219 stubs are where the rest of the engine goes, and the next milestone —
*"a monster fights"* — needs about forty of them: the AI's predicates over
state that a running stage would have anyway, which
[`format_ai.md`](format_ai.md) already names one by one.

Two smaller things are left where they are. `prowl_script` is still defined by
nothing, so a boss whose `isActive()` is false tail-calls into a hole; and the
`.psq` residue in [`format_psq.md`](format_psq.md) — `_OP_COMPARITH`'s packed
`_arg1`, which the disc emits three times — is implemented from the
interpreter's own definition, and the sweep retires it exactly **once**
without faulting. That is weaker than a confirmation: a wrong operand order
would compute the wrong number rather than raise, and nothing on the disc
checks the answer.
