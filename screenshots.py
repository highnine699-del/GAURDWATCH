"""
Timed Screenshots Module
Captures desktop screenshots at random intervals
"""
import threading
import time
import random
from pathlib import Path
import mss
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class ScreenshotsModule:
    """Timed screenshot module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.shots_dir = session_dir / "screenshots"
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self.db = db
        self.session_id = session_id
        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread = None
        
        self._interval_min = config.intervals.get("screenshot_min", 90)
        self._interval_max = config.intervals.get("screenshot_max", 240)
    
    def _capture_loop(self) -> None:
        """Main screenshot capture loop"""
        while self._running and not self._stop_event.is_set():
            try:
                wait = random.randint(self._interval_min, self._interval_max)
                
                # Wait with stop check
                for _ in range(wait):
                    if self._stop_event.is_set():
                        return
                    time.sleep(1)
                
                # Skip if idle
                if get_idle_seconds() > 60:
                    continue
                
                # Capture screenshot
                from datetime import datetime
                ts = datetime.now().strftime("%H%M%S")
                filename = f"screen_{ts}.png"
                filepath = self.shots_dir / filename
                
                with mss.mss() as sct:
                    sct.shot(output=str(filepath))
                
                # Store in database
                self.db.add_file(
                    session_id=self.session_id,
                    file_path=str(filepath.relative_to(self.session_dir)),
                    file_type="screenshot",
                    size_bytes=filepath.stat().st_size
                )
                
                event_bus.publish(Event(
                    event_type="SCREENSHOT",
                    priority="INFO",
                    detail=filename,
                    source="screenshots",
                    data={"filename": filename}
                ))
                
            except Exception as e:
                event_bus.publish(Event(
                    event_type="SCREENSHOT_ERROR",
                    priority="INFO",
                    detail=str(e),
                    source="screenshots"
                ))
    
    def start(self) -> None:
        """Start screenshot capture"""
        if not config.modules.get("screenshots", True):
            event_bus.publish(Event(
                event_type="SCREENSHOT_SKIP",
                priority="INFO",
                detail="Screenshots disabled in config",
                source="screenshots"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._worker_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._worker_thread.start()
        
        event_bus.publish(Event(
            event_type="SCREENSHOT_START",
            priority="INFO",
            detail="Screenshot capture started",
            source="screenshots"
        ))
    
    def stop(self) -> None:
        """Stop screenshot capture"""
        self._running = False
        self._stop_event.set()
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
    
    def get_count(self) -> int:
        """Get number of screenshots captured"""
        try:
            image_format = config.storage.get("screenshot_format", "jpeg").lower()
            ext = "*.jpg" if image_format == "jpeg" else "*.png"
            return len(list(self.shots_dir.glob(ext)))
        except Exception:
            return 0


def get_idle_seconds() -> float:
    """Get idle seconds (imported from monitor to avoid circular import)"""
    import ctypes
    
    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    try:
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0
    except Exception:
        return 0.0
