"""Recompile a decrypted PS3 executable to C++.

    python -m ps3kit.recomp GAME.elf --out build/recomp [--per-file 20000] [--comments]

Writes, into --out:
    funcs.h          prototypes of every recompiled entry point
    recomp_NNN.cpp   the functions, split by instruction count
    table.cpp        the sorted address -> function table for indirect calls
    spu_NNN.cpp      each SPU program the executable carries, translated whole
    spu_table.cpp    those programs: image address, size, local-store base
    imports.cpp      every imported function: its library, name, NID and the
                     slot the loader fills (the runtime binds them by name)
    CMakeLists.txt   the library, the link check, and the runtime targets
    report.txt       units, entries, switch tables, anything not handled

The generated code is the game's own code, translated: it belongs in a build
directory, never in a repository. It needs ps3kit/runtime.
"""
import argparse
import os
import time

from ..elf import Image, load_names
from . import emit as E
from . import spu as S
from .program import Program

RUNTIME = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "runtime"))


class Out:
    """A generated file, written only if its content changed: a rebuild after
    a small change recompiles only what it touched."""

    def __init__(self, path):
        self.path, self.parts = path, []

    def write(self, s):
        self.parts.append(s)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        text = "".join(self.parts)
        try:
            with open(self.path, encoding="utf-8", newline="") as f:
                if f.read() == text:
                    return
        except OSError:
            pass
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


class FnCtx:
    """Control-flow answers for one entry's body."""

    def __init__(self, prog, entry, end, entries):
        self.prog, self.entry, self.end, self.entries = prog, entry, end, entries
        self.tables = prog.tables

    def tail(self, t):
        if t in self.entries:
            return f"PPU_TAIL({E.fname(t)});"
        return f'{{ ppu_unimplemented(c, 0x{t:08X}u, "branch to unknown target"); return; }}'

    def jump(self, t, src):
        if self.entry <= t < self.end:
            return f"goto L_{t:08X};"
        return self.tail(t)

    def call(self, t):
        if t in self.entries:
            return f"{E.fname(t)}(c);"
        return f'ppu_unimplemented(c, 0x{t:08X}u, "call to unknown target");'


