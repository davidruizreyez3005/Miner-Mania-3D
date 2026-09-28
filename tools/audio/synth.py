#!/usr/bin/env python3
"""Procedural sound library for Miner Mania 3D.

    python tools/audio/synth.py [--out assets/generated/audio] [--only id1,id2] [--list]

Every sound effect, ambience loop and music track is synthesised from code
(numpy) with fixed seeds, so the audio set is reproducible from source like
the 3D assets and carries no third-party licences. Output: 16-bit PCM WAV
(mono for effects, stereo for music/ambience). Loops are written seamlessly
(the tail is cross-faded into the head) and flagged in the manifest that
data/audio.json and the Audio autoload use.
"""

import argparse
import json
import math
import os
import struct
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SR = 44100


# --------------------------------------------------------------------------- primitives

def rng(seed):
    return np.random.default_rng(seed)


def t_axis(dur, sr=SR):
    return np.arange(int(dur * sr)) / sr


def env_adsr(n, a, d, s, r, sr=SR):
    a_n, d_n, r_n = int(a * sr), int(d * sr), int(r * sr)
    s_n = max(0, n - a_n - d_n - r_n)
    e = np.concatenate([
        np.linspace(0, 1, max(a_n, 1), endpoint=False),
        np.linspace(1, s, max(d_n, 1), endpoint=False),
        np.full(s_n, s),
        np.linspace(s, 0, max(r_n, 1)),
    ])
    return e[:n] if len(e) >= n else np.pad(e, (0, n - len(e)))


def env_exp(n, tau, sr=SR):
    return np.exp(-np.arange(n) / (tau * sr))


def onepole_lp(x, cutoff, sr=SR):
    a = math.exp(-2 * math.pi * cutoff / sr)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def lp(x, cutoff, sr=SR):
    """Fast FFT low-pass (brick-wall with a short roll-off)."""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / sr)
    roll = np.clip(1 - (f - cutoff) / (cutoff * 0.3 + 1), 0, 1)
    return np.fft.irfft(X * roll, n)


def hp(x, cutoff, sr=SR):
    return x - lp(x, cutoff, sr)


def bp(x, lo, hi, sr=SR):
    return lp(hp(x, lo, sr), hi, sr)


def noise(n, r):
    return r.standard_normal(n)


def sine(freq, t, phase=0.0):
    return np.sin(2 * np.pi * freq * t + phase)


def saw(freq, t):
    return 2 * ((freq * t) % 1.0) - 1


def tri(freq, t):
    return 2 * np.abs(saw(freq, t)) - 1


def norm(x, peak=0.9):
    m = np.max(np.abs(x))
    return x * (peak / m) if m > 0 else x


def fade(x, fin=0.002, fout=0.01, sr=SR):
    n = len(x)
    a, b = int(fin * sr), int(fout * sr)
    if a > 0:
        x[:a] *= np.linspace(0, 1, a)
    if b > 0:
        x[-b:] *= np.linspace(1, 0, b)
    return x


def make_loop(x, xfade=0.25, sr=SR):
    """Seamless loop: cross-fade the last `xfade` seconds into the start."""
    n = int(xfade * sr)
    if x.ndim == 1:
        head, tail = x[:n].copy(), x[-n:].copy()
        w = np.linspace(0, 1, n)
        out = x[:-n].copy()
        out[:n] = head * w + tail * (1 - w)
        return out
    return np.stack([make_loop(x[:, c], xfade, sr) for c in range(x.shape[1])], axis=1)


def reverb(x, room=0.5, decay=1.2, mix=0.25, seed=1, sr=SR):
    """Cheap convolution reverb with a noise impulse response."""
    r = rng(seed)
    n = int(decay * sr)
    ir = noise(n, r) * env_exp(n, decay / 5)
    ir = lp(ir, 3000 + 5000 * (1 - room))
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    wet = np.convolve(x, ir)
    total = len(x) + n
    wet = np.pad(wet, (0, max(0, total - len(wet))))[:total]
    dry = np.pad(x, (0, n))
    return dry * (1 - mix) + wet * mix


