"""
SQLite Database for Evidence Storage
Provides structured, queryable evidence storage
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager


class EvidenceDatabase:
    """SQLite database for structured evidence storage"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialize_db()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _initialize_db(self) -> None:
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_secs INTEGER,
                    total_events INTEGER DEFAULT 0,
                    high_priority_events INTEGER DEFAULT 0
                )
            """)
            
            # Events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    priority TEXT DEFAULT 'INFO',
                    detail TEXT,
                    source TEXT,
                    data TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Files table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_hash TEXT,
                    size_bytes INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Evidence hashes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evidence_hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    verified BOOLEAN DEFAULT 1,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                    UNIQUE(session_id, file_path)
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_session ON files(session_id)")
    
    def create_session(self, session_id: str) -> int:
        """Create a new session record"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (session_id, start_time) VALUES (?, ?)",
                (session_id, datetime.now().isoformat())
            )
            return cursor.lastrowid
    
    def end_session(self, session_id: str) -> None:
        """Update session with end time and duration"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT start_time FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            
            if row:
                start_time = datetime.fromisoformat(row['start_time'])
                end_time = datetime.now()
                duration = int((end_time - start_time).total_seconds())
                
                cursor.execute(
                    """UPDATE sessions 
                       SET end_time = ?, duration_secs = ? 
                       WHERE session_id = ?""",
                    (end_time.isoformat(), duration, session_id)
                )
    
    def add_event(self, session_id: str, event_type: str, priority: str = "INFO",
                  detail: str = "", source: str = "", data: Dict = None) -> int:
        """Add an event to the database"""
        if data is None:
            data = {}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO events 
                   (session_id, event_type, timestamp, priority, detail, source, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, event_type, datetime.now().isoformat(),
                 priority, detail, source, json.dumps(data))
            )
            
            # Update session event counts
            cursor.execute(
                """UPDATE sessions 
                   SET total_events = total_events + 1,
                       high_priority_events = high_priority_events + ?
                   WHERE session_id = ?""",
                (1 if priority == "HIGH" else 0, session_id)
            )
            
            return cursor.lastrowid
    
    def add_file(self, session_id: str, file_path: str, file_type: str,
                 file_hash: str = None, size_bytes: int = 0) -> int:
        """Add a file record to the database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO files 
                   (session_id, file_path, file_type, file_hash, size_bytes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, file_path, file_type, file_hash,
                 size_bytes, datetime.now().isoformat())
            )
            return cursor.lastrowid
    
    def store_hash(self, session_id: str, file_path: str, file_hash: str) -> None:
        """Store evidence file hash"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO evidence_hashes 
                   (session_id, file_path, hash)
                   VALUES (?, ?, ?)""",
                (session_id, file_path, file_hash)
            )
    
    def verify_hash(self, session_id: str, file_path: str, current_hash: str) -> bool:
        """Verify file hash against stored hash"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT hash FROM evidence_hashes WHERE session_id = ? AND file_path = ?",
                (session_id, file_path)
            )
            row = cursor.fetchone()
            
            if not row:
                return False
            
            stored_hash = row['hash']
            is_valid = stored_hash == current_hash
            
            # Update verification status
            cursor.execute(
                "UPDATE evidence_hashes SET verified = ? WHERE session_id = ? AND file_path = ?",
                (is_valid, session_id, file_path)
            )
            
            return is_valid
    
    def get_events(self, session_id: str = None, event_type: str = None,
                   priority: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Query events with optional filters"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM events WHERE 1=1"
            params = []
            
            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)
            
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            
            if priority:
                query += " AND priority = ?"
                params.append(priority)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            events = []
            for row in cursor.fetchall():
                event = dict(row)
                if event['data']:
                    event['data'] = json.loads(event['data'])
                events.append(event)
            
            return events
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get statistics for a session"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            session = dict(cursor.fetchone())
            
            # Count files by type
            cursor.execute(
                "SELECT file_type, COUNT(*) as count FROM files WHERE session_id = ? GROUP BY file_type",
                (session_id,)
            )
            file_counts = {row['file_type']: row['count'] for row in cursor.fetchall()}
            
            session['file_counts'] = file_counts
            
            return session
    
    def search_events(self, search_term: str, session_id: str = None) -> List[Dict[str, Any]]:
        """Search events by detail text"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM events WHERE detail LIKE ?"
            params = [f"%{search_term}%"]
            
            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)
            
            query += " ORDER BY timestamp DESC LIMIT 100"
            
            cursor.execute(query, params)
            
            events = []
            for row in cursor.fetchall():
                event = dict(row)
                if event['data']:
                    event['data'] = json.loads(event['data'])
                events.append(event)
            
            return events
    
    def get_high_priority_events(self, session_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get high priority events"""
        return self.get_events(session_id=session_id, priority="HIGH", limit=limit)
    
    def cleanup_old_sessions(self, retain_days: int = 30) -> int:
        """Remove sessions older than retain_days"""
        cutoff_date = datetime.now().timestamp() - (retain_days * 86400)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """DELETE FROM sessions 
                   WHERE datetime(start_time) < datetime(?, 'unixepoch')""",
                (cutoff_date,)
            )
            return cursor.rowcount
