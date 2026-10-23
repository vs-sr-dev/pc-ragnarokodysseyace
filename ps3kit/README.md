# ps3kit

A game-agnostic toolkit for native PC ports of PS3 games: the executable's
structure, the Cell PPU, a static recompiler from PPU code to C++, and a
runtime that replaces the PS3's system software under the recompiled game.

The same idea as [wiikit](https://github.com/vs-sr-dev/wiikit) and
[ps2kit](https://github.com/vs-sr-dev/ps2kit),
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
| PC-ROA (this repository) | Ragnarok Odyssey ACE (2013) | everything so far: the descriptor table, the imports, the PPU recompiler, the process start, threads, files, the command buffer to its first flip, the audio ports and their clock, the window, the RSX's draws: the publishers' logos; save data; cellSail and an MPEG-2 decoder: the first movie; the controller: the title screen, the main menu and character creation; the SPU recompiler and a job manager: CRI's sound, heard |
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
python -m ps3kit.spu GAME.elf --at 0xF3D260 --base 0xF3D200   # read SPU code, local-store addresses
python -m ps3kit.spu GAME.elf --mix 0xF3D200:0xFE20           # an SPU program's census
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
method of frame N with its argument, `PS3KIT_DRAWDUMP=N` draw N's vertices,
constants and state, `PS3KIT_SHADERDUMP=1` every program pair as GLSL,
`PS3KIT_TEXDUMP=DIR` every texture as first decoded (PNG), and
`PS3KIT_GLDEBUG=1` the OpenGL driver's complaints, `PS3KIT_GLSYNC=N` each
draw from draw N on, waited for (so that a draw which brings the driver down
is the last one reported), `PS3KIT_SAVEDATA=1` each save
data step and callback result, `PS3KIT_SAIL=1` each movie player call and
event and every 30th frame shown.

`PS3KIT_SPU=1` reports each SPU program's first job and how long its jobs
take, `PS3KIT_SPU_DMA=1` every DMA transfer an SPU program makes (`=2` with
its words), `PS3KIT_SPU_TRACE=1` every indirect branch in SPU code, and
`PS3KIT_SPU_TRACE=2` every instruction, once the code has been generated with
`python -m ps3kit.recomp ... --spu-step`. `PS3KIT_AUDIODUMP=FILE.wav` writes
what the audio output plays.

`PS3KIT_PAD_PRESS="30:cross,46:start,52:cross+up"` presses the controller's
buttons for a fifth of a second at those times (seconds from the window's
first poll), so that a run nobody plays can still get past a screen.

`mpeg2test MOVIE OUT.yuv [--offset BYTES]` (`ninja mpeg2test`) runs the MPEG-2
decoder alone, on a program stream or an elementary stream, so that its
frames can be compared with another decoder's.

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

**SPU programs.** Each one is translated whole into a single function,
compiled for the local-store address it will be loaded at: every
instruction is a label, a direct branch is a goto, and an indirect one (a
return, a computed jump) goes through a switch over every instruction. SPU
code has no call distinct from a branch and returns through registers, so
this needs no discovery of functions at all. A register keeps its bytes in
host order reversed as a whole, which makes the 128-bit value the same
number as on the SPU: element-wise operations run on host vector lanes and
quadword shifts are shifts of an `unsigned __int128`. SPURS job binaries are
found by the header their job runtime (JOBCRT) carries; they are
position-independent and relocate themselves.

## Layers

| Layer | Question it answers | Now | Next |
|---|---|---|---|
| 1. Recognise | What is in this executable? | `elf`: segments, process parameters, TLS, the descriptor table, imports by name; SPURS job binaries by their job-runtime header | SPU ELFs, task sets, the middleware it links |
| 2. Read code | What does this function do? | `ppu`: the PPU decoder, disassembly, census; `spu`: the same for the SPU | cross-references through the TOC |
| 3. Recompile | The code as C++ | `recomp`: discovery, switch tables, the whole user-mode PPU set and the VMX operations games use; each SPU program whole, every SPU instruction but `bisled` and the double compares by magnitude | SPU ELFs and task sets |
| 4. Run | The PS3 under the game | `runtime`: memory map, dispatch, loader, imports, lv2 calls, the process start; PPU threads, lightweight and lv2 synchronisation, event queues; the file system (cellFs and sys_fs); cellGame; cellGcmSys and cellResc with a FIFO consumer, labels, flips and a 59.94 Hz vblank; the renderer (SDL3, OpenGL 4.5): a window, render targets on the host GPU, clears, draws with vertex and fragment programs translated to GLSL, textures, blending, flips; video out; cellAudio and the audio output, with the 48 kHz clock that consumes the ports and plays them through SDL3; SPURS job queues with a job manager running recompiled SPU programs: the SPU's channels, its DMA and atomic unit; save data (Auto, ListAuto, Fixed) with PARAM.SFO; cellSail playing PAMF through the runtime's own MPEG-2 decoder; cellPad from the host's gamepad and keyboard | the rest of the 3D engine's state (fog, clip planes, two-sided colour, point sprites), fonts, the list save dialogs, SPURS task sets and SPU thread groups |

## Known approximations

Declared here as they are made, so that the list is the cost:

- `fres`, `frsqrte` and the VMX estimates return exact values, not the
  hardware's estimates; FPSCR exception bits are not kept.
- The word divides write zero into the undefined high word.
- `lwarx`/`stwcx.` is a compare-and-swap against the value the reservation
  saw: a store of the same value in between goes unnoticed.
- Guest threads are host threads and the host schedules them. Guest
  priorities order nothing among themselves; a thread more urgent than the
  primary thread runs at the host's above-normal priority. Every
  synchronisation object shares one lock and one condition variable; waiters
  race rather than queue.
- `sys_timer_usleep` and the system's clocks sleep on a high-resolution
  waitable timer on Windows, and the process opts out of the power
  throttling that coarsens a background window's timers. With the ordinary
  sleep, CRI's 60 Hz server woke up to 12 ms late a few times a second and
  the audio it feeds fell a whole port behind.
- The RSX's 3D engine is the registers a draw reads so far: surfaces,
  clears, viewport, scissor, blending, colour masks, depth, stencil,
  culling, logic op, alpha test, vertex arrays, both programs, textures.
  Fog, user clip planes, two-sided colour, flat shading, point sprites,
  polygon offset and depth bounds are written and not acted on.
- Fragment programs keep their 16-bit H registers apart from the 32-bit R
  registers instead of aliasing two H onto one R, and compute everything at
  full precision; only the fixed-point and saturating clamps are applied.
- Not translated yet, and reported when met: a vertex program's branch
  through the address register (BRA) and its texture fetches, `CAL` in a
  fragment program, indexed fragment inputs, texture expansion (`_bx2`),
  unnormalised texture coordinates and packed (`CMP`) vertex attributes.
- A texture is copied and hashed whole on every draw that binds it, and the
  renderer keeps each distinct one until 512 MB have been sent; then it
  forgets them all. A render target the game samples is found on the GPU by
  its address, before guest memory is read.
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
- The audio system's clock consumes every started port's block each
  256/48000 s, clears it and moves the read index on, from the host's steady
  clock, and plays what it took: mixed down to stereo (centre and surrounds
  at -3 dB, the LFE dropped) and sent to an SDL3 stream, which drops a block
  when more than a fifth of a second is queued. The port buffers and read
  indices live in the runtime's heap, so their addresses are the runtime's
  own.
- The audio output is fixed like the video output: HDMI, two-channel linear
  PCM at 48 kHz. Configuring any other channel count is refused.
- A SPURS job queue's jobs run when they are pushed, on the pushing thread,
  in a local store of that thread's, so every job has completed when the
  push returns and a sync never waits. The manager is the runtime's own: the
  binary sits at local store 0x1000, its context and descriptor below it,
  its buffers above and the stack at the top. Of the context it fills the
  input buffer, the output buffer, scratch, the DMA tag (16, a choice; the
  job uses the next one too) and the descriptor's address; the word at
  +0x14, which the job runtime insists is a non-null local-store pointer and
  then clears, points at the descriptor's copy. Cache lists and in-out
  buffers are refused and reported. A job whose program was not recompiled
  completes having done nothing.
- The MFC completes each command as it is issued, so every tag group is
  always complete; list stall-and-notify is not honoured. GETLLAR and
  PUTLLC compare the whole 128-byte line under a lock shared by the SPUs
  only. The mailboxes are reported and never answered; the decrementer runs
  at 79.8 MHz from the host clock.
- SPU single precision is the host's IEEE arithmetic: no saturation in
  place of infinities, denormals kept. `frest`/`frsqest` are exact and `fi`
  passes its estimate through.
- `cellSysutilGetBgmPlaybackStatus` reports the system's music player
  stopped. Its PLAY state is 0, so a status left unwritten told the game the
  user's music was playing, and CRI held the game's own music at -100 dB.
- Save data: no dialog is drawn. A Fixed operation's confirmation is
  answered yes; a callback's error ends the call with
  `CELL_SAVEDATA_ERROR_CBRESULT` and no message. The List operations, whose
  list dialog is the user's, are not implemented. Files are stored as written:
  secure files are not encrypted and no `PARAM.PFD` is made; the runtime's
  `PS3KIT.LST` keeps the files' order and which are secure. `ACCOUNT_ID`,
  `PARAMS` and `PARAMS2` in a save's PARAM.SFO are zeros. The system's own
  files are reported as 35 KB, and the free space as `cellGameBootCheck`
  reports it.
- cellSail plays the first video stream of a PAMF file; audio streams,
  MP4 and AVI are not supported. The order of its events is a reading of
  what the one caller so far polls for (see `sail.cpp`); the state the
  player passes through at the end of a stream (straight to OPENED) is the
  runtime's. It allocates nothing through the game's allocator; it asks the
  graphics adapter for four frame buffers. Frames are shown on the host's
  clock from the first one decoded, never dropped.
- `cellSailGraphicsAdapterGetFrame2` returns the frame's size in bytes: its
  caller takes any result above 255 as a frame. `PtsToTimePosition` answers
  in microseconds from the first picture; the caller only tests it against
  zero, so the unit is unconfirmed.
- Movie frames are converted to ARGB with the stream's matrix (BT.709 here)
  from limited range, chroma interpolated linearly; how the system's
  converter filters is not known.
- The MPEG-2 decoder uses the floating-point reference IDCT. On the disc's
  movies it is within 3 levels of ffmpeg's (63 dB and above), which is the
  difference between two IDCTs. Field pictures and dual-prime prediction
  are reported and not decoded; nothing on this disc uses them.
- A texture whose format the renderer does not know, or whose linear rows
  are longer than their pitch, is reported with its registers and drawn
  with no image.
- One standard controller is connected to port 0, and no keyboard. Its
  state is the host's first SDL gamepad, by position (south is cross), and
  the keyboard mapped onto the same buttons (see `pad.cpp`); the keyboard
  map is the runtime's own, standing where a gamepad goes. Pressure values
  are 255 for a pressed button, the triggers' travel for L2 and R2; the
  motion sensors report a controller at rest; the motors do not turn.
- Vertex programs that branch are translated as the basic blocks their
  start reaches, in a loop over a program counter, at most 65,535 passes a
  vertex (a `switch` with a case
  per instruction brought the NVIDIA driver down). A branch tests its
  condition whether or not the instruction's test-enable bit is set; read
  the other way, every branch was taken and a skinning loop never ended.
- An import with no implementation returns `CELL_OK`; an lv2 call with none
  returns `CELL_ENOSYS`. Both are reported.
