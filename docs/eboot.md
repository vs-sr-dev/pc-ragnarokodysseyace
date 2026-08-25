# The EBOOT, opened as a program

*Session 31. [`format_self.md`](format_self.md) is the container and how it
decrypts; this is the program that comes out of it, and the first thing read
off it. Tools: [`../tools/ppc.py`](../tools/ppc.py) and the two Ghidra scripts
in [`../tools/ghidra`](../tools/ghidra).*

[`STRATEGY.md`](STRATEGY.md) has pointed at this session since session 10 and
[`combat_loop.md`](combat_loop.md) named the price: **six of the nine items in
its ledger are inside the binary and each is one function or one enum**. The
first of the six is the damage expression, which
[`parity.md`](parity.md) counts as three of its seven stand-ins. That one is
below, in full, with an address on every term.

---

## The file will not disassemble itself

`self.py decrypt` gives 19,839,612 bytes of PowerPC 64 big-endian ELF: two
loaded segments, **16,141,416 bytes of code at `0x10000`** and 3,652,220 of
data at `0xf80000`, entry `0xfd01e8`.

It is stripped. No symbol table, no section names, and — the part that
matters — nothing that says where a function begins. Handed to Ghidra as it
is, with its own PowerPC analysers and every default on:

```
     Total Time   16 secs
```

Sixteen seconds, no functions, no code. That is not Ghidra being weak; it is a
16 MB haystack with no needle offered, and the heuristic search for prologues
did not even get started because nothing seeded it.

## Where the functions are, and why the loader throws

They are all in one table, and the ABI puts it there. On PowerPC 64 a function
pointer is not an address but a pointer to a **descriptor**, and the
descriptors live in `.opd`. `e_entry` is one of them: `0xfd01e8` is not code.

The ordinary 64-bit ABI makes a descriptor three 8-byte fields — entry, TOC,
environment. **This build's are two 4-byte ones**, because the PS3 runs a
64-bit ELF in a 32-bit address space:

```
0x00fd01d8  00010200 0111b8b8   00a5716c 0111b8b8   00010240 0111b8b8 ...
            entry    toc        entry    toc        entry    toc
```

That difference is not cosmetic and it is worth stating plainly, because it
cost the session its first two hours: **Ghidra 12.1.2's own `ELF` importer
fails on this file**, with a `NullPointerException` in
`PowerPC64_ElfExtension.markupDescriptorEntry`, reached from
`processOPDEntry`. It reads 8-byte fields out of 8-byte records, so every
entry address it computes is two descriptors glued together, lands nowhere,
and `createFunction` hands back `null`. Clearing `e_shoff`, `e_shnum` and
`e_shstrndx` in a copy of the ELF is enough to get past it — with no sections
there is no `.opd` section to mark up — and the section table is no loss
anyway, since `decrypt` does not write it out.

`ppc.py opd` reads the table with nothing but its own arithmetic. It starts at
`e_entry`, walks both ways for as long as the records stay descriptors — the
entry inside an executable segment and 4-aligned, the TOC inside a writable
one — and stops when they do not:

```
$ python tools/ppc.py opd eboot.elf
the function table is at 0x00fd01d8
  165596 descriptors of 8 bytes, 69691 distinct functions
  4 TOC runs, which is a TOC wider than one r2 offset reaches:
    0x0111b8b8   47325 descriptors
    0x0112b800   42650 descriptors
    0x0113b7e0   62068 descriptors
    0x0114b784   13553 descriptors
  entries run 0x00010200 to 0x00a5716c
  the five commonest first instructions:
    f821ff71   11313 stdu r1,-144(r1)
    f821ff91    9339 stdu r1,-112(r1)
    f821ff61    5213 stdu r1,-160(r1)
    7c691b78    4690
    f821ff81    4326 stdu r1,-128(r1)
```

Three things say the walk stopped in the right place.

- **The commonest first word is a stack prologue.** `stdu r1,-N(r1)` heads
  30,191 of the 69,691, in the frame sizes a compiler emits, and `7c691b78`
  is `mr r9,r3`. A table walked one record too far would show the last few
  entries pointing at the middle of something.
