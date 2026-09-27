"""Independent GLB inspection (pure Python + numpy, no bpy).

Blender reporting a successful export proves nothing about the file. This
module re-reads the GLB bytes and validates structure, references, accessor
data, skins, animations (by actually evaluating them), images, bounds and
naming. It runs inside Blender right after export and again standalone in CI
(tools/validate_assets.py) against the manifest.
"""

import json
import math
import re
import struct

import numpy as np

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942

COMPONENT = {5120: (np.int8, 1), 5121: (np.uint8, 1), 5122: (np.int16, 2), 5123: (np.uint16, 2),
             5125: (np.uint32, 4), 5126: (np.float32, 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
ALLOWED_EXTENSIONS = {"KHR_materials_emissive_strength", "KHR_materials_specular", "KHR_materials_ior",
                      "KHR_texture_transform"}
NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
BLENDER_DUP_RE = re.compile(r"\.\d{3}$")
UUID_RE = re.compile(r"[0-9a-fA-F]{16,}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-")


class GLBError(Exception):
    pass


# ------------------------------------------------------------------ math utils

def quat_to_mat(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    return np.array([
        [1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
        [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
        [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)],
    ])


def trs_matrix(t, r, s):
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(r) * np.asarray(s)[None, :]
    m[:3, 3] = t
    return m


def slerp(q0, q1, a):
    q0 = np.asarray(q0, dtype=np.float64)
    q1 = np.asarray(q1, dtype=np.float64)
    d = float(np.dot(q0, q1))
    if d < 0.0:
        q1 = -q1
        d = -d
    if d > 0.9995:
        q = q0 + a * (q1 - q0)
        return q / np.linalg.norm(q)
    th = math.acos(min(1.0, d))
    return (math.sin((1 - a) * th) * q0 + math.sin(a * th) * q1) / math.sin(th)


def quat_angle_deg(q0, q1):
    d = abs(float(np.dot(np.asarray(q0) / np.linalg.norm(q0), np.asarray(q1) / np.linalg.norm(q1))))
    return math.degrees(2.0 * math.acos(min(1.0, d)))


# ------------------------------------------------------------------ container

class GLB:
    def __init__(self, data, name="<memory>"):
        self.name = name
        self.size = len(data)
        if len(data) < 20:
            raise GLBError("file too small to be a GLB")
        magic, version, length = struct.unpack_from("<III", data, 0)
        if magic != GLB_MAGIC:
            raise GLBError("bad magic (not a binary glTF)")
        if version != 2:
            raise GLBError(f"unsupported GLB version {version}")
        if length != len(data):
            raise GLBError(f"header length {length} != file size {len(data)} (truncated or padded file)")
        off = 12
        self.json = None
        self.bin = b""
        chunk_index = 0
        while off < length:
            if off + 8 > length:
                raise GLBError("truncated chunk header")
            clen, ctype = struct.unpack_from("<II", data, off)
            off += 8
            if off + clen > length:
                raise GLBError("chunk extends past end of file")
            chunk = data[off:off + clen]
            if chunk_index == 0:
                if ctype != CHUNK_JSON:
                    raise GLBError("first chunk is not JSON")
                try:
                    self.json = json.loads(chunk.decode("utf-8").rstrip(" \x00"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise GLBError(f"invalid JSON chunk: {exc}") from exc
            elif ctype == CHUNK_BIN:
                self.bin = chunk
            off += clen
            if clen % 4:
                raise GLBError("chunk not 4-byte aligned")
            chunk_index += 1
        if self.json is None:
            raise GLBError("missing JSON chunk")
        self._acc_cache = {}

    @classmethod
    def load(cls, path):
        with open(path, "rb") as fh:
            return cls(fh.read(), path)

    def get(self, key):
        return self.json.get(key, [])

    # -- data access -----------------------------------------------------------
    def buffer_view_bytes(self, idx):
        bv = self.get("bufferViews")[idx]
        if bv.get("buffer", 0) != 0:
            raise GLBError("external buffers are not allowed in GLB assets")
        start = bv.get("byteOffset", 0)
        end = start + bv["byteLength"]
        if end > len(self.bin):
            raise GLBError(f"bufferView {idx} exceeds BIN chunk ({end} > {len(self.bin)})")
        return self.bin[start:end], bv.get("byteStride")

    def accessor(self, idx):
        if idx in self._acc_cache:
            return self._acc_cache[idx]
        acc = self.get("accessors")[idx]
        if "sparse" in acc:
            raise GLBError(f"accessor {idx}: sparse accessors are not expected in game assets")
        dtype, csize = COMPONENT[acc["componentType"]]
        nc = NCOMP[acc["type"]]
        count = acc["count"]
        if "bufferView" not in acc:
            arr = np.zeros((count, nc), dtype=np.float64)
        else:
            raw, stride = self.buffer_view_bytes(acc["bufferView"])
            base = acc.get("byteOffset", 0)
            elem = csize * nc
            stride = stride or elem
            need = base + stride * (count - 1) + elem if count else 0
            if need > len(raw):
                raise GLBError(f"accessor {idx} reads past its bufferView ({need} > {len(raw)})")
            if stride == elem:
                arr = np.frombuffer(raw, dtype=dtype, count=count * nc, offset=base).reshape(count, nc)
            else:
                rows = [np.frombuffer(raw, dtype=dtype, count=nc, offset=base + i * stride) for i in range(count)]
                arr = np.stack(rows) if rows else np.zeros((0, nc), dtype=dtype)
            if acc.get("normalized"):
                info = np.iinfo(dtype)
                arr = np.maximum(arr.astype(np.float64) / info.max, -1.0)
        arr = arr.astype(np.float64) if arr.dtype == np.float32 else arr
        self._acc_cache[idx] = arr
        return arr

    # -- scene graph -----------------------------------------------------------
    def parents(self):
        par = {}
        for i, n in enumerate(self.get("nodes")):
            for c in n.get("children", []):
                if c in par:
                    raise GLBError(f"node {c} has multiple parents")
                par[c] = i
        return par

    def node_trs(self, i):
        n = self.get("nodes")[i]
        if "matrix" in n:
            m = np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
            t = m[:3, 3].copy()
            sx, sy, sz = (np.linalg.norm(m[:3, k]) for k in range(3))
            rot = m[:3, :3] / np.array([sx, sy, sz])[None, :]
            q = _mat_to_quat(rot)
            return t, q, np.array([sx, sy, sz])
        return (np.array(n.get("translation", [0, 0, 0]), dtype=np.float64),
                np.array(n.get("rotation", [0, 0, 0, 1]), dtype=np.float64),
                np.array(n.get("scale", [1, 1, 1]), dtype=np.float64))

    def world_matrices(self, overrides=None):
        nodes = self.get("nodes")
        par = self.parents()
        local = []
        for i in range(len(nodes)):
            t, r, s = self.node_trs(i)
            if overrides and i in overrides:
                ot, orr, os_ = overrides[i]
                t = ot if ot is not None else t
                r = orr if orr is not None else r
                s = os_ if os_ is not None else s
            local.append(trs_matrix(t, r, s))
        world = [None] * len(nodes)

        def resolve(i, depth=0):
            if depth > 256:
                raise GLBError("node hierarchy cycle detected")
            if world[i] is None:
                p = par.get(i)
                world[i] = local[i] if p is None else resolve(p, depth + 1) @ local[i]
            return world[i]

        for i in range(len(nodes)):
            resolve(i)
        return world

    def scene_roots(self):
        scenes = self.get("scenes")
        if not scenes:
            raise GLBError("no scenes")
        idx = self.json.get("scene", 0)
        return scenes[idx].get("nodes", [])

    # -- meshes ----------------------------------------------------------------
    def primitive_triangles(self, prim):
        mode = prim.get("mode", 4)
        if mode != 4:
            raise GLBError(f"primitive mode {mode} is not TRIANGLES")
        if "indices" in prim:
            return self.get("accessors")[prim["indices"]]["count"] // 3
        return self.get("accessors")[prim["attributes"]["POSITION"]]["count"] // 3

    def mesh_triangles(self, mesh_idx):
        return sum(self.primitive_triangles(p) for p in self.get("meshes")[mesh_idx]["primitives"])

    # -- animation -------------------------------------------------------------
    def channel_data(self, anim):
        out = []
        for ch in anim.get("channels", []):
            smp = anim["samplers"][ch["sampler"]]
            times = self.accessor(smp["input"])[:, 0]
            vals = self.accessor(smp["output"])
            out.append((ch["target"].get("node"), ch["target"]["path"], smp.get("interpolation", "LINEAR"),
                        times, vals))
        return out

    def sample_channels(self, channels, t):
        ov = {}
        for node, path, interp, times, vals in channels:
            if node is None or path == "weights":
                continue
            cubic = interp == "CUBICSPLINE"
            v = _sample(times, vals, t, interp, path == "rotation", cubic)
            cur = ov.setdefault(node, [None, None, None])
            cur[{"translation": 0, "rotation": 1, "scale": 2}[path]] = v
        return ov


def _mat_to_quat(m):
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        return np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s])
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        return np.array([0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s])
    if m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        return np.array([(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s])
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
    return np.array([(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s])


def _sample(times, vals, t, interp, is_rot, cubic):
    if cubic:
        vals = vals.reshape(len(times), 3, -1)[:, 1, :]
    if t <= times[0]:
        return vals[0].copy()
    if t >= times[-1]:
        return vals[-1].copy()
    k = int(np.searchsorted(times, t, side="right")) - 1
    k = max(0, min(k, len(times) - 2))
    if interp == "STEP":
        return vals[k].copy()
    t0, t1 = times[k], times[k + 1]
    a = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
    if is_rot:
        return slerp(vals[k], vals[k + 1], a)
    return vals[k] * (1 - a) + vals[k + 1] * a


# ------------------------------------------------------------------ image headers

def image_info(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if data[12:16] != b"IHDR":
            raise GLBError("PNG without IHDR")
        w, h = struct.unpack(">II", data[16:24])
        return "image/png", w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "image/jpeg", w, h
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
        raise GLBError("JPEG without SOF marker")
    raise GLBError("unknown image format (expected PNG or JPEG)")


# ------------------------------------------------------------------ inspection

class Report:
    def __init__(self, path):
        self.path = path
        self.errors = []
        self.warnings = []
        self.stats = {}

    def err(self, code, msg):
        self.errors.append({"code": code, "message": msg})

    def warn(self, code, msg):
        self.warnings.append({"code": code, "message": msg})

    @property
    def ok(self):
        return not self.errors

    def as_dict(self):
        return {"path": self.path, "ok": self.ok, "errors": self.errors, "warnings": self.warnings,
                "stats": self.stats}


def _finite(arr):
    return bool(np.all(np.isfinite(arr))) if arr.dtype.kind == "f" else True


def inspect(path_or_glb, expect=None):
    """Inspect a GLB. ``expect`` keys (all optional):

    kind: 'static'|'skinned'; animations: [names]; loop: {name: bool};
    skeleton: [bone names]; skeleton_parents: {bone: parent};
    triangles: [min, max]; max_file_mb; dims_min/dims_max (Blender xyz meters);
    origin: 'base'|'grip'|'center'|'embedded'|'tile'|'ceiling'|'any'; max_texture; max_materials;
    required_nodes: [names]; clips: {name: {...clip spec...}}; grips: {...};
    anim_cfg: pipeline animation thresholds; collision: True for collision files.
    """
    expect = expect or {}
    rep = Report(getattr(path_or_glb, "name", path_or_glb))
    try:
        glb = path_or_glb if isinstance(path_or_glb, GLB) else GLB.load(path_or_glb)
    except (OSError, GLBError) as exc:
        rep.err("GLB_CORRUPT", str(exc))
        return rep
    try:
        _inspect(glb, expect, rep)
    except GLBError as exc:
        rep.err("GLB_INVALID", str(exc))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        rep.err("GLB_MALFORMED", f"{type(exc).__name__}: {exc}")
    return rep


def _check_refs(js, rep, expect=None):
    expect = expect or {}
    counts = {k: len(js.get(k, [])) for k in ("nodes", "meshes", "accessors", "bufferViews", "materials",
                                             "textures", "images", "samplers", "skins", "animations")}

    def ref(kind, idx, where):
        if not isinstance(idx, int) or idx < 0 or idx >= counts[kind]:
            rep.err("BAD_REFERENCE", f"{where} references {kind}[{idx}] (have {counts[kind]})")
            return False
        return True

    for i, n in enumerate(js.get("nodes", [])):
        for c in n.get("children", []):
            ref("nodes", c, f"node {i} child")
        if "mesh" in n:
            ref("meshes", n["mesh"], f"node {i}")
        if "skin" in n:
            ref("skins", n["skin"], f"node {i}")
        if "camera" in n:
            rep.err("FORBIDDEN_CAMERA", f"node {i} ({n.get('name')}) carries a camera")
    for i, m in enumerate(js.get("meshes", [])):
        for j, p in enumerate(m.get("primitives", [])):
            for a, acc in p.get("attributes", {}).items():
                ref("accessors", acc, f"mesh {i} prim {j} {a}")
            if "indices" in p:
                ref("accessors", p["indices"], f"mesh {i} prim {j} indices")
            if "material" in p:
                ref("materials", p["material"], f"mesh {i} prim {j}")
            elif not expect.get("allow_no_material"):
                rep.err("MISSING_MATERIAL", f"mesh {i} ({m.get('name')}) primitive {j} has no material")
    for i, a in enumerate(js.get("accessors", [])):
        if "bufferView" in a:
            ref("bufferViews", a["bufferView"], f"accessor {i}")
    for i, t in enumerate(js.get("textures", [])):
        if "source" in t:
            ref("images", t["source"], f"texture {i}")
        else:
            rep.err("TEXTURE_NO_SOURCE", f"texture {i} has no image source")
        if "sampler" in t:
            ref("samplers", t["sampler"], f"texture {i}")
    for i, img in enumerate(js.get("images", [])):
        if "uri" in img:
            rep.err("EXTERNAL_IMAGE", f"image {i} uses an external URI; GLB assets must embed images")
        elif "bufferView" in img:
            ref("bufferViews", img["bufferView"], f"image {i}")
    for i, mat in enumerate(js.get("materials", [])):
        pbr = mat.get("pbrMetallicRoughness", {})
        for key in ("baseColorTexture", "metallicRoughnessTexture"):
            if key in pbr:
                ref("textures", pbr[key]["index"], f"material {i} {key}")
        for key in ("normalTexture", "occlusionTexture", "emissiveTexture"):
            if key in mat:
                ref("textures", mat[key]["index"], f"material {i} {key}")
    for i, s in enumerate(js.get("skins", [])):
        for j in s.get("joints", []):
            ref("nodes", j, f"skin {i} joint")
        if "inverseBindMatrices" in s:
            ref("accessors", s["inverseBindMatrices"], f"skin {i} IBM")
    for i, an in enumerate(js.get("animations", [])):
        for c in an.get("channels", []):
            if c.get("sampler", -1) >= len(an.get("samplers", [])):
                rep.err("BAD_REFERENCE", f"animation {i} channel references missing sampler")
            if "node" in c.get("target", {}):
                ref("nodes", c["target"]["node"], f"animation {i} channel")
        for s in an.get("samplers", []):
            ref("accessors", s["input"], f"animation {i} sampler input")
            ref("accessors", s["output"], f"animation {i} sampler output")


def _inspect(glb, expect, rep):
    js = glb.json
    asset = js.get("asset", {})
    if asset.get("version") != "2.0":
        rep.err("GLTF_VERSION", f"asset.version is {asset.get('version')!r}, expected '2.0'")
    rep.stats["generator"] = asset.get("generator")
    rep.stats["file_size"] = glb.size
    used = set(js.get("extensionsUsed", []))
    if js.get("extensionsRequired"):
        rep.err("REQUIRED_EXTENSION", f"extensionsRequired must be empty: {js['extensionsRequired']}")
    bad = used - ALLOWED_EXTENSIONS
    if bad:
        rep.err("UNSUPPORTED_EXTENSION", f"unsupported glTF extensions for Godot: {sorted(bad)}")
    if "KHR_lights_punctual" in used or js.get("cameras"):
        rep.err("FORBIDDEN_OBJECT", "lights or cameras exported")
    _check_refs(js, rep, expect)
    if rep.errors:
        return

    # -- accessors: finiteness and declared bounds
    for i, acc in enumerate(js.get("accessors", [])):
        arr = glb.accessor(i)
        if not _finite(arr):
            rep.err("NAN_OR_INF", f"accessor {i} contains NaN/Inf")
    nodes = js.get("nodes", [])

    # -- naming
    names = []
    for i, n in enumerate(nodes):
        nm = n.get("name")
        if not nm:
            rep.err("UNNAMED_NODE", f"node {i} has no name")
            continue
        names.append(nm)
        if not NAME_RE.match(nm):
            rep.err("BAD_NODE_NAME", f"node name {nm!r} contains unsupported characters")
        if BLENDER_DUP_RE.search(nm):
            rep.err("BLENDER_DUPLICATE_NAME", f"node name {nm!r} has a Blender duplicate suffix")
        if UUID_RE.search(nm):
            rep.err("RANDOM_NAME", f"node name {nm!r} looks like a random identifier")
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        rep.err("DUPLICATE_NODE_NAMES", f"duplicate node names: {dup[:10]}")
    for key in ("materials", "meshes", "animations"):
        for i, item in enumerate(js.get(key, [])):
            nm = item.get("name", "")
            if nm and (BLENDER_DUP_RE.search(nm) or UUID_RE.search(nm)):
                rep.err("BAD_RESOURCE_NAME", f"{key}[{i}] name {nm!r} is not clean")

    # -- meshes & triangles
    world = glb.world_matrices()
    tri_total = 0
    skinned_nodes = []
    render_nodes = []
    for i, n in enumerate(nodes):
        if "mesh" not in n:
            continue
        tris = glb.mesh_triangles(n["mesh"])
        tri_total += tris
        render_nodes.append(i)
        if "skin" in n:
            skinned_nodes.append(i)
        for j, p in enumerate(js["meshes"][n["mesh"]]["primitives"]):
            attrs = p["attributes"]
            if "POSITION" not in attrs:
                rep.err("NO_POSITION", f"mesh {n['mesh']} prim {j} has no POSITION")
                continue
            pacc = js["accessors"][attrs["POSITION"]]
            if "min" not in pacc or "max" not in pacc:
                rep.err("POSITION_BOUNDS", f"POSITION accessor {attrs['POSITION']} lacks min/max")
            if "NORMAL" not in attrs:
                rep.err("NO_NORMALS", f"mesh {n['mesh']} prim {j} has no normals")
            else:
                nrm = glb.accessor(attrs["NORMAL"])
                if len(nrm) and np.abs(np.linalg.norm(nrm, axis=1) - 1.0).max() > 0.01:
                    rep.err("NORMAL_NOT_UNIT", f"mesh {n['mesh']} prim {j} has non-unit normals")
            mat = js["materials"][p["material"]] if "material" in p else {}
            textured = "baseColorTexture" in mat.get("pbrMetallicRoughness", {}) or "normalTexture" in mat
            if "normalTexture" in mat and "TANGENT" not in attrs:
                rep.err("NO_TANGENTS", f"normal-mapped primitive (mesh {n['mesh']} prim {j}) has no TANGENT")
            if "TANGENT" in attrs:
                tan = glb.accessor(attrs["TANGENT"])
                bad = np.abs(np.linalg.norm(tan[:, :3], axis=1) - 1.0) > 0.01
                if bad.any() or not np.all(np.isin(np.round(tan[:, 3]), (-1.0, 1.0))):
                    rep.err("TANGENT_INVALID", f"mesh {n['mesh']} prim {j}: {int(bad.sum())} non-unit tangents "
                                               f"or invalid handedness")
            if textured and "TEXCOORD_0" not in attrs:
                rep.err("NO_UV", f"textured primitive (mesh {n['mesh']} prim {j}) has no TEXCOORD_0")
            if textured and "TEXCOORD_0" in attrs:
                uv = glb.accessor(attrs["TEXCOORD_0"])
                if uv.size and (uv.min() < -0.01 or uv.max() > 1.01):
                    rep.err("UV_RANGE", f"UVs outside 0..1 on mesh {n['mesh']} prim {j}")
            if "indices" in p:
                idx = glb.accessor(p["indices"])
                vcount = pacc["count"]
                if idx.size and int(idx.max()) >= vcount:
                    rep.err("INDEX_RANGE", f"mesh {n['mesh']} prim {j} index {int(idx.max())} >= {vcount}")
            if "skin" in n:
                if "JOINTS_0" not in attrs or "WEIGHTS_0" not in attrs:
                    rep.err("SKIN_ATTRS", f"skinned mesh {n['mesh']} prim {j} lacks JOINTS_0/WEIGHTS_0")
                else:
                    w = glb.accessor(attrs["WEIGHTS_0"])
                    jn = glb.accessor(attrs["JOINTS_0"])
                    sums = w.sum(axis=1)
                    if w.size and (np.abs(sums - 1.0).max() > 0.01 or w.min() < -1e-6):
                        rep.err("WEIGHTS_NOT_NORMALIZED",
                                f"mesh {n['mesh']} prim {j} weight sums in [{sums.min():.4f}, {sums.max():.4f}]")
                    nj = len(js["skins"][n["skin"]]["joints"])
                    if jn.size and int(jn.max()) >= nj:
                        rep.err("JOINT_RANGE", f"mesh {n['mesh']} prim {j} joint index {int(jn.max())} >= {nj}")
                    if "JOINTS_1" in attrs:
                        rep.err("TOO_MANY_INFLUENCES", f"mesh {n['mesh']} uses more than 4 influences")
    rep.stats["triangles"] = tri_total
    rep.stats["materials"] = len(js.get("materials", []))
    rep.stats["textures"] = len(js.get("textures", []))
    rep.stats["meshes"] = len(js.get("meshes", []))
    rep.stats["nodes"] = len(nodes)
    rep.stats["node_names"] = names
    if not render_nodes and not expect.get("allow_no_mesh"):
        rep.err("NO_MESH", "GLB contains no mesh nodes")

    # -- materials/images
    max_tex = 0
    for i, img in enumerate(js.get("images", [])):
        raw, _ = glb.buffer_view_bytes(img["bufferView"])
        try:
            mime, w, h = image_info(raw)
        except GLBError as exc:
            rep.err("IMAGE_INVALID", f"image {i}: {exc}")
            continue
        if img.get("mimeType") != mime:
            rep.err("IMAGE_MIME", f"image {i} mimeType {img.get('mimeType')} but data is {mime}")
        if w & (w - 1) or h & (h - 1):
            rep.err("IMAGE_NPOT", f"image {i} is {w}x{h} (not power of two)")
        max_tex = max(max_tex, w, h)
    rep.stats["max_texture"] = max_tex
    if expect.get("max_texture") and max_tex > expect["max_texture"]:
        rep.err("TEXTURE_BUDGET", f"texture {max_tex}px exceeds budget {expect['max_texture']}px")
    if expect.get("max_materials") is not None and len(js.get("materials", [])) > expect["max_materials"]:
        rep.err("MATERIAL_BUDGET", f"{len(js['materials'])} materials > {expect['max_materials']}")
    for i, mat in enumerate(js.get("materials", [])):
        pbr = mat.get("pbrMetallicRoughness", {})
        for key in ("metallicFactor", "roughnessFactor"):
            v = pbr.get(key, 1.0)
            if not (0.0 <= v <= 1.0):
                rep.err("MATERIAL_RANGE", f"material {mat.get('name')} {key}={v}")

    # -- skins
    bone_names = []
    par = glb.parents()
    for si, skin in enumerate(js.get("skins", [])):
        joints = skin["joints"]
        bone_names = [nodes[j].get("name") for j in joints]
        rep.stats["bones"] = len(joints)
        if "inverseBindMatrices" not in skin:
            rep.err("NO_IBM", f"skin {si} lacks inverseBindMatrices")
            continue
        ibm = glb.accessor(skin["inverseBindMatrices"])
        if len(ibm) != len(joints):
            rep.err("IBM_COUNT", f"skin {si}: {len(ibm)} IBMs for {len(joints)} joints")
            continue
        # Rest pose must equal bind pose: joint_world @ IBM == skeleton-space identity (up to the mesh node).
        worst = 0.0
        for k, j in enumerate(joints):
            m = ibm[k].reshape(4, 4).T
            if abs(np.linalg.det(m[:3, :3])) < 1e-8:
                rep.err("IBM_SINGULAR", f"skin {si} joint {nodes[j].get('name')} has a singular IBM")
                continue
            prod = world[j] @ m
            ref = None
            for ni in skinned_nodes:
                if js["nodes"][ni].get("skin") == si:
                    ref = world[ni]
                    break
            target = ref if ref is not None else np.eye(4)
            worst = max(worst, float(np.abs(prod - target).max()))
        rep.stats["bind_pose_error"] = round(worst, 6)
        if worst > 1e-3:
            rep.err("BIND_POSE_MISMATCH", f"skin {si}: rest pose differs from bind pose (max err {worst:.4f})")
    # glTF ignores a skinned mesh node's (inherited) transform; engines differ
    # in how strictly they follow that, so require identity to be unambiguous.
    for ni in skinned_nodes:
        if float(np.abs(world[ni] - np.eye(4)).max()) > 1e-5:
            rep.err("SKINNED_MESH_TRANSFORM", f"skinned mesh node {nodes[ni].get('name')} has a non-identity world transform")
    if expect.get("kind") == "skinned" and not js.get("skins"):
        rep.err("NO_SKIN", "asset is expected to be skinned but has no skin")
    if expect.get("skeleton"):
        want = list(expect["skeleton"])
        missing = [b for b in want if b not in bone_names]
        extra = [b for b in bone_names if b not in want]
        if missing:
            rep.err("SKELETON_MISSING_BONES", f"missing bones: {missing[:12]}")
        if extra:
            rep.err("SKELETON_EXTRA_BONES", f"unexpected bones (control/debug bones exported?): {extra[:12]}")
        name_to_idx = {nodes[i].get("name"): i for i in range(len(nodes))}
        for b, p in (expect.get("skeleton_parents") or {}).items():
            bi = name_to_idx.get(b)
            if bi is None:
                continue
            actual = par.get(bi)
            actual_name = nodes[actual].get("name") if actual is not None else None
            if p is not None and actual_name != p:
                rep.err("SKELETON_HIERARCHY", f"bone {b} parent is {actual_name}, expected {p}")

    # -- bounds (static meshes via node transforms; skinned via bind pose = POSITION space)
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for ni in render_nodes:
        n = nodes[ni]
        m = world[ni]
        for p in js["meshes"][n["mesh"]]["primitives"]:
            acc = js["accessors"][p["attributes"]["POSITION"]]
            bmin, bmax = np.array(acc["min"]), np.array(acc["max"])
            corners = np.array([[x, y, z, 1.0] for x in (bmin[0], bmax[0]) for y in (bmin[1], bmax[1])
                                for z in (bmin[2], bmax[2])])
            wc = (m @ corners.T).T[:, :3]
            lo = np.minimum(lo, wc.min(axis=0))
            hi = np.maximum(hi, wc.max(axis=0))
    if np.all(np.isfinite(lo)):
        # glTF (x, y-up, z-front) -> Blender (x, y = -z, z = y)
        bl_lo = np.array([lo[0], -hi[2], lo[1]])
        bl_hi = np.array([hi[0], -lo[2], hi[1]])
        dims = bl_hi - bl_lo
        rep.stats["dimensions"] = [round(float(d), 4) for d in dims]
        rep.stats["bounds_min"] = [round(float(d), 4) for d in bl_lo]
        rep.stats["bounds_max"] = [round(float(d), 4) for d in bl_hi]
        dmin, dmax = expect.get("dims_min"), expect.get("dims_max")
        if dmin and any(d < m - 1e-6 for d, m in zip(dims, dmin)):
            rep.err("DIMENSIONS_TOO_SMALL", f"dimensions {rep.stats['dimensions']} below minimum {dmin}")
        if dmax and any(d > m + 1e-6 for d, m in zip(dims, dmax)):
            rep.err("DIMENSIONS_TOO_LARGE", f"dimensions {rep.stats['dimensions']} exceed maximum {dmax}")
        origin = expect.get("origin", "any")
        size = max(float(dims.max()), 1e-6)
        if origin in ("base", "embedded", "ceiling", "tile"):
            inside_xy = (bl_lo[0] - 0.05 * size <= 0.0 <= bl_hi[0] + 0.05 * size and
                         bl_lo[1] - 0.05 * size <= 0.0 <= bl_hi[1] + 0.05 * size)
            if not inside_xy:
                rep.err("ORIGIN_OFF_FOOTPRINT", f"origin lies outside the footprint {rep.stats['bounds_min']}..{rep.stats['bounds_max']}")
            if origin == "base" and abs(bl_lo[2]) > max(0.02, 0.02 * dims[2]):
                rep.err("ORIGIN_NOT_ON_GROUND", f"lowest point z={bl_lo[2]:.3f} (origin must be at the base)")
            if origin == "embedded" and not (-0.4 * dims[2] <= bl_lo[2] <= 0.01):
                rep.err("ORIGIN_EMBED", f"embedded asset base z={bl_lo[2]:.3f} outside allowed range")
            if origin == "tile" and not (-0.5 <= bl_lo[2] <= 0.01):
                rep.err("ORIGIN_TILE", f"tile skirt bottom z={bl_lo[2]:.3f} outside allowed range")
            if origin == "ceiling" and abs(bl_hi[2]) > max(0.02, 0.02 * dims[2]):
                rep.err("ORIGIN_NOT_ON_CEILING", f"highest point z={bl_hi[2]:.3f} (origin must be at the mount)")
        elif origin == "center":
            c = (bl_lo + bl_hi) / 2
            if np.linalg.norm(c) > 0.1 * size + 0.02:
                rep.err("ORIGIN_NOT_CENTERED", f"bounds center {c.round(3).tolist()} is far from origin")
        elif origin == "grip":
            if not (np.all(bl_lo <= 0.02) and np.all(bl_hi >= -0.02)):
                rep.err("ORIGIN_GRIP", "grip origin lies outside the tool bounds")

    # -- budgets
    tri_rng = expect.get("triangles")
    if tri_rng:
        lo_t, hi_t = tri_rng
        if tri_total > hi_t:
            rep.err("TRIANGLE_BUDGET", f"{tri_total} triangles exceed hard budget {hi_t}")
        elif expect.get("triangles_soft_max") and tri_total > expect["triangles_soft_max"]:
            rep.warn("BUDGET_OVER_TARGET", f"{tri_total} triangles above target {expect['triangles_soft_max']}")
        if tri_total < lo_t:
            rep.warn("BUDGET_BELOW_MIN", f"{tri_total} triangles below budget minimum {lo_t}")
    if expect.get("max_file_mb") and glb.size > expect["max_file_mb"] * 1024 * 1024:
        rep.err("FILE_SIZE_BUDGET", f"{glb.size / 1048576:.2f} MB exceeds {expect['max_file_mb']} MB")
    for req in expect.get("required_nodes", []):
        if req not in names:
            rep.err("MISSING_NODE", f"required node '{req}' missing")
    for forbidden in expect.get("forbidden_node_patterns", []):
        rx = re.compile(forbidden)
        hits = [n for n in names if rx.search(n)]
        if hits:
            rep.err("FORBIDDEN_NODE", f"nodes matching {forbidden!r} must not be exported: {hits[:6]}")

    _inspect_animations(glb, expect, rep, world)


def _inspect_animations(glb, expect, rep, rest_world):
    js = glb.json
    nodes = js.get("nodes", [])
    anims = js.get("animations", [])
    names = [a.get("name", "") for a in anims]
    rep.stats["animations"] = names
    want = expect.get("animations") or []
    missing = [a for a in want if a not in names]
    if missing:
        rep.err("MISSING_ANIMATION", f"missing animation clips: {missing}")
    if expect.get("no_animations") and anims:
        rep.err("UNEXPECTED_ANIMATION", f"asset should not carry animations: {names}")
    dupe = sorted({n for n in names if names.count(n) > 1})
    if dupe:
        rep.err("DUPLICATE_ANIMATION", f"duplicate clip names {dupe}")
    acfg = expect.get("anim_cfg") or {}
    fps = acfg.get("fps", 30)
    name_to_idx = {n.get("name"): i for i, n in enumerate(nodes)}
    joint_set = set()
    for skin in js.get("skins", []):
        joint_set.update(skin["joints"])
    details = {}
    for ai, anim in enumerate(anims):
        nm = anim.get("name", f"anim{ai}")
        chans = glb.channel_data(anim)
        if not chans:
            rep.err("EMPTY_ANIMATION", f"clip {nm} has no channels")
            continue
        t_end = 0.0
        t_start = 1e9
        for node, path, interp, times, vals in chans:
            if len(times) == 0:
                rep.err("EMPTY_SAMPLER", f"clip {nm}: empty sampler")
                continue
            if np.any(np.diff(times) <= 0):
                rep.err("NON_MONOTONIC_TIME", f"clip {nm}: keyframe times not strictly increasing")
            if times[0] < -1e-6:
                rep.err("NEGATIVE_TIME", f"clip {nm}: negative keyframe time")
            t_end = max(t_end, float(times[-1]))
            t_start = min(t_start, float(times[0]))
            if node is not None and node not in joint_set and js.get("skins") and not expect.get("allow_node_anim"):
                rep.err("NON_JOINT_TARGET", f"clip {nm} animates non-joint node {nodes[node].get('name')}")
            if path == "rotation":
                norms = np.linalg.norm(vals if interp != "CUBICSPLINE" else vals.reshape(len(times), 3, 4)[:, 1],
                                       axis=1)
                if np.abs(norms - 1.0).max() > acfg.get("quaternion_norm_tolerance", 1e-3):
                    rep.err("QUAT_NOT_UNIT", f"clip {nm}: non-unit rotation on {nodes[node].get('name')}")
            elif path == "translation":
                if np.abs(vals).max() > acfg.get("max_bone_translation_m", 50.0) and node in joint_set:
                    rep.err("TRANSLATION_OUT_OF_BOUNDS",
                            f"clip {nm}: joint {nodes[node].get('name')} translates {np.abs(vals).max():.2f} m")
            elif path == "scale":
                if vals.size and (vals.min() < 0.01 or vals.max() > 10.0):
                    rep.err("SCALE_OUT_OF_BOUNDS", f"clip {nm}: extreme scale on {nodes[node].get('name')}")
        duration = t_end - min(t_start, 0.0)
        frames = int(round(duration * fps)) + 1
        details[nm] = {"duration": round(duration, 4), "frames": frames, "channels": len(chans)}
        if duration < acfg.get("min_duration_s", 0.0) - 1e-6 or duration > acfg.get("max_duration_s", 1e9):
            rep.err("DURATION_OUT_OF_RANGE", f"clip {nm} duration {duration:.3f}s outside allowed range")
        spec = (expect.get("clips") or {}).get(nm)
        if spec is None:
            continue
        if abs(duration - spec["duration"]) > 1.5 / fps:
            rep.err("DURATION_MISMATCH", f"clip {nm} lasts {duration:.3f}s, spec says {spec['duration']}s")
        # Evaluate the clip frame by frame through the skeleton.
        times = np.linspace(0.0, t_end, max(2, frames))
        frames_world = []
        for t in times:
            ov = glb.sample_channels(chans, t)
            frames_world.append(glb.world_matrices({k: tuple(v) for k, v in ov.items()}))
        for fw in frames_world:
            for i in joint_set:
                if not np.all(np.isfinite(fw[i])):
                    rep.err("NAN_POSE", f"clip {nm}: non-finite pose")
                    break
        if spec.get("loop"):
            _check_loop(glb, nm, chans, t_end, acfg, rep)
        _check_contacts(nm, spec, times, frames_world, name_to_idx, acfg, rep, details[nm])
        _check_grips(nm, spec, times, frames_world, name_to_idx, expect, acfg, rep, details[nm])
    rep.stats["animation_details"] = details


def _check_loop(glb, nm, chans, t_end, acfg, rep):
    rot_tol = acfg.get("loop_rotation_tolerance_deg", 1.5)
    tr_tol = acfg.get("loop_translation_tolerance_m", 0.01)
    nodes = glb.json["nodes"]
    worst_r, worst_t = 0.0, 0.0
    for node, path, interp, times, vals in chans:
        if node is None:
            continue
        v0 = _sample(times, vals, 0.0, interp, path == "rotation", interp == "CUBICSPLINE")
        v1 = _sample(times, vals, t_end, interp, path == "rotation", interp == "CUBICSPLINE")
        if path == "rotation":
            d = quat_angle_deg(v0, v1)
            if d > worst_r:
                worst_r = d
            if d > rot_tol:
                rep.err("LOOP_DISCONTINUITY", f"clip {nm}: {nodes[node].get('name')} rotation jumps {d:.2f} deg at loop")
                return
        elif path == "translation":
            d = float(np.linalg.norm(v0 - v1))
            worst_t = max(worst_t, d)
            if d > tr_tol:
                rep.err("LOOP_DISCONTINUITY", f"clip {nm}: {nodes[node].get('name')} translation jumps {d * 100:.1f} cm at loop")
                return


def _gltf_to_bl(p):
    return np.array([p[0], -p[2], p[1]])


def _check_contacts(nm, spec, times, frames_world, name_to_idx, acfg, rep, info):
    feet = spec.get("feet")
    if feet not in ("planted", "locomotion"):
        return
    speed = 0.0
    rm = spec.get("root_motion", {})
    if rm.get("type") == "in_place":
        speed = float(rm.get("speed_mps", 0.0))
    thr = acfg.get("foot_contact_height_m", 0.045)
    thr_v = acfg.get("foot_contact_speed_mps", 0.3)
    max_slide = acfg.get("foot_slide_max_m", 0.035)
    worst = 0.0
    contact_frames = 0
    ground_v = np.array([0.0, speed])
    for side in ("L", "R"):
        idx = name_to_idx.get(f"toe.{side}")
        if idx is None:
            rep.err("CONTACT_JOINT_MISSING", f"clip {nm}: toe.{side} joint missing for contact analysis")
            return
        pos = np.array([_gltf_to_bl(fw[idx][:3, 3]) for fw in frames_world])
        rest_h = pos[:, 2].min()
        # A foot is in contact when it is near the ground AND moving with it
        # (horizontal speed relative to the ground below thr_v); low, fast
        # swing frames are not contacts. Slow slides accumulate over the
        # contact span and are caught by max_slide below.
        vel = np.gradient(pos[:, :2], times, axis=0) if len(times) > 2 else np.zeros((len(times), 2))
        rel_speed = np.linalg.norm(vel - ground_v, axis=1)
        contact = (pos[:, 2] <= max(rest_h, 0.0) + thr) & (rel_speed <= thr_v)
        contact_frames += int(contact.sum())
        # Expected ground motion in character space: the worker faces -Y and moves forward,
        # so planted feet travel toward +Y at `speed`.
        start = None
        for k in range(len(times) + 1):
            c = k < len(times) and contact[k]
            if c and start is None:
                start = k
            elif not c and start is not None:
                if k - 1 > start:
                    dt = times[k - 1] - times[start]
                    disp = pos[k - 1, :2] - pos[start, :2]
                    expected = np.array([0.0, speed * dt])
                    slide = float(np.linalg.norm(disp - expected))
                    worst = max(worst, slide)
                start = None
    info["foot_slide_m"] = round(worst, 4)
    info["contact_frames"] = contact_frames
    if feet == "planted" and contact_frames < len(times):
        rep.err("FEET_NOT_PLANTED", f"clip {nm}: feet leave the ground in a planted clip")
    if worst > max_slide:
        rep.err("FOOT_SLIDING", f"clip {nm}: foot slides {worst * 100:.1f} cm during contact (max {max_slide * 100:.1f} cm)")


def _check_grips(nm, spec, times, frames_world, name_to_idx, expect, acfg, rep, info):
    grip_key = spec.get("grip")
    if not grip_key:
        return
    grip = (expect.get("grips") or {}).get(grip_key)
    if grip is None:
        rep.err("GRIP_SPEC_MISSING", f"clip {nm}: grip spec {grip_key} missing")
        return
    tol = acfg.get("grip_tolerance_m", 0.025)
    window = spec.get("grip_window")
    worst = 0.0
    for k, t in enumerate(times):
        if window and not (window[0] - 1e-6 <= t <= window[1] + 1e-6):
            continue
        fw = frames_world[k]
        if "socket" in grip:
            a = name_to_idx.get(grip["relative_to"])
            b = name_to_idx.get(grip["socket"])
            if a is None or b is None:
                rep.err("GRIP_JOINT_MISSING", f"clip {nm}: grip joints missing")
                return
            target = fw[a] @ np.array(list(grip["offset"]) + [1.0])
            d = float(np.linalg.norm(fw[b][:3, 3] - target[:3]))
            worst = max(worst, d)
        else:
            ref = name_to_idx.get(grip["relative_to"])
            if ref is None:
                rep.err("GRIP_JOINT_MISSING", f"clip {nm}: {grip['relative_to']} missing")
                return
            for sock, off in zip(grip["socket_pair"], grip["offsets"]):
                si = name_to_idx.get(sock)
                if si is None:
                    rep.err("GRIP_JOINT_MISSING", f"clip {nm}: {sock} missing")
                    return
                if grip["relative_to"] == "root":
                    # Offsets are authored in Blender space relative to the worker root.
                    o = np.array(off, dtype=np.float64)
                    local = np.array([o[0], o[2], -o[1], 1.0])
                else:
                    local = np.array(list(off) + [1.0])
                target = fw[ref] @ local
                d = float(np.linalg.norm(fw[si][:3, 3] - target[:3]))
                worst = max(worst, d)
    info["grip_error_m"] = round(worst, 4)
    if worst > tol:
        rep.err("GRIP_MISALIGNED", f"clip {nm}: hand/tool grip error {worst * 100:.1f} cm (max {tol * 100:.1f} cm)")
