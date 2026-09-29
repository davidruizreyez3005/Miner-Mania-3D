#!/usr/bin/env python3
"""On-device test of the exported APK (an Android emulator or a phone).

Installs the APK, launches it and plays the first minutes with real touch
input (adb `input`, which goes through Android's input pipeline like a
finger), following the game through the lines it logs:

    [boot] ...                 version, window/view size, renderer
    [state] A -> B             every game-state transition
    [save] written: ...        every save (claim time, money)

Steps: title screen; tap "Start mining"; the world loads; skip the first
tutorial tip; pan the camera (the picture must change); open the pause menu
and resume by touch; pause and resume with the Back key; let the mine run
(autosaves must show the claim clock advancing); send the app to the
background (it must save) and bring it back (same process). Fails on any
crash, ANR, script error or engine error. Writes a JSON report, a Markdown
summary, the logcat and screenshots to --out.

    python tools/device/device_smoke.py --apk build/apk/MinerMania3D-debug.apk \
        --sdk "$ANDROID_SDK" --out build/device

Tap positions come from the UI layout code for the 720x1280 design size
(see TARGETS) and are mapped to the screen with the window/view sizes from
the [boot] line, so they follow the canvas_items/expand stretch.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PACKAGE = "com.minermania.mm3d"

LOG_RE = re.compile(r"^\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d+\s+(\d+)\s+(\d+)\s+([VDIWEFA])\s+(.*?)\s*: (.*)$")
BOOT_RE = re.compile(r"\[boot\] (.*) window \((\d+), (\d+)\), view \(([\d.]+), ([\d.]+)\), (.*)$")
SAVE_RE = re.compile(r"\[save\] (written|FAILED): claim time (\d+) s, money (\d+)")
GODOT_ERROR_PREFIXES = ("SCRIPT ERROR", "USER SCRIPT ERROR", "ERROR", "USER ERROR")
# What Godot logs when it probes Vulkan on a device without it and switches to
# OpenGL ES (only accepted when the run is meant to test that fallback).
VULKAN_PROBE_ERRORS = ("vkEnumeratePhysicalDevices reported zero accessible devices",
                       "rendering_context_driver_vulkan.cpp")
FRAME_STATS_RE = re.compile(r"app_time_stats: avg=([\d.]+)ms")


def targets(w: float, h: float) -> dict:
    """Centres of the controls the test taps, in view (content) coordinates."""
    card_w = min(w - 32.0, 680.0)
    return {
        # main.gd _show_menu: the stack at the bottom of the title screen
        # (version caption, Settings, Start mining) - a fresh install has no
        # Continue button.
        "start": (w * 0.5, h - 301.0),
        # tutorial_overlay.gd _layout_card: the first tip (no anchor) sits at
        # 60% of the height; "Skip tips" is its bottom-left button.
        "skip_tips": ((w - card_w) * 0.5 + 85.0, h * 0.60 + 128.0),
        # hud.gd _build_top: the pause button at the right end of the top bar.
        "pause": (w - 64.0, 62.0),
        # pause_panel.gd: centred popup, "Resume" is its first button.
        "resume": (w * 0.5, h * 0.5 - 126.0),
    }


class Failure(Exception):
    pass


class Device:
    def __init__(self, adb: str, serial: str):
        self.adb = adb
        self.serial = serial

    def run(self, *args: str, timeout: float = 60.0, check: bool = True, binary: bool = False):
        cmd = [self.adb, "-s", self.serial, *args]
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if check and r.returncode != 0:
            raise Failure(f"{' '.join(args[:3])} failed: {r.stderr.decode(errors='replace').strip()[:400]}")
        return r.stdout if binary else r.stdout.decode(errors="replace").replace("\r", "")

    def shell(self, cmd: str, timeout: float = 60.0, check: bool = True) -> str:
        return self.run("shell", cmd, timeout=timeout, check=check)

    def pid(self) -> str:
        return self.shell(f"pidof {PACKAGE}", check=False).strip()

    def tap(self, x: float, y: float) -> None:
        self.shell(f"input tap {int(round(x))} {int(round(y))}")

    def swipe(self, a: tuple, b: tuple, ms: int) -> None:
        self.shell(f"input swipe {int(a[0])} {int(a[1])} {int(b[0])} {int(b[1])} {ms}")

    def key(self, code: str) -> None:
        self.shell(f"input keyevent {code}")

    def screenshot(self, path: Path) -> None:
        path.write_bytes(self.run("exec-out", "screencap", "-p", binary=True, timeout=60))

    def frame(self) -> tuple:
        """Raw RGBA frame: (width, height, bytes)."""
        raw = self.run("exec-out", "screencap", binary=True, timeout=60)
        w = int.from_bytes(raw[0:4], "little")
        h = int.from_bytes(raw[4:8], "little")
        return w, h, raw[len(raw) - w * h * 4:]


class Logcat:
    """Streams `adb logcat` to a file and keeps the parsed lines in memory."""

    def __init__(self, dev: Device, path: Path):
        dev.run("logcat", "-c", check=False)
        self.lines: list = []
        self.lock = threading.Lock()
        self.file = path.open("w", encoding="utf-8")
        self.proc = subprocess.Popen([dev.adb, "-s", dev.serial, "logcat", "-v", "threadtime"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self) -> None:
        for raw in self.proc.stdout:
            line = raw.decode(errors="replace").rstrip("\r\n")
            self.file.write(line + "\n")
            m = LOG_RE.match(line)
            entry = {"pid": m.group(1), "prio": m.group(3), "tag": m.group(4), "msg": m.group(5)} if m \
                else {"pid": "", "prio": "", "tag": "", "msg": line}
            with self.lock:
                self.lines.append(entry)

    def mark(self) -> int:
        with self.lock:
            return len(self.lines)

    def game(self, since: int = 0) -> list:
        """Messages the game logged (tag "godot") since a mark."""
        with self.lock:
            return [e["msg"] for e in self.lines[since:] if e["tag"] == "godot"]

    def wait(self, pattern: str, timeout: float, since: int = 0) -> tuple:
        """Waits for a game log line matching `pattern`; returns (message, index)."""
        rx = re.compile(pattern)
        end = time.monotonic() + timeout
        idx = since
        while True:
            with self.lock:
                batch = self.lines[idx:]
                start = idx
                idx = len(self.lines)
            for i, e in enumerate(batch):
                if e["tag"] == "godot" and rx.search(e["msg"]):
                    return e["msg"], start + i + 1
            if time.monotonic() > end:
                raise Failure(f"timed out after {timeout:.0f}s waiting for '{pattern}'")
            time.sleep(0.25)

    def frame_ms(self, pid: str) -> float | None:
        """Median frame time the emulator's GL layer reports for the game."""
        with self.lock:
            vals = [float(m.group(1)) for e in self.lines if e["pid"] == pid
                    for m in [FRAME_STATS_RE.search(e["msg"])] if m]
        return sorted(vals)[len(vals) // 2] if vals else None

    def problems(self, allowed: tuple = ()) -> dict:
        crashes, errors, gaps, expected = [], [], [], []
        with self.lock:
            lines = list(self.lines)
        for i, e in enumerate(lines):
            msg, tag = e["msg"], e["tag"]
            if tag == "ndk_translation" and "Undefined instruction" in msg:
                gaps.append(msg)
            if tag == "AndroidRuntime" and "FATAL EXCEPTION" in msg:
                crashes.append(msg)
            elif tag == "libc" and "Fatal signal" in msg:
                crashes.append(msg)
            elif tag == "ActivityManager" and (f"ANR in {PACKAGE}" in msg or
                                                (f"Process {PACKAGE}" in msg and "has died" in msg)):
                crashes.append(msg)
            elif tag == "godot" and e["prio"] in ("E", "F") and msg.lstrip().startswith(GODOT_ERROR_PREFIXES):
                where = ""
                for j in range(i + 1, min(i + 6, len(lines))):
                    if lines[j]["tag"] == "godot" and lines[j]["msg"].strip().startswith("at:"):
                        where = lines[j]["msg"].strip()
                        break
                text = f"{msg.strip()} {where}".strip()
                (expected if any(a in text for a in allowed) else errors).append(text)
        return {"crashes": crashes, "errors": errors, "translation_gaps": gaps, "expected_messages": expected}

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.thread.join(timeout=10)
        self.file.close()


def frame_diff(a: tuple, b: tuple, top: int, bottom: int, right: int = 0) -> float:
    """Mean absolute grey-level difference (0-255) between two frames over the
    rows [top, h - bottom) and columns [0, w - right), on an 8-pixel grid."""
    w, h, pa = a
    _, _, pb = b
    total, n = 0, 0
    for y in range(top, h - bottom, 8):
        row = y * w * 4
        for x in range(0, w - right, 8):
            i = row + x * 4
            ga = pa[i] * 3 + pa[i + 1] * 6 + pa[i + 2]
            gb = pb[i] * 3 + pb[i + 1] * 6 + pb[i + 2]
            total += abs(ga - gb)
            n += 1
    return total / max(n, 1) / 10.0


class Run:
    def __init__(self, args):
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.dev = Device(args.adb or str(Path(args.sdk) / "platform-tools" / "adb"), args.serial)
        self.steps: list = []
        self.report: dict = {"label": args.label, "package": PACKAGE, "apk": str(args.apk), "serial": args.serial,
                             "steps": self.steps}
        self.log: Logcat | None = None
        self.scale = (1.0, 1.0)
        self.view = (720.0, 1280.0)
        self.shots: list = []
        self.slow = args.slow

    def t(self, s: float) -> float:
        return s * self.slow

    def step(self, name: str, fn) -> None:
        t0 = time.monotonic()
        entry = {"name": name, "ok": False, "seconds": 0.0, "detail": ""}
        self.steps.append(entry)
        print(f"--- {name}", flush=True)
        try:
            entry["detail"] = fn() or ""
            entry["ok"] = True
        except Failure as e:
            entry["detail"] = str(e)
            raise
        finally:
            entry["seconds"] = round(time.monotonic() - t0, 1)
            print(f"    {'ok' if entry['ok'] else 'FAILED'} ({entry['seconds']}s) {entry['detail']}", flush=True)

    def shot(self, name: str) -> None:
        p = self.out / f"{len(self.shots) + 1:02d}_{name}.png"
        try:
            self.dev.screenshot(p)
            self.shots.append(p.name)
        except (Failure, subprocess.TimeoutExpired) as e:
            print(f"    (screenshot {name} failed: {e})", flush=True)

    def screen(self, name: str) -> tuple:
        x, y = targets(*self.view)[name]
        return x * self.scale[0], y * self.scale[1]

    def tap(self, name: str) -> None:
        self.dev.tap(*self.screen(name))

    # ------------------------------------------------------------------ steps

    def install(self) -> str:
        self.dev.run("uninstall", PACKAGE, check=False, timeout=120)
        t0 = time.monotonic()
        out = self.dev.run("install", "-r", "-t", str(self.args.apk), timeout=self.t(600))
        if "Success" not in out:
            raise Failure("install did not report Success: " + out.strip()[-300:])
        dump = self.dev.shell(f"dumpsys package {PACKAGE}")
        abi = re.search(r"primaryCpuAbi=(\S+)", dump)
        ver = re.search(r"versionName=(\S+)", dump)
        self.report["primary_abi"] = abi.group(1) if abi else "?"
        self.report["version_name"] = ver.group(1) if ver else "?"
        self.report["install_s"] = round(time.monotonic() - t0, 1)
        comp = self.dev.shell(f"cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {PACKAGE}")
        self.component = comp.strip().splitlines()[-1].strip()
        if "/" not in self.component:
            raise Failure("no launcher activity: " + comp.strip())
        return f"version {self.report['version_name']}, ABI {self.report['primary_abi']}, " \
               f"launcher {self.component}, {self.report['install_s']}s"

    def launch(self) -> str:
        self.log = Logcat(self.dev, self.out / "logcat.txt")
        t0 = time.monotonic()
        am = self.dev.shell(f"am start -W -n {self.component}", timeout=self.t(120))
        total = re.search(r"TotalTime: (\d+)", am)
        self.report["activity_start_ms"] = int(total.group(1)) if total else None
        msg, _ = self.log.wait(r"^\[boot\]", self.t(180))
        m = BOOT_RE.search(msg)
        if not m:
            raise Failure("unreadable boot line: " + msg)
        win = (float(m.group(2)), float(m.group(3)))
        self.view = (float(m.group(4)), float(m.group(5)))
        self.scale = (win[0] / self.view[0], win[1] / self.view[1])
        self.report["boot_line"] = msg
        self.report["window"] = [int(win[0]), int(win[1])]
        self.report["view"] = list(self.view)
        self.report["renderer"] = m.group(6)
        driver = m.group(6).split(" ")[0].split("/")[-1]
        if self.args.expect_driver and driver != self.args.expect_driver:
            raise Failure(f"the game runs on {driver}, expected {self.args.expect_driver}: {m.group(6)}")
        first = self.dev.frame()
        self.log.wait(r"^\[state\] BOOT -> MAIN_MENU", self.t(300))
        self.report["title_s"] = round(time.monotonic() - t0, 1)
        self.pid0 = self.dev.pid()
        if not self.pid0:
            raise Failure("the game process is not running")
        # The splash stays up until the title's first frame is drawn.
        end = time.monotonic() + self.t(30)
        while time.monotonic() < end and frame_diff(first, self.dev.frame(), 0, 0) < 3.0:
            time.sleep(1.0)
        self.shot("title")
        return f"title screen after {self.report['title_s']}s; {m.group(6)}; window {int(win[0])}x{int(win[1])}"

    def start_game(self) -> str:
        mark = self.log.mark()
        t0 = time.monotonic()
        self.tap("start")
        _, i = self.log.wait(r"^\[state\] MAIN_MENU -> LOADING", self.t(30), mark)
        time.sleep(1)
        self.shot("loading")
        _, i = self.log.wait(r"^\[state\] LOADING -> PLAYING", self.t(600), i)
        self.report["world_load_s"] = round(time.monotonic() - t0, 1)
        self.log.wait(r"^\[state\] PLAYING -> TUTORIAL", self.t(120), i)
        time.sleep(self.t(4))
        self.shot("tutorial")
        return f"tap on Start mining; playing after {self.report['world_load_s']}s; the first tip is shown"

    def skip_tutorial(self) -> str:
        mark = self.log.mark()
        self.tap("skip_tips")
        self.log.wait(r"^\[state\] TUTORIAL -> PLAYING", self.t(30), mark)
        time.sleep(self.t(3))
        self.shot("playing")
        return "tap on Skip tips closed the tutorial"

    def camera(self) -> str:
        # Compare only the 3D view between the toasts (top) and the action
        # buttons (bottom), left of the level strip: HUD numbers and toasts
        # change on their own.
        region = (int(260 * self.scale[1]), int(330 * self.scale[1]), int(120 * self.scale[0]))
        still_a = self.dev.frame()
        time.sleep(self.t(3))
        still_b = self.dev.frame()
        idle = frame_diff(still_a, still_b, *region)
        w, h = still_b[0:2]
        self.dev.swipe((w * 0.72, h * 0.55), (w * 0.28, h * 0.40), 700)
        # Software-rendered emulators draw a frame every second or two: poll.
        pan, end = 0.0, time.monotonic() + self.t(45)
        need = max(3.0 * idle, 6.0)
        while time.monotonic() < end:
            time.sleep(1.5)
            pan = max(pan, frame_diff(still_b, self.dev.frame(), *region))
            if pan >= need:
                break
        self.shot("camera_pan")
        self.report["camera"] = {"idle_diff": round(idle, 2), "pan_diff": round(pan, 2)}
        if pan < need:
            raise Failure(f"the picture barely changed after a pan swipe (diff {pan:.1f}, idle {idle:.1f})")
        return f"pan swipe moved the view (image difference {pan:.1f} vs {idle:.1f} idle)"

    def pause_touch(self) -> str:
        mark = self.log.mark()
        self.tap("pause")
        _, i = self.log.wait(r"^\[state\] PLAYING -> PAUSED", self.t(20), mark)
        time.sleep(self.t(2))
        self.shot("paused")
        self.tap("resume")
        self.log.wait(r"^\[state\] PAUSED -> PLAYING", self.t(20), i)
        return "pause button and Resume by touch"

    def back_key(self) -> str:
        mark = self.log.mark()
        self.dev.key("KEYCODE_BACK")
        _, i = self.log.wait(r"^\[state\] PLAYING -> PAUSED", self.t(20), mark)
        time.sleep(self.t(1))
        self.dev.key("KEYCODE_BACK")
        self.log.wait(r"^\[state\] PAUSED -> PLAYING", self.t(20), i)
        return "Back pauses, Back again resumes"

    def simulation(self) -> str:
        mark = self.log.mark()
        saves = []
        idx = mark
        # The mine runs in real time on a phone; software-rendered emulators
        # draw so slowly that the capped frame step makes it run slower.
        end = time.monotonic() + self.t(420)
        while len(saves) < 2:
            msg, idx = self.log.wait(r"^\[save\] ", max(1.0, end - time.monotonic()), idx)
            m = SAVE_RE.search(msg)
            if not m or m.group(1) != "written":
                raise Failure("save failed: " + msg)
            saves.append((int(m.group(2)), int(m.group(3))))
        self.report["autosaves"] = saves
        if saves[1][0] <= saves[0][0]:
            raise Failure(f"the claim clock did not advance between autosaves: {saves}")
        self.shot("running")
        return f"autosaves at claim time {saves[0][0]}s and {saves[1][0]}s (money {saves[1][1]})"

    def background(self) -> str:
        mark = self.log.mark()
        self.dev.key("KEYCODE_HOME")
        self.log.wait(r"^\[save\] written", self.t(30), mark)
        time.sleep(self.t(5))
        self.dev.shell(f"am start -W -n {self.component}", timeout=self.t(60))
        time.sleep(self.t(6))
        pid = self.dev.pid()
        if pid != self.pid0:
            raise Failure(f"the game restarted instead of resuming (pid {self.pid0} -> {pid or 'none'})")
        self.shot("resumed")
        return "saved when sent to the background, resumed in the same process"

    def stability(self) -> str:
        time.sleep(self.t(15))
        pid = self.dev.pid()
        if pid != self.pid0:
            raise Failure(f"the game process is gone (pid {self.pid0} -> {pid or 'none'})")
        mem = self.dev.shell(f"dumpsys meminfo {PACKAGE}", check=False)
        pss = re.search(r"TOTAL PSS:\s+(\d+)", mem) or re.search(r"TOTAL\s+(\d+)", mem)
        self.report["memory_pss_mb"] = round(int(pss.group(1)) / 1024.0, 1) if pss else None
        return f"still running; memory (PSS) {self.report['memory_pss_mb']} MB"

    # -------------------------------------------------------------------- run

    def execute(self) -> bool:
        ok = True
        try:
            self.step("install", self.install)
            self.step("launch to the title screen", self.launch)
            self.step("touch: start a new claim, world loads", self.start_game)
            self.step("touch: skip the tutorial tip", self.skip_tutorial)
            self.step("touch: camera pan", self.camera)
            self.step("touch: pause menu and resume", self.pause_touch)
            self.step("Back key: pause and resume", self.back_key)
            self.step("simulation runs (autosaves)", self.simulation)
            self.step("background and resume", self.background)
            self.step("stability", self.stability)
        except Failure as e:
            ok = False
            print(f"FAILED: {e}", flush=True)
            self.shot("failure")
        except subprocess.TimeoutExpired as e:
            ok = False
            self.steps.append({"name": "adb", "ok": False, "seconds": 0.0, "detail": f"adb timed out: {e}"})
            print(f"FAILED: adb timed out: {e}", flush=True)
        time.sleep(1)
        if self.log:
            allowed = VULKAN_PROBE_ERRORS if self.args.expect_driver == "opengl3" else ()
            probs = self.log.problems(allowed)
            self.report["crashes"] = probs["crashes"]
            self.report["engine_errors"] = probs["errors"]
            self.report["expected_fallback_messages"] = probs["expected_messages"]
            self.report["translation_gaps"] = probs["translation_gaps"]
            self.report["emulator_frame_ms_median"] = self.log.frame_ms(getattr(self, "pid0", "") or "")
            self.report["game_log"] = self.log.game()[-400:]
            self.log.close()
            if probs["crashes"]:
                ok = False
                print("CRASH: " + " | ".join(probs["crashes"][:5]), flush=True)
            if probs["translation_gaps"]:
                print("The emulator's ARM translation (ndk_translation) cannot execute an instruction of the "
                      "arm64 build: " + probs["translation_gaps"][0], flush=True)
            if probs["errors"]:
                ok = False
                print(f"{len(probs['errors'])} engine/script errors:\n  " + "\n  ".join(probs["errors"][:20]), flush=True)
        self.report["screenshots"] = self.shots
        self.report["passed"] = ok and all(s["ok"] for s in self.steps)
        (self.out / "device_report.json").write_text(json.dumps(self.report, indent=2), encoding="utf-8")
        (self.out / "device_report.md").write_text(self.markdown(), encoding="utf-8")
        return self.report["passed"]

    def markdown(self) -> str:
        r = self.report
        title = f"On-device test ({r['label']})" if r.get("label") else "On-device test"
        lines = [f"### {title}: {'PASSED' if r['passed'] else 'FAILED'}", ""]
        if r.get("renderer"):
            lines.append(f"- {PACKAGE} {r.get('version_name', '?')} on `{r.get('primary_abi', '?')}`, "
                         f"window {r.get('window')}, renderer {r.get('renderer')}")
        for k, label in (("title_s", "title screen after launch"), ("world_load_s", "world loaded after tap"),
                         ("memory_pss_mb", "memory PSS (MB)"),
                         ("emulator_frame_ms_median", "frame time on this software-rendered emulator (ms, median)")):
            if r.get(k) is not None:
                lines.append(f"- {label}: {r[k]}")
        lines += ["", "| Step | Result | Time | Detail |", "| --- | --- | --- | --- |"]
        for s in self.steps:
            detail = str(s["detail"]).replace("|", "/")
            lines.append(f"| {s['name']} | {'ok' if s['ok'] else 'FAILED'} | {s['seconds']}s | {detail} |")
        if r.get("crashes"):
            lines += ["", "**Crashes:** " + "; ".join(r["crashes"][:5])]
        if r.get("translation_gaps"):
            lines += ["", "**ARM translation gap:** the emulator's ndk_translation cannot execute an instruction of "
                      "the arm64 engine binary (`" + r["translation_gaps"][0] + "`); real arm64 devices run it natively."]
        if r.get("expected_fallback_messages"):
            lines += ["", f"Expected while switching to OpenGL ES ({len(r['expected_fallback_messages'])}): "
                      + "; ".join(f"`{m[:120]}`" for m in r["expected_fallback_messages"][:3])]
        if r.get("engine_errors"):
            lines += ["", f"**Engine/script errors ({len(r['engine_errors'])}):**", ""]
            lines += [f"- `{e[:300]}`" for e in r["engine_errors"][:15]]
        return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apk", required=True, type=Path)
    ap.add_argument("--sdk", default="", help="Android SDK with platform-tools (for adb)")
    ap.add_argument("--adb", default="", help="adb binary (default: <sdk>/platform-tools/adb)")
    ap.add_argument("--serial", default="emulator-5554")
    ap.add_argument("--out", default="build/device")
    ap.add_argument("--slow", type=float, default=1.0, help="multiply every timeout (slow devices)")
    ap.add_argument("--label", default="", help="name of this run in the report (e.g. the build variant)")
    ap.add_argument("--expect-driver", default="", help="fail unless the game renders with this driver (vulkan, opengl3)")
    args = ap.parse_args()
    if not args.apk.is_file():
        print(f"error: {args.apk} not found", file=sys.stderr)
        return 2
    if not args.adb and not args.sdk:
        print("error: pass --sdk or --adb", file=sys.stderr)
        return 2
    run = Run(args)
    passed = run.execute()
    print(("PASSED" if passed else "FAILED") + f" - report in {run.out}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
