"""
Idle/Wake Detector Module
Detects when PC wakes from idle state
"""
import threading
import time
import sys
import ctypes
from datetime import datetime
from pathlib import Path
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class _LASTINPUTINFO(ctypes.Structure):
    """Windows structure for last input info"""
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds() -> float:
    """Get number of seconds since last user input"""
    if sys.platform != 'win32':
        return 0.0

    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    try:
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0
    except Exception:
        return 0.0


class IdleWakeModule:
    """Idle/wake detection module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str, webcam_callback):
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self.webcam_callback = webcam_callback
        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread = None
        self._was_idle = False
        self._idle_since = None
        self._idle_trigger = config.intervals.get("idle_trigger_sec", 300)
    
    def _monitor_loop(self) -> None:
        """Main idle/wake monitoring loop"""
        while self._running and not self._stop_event.is_set():
            try:
                idle = get_idle_seconds()
                
                # Check for idle state
                if idle >= self._idle_trigger and not self._was_idle:
                    self._was_idle = True
                    self._idle_since = datetime.now()
                    
                    event_bus.publish(Event(
                        event_type="PC_IDLE",
                        priority="INFO",
                        detail=f"No activity for {idle:.0f}s — standby",
                        source="idle_wake",
                        data={"idle_seconds": idle}
                    ))
                
                # Check for wake from idle
                elif idle < 5 and self._was_idle:
                    self._was_idle = False
                    mins = int((datetime.now() - self._idle_since).total_seconds() / 60) if self._idle_since else 0
                    
                    event_bus.publish(Event(
                        event_type="WAKE_FROM_IDLE",
                        priority="HIGH",
                        detail=f"PC active after {mins} min idle — POSSIBLE INTRUDER",
                        source="idle_wake",
                        data={"idle_minutes": mins}
                    ))
                    
                    # Trigger webcam capture
                    if self.webcam_callback:
                        self.webcam_callback(label="intruder")
                
            except Exception as e:
                event_bus.publish(Event(
                    event_type="IDLE_WAKE_ERROR",
                    priority="INFO",
                    detail=str(e),
                    source="idle_wake"
                ))
            
            self._stop_event.wait(3)
    
    def start(self) -> None:
        """Start idle/wake monitoring"""
        if not config.modules.get("idle_wake", True):
            event_bus.publish(Event(
                event_type="IDLE_WAKE_SKIP",
                priority="INFO",
                detail="Idle/wake detection disabled in config",
                source="idle_wake"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._worker_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._worker_thread.start()
        
        event_bus.publish(Event(
            event_type="IDLE_WAKE_START",
            priority="INFO",
            detail="Idle/wake detector started",
            source="idle_wake"
        ))
    
    def stop(self) -> None:
        """Stop idle/wake monitoring"""
        self._running = False
        self._stop_event.set()
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
