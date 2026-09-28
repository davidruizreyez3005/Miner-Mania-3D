"""Reproducible MikkTSpace tangents for the glTF export and tangent-space bakes.

Blender 4.5 runs MikkTSpace (``Mesh.calc_tangents``, and Cycles' tangents for
tangent-space normal bakes) multi-threaded once a mesh has more than ~10k
triangles, and its per-vertex sums then depend on thread timing: the tangents
change by ~1e-7 on every call. The glTF exporter's 4-decimal rounding and the
8-bit normal maps turn that into a few differing values per build, so large
assets were not byte-reproducible. Smaller meshes are processed in one piece
and give the same result on every call.

A corner's MikkTSpace tangent depends only on the faces around its position
(corners are welded by position, normal and UV), so cutting a mesh between
connected components - merged across coincident positions - changes no
tangent. ``face_chunks`` groups whole components into chunks below the
threading size, and ``chunk_mesh`` copies one chunk with all its attributes
(custom normals and sharp edges included), so each chunk has exactly the
corner normals, UVs and tangents it had in the whole mesh.
"""

import bpy
import numpy as np

from core.errors import PipelineError

CHUNK_TRIS = 8000           # Blender threads MikkTSpace above ~10k triangles

# Generic attribute types chunk_mesh copies, with their foreach property.
_ATTR_PROP = {"FLOAT": "value", "INT": "value", "BOOLEAN": "value", "INT8": "value", "FLOAT2": "vector",
              "FLOAT_VECTOR": "vector", "FLOAT_COLOR": "color", "BYTE_COLOR": "color", "INT16_2D": "value",
              "INT32_2D": "value", "QUATERNION": "value"}
_ATTR_WIDTH = {"FLOAT2": 2, "FLOAT_VECTOR": 3, "FLOAT_COLOR": 4, "BYTE_COLOR": 4, "INT16_2D": 2, "INT32_2D": 2,
               "QUATERNION": 4}
_ATTR_DTYPE = {"INT": np.int32, "BOOLEAN": bool, "INT8": np.int8, "INT16_2D": np.int16, "INT32_2D": np.int32}


def _topology(me):
    start = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_start", start)
    total = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_total", total)
    corner_vert = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", corner_vert)
    return start, total, corner_vert


def triangle_count(me):
    total = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_total", total)
    return int((total - 2).sum())