def karplus(freq, dur, r, bright=0.5, sr=SR):
    """Karplus-Strong plucked string."""
    n = int(dur * sr)
    period = max(2, int(sr / freq))
    buf = r.uniform(-1, 1, period)
    buf = lp(np.tile(buf, 4), 2000 + 6000 * bright)[:period]
    out = np.empty(n)
    idx = 0
    decay = 0.996
    for i in range(n):
        v = buf[idx]
        out[i] = v
        nxt = buf[(idx + 1) % period]
        buf[idx] = decay * 0.5 * (v + nxt)
        idx = (idx + 1) % period
    return out


def note(name):
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    key, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((names[key] + 12 * (octave + 1) - 69) / 12)


def mix_at(buf, x, start, gain=1.0):
    s = int(start)
    if s < 0:
        x = x[-s:]
        s = 0
    e = min(len(buf), s + len(x))
    if e > s:
        buf[s:e] += x[: e - s] * gain


# --------------------------------------------------------------------------- effects

def pick_hit(seed):
    r = rng(seed)
    t = t_axis(0.35)
    n = len(t)
    click = bp(noise(n, r), 1800, 7000) * env_exp(n, 0.012)
    thump = sine(90 + r.uniform(-10, 10), t) * env_exp(n, 0.05)
    ring = (sine(2400 + r.uniform(-200, 200), t) + 0.5 * sine(3900 + r.uniform(-300, 300), t)) * env_exp(n, 0.06) * 0.25
    grit = bp(noise(n, r), 400, 2500) * env_exp(n, 0.09) * 0.4
    return fade(norm(click * 1.2 + thump * 0.8 + ring + grit, 0.95), 0.0005, 0.03)


def rock_break(seed=11):
    r = rng(seed)
    n = int(0.9 * SR)
    x = lp(noise(n, r), 1500) * env_exp(n, 0.25) * 0.8
    for k in range(18):
        s = r.uniform(0, 0.6) * SR
        c = bp(noise(int(0.04 * SR), r), 1000, 6000) * env_exp(int(0.04 * SR), 0.008)
        mix_at(x, c, s, r.uniform(0.2, 0.6))
    boom = sine(55, t_axis(0.9)) * env_exp(n, 0.2)
    return fade(norm(x + boom * 0.6), 0.001, 0.05)


def drill_loop(seed=12):
    r = rng(seed)
    t = t_axis(1.0)
    n = len(t)
    am = 0.55 + 0.45 * np.sign(np.sin(2 * np.pi * 22 * t))
    body = bp(noise(n, r), 300, 5000) * am
    motor = (saw(110, t) * 0.3 + sine(55, t) * 0.4)
    return make_loop(norm(lp(body * 0.8 + motor * 0.5, 7000), 0.8), 0.1)


def machine_hum(seed=13, base=60.0, wobble=0.3, dur=2.0):
    r = rng(seed)
    t = t_axis(dur + 0.25)
    x = sum(sine(base * k, t) / k for k in range(1, 7))
    x *= 1 + 0.08 * sine(wobble, t)
    x += lp(noise(len(t), r), 400) * 0.25
    return make_loop(norm(x, 0.6), 0.25)


def crusher_loop(seed=14):
    r = rng(seed)
    dur = 2.0
    n = int((dur + 0.25) * SR)
    x = lp(noise(n, r), 200) * 0.5
    for k in range(5):
        s = k * 0.5 * SR
        hit = lp(noise(int(0.25 * SR), r), 900) * env_exp(int(0.25 * SR), 0.05)
        mix_at(x, hit, s, 1.0)
        crunch = bp(noise(int(0.3 * SR), r), 800, 4000) * env_exp(int(0.3 * SR), 0.08)
        mix_at(x, crunch, s + 0.03 * SR, 0.35)
    x += sine(40, t_axis(dur + 0.25)) * 0.3
    return make_loop(norm(x, 0.8), 0.25)


