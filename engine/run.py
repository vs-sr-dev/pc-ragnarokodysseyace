"""
run.py - drive the capsule, and report what the game's numbers produce.

The milestone this serves is the first one in
[`STRATEGY.md`](../docs/STRATEGY.md): **"the numbers are real"**. Thirteen
sessions produced a complete reading of the disc and never once ran any of it.
Every check in this repository is arithmetic - the files consume exactly, the
sentinels return, the indices resolve - and none of them is the same thing as
a body moving at `acc = 0.035` and arriving somewhere.

    python engine/run.py numbers extract/tree/job.cpk/sw/sw.json
    python engine/run.py walk extract/tree/stage.cpk/010_01_01/param.pac \\
                              extract/tree/job.cpk/sw/sw.json
    python engine/run.py trace <stage dir> <class json> out.png

    python engine/run.py stride <stage dir> <class json> extract/tree \\
                               msw213run [gait] [start] [cycles]

    python engine/run.py check extract/tree/stage.cpk
    python engine/run.py sweep extract/tree/stage.cpk <class json>

`numbers` needs no stage: it turns the parameter table into quantities a
person can have an opinion about - seconds, metres, multiples of Earth
gravity. `walk` runs the loop on a real stage and reports whether the body
stayed on the ground the whole way. `trace` draws it. `stride` gives the body
a skeleton - see [`pose.py`](pose.py) - and prints where its planted foot is
against the mesh under it, which is the first thing here that has a shape and
not just a position. `check` asks the two questions across all 155 stages that
only a simulation thinks to ask - is the marker table consistent with the
collision mesh, and does the fence close.
"""
from __future__ import annotations

import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from actor import FPS, Actor, bearing, load                   # noqa: E402
from world import World                                       # noqa: E402

# A `jump_*` exit is a box up to 10 m wide, so a spawn inside a small room can
# be "at" the exit on frame one. Only crossings longer than this are counted
# as crossings.
LONG = 20.0


def cmd_numbers(json_path) -> int:
    p = load(json_path)
    name = pathlib.Path(json_path).stem
    acc, run, walk = p['acc'], p['run_sp'], p['walk_sp']
    fast, facc = p['fast_sp'], p['fast_acc']
    g, jp = p['fall_gravity_y'], p['jp_speed_y']
    ra, rs = p['rot_y_acc'], p['rot_y_spd']

    print(f'{name} record 0, at {FPS:.0f} frames a second, one unit a metre')
    print()
    print('  speed')
    for label, sp, a in (('walk', walk, acc), ('run', run, acc),
                         ('dash', fast, facc)):
        frames = sp / a
        print(f'    {label:<5} {sp:>6.3f} m/frame = {sp * FPS:>5.2f} m/s, '
              f'reached in {frames:>5.2f} frames '
              f'({frames / FPS:.2f} s) over {0.5 * sp * frames:.2f} m')
    print()
    print('  turning')
    peak = ra * math.sqrt(180.0 / ra)          # if it never reaches the cap
    if peak <= rs:
        half = 2.0 * math.sqrt(180.0 / ra)
    else:
        spin = rs / ra                          # frames spent accelerating
        covered = rs * spin                     # degrees to spin up and down
        half = 2.0 * spin + (180.0 - covered) / rs
    print(f'    rot_y_acc {ra} deg/frame^2, capped at rot_y_spd {rs} '
          f'deg/frame')
    print(f'    a 180 degree turn takes {half:.2f} frames '
          f'= {half / FPS:.2f} s')
    print()
    print('  the jump')
    apex = jp * jp / (2.0 * -g)
    up = jp / -g
    print(f'    jp_speed_y {jp} m/frame, fall_gravity_y {g} m/frame^2')
    print(f'    apex {apex:.2f} m after {up:.1f} frames, '
          f'airtime {2 * up / FPS:.2f} s')
    print(f'    gravity is {-g * FPS * FPS:.1f} m/s^2, '
          f'{-g * FPS * FPS / 9.81:.1f} times Earth')
    print()
    print('  the body')
    print(f'    col_r {p["col_r"]} m, weight {p["weight"]}')
    return 0


def _plan(world, start_name, goal_name):
    a = world.marker(start_name)
    b = world.marker(goal_name)
    return a, b


