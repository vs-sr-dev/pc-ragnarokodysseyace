"""
actor.py - the movement model, driven entirely by the game's own numbers.

Not one constant in this file is invented. Every value comes out of the class
JSON that [`params.md`](../docs/params.md) reads, and the two unit constants
come from [`units.md`](../docs/units.md):

    acc               0.035    metres per frame squared
    run_sp            0.17     metres per frame
    ry_r_walk/run/fast/fall  0.15 / 0.30 / 0.35 / 0.35   metres
    walk_sp           0.05
    fast_sp / fast_acc  0.28 / 0.045
    rot_y_acc         8        degrees per frame squared
    rot_y_spd         32       degrees per frame
    fall_gravity_y   -0.035    metres per frame squared
    fall_spd_max      8
    jp_speed_y        0.42     metres per frame
    col_r             0.5      metres

    one frame        1/30 s
    one unit         1 metre

**All six classes share every one of those**, which is why the model is one
model and not six; `params.md` counted 173 of 225 fields byte-identical across
the six and locomotion is entirely inside that 173.

## What the disc does not say, and what is assumed instead

Three things, all of them stated here so they can be argued with:

- **Deceleration.** There is no ground brake field. `brake` exists only for
  attacks (`atk_brake`), evades (`es_brake1..3`), knockback and landing, so
  ordinary running has none of its own. The model therefore decelerates at
  `acc`, the same rate it accelerates - the assumption that costs the fewest
  new numbers.
- **Turning.** `rot_y_acc` and `rot_y_spd` are an acceleration and a cap, so
  the turn is integrated and braked to stop on the target heading rather than
  snapped. Nothing on the disc describes the braking, so it is the textbook
  one: decelerate when the remaining angle is less than `w^2 / (2 * a)`.
- **The stick.** A real pad gives a magnitude; the model takes 0, `walk`,
  `run` or `fast` as four discrete targets, which is enough to test the
  numbers and avoids inventing a curve the disc does not have.
- **Walls.** A blocked step slides along the fence instead of stopping. The
  disc says where the fence is and nothing about what happens at it, so this
  is the engine's choice, marked as such.
- **The ground under a body.** The ground is asked for under a *disc* and
  not under the centre point - `world.under` rather than `world.floor`. A
  body that has gone a hand's breadth past the lip of a slab is still
  standing on it, and the disc's own stairs have gaps of a fifth of a metre
  between their steps that a body moving 0.17 m in a frame would otherwise
  fall into. **The radius of that disc is not invented either**: the class
  JSON carries `ry_r_walk` 0.15, `ry_r_run` 0.30, `ry_r_fast` 0.35 and
  `ry_r_fall` 0.35 - four radii keyed to exactly the four locomotion states
  this model has, carried by all six classes, by no monster, and read by
  nothing until now. What the name abbreviates is not on the disc; that a
  per-gait radius growing with speed is the ground probe is the reading, and
  it is the only per-gait length the player's table has.

Everything else - the values, the units, the frame - is read, not chosen.
"""
from __future__ import annotations

import json
import math
import pathlib

FPS = 30.0                     # units.md, from the run cycle and from gravity

WANT = ('acc', 'run_sp', 'walk_sp', 'fast_sp', 'fast_acc',
        'rot_y_acc', 'rot_y_spd', 'weight', 'col_r',
        'fall_gravity_y', 'fall_spd_max', 'jp_speed_y',
        'aerial_gravity_y', 'aerial_spd_y',
        'ry_r_walk', 'ry_r_run', 'ry_r_fast', 'ry_r_fall')


def load(json_path, record: str = '0') -> dict:
    """One class's record, merged over the base as `params.py` merges it."""
    raw = json.loads(pathlib.Path(json_path).read_text(encoding='utf-8'))
    out = dict(raw['0'])
    if record != '0':
        out.update(raw[record])
    return out


