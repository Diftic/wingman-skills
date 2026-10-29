"""NavPoint Linux probe: can NavPoint see Star Citizen from inside this Wingman?

Runs inside Wingman's own Python, so it tests exactly the environment NavPoint
would run in. Read-only: it installs nothing, sends nothing anywhere and changes
no settings. Kept free of Wingman imports so it can be tested on its own.

Only the small top-right corner of the game is saved, never a full screenshot.
Process command lines are not stored, and the home folder is written as "~".
"""

import ctypes
import ctypes.util
import datetime
import json
import os
import platform
import re
import shutil
import sys
import time
import zipfile

CAPTURE_W, CAPTURE_H = 675, 175  # NavPoint's overlay block, right edge of the game client area
TITLE = "star citizen"
HOME = os.path.expanduser("~")


def mask(text):
    return str(text).replace(HOME, "~") if HOME and HOME not in ("/", "~") else str(text)


def guarded(fn, *args):
    """Run one check; a failure becomes part of the report instead of ending the probe."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - the failure is the finding
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def wine_version():
    """Wine's version string when this Python runs under Wine, else ''."""
    if sys.platform != "win32":
        return ""
    try:
        fn = ctypes.WinDLL("ntdll").wine_get_version
    except (AttributeError, OSError):
        return ""
    fn.restype = ctypes.c_char_p
    return fn().decode()


def system_info():
    distro = ""
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            distro = dict(line.rstrip().split("=", 1) for line in fh if "=" in line).get("PRETTY_NAME", "").strip('"')
    except OSError:
        pass
    env = {k: os.environ.get(k, "") for k in (
        "XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY", "XDG_CURRENT_DESKTOP",
        "DESKTOP_SESSION", "GDK_SCALE", "QT_SCALE_FACTOR")}
    return {"sys_platform": sys.platform, "wine": wine_version(), "platform": platform.platform(),
            "distro": distro, "python": sys.version.split()[0], "frozen": bool(getattr(sys, "frozen", False)),
            "executable": mask(sys.executable), "env": env}


def modules():
    found = {}
    for name in ("mss", "PIL", "numpy", "onnxruntime", "cv2"):
        try:
            mod = __import__(name)
            found[name] = getattr(mod, "__version__", "present")
        except Exception as exc:  # noqa: BLE001 - any import failure is the answer
            found[name] = f"missing ({type(exc).__name__})"
    try:
        import onnxruntime
        found["onnxruntime_providers"] = onnxruntime.get_available_providers()
    except Exception:  # noqa: BLE001
        pass
    found["libX11"] = ctypes.util.find_library("X11") or ""
    return found


def processes():
    """Names of relevant processes and whether they are Windows programs. No command lines kept."""
    if not os.path.isdir("/proc"):
        return {"skipped": "no /proc (not a Linux process view)"}
    patterns = {
        "star_citizen": re.compile(r"starcitizen\.exe", re.I),
        "rsi_launcher": re.compile(r"rsi launcher", re.I),
        "wingman": re.compile(r"wingman", re.I),
        "wine_or_proton": re.compile(r"(^|/)(wine|wine64|wineserver|wine64-preloader)\b|proton", re.I),
        "gamescope": re.compile(r"gamescope", re.I),
        "lutris": re.compile(r"lutris", re.I),
        "steam": re.compile(r"(^|/)steam\b", re.I),
    }
    found = {key: [] for key in patterns}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except OSError:
            continue
        if not cmd:
            continue
        exe = os.path.basename(cmd.split(" ")[0])
        for key, pattern in patterns.items():
            if pattern.search(cmd) and len(found[key]) < 5:
                found[key].append({"exe": mask(exe)[:60], "windows_exe": ".exe" in cmd.lower()})
    return found