def generate(img, out, per_file=20000, comments=False, log=print, spu_step=False):
    t0 = time.time()
    prog = Program(img, log=log)
    entries = set(prog.entries)
    os.makedirs(out, exist_ok=True)
    unsupported, files, n_ins = {}, [], 0
    buf, count, idx = [], 0, 0

    def flush():
        nonlocal buf, count, idx
        if not buf:
            return
        name = f"recomp_{idx:03d}.cpp"
        with Out(os.path.join(out, name)) as f:
            f.write('#include "funcs.h"\n\n')
            f.write("\n".join(buf))
        files.append(name)
        buf, count, idx = [], 0, idx + 1

    for e in prog.entries:
        u, end = prog.body(e)
        body = prog.ins(e, end)
        fn = FnCtx(prog, e, end, entries)
        labels = prog.labels(e, body)
        lines = [f"void {E.fname(e)}(PPUContext& c) {{"]
        for a, ins in body:
            if a in labels:
                lines.append(f"L_{a:08X}:")
            try:
                code = E.emit(ins, a, fn)
            except E.Unsupported as ex:
                unsupported[str(ex)] = unsupported.get(str(ex), 0) + 1
                code = [f'ppu_unimplemented(c, 0x{a:08X}u, "{ex}");']
            if comments:
                code[0] += f"  // {a:08X}"
            lines.append("    " + code[0])
            lines.extend("    " + x for x in code[1:])
        last = body[-1][1] if body else None
        if last is None or not E.terminates(last):
            lines.append("    " + fn.tail(end))
        lines.append("}\n")
        buf.append("\n".join(lines))
        count += len(body)
        n_ins += len(body)
        if count >= per_file:
            flush()
    flush()

    with Out(os.path.join(out, "funcs.h")) as f:
        f.write("#pragma once\n#include \"ppu.h\"\n\n")
        for e in prog.entries:
            f.write(f"void {E.fname(e)}(PPUContext& c);\n")
    with Out(os.path.join(out, "table.cpp")) as f:
        f.write('#include "funcs.h"\n#include <cstddef>\n\n')
        f.write("extern const PPUFuncEntry g_ppu_funcs[] = {\n")
        for e in prog.entries:
            f.write(f"    {{0x{e:08X}u, {E.fname(e)}}},\n")
        f.write("};\n")
        f.write(f"extern const size_t g_ppu_nfuncs = {len(prog.entries)};\n")

    spu_progs = S.find_jobs(img)
    spu_unsupported = {}
    for k, sp in enumerate(spu_progs):
        code, uns = S.translate(img, sp, comments, spu_step)
        for op, n in uns.items():
            spu_unsupported[op] = spu_unsupported.get(op, 0) + n
        name = f"spu_{k:03d}.cpp"
        with Out(os.path.join(out, name)) as f:
            f.write('#include "spu.h"\n\n')
            f.write(code)
        files.append(name)
    with Out(os.path.join(out, "spu_table.cpp")) as f:
        f.write('#include "spu.h"\n#include <cstddef>\n\n')
        for sp in spu_progs:
            f.write(f"uint32_t {sp.fname}(SPUContext& s, uint32_t pc);\n")
        f.write("extern const SPUProgram g_spu_programs[] = {\n")
        for sp in spu_progs:
            f.write(f'    {{0x{sp.ea:08X}u, 0x{sp.size:X}u, 0x{sp.base:X}u, {sp.fname}, "{sp.name}"}},\n')
        f.write("    {0, 0, 0, nullptr, nullptr}\n};\n")
        f.write(f"extern const size_t g_spu_nprograms = {len(spu_progs)};\n")

    names = load_names()
    imports = img.imports()
    n_imp = sum(len(m.nids) for m in imports)
    with Out(os.path.join(out, "imports.cpp")) as f:
        f.write('#include "ppu.h"\n#include <cstddef>\n\n'
                "// Every function the executable imports, in stub-table order: the\n"
                "// runtime fills each slot with a descriptor of its own and binds the\n"
                "// name to an HLE function, or to a logged stub.\n")
        f.write("extern const PPUImport g_ppu_imports[] = {\n")
        for m in imports:
            for n, slot in zip(m.nids, m.slots):
                name = names.get(n, f"nid_{n:08X}")
                f.write(f'    {{"{m.module}", "{name}", 0x{n:08X}u, 0x{slot:08X}u}},\n')
        f.write("    {nullptr, nullptr, 0, 0}\n};\n")
        f.write(f"extern const size_t g_ppu_nimports = {n_imp};\n")

    with Out(os.path.join(out, "CMakeLists.txt")) as f:
        rt = RUNTIME.replace("\\", "/")
        srcs = "\n    ".join(files + ["table.cpp", "imports.cpp", "spu_table.cpp"])
        f.write(f"""cmake_minimum_required(VERSION 3.20)
project(ps3kit_recomp CXX)
set(CMAKE_CXX_STANDARD 20)
set(PS3KIT_RUNTIME "{rt}")
add_library(recomp STATIC
    {srcs})
target_include_directories(recomp PUBLIC ${{PS3KIT_RUNTIME}})
target_compile_options(recomp PRIVATE -Wno-unused-label -Wno-unused-variable -fno-strict-aliasing)
include(${{PS3KIT_RUNTIME}}/runtime.cmake)
add_executable(linkcheck ${{PS3KIT_RUNTIME}}/linkcheck.cpp)
target_link_libraries(linkcheck ps3kit_core recomp)
# a port adds its own targets (tests, its game layer) with -DPS3KIT_EXTRA=file.cmake
if(DEFINED PS3KIT_EXTRA)
  include(${{PS3KIT_EXTRA}})
endif()
""")
    extra = [e for e in prog.entries if prog.unit_at(e).start != e]
    report = [
        f"code             {prog.lo:08X}-{prog.hi:08X}",
        f"units            {len(prog.units)} ({len(prog.opd_toc)} with a descriptor, "
        f"{sum(1 for u in prog.units if u.toc is None)} with no TOC known)",
        f"entries          {len(prog.entries)} ({len(extra)} inside units)",
        f"instructions     {n_ins}",
        f"switch tables    {len(prog.tables)} resolved, {len(prog.unresolved_tables)} unresolved",
        f"bad targets      {len(prog.bad_targets)}",
        f"imports          {len(imports)} libraries, {n_imp} functions",
        f"unsupported      {unsupported or 'none'}",
        f"spu programs     {len(spu_progs)}: " + ", ".join(f"{p.name} {p.ea:08X}+{p.size:X}" for p in spu_progs),
        f"spu unsupported  {spu_unsupported or 'none'}",
        f"files            {len(files)}",
        f"time             {time.time() - t0:.1f} s",
    ]
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
        for a in prog.unresolved_tables:
            f.write(f"unresolved switch table {a:08X}\n")
        for a, t in prog.bad_targets:
            f.write(f"bad target {a:08X} -> {t:08X}\n")
    log("\n".join(report))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-file", type=int, default=20000)
    ap.add_argument("--comments", action="store_true", help="the guest address on every line")
    ap.add_argument("--spu-step", action="store_true",
                    help="SPU programs report every instruction under PS3KIT_SPU_TRACE=2 (slow)")
    a = ap.parse_args()
    generate(Image(a.image), a.out, a.per_file, a.comments, spu_step=a.spu_step)


if __name__ == "__main__":
    main()