- **The four TOC values are four windows of one TOC.** They are `0x111b8b8`,
  `0x112b800`, `0x113b7e0` and `0x114b784` — 64 KB apart, which is exactly
  the span a signed 16-bit `r2` displacement reaches. A 256 KB TOC has to be
  addressed in four windows, and each window's functions get their own run of
  descriptors.
- **The container's own section table agrees, to the byte.** The `SELF` keeps
  a 32-entry section header table in the clear past the last segment —
  `self.py sections` prints it, names excepted, because `.shstrtab` is not in
  the clear — and its section 23 is `addr 0x00fd01d8`, `1,324,768 bytes`.
  That is 165,596 × 8. The walk and the table were never told about each
  other.

**And a caveat that came out of using this, not out of writing it.** 6,207 of
the 69,691 entries carry more than one descriptor, with different TOC values —
4,260 with two, 1,241 with three, 706 with all four. They are smaller than
average (mean 84 bytes against 161, and 3 % of them reach 256 bytes against
15 %), and **1,762 of the small ones are byte-identical to another entry**, so
identical-code folding is certainly at work: one body, several callers, and a
descriptor per identity. What `r2` such a body sees is therefore **not settled
by its descriptor**, and `FUN_001b0cb0` — a lazy singleton that really does
read `lwz r11, -0x5044(r2)` — is the case that shows it: of its four TOCs,
two resolve its three slots to a plausible guard byte, object pointer and
`atexit` callback, and two resolve them to a float and to noise. So
`ppc.py refs` accepts a hit under **any** of a function's TOCs, which is right
for finding candidates and can over-report on the 9 % that are folded. Every
address in this document was confirmed by reading the code it points at.

Fed those 69,691 entries, the same Ghidra run that found nothing finds
everything:

```
PlantOpd: 69691 function entries to plant
PlantOpd: disassembled from every one of them
PlantOpd: 69691 functions, 274 named, 0 refused
     Total Time   233 secs
```

## The 274 names, and where they come from

The engine binds its script interface by name — session 30 established that
274 of the 285 native names are strings inside the binary, the 285 being the
291 below less Squirrel's own five and `prowl_script` — and the registration
calls leave their arguments behind them **in the TOC, in source order**:

```
0x01144e3c  D:01104240  S:00f37bb0  S:00f37bc0    setWaitCount | .i
0x01144e48  D:01104238  S:00f37bc8                cfGetRandI
0x01144e50  D:01104230  S:00f37bd8  S:00f37be8    cfGetRandF   | .f
0x01144e5c  D:01104228  S:00f37bf0  S:00f37c00    cfPadStartFocus | .
```

`D` is a pointer into the function table and `S` a pointer into the string
pool; `.i` and `.f` are Squirrel typemasks, and a name has none when an
earlier call already needed that mask and the compiler reused its slot. So
**a descriptor immediately followed by a name the disc calls is a
registration**, and that is the whole join. `ppc.py natives` takes the name
list from `psq.py api` — the names the 3,011 scripts actually call, with the
296 that a `.psq` defines separated out — and reports:

```
291 names the disc calls and no .psq defines, 296 it does
274 of them are a descriptor and a name in adjacent TOC slots
  0x009d8f34  cfAddItem       descriptor 0x011048d0  slot 0x01145540
  ...
17 not placed:
  EffData  SoundManager_getInstance  Vec3  array  cfShopCannon  cfTestVec3
  getSampleFloatArray3  getSampleFloatArray4  getSampleIntArray2
  getconsttable  getroottable  isRecoverFaint  isRecoverParalyz
  isRecoverPoison  print  prowl_script  suspend
```

Five of the seventeen are Squirrel's own standard library and `prowl_script`
is the dead reference [`format_api.md`](format_api.md) identified; the other
eleven are class constructors and sample bindings, which are registered
against a class rather than the root table.

The names are worth what they cost. `cfAddItem`, planted, decompiles to

```c
undefined8 cfAddItem(HSQUIRRELVM v) {
  local_2c[0] = 0;  local_30 = 0;
  sq_getinteger(v, 2, &local_30);
  sq_getinteger(v, 3, local_2c);
  iVar1 = FUN_009ceda4((long)local_30, (long)local_2c[0]);
  sq_pushinteger(v, (long)iVar1);
  return 1;
}
```

— where the two `sq_*` names are this document's, inferred from the call
shape and not planted by anything. That is what one name buys: the two
Squirrel entry points either side of it, and `FUN_009ceda4(item, count)` in
between, which is the engine's real add-an-item.

