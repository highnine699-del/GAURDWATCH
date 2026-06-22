"""
Failed Login Counter Module
Checks Windows Security logs for failed login attempts
"""
import subprocess
from pathlib import Path
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class FailedLoginsModule:
    """Failed login detection module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self._running = False
        
        # Check if win32 is available
        self._win32_ok = True
        try:
            import win32evtlog
        except ImportError:
            self._win32_ok = False
    
    def check_failed_logins(self) -> None:
        """Check Windows Security logs for failed login attempts"""
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
    
    def start(self) -> None:
        """Start failed login checking"""
        self._running = True
        self.check_failed_logins()
        
        event_bus.publish(Event(
            event_type="FAILED_LOGINS_START",
            priority="INFO",
            detail="Failed login checker started",
            source="failed_logins"
        ))
    
    def stop(self) -> None:
        """Stop failed login checking"""
        self._running = False
