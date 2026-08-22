# The actor parameters — 89 JSON files

**Status: read.** No format work was needed; the files are plain, pretty-printed
JSON sitting on the disc uncompressed. Tool:
[`../tools/params.py`](../tools/params.py).

89 files, 1,069 records, 1,056 distinct field names. Six in `job.cpk`, one per
player class; 83 in `monster.cpk`, one per monster directory.

These are the numbers that decide how the game *feels*: acceleration, run
speed, turn rate, hit-stop windows, stagger thresholds, status resistances,
drop rates. On a reimplementation they are worth more than any amount of
disassembly, and the disc hands them over in the clear.

## Records are a base plus overlays

Each file is a dictionary keyed by a number. Record `"0"` is the base; the rest
merge over it. It is a **merge, not a subset overlay** — 440 of the 980
non-base records introduce at least one field the base never set, so a reader
that assumes the base declares the full schema will silently drop those.

### For a monster the key is a difficulty tier

The pairing is regular and measurable. For every even key `n` with a partner
`n+1`, the two are the same monster at a higher `region_lv`:

```
$ python tools/params.py tiers extract/tree
168 (n, n+1) key pairs across the monsters
  region_lv step: +3 x123, +1 x44, +0 x1
  hp ratio      : 1.5x x138, 1.0x x30
  atk ratio     : 1.2x x46, 1.0x x16, 1.13x x8, 1.12x x7, 1.171x x7
```

`hp` is **exactly ×1.5** in 138 of 168 pairs — a rule, not a coincidence.
`atk` is hand-tuned; ×1.2 is the most common but far from universal.

The Orc King, whole:

| key | region_lv | hp | atk |
|---:|---:|---:|---:|
| 10 | 1 | 25,000 | 300 |
| 11 | 4 | 37,500 | 360 |
| 20 | 2 | 25,000 | 400 |
| 21 | 5 | 37,500 | 480 |
| 40 | 6 | 60,000 | 800 |
| 41 | 7 | 90,000 | 850 |
| 250 | 2 | 30,000 | 480 |
| 251 | 5 | 45,000 | 570 |

### For a player class there are three records

Record 0 is the base. Record 1 raises `acc` (0.035 → 0.1), `run_sp`
(0.17 → 0.22), `fast_acc` and `fast_sp`, drops `stun_f` from `[90, 0]` to `0`,
and lifts the first element of every `ab_*` status vector from 7 to 9 — 39
fields in all. Record 2 changes four movement fields, slightly.

Record 1 is plainly a **buffed state**: faster, unstunnable, more resistant.
Nothing in the file names it, and searching the game's text for a matching
mechanic found nothing, so this document does not claim to know what it is.
The Yggdrasil tower has a "fever" mechanic with its own tables
(`yggdrasill_fever_status_up.bin` grants a 60-second buff) which is the obvious
candidate, but no data on the disc connects the two.

## The six classes are more alike than expected

Of the 225 fields in a class's base record, **173 are byte-identical across all
six** and only 52 differ. Basic locomotion is shared exactly:

```
                as       cl       hs       ht       mg       sw
acc          0.035    0.035    0.035    0.035    0.035    0.035
run_sp        0.17     0.17     0.17     0.17     0.17     0.17
walk_sp       0.05     0.05     0.05     0.05     0.05     0.05
rot_y_spd       32       32       32       32       32       32
weight          50       50       50       50       50       50
col_r          0.5      0.5      0.5      0.5      0.5      0.5
```

What differs is combat: attack speed and braking, evade (`es_*`), hit-stop,
critical rate, and guard.

**Guard is the tell.** `guard`, `guard_def`, `guard_ap_mul`, `guard_resist_s`,
`guard_resist_l`, `guard_dmg_cut_rate` and the whole `jg_*` family are present
for **`cl` and `sw` only** and absent from the other four. Those are the two
classes that carry a shield. A field that exists for exactly the right two
classes is the kind of confirmation that costs nothing and settles a naming
question outright.

The evade profile separates them further — the Assassin accelerates harder and
travels further than anyone (`es_acc` 0.4 against 0.2, `es_spd` 0.58 against
0.29–0.36) and recovers in a third of the frames.

For a reimplementation this means **one movement model, not six**: build the
shared locomotion once and parameterise the 52 combat fields.

## The stagger model, complete

Four fields describe it, and they close:

```
stg_p     [7, 40, 80, 100]        thresholds
stg_s_r   [1, 0.8, 0.5, 0]        small flinch
stg_l_r   [0, 1, 0.5, 0]          large flinch
stg_d_r   [0, 0, 0.2, 1]          knockdown
stg_dec_s 0.8                     decay
```

