# `.anmcmd` — the animation command lists

**Status: container solved, opcodes open.** 2,053 files, **6,802 blocks, 10,175
commands, 0 unreadable**, and every arithmetic check closing on every file.
Reader: [`../tools/anmcmd.py`](../tools/anmcmd.py).

This is what turns an animation into an event. A [`CNOM`](format_cnom.md) moves
the bones; one of these says what happens on which frame of it — and the things
it would arm, the `collision_*.CTXT` capsules bound to bones through a model's
locator table, are described in [`format_cmdl.md`](format_cmdl.md).

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

## The opcodes

52 of them, and **51 have one fixed size wherever they appear**, from 4 bytes —
an opcode with no payload at all — up to 120.

The exception is opcode 0, the commonest at 2,508 uses, whose size is always
`12 + 116 * n`: twelve bytes of head and then one to sixteen records of 116.
Whatever it is, it is a list, and it is the thing an animation most often has
to say.

The numbering runs 0 to 62, and then jumps to 1000, 1002, 1004 and 10000. Those
four read like locator ids — `1000` and `10000` *are* locator ids, on 251 and
247 models — but 1002 and 1004 are locator ids on no model on the disc, so they
are opcodes in a high range and not addresses. Checking cost a minute and would
have been a plausible wrong answer.

What the opcodes mean is open. `anmcmd.py census` prints all 52 with their
sizes and the containers they occur in, which is where naming them starts.

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
frames, not seconds or ticks.

## Still open

- All 52 opcodes. The place to start is opcode 0 — the commonest, the only
  variable-length one, and a list of fixed records, which is the shape of a
  hitbox set.
- Why 554 files name no motion. Some are plainly not animations at all
  (`stick_bullet`, `soul_breaker_bullet`); the rest may key through the 2,690
  `.mkc` files, which sit beside the `CNOM` in the same `.pac`.
- The frame rate, which these lists are now in a position to settle: they carry
  event frames for moves whose durations the [actor
  parameters](params.md) also describe.