def conveyor_loop(seed=15):
    r = rng(seed)
    dur = 2.0
    n = int((dur + 0.25) * SR)
    x = bp(noise(n, r), 200, 2500) * 0.25
    for k in range(int(dur * 9) + 2):
        s = k * SR / 9 + r.uniform(-200, 200)
        c = bp(noise(int(0.02 * SR), r), 1500, 6000) * env_exp(int(0.02 * SR), 0.004)
        mix_at(x, c, s, r.uniform(0.3, 0.6))
    hum = machine_hum(16, 50, 0.5, dur + 0.25)
    mix_at(x, hum, 0, 0.3)
    return make_loop(norm(x, 0.7), 0.25)


def generator_loop(seed=17):
    t = t_axis(1.25)
    f = 28.0
    x = sum(np.sign(sine(f * k, t)) / (k * k) for k in range(1, 6)) * 0.5
    x *= 0.7 + 0.3 * (0.5 + 0.5 * sine(f / 2, t))
    x = lp(x, 900)
    r = rng(seed)
    x += lp(noise(len(t), r), 300) * 0.2
    return make_loop(norm(x, 0.7), 0.25)


def pump_loop(seed=18):
    r = rng(seed)
    dur = 2.0
    n = int((dur + 0.25) * SR)
    x = np.zeros(n)
    for k in range(6):
        s = k * SR / 3
        w = lp(noise(int(0.3 * SR), r), 1200) * env_adsr(int(0.3 * SR), 0.05, 0.1, 0.4, 0.12)
        mix_at(x, w, s, 0.8)
        th = sine(70, t_axis(0.12)) * env_exp(int(0.12 * SR), 0.03)
        mix_at(x, th, s, 0.6)
    return make_loop(norm(x, 0.7), 0.25)


def lift_motor_loop(seed=19):
    r = rng(seed)
    t = t_axis(2.25)
    whine = sine(420, t) * 0.2 + sine(840, t) * 0.08
    hum = sine(100, t) * 0.35
    creak = np.zeros(len(t))
    for k in range(3):
        s = r.uniform(0.1, 1.8) * SR
        c = bp(noise(int(0.2 * SR), r), 300, 1200) * env_adsr(int(0.2 * SR), 0.05, 0.05, 0.6, 0.08)
        mix_at(creak, c, s, 0.15)
    return make_loop(norm(whine + hum + creak + lp(noise(len(t), r), 600) * 0.1, 0.6), 0.25)


def bell(freq=880, dur=1.4, seed=20):
    t = t_axis(dur)
    n = len(t)
    parts = [(1.0, 1.0), (2.76, 0.5), (5.4, 0.25), (8.93, 0.12)]
    x = sum(a * sine(freq * p, t) * env_exp(n, dur / (2 + p)) for p, a in parts)
    return fade(norm(x, 0.8), 0.001, 0.05)


def truck_loop(seed=21):
    t = t_axis(1.25)
    f = 38.0
    x = sum(sine(f * k, t) / k for k in range(1, 9))
    x *= 0.75 + 0.25 * sine(f / 4, t)
    r = rng(seed)
    x = lp(x + lp(noise(len(t), r), 500) * 0.3, 1200)
    return make_loop(norm(x, 0.7), 0.25)


def horn(seed=22):
    t = t_axis(0.7)
    n = len(t)
    x = (saw(330, t) + saw(415, t)) * env_adsr(n, 0.02, 0.05, 0.8, 0.1)
    return fade(norm(lp(x, 2500), 0.7))


def footstep(seed):
    r = rng(seed)
    n = int(0.14 * SR)
    x = bp(noise(n, r), 300, 5000) * env_exp(n, 0.025)
    for k in range(6):
        c = bp(noise(int(0.01 * SR), r), 2000, 8000) * env_exp(int(0.01 * SR), 0.002)
        mix_at(x, c, r.uniform(0, 0.06) * SR, 0.4)
    return fade(norm(x, 0.8), 0.0005, 0.02)


def cart_loop(seed=23):
    r = rng(seed)
    dur = 2.0
    n = int((dur + 0.25) * SR)
    x = lp(noise(n, r), 350) * 0.4
    for k in range(4):
        s = k * 0.5 * SR
        for dd in (0.0, 0.06):
            c = bp(noise(int(0.05 * SR), r), 500, 3000) * env_exp(int(0.05 * SR), 0.01)
            mix_at(x, c, s + dd * SR, 0.8)
    return make_loop(norm(x, 0.7), 0.25)


