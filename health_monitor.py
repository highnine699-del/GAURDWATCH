"""
Health Monitoring System for GuardWatch Modules
Monitors module health and enables automatic recovery
"""
import threading
import time
from typing import Dict, Callable, Optional
from datetime import datetime
from enum import Enum
import traceback
from config import config


class ModuleStatus(Enum):
    """Module health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RESTARTING = "restarting"


class ModuleHealth:
    """Health status for a single module"""
    
    def __init__(self, name: str):
        self.name = name
        self.status = ModuleStatus.HEALTHY
        self.last_check = datetime.now()
        self.last_error: Optional[str] = None
        self.restart_count = 0
        self.max_restarts = 3
    
    def update_status(self, status: ModuleStatus, error: str = None) -> None:
        """Update module status"""
        self.status = status
        self.last_check = datetime.now()
        if error:
            self.last_error = error
    
    def record_restart(self) -> None:
        """Record a restart attempt"""
        self.restart_count += 1
        self.last_check = datetime.now()
    
    def can_restart(self) -> bool:
        """Check if module can be restarted"""
        return self.restart_count < self.max_restarts
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "status": self.status.value,
            "last_check": self.last_check.isoformat(),
            "last_error": self.last_error,
            "restart_count": self.restart_count,
            "can_restart": self.can_restart()
        }


class HealthMonitor:
    """Monitors health of all GuardWatch modules"""
    
    def __init__(self, check_interval_sec: int = 30):
        self._modules: Dict[str, ModuleHealth] = {}
        self._restart_callbacks: Dict[str, Callable] = {}
        self._check_interval = check_interval_sec
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    def register_module(self, name: str, restart_callback: Callable = None) -> None:
        """Register a module for health monitoring"""
        self._modules[name] = ModuleHealth(name)
        if restart_callback:
            self._restart_callbacks[name] = restart_callback
    
    def update_module_status(self, name: str, status: ModuleStatus, error: str = None) -> None:
        """Update status of a module"""
        if name in self._modules:
            self._modules[name].update_status(status, error)
    
    def report_error(self, name: str, error: str) -> None:
        """Report an error for a module"""
        if name in self._modules:
            self._modules[name].update_status(ModuleStatus.FAILED, error)
    
    def report_heartbeat(self, name: str) -> None:
        """Report a heartbeat from a module (indicates it's healthy)"""
        if name in self._modules:
            self._modules[name].update_status(ModuleStatus.HEALTHY)
    
    def get_module_health(self, name: str) -> Optional[Dict]:
        """Get health status of a specific module"""
        if name in self._modules:
            return self._modules[name].to_dict()
        return None
    
    def get_all_health(self) -> Dict[str, Dict]:
        """Get health status of all modules"""
        return {name: health.to_dict() for name, health in self._modules.items()}
    
    def start(self) -> None:
        """Start the health monitor"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop(self) -> None:
        """Stop the health monitor"""
        self._running = False
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop"""
        while self._running and not self._stop_event.is_set():
            try:
                self._check_modules()
                self._stop_event.wait(self._check_interval)
            except Exception as e:
                print(f"[HealthMonitor] Error in monitor loop: {e}")
                traceback.print_exc()
    
    def _check_modules(self) -> None:
        """Check health of all modules and attempt recovery if needed"""
        for name, health in self._modules.items():
            # Check if module hasn't reported recently
            time_since_check = (datetime.now() - health.last_check).total_seconds()
            
            if time_since_check > (self._check_interval * 3):
                # Module hasn't reported in a while, mark as degraded
                health.update_status(ModuleStatus.DEGRADED, "No recent heartbeat")
            
            # Attempt recovery for failed modules
            if health.status == ModuleStatus.FAILED and health.can_restart():
                self._attempt_restart(name, health)
    
    def _attempt_restart(self, name: str, health: ModuleHealth) -> None:
        """Attempt to restart a failed module"""
        if not config.recovery.get("enabled", True):
            return
        
        print(f"[HealthMonitor] Attempting to restart module: {name}")
        health.update_status(ModuleStatus.RESTARTING)
        health.record_restart()
        
        retry_delay = config.recovery.get("retry_delay_sec", 10)
        
        if name in self._restart_callbacks:
            try:
                # Wait before retry
                import time
                time.sleep(retry_delay)
                
                self._restart_callbacks[name]()
                print(f"[HealthMonitor] Successfully restarted module: {name}")
                health.update_status(ModuleStatus.HEALTHY)
            except Exception as e:
                print(f"[HealthMonitor] Failed to restart module {name}: {e}")
                health.update_status(ModuleStatus.FAILED, str(e))
    
    def get_health_summary(self) -> str:
        """Get a formatted health summary"""
        summary = ["Module Health Status", "=" * 40, ""]
        
        healthy = 0
        degraded = 0
        failed = 0
        
        for name, health in self._modules.items():
            status_icon = "✓" if health.status == ModuleStatus.HEALTHY else \
                         "!" if health.status == ModuleStatus.DEGRADED else \
                         "✗"
            summary.append(f"{status_icon} {name}: {health.status.value}")
            
            if health.status == ModuleStatus.HEALTHY:
                healthy += 1
            elif health.status == ModuleStatus.DEGRADED:
                degraded += 1
            else:
                failed += 1
        
        summary.append("")
        summary.append(f"Total: {len(self._modules)} | Healthy: {healthy} | Degraded: {degraded} | Failed: {failed}")
        
        return "\n".join(summary)