def cmd_walk(stage_dir, json_path, start='appear01', goal='', gait='run',
             limit=3000) -> int:
    w = World(stage_dir)
    p = load(json_path)
    if not goal:
        jumps = [m for m in w.stage.markers if m.kind.startswith('jump_')]
        if not jumps:
            raise SystemExit(f'{w.name}: no jump marker, name a goal')
        goal = jumps[0].name
    a, b = _plan(w, start, goal)

    face = a.rotation[1]
    want = bearing(a.position[0], a.position[2], b.position[0], b.position[2])
    off = abs(((want - face + 180.0) % 360.0) - 180.0)

    print(f'{w.name}: {w.ccls.count} collision triangles, '
          f'{len(w.stage.markers)} markers, '
          f'{sum(len(f.points) for f in w.fences())} fence points')
    print(f'  start {start:<16} {a.position[0]:8.3f} {a.position[1]:7.3f} '
          f'{a.position[2]:9.3f}   marker faces {face:6.2f} deg')
    print(f'  goal  {goal:<16} {b.position[0]:8.3f} {b.position[1]:7.3f} '
          f'{b.position[2]:9.3f}   bearing to it {want:6.2f} deg')
    print(f'  the marker faces its exit to within {off:.2f} degrees '
          + ('- so heading 0 is +Z' if off < 90 else
             '- which the +Z convention does NOT explain'))

    floor = w.floor(a.position[0], a.position[2])
    print(f'  the ground under the spawn is at y = '
          + ('none - the spawn is off the mesh' if floor is None
             else f'{floor:.3f}, the marker says {a.position[1]:.3f}'))

    act = Actor(p, a.position[0], a.position[1], a.position[2], face)
    reach = max(3.0, max(b.extents[0], b.extents[2]))
    log, off_mesh, fence = [], 0, None
    for _ in range(limit):
        head = bearing(act.x, act.z, b.position[0], b.position[2])
        r = act.step(w, gait=gait, facing=head)
        log.append(r)
        if r['event'].startswith('off'):
            off_mesh += 1
        if r['event'].startswith('fence') and fence is None:
            fence = r
        if math.hypot(act.x - b.position[0], act.z - b.position[2]) <= reach:
            break

    d = math.hypot(a.position[0] - b.position[0],
                   a.position[2] - b.position[2])
    travelled = sum(r['speed'] for r in log)
    n = len(log)
    print()
    print(f'  {n} frames = {n / FPS:.2f} s at {gait}, '
          f'{travelled:.2f} m travelled over {d:.2f} m of straight line')
    print(f'  top speed {max(r["speed"] for r in log):.3f} m/frame '
          f'= {max(r["speed"] for r in log) * FPS:.2f} m/s')
    print(f'  frames with no ground underneath: {off_mesh} of {n}')
    touched = sum(1 for r in log if r['event'].startswith('fence'))
    if fence:
        print(f'  first touched the {fence["event"]} at frame '
              f'{fence["frame"]}, ({fence["x"]:.2f}, {fence["z"]:.2f}); '
              f'{touched} of {n} frames in contact')
    ys = [r['y'] for r in log]
    jump = max((abs(b - a) for a, b in zip(ys, ys[1:])), default=0.0)
    print(f'  the ground ran from y = {min(ys):.3f} to {max(ys):.3f}, '
          f'never stepping more than {jump:.3f} m in one frame')
    arrived = math.hypot(act.x - b.position[0], act.z - b.position[2]) <= reach
    print(f'  arrived: {"yes" if arrived else "no"}')
    return 0


