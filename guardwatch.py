"""
GuardWatch v3.0 — PC Intruder Evidence Suite + Web Dashboard
============================================================
Collects timestamped proof of unauthorized access on YOUR OWN PC.
Now with FILE ACTIVITY MONITORING and WEB DASHBOARD.

Setup:
    pip install mss Pillow pyperclip pynput opencv-python pywin32 flask watchdog

Usage:
    python guardwatch.py                 # Start with web dashboard (http://localhost:5555)
    python guardwatch.py --report        # Text evidence summary
    python guardwatch.py --clear         # Wipe all evidence

What it monitors:
  1.  Idle / Wake detection
  2.  Timed screenshots
  3.  Clipboard monitoring
  4.  Keystrokes
  5.  Steps recorder (mouse clicks)
  6.  Browser history (before/after)
  7.  Webcam snapshot on wake
  8.  Window title tracker
  9.  USB device detection
  10. Failed login counter
  11. FILE ACTIVITY MONITORING (NEW) — tracks all file changes + suspicious patterns
"""

import argparse
import base64
import ctypes
import json
import os
import random
import shutil
import sqlite3
import string
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Dict, List

# Fix Windows console encoding issue
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# ── Dependency check ───────────────────────────────────────────────────────────
_MISSING = []
for _pkg in ("mss", "PIL", "flask"):
    try:
        __import__(_pkg)
    except ImportError:
        _MISSING.append(_pkg)

if _MISSING:
    print(f"[GuardWatch] Missing: {', '.join(_MISSING)}")
    print("Run:  pip install mss Pillow opencv-python pywin32 flask watchdog")
    sys.exit(1)

import mss
try:
    import pyperclip
    PYPERCLIP_OK = True
except ImportError:
    pyperclip = None
    PYPERCLIP_OK = False
from flask import Flask, jsonify, render_template_string
from PIL import Image, ImageDraw
from pynput import keyboard, mouse

try:
    import cv2
    WEBCAM_OK = True
except ImportError:
    WEBCAM_OK = False

try:
    import win32gui
    import win32evtlog
    WIN32_OK = True
except ImportError:
    WIN32_OK = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_OK = True
except ImportError:
    WATCHDOG_OK = False

# ── Storage ────────────────────────────────────────────────────────────────────
_APPDATA      = Path(os.environ.get("APPDATA", str(Path.home())))
_LOCALAPPDATA  = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
EVIDENCE_ROOT = _APPDATA / "Microsoft" / "CLR" / "gw_evidence"
EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)

# ── Config ─────────────────────────────────────────────────────────────────────
SCREENSHOT_INTERVAL  = (90, 240)
IDLE_TRIGGER_SEC     = 300
CLIPBOARD_POLL_SEC   = 1.5
WINDOW_POLL_SEC      = 3
USB_POLL_SEC         = 2
WEBCAM_WARMUP_FRAMES = 5
STEP_MIN_GAP_SEC     = 0.6

# File monitoring config
MONITORED_DIRS = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    _LOCALAPPDATA / "Temp",
    _APPDATA / "Microsoft" / "Office",
]
SUSPICIOUS_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".dll", ".scr", ".vbs", ".js"}
IGNORE_DIRS = {".git", "__pycache__", "node_modules", "AppData", "$RECYCLE.BIN"}

if sys.platform == 'win32':
    BROWSER_DBS = {
        "Chrome": _LOCALAPPDATA / "Google/Chrome/User Data/Default/History",
        "Edge":   _LOCALAPPDATA / "Microsoft/Edge/User Data/Default/History",
    }
    FIREFOX_BASE = _APPDATA / "Mozilla" / "Firefox" / "Profiles"
else:
    BROWSER_DBS = {}
    FIREFOX_BASE = Path.home() / ".mozilla" / "firefox"


# ── Windows helpers ────────────────────────────────────────────────────────────
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_seconds() -> float:
    if sys.platform != 'win32':
        return 0.0

    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    try:
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0
    except Exception:
        return 0.0

