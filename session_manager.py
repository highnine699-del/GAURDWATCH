"""
Session Manager
Manages evidence sessions with automatic cleanup and rotation
"""
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict
from config import config
from database import EvidenceDatabase
from hashing import EvidenceHasher


class SessionManager:
    """Manages evidence sessions"""
    
    def __init__(self):
        self.evidence_root = config.get_evidence_root()
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.current_session_id: Optional[str] = None
        self.current_session_dir: Optional[Path] = None
        self.db: Optional[EvidenceDatabase] = None
        self.hasher: Optional[EvidenceHasher] = None
        
        # Run cleanup on initialization
        self.cleanup_old_sessions()
        self.enforce_size_limit()
    
    def create_session(self) -> str:
        """Create a new evidence session"""
        self.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session_dir = self.evidence_root / self.current_session_id
        self.current_session_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.current_session_dir / "webcam").mkdir(exist_ok=True)
        (self.current_session_dir / "steps").mkdir(exist_ok=True)
        (self.current_session_dir / "screenshots").mkdir(exist_ok=True)
        (self.current_session_dir / "file_activity").mkdir(exist_ok=True)
        
        # Initialize database
        db_path = self.current_session_dir / config.storage.get("database_name", "evidence.db")
        self.db = EvidenceDatabase(db_path)
        self.db.create_session(self.current_session_id)
        
        # Initialize hasher
        self.hasher = EvidenceHasher(self.current_session_dir)
        
        return self.current_session_id
    
    def end_session(self) -> None:
        """End current session"""
        if self.db and self.current_session_id:
            self.db.end_session(self.current_session_id)
    
    def get_session_dir(self) -> Path:
        """Get current session directory"""
        return self.current_session_dir
    
    def get_session_id(self) -> str:
        """Get current session ID"""
        return self.current_session_id
    
    def get_database(self) -> EvidenceDatabase:
        """Get current session database"""
        return self.db
    
    def get_hasher(self) -> EvidenceHasher:
        """Get current session hasher"""
        return self.hasher
    
    def cleanup_old_sessions(self) -> int:
        """Remove sessions older than retention period"""
        if not config.retention.get("enabled", True):
            return 0
        
        retain_days = config.retention.get("retain_days", 30)
        cutoff = datetime.now() - timedelta(days=retain_days)
        
        removed = 0
        for session_dir in self.evidence_root.iterdir():
            if not session_dir.is_dir():
                continue
            
            try:
                # Parse session ID as datetime
                session_date = datetime.strptime(session_dir.name, "%Y%m%d_%H%M%S")
                
                if session_date < cutoff:
                    # Compress before deleting if enabled
                    if config.retention.get("compress_old", False):
                        self._compress_session(session_dir)
                    
                    # Delete session
                    shutil.rmtree(session_dir)
                    removed += 1
            except (ValueError, Exception):
                continue
        
        return removed
    
    def _compress_session(self, session_dir: Path) -> None:
        """Compress a session directory"""
        import zipfile
        
        zip_path = session_dir.parent / f"{session_dir.name}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in session_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(session_dir.parent)
                    zipf.write(file_path, arcname)
    
    def get_total_size(self) -> int:
        """Get total size of all evidence in bytes"""
        total = 0
        for session_dir in self.evidence_root.iterdir():
            if session_dir.is_dir():
                for file_path in session_dir.rglob('*'):
                    if file_path.is_file():
                        total += file_path.stat().st_size
        return total
    
    def enforce_size_limit(self) -> int:
        """Remove oldest sessions if size limit exceeded"""
        max_size_gb = config.retention.get("max_size_gb", 50)
        max_size_bytes = max_size_gb * 1024 * 1024 * 1024
        
        current_size = self.get_total_size()
        
        if current_size <= max_size_bytes:
            return 0
        
        # Get all sessions sorted by date
        sessions = []
        for session_dir in self.evidence_root.iterdir():
            if session_dir.is_dir():
                try:
                    session_date = datetime.strptime(session_dir.name, "%Y%m%d_%H%M%S")
                    size = sum(f.stat().st_size for f in session_dir.rglob('*') if f.is_file())
                    sessions.append((session_date, session_dir, size))
                except (ValueError, Exception):
                    continue
        
        # Sort by date (oldest first)
        sessions.sort(key=lambda x: x[0])
        
        removed = 0
        for session_date, session_dir, size in sessions:
            if current_size <= max_size_bytes:
                break
            
            try:
                shutil.rmtree(session_dir)
                current_size -= size
                removed += 1
            except Exception:
                continue
        
        return removed
    
    def list_sessions(self) -> List[Dict]:
        """List all sessions with metadata"""
        sessions = []
        
        for session_dir in self.evidence_root.iterdir():
            if not session_dir.is_dir():
                continue
            
            try:
                session_date = datetime.strptime(session_dir.name, "%Y%m%d_%H%M%S")
                size = sum(f.stat().st_size for f in session_dir.rglob('*') if f.is_file())
                
                # Check if database exists
                db_path = session_dir / config.storage.get("database_name", "evidence.db")
                has_db = db_path.exists()
                
                sessions.append({
                    "id": session_dir.name,
                    "date": session_date.isoformat(),
                    "size_bytes": size,
                    "size_mb": size / (1024 * 1024),
                    "has_database": has_db
                })
            except (ValueError, Exception):
                continue
        
        # Sort by date descending
        sessions.sort(key=lambda x: x["date"], reverse=True)
        
        return sessions