class _X11:
    """The few libX11 calls needed to name the focused window and place it on screen."""

    def __init__(self):
        path = ctypes.util.find_library("X11") or "libX11.so.6"
        x = ctypes.CDLL(path)
        vp, ul, ui, ci = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint, ctypes.c_int
        x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [ctypes.c_char_p], vp
        x.XDefaultRootWindow.argtypes, x.XDefaultRootWindow.restype = [vp], ul
        x.XInternAtom.argtypes, x.XInternAtom.restype = [vp, ctypes.c_char_p, ci], ul
        x.XGetWindowProperty.argtypes = [vp, ul, ul, ctypes.c_long, ctypes.c_long, ci, ul,
                                         ctypes.POINTER(ul), ctypes.POINTER(ci), ctypes.POINTER(ul),
                                         ctypes.POINTER(ul), ctypes.POINTER(ctypes.c_void_p)]
        x.XGetWindowProperty.restype = ci
        x.XGetGeometry.argtypes = [vp, ul, ctypes.POINTER(ul), ctypes.POINTER(ci), ctypes.POINTER(ci),
                                   ctypes.POINTER(ui), ctypes.POINTER(ui), ctypes.POINTER(ui), ctypes.POINTER(ui)]
        x.XTranslateCoordinates.argtypes = [vp, ul, ul, ci, ci, ctypes.POINTER(ci), ctypes.POINTER(ci),
                                            ctypes.POINTER(ul)]
        x.XFree.argtypes, x.XCloseDisplay.argtypes = [vp], [vp]
        self.x = x
        self.display = x.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError(f"XOpenDisplay failed (DISPLAY={os.environ.get('DISPLAY', '')!r})")
        self.root = x.XDefaultRootWindow(self.display)

    def prop(self, window, name, as_text):
        x, ul, ci = self.x, ctypes.c_ulong, ctypes.c_int
        atom = x.XInternAtom(self.display, name.encode(), 0)
        kind, fmt, count, after, data = ul(), ci(), ul(), ul(), ctypes.c_void_p()
        status = x.XGetWindowProperty(self.display, window, atom, 0, 1024, 0, 0, ctypes.byref(kind),
                                      ctypes.byref(fmt), ctypes.byref(count), ctypes.byref(after),
                                      ctypes.byref(data))
        if status != 0 or not data.value or count.value == 0:
            return None
        try:
            if as_text:
                raw = ctypes.string_at(data.value, count.value * (fmt.value // 8))
                return raw.replace(b"\0", b" | ").decode("utf-8", "replace").strip(" |")
            return ctypes.cast(data, ctypes.POINTER(ul))[0]  # format-32 items are C longs
        finally:
            x.XFree(data)

    def geometry(self, window):
        ul, ui, ci = ctypes.c_ulong, ctypes.c_uint, ctypes.c_int
        root, gx, gy, w, h, border, depth = ul(), ci(), ci(), ui(), ui(), ui(), ui()
        self.x.XGetGeometry(self.display, window, ctypes.byref(root), ctypes.byref(gx), ctypes.byref(gy),
                            ctypes.byref(w), ctypes.byref(h), ctypes.byref(border), ctypes.byref(depth))
        ax, ay, child = ci(), ci(), ul()
        self.x.XTranslateCoordinates(self.display, window, self.root, 0, 0,
                                     ctypes.byref(ax), ctypes.byref(ay), ctypes.byref(child))
        return {"x": ax.value, "y": ay.value, "width": w.value, "height": h.value}

    def close(self):
        self.x.XCloseDisplay(self.display)


def active_window_x11():
    xs = _X11()
    try:
        wid = xs.prop(xs.root, "_NET_ACTIVE_WINDOW", as_text=False)
        if not wid:
            return {"ok": False, "why": "no _NET_ACTIVE_WINDOW (window manager does not report focus to X11)"}
        titles = [t for t in (xs.prop(wid, "_NET_WM_NAME", True), xs.prop(wid, "WM_NAME", True)) if t]
        wm_class = xs.prop(wid, "WM_CLASS", True) or ""
        return {"ok": True, "api": "x11", "id": hex(wid), "titles": [mask(t) for t in titles],
                "wm_class": mask(wm_class), "geometry": xs.geometry(wid),
                "is_star_citizen": any(TITLE in t.lower() for t in titles)}
    finally:
        xs.close()


def active_window_win32():
    """NavPoint's own Windows check, for a Wingman running under Wine."""
    from ctypes import wintypes
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = wintypes.HWND
    handle = user.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(512)
    user.GetWindowTextW(handle, title, 512)
    rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
    user.GetClientRect(handle, ctypes.byref(rect))
    user.ClientToScreen(handle, ctypes.byref(origin))
    return {"ok": True, "api": "win32", "titles": [title.value],
            "geometry": {"x": origin.x, "y": origin.y, "width": rect.right, "height": rect.bottom},
            "is_star_citizen": TITLE in title.value.lower()}


def active_window():
    return guarded(active_window_win32 if sys.platform == "win32" else active_window_x11)


def open_screen():
    """mss's screen grabber: `mss.MSS` in new releases, `mss.mss` in older ones."""
    import mss
    return (getattr(mss, "MSS", None) or mss.mss)()


def image_stats(img):
    from PIL import ImageStat
    grey = img.convert("L")
    stat = ImageStat.Stat(grey)
    colours = img.getcolors(maxcolors=1_000_000)
    return {"mean": round(stat.mean[0], 1), "stddev": round(stat.stddev[0], 1),
            "distinct_colours": len(colours) if colours else ">1e6",
            "bright_fraction": round(sum(grey.histogram()[161:]) / (img.width * img.height), 4),
            "looks_black": stat.mean[0] < 3 and stat.stddev[0] < 2}


def capture(window, out_dir):
    from PIL import Image
    result = {"ok": True, "shots": []}
    with open_screen() as sct:
        result["monitors"] = sct.monitors
        regions = []
        g = window.get("geometry") if window.get("is_star_citizen") else None
        if g and g.get("width"):
            regions.append(("sc_window_corner", {"left": g["x"] + g["width"] - CAPTURE_W, "top": g["y"],
                                                 "width": CAPTURE_W, "height": CAPTURE_H}))
        for i, mon in enumerate(sct.monitors[1:], start=1):
            regions.append((f"monitor{i}_corner", {"left": mon["left"] + mon["width"] - CAPTURE_W,
                                                   "top": mon["top"], "width": CAPTURE_W, "height": CAPTURE_H}))
        for name, region in regions:
            for attempt in (1, 2):
                try:
                    raw = sct.grab(region)
                    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                    filename = f"{name}_{attempt}.png"
                    img.save(os.path.join(out_dir, filename))
                    result["shots"].append({"name": name, "attempt": attempt, "region": region,
                                            "file": filename, **image_stats(img)})
                except Exception as exc:  # noqa: BLE001 - the failure is the finding
                    result["shots"].append({"name": name, "attempt": attempt, "region": region,
                                            "error": f"{type(exc).__name__}: {exc}"})
                time.sleep(0.5)
    return result


def run_probe(base_dir, extra=None):
    """Run every check, write the report and the PNGs, and return (zip_path, verdict)."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(base_dir, f"navpoint_probe_{stamp}")
    os.makedirs(out_dir)
    report = {"probe_version": 2, "time": stamp, **(extra or {})}
    report["system"] = guarded(system_info)
    report["modules"] = guarded(modules)
    report["processes"] = guarded(processes)
    samples = []
    for _ in range(3):
        samples.append(active_window())
        time.sleep(1.0)
    report["active_window_samples"] = samples
    window = next((s for s in samples if s.get("is_star_citizen")), samples[-1])
    report["capture"] = guarded(capture, window, out_dir)

    shots = [s for s in report["capture"].get("shots", []) if "error" not in s]
    system = report["system"] if isinstance(report["system"], dict) else {}
    procs = report["processes"] if isinstance(report["processes"], dict) else {}
    report["verdict"] = {
        "wingman_python": system.get("sys_platform", "?") + (f" (Wine {system['wine']})" if system.get("wine") else ""),
        "session": system.get("env", {}).get("XDG_SESSION_TYPE") or "unknown",
        "star_citizen_process_seen": bool(procs.get("star_citizen")) if "skipped" not in procs else None,
        "active_window_is_star_citizen": any(s.get("is_star_citizen") for s in samples),
        "any_capture_not_black": any(not s["looks_black"] for s in shots),
        "corner_has_bright_text_pixels": any(s["bright_fraction"] > 0.003 for s in shots),
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    zip_path = out_dir + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(out_dir)):
            zf.write(os.path.join(out_dir, name), os.path.join(os.path.basename(out_dir), name))
    shutil.rmtree(out_dir, ignore_errors=True)  # the zip holds everything
    return zip_path, report["verdict"]
