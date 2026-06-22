"""
Webcam Snapshot Module
Captures photos on wake events for intruder identification
"""
import threading
import time
from pathlib import Path
from typing import Optional
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class WebcamModule:
    """Webcam capture module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        self.session_dir = session_dir
        self.webcam_dir = session_dir / "webcam"
        self.webcam_dir.mkdir(parents=True, exist_ok=True)
        self.db = db
        self.session_id = session_id
        self._running = False
        self._stop_event = threading.Event()
        
        # Check if opencv is available
        self._webcam_ok = True
        try:
            import cv2
        except ImportError:
            self._webcam_ok = False
            print("[Webcam] opencv-python not installed, webcam disabled")
    
    def capture(self, label: str = "wake") -> None:
        """Capture webcam photos in background thread"""
        if not self._webcam_ok or not config.modules.get("webcam", True):
            event_bus.publish(Event(
                event_type="WEBCAM_SKIP",
                priority="INFO",
                detail="Webcam disabled or opencv not installed",
                source="webcam"
            ))
            return
        
        threading.Thread(target=self._capture_thread, args=(label,), daemon=True).start()
    
    def _capture_thread(self, label: str) -> None:
        """Background thread for capturing photos"""
        try:
            warmup_frames = config.intervals.get("webcam_warmup_frames", 5)
            
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                event_bus.publish(Event(
                    event_type="WEBCAM_ERROR",
                    priority="INFO",
                    detail="No camera found or camera in use",
                    source="webcam"
                ))
                return
            
            # Warm up camera
            for _ in range(warmup_frames):
                cap.read()
                time.sleep(0.1)
            
            # Capture 2 photos
            for i in range(2):
                ret, frame = cap.read()
                if ret:
                    from datetime import datetime
                    ts = datetime.now().strftime("%H%M%S")
                    filename = f"cam_{label}_{ts}_{i+1}.jpg"
                    filepath = self.webcam_dir / filename
                    
                    # Use JPEG with configurable quality
                    quality = config.storage.get("screenshot_quality", 85)
                    cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
                    
                    # Store in database
                    self.db.add_file(
                        session_id=self.session_id,
                        file_path=str(filepath.relative_to(self.session_dir)),
                        file_type="webcam",
                        size_bytes=filepath.stat().st_size
                    )
                    
                    event_bus.publish(Event(
                        event_type="WEBCAM_PHOTO",
                        priority="HIGH",
                        detail=f"Saved → {filename}",
                        source="webcam",
                        data={"filename": filename, "label": label}
                    ))
                
                time.sleep(0.5)
            
            cap.release()
            
        except Exception as e:
            event_bus.publish(Event(
                event_type="WEBCAM_ERROR",
                priority="INFO",
                detail=str(e),
                source="webcam"
            ))
    
    def start(self) -> None:
        """Start webcam module"""
        self._running = True
        self._stop_event.clear()
    
    def stop(self) -> None:
        """Stop webcam module"""
        self._running = False
        self._stop_event.set()
