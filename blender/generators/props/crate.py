"""Wooden and steel-framed crates.

Construction: plank panels with small gaps inside a perimeter frame, diagonal
brace on the large faces, steel corner brackets and screws as LOD0-only
detail. ``carry=True`` builds the standard carry crate (hand holes, 0.46 x
0.36 x 0.36 m) that matches the worker carry animations' grip width.
"""

from utilities.meshkit import trs


def build(ctx):
    sx, sy, sz = ctx.param("size", (0.8, 0.6, 0.6))
    wood = ctx.param("wood", "wood:wood_light")
    metal = ctx.param("metal", "steel_dark")
    carry = ctx.param("carry", False)
    board = ctx.param("board", 0.022)
    frame_w = ctx.param("frame", 0.07)
    rng = ctx.rng.child("planks")
    panels = ctx.geo("panels")
    frame = ctx.geo("frame")
    detail = ctx.geo("brackets", max_lod=0)

    def plank_face(center, u_len, v_len, normal_axis, sign, planks, horizontal=True):
        """Planks filling a face; u along the plank length."""
        gap = 0.006
        count = planks
        width = (v_len - gap * (count - 1)) / count
        for i in range(count):
            off = -v_len / 2 + width / 2 + i * (width + gap)
            jitter = rng.uniform(-0.002, 0.002)
            if normal_axis == "y":
                size = (u_len, board, width) if horizontal else (width, board, u_len)
                loc = (center[0], center[1], center[2] + off) if horizontal else (center[0] + off, center[1], center[2])
            elif normal_axis == "x":
                size = (board, u_len, width)
                loc = (center[0], center[1], center[2] + off)
            else:
                size = (u_len, width, board)
                loc = (center[0], center[1] + off, center[2])
            panels.box(size, matrix=trs((loc[0], loc[1], loc[2] + jitter * 0)), mat=wood, bevel=0.004, segments=1,
                       pattern_offset=(rng.uniform(0, 10), rng.uniform(0, 10), 0))

    inner = 0.004
    n_planks = max(3, int(round(sz / 0.12)))
    # Front / back faces (normal Y)
    for sgn in (-1, 1):
        plank_face((0, sgn * (sy / 2 - board / 2 - inner), sz / 2), sx - 2 * frame_w + 0.01, sz - 2 * frame_w + 0.01,
                   "y", sgn, n_planks)
        plank_face((sgn * (sx / 2 - board / 2 - inner), 0, sz / 2), sy - 2 * frame_w + 0.01, sz - 2 * frame_w + 0.01,
                   "x", sgn, n_planks)
    # Top and bottom
    for z in (board / 2 + inner, sz - board / 2 - inner):
        plank_face((0, 0, z), sx - 0.01, sy - 0.01, "z", 1, max(3, int(round(sy / 0.12))))
    # Perimeter frame boards (thicker, proud of the panels)
    t = board * 1.6
    for sgn_y in (-1, 1):
        y = sgn_y * (sy / 2 - t / 2)
        for z in (frame_w / 2, sz - frame_w / 2):
            frame.box((sx, t, frame_w), matrix=trs((0, y, z)), mat=wood, bevel=0.006, segments=1,
                      pattern_offset=(rng.uniform(0, 10), 0, 0))
        for sgn_x in (-1, 1):
            frame.box((frame_w, t, sz - 2 * frame_w), matrix=trs((sgn_x * (sx / 2 - frame_w / 2), y, sz / 2)),
                      mat=wood, bevel=0.006, segments=1, pattern_offset=(0, rng.uniform(0, 10), 0))
    for sgn_x in (-1, 1):
        x = sgn_x * (sx / 2 - t / 2)
        for z in (frame_w / 2, sz - frame_w / 2):
            frame.box((t, sy - 2 * t, frame_w), matrix=trs((x, 0, z)), mat=wood, bevel=0.006, segments=1)
    if not carry and sx > 0.5:
        import math
        diag = math.hypot(sx - 2 * frame_w, sz - 2 * frame_w)
        ang = math.degrees(math.atan2(sz - 2 * frame_w, sx - 2 * frame_w))
        for sgn_y in (-1, 1):
            frame.box((diag - 0.02, t * 0.9, frame_w * 0.8), matrix=trs((0, sgn_y * (sy / 2 - t / 2), sz / 2), (0, -ang, 0)),
                      mat=wood, bevel=0.005, segments=1)
    # Steel corner brackets + screws
    b = min(0.09, 0.14 * min(sx, sy, sz))
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            for z in (0.0, sz):
                zz = z + (b / 2 if z == 0 else -b / 2)
                cx, cy = sx_ * (sx / 2 + 0.002), sy_ * (sy / 2 + 0.002)
                detail.box((0.004, b, b), matrix=trs((cx, sy_ * (sy / 2 - b / 2), zz)), mat=metal, bevel=0.0015, segments=1)
                detail.box((b, 0.004, b), matrix=trs((sx_ * (sx / 2 - b / 2), cy, zz)), mat=metal, bevel=0.0015, segments=1)
                for d in (0.28 * b, 0.67 * b):
                    detail.cylinder(0.006, 0.004, segments=6,
                                    matrix=trs((cx + sx_ * 0.002, sy_ * (sy / 2 - d), zz), (0, 90, 0)), mat="steel")
    if carry:
        # Hand-hold blocks on the sides show where the worker grips the crate.
        for sgn_x in (-1, 1):
            frame.box((0.03, 0.16, 0.035), matrix=trs((sgn_x * (sx / 2 + 0.012), 0, sz * 0.56)), mat=wood, bevel=0.008,
                      segments=2)
    ctx.col_box((0, 0, sz / 2), (sx, sy, sz))
