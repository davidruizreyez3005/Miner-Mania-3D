"""Split a multi-clip GLB into single-clip GLBs.

Pure Python and deterministic: the JSON is copied, every animation except the
kept ones is dropped, unreferenced accessors/bufferViews are garbage-collected
and the binary chunk is rebuilt with 4-byte alignment. Meshes, skins,
materials and textures are preserved byte-for-byte, so every split file
imports into Godot with the same Skeleton3D and track paths as the library.
"""

import copy
import json
import struct

from core.errors import PipelineError

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


def read_glb(path):
    with open(path, "rb") as fh:
        data = fh.read()
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC or version != 2 or length != len(data):
        raise PipelineError(f"{path}: not a valid GLB 2.0 file")
    off = 12
    js, bin_ = None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == CHUNK_JSON:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == CHUNK_BIN:
            bin_ = chunk
        off += 8 + clen
    if js is None:
        raise PipelineError(f"{path}: GLB has no JSON chunk")
    return js, bin_


def write_glb(path, js, bin_):
    jbytes = json.dumps(js, separators=(",", ":"), sort_keys=False).encode("utf-8")
    jbytes += b" " * ((4 - len(jbytes) % 4) % 4)
    bbytes = bin_ + b"\0" * ((4 - len(bin_) % 4) % 4)
    total = 12 + 8 + len(jbytes) + (8 + len(bbytes) if bbytes else 0)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", GLB_MAGIC, 2, total))
        fh.write(struct.pack("<II", len(jbytes), CHUNK_JSON))
        fh.write(jbytes)
        if bbytes:
            fh.write(struct.pack("<II", len(bbytes), CHUNK_BIN))
            fh.write(bbytes)


def _used_accessors(js):
    used = set()
    for mesh in js.get("meshes", []):
        for prim in mesh.get("primitives", []):
            used.update(prim.get("attributes", {}).values())
            if "indices" in prim:
                used.add(prim["indices"])
            for tgt in prim.get("targets", []):
                used.update(tgt.values())
    for skin in js.get("skins", []):
        if "inverseBindMatrices" in skin:
            used.add(skin["inverseBindMatrices"])
    for anim in js.get("animations", []):
        for s in anim.get("samplers", []):
            used.add(s["input"])
            used.add(s["output"])
    return used


def keep_animations(js, bin_, names):
    """Return (json, bin) containing only the animations named in ``names``."""
    names = set(names)
    out = copy.deepcopy(js)
    out["animations"] = [a for a in js.get("animations", []) if a.get("name") in names]
    missing = names - {a.get("name") for a in out["animations"]}
    if missing:
        raise PipelineError(f"GLB split: animations not found: {sorted(missing)}")
    if any(b.get("uri") for b in js.get("buffers", [])) or len(js.get("buffers", [])) > 1:
        raise PipelineError("GLB split supports a single embedded buffer only")
    acc_used = sorted(_used_accessors(out))
    acc_map = {old: new for new, old in enumerate(acc_used)}
    accessors = [copy.deepcopy(js["accessors"][i]) for i in acc_used]
    bv_used = set()
    for a in accessors:
        if "bufferView" in a:
            bv_used.add(a["bufferView"])
        sp = a.get("sparse")
        if sp:
            bv_used.add(sp["indices"]["bufferView"])
            bv_used.add(sp["values"]["bufferView"])
    for img in out.get("images", []):
        if "bufferView" in img:
            bv_used.add(img["bufferView"])
    bv_order = sorted(bv_used)
    bv_map = {}
    views = []
    blob = bytearray()
    for new, old in enumerate(bv_order):
        bv = copy.deepcopy(js["bufferViews"][old])
        start = bv.get("byteOffset", 0)
        chunk = bin_[start: start + bv["byteLength"]]
        pad = (4 - len(blob) % 4) % 4
        blob.extend(b"\0" * pad)
        bv["byteOffset"] = len(blob)
        bv["buffer"] = 0
        blob.extend(chunk)
        views.append(bv)
        bv_map[old] = new
    for a in accessors:
        if "bufferView" in a:
            a["bufferView"] = bv_map[a["bufferView"]]
        sp = a.get("sparse")
        if sp:
            sp["indices"]["bufferView"] = bv_map[sp["indices"]["bufferView"]]
            sp["values"]["bufferView"] = bv_map[sp["values"]["bufferView"]]
    for img in out.get("images", []):
        if "bufferView" in img:
            img["bufferView"] = bv_map[img["bufferView"]]
    for mesh in out.get("meshes", []):
        for prim in mesh.get("primitives", []):
            prim["attributes"] = {k: acc_map[v] for k, v in prim.get("attributes", {}).items()}
            if "indices" in prim:
                prim["indices"] = acc_map[prim["indices"]]
            if "targets" in prim:
                prim["targets"] = [{k: acc_map[v] for k, v in t.items()} for t in prim["targets"]]
    for skin in out.get("skins", []):
        if "inverseBindMatrices" in skin:
            skin["inverseBindMatrices"] = acc_map[skin["inverseBindMatrices"]]
    for anim in out["animations"]:
        for s in anim.get("samplers", []):
            s["input"] = acc_map[s["input"]]
            s["output"] = acc_map[s["output"]]
    out["accessors"] = accessors
    out["bufferViews"] = views
    out["buffers"] = [{"byteLength": len(blob)}]
    return out, bytes(blob)


