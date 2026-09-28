#!/usr/bin/env python3
"""Tileable surface textures for terrain, rock faces and gallery interiors.

    python tools/textures/texgen.py [--out assets/generated/textures] [--size 512]

Large surfaces (the valley terrain, the cut face of the mountain, gallery
floors and walls) are shaded in Godot with these tiling PBR sets; props and
machines keep their own baked textures from the Blender pipeline. Every set
is generated from periodic noise (FFT-filtered fBm and wrap-around Worley
cells), so it tiles seamlessly, and from fixed seeds, so it is reproducible.
Outputs per set: <name>_albedo.png (sRGB), <name>_normal.png (OpenGL
tangent space) and <name>_orm.png (R occlusion, G roughness, B metallic).
"""

import argparse
import json
import os
import struct
import sys
import zlib

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ----------------------------------------------------------------- periodic noise

def fbm(n, beta, seed, lo_cut=1.0):
    """Periodic fractal noise via spectral synthesis (amplitude ~ 1/f^beta)."""
    r = np.random.default_rng(seed)
    white = r.standard_normal((n, n))
    F = np.fft.fft2(white)
    fx = np.fft.fftfreq(n)[:, None] * n
    fy = np.fft.fftfreq(n)[None, :] * n
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    amp = 1.0 / np.maximum(f, lo_cut) ** beta
    amp[0, 0] = 0.0
    out = np.real(np.fft.ifft2(F * amp))
    out -= out.min()
    return out / (out.max() + 1e-12)


def fbm_aniso(n, beta, seed, sx=1.0, sy=1.0):
    """Periodic fbm stretched along an axis (sx > 1 elongates features along x)."""
    r = np.random.default_rng(seed)
    F = np.fft.fft2(r.standard_normal((n, n)))
    fy = np.fft.fftfreq(n)[:, None] * n * sy
    fx = np.fft.fftfreq(n)[None, :] * n * sx
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    amp = 1.0 / np.maximum(f, 1.0) ** beta
    amp[0, 0] = 0.0
    out = np.real(np.fft.ifft2(F * amp))
    out -= out.min()
    return out / (out.max() + 1e-12)


def worley(n, cells, seed, jitter=1.0):
    """Periodic Worley noise: returns (F1 distance, F2 distance, cell id), normalised."""
    r = np.random.default_rng(seed)
    pts = (np.arange(cells)[:, None] + 0.5 + (r.random((cells, 2)) - 0.5) * jitter)
    pts = np.stack(np.meshgrid(np.arange(cells), np.arange(cells), indexing="ij"), -1).reshape(-1, 2).astype(float)
    pts += 0.5 + (r.random(pts.shape) - 0.5) * jitter
    pts *= n / cells
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    f1 = np.full((n, n), 1e9)
    f2 = np.full((n, n), 1e9)
    ident = np.zeros((n, n), dtype=np.int64)
    for i, (py, px) in enumerate(pts):
        dy = np.abs(ys - py)
        dx = np.abs(xs - px)
        dy = np.minimum(dy, n - dy)
        dx = np.minimum(dx, n - dx)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < f1
        f2 = np.where(closer, f1, np.minimum(f2, d))
        ident = np.where(closer, i, ident)
        f1 = np.where(closer, d, f1)
    scale = n / cells
    return f1 / scale, f2 / scale, ident


def blur_wrap(img, radius):
    if radius <= 0:
        return img
    k = int(radius)
    out = img.copy()
    for axis in (0, 1):
        acc = np.zeros_like(out)
        for s in range(-k, k + 1):
            acc += np.roll(out, s, axis=axis)
        out = acc / (2 * k + 1)
    return out


def normal_from_height(h, strength):
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    nx = -dx * strength
    ny = dy * strength          # OpenGL convention (green up), Godot's default
    nz = np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / ln, ny / ln, nz / ln], -1)
    return (n * 0.5 + 0.5)


