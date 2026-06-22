"""
Steps Recorder Module
Captures annotated screenshots on every mouse click
"""
import threading
import time
import ctypes
from datetime import datetime
from pathlib import Path
from typing import Optional
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase

try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except ImportError:
    Image = None
    ImageDraw = None
    PIL_OK = False

try:
    import mss
    MSS_OK = True
except ImportError:
    mss = None
    MSS_OK = False

try:
    from pynput import mouse
    PYNPUT_OK = True
except ImportError:
    mouse = None
    PYNPUT_OK = False


class StepsModule:
    """Steps recorder module (annotated click screenshots)"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.steps_dir = session_dir / "steps"
        self.steps_dir.mkdir(parents=True, exist_ok=True)
        self.db = db
        self.session_id = session_id
        self._running = False
        self._stop_event = threading.Event()
        self._listener: Optional['mouse.Listener'] = None
        self._step_count = 0
        self._last_click_time = 0.0
        self._min_gap = config.intervals.get("step_min_gap_sec", 0.6)
        self._mouse_ok = PYNPUT_OK
        self._mss_ok = MSS_OK
        self._pil_ok = PIL_OK
    
    def _capture_step(self, x: int, y: int, btn_label: str) -> None:
        """Capture annotated screenshot of click"""
        now = time.time()
        if now - self._last_click_time < self._min_gap:
            return
        self._last_click_time = now
        
        self._step_count += 1
        n = self._step_count
        ts = datetime.now().strftime("%H:%M:%S")
        
        try:
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[0])
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        except Exception as e:
            event_bus.publish(Event(
                event_type="STEP_ERROR",
                priority="INFO",
                detail=str(e),
                source="steps"
            ))
            return
        
        # Draw crosshair and label
        draw = ImageDraw.Draw(img)
        R = 22
        draw.ellipse([x-R, y-R, x+R, y+R], outline="#FF2222", width=3)
        draw.ellipse([x-5, y-5, x+5, y+5], fill="#FF2222")
        
        # Cross lines
        for x0, y0, x1, y1 in [
            (x-R-6, y, x-R+2, y), (x+R-2, y, x+R+6, y),
            (x, y-R-6, x, y-R+2), (x, y+R-2, x, y+R+6)
        ]:
            draw.line([x0, y0, x1, y1], fill="#FF2222", width=2)
        
        # Label
        label = f" Step {n}: {btn_label} @ {ts} "
        tw, th = len(label) * 8, 18
        lx = min(max(x + 28, 4), img.width - tw - 4)
        ly = min(max(y - 26, 4), img.height - th - 4)
        draw.rectangle([lx, ly, lx+tw, ly+th], fill="#CC0000")
        draw.text((lx+4, ly+2), label.strip(), fill="#FFFFFF")
        
        # Save
        image_format = config.storage.get("screenshot_format", "jpeg").lower()
        ext = ".jpg" if image_format == "jpeg" else ".png"
        fname = f"step_{n:04d}_{ts.replace(':', '')}{ext}"
        filepath = self.steps_dir / fname
        
        try:
            if image_format == "jpeg":
                img.save(filepath, "JPEG", quality=config.storage.get("screenshot_quality", 85), optimize=True)
            else:
                img.save(filepath, "PNG", optimize=True)
            
            self.db.add_file(
                session_id=self.session_id,
                file_path=str(filepath.relative_to(self.session_dir)),
                file_type="step",
                size_bytes=filepath.stat().st_size
            )
            
            event_bus.publish(Event(
                event_type="STEP",
                priority="INFO",
                detail=f"Step {n} — {btn_label} at ({x},{y})",
                source="steps",
                data={"step_number": n, "x": x, "y": y, "button": btn_label}
            ))
        except Exception as e:
            event_bus.publish(Event(
                event_type="STEP_ERROR",
                priority="INFO",
                detail=str(e),
                source="steps"
            ))
    
    def _on_click(self, x, y, btn, pressed) -> None:
        """Handle mouse click events"""
        if not pressed or self._stop_event.is_set():
            return
        
        s = str(btn).lower()
        label = "Left-click" if "left" in s else ("Right-click" if "right" in s else "Middle-click")
        
        threading.Thread(target=self._capture_step, args=(x, y, label), daemon=True).start()
    
    def start(self) -> None:
        """Start steps recorder"""
        if not config.modules.get("steps", True):
            event_bus.publish(Event(
                event_type="STEPS_SKIP",
                priority="INFO",
                detail="Steps recorder disabled in config",
                source="steps"
            ))
            return

        if not (self._mouse_ok and self._mss_ok and self._pil_ok):
            event_bus.publish(Event(
                event_type="STEPS_SKIP",
                priority="INFO",
                detail="Required packages for steps recorder are missing",
                source="steps"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._listener = mouse.Listener(on_click=self._on_click)
        self._listener.start()
        
        event_bus.publish(Event(
            event_type="STEPS_START",
            priority="INFO",
            detail="Steps recorder started",
            source="steps"
        ))
    
    def stop(self) -> None:
        """Stop steps recorder"""
        self._running = False
        self._stop_event.set()
        
        if self._listener:
            self._listener.stop()
            self._listener.join()
    
    def get_count(self) -> int:
        """Get number of steps captured"""
        return self._step_count
