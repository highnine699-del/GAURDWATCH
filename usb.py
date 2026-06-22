"""
USB Device Detection Module
Detects drive insertion and removal
"""
import threading
import time
import ctypes
import string
import mss
from datetime import datetime
from pathlib import Path
from typing import Dict
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class USBModule:
    """USB device detection module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread = None
        self._known_drives: Dict[str, str] = {}
        
        self._drive_types = {
            1: "No-root",
            2: "Removable",
            3: "Fixed",
            4: "Network",
            5: "CD/DVD",
            6: "RAM disk"
        }
    
    def _get_current_drives(self) -> Dict[str, str]:
        """Get current list of drives"""
        drives = {}
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        
        for letter in string.ascii_uppercase:
            if mask & 1:
                path = f"{letter}:\\"
                dtype = self._drive_types.get(
                    ctypes.windll.kernel32.GetDriveTypeW(path),
                    "Unknown"
                )
                drives[path] = dtype
            mask >>= 1
        
        return drives
    
    def _monitor_loop(self) -> None:
        """Main USB monitoring loop"""
        poll_interval = config.intervals.get("usb_poll_sec", 2)
        self._known_drives = self._get_current_drives()
        
        while self._running and not self._stop_event.is_set():
            try:
                current = self._get_current_drives()
                
                # Check for new drives (inserted)
                for drive, dtype in current.items():
                    if drive not in self._known_drives:
                        event_bus.publish(Event(
                            event_type="USB_INSERTED",
                            priority="HIGH",
                            detail=f"{dtype} drive at {drive}",
                            source="usb",
                            data={"drive": drive, "type": dtype}
                        ))
                        
                        # Capture screenshot
                        try:
                            ts = datetime.now().strftime("%H%M%S")
                            fname = f"usb_insert_{ts}.png"
                            filepath = self.session_dir / fname
                            
                            with mss.mss() as sct:
                                sct.shot(output=str(filepath))
                            
                            self.db.add_file(
                                session_id=self.session_id,
                                file_path=str(filepath.relative_to(self.session_dir)),
                                file_type="usb_screenshot",
                                size_bytes=filepath.stat().st_size
                            )
                        except Exception:
                            pass
                
                # Check for removed drives
                for drive in self._known_drives:
                    if drive not in current:
                        event_bus.publish(Event(
                            event_type="USB_REMOVED",
                            priority="INFO",
                            detail=f"Drive {drive} ejected",
                            source="usb",
                            data={"drive": drive}
                        ))
                
                self._known_drives = current
                
            except Exception as e:
                event_bus.publish(Event(
                    event_type="USB_ERROR",
                    priority="INFO",
                    detail=str(e),
                    source="usb"
                ))
            
            self._stop_event.wait(poll_interval)
    
    def start(self) -> None:
        """Start USB monitoring"""
        if not config.modules.get("usb_detection", True):
            event_bus.publish(Event(
                event_type="USB_SKIP",
                priority="INFO",
                detail="USB detection disabled in config",
                source="usb"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._worker_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._worker_thread.start()
        
        event_bus.publish(Event(
            event_type="USB_START",
            priority="INFO",
            detail="USB detector started",
            source="usb"
        ))
    
    def stop(self) -> None:
        """Stop USB monitoring"""
        self._running = False
        self._stop_event.set()
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