def ore_drop(seed=24):
    r = rng(seed)
    n = int(0.6 * SR)
    x = np.zeros(n)
    for k in range(14):
        c = bp(noise(int(0.03 * SR), r), 700, 5000) * env_exp(int(0.03 * SR), 0.006)
        mix_at(x, c, r.uniform(0, 0.35) * SR, r.uniform(0.3, 0.9))
    x += sine(80, t_axis(0.6)) * env_exp(n, 0.08) * 0.6
    return fade(norm(x, 0.85), 0.0005, 0.05)


def blast(seed=25):
    r = rng(seed)
    n = int(2.5 * SR)
    t = t_axis(2.5)
    boom = sine(45, t) * env_exp(n, 0.35) + sine(32, t) * env_exp(n, 0.6) * 0.6
    burst = lp(noise(n, r), 2500) * env_exp(n, 0.12)
    rumble = lp(noise(n, r), 180) * env_exp(n, 0.8) * 0.8
    x = boom + burst * 0.8 + rumble
    for k in range(25):
        c = bp(noise(int(0.04 * SR), r), 1000, 6000) * env_exp(int(0.04 * SR), 0.008)
        mix_at(x, c, r.uniform(0.2, 1.6) * SR, r.uniform(0.1, 0.35))
    return fade(norm(x, 0.95), 0.0005, 0.2)


def construct(seed=26):
    r = rng(seed)
    n = int(1.4 * SR)
    x = np.zeros(n)
    for k in range(6):
        s = (0.05 + k * 0.2) * SR
        h = pick_hit(100 + k)[: int(0.2 * SR)]
        mix_at(x, h, s, 0.6 if k % 2 else 0.9)
    for k in range(10):
        c = bp(noise(int(0.015 * SR), r), 2500, 8000) * env_exp(int(0.015 * SR), 0.003)
        mix_at(x, c, (1.0 + k * 0.035) * SR, 0.4)
    return fade(norm(x, 0.85))


def repair(seed=27):
    r = rng(seed)
    n = int(0.8 * SR)
    x = np.zeros(n)
    for k, s in enumerate((0.02, 0.28, 0.5)):
        t = t_axis(0.25)
        clank = (sine(1500 + 300 * k, t) + sine(2310 + 200 * k, t) * 0.6) * env_exp(len(t), 0.05)
        clank += bp(noise(len(t), r), 2000, 7000) * env_exp(len(t), 0.01)
        mix_at(x, clank, s * SR, 0.8)
    return fade(norm(x, 0.8))


def steam(seed=28):
    r = rng(seed)
    n = int(1.2 * SR)
    x = hp(noise(n, r), 2500) * env_adsr(n, 0.05, 0.2, 0.6, 0.5)
    return fade(norm(x, 0.6))


# --------------------------------------------------------------------------- UI

def ui_tap():
    t = t_axis(0.05)
    x = sine(1250, t) * env_exp(len(t), 0.012) + sine(2500, t) * env_exp(len(t), 0.006) * 0.3
    return fade(norm(x, 0.7), 0.0005, 0.01)


def whoosh(up=True, seed=30):
    r = rng(seed)
    n = int(0.2 * SR)
    x = noise(n, r)
    y = np.zeros(n)
    chunks = 20
    for i in range(chunks):
        a, b = i * n // chunks, (i + 1) * n // chunks
        fr = (i / chunks) if up else 1 - i / chunks
        y[a:b] = bp(x, 400 + 3000 * fr, 800 + 4000 * fr)[a:b]
    return fade(norm(y * env_adsr(n, 0.05, 0.05, 0.7, 0.08), 0.4))


def ui_error():
    t = t_axis(0.3)
    x = np.zeros(len(t))
    for s in (0.0, 0.14):
        tt = t_axis(0.11)
        b = np.sign(sine(180, tt)) * env_adsr(len(tt), 0.005, 0.02, 0.7, 0.03)
        mix_at(x, lp(b, 1500), s * SR, 0.6)
    return fade(norm(x, 0.6))