def ao_from_height(h, radius=6, strength=1.6):
    avg = blur_wrap(h, radius)
    return np.clip(1.0 - (avg - h) * strength, 0.35, 1.0)


def lerp(a, b, t):
    return a + (b - a) * t


def ramp(t, stops):
    """Colour ramp: stops = [(pos, (r,g,b)), ...] with rgb in 0..1 (sRGB)."""
    t = np.clip(t, 0.0, 1.0)
    out = np.zeros(t.shape + (3,))
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        m = (t >= p0) & (t <= p1)
        f = ((t - p0) / max(p1 - p0, 1e-9))[..., None]
        out = np.where(m[..., None], np.array(c0) + (np.array(c1) - np.array(c0)) * f, out)
    return out


def hexc(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


# ----------------------------------------------------------------- PNG writer

def write_png(path, arr):
    """arr: HxWx3 or HxWx4 float 0..1 -> 8-bit PNG (no external dependencies)."""
    a = np.clip(np.asarray(arr) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    h, w, c = a.shape
    color_type = {3: 2, 4: 6}[c]
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        fh.write(chunk(b"IEND", b""))


# ----------------------------------------------------------------- materials

def grass(n, seed=101):
    base = fbm(n, 1.6, seed)
    fine = fbm(n, 0.6, seed + 1)
    blades = fbm(n, 0.2, seed + 2)
    patches = fbm(n, 2.2, seed + 3)
    h = 0.5 * base + 0.3 * fine + 0.2 * blades
    col = ramp(0.55 * patches + 0.45 * fine, [(0.0, hexc("#4a5a2c")), (0.45, hexc("#627433")), (0.7, hexc("#7a8a3e")), (1.0, hexc("#9a9a58"))])
    dry = np.clip((patches - 0.62) * 3.0, 0, 1)[..., None]
    col = lerp(col, np.array(hexc("#8e8456")), dry * 0.7)
    col *= (0.82 + 0.3 * blades)[..., None]
    rough = 0.88 + 0.1 * fine
    return col, h, rough, 0.0, 5.0


def dirt(n, seed=111):
    base = fbm(n, 1.8, seed)
    fine = fbm(n, 0.8, seed + 1)
    f1, f2, ident = worley(n, 24, seed + 2, 0.9)
    pebbles = np.clip(1.0 - f1 * 2.6, 0, 1) * (ident % 5 == 0)
    h = 0.6 * base + 0.25 * fine + 0.35 * pebbles
    col = ramp(0.6 * base + 0.4 * fine, [(0.0, hexc("#5a4632")), (0.5, hexc("#7a6046")), (1.0, hexc("#957a5c"))])
    col = lerp(col, np.array(hexc("#a39a8c")), (pebbles * 0.8)[..., None])
    rough = 0.9 - 0.15 * pebbles
    return col, h, rough, 0.0, 6.0


def gravel(n, seed=121):
    f1, f2, ident = worley(n, 40, seed, 1.0)
    stones = np.clip((f2 - f1) * 3.2, 0, 1)
    shade = (np.random.default_rng(seed + 5).random(ident.max() + 1))[ident]
    fine = fbm(n, 0.7, seed + 1)
    h = 0.7 * stones * (0.6 + 0.4 * shade) + 0.3 * fine
    col = ramp(0.55 * shade + 0.45 * fine, [(0.0, hexc("#56514a")), (0.5, hexc("#77716a")), (1.0, hexc("#9d978d"))])
    col *= (0.65 + 0.35 * stones)[..., None]
    rough = 0.8 + 0.15 * (1 - stones)
    return col, h, rough, 0.0, 7.0


def rock(n, seed=131, palette=("#3e3934", "#6a625a", "#9a9087")):
    """Fractured rock: layered fbm with ridged-noise fractures and a few large
    Worley facets (weathered planes), no regular cell pattern."""
    base = fbm(n, 2.1, seed)
    mid = fbm(n, 1.3, seed + 1)
    fine = fbm(n, 0.55, seed + 2)
    ridged = 1.0 - np.abs(2.0 * fbm(n, 1.6, seed + 4) - 1.0)
    fractures = np.clip((ridged - 0.86) * 7.0, 0, 1)
    f1, f2, _ = worley(n, 5, seed + 3, 1.0)
    facets = np.clip((f2 - f1) * 1.5, 0, 1)
    h = 0.45 * base + 0.25 * mid + 0.15 * fine + 0.15 * facets - 0.3 * fractures
    t = 0.5 * mid + 0.3 * base + 0.2 * fine
    col = ramp(t, [(0.0, hexc(palette[0])), (0.55, hexc(palette[1])), (1.0, hexc(palette[2]))])
    col *= (1.0 - 0.4 * fractures)[..., None]
    rough = 0.82 + 0.12 * fine - 0.08 * facets
    return col, h, rough, 0.0, 9.0


def strata(n, seed=141):
    """Layered sediment for the cut face: horizontal beds with wavy contacts."""
    ys = np.arange(n)[:, None].astype(float) / n
    warp = fbm(n, 2.2, seed) * 0.08
    bands = (ys + warp) * 8.0          # 8 beds per tile, matching the 8-entry tone table (tiles vertically)
    bed = np.floor(bands)
    frac = bands - bed
    r = np.random.default_rng(seed)
    bed_tone = r.random(8)[(bed.astype(int)) % 8]
    fine = fbm(n, 0.6, seed + 1)
    mid = fbm(n, 1.3, seed + 2)
    contact = np.clip(1.0 - np.abs(frac - 0.5) * 2.0, 0, 1) ** 0.3
    h = 0.35 * contact + 0.35 * mid + 0.3 * fine + 0.2 * bed_tone
    col = ramp(0.5 * bed_tone + 0.3 * mid + 0.2 * fine, [(0.0, hexc("#4c4238")), (0.4, hexc("#6d5f50")), (0.75, hexc("#8e7e6a")), (1.0, hexc("#a8977f"))])
    col *= (0.75 + 0.25 * contact)[..., None]
    rough = 0.86 + 0.1 * fine
    return col, h, rough, 0.0, 7.0


def concrete(n, seed=151):
    base = fbm(n, 1.4, seed)
    fine = fbm(n, 0.3, seed + 1)
    pores = (fbm(n, 0.1, seed + 2) > 0.82).astype(float) * 0.6
    stains = np.clip((fbm(n, 2.4, seed + 3) - 0.6) * 2.5, 0, 1)
    h = 0.5 * base + 0.3 * fine - 0.3 * pores
    col = ramp(0.6 * base + 0.4 * fine, [(0.0, hexc("#7c7a74")), (1.0, hexc("#a9a69e"))])
    col = lerp(col, np.array(hexc("#5e5a52")), (stains * 0.5)[..., None])
    col *= (1.0 - pores * 0.5)[..., None]
    rough = 0.9 - 0.1 * base
    return col, h, rough, 0.0, 4.0


def snow(n, seed=161):
    base = fbm(n, 1.8, seed)
    fine = fbm(n, 0.4, seed + 1)
    h = 0.7 * base + 0.3 * fine
    col = ramp(0.7 * base + 0.3 * fine, [(0.0, hexc("#c9d3dc")), (1.0, hexc("#f4f7fa"))])
    rough = 0.55 + 0.25 * fine
    return col, h, rough, 0.0, 3.0


def wood(n, seed=171):
    """Weathered timber: planks along x with grain, knots and gaps."""
    ys = np.arange(n)[:, None].astype(float) / n
    planks = 4
    plank_id = np.floor(ys * planks).astype(int) % planks
    r = np.random.default_rng(seed)
    tone = r.random(planks)[plank_id]
    grain = fbm(n, 1.0, seed)
    stretched = fbm_aniso(n, 1.1, seed + 1, sx=10.0, sy=1.0)
    gap = (np.abs((ys * planks) % 1.0 - 0.0) < 0.03) | (np.abs((ys * planks) % 1.0 - 1.0) < 0.03)
    h = 0.5 * stretched + 0.3 * grain + 0.2 * tone - 0.6 * gap
    col = ramp(0.5 * stretched + 0.3 * tone + 0.2 * grain, [(0.0, hexc("#4a3524")), (0.5, hexc("#6e5238")), (1.0, hexc("#8f7050"))])
    col *= np.where(gap, 0.35, 1.0)[..., None]
    rough = 0.85 + 0.1 * grain
    return col, h, rough, 0.0, 6.0


def steel(n, seed=181):
    """Painted steel with wear: scuffs show bare metal, rust in the dirt."""
    base = fbm(n, 1.5, seed)
    fine = fbm(n, 0.3, seed + 1)
    wear = np.clip((fbm(n, 1.1, seed + 2) - 0.68) * 5.0, 0, 1)
    rust = np.clip((fbm(n, 1.8, seed + 3) - 0.7) * 4.0, 0, 1)
    h = 0.3 * base + 0.2 * fine - 0.3 * wear
    col = np.ones((n, n, 3)) * np.array(hexc("#5f6b73"))
    col = lerp(col, np.array(hexc("#9aa0a4")), wear[..., None])
    col = lerp(col, np.array(hexc("#7a4a2e")), (rust * 0.7)[..., None])
    col *= (0.9 + 0.2 * fine)[..., None]
    rough = 0.55 + 0.3 * rust - 0.2 * wear
    metal = 0.35 + 0.5 * wear
    return col, h, rough, 0.0, 3.0


SETS = {"grass": grass, "dirt": dirt, "gravel": gravel, "rock": rock, "strata": strata, "concrete": concrete, "snow": snow, "wood": wood, "steel": steel}


def build(name, fn, n, out):
    col, h, rough, metal, nstrength = fn(n)
    ao = ao_from_height(h)
    albedo = np.clip(col * (0.55 + 0.45 * ao)[..., None], 0, 1)
    normal = normal_from_height(h, nstrength)
    orm = np.stack([ao, np.clip(rough, 0.05, 1.0), np.full_like(h, metal)], -1)
    for kind, img in (("albedo", albedo), ("normal", normal), ("orm", orm)):
        write_png(os.path.join(out, f"{name}_{kind}.png"), img)
    # Tiling check: the wrap-around step must look like any interior step.
    edge = float(np.mean(np.abs(albedo[0] - albedo[-1])) + np.mean(np.abs(albedo[:, 0] - albedo[:, -1])))
    inner = float(np.mean(np.abs(np.diff(albedo, axis=0))) + np.mean(np.abs(np.diff(albedo, axis=1))))
    return {"albedo": f"res://assets/generated/textures/{name}_albedo.png",
            "normal": f"res://assets/generated/textures/{name}_normal.png",
            "orm": f"res://assets/generated/textures/{name}_orm.png",
            "size": n, "seam_ratio": round(edge / max(inner, 1e-6), 3),
            "mean_albedo": [round(float(x), 3) for x in albedo.reshape(-1, 3).mean(0)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "assets/generated/textures"))
    ap.add_argument("--size", type=int, default=512)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    manifest = {}
    bad = []
    for name, fn in SETS.items():
        info = build(name, fn, args.size, args.out)
        manifest[name] = info
        print(f"{name:10s} seam ratio {info['seam_ratio']:.2f}  mean albedo {info['mean_albedo']}")
        if info["seam_ratio"] > 2.5:
            bad.append(f"{name}: visible tiling seam (ratio {info['seam_ratio']})")
    with open(os.path.join(args.out, "textures.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
        fh.write("\n")
    if bad:
        print("texture check failed:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