def get_active_window_title() -> str:
    if sys.platform != 'win32':
        return ""

    if WIN32_OK:
        try:
            return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        except Exception:
            pass
    try:
        buf  = ctypes.create_unicode_buffer(512)
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  Evidence Session with Event Queue (for web dashboard)
# ══════════════════════════════════════════════════════════════════════════════
class EvidenceSession:
    def __init__(self):
        self.start      = datetime.now()
        self.sid        = self.start.strftime("%Y%m%d_%H%M%S")
        self.dir        = EVIDENCE_ROOT / self.sid
        self.shots_dir  = self.dir / "screenshots"
        self.steps_dir  = self.dir / "steps"
        self.webcam_dir = self.dir / "webcam"
        self.files_dir  = self.dir / "file_activity"
        for d in (self.dir, self.shots_dir, self.steps_dir, self.webcam_dir, self.files_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._events: List[Dict] = []
        self._lock = threading.Lock()
        self.event_queue = Queue()  # For web dashboard live updates

        self._keylog_path = self.dir / "keystrokes.txt"
        self._clip_path   = self.dir / "clipboard.txt"
        self._win_path    = self.dir / "window_titles.txt"
        self._events_path = self.dir / "events.json"
        self._files_path  = self.dir / "file_activity.json"

    def log(self, kind: str, detail: str = "", priority: str = "INFO"):
        ts    = datetime.now().isoformat(timespec="seconds")
        entry = {"time": ts, "priority": priority, "event": kind, "detail": detail}
        with self._lock:
            self._events.append(entry)
        try:
            with open(self._events_path, "w", encoding="utf-8") as f:
                json.dump(self._events, f, indent=2)
        except Exception as e:
            print(f"Failed to write events: {e}")
        flag = "⚠️  " if priority == "HIGH" else "    "
        print(f"{flag}[{ts[11:]}] {kind}: {detail[:80]}")
        
        # Queue for web dashboard
        self.event_queue.put(entry)

    def append(self, path: Path, text: str):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            print(f"Failed to append to {path.name}: {e}")

    def write_keystrokes(self, text: str):
        self.append(self._keylog_path, text)

    def write_clipboard(self, content: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.append(self._clip_path, f"\n{'─'*50}\n[{ts}]\n{content}\n")

    def write_window(self, title: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.append(self._win_path, f"[{ts}] {title}\n")

    def get_live_events(self, limit: int = 50) -> List[Dict]:
        """Return last N events for dashboard."""
        with self._lock:
            return self._events[-limit:]

    def get_stats(self) -> Dict:
        """Return evidence statistics for dashboard."""
        return {
            "session_id": self.sid,
            "uptime_secs": int((datetime.now() - self.start).total_seconds()),
            "total_events": len(self._events),
            "high_priority": len([e for e in self._events if e.get("priority") == "HIGH"]),
            "files": {
                "webcam": len(list(self.webcam_dir.glob("*.jpg"))),
                "steps": len(list(self.steps_dir.glob("*.png"))),
                "screenshots": len(list(self.shots_dir.glob("*.png"))),
                "file_activity": len([e for e in self._events if e.get("event").startswith("FILE_")]),
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Module 11 — File Activity Monitoring (NEW)
# ══════════════════════════════════════════════════════════════════════════════
class FileActivityHandler(FileSystemEventHandler):
    def __init__(self, session: EvidenceSession):
        self.session = session
        self._last_events = {}
        self._suspicious_patterns = {}

    def _should_ignore(self, path: Path) -> bool:
        """Skip system files, temp files, and monitoring artifacts."""
        ignore_patterns = {".tmp", ".log", "$", "~", ".vscode", "thumbs.db", ".ds_store"}
        name = path.name.lower()
        for p in ignore_patterns:
            if p in name:
                return True
        for d in IGNORE_DIRS:
            if d in str(path):
                return True
        return False

    def on_created(self, event):
        if event.is_directory or self._should_ignore(Path(event.src_path)):
            return
        path = Path(event.src_path)
        priority = "HIGH" if path.suffix in SUSPICIOUS_EXTENSIONS else "INFO"
        detail = f"Created → {path.name} ({path.stat().st_size} bytes)"
        self.session.log("FILE_CREATED", detail, priority=priority)

    def on_deleted(self, event):
        if event.is_directory or self._should_ignore(Path(event.src_path)):
            return
        path = Path(event.src_path)
        self.session.log("FILE_DELETED", f"Deleted → {path.name}", priority="INFO")

    def on_modified(self, event):
        if event.is_directory or self._should_ignore(Path(event.src_path)):
            return
        path = Path(event.src_path)
        now = time.time()
        key = str(path)
        
        # Avoid duplicate events (watchdog fires multiple times per file change)
        if key in self._last_events and (now - self._last_events[key]) < 1.0:
            return
        self._last_events[key] = now
        
        detail = f"Modified → {path.name}"
        self.session.log("FILE_MODIFIED", detail, priority="INFO")

def start_file_monitor(session: EvidenceSession, stop: threading.Event):
    """Monitor key folders for file activity."""
    if not WATCHDOG_OK:
        session.log("FILE_MONITOR_SKIP", "Install watchdog: pip install watchdog")
        return

    observer = Observer()
    handler = FileActivityHandler(session)
    
    for dir_path in MONITORED_DIRS:
        if dir_path.exists():
            observer.schedule(handler, str(dir_path), recursive=True)
    
    observer.start()
    session.log("FILE_MONITOR_START", f"Monitoring {len(MONITORED_DIRS)} folders")
    
    try:
        while not stop.is_set():
            time.sleep(1)
    except Exception as e:
        session.log("FILE_MONITOR_ERROR", str(e))
    finally:
        observer.stop()
        observer.join()


# ══════════════════════════════════════════════════════════════════════════════
#  Module 7 — Webcam Snapshot
# ══════════════════════════════════════════════════════════════════════════════
def capture_webcam(session: EvidenceSession, label: str = "wake"):
    if not WEBCAM_OK:
        session.log("WEBCAM_SKIP", "Install opencv-python to enable webcam capture")
        return

    def _shoot():
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                session.log("WEBCAM_ERROR", "No camera found or camera in use")
                return
            for _ in range(WEBCAM_WARMUP_FRAMES):
                cap.read()
                time.sleep(0.1)
            for i in range(2):
                ret, frame = cap.read()
                if ret:
                    ts   = datetime.now().strftime("%H%M%S")
                    path = session.webcam_dir / f"cam_{label}_{ts}_{i+1}.jpg"
                    cv2.imwrite(str(path), frame)
                    session.log("WEBCAM_PHOTO", f"Saved → {path.name}", priority="HIGH")
                time.sleep(0.5)
            cap.release()
        except Exception as e:
            session.log("WEBCAM_ERROR", str(e))

    threading.Thread(target=_shoot, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
#  Module 1 — Idle / Wake Detector
# ══════════════════════════════════════════════════════════════════════════════
def idle_watcher(session: EvidenceSession, stop: threading.Event):
    was_idle   = False
    idle_since = None

    while not stop.is_set():
        idle = get_idle_seconds()

        if idle >= IDLE_TRIGGER_SEC and not was_idle:
            was_idle   = True
            idle_since = datetime.now()
            session.log("PC_IDLE", f"No activity for {idle:.0f}s — standby")

        elif idle < 5 and was_idle:
            was_idle = False
            mins = int((datetime.now() - idle_since).total_seconds() / 60) if idle_since else 0
            session.log(
                "WAKE_FROM_IDLE",
                f"PC active after {mins} min idle — POSSIBLE INTRUDER",
                priority="HIGH"
            )
            capture_webcam(session, label="intruder")

        time.sleep(3)


# ══════════════════════════════════════════════════════════════════════════════
#  Module 2 — Timed Screenshots
# ══════════════════════════════════════════════════════════════════════════════
def screenshotter(session: EvidenceSession, stop: threading.Event):
    with mss.mss() as sct:
        while not stop.is_set():
            wait = random.randint(*SCREENSHOT_INTERVAL)
            for _ in range(wait):
                if stop.is_set():
                    return
                time.sleep(1)
            if get_idle_seconds() > 60:
                continue
            ts   = datetime.now().strftime("%H%M%S")
            path = session.shots_dir / f"screen_{ts}.png"
            try:
                sct.shot(output=str(path))
                session.log("SCREENSHOT", path.name)
            except Exception as e:
                session.log("SCREENSHOT_ERROR", str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  Module 3 — Clipboard Watcher
# ══════════════════════════════════════════════════════════════════════════════
def clipboard_watcher(session: EvidenceSession, stop: threading.Event):
    if not PYPERCLIP_OK:
        session.log(
            "CLIPBOARD_SKIP",
            "Clipboard monitoring unavailable because pyperclip is not installed",
            priority="INFO"
        )
        return

    last = ""
    while not stop.is_set():
        try:
            curr = pyperclip.paste()
            if curr and curr != last:
                last = curr
                session.write_clipboard(curr)
                preview = curr[:100].replace("\n", " ")
                session.log("CLIPBOARD", f"{len(curr)} chars — \"{preview}{'…' if len(curr)>100 else ''}\"")
        except Exception as e:
            session.log("CLIPBOARD_ERROR", str(e), priority="INFO")
        time.sleep(CLIPBOARD_POLL_SEC)


# ══════════════════════════════════════════════════════════════════════════════
#  Module 4 — Keystroke Logger
# ══════════════════════════════════════════════════════════════════════════════
def make_key_listener(session: EvidenceSession, stop: threading.Event):
    _last_minute = [None]
    _SPECIAL = {
        keyboard.Key.space:     " ",
        keyboard.Key.enter:     "\n[ENTER]\n",
        keyboard.Key.backspace: "[⌫]",
        keyboard.Key.tab:       "[TAB]",
        keyboard.Key.delete:    "[DEL]",
        keyboard.Key.esc:       "[ESC]",
        keyboard.Key.up:        "[↑]", keyboard.Key.down:  "[↓]",
        keyboard.Key.left:      "[←]", keyboard.Key.right: "[→]",
    }

    def on_press(key):
        if stop.is_set():
            return False
        minute = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"\n── {minute} ──\n" if minute != _last_minute[0] else ""
        _last_minute[0] = minute
        try:
            char = key.char or ""
        except AttributeError:
            char = _SPECIAL.get(key, f"[{key.name.upper()}]")
        if char:
            session.write_keystrokes(header + char)

    return keyboard.Listener(on_press=on_press)


# ══════════════════════════════════════════════════════════════════════════════
#  Module 5 — Steps Recorder
# ══════════════════════════════════════════════════════════════════════════════
def make_steps_recorder(session: EvidenceSession, stop: threading.Event):
    _step      = [0]
    _last_time = [0.0]

    def capture_step(x: int, y: int, btn_label: str):
        now = time.time()
        if now - _last_time[0] < STEP_MIN_GAP_SEC:
            return
        _last_time[0] = now
        _step[0] += 1
        n  = _step[0]
        ts = datetime.now().strftime("%H:%M:%S")

        try:
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[0])
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        except Exception as e:
            session.log("STEP_ERROR", str(e))
            return

        draw = ImageDraw.Draw(img)
        R = 22
        draw.ellipse([x-R, y-R, x+R, y+R], outline="#FF2222", width=3)
        draw.ellipse([x-5,  y-5,  x+5,  y+5],  fill="#FF2222")
        for x0, y0, x1, y1 in [
            (x-R-6, y, x-R+2, y), (x+R-2, y, x+R+6, y),
            (x, y-R-6, x, y-R+2), (x, y+R-2, x, y+R+6)
        ]:
            draw.line([x0, y0, x1, y1], fill="#FF2222", width=2)
        label = f" Step {n}: {btn_label} @ {ts} "
        tw, th = len(label) * 8, 18
        lx = min(max(x + 28, 4), img.width  - tw - 4)
        ly = min(max(y - 26, 4), img.height - th - 4)
        draw.rectangle([lx, ly, lx+tw, ly+th], fill="#CC0000")
        draw.text((lx+4, ly+2), label.strip(), fill="#FFFFFF")

        fname = f"step_{n:04d}_{ts.replace(':', '')}.png"
        try:
            img.save(session.steps_dir / fname)
            session.log("STEP", f"Step {n} — {btn_label} at ({x},{y})")
        except Exception as e:
            session.log("STEP_ERROR", str(e))

    def on_click(x, y, btn, pressed):
        if not pressed or stop.is_set():
            return
        s     = str(btn).lower()
        label = "Left-click" if "left" in s else ("Right-click" if "right" in s else "Middle-click")
        threading.Thread(target=capture_step, args=(x, y, label), daemon=True).start()

    return mouse.Listener(on_click=on_click)


# ══════════════════════════════════════════════════════════════════════════════
#  Module 6 — Browser History
# ══════════════════════════════════════════════════════════════════════════════
def snapshot_browser_history(session: EvidenceSession, label: str):
    results = {}

    def read_chromium(name: str, db_path: Path):
        if not db_path.exists():
            return
        tmp = EVIDENCE_ROOT / f"_tmp_{name}"
        try:
            shutil.copy2(db_path, tmp)
            con  = sqlite3.connect(tmp)
            rows = con.execute(
                "SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 150"
            ).fetchall()
            con.close()
            OFFSET = 11644473600
            results[name] = [
                {"time": datetime.fromtimestamp(t/1_000_000 - OFFSET).strftime("%Y-%m-%d %H:%M:%S"),
                 "title": title or "", "url": url}
                for url, title, t in rows
            ]
        except Exception as e:
            results[name] = [{"error": str(e)}]
        finally:
            try: tmp.unlink()
            except Exception: pass

    for name, path in BROWSER_DBS.items():
        read_chromium(name, path)

    if FIREFOX_BASE.exists():
        for profile in FIREFOX_BASE.iterdir():
            places = profile / "places.sqlite"
            if places.exists():
                tmp = EVIDENCE_ROOT / "_tmp_firefox"
                try:
                    shutil.copy2(places, tmp)
                    con  = sqlite3.connect(tmp)
                    rows = con.execute(
                        "SELECT url, title, last_visit_date FROM moz_places WHERE last_visit_date IS NOT NULL ORDER BY last_visit_date DESC LIMIT 150"
                    ).fetchall()
                    con.close()
                    results["Firefox"] = [
                        {"time": datetime.fromtimestamp(t/1_000_000).strftime("%Y-%m-%d %H:%M:%S"),
                         "title": title or "", "url": url}
                        for url, title, t in rows
                    ]
                except Exception as e:
                    results["Firefox"] = [{"error": str(e)}]
                finally:
                    try:
                        tmp.unlink()
                    except Exception as e:
                        session.log("BROWSER_HISTORY_ERROR", f"Failed to clean temporary Firefox DB: {e}", priority="INFO")
# ══════════════════════════════════════════════════════════════════════════════
#  Module 9 — USB Device Detection
# ══════════════════════════════════════════════════════════════════════════════
def usb_detector(session: 'EvidenceSession', stop: threading.Event):
    """USB device detector - Windows only"""
    import platform
    if platform.system() != "Windows":
        session.log("USB_SKIP", "USB detection only available on Windows", "INFO")
        return
    
    DTYPE = {1: "No-root", 2: "Removable", 3: "Fixed", 4: "Network", 5: "CD/DVD", 6: "RAM disk"}

    def current_drives() -> Dict[str, str]:
        drives, mask = {}, ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if mask & 1:
                path     = f"{letter}:\\"
                drives[path] = DTYPE.get(ctypes.windll.kernel32.GetDriveTypeW(path), "Unknown")
            mask >>= 1
        return drives

    known = current_drives()
    while not stop.is_set():
        current = current_drives()
        for drive, dtype in current.items():
            if drive not in known:
                session.log("USB_INSERTED", f"{dtype} drive at {drive}", priority="HIGH")
                try:
                    with mss.mss() as sct:
                        sct.shot(output=str(session.dir / f"usb_insert_{datetime.now().strftime('%H%M%S')}.png"))
                except Exception as e:
                    session.log("USB_ERROR", f"USB screenshot capture failed: {e}", priority="INFO")
        for drive in known:
            if drive not in current:
                session.log("USB_REMOVED", f"Drive {drive} ejected")
        known = current
        time.sleep(USB_POLL_SEC)


# ══════════════════════════════════════════════════════════════════════════════
#  Module 10 — Failed Login Counter
# ══════════════════════════════════════════════════════════════════════════════
def check_failed_logins(session: EvidenceSession):
    count = 0

    if WIN32_OK:
        try:
            handle = win32evtlog.OpenEventLog(None, "Security")
            flags  = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            events = win32evtlog.ReadEventLog(handle, flags, 0)
            for ev in (events or []):
                if (ev.EventID & 0xFFFF) == 4625:
                    count += 1
                if count >= 100:
                    break
            win32evtlog.CloseEventLog(handle)
        except Exception as e:
            session.log("FAILED_LOGINS_NOTE", f"Run as Admin for Security log access ({e})")
            return
    else:
        if sys.platform != 'win32':
            session.log("FAILED_LOGINS_SKIP", "Failed login counter only available on Windows", "INFO")
            return
        try:
            result = subprocess.run(
                ["wevtutil", "qe", "Security",
                 "/q:*[System[EventID=4625]]", "/c:100", "/f:text"],
                capture_output=True, text=True, timeout=15
            )
            count = result.stdout.lower().count("event id: 4625") + \
                    result.stdout.lower().count("eventid: 4625")
            if result.returncode != 0 and count == 0:
                session.log("FAILED_LOGINS_NOTE", "wevtutil access denied — run as Administrator for this feature")
                return
        except Exception as e:
            session.log("FAILED_LOGINS_NOTE", str(e))
            return

    prio   = "HIGH" if count > 2 else "INFO"
    detail = f"{count} failed login attempt(s) found"
    if count > 2:
        detail += " — someone was trying passwords!"
    session.log("FAILED_LOGINS", detail, priority=prio)


# ══════════════════════════════════════════════════════════════════════════════
#  CLI Report
# ══════════════════════════════════════════════════════════════════════════════
def show_report():
    sessions = sorted([d for d in EVIDENCE_ROOT.iterdir() if d.is_dir()])
    if not sessions:
        print("No sessions found:", EVIDENCE_ROOT)
        return

    print(f"\n{'═'*64}")
    print(f"  GUARDWATCH v3.0 — EVIDENCE REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*64}")

    for s in sessions:
        print(f"\n📁  SESSION  {s.name}")
        print(f"    Path: {s}")

        events = []
        evf = s / "events.json"
        if evf.exists():
            try:
                with open(evf, encoding="utf-8") as f:
                    events = json.load(f)
            except Exception as e:
                print(f"    ⚠️  Failed to load events: {e}")

        high = [e for e in events if e.get("priority") == "HIGH"]
        if high:
            print(f"\n    ⚠️  HIGH-PRIORITY EVENTS ({len(high)}):")
            for e in high[:10]:
                print(f"       [{e['time'][11:]}] {e['event']}: {e['detail']}")
            if len(high) > 10:
                print(f"       ... +{len(high)-10} more")
        else:
            print(f"    ✓  No high-priority events this session")

        def count(glob_path, pattern):
            d = s / glob_path
            return len(list(d.glob(pattern))) if d.exists() else 0

        def fsize(fname):
            p = s / fname
            return f"{p.stat().st_size} bytes" if p.exists() else "—"

        print(f"\n    Evidence:")
        print(f"      Webcam photos     : {count('webcam','*.jpg')}")
        print(f"      Steps (clicks)    : {count('steps','step_*.png')}")
        print(f"      Screenshots       : {count('screenshots','*.png')}")
        print(f"      File activity     : {len([e for e in events if 'FILE_' in e.get('event','')])} events")
        print(f"      Keystrokes        : {fsize('keystrokes.txt')}")
        print(f"      Clipboard         : {fsize('clipboard.txt')}")
        print()


# ══════════════════════════════════════════════════════════════════════════════
#  Flask Web Dashboard
# ══════════════════════════════════════════════════════════════════════════════
def create_dashboard_app(session: EvidenceSession, stop: threading.Event):
    """Create Flask app for web dashboard."""
    app = Flask(__name__)

    # Dashboard HTML template
    DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GuardWatch v3.0 — Live Dashboard</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box }
        body { background:#0a0e27; color:#e0e0e0; font-family:'Courier New',monospace; padding:20px }
        .container { max-width:1400px; margin:0 auto }
        .header { border-bottom:2px solid #ff3333; padding-bottom:15px; margin-bottom:25px }
        h1 { color:#ff3333; font-size:28px; margin-bottom:5px }
        .status { display:flex; gap:40px; margin-top:15px; font-size:13px }
        .status-item { display:flex; gap:10px }
        .status-label { color:#888 }
        .status-value { color:#ff8888; font-weight:bold }
        
        .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:25px }
        .card { background:#1a1f3a; border:1px solid #333; border-radius:6px; padding:15px }
        .card h2 { color:#ff6666; font-size:14px; text-transform:uppercase; margin-bottom:12px; border-bottom:1px solid #333; padding-bottom:8px }
        
        .event-log { background:#1a1f3a; border:1px solid #333; border-radius:6px; padding:15px; max-height:500px; overflow-y:auto }
        .event { padding:8px; border-bottom:1px solid #222; font-size:12px; line-height:1.4 }
        .event:last-child { border-bottom:none }
        .event.HIGH { background:#4a0000; color:#ff9999; border-left:3px solid #ff3333 }
        .event.INFO { color:#b0b0b0 }
        .event-time { color:#888; font-size:11px }
        
        .stat-box { text-align:center; padding:15px; background:#111827; border-radius:4px }
        .stat-number { font-size:24px; color:#ff3333; font-weight:bold }
        .stat-label { font-size:12px; color:#888; margin-top:5px; text-transform:uppercase }
        
        .controls { display:flex; gap:10px }
        button { background:#ff3333; color:#fff; border:none; padding:10px 20px; border-radius:4px; cursor:pointer; font-family:monospace; font-weight:bold; font-size:13px }
        button:hover { background:#ff5555 }
        
        @media (max-width:1000px) { .grid { grid-template-columns:1fr } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔴 GuardWatch v3.0</h1>
            <div class="status">
                <div class="status-item">
                    <span class="status-label">Session:</span>
                    <span class="status-value" id="session">—</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Uptime:</span>
                    <span class="status-value" id="uptime">0s</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Events:</span>
                    <span class="status-value" id="total-events">0</span>
                </div>
                <div class="status-item">
                    <span class="status-label">🚨 High Priority:</span>
                    <span class="status-value" id="high-priority">0</span>
                </div>
            </div>
        </div>

        <div class="grid">
            <div>
                <div class="card">
                    <h2>📊 Evidence Statistics</h2>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px">
                        <div class="stat-box">
                            <div class="stat-number" id="webcam-count">0</div>
                            <div class="stat-label">Webcam Photos</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number" id="steps-count">0</div>
                            <div class="stat-label">Step Clicks</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number" id="screenshots-count">0</div>
                            <div class="stat-label">Screenshots</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number" id="file-count">0</div>
                            <div class="stat-label">File Changes</div>
                        </div>
                    </div>
                </div>
            </div>

            <div>
                <div class="card">
                    <h2>⚙️ Controls</h2>
                    <div class="controls" style="flex-direction:column; gap:8px">
                        <button onclick="openEvidenceFolder()">📁 Open Evidence Folder</button>
                        <button onclick="stopMonitoring()">⏹️ Stop Monitoring</button>
                        <button onclick="refreshStats()">🔄 Refresh</button>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>📋 Live Event Stream (Last 30)</h2>
            <div class="event-log" id="event-log">
                <div class="event INFO" style="text-align:center; color:#888">Loading events...</div>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = '/api';
        let lastEventCount = 0;

        async function updateDashboard() {
            try {
                const res = await fetch(API_BASE + '/stats');
                const stats = await res.json();
                
                document.getElementById('session').textContent = stats.session_id.slice(-12);
                document.getElementById('uptime').textContent = formatUptime(stats.uptime_secs);
                document.getElementById('total-events').textContent = stats.total_events;
                document.getElementById('high-priority').textContent = stats.high_priority;
                
                document.getElementById('webcam-count').textContent = stats.files.webcam;
                document.getElementById('steps-count').textContent = stats.files.steps;
                document.getElementById('screenshots-count').textContent = stats.files.screenshots;
                document.getElementById('file-count').textContent = stats.files.file_activity;

                // Fetch and display events
                const evRes = await fetch(API_BASE + '/events');
                const events = await evRes.json();
                updateEventLog(events);
            } catch (e) {
                console.error('Error updating dashboard:', e);
            }
        }

        function updateEventLog(events) {
            const log = document.getElementById('event-log');
            if (events.length === 0) {
                log.innerHTML = '<div class="event INFO" style="text-align:center">No events yet...</div>';
                return;
            }
            
            log.innerHTML = events.reverse().map(e => `
                <div class="event ${e.priority}">
                    <div class="event-time">${e.time.slice(-8)}</div>
                    <strong>${e.event}</strong><br>
                    ${e.detail.slice(0, 120)}${e.detail.length > 120 ? '…' : ''}
                </div>
            `).join('');
        }

        function formatUptime(secs) {
            const h = Math.floor(secs / 3600);
            const m = Math.floor((secs % 3600) / 60);
            const s = secs % 60;
            return h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`;
        }

        function openEvidenceFolder() {
            fetch('/api/open-folder').catch(e => console.error(e));
        }

        function stopMonitoring() {
            if (confirm('Stop monitoring and generate final report?')) {
                fetch('/api/stop').then(() => {
                    document.body.innerHTML = '<h1 style="color:#ff3333">GuardWatch stopped. Evidence saved.</h1>';
                });
            }
        }

        function refreshStats() {
            updateDashboard();
        }

        // Update every 2 seconds
        updateDashboard();
        setInterval(updateDashboard, 2000);
    </script>
</body>
</html>
"""

    @app.route('/')
    def dashboard():
        return render_template_string(DASHBOARD_HTML)

    @app.route('/api/stats')
    def api_stats():
        return jsonify(session.get_stats())

    @app.route('/api/events')
    def api_events():
        return jsonify(session.get_live_events(limit=30))

    @app.route('/api/open-folder')
    def api_open_folder():
        try:
            os.startfile(str(session.dir))
        except Exception:
            pass
        return jsonify({"ok": True})

    @app.route('/api/stop')
    def api_stop_mon():
        stop.set()
        return jsonify({"ok": True})

    return app


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="GuardWatch v3.0 — PC intruder evidence suite + web dashboard")
    parser.add_argument("--report", action="store_true", help="Print evidence summary")
    parser.add_argument("--clear",  action="store_true", help="Delete all evidence (confirms first)")
    args = parser.parse_args()

    if args.report:
        show_report(); return

    if args.clear:
        if input("Delete ALL evidence? Type YES to confirm: ").strip() == "YES":
            shutil.rmtree(EVIDENCE_ROOT)
            EVIDENCE_ROOT.mkdir(parents=True)
            print("Evidence cleared.")
        else:
            print("Cancelled.")
        return

    # ── Start session ──────────────────────────────────────────────────────────
    session = EvidenceSession()
    stop    = threading.Event()

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║          GUARDWATCH v3.0 — ACTIVE + WEB DASHBOARD         ║
║                                                           ║
║  Session : {session.sid:<51}║
║  Dashboard: http://localhost:5555                        ║
║                                                           ║
║  Modules:                                                 ║
║  ✓ Idle/wake       ✓ Webcam          ✓ File Monitor       ║
║  ✓ Screenshots     ✓ Window titles   ✓ USB detector       ║
║  ✓ Click recorder  ✓ Clipboard       ✓ Failed logins      ║
║  ✓ Keystrokes      ✓ Browser hist.                        ║
║                                                           ║
║  Press Ctrl+C to stop and save evidence                  ║
╚═══════════════════════════════════════════════════════════╝
""")

    snapshot_browser_history(session, "before")
    check_failed_logins(session)
    session.log("SESSION_START", "GuardWatch v3.0 monitoring started")

    # Background threads
    for fn in (idle_watcher, screenshotter, clipboard_watcher, window_tracker, usb_detector, start_file_monitor):
        threading.Thread(target=fn, args=(session, stop), daemon=True).start()

    key_listener   = make_key_listener(session, stop)
    steps_listener = make_steps_recorder(session, stop)
    key_listener.start()
    steps_listener.start()

    # Start Flask dashboard
    app = create_dashboard_app(session, stop)
    
    print("\n✓ Dashboard live at: http://localhost:5555")
    print("  Open in your browser (or any device on your network)\n")

    try:
        app.run(host='0.0.0.0', port=5555, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n[GuardWatch] Stopping...")

    # ── Shutdown ───────────────────────────────────────────────────────────────
    stop.set()
    key_listener.stop()
    steps_listener.stop()

    snapshot_browser_history(session, "after")
    check_failed_logins(session)
    session.log("SESSION_END", "GuardWatch stopped by user")

    print(f"\n✓ Evidence saved to:\n   {session.dir}")
    print(f"\n📋 View summary:  python guardwatch.py --report")


if __name__ == "__main__":
    main()