## The binary names its own types

1,271 length-prefixed C++ type names are in the file, which is GCC's RTTI with
its `typeinfo` name strings intact. The commonest prefixes are `Mu` (438,
the menus), `Md` (118), `bt` (97, Bullet), `It` (64), `CH`, `UN`, `Ob`. Among
them:

```
  0x00ef26e0  8MdDamage           0x00ef1da0  8MdAttack
  0x00ef29d8  14MdDamageAerial    0x00ef3d48  5MdHit
  0x00ef2bd0  16MdDamageSpinBlow  0x00ef3da0  8MdHitBuf
  0x00e9f9a0  25MdDamageCalcEventListener
  0x00e9f988  21MdDamageEventListener
  0x00f01f78  10DamageInfo        0x00efe028  9HitAtkLog
```

A name string is pointed at by its `typeinfo`, and a `typeinfo` is pointed at
by every vtable of its class, so two word searches walk from a class name to
its method table. `8MdDamage`'s three vtables put its methods between
`0x0061d000` and `0x00620000`, which is how this session found the module at
all.

Two more things fell out of the strings. The build's assertion macros kept
their `__FILE__`, so `E:/external_job/workspace/rhn_ps3_us/home/program/`
is the source root, with `ga/source/lib/` a middleware layer beside
`domain/src/`; and the anonymous namespaces name seven `.cpp` under
`src/app/` — `piece/piece.cpp`, `entity/stage/destructible_object.cpp`,
`entity/stage/treasure_coffer.cpp`, `item/it_closet_accessor.cpp`,
`menu/shop/billing/mu_sh_billing.cpp`, `other/collision_mgr.cpp`, `main.cpp`.

## A cross-reference that needs no disassembler

Almost every global in this build is reached as `lwz rN, d(r2)`, and `r2` is
whatever the caller loaded out of the descriptor. That makes an exact
cross-reference two steps of arithmetic, and `ppc.py refs` is those two:

1. find the TOC slots whose word is the address wanted;
2. find the `r2`-relative instructions whose displacement lands on one of
   them, **under the TOC the containing function's own descriptor gives it**.

Nothing is guessed — the descriptor names the `r2`. It runs over all four
million instructions in about a second:

```
$ python tools/ppc.py refs eboot.elf ef5550        # "se_hitlevel_tbl"
6 instructions reach 0x00ef5550 through the TOC
  in the function at 0x003ec7fc:  0x003ec800  lwz  from slot 0x0113756c
  ...
  in the function at 0x006587c8:  0x0065881c  lwz  from slot 0x0113756c
```

This is what turns a name in a string pool into a function, and it is how
every address below was found.

---

# The damage expression

**Ledger item 1.** `combat_loop.md` put it this way: *"Every input is on the
disc — the weapon's attack, the monster's `def`, the region's flat modifier
and six multipliers, `cri` and `dmg_critical_factor` — and the expression
combining them is not."* It is `FUN_00622fe4`, 1,368 bytes at `0x00622fe4`,
and this is it.

## Where it sits

`FUN_0061f890` (2,372 bytes) is the hit resolver — one landed volume against
one body — and it calls two things in order:

```c
level  = FUN_006235fc(scratch, target, hit, attacker, source);
damage = FUN_00622fe4(scratch, target, hit, attacker, source, level, critical, 0);
...
actor[0x21] += damage;          /* a running total on the attacker */
```

so `FUN_00622fe4` is *the* number. It builds two structures, hands both to the
listener chain, and then multiplies.

## The two structures, and their defaults

The attack side is built by `FUN_00245870` (reached through the thunk at
`0x00a4c0ac`) and the defence side by `FUN_00245678` (through `0x00a4c0cc`).
Both are short enough to read whole, and between them they name every field:

```
  the attack side, eleven floats           the defence side, six floats
  ------------------------------           ----------------------------
  a[0]  base      virtual  +0x10c          d[0]  base   param + 0x2c4
  a[1]  flat      0.0                      d[1]  flat   0.0
  a[2]  add       virtual  +0x110          d[2]  rate   1.0
  a[3]  rate      1.0                      d[3]  mul    1.0
  a[4]  power     the hit record's [0]      d[4]  mul add 0.0
  a[5]  power add 0.0                      d[5]  cut    0.0
  a[6]  crit      "dmg_critical_factor"
  a[7]  crit add  0.0
  a[8]  spare     1.0
  a[9]  the hit record's [1]
  a[10] 0.0
```