def cmd_trace(stage_dir, json_path, out, start='appear01', goal='',
              gait='run', limit=3000) -> int:
    import matplotlib                                         # noqa: PLC0415
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt                           # noqa: PLC0415
    from matplotlib.collections import LineCollection         # noqa: PLC0415

    w = World(stage_dir)
    p = load(json_path)
    if not goal:
        goal = next(m.name for m in w.stage.markers
                    if m.kind.startswith('jump_'))
    a, b = _plan(w, start, goal)

    act = Actor(p, a.position[0], a.position[1], a.position[2], a.rotation[1])
    reach = max(3.0, max(b.extents[0], b.extents[2]))
    path = [(act.x, act.z)]
    for _ in range(limit):
        head = bearing(act.x, act.z, b.position[0], b.position[2])
        act.step(w, gait=gait, facing=head)
        path.append((act.x, act.z))
        if math.hypot(act.x - b.position[0], act.z - b.position[2]) <= reach:
            break

    fig, ax = plt.subplots(figsize=(9, 11), dpi=140)
    segs = []
    for t in w.tris:
        v = [(q[0], q[2]) for q in t['v']]
        segs += [(v[0], v[1]), (v[1], v[2]), (v[2], v[0])]
    ax.add_collection(LineCollection(segs, linewidths=0.35,
                                     colors='#c8ccd4', zorder=1))
    for ln in w.fences():
        pts = [(q[0], q[2]) for q in ln.world()]
        ax.plot([q[0] for q in pts], [q[1] for q in pts], '-',
                color='#d0574b', linewidth=1.4, zorder=3)
    for m in w.stage.markers:
        if m.kind in ('emgen_pos', 'appear') or m.kind.startswith('jump_'):
            ax.plot(m.position[0], m.position[2], '.', markersize=4,
                    color='#7a8290', zorder=4)
    ax.plot([q[0] for q in path], [q[1] for q in path], '-',
            color='#1f6feb', linewidth=2.0, zorder=5)
    ax.plot(path[0][0], path[0][1], 'o', color='#1a7f37', markersize=7,
            zorder=6)
    ax.plot(path[-1][0], path[-1][1], 'o', color='#8250df', markersize=7,
            zorder=6)
    ax.set_aspect('equal')
    ax.set_xlabel('x, metres')
    ax.set_ylabel('z, metres')
    ax.set_title(f'{w.name} - {len(path) - 1} frames '
                 f'({(len(path) - 1) / FPS:.1f} s) at {gait}, '
                 f'{pathlib.Path(json_path).stem} parameters')
    ax.grid(True, linewidth=0.3, alpha=0.4)
    fig.tight_layout()
    fig.savefig(out)
    print(f'{out}  ({len(path) - 1} frames)')
    return 0


def cmd_stride(stage_dir, json_path, tree, motion, gait='run',
               start='appear01', cycles='2') -> int:
    """Play one animation on the walking capsule, and watch the foot.

    This is the whole point of the pose layer stated as one number. The
    animation slides its planted foot backwards at whatever rate it was
    authored for; the actor carries the body forwards at whatever `walk_sp` or
    `run_sp` says. If the two agree the foot stands still on the ground while
    it is down, and if they do not it skates - which is the same test an
    animator does by eye, done in arithmetic.

    The height above the mesh is the other half: the foot is placed from the
    skeleton and the ground is read from the collision mesh under it, and
    nothing has arranged for the two to meet.
    """
    from pose import TOUCH, load as load_pose                 # noqa: PLC0415

    w = World(stage_dir)
    p = load(json_path)
    body, play, path = load_pose(tree, motion)
    a = w.marker(start)
    act = Actor(p, a.position[0], a.position[1], a.position[2],
                a.rotation[1])
    frames = max(1, int(cycles)) * play.length
    speed = p[{'walk': 'walk_sp', 'run': 'run_sp',
               'fast': 'fast_sp'}.get(gait, 'run_sp')]

    print(f'{w.name}, {pathlib.Path(json_path).stem} parameters, '
          f'{path.stem} on {body.path.stem}')
    print(f'  {play.declared} frames declared, {play.length} in the loop; '
          f'the cycle slides {play.slide():.4f} m a frame and {gait} is '
          f'{speed} m/frame')
    print()
    print('  frame        x         z   speed   the lower foot       '
          'above the mesh    slips')
    was = None
    heights, slips = [], []
    for f in range(1, frames + 1):
        r = act.step(w, gait=gait)
        at = play.at(float((f - 1) % play.length))
        rad = math.radians(act.heading)
        sin, cos = math.sin(rad), math.cos(rad)
        world = {}
        for n, (mx, my, mz) in at.items():
            world[n] = (act.x + mx * cos + mz * sin, act.y + my,
                        act.z - mx * sin + mz * cos)
        low = min(world, key=lambda n: world[n][1])
        fx, fy, fz = world[low]
        ground = w.floor(fx, fz, fy + act.radius)
        # A foot at its standing height while the body itself is falling is
        # not planted on anything, so the actor has to be on the ground too.
        down = at[low][1] - body.standing[low] <= TOUCH and act.grounded
        slip = None
        if was is not None and was[0] == low and down and was[3]:
            slip = math.hypot(fx - was[1], fz - was[2])
            slips.append(slip)
        was = (low, fx, fz, down)
        # what the ground has to meet is the sole, not the ankle joint, so
        # the height the node stands at comes off it first.
        over = None if ground is None else fy - body.standing[low] - ground
        if over is not None and down:
            heights.append(over)
        if down:
            state = ''
        else:
            state = '   falling' if not act.grounded else '   in the air'
        print(f'  {f:5d} {act.x:9.3f} {act.z:9.3f} {r["speed"]:7.3f}   '
              f'{low:<16} {"-" if over is None else f"{over:+8.3f}"}   '
              f'{"" if slip is None else f"{slip:8.4f}"}{state}')
    print()
    if not heights:
        print(f'  never planted in {frames} frames - the body spent them '
              f'off the ground, so there was nothing to stand on')
    if heights:
        heights.sort()
        print(f'  planted on {len(heights)} of {frames} frames, and while it '
              f'is planted the foot sits')
        print(f'    {statistics.median(heights):+.4f} m above the collision '
              f'mesh, {heights[0]:+.4f} to {heights[-1]:+.4f}')
    if slips:
        slips.sort()
        print(f'    and slides {statistics.median(slips):.4f} m a frame over '
              f'the ground - the cycle is authored for')
        print(f'    {play.slide():.4f} and the body is moving at {speed}, so '
              f'{abs(play.slide() - speed):.4f} of that is the disagreement')
    return 0

