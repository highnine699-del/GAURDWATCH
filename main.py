"""
GuardWatch v4.0 — PC Intruder Evidence Suite (Refactored)
Modular architecture with event bus, SQLite storage, health monitoring, and enhanced dashboard
"""
import argparse
import sys
import threading
import time
import signal
from pathlib import Path
from datetime import datetime

# Import configuration
from config import config

# Import core infrastructure
from event_bus import event_bus, Event
from database import EvidenceDatabase
from health_monitor import HealthMonitor, ModuleStatus
from session_manager import SessionManager

# Import modules
from webcam import WebcamModule
from keyboard import KeyboardModule
from clipboard import ClipboardModule
from steps import StepsModule
from usb import USBModule
from browser import BrowserModule
from file_monitor import FileMonitorModule
from monitor import IdleWakeModule
from screenshots import ScreenshotsModule
from window_tracker import WindowTrackerModule
from failed_logins import FailedLoginsModule
from risk_engine import RiskEngine
from dashboard import Dashboard
from report import ReportGenerator


class GuardWatch:
    """Main GuardWatch application"""
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.session_id = None
        self.session_dir = None
        self.db = None
        self.hasher = None
        
        self.modules = {}
        self.health_monitor = None
        self.risk_engine = None
        self.dashboard = None
        self.report_generator = None
        
        self._running = False
        self._stop_event = threading.Event()
    
    def initialize(self) -> None:
        """Initialize GuardWatch"""
        print("╔═══════════════════════════════════════════════════════════╗")
        print("║          GUARDWATCH v4.0 — MODULAR ARCHITECTURE           ║")
        print("╚═══════════════════════════════════════════════════════════╝")
        print()
        
        # Create session
        self.session_id = self.session_manager.create_session()
        self.session_dir = self.session_manager.get_session_dir()
        self.db = self.session_manager.get_database()
        self.hasher = self.session_manager.get_hasher()
        
        print(f"Session: {self.session_id}")
        print(f"Evidence: {self.session_dir}")
        print()
        
        # Initialize health monitor
        self.health_monitor = HealthMonitor(
            check_interval_sec=config.intervals.get("health_check_sec", 30)
        )
        
        # Initialize risk engine
        self.risk_engine = RiskEngine(self.db, self.session_id)
        
        # Initialize dashboard
        self.dashboard = Dashboard(self.db, self.session_id, self.session_dir)
        
        # Initialize report generator
        self.report_generator = ReportGenerator(self.db, self.session_dir, self.session_id)
        
        # Setup dashboard callbacks
        self.dashboard.set_screenshot_callback(self._trigger_screenshot)
        self.dashboard.set_export_callback(self._export_evidence)
        self.dashboard.set_stop_callback(self.stop)
    
    def _trigger_screenshot(self) -> None:
        """Trigger immediate screenshot"""
        if "screenshots" in self.modules:
            # This would need to be implemented in the screenshots module
            pass
    
    def _export_evidence(self, format_type: str) -> str:
        """Export evidence in specified format"""
        try:
            path = self.report_generator.export(format_type)
            return str(path)
        except Exception as e:
            print(f"[Export] Failed: {e}")
            return None
    
    def start_modules(self) -> None:
        """Start all monitoring modules"""
        print("Starting modules...")
        print()
        
        # Idle/Wake detector (must start first to trigger webcam)
        idle_wake = IdleWakeModule(
            self.session_dir, self.db, self.session_id,
            webcam_callback=lambda label: self.modules["webcam"].capture(label)
        )
        self.modules["idle_wake"] = idle_wake
        idle_wake.start()
        self.health_monitor.register_module("idle_wake", lambda: idle_wake.start())
        print("  ✓ Idle/Wake detector")
        
        # Webcam
        webcam = WebcamModule(self.session_dir, self.db, self.session_id)
        self.modules["webcam"] = webcam
        webcam.start()
        self.health_monitor.register_module("webcam", lambda: webcam.start())
        print("  ✓ Webcam capture")
        
        # Screenshots
        screenshots = ScreenshotsModule(self.session_dir, self.db, self.session_id)
        self.modules["screenshots"] = screenshots
        screenshots.start()
        self.health_monitor.register_module("screenshots", lambda: screenshots.start())
        print("  ✓ Timed screenshots")
        
        # Keyboard
        keyboard = KeyboardModule(self.session_dir, self.db, self.session_id)
        self.modules["keyboard"] = keyboard
        keyboard.start()
        self.health_monitor.register_module("keyboard", lambda: keyboard.start())
        print("  ✓ Keystroke logger")
        
        # Clipboard
        clipboard = ClipboardModule(self.session_dir, self.db, self.session_id)
        self.modules["clipboard"] = clipboard
        clipboard.start()
        self.health_monitor.register_module("clipboard", lambda: clipboard.start())
        print("  ✓ Clipboard monitor")
        
        # Steps recorder
        steps = StepsModule(self.session_dir, self.db, self.session_id)
        self.modules["steps"] = steps
        steps.start()
        self.health_monitor.register_module("steps", lambda: steps.start())
        print("  ✓ Steps recorder")
        
        # Window tracker
        window_tracker = WindowTrackerModule(self.session_dir, self.db, self.session_id)
        self.modules["window_tracker"] = window_tracker
        window_tracker.start()
        self.health_monitor.register_module("window_tracker", lambda: window_tracker.start())
        print("  ✓ Window tracker")
        
        # USB detector
        usb = USBModule(self.session_dir, self.db, self.session_id)
        self.modules["usb"] = usb
        usb.start()
        self.health_monitor.register_module("usb", lambda: usb.start())
        print("  ✓ USB detector")
        
        # Browser history
        browser = BrowserModule(self.session_dir, self.db, self.session_id)
        self.modules["browser"] = browser
        browser.start()
        browser.capture_snapshot("before")
        self.health_monitor.register_module("browser", lambda: browser.start())
        print("  ✓ Browser history")
        
        # File monitor
        file_monitor = FileMonitorModule(self.session_dir, self.db, self.session_id)
        self.modules["file_monitor"] = file_monitor
        file_monitor.start()
        self.health_monitor.register_module("file_monitor", lambda: file_monitor.start())
        print("  ✓ File activity monitor")
        
        # Failed logins
        failed_logins = FailedLoginsModule(self.session_dir, self.db, self.session_id)
        self.modules["failed_logins"] = failed_logins
        failed_logins.start()
        self.health_monitor.register_module("failed_logins", lambda: failed_logins.start())
        print("  ✓ Failed login checker")
        
        # Risk engine
        self.risk_engine.start()
        print("  ✓ Risk engine")
        
        # Health monitor
        self.health_monitor.start()
        print("  ✓ Health monitor")
        
        # Dashboard
        self.dashboard.start()
        print("  ✓ Web dashboard")
        
        print()
        print("All modules started. Press Ctrl+C to stop.")
        print()
        
        # Log session start
        event_bus.publish(Event(
            event_type="SESSION_START",
            priority="INFO",
            detail=f"GuardWatch v4.0 monitoring started",
            source="main"
        ))
    
    def stop_modules(self) -> None:
        """Stop all monitoring modules"""
        print()
        print("Stopping modules...")
        
        # Stop in reverse order
        for name in reversed(list(self.modules.keys())):
            module = self.modules[name]
            try:
                module.stop()
                print(f"  ✓ Stopped {name}")
            except Exception as e:
                print(f"  ✗ Error stopping {name}: {e}")
        
        # Stop risk engine
        if self.risk_engine:
            self.risk_engine.stop()
            print("  ✓ Stopped risk engine")
        
        # Stop health monitor
        if self.health_monitor:
            self.health_monitor.stop()
            print("  ✓ Stopped health monitor")
        
        # Stop dashboard
        if self.dashboard:
            self.dashboard.stop()
            print("  ✓ Stopped dashboard")
        
        # Capture browser history after
        if "browser" in self.modules:
            self.modules["browser"].capture_snapshot("after")
            print("  ✓ Captured browser history (after)")
        
        # End session
        self.session_manager.end_session()
        print("  ✓ Session ended")
        
        # Generate reports
        self._generate_reports()
        
        # Generate session summary
        self._print_session_summary()
        
        # Verify evidence integrity
        if config.storage.get("verify_integrity", True):
            self._verify_evidence()
        
        print()
        print("GuardWatch stopped.")
    
    def _generate_reports(self) -> None:
        """Generate evidence reports"""
        print()
        print("Generating reports...")
        
        try:
            html_path = self.report_generator.generate_html_report()
            print(f"  ✓ HTML report: {html_path.name}")
        except Exception as e:
            print(f"  ✗ HTML report failed: {e}")
        
        try:
            json_path = self.report_generator.generate_json_report()
            print(f"  ✓ JSON report: {json_path.name}")
        except Exception as e:
            print(f"  ✗ JSON report failed: {e}")
    
    def _print_session_summary(self) -> None:
        """Print session summary"""
        print()
        print("=" * 60)
        print("SESSION SUMMARY")
        print("=" * 60)
        
        summary = self.report_generator.generate_session_summary()
        
        print(f"Session ID: {summary['session_id']}")
        print(f"Duration: {summary['duration_minutes']} minutes")
        print(f"Total Events: {summary['total_events']}")
        print(f"High Priority Events: {summary['high_priority_events']}")
        print(f"Risk Level: {summary['risk_level']}")
        print()
        print("Evidence Files:")
        for file_type, count in summary['file_counts'].items():
            print(f"  {file_type}: {count}")
        
        if summary['top_events']:
            print()
            print("Top High-Priority Events:")
            for event in summary['top_events'][:5]:
                print(f"  [{event['timestamp'].split('T')[1][:8]}] {event['event_type']}: {event['detail']}")
    
    def _verify_evidence(self) -> None:
        """Verify evidence integrity"""
        print()
        print("Verifying evidence integrity...")
        
        report = self.hasher.generate_integrity_report()
        print(report)
    
    def run(self) -> None:
        """Run GuardWatch"""
        self._running = True
        self._stop_event.clear()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            while self._running and not self._stop_event.is_set():
                self._stop_event.wait(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals"""
        print()
        print("Shutdown signal received...")
        self._running = False
        self._stop_event.set()
    
    def stop(self) -> None:
        """Stop GuardWatch"""
        if self._running:
            self._running = False
            self._stop_event.set()
            self.stop_modules()


def show_report() -> None:
    """Show evidence report from previous sessions"""
    session_manager = SessionManager()
    sessions = session_manager.list_sessions()
    
    if not sessions:
        print("No sessions found.")
        return
    
    print()
    print("=" * 60)
    print("EVIDENCE SESSIONS")
    print("=" * 60)
    print()
    
    for session in sessions:
        print(f"Session: {session['id']}")
        print(f"Date: {session['date']}")
        print(f"Size: {session['size_mb']:.2f} MB")
        print(f"Database: {'Yes' if session['has_database'] else 'No'}")
        print()


def clear_evidence() -> None:
    """Clear all evidence"""
    import shutil
    
    session_manager = SessionManager()
    evidence_root = session_manager.evidence_root
    
    print(f"This will delete all evidence in: {evidence_root}")
    response = input("Are you sure? (yes/no): ")
    
    if response.lower() == "yes":
        shutil.rmtree(evidence_root)
        print("Evidence cleared.")
    else:
        print("Cancelled.")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="GuardWatch v4.0 — PC Intruder Evidence Suite")
    parser.add_argument("--report", action="store_true", help="Show evidence report")
    parser.add_argument("--clear", action="store_true", help="Clear all evidence")
    
    args = parser.parse_args()
    
    if args.report:
        show_report()
    elif args.clear:
        clear_evidence()
    else:
        # Run GuardWatch
        guardwatch = GuardWatch()
        
        try:
            guardwatch.initialize()
            guardwatch.start_modules()
            guardwatch.run()
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            guardwatch.stop()


if __name__ == "__main__":
    main()