Every `add` is zero and every `rate` is one on a bare hit. **They are there
for the listeners**: `MdDamageCalcEventListener` is called once over the
attacker's list with the attack structure (`vtable + 8`) and once over the
target's with the defence structure (`vtable + 0xc`), between the build and
the arithmetic, and that is where a card, an ability or a buff gets to move a
term. The class is named in the binary and it is exactly what its name says.

The attacker's base attack is a **virtual call**, not a field — which is the
disc's own split showing through: `params.md` found `atk` in 82 actors and
all 82 are monsters, and the six player classes carry none of the three. One
implementation reads the parameter block, the other reads the weapon.

## The expression

The two constants in it are `1.0` and `0.0`, read out of TOC `0x113b7e0` at
`-0x55c4` and `-0x55c0`. Written out:

```
  attack  =  clamp≥1( (a[0] + a[2]) * a[3] + a[1] )      the attack, modified
          *  max0( a[4] + a[5] )                          the hit's power
          *  max0( d[3] + d[4] )                          what the target takes
          *  a[8]
          *  ( critical ? a[6] + a[7] + 1 : 1 )           dmg_critical_factor

  defence =  max0( d[0] * d[2] + d[1] )                   def, modified

  damage  =  attack - defence

  if damage > 0:
      damage *= 1 + f(hit, target)                        a per-node factor
      damage -= damage * max0( d[5] )                     a cut, as a rate

  damage  =  max( damage, 1 )
```

and then, once, an ability: if the attacker's ability holder answers to id
`0xcc`, `damage = max((value + 1) * damage, 0)`. `it_db_ability.bin` has 233
rows, so `0xcc` is one of them; the hit resolver above queries `0x70` and
`0x71` the same way, and `0x70`'s range in that table is `(0, 1)`, which is a
rate. **The engine indexes the disc's own ability table by row number**, in
the clear, in the damage path.

Four of those lines are worth naming separately.

- **The defence is subtracted.** `combat_loop.md` item 5 asked for the sign
  convention of a region's flat modifier and said *"nothing on the disc proves
  it is subtracted rather than added"*. The binary does: `attack - defence`,
  one `fsubs`, and the defence term is clamped to zero first so a negative one
  cannot add. A weak point is `-450` and it makes the subtraction smaller.
- **The floor is 1, not 0.** A hit that fails to get through still takes a
  point. That is a real behaviour and no table on the disc carries it.
- **The critical is a multiplier of the form `1 + factor`**, and `factor` is
  read out of the actor's parameters by the name `dmg_critical_factor` — the
  same string `params.md` has listed since session 12.
- **The per-node factor is authored on the hit.** `FUN_00622c7c` looks the
  target's node identifier (`+0x2c`) up in a table the hit record carries at
  `+0x8c`, `[0xf8]` entries of twelve bytes, and applies its second word as
  `1 + f`. So a single volume can be worth different amounts against different
  parts, independently of the region's own multipliers.

## The parameter record, and the offset that proves it

`d[0]` is `*(float *)(parameters + 0x2c4)` and the claim that `0x2c4` is `def`
is not an inference. The parameter reader is `FUN_0064b3d8`: it walks a
default block and a resolved block side by side, one field per call, with the
field's **name** in `r5` each time. Reading its TOC slots back through
`ppc.py`:

```
  r2-0x47e4  wall_stop     stw   0x6c      an int
  r2-0x47e0  wall_dmg      stfs  0x70
  r2-0x47dc  atk           stfs  0x74
  r2-0x47d8  cri           stfs  0x78
  r2-0x47d4  def           stfs  0x80
```

and both callers place that record at a fixed offset in the parameter object:

```
0x0064bb38  addi  r4, r31, 0x244
0x0064bb54  bl    0x64b3d8
```

`0x244 + 0x80 = 0x2c4`. The name order is the disc's own — `params.md` lists
`atk`, `cri`, `def` in that order — the offsets are the compiler's, and they
meet on the number the damage function reads.

---

---

