"""
Window Title Tracker Module
Monitors which application has focus
"""
import threading
import time
import ctypes
from pathlib import Path
from datetime import datetime
from typing import Optional
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class WindowTrackerModule:
    """Window title tracking module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self._win_path = session_dir / "window_titles.txt"
        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread = None
        self._last_title = ""
        self._poll_interval = config.intervals.get("window_poll_sec", 3)
        
        # Check if win32 is available
        self._win32_ok = True
        try:
            import win32gui
        except ImportError:
            self._win32_ok = False
    
    def _get_active_window_title(self) -> str:
        """Get title of active window"""
        if self._win32_ok:
            try:
                import win32gui
                return win32gui.GetWindowText(win32gui.GetForegroundWindow())
            except Exception:
                pass
        
        try:
            buf = ctypes.create_unicode_buffer(512)
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
            return buf.value
        except Exception:
            return ""
    
    def _write_window(self, title: str) -> None:
        """Write window title to file"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self._win_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {title}\n")
        except Exception as e:
            event_bus.publish(Event(
                event_type="WINDOW_ERROR",
                priority="INFO",
                detail=str(e),
                source="window_tracker"
            ))
    
    def _monitor_loop(self) -> None:
        """Main window tracking loop"""
        while self._running and not self._stop_event.is_set():
            try:
                title = self._get_active_window_title()
                
                if title and title != self._last_title:
                    self._last_title = title
                    self._write_window(title)
                    
                    event_bus.publish(Event(
                        event_type="WINDOW_FOCUS",
                        priority="INFO",
                        detail=title,
                        source="window_tracker",
                        data={"title": title}
                    ))
                
            except Exception as e:
                event_bus.publish(Event(
                    event_type="WINDOW_ERROR",
                    priority="INFO",
                    detail=str(e),
                    source="window_tracker"
                ))
            
            self._stop_event.wait(self._poll_interval)
    
    def start(self) -> None:
        """Start window tracking"""
        if not config.modules.get("window_titles", True):
            event_bus.publish(Event(
                event_type="WINDOW_SKIP",
                priority="INFO",
                detail="Window tracking disabled in config",
                source="window_tracker"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._worker_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._worker_thread.start()
        
        event_bus.publish(Event(
            event_type="WINDOW_START",
            priority="INFO",
            detail="Window tracker started",
            source="window_tracker"
        ))
    
    def stop(self) -> None:
        """Stop window tracking"""
        self._running = False
        self._stop_event.set()
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
