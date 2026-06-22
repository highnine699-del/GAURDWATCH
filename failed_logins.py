"""
Failed Login Counter Module
Checks Windows Security logs for failed login attempts
"""
import subprocess
import time
import threading
from pathlib import Path
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class FailedLoginsModule:
    """Failed login detection module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        import platform
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self._running = False
        self._is_windows = platform.system() == "Windows"
        
        # Check if win32 is available (Windows only)
        self._win32_ok = False
        if self._is_windows:
            try:
                import win32evtlog
                self._win32_ok = True
            except ImportError:
                self._win32_ok = False
    
    def check_failed_logins(self) -> None:
        """Check Windows Security logs for failed login attempts"""
        if not self._is_windows:
            event_bus.publish(Event(
                event_type="FAILED_LOGINS_SKIP",
                priority="INFO",
                detail="Failed login detection only available on Windows",
                source="failed_logins"
            ))
            return
        
        if not config.modules.get("failed_logins", True):
            event_bus.publish(Event(
                event_type="FAILED_LOGINS_SKIP",
                priority="INFO",
                detail="Failed login check disabled in config",
                source="failed_logins"
            ))
            return
        
        count = 0
        
        if self._win32_ok:
            try:
                import win32evtlog
                handle = win32evtlog.OpenEventLog(None, "Security")
                flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                events = win32evtlog.ReadEventLog(handle, flags, 0)
                
                for ev in (events or []):
                    if (ev.EventID & 0xFFFF) == 4625:
                        count += 1
                    if count >= 100:
                        break
                
                win32evtlog.CloseEventLog(handle)
            except Exception as e:
                event_bus.publish(Event(
                    event_type="FAILED_LOGINS_NOTE",
                    priority="INFO",
                    detail=f"Run as Admin for Security log access ({e})",
                    source="failed_logins"
                ))
                return
        else:
            try:
                result = subprocess.run(
                    ["wevtutil", "qe", "Security",
                     "/q:*[System[EventID=4625]]", "/c:100", "/f:text"],
                    capture_output=True, text=True, timeout=15
                )
                count = result.stdout.lower().count("event id: 4625") + \
                        result.stdout.lower().count("eventid: 4625")
                
                if result.returncode != 0 and count == 0:
                    event_bus.publish(Event(
                        event_type="FAILED_LOGINS_NOTE",
                        priority="INFO",
                        detail="wevtutil access denied — run as Administrator",
                        source="failed_logins"
                    ))
                    return
            except Exception as e:
                event_bus.publish(Event(
                    event_type="FAILED_LOGINS_NOTE",
                    priority="INFO",
                    detail=str(e),
                    source="failed_logins"
                ))
                return
        
        priority = "HIGH" if count > 2 else "INFO"
        detail = f"{count} failed login attempt(s) found"
        if count > 2:
            detail += " — someone was trying passwords!"
        
        event_bus.publish(Event(
            event_type="FAILED_LOGINS",
            priority=priority,
            detail=detail,
            source="failed_logins",
            data={"count": count}
        ))
        
        return count
    
    def _poll_loop(self) -> None:
        """Polling loop for checking failed logins"""
        # Establish baseline count
        self._baseline_count = self.check_failed_logins()
        
        while self._running and not self._stop_event.is_set():
            try:
                # Wait 60 seconds between checks
                for _ in range(60):
                    if self._stop_event.is_set():
                        return
                    time.sleep(1)
                
                # Check for new failed logins
                current_count = self.check_failed_logins()
                new_failures = current_count - self._baseline_count
                
                if new_failures > 0:
                    priority = "HIGH" if new_failures > 2 else "INFO"
                    detail = f"{new_failures} new failed login attempt(s) since last check"
                    if new_failures > 2:
                        detail += " — someone was trying passwords!"
                    
                    event_bus.publish(Event(
                        event_type="FAILED_LOGINS",
                        priority=priority,
                        detail=detail,
                        source="failed_logins",
                        data={"count": new_failures}
                    ))
                    
                    # Update baseline
                    self._baseline_count = current_count
                    
            except Exception as e:
                event_bus.publish(Event(
                    event_type="FAILED_LOGINS_ERROR",
                    priority="INFO",
                    detail=str(e),
                    source="failed_logins"
                ))
    
    def start(self) -> None:
        """Start failed login checking"""
        if not config.modules.get("failed_logins", True):
            event_bus.publish(Event(
                event_type="FAILED_LOGINS_SKIP",
                priority="INFO",
                detail="Failed login check disabled in config",
                source="failed_logins"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._worker_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._worker_thread.start()
        
        event_bus.publish(Event(
            event_type="FAILED_LOGINS_START",
            priority="INFO",
            detail="Failed login checker started (polling every 60s)",
            source="failed_logins"
        ))
    
    def stop(self) -> None:
        """Stop failed login checking"""
        self._running = False
        self._stop_event.set()
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
