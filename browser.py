"""
Browser History Module
Captures before/after snapshots of browser history
"""
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from event_bus import Event, event_bus
from config import config
from database import EvidenceDatabase


class BrowserModule:
    """Browser history monitoring module"""
    
    def __init__(self, session_dir: Path, db: EvidenceDatabase, session_id: str):
        import os
        import platform
        self.session_dir = session_dir
        self.db = db
        self.session_id = session_id
        self._running = False
        self._is_windows = platform.system() == "Windows"
        
        if self._is_windows:
            self._browser_dbs = {
                "Chrome": Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Google/Chrome/User Data/Default/History",
                "Edge": Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Microsoft/Edge/User Data/Default/History",
            }
            self._firefox_base = Path(os.environ.get("APPDATA", Path.home())) / "Mozilla/Firefox/Profiles"
        else:
            # Linux/Mac paths
            self._browser_dbs = {}
            self._firefox_base = Path.home() / ".mozilla" / "firefox"
    
    def _read_chromium_history(self, name: str, db_path: Path) -> List[Dict]:
        """Read Chromium-based browser history"""
        if not db_path.exists():
            return []
        
        results = []
        tmp = self.session_dir / f"_tmp_{name}"
        
        try:
            shutil.copy2(db_path, tmp)
            with sqlite3.connect(tmp) as con:
                rows = con.execute(
                    "SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 150"
                ).fetchall()
            OFFSET = 11644473600
            results = [
                {
                    "time": datetime.fromtimestamp(t/1_000_000 - OFFSET).strftime("%Y-%m-%d %H:%M:%S"),
                    "title": title or "",
                    "url": url
                }
                for url, title, t in rows
            ]
        except Exception as e:
            results = [{"error": str(e)}]
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
        
        return results
    
    def _read_firefox_history(self) -> List[Dict]:
        """Read Firefox browser history"""
        results = []
        
        if not self._firefox_base.exists():
            return results
        
        for profile in self._firefox_base.iterdir():
            places = profile / "places.sqlite"
            if places.exists():
                tmp = self.session_dir / "_tmp_firefox"
                
                try:
                    shutil.copy2(places, tmp)
                    with sqlite3.connect(tmp) as con:
                        rows = con.execute(
                            "SELECT url, title, last_visit_date FROM moz_places WHERE last_visit_date IS NOT NULL ORDER BY last_visit_date DESC LIMIT 150"
                        ).fetchall()
                    results = [
                        {
                            "time": datetime.fromtimestamp(t/1_000_000).strftime("%Y-%m-%d %H:%M:%S"),
                            "title": title or "",
                            "url": url
                        }
                        for url, title, t in rows
                    ]
                except Exception as e:
                    results = [{"error": str(e)}]
                finally:
                    if tmp.exists():
                        try:
                            tmp.unlink()
                        except Exception:
                            pass
                
                break
        
        return results
    
    def capture_snapshot(self, label: str) -> None:
        """Capture browser history snapshot"""
        if not config.modules.get("browser_history", True):
            event_bus.publish(Event(
                event_type="BROWSER_SKIP",
                priority="INFO",
                detail="Browser history disabled in config",
                source="browser"
            ))
            return
        
        results = {}
        
        if not self._is_windows:
            event_bus.publish(Event(
                event_type="BROWSER_SKIP",
                priority="INFO",
                detail="Browser history capture only supported on Windows",
                source="browser"
            ))
            return
        
        # Read Chromium browsers
        for name, path in self._browser_dbs.items():
            results[name] = self._read_chromium_history(name, path)
        
        # Read Firefox
        results["Firefox"] = self._read_firefox_history()
        
        # Save to file
        import json
        out = self.session_dir / f"browser_history_{label}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        total = sum(len(v) for v in results.values() if isinstance(v, list))
        
        event_bus.publish(Event(
            event_type="BROWSER_SNAPSHOT",
            priority="INFO",
            detail=f"{label}: {total} URLs from {list(results.keys())}",
            source="browser",
            data={"label": label, "total_urls": total, "browsers": list(results.keys())}
        ))
    
    def start(self) -> None:
        """Start browser module"""
        self._running = True
        event_bus.publish(Event(
            event_type="BROWSER_START",
            priority="INFO",
            detail="Browser module started",
            source="browser"
        ))
    
    def stop(self) -> None:
        """Stop browser module"""
        self._running = False