def face_chunks(me, limit=CHUNK_TRIS):
    """Face index arrays (ascending) of whole components, at most ``limit`` triangles each."""
    start, total, corner_vert = _topology(me)
    if not len(start):
        return []
    tris = total - 2
    if int(tris.sum()) <= limit:
        return [np.arange(len(start))]
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    parent = list(range(len(me.vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # Coincident vertices belong together (+0.0 folds -0.0 into 0.0, as == does).
    _, first, inv = np.unique(co.reshape(-1, 3) + np.float32(0.0), axis=0, return_index=True, return_inverse=True)
    rep = first[inv.ravel()]
    for v in np.nonzero(rep != np.arange(len(rep)))[0].tolist():
        union(v, int(rep[v]))
    lead = np.repeat(corner_vert[start], total)            # first vertex of each corner's face
    for a, b in zip(corner_vert.tolist(), lead.tolist()):
        if a != b:
            union(a, b)
    comp = np.array([find(v) for v in corner_vert[start].tolist()], dtype=np.int64)
    _, order_idx, comp_idx = np.unique(comp, return_index=True, return_inverse=True)
    comp_tris = np.bincount(comp_idx, weights=tris).astype(np.int64)
    chunks, current, count = [], [], 0
    for c in np.argsort(order_idx, kind="stable").tolist():  # components in face order
        t = int(comp_tris[c])
        if t > limit:
            raise PipelineError(f"{me.name}: a connected surface of {t} triangles exceeds {limit}; its "
                                f"MikkTSpace tangents would not be reproducible (split the part)")
        if current and count + t > limit:
            chunks.append(current)
            current, count = [], 0
        current.append(c)
        count += t
    chunks.append(current)
    return [np.nonzero(np.isin(comp_idx, c))[0] for c in chunks]


def chunk_mesh(me, faces, name):
    """New mesh with the given faces of ``me``, copying every attribute
    (custom normals, sharp edges, UV maps, material indices, ...) and the
    material slots. Returns (mesh, corner indices of ``me`` in the new mesh's
    corner order)."""
    start, total, corner_vert = _topology(me)
    faces = np.asarray(faces, dtype=np.int64)
    sizes = total[faces]
    offsets = np.concatenate(([0], np.cumsum(sizes)[:-1]))
    corners = np.repeat(start[faces] - offsets, sizes) + np.arange(sizes.sum())
    verts, remap = np.unique(corner_vert[corners], return_inverse=True)
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)

    m = bpy.data.meshes.new(name)
    m.vertices.add(len(verts))
    m.vertices.foreach_set("co", co.reshape(-1, 3)[verts].ravel())
    m.loops.add(len(corners))
    m.loops.foreach_set("vertex_index", remap.astype(np.int32))
    m.polygons.add(len(faces))
    m.polygons.foreach_set("loop_start", offsets.astype(np.int32))
    m.update(calc_edges=True)
    for mat in me.materials:
        m.materials.append(mat)
    # Edges are rebuilt; map each back to the source edge with the same vertices.
    n = len(me.vertices)
    src = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", src)
    src = src.reshape(-1, 2)
    src_key = src.min(axis=1) * n + src.max(axis=1)
    dst = np.empty(len(m.edges) * 2, dtype=np.int64)
    m.edges.foreach_get("vertices", dst)
    dst = verts[dst.reshape(-1, 2)]
    dst_key = dst.min(axis=1) * n + dst.max(axis=1)
    order = np.argsort(src_key, kind="stable")
    edges = order[np.minimum(np.searchsorted(src_key[order], dst_key), len(order) - 1)]
    if not np.array_equal(src_key[edges], dst_key):
        raise PipelineError(f"{me.name}: chunk edges do not match the source edges")
    pick = {"POINT": verts, "EDGE": edges, "CORNER": corners, "FACE": faces}
    for a in me.attributes:
        if a.name.startswith(".") or a.name == "position" or a.domain not in pick:
            continue
        if a.data_type not in _ATTR_PROP:
            raise PipelineError(f"{me.name}: cannot copy attribute {a.name} of type {a.data_type}")
        prop, width = _ATTR_PROP[a.data_type], _ATTR_WIDTH.get(a.data_type, 1)
        buf = np.empty(len(a.data) * width, dtype=_ATTR_DTYPE.get(a.data_type, np.float32))
        a.data.foreach_get(prop, buf)
        out = m.attributes.get(a.name) or m.attributes.new(a.name, a.data_type, a.domain)
        out.data.foreach_set(prop, buf.reshape(len(a.data), width)[pick[a.domain]].ravel())
    for uv in me.uv_layers:
        m.uv_layers[uv.name].active = uv.active
        m.uv_layers[uv.name].active_render = uv.active_render
    m.update()
    return m, corners


def _calc(me, uv_name):
    me.calc_tangents(uvmap=uv_name)
    t = np.empty(len(me.loops) * 3, dtype=np.float32)
    me.loops.foreach_get("tangent", t)
    s = np.empty(len(me.loops), dtype=np.float32)
    me.loops.foreach_get("bitangent_sign", s)
    return t.reshape(-1, 3), s


def loop_tangents(me, uv_name, limit=CHUNK_TRIS):
    """Per-corner MikkTSpace tangents (N x 3) and bitangent signs (N) of
    ``me`` for UV map ``uv_name``, identical on every run."""
    chunks = face_chunks(me, limit)
    if len(chunks) <= 1:
        return _calc(me, uv_name)
    tangent = np.zeros((len(me.loops), 3), dtype=np.float32)
    sign = np.zeros(len(me.loops), dtype=np.float32)
    done = np.zeros(len(me.loops), dtype=bool)
    for i, faces in enumerate(chunks):
        m, corners = chunk_mesh(me, faces, f"__tangent_chunk_{i}")
        try:
            tangent[corners], sign[corners] = _calc(m, uv_name)
        finally:
            bpy.data.meshes.remove(m)
        done[corners] = True
    if not done.all():
        raise PipelineError(f"{me.name}: {int((~done).sum())} corners were not covered by tangent chunks")
    return tangent, sign