class Actor:
    """A capsule that moves the way the parameter table says it should."""

    def __init__(self, params: dict, x=0.0, y=0.0, z=0.0, heading=0.0):
        self.p = params
        self.x, self.y, self.z = x, y, z
        self.heading = heading         # degrees, 0 faces +Z
        self.speed = 0.0               # metres per frame, along the heading
        self.turn_rate = 0.0           # degrees per frame
        self.vy = 0.0
        self.grounded = True
        self.frame = 0

    # -- the parameters, named ---------------------------------------------

    @property
    def radius(self) -> float:
        return self.p['col_r']

    def target_speed(self, gait: str) -> float:
        return {'stop': 0.0, 'walk': self.p['walk_sp'],
                'run': self.p['run_sp'], 'fast': self.p['fast_sp']}[gait]

    def accel(self, gait: str) -> float:
        return self.p['fast_acc'] if gait == 'fast' else self.p['acc']

    def probe(self, gait: str) -> float:
        """How far out from its centre the body looks for ground.

        `ry_r_walk`, `ry_r_run`, `ry_r_fast` and `ry_r_fall` - the disc's,
        one per locomotion state, and see the note at the head of this file
        for what is read and what is assumed. `stop` gets the walking one."""
        return self.p.get('ry_r_' + ('walk' if gait == 'stop' else gait),
                          self.p['ry_r_run'])

    # -- one frame ---------------------------------------------------------

    def step(self, world, gait: str = 'run', facing: float = None,
             jump: bool = False) -> dict:
        """Advance one simulation frame. Returns what happened, for the log."""
        self.frame += 1
        if facing is not None:
            self._turn(facing)

        want = self.target_speed(gait)
        a = self.accel(gait)
        if self.speed < want:
            self.speed = min(want, self.speed + a)
        elif self.speed > want:
            self.speed = max(want, self.speed - a)

        rad = math.radians(self.heading)
        dx = math.sin(rad) * self.speed
        dz = math.cos(rad) * self.speed

        event = ''
        want_x, want_z = self.x + dx, self.z + dz
        # The body is a capsule of radius `col_r` and the fence is a line, so
        # the centre is pushed back to exactly `col_r` from it. Sliding falls
        # out of that for free: the along-wall component survives, the into-
        # wall component does not. What happens at a wall is not on the disc,
        # so this is the engine's choice - but the 0.5 it uses is not.
        (px, pz), touched = world.push_out((want_x, want_z), self.radius)
        if touched:
            event = 'fence ' + touched[0]
            moved = math.hypot(px - self.x, pz - self.z)
            self.speed = min(self.speed, moved)
        self.x, self.z = px, pz

        if jump and self.grounded:
            self.vy = self.p['jp_speed_y']
            self.grounded = False
            event = event or 'jump'

        if self.grounded:
            # Step up onto anything within `col_r`; step down onto anything
            # within `col_r`; beyond that, walk off it and fall. The tolerance
            # is the capsule radius because nothing on the disc names a step
            # height, and reusing a parameter beats inventing one.
            step = self.radius
            ground = world.under(self.x, self.z, self.y + step,
                                 self.probe(gait))
            if ground is None:
                event = event or 'off the mesh'
                self.grounded = False
            elif ground < self.y - step:
                event = event or 'walked off'
                self.grounded = False
            else:
                self.y = ground
        else:
            self.vy = max(-self.p['fall_spd_max'],
                          self.vy + self.p['fall_gravity_y'])
            self.y += self.vy
            ground = world.under(self.x, self.z, self.y + 0.01,
                                 self.probe('fall'))
            if ground is None:
                event = event or 'off the mesh'
            elif self.vy <= 0 and self.y <= ground:
                self.y = ground
                self.vy = 0.0
                self.grounded = True
                event = event or 'land'
        return {'frame': self.frame, 'x': self.x, 'y': self.y,
                'z': self.z, 'speed': self.speed,
                'heading': self.heading, 'event': event}

    def _turn(self, target: float) -> None:
        """Turn toward `target` under rot_y_acc and rot_y_spd."""
        a = self.p['rot_y_acc']
        cap = self.p['rot_y_spd']
        left = ((target - self.heading + 180.0) % 360.0) - 180.0
        if abs(left) < 1e-9 and abs(self.turn_rate) < 1e-9:
            return
        want = math.copysign(cap, left)
        # brake in time to stop on the target rather than overshoot it
        if self.turn_rate * self.turn_rate >= 2.0 * a * abs(left):
            want = 0.0
        if self.turn_rate < want:
            self.turn_rate = min(want, self.turn_rate + a)
        elif self.turn_rate > want:
            self.turn_rate = max(want, self.turn_rate - a)
        if abs(self.turn_rate) >= abs(left):
            self.heading = target % 360.0
            self.turn_rate = 0.0
        else:
            self.heading = (self.heading + self.turn_rate) % 360.0


def bearing(fx: float, fz: float, tx: float, tz: float) -> float:
    """The heading that points from one XZ point at another, degrees."""
    return math.degrees(math.atan2(tx - fx, tz - fz)) % 360.0