def ui_coin():
    t = t_axis(0.5)
    n = len(t)
    x = np.zeros(n)
    for s, f in ((0.0, 1760), (0.07, 2637)):
        tt = t_axis(0.43)
        b = (sine(f, tt) + 0.4 * sine(f * 2.01, tt)) * env_exp(len(tt), 0.12)
        mix_at(x, b, s * SR, 0.7)
    return fade(norm(reverb(x, 0.3, 0.6, 0.2, 31)[: n + int(0.3 * SR)], 0.7))


def ui_purchase():
    n = int(0.7 * SR)
    r = rng(32)
    x = bp(noise(n, r), 2000, 8000) * env_exp(n, 0.01) * 0.6
    x += np.pad(ui_coin(), (int(0.05 * SR), 0))[:n]
    return fade(norm(x, 0.75))


def arpeggio(notes, step=0.07, dur=0.35, wave=tri, seed=33, tail=0.4):
    n = int((step * len(notes) + dur + tail) * SR)
    x = np.zeros(n)
    for i, nn in enumerate(notes):
        tt = t_axis(dur)
        b = (wave(note(nn), tt) * 0.6 + sine(note(nn) * 2, tt) * 0.2) * env_adsr(len(tt), 0.005, 0.08, 0.4, 0.15)
        mix_at(x, b, i * step * SR, 0.7)
    return fade(norm(reverb(x, 0.4, 0.8, 0.22, seed)[:n], 0.75))


def fanfare():
    chords = [["C5", "E5", "G5"], ["F5", "A5", "C6"], ["G5", "B5", "D6", "G6"]]
    n = int(1.4 * SR)
    x = np.zeros(n)
    for i, ch in enumerate(chords):
        dur = 0.22 if i < 2 else 0.8
        tt = t_axis(dur)
        for nn in ch:
            b = lp(saw(note(nn), tt), 3500) * env_adsr(len(tt), 0.01, 0.06, 0.7, 0.12)
            mix_at(x, b, i * 0.2 * SR, 0.25)
    return fade(norm(reverb(x, 0.5, 1.0, 0.25, 34)[:n], 0.8))


def sparkle(seed=35, dur=1.8, notes=("E6", "G#6", "B6", "E7", "B6", "G#6", "E7")):
    r = rng(seed)
    n = int(dur * SR)
    x = np.zeros(n)
    for i, nn in enumerate(notes):
        b = bell(note(nn), 0.9, seed + i)
        mix_at(x, b, (i * 0.09 + r.uniform(0, 0.02)) * SR, 0.5)
    x += hp(noise(n, r), 6000) * env_adsr(n, 0.3, 0.3, 0.2, 0.8) * 0.05
    return fade(norm(reverb(x, 0.2, 1.5, 0.35, seed)[:n], 0.75))


def prestige():
    n = int(3.5 * SR)
    t = t_axis(3.5)
    x = np.zeros(n)
    for nn in ("C3", "G3", "C4", "E4", "G4", "C5"):
        x += lp(saw(note(nn), t) + saw(note(nn) * 1.003, t), 2200) * 0.12
    x *= np.clip(t / 2.2, 0, 1) ** 2 * env_adsr(n, 0.01, 0.01, 1.0, 1.0)
    mix_at(x, blast(36), 2.2 * SR, 0.4)
    mix_at(x, sparkle(37, 1.3), 2.2 * SR, 0.6)
    return fade(norm(x, 0.9))


def alert():
    n = int(0.5 * SR)
    x = np.zeros(n)
    for s, f in ((0.0, 880), (0.18, 660)):
        tt = t_axis(0.16)
        mix_at(x, sine(f, tt) * env_adsr(len(tt), 0.005, 0.02, 0.8, 0.04), s * SR, 0.6)
    return fade(norm(x, 0.65))


def pop():
    t = t_axis(0.08)
    f = 600 * np.exp(-t * 20) + 300
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_exp(len(t), 0.02)
    return fade(norm(x, 0.6))