# The player's numbers, and the file they were in all along

**Ledger item 2**, and the binary found it on the disc rather than in itself.

The attack term's base is a **virtual call**, `vtable + 0x10c`, and that looked
like the split: the monster reads a field, the player computes from the
weapon. It is not the split. Bounding each vtable by its own length and
reading slot `+0x10c` out of all 1,169 typeinfo objects gives **three
implementations**, and one of them covers **all 67 `CH*` classes** — the six
player classes and every monster together:

```c
double CHCharacter::attack(Actor *this) {          /* 0x002471bc */
    if (this->parameters == 0) return 0.0;
    return *(float *)(this->parameters + 0x2b8);   /* atk */
}
double CHCharacter::attackAdd(Actor *this) {       /* 0x0024a098 */
    ...                                            /* +0x2c0 */
}
```

`+0x2b8` is `atk` and `+0x2c0` is the offset the parameter reader **skips** —
`atk` at record `0x74`, `cri` at `0x78`, `def` at `0x80`, and nothing parsed at
`0x7c`. So a player's `atk` is not absent from the struct. It is *written* into
it by something that is not the JSON, and the setters say so plainly:

```
0x0064a82c  stfs f1,0x2b8(r3)   stfs f1,0x9c(r3)   blr     set atk
0x0064a838  stfs f1,0x2c4(r3)   stfs f1,0xa8(r3)   blr     set def
0x0064a844  stfs f1,0x2c0(r3)   stfs f1,0xa4(r3)   blr     set atk add
0x0064a850  stfs f1,0x244(r3)   stfs f1,0x28(r3)   blr     set hit points
```

Four setters, twelve bytes each, and each writes the field **twice** — once at
`+0x244` and once at `+0x28`, exactly `0x21c` apart. That is the parameter
object holding two copies of the same record, the parsed defaults and the
resolved values, which is the pair `FUN_0064b3d8` walks side by side.

Three callers set them, and one is the answer:

```c
FUN_006dba28() -> setHp    /* rec + 8, an int   */
FUN_006dba88() -> setAtk   /* rec + 0, a float  */
FUN_006dbaac() -> setDef   /* rec + 4, a float  */

int record(this, job, level) {           /* FUN_006db9fc */
    return *(int *)(this->table[job] + 4) + level * 0x10;
}
```

**A sixteen-byte record, indexed by job and by level.** That is a growth
curve, and `combat_loop.md` item 2 had concluded there was none on the disc.

## `misc.cpk/ccparamobj.bin`

There is. It is an `ELBN` — a format this repository has read since session 19
— and it had been sitting in the survey with its contents unread, under the
engine's own names:

```
$ python tools/elbn.py levels extract/tree
misc.cpk/ccparamobj.bin
  19 entries; the six classes, their headers and their tables
  the header says (count, offset) and the table is that long, on 6 of 6

  lv  warrior                      hammersmith                  assassin
         atk    def      hp     4th     atk    def      hp     4th     atk    def      hp     4th
   0    80.0   30.0    1000    1000   125.0   35.0    1250     850    80.0   30.0     800    1200
   9   160.0   83.0    2800    2800   190.0   80.0    3500    2200   140.0   68.0    2200    3300
  13   160.0   83.0    2800    2800   190.0   80.0    3500    2200   140.0   68.0    2200    3300
```

`as_par`, `cl_par`, `hs_par`, `ht_par`, `mg_par`, `sw_par` are eight bytes
each and read `(14, offset)`; `as_lv_par` and its five siblings are 224 bytes
each, which is 14 rows of 16. **The header and the table agree on all six.**

Item 2 asked for *"the starting value the modifiers apply to"* and said, from
`hp_rec` and ability 3's ±8000, that it had to be **in the thousands**. It is:
700 for the mage, 1,250 for the hammersmith.

Three more things fall out, and none of them was arranged.

- **`job_par` has eight slots and two are zero** — `as`, `cl`, —, `hs`, `ht`,
  `mg`, —, `sw`. Those are the job ids `it_db_weapon.bin` column 5 uses,
  **0, 1, 3, 4, 5, 7**, a numbering this repository has carried since session
  21 without knowing why it skips 2 and 6. The EBOOT answers that too: eight
  job names sit in one run at `0x00f01f30`, alphabetically — `assassin`,
  `cleric`, **`gunner`**, `hummer`, `hunter`, `mage`, **`ninja`**, `sword`.
  The two holes are the two jobs that did not ship.
