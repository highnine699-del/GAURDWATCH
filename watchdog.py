"""
Watchdog Process for GuardWatch
Monitors the main GuardWatch process and restarts it on failure
Prevents single point of failure
"""
import subprocess
import time
import sys
import signal
from pathlib import Path
from datetime import datetime


class Watchdog:
    """Watchdog process to monitor and restart GuardWatch"""
    
    def __init__(self, max_retries: int = 5, restart_delay: int = 10):
        self.max_retries = max_retries
        self.restart_delay = restart_delay
        self.retry_count = 0
        self.running = True
        self.process = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"[Watchdog] Received signal {signum}, shutting down...")
        self.running = False
        if self.process:
            self.process.terminate()
    
    def _get_main_py_path(self) -> Path:
        """Get path to main.py"""
        return Path(__file__).parent / "main.py"
    
    def _log_restart(self, reason: str):
        """Log restart event"""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] Watchdog restart: {reason} (attempt {self.retry_count}/{self.max_retries})\n"
        
        log_file = Path(__file__).parent / "watchdog.log"
        with open(log_file, 'a') as f:
            f.write(log_entry)
    
    def start(self):
        """Start watchdog monitoring loop"""
        print("[Watchdog] Starting GuardWatch watchdog process")
        print(f"[Watchdog] Max retries: {self.max_retries}, Restart delay: {self.restart_delay}s")
        
        main_py = self._get_main_py_path()
        
        while self.running and self.retry_count < self.max_retries:
            try:
                print(f"[Watchdog] Starting GuardWatch (attempt {self.retry_count + 1})")
                
                # Start GuardWatch process
                self.process = subprocess.Popen(
                    [sys.executable, str(main_py)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # Wait for process to complete
                return_code = self.process.wait()
                
                if return_code == 0:
                    print("[Watchdog] GuardWatch exited normally")
                    break
                
                # Process crashed
                self.retry_count += 1
                reason = f"Exit code {return_code}"
                self._log_restart(reason)
                
                print(f"[Watchdog] GuardWatch crashed: {reason}")
                
                if self.retry_count < self.max_retries and self.running:
                    print(f"[Watchdog] Restarting in {self.restart_delay} seconds...")
                    time.sleep(self.restart_delay)
                
            except KeyboardInterrupt:
                print("[Watchdog] Interrupted by user")
                self.running = False
                break
            except Exception as e:
                self.retry_count += 1
                reason = f"Exception: {e}"
                self._log_restart(reason)
                print(f"[Watchdog] Error: {e}")
                
                if self.retry_count < self.max_retries and self.running:
                    time.sleep(self.restart_delay)
        
        if self.retry_count >= self.max_retries:
            print(f"[Watchdog] Max retries ({self.max_retries}) exceeded. Giving up.")
        
        print("[Watchdog] Shutting down")


def main():
    """Main entry point for watchdog"""
    import argparse
    
    parser = argparse.ArgumentParser(description="GuardWatch Watchdog Process")
    parser.add_argument("--max-retries", type=int, default=5, help="Maximum restart attempts")
    parser.add_argument("--restart-delay", type=int, default=10, help="Delay between restarts (seconds)")
    
    args = parser.parse_args()
    
    watchdog = Watchdog(max_retries=args.max_retries, restart_delay=args.restart_delay)
    watchdog.start()


if __name__ == "__main__":
    main()
