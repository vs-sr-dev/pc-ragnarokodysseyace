# ps3kit

A game-agnostic toolkit for native PC ports of PS3 games: the executable's
structure, the Cell PPU, a static recompiler from PPU code to C++, and a
runtime that replaces the PS3's system software under the recompiled game.

The same idea as [wiikit](https://github.com/vs-sr-dev/wiikit) and
[ps2kit](https://github.com/vs-sr-dev/pc-extermination/tree/main/ps2kit),
for the PS3. Each PS3 game has its own engine and formats, but a large part
of every port is the *same* work: the same executable format, CPU, system
calls, libraries and GPU. ps3kit collects that shared part. It grows inside
the ports: each piece is written because a game needed it, then kept free
of that game's knowledge. Game formats and game fixes live in the ports.

It lives inside its first port for now, and moves to its own repository when
the second one starts.

## Ports built on it

| Port | Game | What it asked of ps3kit |
|---|---|---|
| PC-ROA (this repository) | Ragnarok Odyssey ACE (2013) | everything so far: the descriptor table, the imports, the PPU recompiler, the process start, threads, files, the command buffer to its first flip, the audio ports and their clock, the window and the first cleared frame |
| *next* | 3D Dot Game Heroes (2009) | the SPUs: 26 SPU programs on SPURS task sets and raw thread groups |

## Using it

ps3kit does not decrypt: the input is the decrypted executable (a 64-bit
big-endian ELF), produced from the player's own `EBOOT.BIN`. The generated
C++ is the game's own code translated, so it belongs in a build directory
and never in a repository.

```sh
python -m ps3kit.elf GAME.elf --imports --opd     # segments, parameters, imports by name
python -m ps3kit.ppu GAME.elf --at 0x10200        # read code
python -m ps3kit.ppu GAME.elf --mix               # the instruction census
python -m ps3kit.recomp GAME.elf --out build/recomp
cmake -S build/recomp -B build/recomp-build -G Ninja -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS_RELEASE=-O1
ninja -C build/recomp-build
build/recomp-build/ps3boot GAME.elf --bdvd DISC --hdd0 DIR   # DISC holds PS3_GAME
```

`ps3boot` opens a window and runs the game behind it; `--no-video` runs the
game alone, `--quit-after SECONDS` ends the run, and `--dump DIR` writes
every 60th shown frame as a PNG (`--dump-every N` for another interval).

Debugging a run: `ps3boot` reports a host fault with the guest address it
touched, and [`gdb_trace.py`](gdb_trace.py) traces any recompiled function
under gdb (arguments, result, the guest call chain) with no debug build:

```sh
PS3KIT_TRACE_FUNCS=81BEE8 PS3KIT_TRACE_CHAIN=1 gdb -q -batch -x ps3kit/gdb_trace.py \
    --args build/recomp-build/ps3boot GAME.elf --bdvd DISC
```

`PS3KIT_TRACE=1` reports every import call (by default each one's first
three), `PS3KIT_FS=1` every file opened, `PS3KIT_RSX_TRACE=N` every RSX
method of frame N with its argument, and `PS3KIT_GLDEBUG=1` the OpenGL
driver's complaints.

Building needs SDL3, CMake, Ninja and clang (the generated code's tail jumps are
`[[clang::musttail]]`; clang 22 from MSYS2 is what is used here). The Python
side has no dependencies.

## How it works

**Functions.** A PS3 executable is stripped, but every function whose
address is ever taken has an 8-byte descriptor, `{entry, toc}`, in one table
that `e_entry` points into. Those entries, plus every `bl` target, are the
units; the code ends where the last unit reachable that way ends (the import
stubs). A branch out of a unit's body to a place that is not a unit start
makes an extra entry, as wiikit does.

**Code.** Each entry becomes `void f_XXXXXXXX(PPUContext&)`. Registers live
in the context; memory is a 4 GiB host reservation indexed by guest address,
big-endian. A branch to another function is a guaranteed tail call, so a
guest loop that crosses a function boundary does not grow the host stack.
Switch tables (`lwz` of the table from the TOC, `lwzx`, `extsw`, `add`,
`bctr`) become C++ `switch`es; every other indirect branch goes through a
sorted address table.

**Imports.** The loader's job, done the loader's way: each slot of the stub
table gets a descriptor whose entry is an address in the runtime's range.
A call through it is dispatched to the C++ function registered under the
import's name (`PS3_HLE(name)`), or to a stub that reports it. Names come
from [`nids.txt`](nids.txt); a NID is computed from its name, never stored.

**System calls.** `sc` dispatches on r11 to `LV2_SYSCALL(number, name)`.

## Layers

| Layer | Question it answers | Now | Next |
|---|---|---|---|
| 1. Recognise | What is in this executable? | `elf`: segments, process parameters, TLS, the descriptor table, imports by name | the SPU programs embedded in it, the middleware it links |
| 2. Read code | What does this function do? | `ppu`: the PPU decoder, disassembly, census | cross-references through the TOC |
| 3. Recompile | The PPU code as C++ | `recomp`: discovery, switch tables, the whole user-mode PPU set and the VMX operations games use | SPU code |
| 4. Run | The PS3 under the game | `runtime`: memory map, dispatch, loader, imports, lv2 calls, the process start; PPU threads, lightweight and lv2 synchronisation, event queues; the file system (cellFs and sys_fs); cellGame; cellGcmSys and cellResc with a FIFO consumer, labels, flips and a 59.94 Hz vblank; the renderer (SDL3, OpenGL 4.5): a window, render targets on the host GPU, clears, flips; video out; cellAudio and the audio output, with the 48 kHz clock that consumes the ports; SPURS job queue ports | drawing (vertex arrays, the vertex and fragment programs, textures, blending), sound out (the SPU jobs that make it), input, cellSail, SPURS |

## Known approximations

Declared here as they are made, so that the list is the cost:

- `fres`, `frsqrte` and the VMX estimates return exact values, not the
  hardware's estimates; FPSCR exception bits are not kept.
- The word divides write zero into the undefined high word.
- `lwarx`/`stwcx.` is a compare-and-swap against the value the reservation
  saw: a store of the same value in between goes unnoticed.
- Guest threads are host threads and the host schedules them: guest
  priorities are kept, not honoured. Every synchronisation object shares one
  lock and one condition variable; waiters race rather than queue.
- The RSX draws nothing yet. It clears: the render targets the surface
  registers name are kept on the host GPU, and `CLEAR_SURFACE` clears them
  inside the scissor with the colour mask applied. Every other method is
  counted and skipped.
- A render target found again at the same address with another size or
  format is made anew, and what it held is lost.
- A display buffer no render target was drawn to is read from guest memory
  when the renderer shows it, which may be up to two flips after the game
  flipped it.
- Resc's conversion shows the source buffer itself, which is only right
  while the source and the display are the same size (1280x720 here).
- `cellRescGetBufferSize`'s colour-buffer size is a reading: the largest
  supported, registered destination times its buffer count. Its vertex-array
  and fragment-shader sizes are the runtime's own.
- The video output is fixed: one HDMI display, 1280x720, 59.94 Hz. System
  callbacks are registered and never raised.
- The audio system plays nothing: its clock consumes every started port's
  block each 256/48000 s, clears it and moves the read index on, from the
  host's steady clock. The port buffers and read indices live in the
  runtime's heap, so their addresses are the runtime's own.
- The audio output is fixed like the video output: HDMI, two-channel linear
  PCM at 48 kHz. Configuring any other channel count is refused.
- A SPURS job queue runs no job. A pushed job is complete at once and its
  outputs stay as they were; each distinct SPU program is reported when it
  is first pushed.
- An import with no implementation returns `CELL_OK`; an lv2 call with none
  returns `CELL_ENOSYS`. Both are reported.