- **The level is story progress, bucketed.** `s_job_data` points at fourteen
  `(threshold, row)` pairs: 12,000 to 24,000 every 1,000, with 0 at the floor.
  [`format_reward.md`](format_reward.md) reads a reward block's head as *"a
  story-progress threshold: 0, or 11000..24000"* — **the same number space and
  the same ceiling**, read off a different table by a different tool three
  sessions ago. So the player levels with the story and not with kills, which
  is what a game with no experience table on its disc had to be doing.
- **The growth stops before the table does.** Row 9 is the last that differs
  from the one above it, on all six classes, so progress 21,000 to 24,000
  moves nothing. The curve ends four rows early.

The fourth column is a reading and is marked as one: it runs the same curve,
it equals `hp` exactly on the warrior, the hunter and the cleric and differs
on the other three, so it is a second pool — and the only other pool the game
names is `it_db_ability.bin` ability 4, *Raises MAX AP*.

## How to rebuild all of this

Four commands. The ELF, the keys and the Ghidra project all stay outside the
repository; the tools do not.

```
python tools/self.py decrypt extract/PS3_GAME/USRDIR/EBOOT.BIN <keys> eboot.elf
python tools/psq.py  api     extract/tree                    > api.tsv
python tools/ppc.py  plant   eboot.elf api.tsv                 plant.tsv
                                       # then strip the section table, see above
analyzeHeadless <project dir> ROA -import eboot.elf \
    -scriptPath tools/ghidra -preScript PlantOpd.java plant.tsv
```

After that every question is one `Query.java` verb and needs no window:

```
analyzeHeadless <project dir> ROA -process eboot.elf -noanalysis \
    -scriptPath tools/ghidra -postScript Query.java decomp 0x00622fe4
```

## What this settles, and what it does not

Settled: **the damage expression** (ledger 1), and **the sign of the defence
term** (half of ledger 5 — what a region's six multipliers are six of is still
open, and `d[3]`/`d[4]` is where they would have to arrive).

Not settled, and each now has a place to stand rather than a search:

- **the hit level** (ledger 4) — `FUN_006235fc` returns the value the
  resolver calls `level`, and it starts from a **byte at `+0x103` of the hit
  record in memory**, passes it through the same listener chain, and returns
  an int. That is very likely the `+0x35` of ledger 3 in its runtime form,
  and it is not proved here;
- **`react_p`** (ledger 8) and **`se_hitlevel_tbl`'s third word** (ledger 7) —
  the six references to `se_hitlevel_tbl` are five accessors around
  `0x003ec7fc` and one loader at `0x006587c8`, which caches three block
  pointers at `+0x24`, `+0x28` and `+0x2c` of its owner. The consumer is
  whatever reads those, and that is a `refs` away;
- **the player's base defence and hit points** (ledger 2) — the attacker's
  base attack is a virtual call, so the player's implementation of it is
  reachable and the same object will carry the rest.

And then it was written into the engine. [`damage.py`](../engine/damage.py)
is the expression line for line and
[`mission.py`](../engine/mission.py) takes a monster's own `hp` down with it,
so **`BLOWS` and `BREAKS` are retired** — see [`parity.md`](parity.md). Two
things had to be decided to do it and both are marked as readings there: where
a region's flat modifier and its six multipliers arrive in the defence
structure. The argument is that the builder's defaults are `0.0` and `1.0` and
the disc's medians, over 315 regions and 1,890 multipliers, are `0.0` and
`1.000`.

One more thing came out of the writing, and it is the sharpest thing this
session found about what is *still* missing. The player's row in the growth
table is chosen by story progress, so at `PROGRESS = 11000` — the save-file
stand-in — a chapter-14 quest fields a level-0 player: a thirteen-quest sample
killed **7 of 50** and closed **0 of 9** arenas. Taking the row from the
quest's own progress requirement, which is what the purse already does for its
reward block, that becomes **61 of 82** and **7 of 14**. The gap that is left
is the **weapon**: a level-13 body swinging a level-1 sword, because nothing
on the disc says what a player would be carrying. Retiring one stand-in made
another one legible, which is what the list is for.