# --------------------------------------------------------------------------- ambience & music

def stereo(l, r_):
    return np.stack([l, r_], axis=1)


def amb_surface(seed=40, dur=16.0, sr=32000):
    r = rng(seed)
    n = int((dur + 1.0) * sr)
    t = np.arange(n) / sr
    wind = noise(n, r)
    wl = lp(wind, 700, sr) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t))
    wr = lp(np.roll(wind, 1200), 700, sr) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.05 * t + 1))
    birds_l = np.zeros(n)
    birds_r = np.zeros(n)
    for k in range(9):
        s = int(r.uniform(0.5, dur - 1) * sr)
        chirps = r.integers(2, 5)
        for c in range(chirps):
            ln = int(0.08 * sr)
            tt = np.arange(ln) / sr
            f0 = r.uniform(2800, 4200)
            f = f0 + 1200 * np.sin(np.pi * tt / tt[-1])
            ch = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.sin(np.pi * tt / tt[-1])
            tgt = birds_l if r.random() < 0.5 else birds_r
            mix_at(tgt, ch, s + c * int(0.12 * sr), 0.08)
    x = stereo(wl * 0.5 + birds_l, wr * 0.5 + birds_r)
    return make_loop(norm(x, 0.5), 1.0, sr), sr


def amb_mine(seed=41, dur=16.0, sr=32000, deep=False):
    r = rng(seed)
    n = int((dur + 1.0) * sr)
    t = np.arange(n) / sr
    rum = lp(noise(n, r), 120 if not deep else 90, sr) * 2.0
    hum = np.sin(2 * np.pi * (48 if not deep else 36) * t) * (0.15 if not deep else 0.25)
    left = rum + hum
    right = np.roll(rum, 3000) + hum
    for k in range(22 if not deep else 12):
        s = int(r.uniform(0.2, dur - 0.5) * sr)
        ln = int(0.25 * sr)
        tt = np.arange(ln) / sr
        f = r.uniform(1400, 2600)
        drip = np.sin(2 * np.pi * (f + 900 * np.exp(-tt * 40)) * tt) * np.exp(-tt / 0.05)
        tgt = left if r.random() < 0.5 else right
        mix_at(tgt, drip, s, r.uniform(0.05, 0.15))
    for k in range(3):
        s = int(r.uniform(1, dur - 2) * sr)
        ln = int(0.8 * sr)
        cr = lp(noise(ln, r), 500, sr) * np.sin(np.pi * np.arange(ln) / ln) ** 2
        mix_at(left, cr, s, 0.25)
        mix_at(right, cr, s + 400, 0.2)
    if deep:
        shimmer = np.sin(2 * np.pi * 1320 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * t)) * 0.02
        left += shimmer
        right += np.roll(shimmer, 700)
    x = stereo(left, right)
    return make_loop(norm(x, 0.5), 1.0, sr), sr


