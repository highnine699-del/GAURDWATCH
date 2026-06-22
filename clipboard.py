"""
Clipboard Monitor Module
Tracks all copy/paste operations
"""
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase

try:
    import pyperclip
except ImportError:
    pyperclip = None


class ClipboardModule:
    """Clipboard monitoring module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self._clip_path = session_dir / "clipboard.txt"
        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._last_content = ""
        self._available = pyperclip is not None
    
    def _write_clipboard(self, content: str) -> None:
        """Write clipboard content to file"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self._clip_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'─'*50}\n[{ts}]\n{content}\n")
        except Exception as e:
            event_bus.publish(Event(
                event_type="CLIPBOARD_ERROR",
                priority="INFO",
                detail=str(e),
                source="clipboard"
            ))
    
    def _monitor_loop(self) -> None:
        """Main clipboard monitoring loop"""
        if not self._available:
            event_bus.publish(Event(
                event_type="CLIPBOARD_SKIP",
                priority="INFO",
                detail="pyperclip not installed; clipboard monitoring unavailable",
                source="clipboard"
            ))
            return

        poll_interval = config.intervals.get("clipboard_poll_sec", 1.5)
        
        while self._running and not self._stop_event.is_set():
            try:
                curr = pyperclip.paste()
                if curr and curr != self._last_content:
                    self._last_content = curr
                    self._write_clipboard(curr)
                    
                    preview = curr[:100].replace("\n", " ")
                    event_bus.publish(Event(
                        event_type="CLIPBOARD",
                        priority="INFO",
                        detail=f"{len(curr)} chars — \"{preview}{'…' if len(curr)>100 else ''}\"",
                        source="clipboard",
                        data={"length": len(curr), "preview": preview}
                    ))
            except Exception as e:
                event_bus.publish(Event(
                    event_type="CLIPBOARD_ERROR",
                    priority="INFO",
                    detail=str(e),
                    source="clipboard"
                ))
            
            self._stop_event.wait(poll_interval)
    
    def start(self) -> None:
        """Start clipboard monitoring"""
        if not config.modules.get("clipboard", True):
            event_bus.publish(Event(
                event_type="CLIPBOARD_SKIP",
                priority="INFO",
                detail="Clipboard monitoring disabled in config",
                source="clipboard"
            ))
            return

        if not self._available:
            event_bus.publish(Event(
                event_type="CLIPBOARD_SKIP",
                priority="INFO",
                detail="pyperclip not installed; clipboard monitoring unavailable",
                source="clipboard"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._worker_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._worker_thread.start()
        
        event_bus.publish(Event(
            event_type="CLIPBOARD_START",
            priority="INFO",
            detail="Clipboard monitor started",
            source="clipboard"
        ))
    
    def stop(self) -> None:
        """Stop clipboard monitoring"""
        self._running = False
        self._stop_event.set()
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
    
    def get_size(self) -> int:
        """Get size of clipboard log file"""
        try:
            return self._clip_path.stat().st_size
        except Exception:
            return 0
