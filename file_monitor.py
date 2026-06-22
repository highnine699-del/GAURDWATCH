"""
File Activity Monitor Module
Tracks file changes in key directories with suspicious pattern detection
"""
import threading
import time
from pathlib import Path
from typing import Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class FileActivityHandler(FileSystemEventHandler):
    """Handler for file system events"""
    
    def __init__(self, session_id: str, monitored_dirs: list[Path]):
        self.session_id = session_id
        self.monitored_dirs = monitored_dirs
        self._last_events: dict = {}
        self._ignore_patterns = {".tmp", ".log", "$", "~", ".vscode", "thumbs.db", ".ds_store"}
        self._ignore_dirs = set(config.monitoring.get("ignore_dirs", []))
        self._suspicious_extensions = set(config.monitoring.get("suspicious_extensions", []))
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored"""
        name = path.name.lower()
        
        # Check ignore patterns
        for pattern in self._ignore_patterns:
            if pattern in name:
                return True
        
        # Check ignore directories
        for ignore_dir in self._ignore_dirs:
            if ignore_dir in str(path):
                return True
        
        return False
    
    def on_created(self, event):
        """Handle file creation"""
        if event.is_directory or self._should_ignore(Path(event.src_path)):
            return
        
        path = Path(event.src_path)
        priority = "HIGH" if path.suffix in self._suspicious_extensions else "INFO"
        
        event_bus.publish(Event(
            event_type="FILE_CREATED",
            priority=priority,
            detail=f"Created → {path.name} ({path.stat().st_size} bytes)",
            source="file_monitor",
            data={"path": str(path), "size": path.stat().st_size, "extension": path.suffix}
        ))
    
    def on_deleted(self, event):
        """Handle file deletion"""
        if event.is_directory or self._should_ignore(Path(event.src_path)):
            return
        
        path = Path(event.src_path)
        event_bus.publish(Event(
            event_type="FILE_DELETED",
            priority="INFO",
            detail=f"Deleted → {path.name}",
            source="file_monitor",
            data={"path": str(path)}
        ))
    
    def on_modified(self, event):
        """Handle file modification"""
        if event.is_directory or self._should_ignore(Path(event.src_path)):
            return
        
        path = Path(event.src_path)
        now = time.time()
        key = str(path)
        
        # Avoid duplicate events (watchdog fires multiple times)
        if key in self._last_events and (now - self._last_events[key]) < 1.0:
            return
        self._last_events[key] = now
        
        event_bus.publish(Event(
            event_type="FILE_MODIFIED",
            priority="INFO",
            detail=f"Modified → {path.name}",
            source="file_monitor",
            data={"path": str(path)}
        ))


class FileMonitorModule:
    """File activity monitoring module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self._running = False
        self._stop_event = threading.Event()
        self._observer: Observer = None
        self._handler: FileActivityHandler = None
        
        # Check if watchdog is available
        self._watchdog_ok = True
        try:
            from watchdog.observers import Observer
        except ImportError:
            self._watchdog_ok = False
            print("[FileMonitor] watchdog not installed, file monitoring disabled")
    
    def start(self) -> None:
        """Start file monitoring"""
        if not config.modules.get("file_activity", True):
            event_bus.publish(Event(
                event_type="FILE_MONITOR_SKIP",
                priority="INFO",
                detail="File monitoring disabled in config",
                source="file_monitor"
            ))
            return
        
        if not self._watchdog_ok:
            event_bus.publish(Event(
                event_type="FILE_MONITOR_SKIP",
                priority="INFO",
                detail="Install watchdog: pip install watchdog",
                source="file_monitor"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        monitored_dirs = config.get_monitored_dirs()
        self._observer = Observer()
        self._handler = FileActivityHandler(self.session_id, monitored_dirs)
        
        count = 0
        for dir_path in monitored_dirs:
            if dir_path.exists():
                self._observer.schedule(self._handler, str(dir_path), recursive=True)
                count += 1
        
        self._observer.start()
        
        event_bus.publish(Event(
            event_type="FILE_MONITOR_START",
            priority="INFO",
            detail=f"Monitoring {count} folders",
            source="file_monitor",
            data={"folders_count": count}
        ))
        
        # Keep thread alive
        threading.Thread(target=self._keep_alive, daemon=True).start()
    
    def _keep_alive(self) -> None:
        """Keep monitoring alive"""
        while self._running and not self._stop_event.is_set():
            self._stop_event.wait(1)
    
    def stop(self) -> None:
        """Stop file monitoring"""
        self._running = False
        self._stop_event.set()
        
        if self._observer:
            self._observer.stop()
            self._observer.join()
