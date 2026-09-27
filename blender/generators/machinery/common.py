"""Interaction stations shared by every machine.

A station is defined by where the worker stands (socket position) and which
way it faces (yaw, degrees about +Z; 0 = the worker faces -Y). The machine
geometry is placed from the animation contract's interaction points, so the
worker's Operate / Repair / Load clips put the hands exactly on the levers,
bolt or load surface when Godot parents the worker to the socket.

Socket convention (documented in docs/asset_pipeline.md): place the worker's
root at the socket transform; the worker's model front (+Z in Godot, -Y in
Blender) then faces the controls.
"""

import math

from mathutils import Matrix, Vector

from core import config
from utilities.meshkit import trs

from .. import kit


def points():
    return config.animation_spec()["interaction_points"]


def station_frame(pos, yaw):
    return Matrix.Translation(Vector(pos)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")


def operate_station(ctx, g, pos, yaw, name="operate", body_mat="paint_worn:dark_steel", knob_mat="plastic:signal_red"):
    """Lever console whose two knobs sit on the Operate clip's hand targets."""
    f = station_frame(pos, yaw)
    ip = points()
    pivot_z = ip["operate_lever_pivot_height"]
    knobs = [Vector(k) for k in ip["operate_levers"]]
    depth_y = knobs[0].y                                   # knobs are this far in front of the worker
    # Console body under the lever pivots.
    g.box((0.62, 0.3, pivot_z), matrix=f @ trs((0.0, depth_y - 0.06, pivot_z / 2)), mat=body_mat, bevel=0.012,
          segments=1)
    g.box((0.66, 0.34, 0.04), matrix=f @ trs((0.0, depth_y - 0.06, pivot_z + 0.02)), mat=kit.DARK, bevel=0.006,
          segments=1)
    for k in knobs:
        base = f @ Vector((k.x, k.y, pivot_z + 0.03))
        top = f @ k
        kit.beam(g, base, top, 0.022, 0.022, kit.CHROME, profile="tube")
        g.sphere(0.034, segments=12, rings=6, matrix=trs(top), mat=knob_mat)
        g.cylinder(0.04, 0.02, segments=12, matrix=trs(base), mat="rubber")
    # Indicator strip facing the operator.
    for i, col in enumerate(("emit:emissive_green", "emit:emissive_amber", "emit:emissive_red")):
        p = f @ Vector((-0.14 + 0.14 * i, depth_y + 0.092, pivot_z - 0.1))
        g.cylinder(0.018, 0.012, segments=10, matrix=kit.axis_frame(p, f.to_3x3() @ Vector((0, 1, 0))), mat=col)
    ctx.socket(name, tuple(pos), (0.0, 0.0, yaw))
    return f


def repair_spot(ctx, g, pos, yaw, name="repair", mat="steel_dark"):
    """Service plate with the bolt the Repair clip's wrench turns."""
    f = station_frame(pos, yaw)
    bolt = f @ Vector(points()["repair_bolt"])
    n = f.to_3x3() @ Vector((0.0, 1.0, 0.0))               # plate faces the kneeling worker
    g.box((0.26, 0.03, 0.2), matrix=kit.axis_frame(bolt - n * 0.03, n) @ trs(rot=(90, 0, 0)), mat=mat, bevel=0.004)
    g.cylinder(0.018, 0.03, segments=6, matrix=kit.axis_frame(bolt - n * 0.01, n), mat=kit.BOLT)
    ctx.socket(name, tuple(pos), (0.0, 0.0, yaw))
    return bolt


def load_socket(ctx, pos, yaw, name="load"):
    """Worker spot for Load/Unload: the box lands on the contract's load_surface."""
    ctx.socket(name, tuple(pos), (0.0, 0.0, yaw))
    return station_frame(pos, yaw) @ Vector(points()["load_surface"])


def yaw_facing(direction):
    """Yaw (degrees) that turns the worker's front (-Y) toward ``direction``."""
    d = Vector((direction[0], direction[1], 0.0)).normalized()
    return math.degrees(math.atan2(d.x, -d.y))


def _worker_for(target, local, yaw):
    w = Vector(target) - (Matrix.Rotation(math.radians(yaw), 3, "Z") @ Vector((local[0], local[1], 0.0)))
    w.z = 0.0
    return w


def repair_at(ctx, g, face_point, normal, name="repair", mat="steel_dark"):
    """Repair station on a machine face: ``face_point`` lies on the surface,
    ``normal`` points out of it (horizontal). The kneeling worker faces the
    face and the wrench turns the bolt 4.5 cm proud of it at the clip's height."""
    n = Vector((normal[0], normal[1], 0.0)).normalized()
    yaw = yaw_facing(-n)
    ip = points()["repair_bolt"]
    bolt = Vector(face_point) + n * 0.045
    bolt.z = ip[2]
    worker = _worker_for(bolt, ip, yaw)
    repair_spot(ctx, g, tuple(worker), yaw, name=name, mat=mat)
    return worker


def interact_at(ctx, g, face_point, normal, name="interact", mat="plastic:plastic_black",
                button_mat="emit:emissive_green"):
    """Push-button plate for the Interact clip on a machine face."""
    n = Vector((normal[0], normal[1], 0.0)).normalized()
    yaw = yaw_facing(-n)
    ip = points()["button"]
    btn = Vector(face_point) + n * 0.03
    btn.z = ip[2]
    worker = _worker_for(btn, ip, yaw)
    g.box((0.16, 0.03, 0.2), matrix=kit.axis_frame(btn - n * 0.02, n) @ trs(rot=(90, 0, 0)), mat=mat, bevel=0.006)
    g.cylinder(0.028, 0.03, segments=16, matrix=kit.axis_frame(btn, n), mat=button_mat)
    ctx.socket(name, tuple(worker), (0.0, 0.0, yaw))
    return worker


def operate_facing(ctx, g, stand, facing, name="operate", **kw):
    """Lever console for a worker standing at ``stand`` and facing ``facing``."""
    return operate_station(ctx, g, stand, yaw_facing(facing), name=name, **kw)
