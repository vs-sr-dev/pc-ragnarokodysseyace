# `effect.bin` — where an effect goes

**Status: solved, both schemas.** 69 files, 3,918 rows; **69 read, 0
failures**. Reader: [`../tools/effect.py`](../tools/effect.py).

A [`.PTP`](format_ptp.md) block is a particle system with no placement in it.
It does not know how big it is, where on the body it hangs, which way it
points, or how often it fires. `effect.bin` is the file that knows, and it is
the last unread link in the effect layer: a [`.mkc`](format_mkc.md) frame
reaches a row here, and the row reaches a `PTB`.

There are two of them, and they are different structs that happen to share a
name, a width and a container:

| | files | rows | who addresses it |
|---|---:|---:|---|
| the **motion** table | 54 | 2,434 | `.mkc` opcode `0801`, by row id |
| the **stage** table | 15 | 1,484 | nobody — it is a placement list |

The stage one carries an `ECH` string pool and the motion one does not, which
is the quickest way to tell them apart.

---

## The motion table

One per motion set: twelve player classes, forty monsters, and the two copies
of `stage.cpk/060`'s shield.

```
+0x00  u8   kind       1, and 0 on 102 rows of 2,434
+0x01  u8   id         the number `.mkc` 0801 asks for
+0x02  u8   category   0 = misc.cpk/misc.PTP, 1 = the actor's own effect.PTP
+0x03  u8   slot       the block in that bank
+0x04  u32  locator    a CMDL S4 id: where on the body it hangs, 0 for none
+0x08  u8   unread     0, 1 or 2
+0x09  u8   unread     a bit field: 0x00 0x40 0x60 0x80 0xc0 0xe0
+0x0a  u8   unread     a bit field: 0x00 .. 0x0a
+0x0b  u8   0xff       on all 2,434 rows
+0x0c  f32  scale
+0x10  f32  x          an offset from the locator, in metres
+0x14  f32  y
+0x18  f32  z
+0x1c  u32  axis       1, 2 or 3, with the angle beside it
+0x20  f32  degrees
+0x24  u32  axis       a second rotation, never about the first axis
+0x28  f32  degrees
+0x2c  ...  zero on all 2,434 rows
```

Everything is big-endian, as everywhere else on this disc.

### `.mkc` addresses the id, not the row

`0801`'s argument is the byte at `+0x01`. It is **unique inside every one of
the 54 tables** — zero duplicates over 2,434 rows — but it skips wherever an
effect was cut, so it is not the row's position: `b15` has 48 rows and ids
that run to 67.

| the `0801` argument read as | of 4,190 references |
|---|---:|
| a 1-based row position | 4,125 resolve |
| **the id byte at `+0x01`** | **4,187 resolve** |

That closes thirteen of the fourteen pacs that
[`format_mkc.md`](format_mkc.md) listed as *indexing past the end of their own
`effect.bin`*. `b02`'s 79 against 73 rows, `b15`'s 67 against 48, `z09`'s 20
against 16 and `fht`'s lone 253 against 43 are all ids that are simply there.
The one that is left is **`z07`**, which asks for 4, 5 and 6 three times
between them and carries ids 1, 2, 3, 7 and 8.

Every table opens on **id 1**, and on 50 of the 54 that row is `(1, 1)` — slot
1 of the actor's own bank, which is often an empty slot. `.mkc` asks for id 1
on three tables only (`fas`, `mas`, and the shield, which all point it
somewhere real), so on the other 51 it is a default row that nothing
addresses.

### The `(category, slot)` pair is the `.PTP` address

The same one `eff_vari_tbl` and the stage scripts use, and it lands:
**2,410 of the 2,434 rows reach a filled block** of the bank the category
names. Eighteen of the twenty-four that do not are the id-1 default row
described above; four more are `fmg`/`mmg` reaching slots `job.cpk/mg`'s bank
leaves empty; the last two are row 31 of the `z18`/`z20` copies of a table
that `z19` and `z27` share, asking for slot 8 of a bank those two monsters
have and these two do not — the same shape of defect as `b19`'s footstep
aimed at emitter 31300.

