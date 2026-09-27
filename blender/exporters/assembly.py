"""Assemble baked parts into the final export hierarchy.

Rules (same for LOD0 and every LOD level):
* parts with ``mm_attach_bone`` -> one rigid object per attachment bone,
  parented to that bone (Godot: BoneAttachment3D).
* every other part -> one mesh. Rigged assets get a single skinned mesh
  ``<name>_mesh`` under the armature ``<name>``; static assets get one mesh
  ``<name>`` that is also the scene root.
* sockets -> empties ``socket_<name>`` under the root (or their bone).
"""

import bpy
from mathutils import Matrix

from core import scene as scn
from core.errors import PipelineError
from rigging import armature_utils


def duplicate(objs, suffix):
    out = []
    for o in objs:
        d = o.copy()
        d.data = o.data.copy()
        d.name = f"{o.name}{suffix}"
        scn.link(d)
        out.append(d)
    return out


def join(objs, name):
    objs = [o for o in objs if o.type == "MESH"]
    if not objs:
        raise PipelineError(f"join('{name}') received no meshes")
    if len(objs) > 1:
        scn.select_only(objs, objs[0])
        r = bpy.ops.object.join()
        if "FINISHED" not in r:
            raise PipelineError(f"join failed for {name}: {r}")
    obj = objs[0]
    obj.name = name
    obj.data.name = name
    return obj


def _apply_transform(obj):
    if obj.matrix_world != Matrix.Identity(4):
        par = obj.parent
        ptype = obj.parent_type
        obj.parent = None
        scn.apply_object_transform(obj)
        if par is not None and ptype == "OBJECT":
            obj.parent = par


def assemble(ctx, parts, suffix=""):
    """Return (root, meshes, attachments). ``suffix`` is '' for LOD0 or '_lod1'..."""
    arm = ctx.armature
    base = f"{ctx.name}{suffix}"
    attach_groups = {}
    main = []
    for p in parts:
        bone = p.get("mm_attach_bone")
        if bone and arm is not None:
            label = p.get("mm_attach_label", p.get("mm_part", bone))
            attach_groups.setdefault((bone, label), []).append(p)
        else:
            main.append(p)
    meshes = []
    attachments = []
    if arm is not None:
        if main:
            for p in main:
                if not any(m.type == "ARMATURE" for m in p.modifiers):
                    raise PipelineError(f"part {p.name} is not bound to the armature")
            mesh = join(main, f"{base}_mesh")
            armature_utils.bind(mesh, arm)
            meshes.append(mesh)
        for (bone, label), grp in sorted(attach_groups.items()):
            for g in grp:
                g.parent = None
                for m in list(g.modifiers):
                    if m.type == "ARMATURE":
                        g.modifiers.remove(m)
            obj = join(grp, f"{base}_{label}")
            _apply_transform(obj)
            armature_utils.attach_to_bone(obj, arm, bone)
            attachments.append(obj)
        root = arm
    else:
        if not main:
            raise PipelineError(f"{base}: no render geometry")
        for p in main:
            _apply_transform(p)
        root = join(main, base)
        meshes.append(root)
    return root, meshes, attachments


def add_sockets(ctx, root):
    out = []
    for s in ctx.sockets:
        e = scn.new_empty(f"socket_{s.name}", s.matrix, display="ARROWS", size=0.15)
        if s.bone and ctx.armature is not None:
            mw = e.matrix_world.copy()
            e.parent = ctx.armature
            e.parent_type = "BONE"
            e.parent_bone = s.bone
            e.matrix_world = mw
        else:
            mw = e.matrix_world.copy()
            e.parent = root
            e.matrix_world = mw
        e["mm_kind"] = "socket"
        out.append(e)
    return out
