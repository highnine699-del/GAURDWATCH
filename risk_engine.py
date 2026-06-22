"""
Risk Engine for Correlated Event Analysis
Analyzes multiple events to calculate threat level
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class RiskEngine:
    """Analyzes correlated events to calculate threat level"""
    
    def __init__(self, db: EvidenceDatabase, session_id: str):
        self.db = db
        self.session_id = session_id
        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._event_buffer: List[Dict] = []
        self._correlation_window = config.risk_engine.get("correlation_window_sec", 300)
        self._high_threshold = config.risk_engine.get("high_priority_threshold", 3)
        self._critical_threshold = config.risk_engine.get("critical_threshold", 5)
        
        # Risk weights for different event types
        self._risk_weights = {
            "WAKE_FROM_IDLE": 2,
            "WEBCAM_PHOTO": 1,
            "USB_INSERTED": 3,
            "FAILED_LOGINS": 4,
            "FILE_CREATED": 2,
            "CLIPBOARD": 1,
            "KEYSTROKE": 1,
        }
    
    def _on_event(self, event: Event) -> None:
        """Handle incoming events"""
        if not config.risk_engine.get("enabled", True):
            return
        
        event_dict = event.to_dict()
        event_dict["processed"] = False
        self._event_buffer.append(event_dict)
        
        # Keep buffer within correlation window
        self._cleanup_buffer()
    
    def _cleanup_buffer(self) -> None:
        """Remove events older than correlation window"""
        cutoff = datetime.now() - timedelta(seconds=self._correlation_window)
        self._event_buffer = [
            e for e in self._event_buffer
            if datetime.fromisoformat(e["timestamp"]) > cutoff
        ]
    
    def _calculate_risk_score(self) -> int:
        """Calculate risk score based on buffered events"""
        score = 0
        recent_events = []
        
        cutoff = datetime.now() - timedelta(seconds=self._correlation_window)
        
        for event in self._event_buffer:
            if datetime.fromisoformat(event["timestamp"]) > cutoff:
                event_type = event["event_type"]
                weight = self._risk_weights.get(event_type, 0)
                score += weight
                recent_events.append(event)
        
        return score
    
    def _analyze_patterns(self) -> Optional[Dict]:
        """Analyze event patterns for suspicious activity"""
        cutoff = datetime.now() - timedelta(seconds=self._correlation_window)
        recent_events = [
            e for e in self._event_buffer
            if datetime.fromisoformat(e["timestamp"]) > cutoff
        ]
        
        if not recent_events:
            return None
        
        # Check for specific patterns
        patterns = {
            "wake_usb": False,
            "wake_clipboard": False,
            "multiple_usb": False,
            "failed_logins": False,
            "suspicious_files": False,
        }
        
        event_types = [e["event_type"] for e in recent_events]
        
        # Pattern: Wake + USB
        if "WAKE_FROM_IDLE" in event_types and "USB_INSERTED" in event_types:
            patterns["wake_usb"] = True
        
        # Pattern: Wake + Clipboard activity
        if "WAKE_FROM_IDLE" in event_types and "CLIPBOARD" in event_types:
            patterns["wake_clipboard"] = True
        
        # Pattern: Multiple USB insertions
        usb_count = event_types.count("USB_INSERTED")
        if usb_count >= 2:
            patterns["multiple_usb"] = True
        
        # Pattern: Failed logins
        if "FAILED_LOGINS" in event_types:
            patterns["failed_logins"] = True
        
        # Pattern: Suspicious file creation
        for e in recent_events:
            if e["event_type"] == "FILE_CREATED" and e.get("priority") == "HIGH":
                patterns["suspicious_files"] = True
                break
        
        # Calculate pattern risk
        pattern_score = sum(patterns.values())
        
        if pattern_score >= 2:
            return {
                "risk_level": "CRITICAL" if pattern_score >= 3 else "HIGH",
                "patterns": patterns,
                "score": pattern_score,
                "event_count": len(recent_events)
            }
        
        return None
    
    def _analysis_loop(self) -> None:
        """Main risk analysis loop"""
        while self._running and not self._stop_event.is_set():
            try:
                self._cleanup_buffer()
                
                # Calculate risk score
                risk_score = self._calculate_risk_score()
                
                # Analyze patterns
                pattern_analysis = self._analyze_patterns()
                
                # Determine risk level
                if pattern_analysis:
                    risk_level = pattern_analysis["risk_level"]
                    detail = f"Pattern analysis: {', '.join([k for k, v in pattern_analysis['patterns'].items() if v])}"
                    
                    event_bus.publish(Event(
                        event_type="RISK_ALERT",
                        priority=risk_level,
                        detail=detail,
                        source="risk_engine",
                        data=pattern_analysis
                    ))
                elif risk_score >= self._critical_threshold:
                    event_bus.publish(Event(
                        event_type="RISK_ALERT",
                        priority="HIGH",
                        detail=f"Critical risk score: {risk_score}",
                        source="risk_engine",
                        data={"score": risk_score, "threshold": self._critical_threshold}
                    ))
                elif risk_score >= self._high_threshold:
                    event_bus.publish(Event(
                        event_type="RISK_ALERT",
                        priority="HIGH",
                        detail=f"High risk score: {risk_score}",
                        source="risk_engine",
                        data={"score": risk_score, "threshold": self._high_threshold}
                    ))
                
            except Exception as e:
                event_bus.publish(Event(
                    event_type="RISK_ENGINE_ERROR",
                    priority="INFO",
                    detail=str(e),
                    source="risk_engine"
                ))
            
            self._stop_event.wait(10)
    
    def start(self) -> None:
        """Start risk engine"""
        if not config.risk_engine.get("enabled", True):
            event_bus.publish(Event(
                event_type="RISK_ENGINE_SKIP",
                priority="INFO",
                detail="Risk engine disabled in config",
                source="risk_engine"
            ))
            return
        
        self._running = True
        self._stop_event.clear()
        
        # Subscribe to all events
        event_bus.subscribe("*", self._on_event)
        
        self._worker_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self._worker_thread.start()
        
        event_bus.publish(Event(
            event_type="RISK_ENGINE_START",
            priority="INFO",
            detail="Risk engine started",
            source="risk_engine"
        ))
    
    def stop(self) -> None:
        """Stop risk engine"""
        self._running = False
        self._stop_event.set()
        
        event_bus.unsubscribe("*", self._on_event)
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
    
    def get_current_risk(self) -> Dict:
        """Get current risk assessment"""
        return {
            "score": self._calculate_risk_score(),
            "buffer_size": len(self._event_buffer),
            "patterns": self._analyze_patterns()
        }