### The `u32` at `+0x04` is a `CMDL` locator id

The same namespace as `.mkc`'s `7ff9` emitter — `CMDL` section `S4`, the
`(id, node)` table [`format_cmdl.md`](format_cmdl.md) describes. **455 of the
457 non-zero values resolve** against the actor's own rig, and the vocabulary
reads itself:

| locator | n | the node it binds to |
|---|---:|---|
| 1000 | 34 | `node_hip` |
| 1100 / 1200 | 22 / 33 | `node_l_hand` / `node_r_hand` |
| 1300 / 1400 | 27 / 4 | `node_head`, `node_human_head` |
| 1600 | 2 | `node_jaw` |
| 1700 / 1800 | 16 / 18 | `node_l_toe`, `node_l_foot` / the right pair |
| 4000 / 4100 | 66 / 1 | `node_r_weapon` / `node_l_weapon` |
| 10000 … 10403 | 201 | `eff_10000`, `eff_10200`, `eff_10300`, `eff_10304`, … |
| 10600 | 1 | `node_tail4` |
| 10900 | 4 | `big_gun`, which is the shield stage's own turret |
| 31100 / 31200 | 5 / 4 | `node_l_finger` / `node_r_finger` |
| 31700 / 31800 | 4 / 3 | `node_l_toe` / `node_r_toe` |

`node_r_weapon` sixty-six times is the weapon trail. The other 1,977 rows
leave the field at 0 and hang the effect off the actor's origin. The two
strays are both `b19`, the rider on a horse, which asks for 35 and 1810 and
declares neither.

### The two rotations

`(u32, f32)` twice. The `u32` is 1, 2 or 3 and the `f32` is an angle in
degrees: 168 of the 181 angles are a whole multiple of five, and **no row
ever names the same axis twice** — 39 rows carry both pairs and all 39 name
two different axes. That is what an artist typing Euler angles into a tool
leaves behind.

### What a table reads like

`python effect.py list extract/tree monster.cpk/pac/z01.pac` — Bloody
Gunner's twenty-five:

```
  id cat slot locator node        scale       offset  rotation    asset
  11   0   58                         1      0 0 1.5              ef_I_hs_rock001_M.pac
  12   0   35   10000 eff_10000       1                           ef_comm_228_wind001_R.rnx
  13   0   67                       2.1    0 1.3 0.5  z-110 y+245 ef_I_def_wind001_M.pac
  16   0   46                       0.5  0.55 0 0.35              ef_I_smoke001.ctex
  17   0   46                       0.5  -0.5 0 0.4               ef_I_smoke001.ctex
  18   0   46                       0.5  1.05 0 0.7               ef_I_smoke001.ctex
```

Rows 16 to 24 are the same smoke puff at half size, scattered a metre either
way with **`y` left at zero** — nine dust clouds on the ground. Row 13 is a
wind shell at twice size, 1.3 m up and turned to face two ways at once.

---

## Category 2 is this file

[`format_ptp.md`](format_ptp.md) had one addressing mode it could not place:
`eff_hitlevel_tbl` in each of the six classes' `objbin.bin` addresses effects
as `(2, id)`, the bow reaches id 252, and **no `PTCP` on the disc has 252
slots**. It does not need one.

**Category 2 is the class's own `effect.bin`, addressed by row id: 96 of 96
pairs resolve.** `python effect.py hitlevel extract/tree`:

```
fht  33 rows  33 distinct (2, id), 33 resolve   scales [0.5, 0.8, 1.0]
```

`fht`'s ids are 110, 111, 112, 120, 121, 122, 130 … 250, 251, 252 — the
"weapon kind × 10 + hit level" the earlier reading guessed at — and each
triple is **one `.PTP` slot at scale 0.5, 0.8 and 1.0**:

