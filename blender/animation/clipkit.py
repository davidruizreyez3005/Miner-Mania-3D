"""Building blocks for procedural clips: timing curves, foot frames, the
standing base pose and a planted-foot locomotion generator."""

import math

from mathutils import Matrix, Quaternion, Vector

from .rig_model import frame, hand_socket_frame, model, socket_frame

FPS = 30


# ----------------------------------------------------------------- curves

def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def smoother(x):
    x = max(0.0, min(1.0, x))
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


def lerp(a, b, t):
    if isinstance(a, (tuple, list)):
        return tuple(x + (y - x) * t for x, y in zip(a, b))
    return a + (b - a) * t


def ease_in(x):
    """Accelerating (swing into an impact)."""
    x = max(0.0, min(1.0, x))
    return x * x * x


def ease_out(x):
    """Decelerating (recoil, settling)."""
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


def linear(x):
    return max(0.0, min(1.0, x))


def keys(t, pts, ease=smooth, loop=None):
    """Piecewise interpolation through [(time, value[, ease]), ...].

    Values may be floats, tuples, Vectors or 4x4 frames (translation lerp,
    rotation slerp). A third element overrides the easing of the segment that
    ends at that key. With ``loop=T`` the last key wraps to the first so
    looping clips stay continuous.
    """
    if loop:
        t = t % loop
        pts = list(pts) + [(pts[0][0] + loop, pts[0][1])]
    if t <= pts[0][0]:
        return _copy(pts[0][1])
    for p0, p1 in zip(pts, pts[1:]):
        t0, v0 = p0[0], p0[1]
        t1, v1 = p1[0], p1[1]
        if t0 <= t <= t1:
            fn = p1[2] if len(p1) > 2 else ease
            a = 0.0 if t1 <= t0 else fn((t - t0) / (t1 - t0))
            if isinstance(v0, Matrix):
                return flerp(v0, v1, a)
            if isinstance(v0, Vector):
                return v0.lerp(v1, a)
            return lerp(v0, v1, a)
    return _copy(pts[-1][1])


def _copy(v):
    return v.copy() if isinstance(v, (Vector, Matrix)) else v


def flerp(a, b, t):
    """Interpolate two rigid 4x4 frames."""
    qa = a.to_quaternion()
    qb = b.to_quaternion()
    if qa.dot(qb) < 0.0:
        qb.negate()
    m = qa.slerp(qb, t).to_matrix().to_4x4()
    m.translation = a.translation.lerp(b.translation, t)
    return m


def tool_frame(pos, handle, face):
    """hand_tool socket frame for a tool whose handle (item +Z) points along
    ``handle`` and whose working face (item -Y) points along ``face``."""
    return socket_frame(Vector(pos), Vector(handle), Vector(face))


def hand_frame(side, pos, palm, fingers):
    """hand_tool socket frame from a palm normal and finger direction."""
    return hand_socket_frame(side, Vector(pos), Vector(palm), Vector(fingers))


def offset_frame(base, offset):
    """``base`` moved by a local offset (same rotation)."""
    m = base.copy()
    m.translation = base @ Vector(offset)
    return m


def carry_frame(pos, yaw=0.0, pitch=0.0):
    """carry_attachment target: box bottom centre, item up = +Z, front = -Y."""
    q = Quaternion(Vector((0, 0, 1)), math.radians(yaw)) @ Quaternion(Vector((1, 0, 0)), math.radians(pitch))
    up = q @ Vector((0, 0, 1))
    front = q @ Vector((0, -1, 0))
    return socket_frame(Vector(pos), up, front)


def wave(t, period, amp=1.0, phase=0.0):
    return amp * math.sin(2.0 * math.pi * (t / period + phase))


def add(*poses):
    """Sum semantic rotation tuples bone-wise."""
    out = {}
    for p in poses:
        for b, v in p.items():
            if b in out:
                out[b] = tuple(x + y for x, y in zip(out[b], v))
            else:
                out[b] = tuple(v)
    return out


def blend(a, b, t):
    # Ordered union: bone names are strings, whose set order changes with every
    # process (hash randomization), and this order becomes the fcurve order.
    keys_ = list(a) + [k for k in b if k not in a]
    out = {}
    for k in keys_:
        va = a.get(k, (0.0, 0.0, 0.0))
        vb = b.get(k, (0.0, 0.0, 0.0))
        out[k] = tuple(x + (y - x) * t for x, y in zip(va, vb))
    return out


# ----------------------------------------------------------------- feet

def rest_foot(side):
    return model().rest[f"foot.{side}"].copy()


def foot_frame(side, ankle, yaw=0.0, pitch=0.0):
    """Foot bone target frame: rest orientation rotated by ``pitch`` (about the
    foot's lateral axis; + lifts the toes) and ``yaw`` (about world Z)."""
    r = rest_foot(side).to_3x3()
    lateral = r.col[0]
    q = Quaternion(Vector((0, 0, 1)), math.radians(yaw)) @ Quaternion(lateral, math.radians(pitch))
    m = (q.to_matrix() @ r).to_4x4()
    m.translation = Vector(ankle)
    return m


def _foot_points(side):
    j = model().sk.joints
    ankle = j[f"ankle.{side}"]
    ball = j[f"ball.{side}"]
    heel = Vector((ankle.x, ankle.y + 0.045, 0.012))
    return ankle, ball, heel


def _pivot_foot(side, pivot_rest, pivot_pos, pitch, yaw):
    """Foot frame rotated by (pitch, yaw) such that the foot-fixed point
    ``pivot_rest`` (rest armature position) lands on ``pivot_pos``."""
    rest = rest_foot(side)
    local = rest.inverted() @ Vector(pivot_rest)          # point fixed in the foot
    ankle, _, _ = _foot_points(side)
    f = foot_frame(side, ankle, yaw=yaw, pitch=pitch)
    f.translation = Vector((0.0, 0.0, 0.0))
    f.translation = Vector(pivot_pos) - (f @ local)
    return f


