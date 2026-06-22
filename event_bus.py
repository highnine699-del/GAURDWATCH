"""
Central Event Bus for GuardWatch
Provides decoupled communication between modules using pub/sub pattern
"""
import threading
import queue
from typing import Callable, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, asdict, field
from collections import deque
import json


@dataclass
class Event:
    """Structured event data"""
    event_type: str
    priority: str = "INFO"
    detail: str = ""
    source: str = ""
    data: Dict[str, Any] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EventBus:
    """Central event bus for pub/sub communication"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread = None
        self._history: deque = deque(maxlen=200)
    
    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to events of a specific type"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Unsubscribe from events of a specific type"""
        with self._lock:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)
    
    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers"""
        self._event_queue.put(event)
    
    def start(self) -> None:
        """Start the event bus worker thread"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_events, daemon=True)
        self._worker_thread.start()
    
    def stop(self) -> None:
        """Stop the event bus worker thread"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
    
    def _process_events(self) -> None:
        """Process events from the queue and notify subscribers"""
        while self._running:
            try:
                event = self._event_queue.get(timeout=0.1)
                self._notify_subscribers(event)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[EventBus] Error processing event: {e}")
    
    def _notify_subscribers(self, event: Event) -> None:
        """Notify all subscribers of an event"""
        with self._lock:
            self._history.append(event.to_dict())
            subscribers = self._subscribers.get(event.event_type, [])
            all_subscribers = self._subscribers.get("*", [])  # Wildcard subscribers
            
            for callback in subscribers + all_subscribers:
                try:
                    callback(event)
                except Exception as e:
                    print(f"[EventBus] Error in subscriber callback: {e}")
    
    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent events from history (non-destructive, thread-safe)"""
        with self._lock:
            return list(self._history)[-limit:]


# Global event bus instance
event_bus = EventBus()
