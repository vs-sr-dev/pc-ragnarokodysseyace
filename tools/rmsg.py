"""
rmsg.py - reader for `TXT` message files, the game's text.

These carry every string the player reads: item and monster names, item
descriptions, quest text, the encyclopedia. They pair with the `ECH` tables -
`it_db_material.bin` has 411 rows and `it_db_name_material.rmsg` has 411
messages, in the same order - which is how a table row gets a name at all,
since the tables themselves hold no display text.

    0x00  'TXT' NUL
    0x04  u32   0x00010217, the format version
    0x08  u32   number of messages
    0x0C  u32   zero
    0x10        the messages
    ...         the string block, NUL-separated UTF-8

A message record is **variable length**:

    +0x00  u32   index, always the record's own position
    +0x04  u32   offset of the text, counted from 0x10
    +0x08  u32   a small number, 0, 1 or 2, and the same for every record of a
                 file - so a property of the message set rather than of the
                 message. Not identified.
    +0x0C  u32   number of attributes that follow
    then, per attribute:
    +0x00  u32   attribute id
    +0x04  u32   value type
    +0x08  u32   the value

So most records are 16 bytes and the ones carrying an attribute are 28. This
is the only thing about the format that has to be worked out rather than read,
and getting it wrong is quiet rather than loud: a fixed 16-byte stride reads
the first three hundred names correctly and then drifts, which looks like
corruption late in the file instead of a wrong assumption at the start of it.

The offsets are counted from 0x10, not from the start of the file - a small
thing, but it means the first message's offset also tells you where the string
block begins, which is what `check` uses to prove the walk landed right.

Usage:
  python rmsg.py check <dir>          walk every TXT file found and verify it
  python rmsg.py list <dir> <name>    the messages of one file
  python rmsg.py attrs <dir>          what attribute values actually occur
  python rmsg.py grep <dir> <text>    which files contain a string
"""
from __future__ import annotations

import pathlib
import struct
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

MAGIC = b'TXT' + bytes(1)
VERSION = 0x00010217
BASE = 0x10
NUL = bytes(1)


class Attr:
    __slots__ = ('id', 'kind', 'value')

    def __init__(self, ident, kind, value):
        self.id = ident
        self.kind = kind
        self.value = value

    def as_float(self) -> float:
        return struct.unpack('>f', struct.pack('>I', self.value))[0]

    def __repr__(self) -> str:
        return f'<attr {self.id}/{self.kind}={self.value:#x}>'


class Rmsg:
    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != MAGIC:
            raise ValueError(f'{label}: not a TXT ({buf[:4]!r})')
        self.label = label
        self.buf = buf
        self.version, self.count, spare = struct.unpack_from('>III', buf, 4)
        if spare:
            raise ValueError(f'{label}: word at 0x0C is {spare:#x}, not zero')

        self.kinds: set[int] = set()
        self.messages: list[tuple[int, str, list[Attr]]] = []
        o = BASE
        for i in range(self.count):
            idx, off, kind, n_attr = struct.unpack_from('>IIII', buf, o)
            if idx != i:
                raise ValueError(f'{label}: record {i} declares index {idx} - '
                                 f'the walk has drifted')
            self.kinds.add(kind)
            o += 16
            attrs = []
            for _ in range(n_attr):
                attrs.append(Attr(*struct.unpack_from('>III', buf, o)))
                o += 12
            self.messages.append((off, self._text(off), attrs))
        self.strings_at = o

    def _text(self, off: int) -> str:
        a = BASE + off
        if a >= len(self.buf):
            raise ValueError(f'{self.label}: text offset {off:#x} is past the '
                             f'end of the file')
        end = self.buf.index(NUL, a)
        return self.buf[a:end].decode('utf-8', 'replace')

    def check(self) -> None:
        """The records end exactly where the first string begins, and the last
        string ends on the last byte. Both hold only if every record length
        was read right, so this is the test that the variable stride is
        being handled."""
        if not self.messages:
            return
        first = BASE + min(m[0] for m in self.messages)
        if first != self.strings_at:
            raise ValueError(f'{self.label}: records end at '
                             f'{self.strings_at:#x} but the first string is '
                             f'at {first:#x}')
        if self.buf[-1] != 0:
            raise ValueError(f'{self.label}: the file does not end on a NUL')

    @property
    def texts(self) -> list[str]:
        return [m[1] for m in self.messages]


# --------------------------------------------------------------------------

def collect(root):
    root = pathlib.Path(root)
    for p in sorted(root.rglob('*')):
        if not p.is_file():
            continue
        blob = p.read_bytes()
        if blob[:4] == MAGIC:
            yield p.relative_to(root).as_posix(), blob


def _one(root, name):
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Rmsg(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    ok = bad = msgs = attrs = 0
    versions = Counter()
    kinds = Counter()
    errs: list[str] = []
    for path, blob in collect(root):
        try:
            r = Rmsg(blob, path)
            r.check()
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 10:
                errs.append(f'  {exc}')
            continue
        ok += 1
        msgs += r.count
        attrs += sum(len(m[2]) for m in r.messages)
        versions[r.version] += 1
        for k in r.kinds:
            kinds[k] += 1
    for m in errs:
        print(m)
    print(f'{ok} TXT files consistent, {bad} failed, {msgs:,} messages, '
          f'{attrs:,} attributes')
    print('  version: '
          + ', '.join(f'{k:#x} x{v}' for k, v in versions.most_common()))
    print('  word 2 : '
          + ', '.join(f'{k} in {v} files' for k, v in kinds.most_common()))
    return 0 if not bad else 1


def cmd_list(root, name) -> int:
    path, r = _one(root, name)
    print(f'{path}  {r.count} messages')
    for i, (off, text, attrs) in enumerate(r.messages):
        extra = ''
        if attrs:
            extra = '   ' + ' '.join(
                f'[{a.id}/{a.kind}={a.as_float():g}]' if a.kind == 3
                else f'[{a.id}/{a.kind}={a.value:#x}]' for a in attrs)
        print(f'  {i:>5}  {text}{extra}')
    return 0


def cmd_attrs(root) -> int:
    """What the optional attribute actually is. The tool does not know; this
    prints the evidence so a reader can decide."""
    combos = Counter()
    per_file = Counter()
    for path, blob in collect(root):
        try:
            r = Rmsg(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        n = 0
        for _, _, attrs in r.messages:
            for a in attrs:
                f = struct.unpack('>f', struct.pack('>I', a.value))[0]
                combos[(a.id, a.kind, a.value, round(f, 6))] += 1
                n += 1
        if n:
            per_file[path] = n
    print(f'{"id":>4} {"kind":>5} {"value":>12} {"as float":>12}   count')
    for (ident, kind, value, f), c in combos.most_common(30):
        print(f'{ident:>4} {kind:>5} {value:>#12x} {f:>12g}   {c}')
    print(f'{len(per_file)} files carry attributes')
    return 0


def cmd_grep(root, text) -> int:
    n = 0
    for path, blob in collect(root):
        try:
            r = Rmsg(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        hits = [t for t in r.texts if text in t]
        if hits:
            print(f'{path}  ({len(hits)})  ' + ' | '.join(hits[:3]))
            n += 1
    print(f'{n} files')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'list':
        return cmd_list(rest[0], rest[1])
    if cmd == 'attrs':
        return cmd_attrs(rest[0])
    if cmd == 'grep':
        return cmd_grep(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