```
110   1/1   0.5   ef_I_hit101_02_R.rnx
111   1/1   0.8   ef_I_hit101_02_R.rnx
112   1/1   1     ef_I_hit101_02_R.rnx
120   1/2   0.5   ef_I_ht_vulfire001_M.pac
121   1/2   0.8   ef_I_ht_vulfire001_M.pac
122   1/2   1     ef_I_ht_vulfire001_M.pac
```

Eleven weapon kinds, three hit levels, and the hit level is the *scale*. The
same three numbers — 0.5, 0.8, 1.0 — come out of all twelve player tables.

---

## The stage table

One per stage that has ambient effects, sitting beside the `effect.PTP` it
addresses. It is a placement list: a row is one effect standing on one named
marker in one room.

```
+0x00  u32  str  the room, or 0 to carry the previous row's
+0x04  u32  str  the marker the effect stands on
+0x08  u8   unread    0 or 1
+0x09  u8   unread    1 or 10
+0x0a  u8   slot      the block in the stage's own effect.PTP
+0x0b  u8   unread    0x80 or 0xc0
+0x0c  f32  a distance, 15 .. 50
+0x10  f32  the other one, >= the first on 1,469 rows of 1,484
+0x14  f32  x        zero on every row
+0x18  f32  y        the offset the script calls `_y_offset`
+0x1c  f32  z        non-zero on three rows
+0x20  f32  rotation about x, in degrees
+0x24  f32  about y, which is where all the variety is
+0x28  f32  about z, zero on every row
+0x2c  f32  scale
+0x30  f32  seconds, fixed
+0x34  f32  seconds, random
+0x38  i32  cue id, -1 for none
```

There is **no category lane**, because there is no choice: all 1,484 rows land
on a filled block of the stage's own `effect.PTP`, and 24 of them are on a
slot `misc.PTP` leaves empty or has not got, which is what rules the common
bank out.

### The script says what the columns are

`stage.cpk/050_02_03/param.pac` declares the record in the clear and then
lists six markers with it:

    class EffData { _hta_name; _eff_cate; _eff_id; _rnd_radius; _y_offset;
                    _sec_fix; _sec_rnd; _cue_id; _work }

    EffData('ef_fire01', 1, 8, 0, -8.5, 5, 5, 3, 190)
    EffData('ef_fire03', 1, 9, 2, -8.5, 5, 5, 2, 188)

`stage.cpk/050/effect.pac/effect.bin` lists **the same six markers for the
same room**, and the two agree field for field:

| marker | the script's `_eff_id` | the table's `+0x0a` | `_y_offset` | `+0x18` | `_sec_fix`, `_sec_rnd` | `+0x30`, `+0x34` |
|---|---:|---:|---:|---:|---|---|
| `ef_fire01` | 8 | 8 | −8.5 | −8.5 | 5, 5 | 5, 5 |
| `ef_fire02` | 8 | 8 | −8.5 | −8.5 | 5, 5 | 5, 5 |
| `ef_fire03` | 9 | 9 | −8.5 | −8.5 | 5, 5 | 5, 5 |
| `ef_fire04` | 8 | 8 | −8.5 | −8.5 | 5, 5 | 5, 5 |
| `ef_fire05` | 9 | 9 | −8.5 | −8.5 | 5, 5 | 5, 5 |
| `ef_fire06` | 8 | 8 | −8.5 | −8.5 | 5, 5 | 5, 5 |

and slots 8 and 9 are the only two blocks in that file that name
`anm_ef_M_vlcn001.txx`, a volcano. `_rnd_radius` has no lane in the binary —
the script's version of the record carries one field the table does not.

**`_work` is not a field of the record at all: it is a slot number.** The same
script's `effect_update` reads `getInt(0, val._work)`, decrements it, and puts
it back with `setInt` — `setInt`/`getInt` are the host's integer store, banked
and slotted, and `_work` names the slot where that effect's countdown lives.
The six fires are given `190 - 0` … `190 - 5`, with the phase at 191. That is
why the binary has no lane for it: the table is placement, and the countdown is
runtime state.