def music(kind, seed, sr=32000):
    """Loopable music: plucked (Karplus-Strong) arpeggios over pads, bass and light percussion."""
    r = rng(seed)
    if kind == "surface":
        bpm, prog = 96, [["C3", "E4", "G4", "C5"], ["G2", "D4", "G4", "B4"], ["A2", "C4", "E4", "A4"], ["F2", "C4", "F4", "A4"]]
        pattern = [0, 1, 2, 3, 2, 1, 2, 3]
    else:
        bpm, prog = 80, [["A2", "C4", "E4", "A4"], ["F2", "A3", "C4", "F4"], ["C3", "E4", "G4", "C5"], ["G2", "B3", "D4", "G4"]]
        pattern = [0, 2, 1, 3, 1, 2, 3, 2]
    beat = 60.0 / bpm
    bar = beat * 4
    bars = 8
    dur = bar * bars
    n = int((dur + 1.5) * sr)
    left = np.zeros(n)
    right = np.zeros(n)
    global SR
    old = SR
    SR = sr
    try:
        for b in range(bars):
            chord = prog[b % len(prog)]
            base = b * bar
            # pad
            tt = np.arange(int(bar * sr)) / sr
            pad = sum(lp(saw(note(nn) / 2 if i == 0 else note(nn), tt), 1200 if kind == "surface" else 800, sr) for i, nn in enumerate(chord[1:], 1))
            pad *= env_adsr(len(tt), 0.4, 0.3, 0.8, 0.5, sr) * 0.06
            mix_at(left, pad, base * sr, 1.0)
            mix_at(right, pad, base * sr + 90, 1.0)
            # bass
            bt = np.arange(int(beat * 2 * sr)) / sr
            for half in range(2):
                bass = (np.sin(2 * np.pi * note(chord[0]) * bt) + 0.3 * np.sin(4 * np.pi * note(chord[0]) * bt))
                bass *= env_adsr(len(bt), 0.01, 0.2, 0.6, 0.2, sr) * 0.25
                mix_at(left, bass, (base + half * beat * 2) * sr, 1.0)
                mix_at(right, bass, (base + half * beat * 2) * sr, 1.0)
            # plucked arpeggio (eighths)
            for i, pi in enumerate(pattern):
                nn = chord[pi]
                f = note(nn) * (2 if kind == "surface" and pi > 1 else 1)
                pl = karplus(f, beat * 1.5, r, 0.6 if kind == "surface" else 0.35, sr)
                pan = 0.3 + 0.4 * (i % 2)
                mix_at(left, pl, (base + i * beat / 2) * sr, 0.22 * (1 - pan))
                mix_at(right, pl, (base + i * beat / 2) * sr, 0.22 * pan)
            # percussion: shaker on off-beats, soft kick on 1 and 3
            for q in range(8):
                ln = int(0.05 * sr)
                sh = hp(noise(ln, r), 5000, sr) * np.exp(-np.arange(ln) / (0.012 * sr)) * (0.05 if q % 2 else 0.025)
                mix_at(left, sh, (base + q * beat / 2) * sr, 0.8)
                mix_at(right, sh, (base + q * beat / 2) * sr + 60, 0.8)
            for q in (0, 2):
                ln = int(0.2 * sr)
                kt = np.arange(ln) / sr
                kick = np.sin(2 * np.pi * (50 + 80 * np.exp(-kt * 30)) * kt) * np.exp(-kt / 0.08) * 0.35
                mix_at(left, kick, (base + q * beat) * sr, 1.0)
                mix_at(right, kick, (base + q * beat) * sr, 1.0)
        x = stereo(reverb(left, 0.5, 1.5, 0.2, seed, sr)[:n], reverb(right, 0.5, 1.5, 0.2, seed + 1, sr)[:n])
        x = x[: int((dur + 1.0) * sr)]
        return make_loop(norm(x, 0.7), 1.0, sr), sr
    finally:
        SR = old


# --------------------------------------------------------------------------- catalogue

def library():
    """id -> (generator, loop, stereo)."""
    lib = {
        "sfx_pick_hit_1": (lambda: pick_hit(1), False), "sfx_pick_hit_2": (lambda: pick_hit(2), False),
        "sfx_pick_hit_3": (lambda: pick_hit(3), False), "sfx_rock_break": (rock_break, False),
        "sfx_drill_loop": (drill_loop, True), "sfx_machine_hum_loop": (machine_hum, True),
        "sfx_crusher_loop": (crusher_loop, True), "sfx_conveyor_loop": (conveyor_loop, True),
        "sfx_generator_loop": (generator_loop, True), "sfx_pump_loop": (pump_loop, True),
        "sfx_lift_motor_loop": (lift_motor_loop, True), "sfx_lift_bell": (lambda: bell(988, 1.4, 20), False),
        "sfx_truck_loop": (truck_loop, True), "sfx_truck_horn": (horn, False),
        "sfx_footstep_1": (lambda: footstep(51), False), "sfx_footstep_2": (lambda: footstep(52), False),
        "sfx_footstep_3": (lambda: footstep(53), False), "sfx_footstep_4": (lambda: footstep(54), False),
        "sfx_cart_loop": (cart_loop, True), "sfx_ore_drop": (ore_drop, False), "sfx_blast": (blast, False),
        "sfx_construct": (construct, False), "sfx_repair": (repair, False), "sfx_steam": (steam, False),
        "ui_tap": (ui_tap, False), "ui_open": (lambda: whoosh(True), False), "ui_close": (lambda: whoosh(False, 39), False),
        "ui_error": (ui_error, False), "ui_coin": (ui_coin, False), "ui_purchase": (ui_purchase, False),
        "ui_upgrade": (lambda: arpeggio(["C5", "E5", "G5", "C6"]), False),
        "ui_hire": (lambda: arpeggio(["G4", "C5", "E5"], 0.06, 0.3, tri, 38), False),
        "ui_quest": (fanfare, False), "ui_achievement": (lambda: sparkle(42, 1.4, ("C6", "E6", "G6", "C7")), False),
        "ui_discovery": (sparkle, False), "ui_prestige": (prestige, False), "ui_alert": (alert, False), "ui_toast": (pop, False),
    }
    return lib


