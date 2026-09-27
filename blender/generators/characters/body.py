"""Deformation-friendly humanoid body cage.

The body is lofted from explicit cross-section rings around the shared
skeleton, producing an all-quad cage that is later subdivided once
(Catmull-Clark). Construction rules encoded here:

* Torso rings have 18 vertices. The lowest (crotch) ring is a figure-8 whose
  two halves plus the shared crotch edge form two 10-vertex leg loops, so the
  legs branch off without triangles or poles on the thighs.
* Arms leave the torso through a 10-vertex opening (3x2 faces removed on the
  side of the chest) that is bridged to the first arm ring.
* Elbows and knees get three loops (above / at / below the joint); wrists,
  ankles, shoulders and hips get blend loops. Weights are assigned per ring,
  so the Catmull-Clark subdivision interpolates smooth joint falloffs.
* Hands: a flattened palm with four finger bases on the knuckle cap and a
  thumb extruded from the radial side; fingers are 4-sided tubes with a loop
  at every knuckle.

Every vertex carries skin weights (bmesh deform layer), a ``zone`` tag
(region*100 + ring) and pattern coordinates; every face a ``zone`` tag for
its band. Garments reuse this topology (see clothing.py), which gives them
exact, consistent skin weights.

Body variation changes ring shapes only; joints never move.
"""

import math

import bmesh
from mathutils import Vector

from rigging.human_rig import skeleton
from utilities.meshkit import PATTERN_ATTR

TORSO, ARM_L, ARM_R, HAND_L, HAND_R, LEG_L, LEG_R, FOOT_L, FOOT_R, NECK = range(1, 11)
REGION = {"L": {"arm": ARM_L, "hand": HAND_L, "leg": LEG_L, "foot": FOOT_L},
          "R": {"arm": ARM_R, "hand": HAND_R, "leg": LEG_R, "foot": FOOT_R}}

BODY_TYPES = {
    #          girth  shoulder  hip   belly  chest  limb
    "slim":     (0.93, 0.97,    0.96, 0.0,   0.96,  0.98),
    "standard": (1.03, 1.03,    1.0,  0.0,   1.02,  1.1),
    "stocky":   (1.1,  1.1,     1.03, 0.25,  1.07,  1.2),
    "heavy":    (1.14, 1.06,    1.08, 0.85,  1.09,  1.2),
}

N_TORSO = 18
N_LIMB = 10


def _sgnpow(x, p):
    return math.copysign(abs(x) ** p, x)