The rest of that function is the whole effect API in fourteen lines, and it is
worth reading beside this table:

```
function setExplosion(data)
    array   = getHTAPos(data._hta_name)      // the marker, as [x, y, z]
    offsetV = genXZPoint(data._rnd_radius)   // a point in a disc of that radius
    handle  = effStart(data._eff_cate, data._eff_id)
    effSetPos(handle, x, y + data._y_offset, z)
    effSetRot(handle, 0, cfGetRandI(65536), 0)   // a random yaw, one full turn
    cfSndPlayStgSE3D(-1, data._cue_id, 0, x, y, z)
```

and `genCycle(fix, random)` — the period — is `fix * 30 + random * 30 * rand()`,
which converts `_sec_fix` and `_sec_rnd` from seconds to a frame countdown.
See [`format_api.md`](format_api.md).

### Two identities that close

**A row names a cue exactly when it carries a period.** 44 rows do both, 1,440
do neither, and not one does one without the other. A fire that restarts every
five seconds makes a noise when it does; embers and smoke run continuously and
are silent.

**A row stands on a marker its room declares.** 1,483 of the 1,484 `(room,
marker)` pairs are in that room's [`hta.bin`](format_stage.md), so the table
joins straight through to a world position. The one that is not is
`080_01_02`'s `ef_uplight001`, in a room that declares `ef_uplight002` and no
`001`.

### What a stage reads like

`python effect.py list extract/tree stage.cpk/050/effect.pac`:

```
room        marker    slot  scale    y   yaw   period  cue  asset
050_01_01   ef_01        3      1    0     0                ef_M_hinoko001.ctex
            ef_02        2      1 -1.5     0                ef_M_smoke002.ctex
            ...
            ef_09        4      1    0     0  20+10 s    8  ef_M_fire001.ctex
            ef_10        4      1    0     0  25+10 s    8  ef_M_fire001.ctex
```

Embers at the room's centre, smoke a metre or two below the ledges, and two
fires that flare every twenty to thirty-five seconds with a sound.

---

## Still open

- **The three unread bytes of the motion row**, `+0x08` to `+0x0a`. They are
  bit fields and they correlate with the rest of the row without matching it:
  `+0x09` is `0xc0` on 1,192 rows of which 87 % carry an offset and 1 % a
  locator, and `0x00` on 256 of which 66 % carry a locator — which reads like
  a space or a follow mode, one number saying whether the effect rides the
  bone or is dropped in the actor's own frame. Nothing here tests that.
  `0x20` looks like *carries a rotation* and is not: 62 of the 142 rows with a
  rotation have it.
- **The two unread bytes of the stage row**, `+0x08` (0 or 1) and `+0x09`
  (1 or 10). Neither is the category, which is not stored.
- **The two distances at `+0x0c` and `+0x10`** of a stage row. They are
  nearly constant per stage — `050` is 20 and 25 throughout, `160` is 15 and
  20 — and the second is the larger on 1,469 rows of 1,484, which is what a
  near/far cull or fade pair looks like. Read as a pair of seconds they would
  duplicate the period at `+0x30`, which is exact.
- **`kind` at `+0x00` of a motion row**, 0 on 102 rows in 17 tables and 1 on
  the other 2,332. Category, locator, bank and the three bit fields are all
  distributed about the same either side of it, so nothing in the row splits
  with it.
- **`z07`**, whose `.mkc` asks for effect ids 4, 5 and 6 and whose table
  carries 1, 2, 3, 7 and 8.
- **The inside of a `PTB`**, which is still where the actual particles are.
  See [`format_ptp.md`](format_ptp.md).

## Reading one

    python effect.py check    extract/tree                every identity
    python effect.py survey   extract/tree                every table, one line
    python effect.py list     extract/tree <name>         one table, decoded
    python effect.py refs     extract/tree                .mkc, as a row and as an id
    python effect.py hitlevel extract/tree                category 2
    python effect.py locators extract/tree                +0x04 against the rigs
