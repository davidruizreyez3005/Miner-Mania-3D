"""Collision proxy generation.

Collision is built from generator-declared primitives (boxes, cylinders,
capsules, convex hulls) - never a copy of the render mesh. Objects are named
with Godot's ``-convcolonly`` import hint so importing the collision GLB yields
StaticBody3D + ConvexPolygonShape3D nodes directly.
"""

import math

import bmesh
import bpy
from mathutils import Vector

from core import scene as scn
from core.errors import PipelineError

SUFFIX = "-convcolonly"


def _box_verts(size):
    sx, sy, sz = (s / 2.0 for s in size)
    return [Vector((x, y, z)) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]


def _cyl_verts(radius, height, segments):
    out = []
    for k in range(segments):
        a = 2 * math.pi * k / segments
        for z in (-height / 2, height / 2):
            out.append(Vector((radius * math.cos(a), radius * math.sin(a), z)))
    return out


def _capsule_verts(radius, height, segments=10, rings=3):
    out = []
    cyl = max(0.0, height - 2 * radius)
    for k in range(segments):
        a = 2 * math.pi * k / segments
        for r in range(rings + 1):
            phi = (math.pi / 2) * r / rings
            rr = radius * math.cos(phi)
            dz = radius * math.sin(phi)
            out.append(Vector((rr * math.cos(a), rr * math.sin(a), radius + cyl + dz)))
            out.append(Vector((rr * math.cos(a), rr * math.sin(a), radius - dz)))
    return out


def hull_object(name, points):
    bm = bmesh.new()
    for p in points:
        bm.verts.new(p)
    if len(bm.verts) < 4:
        bm.free()
        raise PipelineError(f"collision hull {name} needs at least 4 points")
    res = bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
    # Remove interior / unused vertices reported by the hull operator.
    unused = [v for v in res.get("geom_interior", []) if isinstance(v, bmesh.types.BMVert)]
    unused += [v for v in res.get("geom_unused", []) if isinstance(v, bmesh.types.BMVert)]
    if unused:
        bmesh.ops.delete(bm, geom=list(set(unused)), context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    scn.link(obj)
    obj["mm_kind"] = "collision"
    return obj


def build(ctx):
    """Turn ctx.collision specs into convex mesh objects."""
    objs = []
    for i, spec in enumerate(ctx.collision):
        name = f"{ctx.name}_col_{i:02d}{SUFFIX}"
        if spec.kind == "box":
            pts = [spec.matrix @ v for v in _box_verts(spec.size)]
        elif spec.kind == "cylinder":
            pts = [spec.matrix @ v for v in _cyl_verts(spec.radius, spec.height, spec.segments)]
        elif spec.kind == "capsule":
            pts = [spec.matrix @ v for v in _capsule_verts(spec.radius, spec.height)]
        elif spec.kind == "hull":
            pts = [Vector(p) for p in spec.points]
        else:
            raise PipelineError(f"unknown collision kind {spec.kind}")
        obj = hull_object(name, pts)
        obj["mm_col_kind"] = spec.kind
        objs.append(obj)
    return objs


def validate(ctx, objs, render_lo, render_hi):
    """Closed, convex, bounded, reasonably simple collision."""
    from core.errors import ValidationIssue
    ccfg = ctx.cfg["collision"]
    issues = []
    if ctx.defn.collision != "none" and not objs:
        issues.append(ValidationIssue("error", "COLLISION_MISSING", "asset requires collision but none was generated"))
        return issues
    if len(objs) > ccfg["max_hulls"]:
        issues.append(ValidationIssue("error", "COLLISION_TOO_MANY_HULLS", f"{len(objs)} hulls > {ccfg['max_hulls']}"))
    total_tris = 0
    tol = ccfg["bounds_tolerance_m"]
    eps = ccfg["convexity_epsilon_m"]
    for o in objs:
        me = o.data
        nverts = len(me.vertices)
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        total_tris += tris
        if nverts > ccfg["max_hull_vertices"]:
            issues.append(ValidationIssue("error", "COLLISION_HULL_COMPLEX", f"{o.name}: {nverts} vertices"))
        # Closed: every edge shared by exactly two faces.
        bm = bmesh.new()
        bm.from_mesh(me)
        open_edges = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        bm.free()
        if open_edges:
            issues.append(ValidationIssue("error", "COLLISION_NOT_CLOSED", f"{o.name}: {open_edges} open edges"))
        # Convex: all vertices behind every face plane.
        worst = 0.0
        co = [v.co for v in me.vertices]
        for p in me.polygons:
            n = p.normal
            c = p.center
            for v in co:
                d = n.dot(v - c)
                if d > worst:
                    worst = d
        if worst > eps:
            issues.append(ValidationIssue("error", "COLLISION_NOT_CONVEX", f"{o.name}: {worst * 1000:.1f} mm outside"))
        if o.matrix_world != o.matrix_world.Identity(4):
            issues.append(ValidationIssue("error", "COLLISION_TRANSFORM", f"{o.name}: collision must have identity transform"))
        # Character capsules are standard gameplay controllers (config
        # collision.character_capsule), not fitted shells: only their height
        # must stay within the body; a slim body may be narrower than them.
        axes = (2,) if o.get("mm_col_kind") == "capsule" else (0, 1, 2)
        for v in co:
            if any(v[i] < render_lo[i] - tol or v[i] > render_hi[i] + tol for i in axes):
                issues.append(ValidationIssue("error", "COLLISION_OUT_OF_BOUNDS",
                                              f"{o.name}: vertex {tuple(round(x, 3) for x in v)} outside render bounds"))
                break
    if total_tris > ccfg["max_total_triangles"]:
        issues.append(ValidationIssue("error", "COLLISION_TOO_COMPLEX", f"{total_tris} collision triangles"))
    return issues