`stg_p` is **strictly ascending in all 1,068 records that have it**, and always
four elements — which is what makes "thresholds" a finding rather than a guess.
As accumulated stagger crosses each one, the reaction shifts: small flinch at
first, large flinch in the middle, guaranteed knockdown at the top.

The three ratio vectors do **not** sum to 1 (the per-stage sums run 1.0, 0.8,
1.6, 0.0, 0.3, 1.2 across the disc), so they are independent weights and not a
partition of one reaction.

A boss reads very differently from a player:

```
Orc King      stg_p   [70, 110, 180, 240]
              stg_s_r [0.0, 0.6, 0.1, 0.0]
              stg_l_r [0.0, 0.2, 0.5, 0.0]
              stg_d_r [0.0, 0.0, 0.2, 1.0]
```

Every reaction is zero at stage 0 — nothing under 70 points moves him at all,
which is super-armour written as data — and stage 3 is a guaranteed knockdown.

## A core schema plus a per-move vocabulary

66 fields appear in 80% or more of the monsters. That is the shared actor
model: `hp`, `atk`, `def`, `cri`, `acc`, `run_sp`, `walk_sp`, `rot_y_spd`,
`weight`, `col_r`, `shadow_r`, `scale_min`/`scale_max`, the `stg_*` family, the
`ab_*` family, `stop_*` and `dmg_stop_*` hit-stop windows, `down_f`,
`down_stand_f`, `it_drop`, `prob_silver`/`prob_gold`,
`skill_silver`/`skill_gold`, `myorder_point`, `region_lv`.

609 fields appear in at most two actors. Those are per-move parameters, and
they are named after the monster or the move that uses them: `b05_*` (49),
`b10_*` (44), `b12_*` (38), `spear_*` (20), `fly_*`, `tire_*`. So the file is
a common struct followed by a bag of attack-specific tuning, which is a strong
hint about how the engine is organised: shared actor physics, plus a per-move
table the animation commands read.

## Naming convention

The suffix carries the unit, consistently enough to depend on:

| | | evidence |
|---|---|---|
| `_f` | frames, at 1/30 s each | integral in 1,926 of 1,932 occurrences |
| `_p` | points | integral in all 4,490 occurrences |
| `_sp` | metres per frame | small floats, ~0.05 to 0.6 |
| `_acc` | metres per frame squared | smaller floats still |
| `_r` | radius, or ratio | mixed integral and fractional |
| `_y` | a vertical component | roughly half fractional |

**And the units are now dimensional.** One world unit is one metre and one
frame is 1/30 of a second — see [`units.md`](units.md), which recovers both
from the geometry of the walk and run cycles. So `run_sp = 0.17` is 5.1 metres
a second, `acc = 0.035` is 31.5 metres per second squared, and
`fall_gravity_y = -0.035` is 3.2 times Earth gravity. The animations are
authored against these numbers: the planted foot of `fas213run` slides
backwards at 0.1698 against a declared 0.17.

And the prefix carries the subsystem: `ab_` abnormal status, `stg_` stagger,
`prob_` drop probability, `cmb_` combo, `es_` evade, `jg_` guard, `dmg_`
damage, `camera_` camera.

The `ab_*` status vectors are five elements. Only element 0 changes in the
player's buffed record (7 → 9), which makes element 0 the **resistance
threshold**; across the disc it ranges 1–10 while the other four range
10–250, 10–80, 60–90 and 1–5. The named statuses are `pss`, `psl`, `prl`,
`frz`, `brn`, `nrv`, `ten`, `tir`, `atd`, `dfd` — paralysis, freeze and burn
are unambiguous, and `atd`/`dfd` read as attack-down and defence-down.

## One disc oddity

`z12_00`, `z12_01` and `z12_02` each contain a file named **`z10_00.json`**,
with different contents in each. The actor's identity is its **directory**, not
its filename. Keying on the stem silently reduces 89 files to 86 and keeps
whichever was read last — which is exactly what happened the first time this
was counted.

## Open

- What records 1 and 2 of a player class are.
- The remaining four elements of the `ab_*` vectors.
- `sz`, `flash_c`, `back_angle`, `turn_ang`, `limit_height`, `spin_blow_r`,
  `wall_dmg`, `wall_stop` — present in the core but unexamined.
- `b13_00` records 60 and 61 each carry a field whose **name is the empty
  string**, with the value 0. An authoring artefact, harmless, but a reader
  that indexes fields by name should expect it.