def check(sid, data, loop):
    """Automated sanity checks (we cannot listen in CI): audible, no clipping,
    no NaN, small DC offset, and loops that join without a click."""
    x = np.asarray(data, dtype=float)
    problems = []
    if not np.all(np.isfinite(x)):
        problems.append("non-finite samples")
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x ** 2)))
    if peak > 0.999:
        problems.append(f"clipping (peak {peak:.3f})")
    if rms < 0.01:
        problems.append(f"too quiet (rms {rms:.4f})")
    mono = x if x.ndim == 1 else x.mean(axis=1)
    if abs(float(np.mean(mono))) > 0.02:
        problems.append(f"DC offset {float(np.mean(mono)):.3f}")
    if loop:
        jump = float(np.max(np.abs((x[0] - x[-1]))))
        step = float(np.percentile(np.abs(np.diff(mono)), 99)) + 1e-6
        if jump > max(0.08, 4 * step):
            problems.append(f"loop seam jump {jump:.3f}")
    return {"peak": round(peak, 4), "rms": round(rms, 4), "problems": problems}


def write_wav(path, data, sr):
    data = np.asarray(data)
    ch = 1 if data.ndim == 1 else data.shape[1]
    pcm = np.clip(data, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    raw = pcm.tobytes()
    with open(path, "wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVE")
        fh.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, ch, sr, sr * ch * 2, ch * 2, 16))
        fh.write(b"data" + struct.pack("<I", len(raw)) + raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "assets/generated/audio"))
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    lib = library()
    extra = {
        "amb_surface": lambda: amb_surface(),
        "amb_mine": lambda: amb_mine(),
        "amb_deep": lambda: amb_mine(43, deep=True),
        "mus_surface": lambda: music("surface", 60),
        "mus_mine": lambda: music("mine", 61),
    }
    ids = list(lib.keys()) + list(extra.keys())
    if args.list:
        print("\n".join(ids))
        return 0
    only = set(x for x in args.only.split(",") if x)
    os.makedirs(args.out, exist_ok=True)
    manifest = {}
    failures = []
    for sid in ids:
        if only and sid not in only:
            continue
        if sid in lib:
            fn, loop = lib[sid]
            data, sr = fn(), SR
        else:
            data, sr = extra[sid]()
            loop = True
        path = os.path.join(args.out, sid + ".wav")
        report = check(sid, data, loop)
        if report["problems"]:
            failures.append(f"{sid}: {', '.join(report['problems'])}")
        write_wav(path, data, sr)
        n = len(data)
        manifest[sid] = {"file": "res://" + os.path.relpath(path, REPO).replace(os.sep, "/"), "loop": loop,
                         "seconds": round(n / sr, 3), "sample_rate": sr, "channels": 1 if np.asarray(data).ndim == 1 else 2,
                         "frames": n}
        manifest[sid].update({"peak": report["peak"], "rms": report["rms"]})
        print(f"{sid:24s} {n / sr:6.2f}s rms {report['rms']:.3f} peak {report['peak']:.3f} {'loop' if loop else ''}")
    if failures:
        print("audio check failed:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    if not only:
        with open(os.path.join(args.out, "audio_manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=1, sort_keys=True)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