class BodyCage:
    def __init__(self, body_type="standard", presentation="masculine"):
        self.sk = skeleton()
        self.j = self.sk.joints
        if body_type not in BODY_TYPES:
            raise ValueError(f"unknown body type {body_type}")
        self.girth, self.shoulder, self.hip, self.belly, self.chest, self.limb = BODY_TYPES[body_type]
        self.fem = presentation == "feminine"
        self.bm = bmesh.new()
        self.dl = self.bm.verts.layers.deform.verify()
        self.vzone = self.bm.verts.layers.int.new("zone")
        self.fzone = self.bm.faces.layers.int.new("zone")
        self.pat = self.bm.verts.layers.float_vector.new(PATTERN_ATTR)
        self.groups = {}
        self.rings = {}
        self._build()

    # ------------------------------------------------------------ helpers
    def gidx(self, bone):
        if bone not in self.groups:
            self.groups[bone] = len(self.groups)
        return self.groups[bone]

    def vert(self, co, zone, weights):
        v = self.bm.verts.new(co)
        v[self.vzone] = zone
        v[self.pat] = Vector(co)
        tot = sum(weights.values())
        for b, w in weights.items():
            if w > 0:
                v[self.dl][self.gidx(b)] = w / tot
        return v

    def face(self, verts, zone):
        f = self.bm.faces.new(verts)
        f[self.fzone] = zone
        f.smooth = True
        return f

    def inset_cap(self, face, thickness, zone, weights):
        """Inset a cap face and give the new inner vertices explicit data."""
        bmesh.ops.inset_individual(self.bm, faces=[face], thickness=thickness, depth=0.0)
        tot = sum(weights.values())
        for v in face.verts:
            v[self.vzone] = zone
            v[self.pat] = v.co.copy()
            for g in list(v[self.dl].keys()):
                del v[self.dl][g]
            for b, w in weights.items():
                v[self.dl][self.gidx(b)] = w / tot
        return face

    def loft(self, ra, rb, zone, closed=True):
        n = len(ra)
        faces = []
        for k in range(n if closed else n - 1):
            k2 = (k + 1) % n
            quad = [ra[k], ra[k2], rb[k2], rb[k]]
            if len(set(quad)) < 4:
                quad = list(dict.fromkeys(quad))
            faces.append(self.face(quad, zone))
        return faces

    def bridge(self, loop_a, loop_b, zone):
        """Quad band between two loops of equal length, choosing direction and
        cyclic offset that minimise total edge length (no twisting)."""
        n = len(loop_a)
        if len(loop_b) != n:
            raise ValueError("bridge loops differ in length")
        best = None
        for rev in (False, True):
            lb = list(reversed(loop_b)) if rev else list(loop_b)
            for off in range(n):
                cost = sum((loop_a[k].co - lb[(k + off) % n].co).length for k in range(n))
                if best is None or cost < best[0]:
                    best = (cost, [lb[(k + off) % n] for k in range(n)])
        return self.loft(loop_a, best[1], zone)

    # ------------------------------------------------------------ torso
    def torso_ring(self, z, w, df, db, yc=0.0, squ=2.5, bust=0.0, belly=0.0):
        pts = []
        for k in range(N_TORSO):
            th = 2 * math.pi * k / N_TORSO
            s, c = math.sin(th), math.cos(th)
            x = w * _sgnpow(s, 2.0 / squ)
            d = df if c > 0 else db
            y = yc - d * _sgnpow(c, 2.0 / squ)
            if c > 0 and bust:
                # Two soft lobes at +-35 degrees for the feminine chest.
                lobe = math.exp(-((abs(th if th < math.pi else 2 * math.pi - th) - 0.62) ** 2) / 0.09)
                y -= bust * lobe
            if c > 0 and belly:
                y -= belly * (c ** 2)
            pts.append(Vector((x, y, z)))
        return pts

    def torso_weights(self, ring, k):
        side = "L" if 0 < k < 9 else ("R" if k > 9 else None)
        table = {
            1: {"pelvis": 0.85},
            2: {"pelvis": 0.7, "spine_01": 0.3},
            3: {"pelvis": 0.35, "spine_01": 0.65},
            4: {"spine_01": 0.6, "spine_02": 0.4},
            5: {"spine_01": 0.2, "spine_02": 0.8},
            6: {"spine_02": 0.5, "spine_03": 0.5},
            7: {"spine_03": 1.0},
            8: {"spine_03": 0.65},
            9: {"spine_03": 0.55, "neck": 0.25},
        }
        w = dict(table[ring])
        th = 2 * math.pi * k / N_TORSO
        lateral = abs(math.sin(th))
        if ring == 1 and side:
            w[f"thigh.{side}"] = 0.15 * lateral
        if ring in (8, 9) and side:
            w[f"clavicle.{side}"] = (0.35 if ring == 8 else 0.2) * (0.3 + 0.7 * lateral)
        return w

    def _build_torso(self):
        g, sh, hp, ch = self.girth, self.shoulder, self.hip, self.chest
        fem = self.fem
        waist = 0.93 if fem else 1.0
        hips_f = 1.07 if fem else 1.0
        sh_f = 0.93 if fem else 1.0
        belly = self.belly
        spec = [
            # ring, z, w, df, db, bust, belly
            (1, 0.905, 0.172 * g * hp * hips_f, 0.098 * g, 0.112 * g * hips_f, 0.0, 0.0),
            (2, 0.975, 0.166 * g * hp * hips_f * (0.98 if fem else 1.0), 0.094 * g, 0.1 * g, 0.0, 0.012 * belly),
            (3, 1.045, 0.156 * g * waist, 0.093 * g, 0.086 * g, 0.0, 0.03 * belly),
            (4, 1.12, 0.16 * g * (0.95 if fem else 1.0), 0.1 * g, 0.084 * g, 0.0, 0.045 * belly),
            (5, 1.2, 0.17 * g * ch, 0.108 * g * ch, 0.09 * g, 0.012 if fem else 0.0, 0.03 * belly),
            (6, 1.28, 0.176 * g * ch * sh_f, 0.114 * g * ch, 0.096 * g, 0.03 if fem else 0.0, 0.0),
            (7, 1.36, 0.182 * g * sh * sh_f, 0.104 * g * ch, 0.1 * g, 0.022 if fem else 0.0, 0.0),
            (8, 1.44, 0.178 * g * sh * sh_f, 0.082 * g, 0.088 * g, 0.0, 0.0),
            (9, 1.478, 0.108 * g * (0.95 if fem else 1.0), 0.06 * g, 0.066 * g, 0.0, 0.0),
        ]
        rings = {}
        for ring, z, w, df, db, bust, bel in spec:
            pts = self.torso_ring(z, w, df, db, yc=0.0, bust=bust, belly=bel)
            rings[ring] = [self.vert(p, TORSO * 100 + ring, self.torso_weights(ring, k)) for k, p in enumerate(pts)]
        # Crotch ring (ring 0): figure-8 of two leg loops sharing the crotch edge.
        r_thigh = 0.1 * g * self.limb * (1.04 if fem else 1.0)
        cx = r_thigh * math.cos(math.radians(18))
        z0 = 0.845
        pts0 = [None] * N_TORSO
        for i in range(N_LIMB):
            a = math.radians(18 + 36 * i)
            px = cx - r_thigh * math.cos(a)
            py = -r_thigh * math.sin(a) * (0.95 if i in (0, 9) else 1.0)
            zz = z0 - (0.025 if i in (0, 9) else 0.0)
            if i == 0:
                pts0[0] = Vector((0.0, py, zz))
            elif i == 9:
                pts0[9] = Vector((0.0, py, zz))
            else:
                pts0[i] = Vector((px, py, zz))
                pts0[N_TORSO - i] = Vector((-px, py, zz))
        r0 = []
        for k, p in enumerate(pts0):
            side = "L" if 0 < k < 9 else ("R" if k > 9 else None)
            if side:
                w = {"pelvis": 0.55, f"thigh.{side}": 0.45}
            else:
                # Crotch: shared by both legs; split so a flexing thigh drags it
                # along instead of tearing the edge between the legs.
                w = {"pelvis": 0.5, "thigh.L": 0.25, "thigh.R": 0.25}
            r0.append(self.vert(p, TORSO * 100 + 0, w))
        rings[0] = r0
        self.rings["torso"] = rings
        # Arm openings: remove the 3x2 face block on each side of rings 6..8.
        opening_cols = {"L": (3, 6), "R": (12, 15)}
        for ring in range(0, 9):
            ra, rb = rings[ring], rings[ring + 1]
            for k in range(N_TORSO):
                k2 = (k + 1) % N_TORSO
                if ring in (6, 7) and any(c0 <= k < c1 for c0, c1 in opening_cols.values()):
                    continue
                self.face([ra[k], ra[k2], rb[k2], rb[k]], TORSO * 100 + ring)
        self.openings = {}
        for side, (c0, c1) in opening_cols.items():
            loop = [rings[6][c] for c in range(c0, c1 + 1)] + [rings[7][c1]] + \
                   [rings[8][c] for c in range(c1, c0 - 1, -1)] + [rings[7][c0]]
            self.openings[side] = loop
        # The inner opening vertices (ring 7 between the columns) must go.
        for side, (c0, c1) in opening_cols.items():
            for c in range(c0 + 1, c1):
                self.bm.verts.remove(rings[7][c])
        # Neck stub + cap (hidden inside the head module and collar).
        n0 = self.torso_ring(1.505, 0.06 * g, 0.056 * g, 0.058 * g, yc=0.006, squ=2.0)
        rn = [self.vert(p, NECK * 100 + 0, {"neck": 0.6, "spine_03": 0.4}) for p in n0]
        self.loft(rings[9], rn, TORSO * 100 + 9)
        top = [self.vert(Vector((p.x * 0.7, p.y * 0.7 + 0.002, 1.53)), NECK * 100 + 1, {"neck": 1.0}) for p in n0]
        self.loft(rn, top, NECK * 100 + 0)
        c = self.face(top, NECK * 100 + 1)
        self.inset_cap(c, 0.02, NECK * 100 + 1, {"neck": 1.0})

    # ------------------------------------------------------------ arms & hands
    def _limb_frame(self, side):
        d, t, p = self.sk.hand_frame(side)
        return d, -p, t  # axis, e1 (back of hand / top of arm), e2 (thumb side / front)

    @staticmethod
    def _hand_angles():
        back = [(-0.016, 0.042), (-0.016, 0.021), (-0.016, 0.0), (-0.016, -0.021), (-0.016, -0.042)]
        palm = [(0.016, -0.042), (0.016, -0.021), (0.016, 0.0), (0.016, 0.021), (0.016, 0.042)]
        return [math.atan2(tt, -pp) for pp, tt in back + palm]

    def _limb_ring(self, center, axis, e1, e2, angles, rx, ry, zone, weights, flat=None):
        pts = []
        for a in angles:
            ca, sa = math.cos(a), math.sin(a)
            r1, r2 = rx, ry
            if flat is not None:
                # squircle-ish flattening toward the hand rectangle
                ca = _sgnpow(ca, flat)
                sa = _sgnpow(sa, flat)
            pts.append(center + e1 * (r1 * ca) + e2 * (r2 * sa))
        return [self.vert(p, zone, weights) for p in pts]

    def _build_arm(self, side):
        j = self.j
        s = self.limb * (0.94 if self.fem else 1.0)
        axis, e1, e2 = self._limb_frame(side)
        sh, el, wr = j[f"shoulder.{side}"], j[f"elbow.{side}"], j[f"wrist.{side}"]
        uni = [math.radians(72 - 36 * k) for k in range(N_LIMB)]
        hand = self._hand_angles()
        ua, fa, hd = f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}"
        cl = f"clavicle.{side}"
        reg = REGION[side]["arm"]

        def blend(t):
            return [u + (h - u) * t for u, h in zip(uni, hand)]

        L_ua = (el - sh).length
        L_fa = (wr - el).length
        # (center, rx(top/back), ry(front/thumb), angle-blend, weights)
        spec = [
            (sh + axis * 0.045, 0.064 * s * self.shoulder, 0.06 * s, 0.0, {ua: 0.6, cl: 0.4}),
            (sh + axis * (L_ua * 0.45), 0.052 * s, 0.056 * s, 0.1, {ua: 1.0}),
            (sh + axis * (L_ua * 0.82), 0.045 * s, 0.046 * s, 0.2, {ua: 0.8, fa: 0.2}),
            (el + axis * 0.0, 0.043 * s, 0.043 * s, 0.3, {ua: 0.5, fa: 0.5}),
            (el + axis * (L_fa * 0.15), 0.046 * s, 0.046 * s, 0.4, {ua: 0.2, fa: 0.8}),
            (el + axis * (L_fa * 0.5), 0.038 * s, 0.043 * s, 0.6, {fa: 1.0}),
            (el + axis * (L_fa * 0.84), 0.027 * s, 0.036 * s, 0.85, {fa: 0.9, hd: 0.1}),
            (wr + axis * 0.0, 0.022 * s, 0.033 * s, 1.0, {fa: 0.5, hd: 0.5}),
        ]
        rings = []
        for i, (c, rx, ry, bl, w) in enumerate(spec):
            flat = 0.6 if bl > 0.8 else None
            rings.append(self._limb_ring(c, axis, e1, e2, blend(bl), rx, ry, reg * 100 + i + 1, w, flat))
        self.bridge(self.openings[side], rings[0], reg * 100 + 0)
        for i in range(len(rings) - 1):
            self.loft(rings[i], rings[i + 1], reg * 100 + i + 1)
        self.rings[f"arm.{side}"] = rings
        self._build_hand(side, rings[-1])

    def _build_hand(self, side, wrist):
        j = self.j
        sk = self.sk
        s = self.limb * (0.93 if self.fem else 1.0)
        d, t, p = sk.hand_frame(side)
        hd = f"hand.{side}"
        reg = REGION[side]["hand"]
        w0 = j[f"wrist.{side}"]
        # Palm rings: back row (thumb->pinky) then palm row (pinky->thumb)
        def palm_ring(dist, half_w, half_t, zone, weights, widths=None):
            c = w0 + d * dist
            ws = widths or [half_w, half_w * 0.5, 0.0, -half_w * 0.5, -half_w]
            back = [c - p * half_t + t * x for x in ws]
            palm = [c + p * half_t + t * x for x in reversed(ws)]
            return [self.vert(q, zone, weights) for q in back + palm]

        h1 = palm_ring(0.045 * s, 0.043 * s, 0.017 * s, reg * 100 + 1, {hd: 1.0})
        kn_w = [0.04 * s, 0.019 * s, -0.001 * s, -0.02 * s, -0.038 * s]
        h2 = palm_ring(0.084 * s, 0.045 * s, 0.015 * s, reg * 100 + 2, {hd: 1.0}, kn_w)
        # Wrist -> palm band, leaving the thumb-side quad open for the thumb.
        faces = self.bridge(wrist, h1, reg * 100 + 0)
        self.loft(h1, h2, reg * 100 + 1)
        # Identify the thumb base quad: the band face whose center is farthest along +t.
        thumb_face = max(faces, key=lambda f: f.calc_center_median().dot(t))
        thumb_loop = list(thumb_face.verts)
        self.bm.faces.remove(thumb_face)
        # Finger bases on the knuckle cap.
        back = h2[:5]
        palm = list(reversed(h2[5:]))
        bases = {}
        for i, f in enumerate(("index", "middle", "ring", "pinky")):
            bases[f] = [back[i], back[i + 1], palm[i + 1], palm[i]]
        for f, loop in bases.items():
            self._build_finger(side, f, loop, reg, s)
        self._build_finger(side, "thumb", thumb_loop, reg, s, thumb=True)

    def _build_finger(self, side, finger, base_loop, reg, s, thumb=False):
        sk = self.sk
        pts, curl = sk.finger_chains[(finger, side)]
        d_, t_, p_ = sk.hand_frame(side)
        bones = [f"{finger}_{i + 1:02d}.{side}" for i in range(3)]
        hd = f"hand.{side}"
        width = {"thumb": 0.021, "index": 0.0185, "middle": 0.019, "ring": 0.018, "pinky": 0.0155}[finger] * s
        code = {"index": 10, "middle": 20, "ring": 30, "pinky": 40, "thumb": 50}[finger]
        # Stations along the chain: (point, width scale, weights)
        st = []
        a, b, c, e = pts
        st.append((a + (b - a) * 0.08, 1.0, {hd: 0.5, bones[0]: 0.5}))
        st.append((a + (b - a) * 0.55, 0.96, {bones[0]: 1.0}))
        st.append((b, 0.9, {bones[0]: 0.5, bones[1]: 0.5}))
        st.append((b + (c - b) * 0.55, 0.88, {bones[1]: 1.0}))
        st.append((c, 0.84, {bones[1]: 0.5, bones[2]: 0.5}))
        st.append((c + (e - c) * 0.6, 0.8, {bones[2]: 1.0}))
        st.append((e - (e - c).normalized() * 0.004, 0.62, {bones[2]: 1.0}))
        rings = []
        for i, (pt, ws, w) in enumerate(st):
            axis = (b - a).normalized() if i < 2 else ((c - b).normalized() if i < 4 else (e - c).normalized())
            up = (-curl if not thumb else -curl)
            up = (up - axis * up.dot(axis)).normalized()
            side_v = axis.cross(up).normalized()
            hw = width * ws * 0.5
            ht = width * ws * 0.46
            ring = [pt + up * ht + side_v * hw, pt + up * ht - side_v * hw,
                    pt - up * ht - side_v * hw, pt - up * ht + side_v * hw]
            rings.append([self.vert(q, reg * 100 + code + i + 1, w) for q in ring])
        self.bridge(base_loop, rings[0], reg * 100 + code)
        for i in range(len(rings) - 1):
            self.loft(rings[i], rings[i + 1], reg * 100 + code + i + 1)
        tip = rings[-1]
        cen = sum((v.co for v in tip), Vector()) / 4 + (e - c).normalized() * 0.004
        tipv = self.vert(cen, reg * 100 + code + 9, {bones[2]: 1.0})
        for k in range(4):
            self.face([tip[k], tip[(k + 1) % 4], tipv], reg * 100 + code + 9)

    # ------------------------------------------------------------ legs & feet
    def _build_leg(self, side):
        j = self.j
        s = self.limb * self.girth ** 0.5
        fem = self.fem
        th, cf, ft = f"thigh.{side}", f"calf.{side}", f"foot.{side}"
        reg = REGION[side]["leg"]
        rings0 = self.rings["torso"][0]
        if side == "L":
            loop0 = [rings0[k] for k in range(0, 10)]
        else:
            loop0 = [rings0[0]] + [rings0[k] for k in range(17, 9, -1)] + [rings0[9]]
            loop0 = loop0[:10]
        hip, knee, ankle = j[f"hip.{side}"], j[f"knee.{side}"], j[f"ankle.{side}"]
        sx = 1.0 if side == "L" else -1.0
        inner = Vector((-sx, 0.0, 0.0))
        front = Vector((0.0, -1.0, 0.0))

        def ring_at(center, axis, rx_in, rx_out, ry_f, ry_b, zone, weights):
            e_in = (inner - axis * inner.dot(axis)).normalized()
            e_f = (front - axis * front.dot(axis)).normalized()
            out = []
            for i in range(N_LIMB):
                a = math.radians(18 + 36 * i)
                ci, sf = math.cos(a), math.sin(a)
                r_i = rx_in if ci > 0 else rx_out
                r_f = ry_f if sf > 0 else ry_b
                out.append(center + e_in * (r_i * ci) + e_f * (r_f * sf))
            return [self.vert(q, zone, weights) for q in out]

        ax_t = (knee - hip).normalized()
        ax_c = (ankle - knee).normalized()
        f = 1.05 if fem else 1.0
        spec = [
            (hip + ax_t * 0.075, ax_t, 0.085, 0.096, 0.094, 0.1, {th: 0.8, "pelvis": 0.2}, f),
            (hip + ax_t * 0.2, ax_t, 0.078, 0.088, 0.088, 0.086, {th: 1.0}, f),
            (knee - ax_t * 0.07, ax_t, 0.064, 0.068, 0.068, 0.064, {th: 0.8, cf: 0.2}, 1.0),
            (knee, ax_t, 0.058, 0.061, 0.066, 0.058, {th: 0.5, cf: 0.5}, 1.0),
            (knee + ax_c * 0.06, ax_c, 0.056, 0.058, 0.058, 0.062, {th: 0.2, cf: 0.8}, 1.0),
            (knee + ax_c * 0.17, ax_c, 0.055, 0.058, 0.054, 0.07, {cf: 1.0}, 1.0),
            (knee + ax_c * 0.3, ax_c, 0.043, 0.045, 0.042, 0.05, {cf: 1.0}, 1.0),
            (ankle + ax_c * (-0.012), ax_c, 0.034, 0.036, 0.036, 0.038, {cf: 0.5, ft: 0.5}, 1.0),
        ]
        rings = []
        for i, (c, ax, ri, ro, rf, rb, w, ff) in enumerate(spec):
            rings.append(ring_at(c, ax, ri * s * ff, ro * s * ff, rf * s * ff, rb * s * ff, reg * 100 + i + 1, w))
        self.bridge(loop0, rings[0], reg * 100 + 0)
        for i in range(len(rings) - 1):
            self.loft(rings[i], rings[i + 1], reg * 100 + i + 1)
        self.rings[f"leg.{side}"] = rings
        self._build_foot(side, rings[-1], s)

    def _build_foot(self, side, ankle_ring, s):
        j = self.j
        reg = REGION[side]["foot"]
        ft, to = f"foot.{side}", f"toe.{side}"
        ankle, ball, tip = j[f"ankle.{side}"], j[f"ball.{side}"], j[f"toe_tip.{side}"]
        x = ankle.x
        sx = 1.0 if side == "L" else -1.0
        w = 0.045 * s

        def section(y, z_top, z_bot, half_w, zone, weights, inner_bias=0.0):
            # 10 verts matching the leg layout: inner, front-inner, front(top), ... around the foot axis (Y)
            out = []
            for i in range(N_LIMB):
                a = math.radians(18 + 36 * i)
                ci, sf = math.cos(a), math.sin(a)
                xx = x - sx * half_w * ci * (1.0 + inner_bias)
                zz = (z_top if sf > 0 else z_bot) if abs(sf) > 0.3 else (z_top + z_bot) / 2
                zz = (z_top + z_bot) / 2 + (z_top - z_bot) / 2 * sf
                out.append(Vector((xx, y, zz)))
            return [self.vert(q, zone, weights) for q in out]

        f1 = section(0.03, 0.095, 0.004, w * 1.0, reg * 100 + 1, {ft: 1.0})
        f2 = section(-0.03, 0.078, 0.004, w * 1.05, reg * 100 + 2, {ft: 1.0})
        f3 = section(ball.y + 0.005, 0.05, 0.004, w * 1.08, reg * 100 + 3, {ft: 0.5, to: 0.5})
        f4 = section(tip.y + 0.03, 0.035, 0.004, w * 0.95, reg * 100 + 4, {to: 1.0})
        f5 = section(tip.y + 0.005, 0.026, 0.006, w * 0.6, reg * 100 + 5, {to: 1.0})
        self.bridge(ankle_ring, f1, reg * 100 + 0)
        self.loft(f1, f2, reg * 100 + 1)
        self.loft(f2, f3, reg * 100 + 2)
        self.loft(f3, f4, reg * 100 + 3)
        self.loft(f4, f5, reg * 100 + 4)
        c = self.face(list(f5), reg * 100 + 5)
        self.inset_cap(c, 0.008, reg * 100 + 5, {to: 1.0})
        # Heel: push the back-bottom of the first section backwards.
        for v in f1:
            if v.co.z < 0.05:
                v.co.y += 0.045

    # ------------------------------------------------------------ build
    def _build(self):
        self._build_torso()
        for side in ("L", "R"):
            self._build_arm(side)
            self._build_leg(side)
        bmesh.ops.recalc_face_normals(self.bm, faces=list(self.bm.faces))
        self.bm.normal_update()

    def open_edges(self):
        return [e for e in self.bm.edges if len(e.link_faces) != 2]

    def group_names(self):
        return [b for b, _ in sorted(self.groups.items(), key=lambda kv: kv[1])]


def bm_to_object(bm, name, group_names, library=None, material_key=None, collection=None):
    """Write a bmesh with a deform layer into a new object with named vertex groups."""
    import bpy
    from core import scene as scn
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    obj = bpy.data.objects.new(name, me)
    for g in group_names:
        obj.vertex_groups.new(name=g)
    if library is not None and material_key:
        me.materials.append(library.get(material_key))
    scn.link(obj, collection)
    obj["mm_kind"] = "render"
    me.shade_smooth()
    return obj