def stub_meshes(js, bin_):
    """Replace every mesh with one tiny triangle skinned 100 % to joint 0 and
    drop materials/textures. The skin (and so Godot's Skeleton3D and track
    paths) is untouched; the file becomes a light animation container."""
    import numpy as np
    out = copy.deepcopy(js)
    blob = bytearray(bin_)

    def add_view(data):
        pad = (4 - len(blob) % 4) % 4
        blob.extend(b"\0" * pad)
        out["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        return len(out["bufferViews"]) - 1

    def add_acc(arr, ctype, typ, minmax=False):
        acc = {"bufferView": add_view(arr.tobytes()), "componentType": ctype, "count": int(arr.shape[0]),
               "type": typ}
        if minmax:
            acc["min"] = [float(x) for x in arr.min(axis=0)]
            acc["max"] = [float(x) for x in arr.max(axis=0)]
        out["accessors"].append(acc)
        return len(out["accessors"]) - 1

    pos = np.array([[0.0, 0.0, 0.0], [0.001, 0.0, 0.0], [0.0, 0.001, 0.0]], dtype=np.float32)
    joints = np.zeros((3, 4), dtype=np.uint16)
    weights = np.array([[1.0, 0.0, 0.0, 0.0]] * 3, dtype=np.float32)
    normals = np.array([[0.0, 0.0, 1.0]] * 3, dtype=np.float32)
    a_pos = add_acc(pos, 5126, "VEC3", minmax=True)
    a_nrm = add_acc(normals, 5126, "VEC3")
    a_j = add_acc(joints, 5123, "VEC4")
    a_w = add_acc(weights, 5126, "VEC4")
    for mesh in out.get("meshes", []):
        mesh["primitives"] = [{"attributes": {"POSITION": a_pos, "NORMAL": a_nrm, "JOINTS_0": a_j, "WEIGHTS_0": a_w},
                               "mode": 4}]
    for key in ("materials", "textures", "images", "samplers"):
        out.pop(key, None)
    return out, bytes(blob)


def split(src, clips, path_for, stub=True):
    """Write one GLB per clip name; ``path_for(clip)`` gives the output path.
    With ``stub`` the meshes become a one-triangle skinned stub."""
    js, bin_ = read_glb(src)
    if stub:
        js, bin_ = stub_meshes(js, bin_)
    written = {}
    for clip in clips:
        j2, b2 = keep_animations(js, bin_, [clip])
        p = path_for(clip)
        write_glb(p, j2, b2)
        written[clip] = p
    return written