def foot_from_ball(side, ball_pos, heel_lift=0.0, yaw=0.0):
    """Foot frame pivoting about the ball of the foot (heel raised by
    ``heel_lift`` degrees) with the ball resting at ``ball_pos``."""
    _, ball, _ = _foot_points(side)
    return _pivot_foot(side, ball, ball_pos, -heel_lift, yaw)


def foot_from_heel(side, heel_pos, toe_up=0.0, yaw=0.0):
    """Foot frame pivoting about the heel (toes raised by ``toe_up`` degrees)."""
    _, _, heel = _foot_points(side)
    return _pivot_foot(side, heel, heel_pos, toe_up, yaw)


def rest_ball(side):
    return model().sk.joints[f"ball.{side}"].copy()


def planted(side, dx=0.0, dy=0.0, yaw=0.0):
    """Flat planted foot displaced on the ground (armature space)."""
    b = rest_ball(side) + Vector((dx, dy, 0.0))
    return foot_from_ball(side, b, 0.0, yaw)


# ----------------------------------------------------------------- base pose

STAND = {
    "spine_01": (2.0, 0.0, 0.0), "spine_02": (1.0, 0.0, 0.0), "spine_03": (-2.5, 0.0, 0.0),
    "neck": (3.0, 0.0, 0.0), "head": (-3.0, 0.0, 0.0),
    "clavicle.L": (0.0, 0.0, -3.0), "clavicle.R": (0.0, 0.0, -3.0),
    "upper_arm.L": (6.0, 12.0, -37.0), "upper_arm.R": (6.0, 12.0, -37.0),
    "forearm.L": (14.0, 18.0, 0.0), "forearm.R": (14.0, 18.0, 0.0),
    "hand.L": (6.0, 0.0, 4.0), "hand.R": (6.0, 0.0, 4.0),
}


def stand_feet(width=0.0, yaw_out=5.0):
    return {"L": planted("L", dx=width, yaw=yaw_out), "R": planted("R", dx=-width, yaw=-yaw_out)}


# ----------------------------------------------------------------- locomotion

class Gait:
    """Planted-foot gait for in-place locomotion.

    The character faces -Y; while a foot is in stance its ball moves toward
    +Y at exactly ``speed`` m/s, so moving the character forward at ``speed``
    in-game keeps the foot fixed on the ground (validated after export).
    ``speed`` may be negative (walking backward).
    """

    def __init__(self, period, speed, stance=0.62, step_height=0.07, heel_strike=12.0, toe_off=28.0,
                 width=0.0, yaw_out=5.0, center=0.0):
        self.T = period
        self.v = speed
        self.stance = stance
        self.h = step_height
        self.heel_strike = heel_strike
        self.toe_off = toe_off
        self.width = width
        self.yaw_out = yaw_out
        self.stride = speed * period          # ground travel per cycle
        self.contact_span = abs(speed) * period * stance
        # Offsets are relative to the rest ball, which already sits ~10 cm ahead
        # of the rest ankle (under the hip); center=0 keeps the ankle range
        # centred under the hip so heel strike and toe-off both stay reachable.
        self.center = center

    def foot(self, side, t):
        """(ankle_frame, toe_angle, in_stance) for ``side`` at time t."""
        ph = ((t / self.T) + (0.0 if side == "R" else 0.5)) % 1.0
        base = rest_ball(side) + Vector((self.width * (1 if side == "L" else -1), 0.0, 0.0))
        yaw = self.yaw_out * (1 if side == "L" else -1)
        rz = Quaternion(Vector((0, 0, 1)), math.radians(yaw))
        ankle_r, ball_r, heel_r = _foot_points(side)
        heel_off = rz @ (heel_r - ball_r)
        half = self.contact_span / 2.0
        ahead, behind = (-half, half) if self.v >= 0 else (half, -half)
        ahead += self.center
        behind += self.center
        if ph < self.stance:
            u = ph / self.stance
            y = ahead + (behind - ahead) * u      # ball travels with the ground
            ball_pt = base + Vector((0.0, y, 0.0))
            if u < 0.12 and self.heel_strike:
                toe_up = self.heel_strike * (1.0 - smooth(u / 0.12))
                return foot_from_heel(side, ball_pt + heel_off, toe_up, yaw), 0.0, True
            lift = self.toe_off * smooth((u - 0.72) / 0.28) if u > 0.72 else 0.0
            return foot_from_ball(side, ball_pt, lift, yaw), lift, True
        u = (ph - self.stance) / (1.0 - self.stance)
        # Cubic Hermite swing whose end tangents equal the ground speed: the
        # foot leaves and lands at rest in world space (no velocity pop).
        m = self.v * self.T * (1.0 - self.stance)
        u2, u3 = u * u, u * u * u
        y = behind + (ahead - behind) * (3.0 * u2 - 2.0 * u3) + m * (u - 3.0 * u2 + 2.0 * u3)
        z = self.h * math.sin(math.pi * u) ** 1.2
        ball_pt = base + Vector((0.0, y, z))
        if u < 0.5:
            lift = self.toe_off * (1.0 - smooth(u / 0.35))
            return foot_from_ball(side, ball_pt, lift, yaw), lift * 0.5, False
        toe_up = self.heel_strike * smooth((u - 0.6) / 0.4)
        return foot_from_heel(side, ball_pt + heel_off, toe_up, yaw), 0.0, False

    def phase(self, t, side="R"):
        return ((t / self.T) + (0.0 if side == "R" else 0.5)) % 1.0