def cmd_check(stage_root) -> int:
    """Two questions that only a running simulation can ask.

    Both join files nobody had reason to compare while they were only being
    read: the marker table against the collision mesh, and the fence against
    itself."""
    import collections                                        # noqa: PLC0415
    from world import _height_at                              # noqa: PLC0415

    root = pathlib.Path(stage_root)
    dirs = sorted(p for p in root.iterdir() if (p / 'param.pac').is_dir())
    by_kind = collections.defaultdict(list)
    missing = collections.Counter()
    stages = closed = fenced = 0
    branch = 0

    def nearest(w, x, z, y):
        """The ground nearest a marker's own height, not the highest ground.

        A stage mesh has more than one storey in places, so "the highest
        triangle under this point" answers the wrong question when asking
        whether a marker was placed on the floor."""
        best = None
        for t in w._walkable:                                 # noqa: SLF001
            h = _height_at(t['v'], x, z)
            if h is not None and (best is None or abs(h - y) < abs(best - y)):
                best = h
        return best

    for d in dirs:
        try:
            w = World(d / 'param.pac')
        except (Exception, SystemExit):                       # noqa: BLE001
            continue
        stages += 1
        for m in w.stage.markers:
            k = m.kind
            if k.startswith('appear'):
                k = 'appear'
            elif k.startswith('jump_'):
                k = 'jump'
            elif k not in ('emgen_pos', 'obj', 'pl_q'):
                continue
            y = nearest(w, m.position[0], m.position[2], m.position[1])
            if y is None:
                missing[k] += 1
            else:
                by_kind[k].append(abs(y - m.position[1]))

        lines = w.fences()
        if not lines:
            continue
        fenced += 1
        ends = collections.Counter()
        for ln in lines:
            pts = [(q[0], q[2]) for q in ln.world()]
            for e in (pts[0], pts[-1]):
                ends[(round(e[0], 2), round(e[1], 2))] += 1
        if all(v == 2 for v in ends.values()):
            closed += 1
        elif any(v > 2 for v in ends.values()):
            branch += 1

    print(f'{stages} stages with a collision mesh')
    print()
    print('  markers standing on the mesh - hta.bin against <stage>.col')
    print('    kind          n   none   median    <1cm   <10cm      max')
    for k in ('obj', 'appear', 'jump', 'pl_q', 'emgen_pos'):
        a = sorted(by_kind.get(k, []))
        if not a:
            continue
        print(f'    {k:<10} {len(a):>4} {missing[k]:>6} '
              f'{a[len(a) // 2]:>8.3f} '
              f'{sum(1 for v in a if v <= 0.01):>7} '
              f'{sum(1 for v in a if v <= 0.10):>7} '
              f'{a[-1]:>8.2f}')
    print('    (metres between the marker and the nearest ground under it)')
    print()
    print('  the fence closes - every chara_line endpoint shared by two ends')
    print(f'    {closed} of {fenced} stages close, {branch} branch, '
          f'{fenced - closed - branch} leave an end loose')
    return 0


def cmd_sweep(stage_root, json_path, gait='run', limit=4000) -> int:
    """Cross every stage that has a spawn and an exit, and count.

    One stage crossing proves the loop runs. Every stage crossing is the
    claim worth making: that the parameters, the mesh and the fence are
    consistent with each other across the whole disc and not just where they
    were first looked at."""
    root = pathlib.Path(stage_root)
    p = load(json_path)
    done = arrived = clean = skipped = 0
    times, worst, steps = [], [], []
    for d in sorted(x for x in root.iterdir() if (x / 'param.pac').is_dir()):
        try:
            w = World(d / 'param.pac')
        except (Exception, SystemExit):                       # noqa: BLE001
            skipped += 1
            continue
        names = w.stage.atih.by_name() if w.stage.atih else {}
        start = next((n for n in ('appear01', 'appear') if n in names), None)
        exits = [m for m in w.stage.markers if m.kind.startswith('jump_')]
        if start is None or not exits or not w.fences():
            skipped += 1
            continue
        a, b = names[start], exits[0]
        act = Actor(p, a.position[0], a.position[1], a.position[2],
                    a.rotation[1])
        reach = max(3.0, max(b.extents[0], b.extents[2]))
        off, went, rise, was = 0, 0.0, 0.0, act.y
        for _ in range(limit):
            head = bearing(act.x, act.z, b.position[0], b.position[2])
            r = act.step(w, gait=gait, facing=head)
            off += r['event'].startswith('off')
            went += r['speed']
            rise = max(rise, abs(r['y'] - was))
            was = r['y']
            if math.hypot(act.x - b.position[0],
                          act.z - b.position[2]) <= reach:
                break
        done += 1
        got = math.hypot(act.x - b.position[0],
                         act.z - b.position[2]) <= reach
        arrived += got
        clean += off == 0
        span = math.hypot(a.position[0] - b.position[0],
                          a.position[2] - b.position[2])
        if got and span >= LONG:
            times.append((act.frame / FPS, max(span - reach, 1.0), went,
                          d.name))
        steps.append((rise, d.name))
        if off:
            worst.append((off, d.name))
    times.sort()
    print(f'{done} stages walked, {skipped} skipped for want of a spawn, '
          f'an exit or a fence')
    print(f'  never left the collision mesh: {clean} of {done}')
    print(f'  reached the exit steering straight at it: {arrived} of {done}')
    if times:
        t = [x[0] for x in times]
        print(f'  of those, {len(times)} are a real crossing '
              f'(spawn at least {LONG:.0f} m from the exit):')
        print(f'    time     median {t[len(t) // 2]:>5.1f} s, '
              f'{t[0]:.1f} s to {t[-1]:.1f} s')
        v = sorted(x[2] / x[0] for x in times)
        top = p['run_sp'] * FPS
        print(f'    speed    median {v[len(v) // 2]:>5.2f} m/s over the '
              f'ground, against {top:.2f} m/s flat out')
        det = sorted(x[2] / x[1] for x in times)
        print(f'    detour   median {det[len(det) // 2]:>5.2f} times the '
              f'straight line, which is what the corridors cost')
        print(f'    longest  {times[-1][3]} at {times[-1][0]:.1f} s '
              f'over {times[-1][1]:.0f} m')
    steps.sort(reverse=True)
    if steps:
        cap = p['fall_spd_max']
        print(f'  largest vertical move in one frame, anywhere: '
              f'{steps[0][0]:.3f} m on {steps[0][1]}'
              + (f' - which is fall_spd_max ({cap}) exactly, so the clamp '
                 f'fires' if abs(steps[0][0] - cap) < 1e-6 else ''))
    worst.sort(reverse=True)
    if worst:
        print(f'  {len(worst)} stages have frames with no ground underneath - '
              f'a straight line at the exit crosses a hole in the mesh:')
    for n, name in worst[:6]:
        print(f'    {name}: {n} frames of {limit} at most')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'numbers':
        return cmd_numbers(rest[0])
    if cmd == 'walk':
        return cmd_walk(rest[0], rest[1], *rest[2:])
    if cmd == 'trace':
        return cmd_trace(rest[0], rest[1], rest[2], *rest[3:])
    if cmd == 'stride':
        return cmd_stride(rest[0], rest[1], rest[2], rest[3],
                          *rest[4:])
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'sweep':
        return cmd_sweep(rest[0], rest[1], *rest[2:])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
