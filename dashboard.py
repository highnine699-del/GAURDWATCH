"""
Enhanced Web Dashboard with Active Controls
Real-time monitoring with pause, screenshot, export, search, filter, download
WebSockets support for real-time updates
"""
import os
import sys
import threading
import webbrowser
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request, send_file
from event_bus import event_bus
from config import config
from database import EvidenceDatabase
from datetime import datetime

try:
    from flask_socketio import SocketIO, emit
    SOCKETIO_OK = True
except ImportError:
    SocketIO = None
    emit = None
    SOCKETIO_OK = False


class Dashboard:
    """Enhanced web dashboard for GuardWatch"""
    
    def __init__(self, db: EvidenceDatabase, session_id: str, session_dir: Path):
        import os
        import secrets
        self.db = db
        self.session_id = session_id
        self.session_dir = session_dir
        self.app = Flask(__name__)
        # Generate secure random key or use environment variable
        self.app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
        self.socketio = None
        self._running = False
        self._dashboard_thread: threading.Thread = None
        self._paused = False
        self._screenshot_callback = None
        self._export_callback = None
        self._stop_callback = None
        self._pause_callback = None
        
        self._setup_routes()
        if SOCKETIO_OK and config.dashboard.get("use_websockets", False):
            self._setup_websocket()
    
    def _setup_routes(self) -> None:
        """Setup dashboard routes"""
        
        # Authentication decorator
        from functools import wraps
        from flask import abort
        
        def require_auth(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                if config.dashboard.get("require_auth", False):
                    auth = request.authorization
                    username = os.environ.get('DASHBOARD_USERNAME', config.dashboard.get("username", ""))
                    password = os.environ.get('DASHBOARD_PASSWORD', config.dashboard.get("password", ""))
                    
                    if not auth or auth.username != username or auth.password != password:
                        return jsonify({"error": "Unauthorized"}), 401
                
                # Remote access check
                if config.dashboard.get("allow_remote", True):
                    allowed_hosts = config.dashboard.get("allowed_hosts", [])
                    if allowed_hosts:
                        client_ip = request.remote_addr
                        if client_ip not in allowed_hosts and client_ip != "127.0.0.1" and client_ip != "::1":
                            return jsonify({"error": "Access denied from this IP"}), 403
                
                return f(*args, **kwargs)
            return decorated
        
        @self.app.route('/')
        def index():
            """Main dashboard page"""
            return render_template_string(self._get_dashboard_html())
        
        
        @self.app.route('/api/stats')
        def get_stats():
            """Get session statistics"""
            stats = self.db.get_session_stats(self.session_id)
            # Fix field names for dashboard compatibility
            if 'high_priority_events' in stats:
                stats['high_priority'] = stats['high_priority_events']
            if 'duration_secs' not in stats and 'duration' in stats:
                stats['duration_secs'] = stats['duration']
            return jsonify(stats)
        
        @self.app.route('/api/search')
        @require_auth
        def search_events():
            """Search events"""
            query = request.args.get('q', '')
            if not query:
                return jsonify({"events": []})
            
            events = self.db.search_events(query, self.session_id)
            return jsonify({"events": events})
        
        @self.app.route('/api/events')
        @require_auth
        def get_events():
            """Get events with optional filters"""
            event_type = request.args.get('type')
            priority = request.args.get('priority')
            limit = request.args.get('limit', 100, type=int)
            
            events = self.db.get_events(
                session_id=self.session_id,
                event_type=event_type,
                priority=priority,
                limit=limit
            )
            return jsonify({"events": events})
        
        @self.app.route('/api/high_priority')
        @require_auth
        def get_high_priority():
            """Get high priority events"""
            limit = request.args.get('limit', 50, type=int)
            events = self.db.get_high_priority_events(self.session_id, limit)
            return jsonify({"events": events})
        
        @self.app.route('/api/pause', methods=['POST'])
        def pause_monitoring():
            """Pause/resume monitoring"""
            self._paused = not self._paused
            return jsonify({"paused": self._paused})
        
        @self.app.route('/api/screenshot', methods=['POST'])
        @require_auth
        def take_screenshot():
            """Trigger immediate screenshot"""
            if self._screenshot_callback:
                self._screenshot_callback()
                return jsonify({"success": True})
            return jsonify({"success": False, "error": "Screenshot callback not set"})
        
        @self.app.route('/api/export', methods=['POST'])
        @require_auth
        def export_evidence():
            """Export evidence"""
            format_type = request.json.get('format', 'json')
            if self._export_callback:
                result = self._export_callback(format_type)
                return jsonify({"success": True, "path": result})
            return jsonify({"success": False, "error": "Export callback not set"})
        
        @self.app.route('/api/stop', methods=['POST'])
        @require_auth
        def stop_monitoring():
            """Stop monitoring"""
            if self._stop_callback:
                self._stop_callback()
                return jsonify({"success": True})
            return jsonify({"success": False, "error": "Stop callback not set"})
        
        @self.app.route('/api/health')
        def get_health():
            """Get module health status"""
            # This would be populated by health monitor
            return jsonify({"status": "healthy"})
        
        @self.app.route('/api/open_folder')
        @require_auth
        def open_evidence_folder():
            """Open evidence folder in file explorer"""
            import subprocess
            try:
                if sys.platform == 'win32':
                    subprocess.Popen(['explorer', str(self.session_dir)])
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', str(self.session_dir)])
                else:
                    subprocess.Popen(['xdg-open', str(self.session_dir)])
                return jsonify({"success": True})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/api/download/<path:filename>')
        @require_auth
        def download_file(filename):
            """Download evidence file"""
            try:
                filepath = self.session_dir / filename
                # Path traversal protection: ensure file is within session directory
                resolved_path = filepath.resolve()
                if not str(resolved_path).startswith(str(self.session_dir.resolve())):
                    return jsonify({"error": "Access denied"}), 403
                if filepath.exists():
                    return send_file(filepath, as_attachment=True)
                return jsonify({"error": "File not found"}), 404
            except Exception as e:
                return jsonify({"error": str(e)}), 500
    
    def _setup_websocket(self) -> None:
        """Setup WebSocket event handlers"""
        if not self.socketio:
            return

        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection"""
            emit('connected', {'status': 'connected'})
        
        @self.socketio.on('subscribe_events')
        def handle_subscribe():
            """Subscribe to real-time event updates"""
            emit('subscribed', {'status': 'subscribed'})
    
    def broadcast_event(self, event: dict) -> None:
        """Broadcast event to all connected clients"""
        if config.dashboard.get("use_websockets", False):
            self.socketio.emit('new_event', event)
    
    def _get_dashboard_html(self) -> str:
        """Get dashboard HTML template"""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GuardWatch v4.0 — Enhanced Dashboard</title>
    <style>
        :root {
            --bg: #090b1220;
            --panel: #0f172a;
            --panel-soft: rgba(15, 23, 42, 0.8);
            --border: rgba(148, 163, 184, 0.18);
            --text: #e2e8f0;
            --muted: #94a3b8;
            --primary: #fb7185;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
        }

        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            background: radial-gradient(circle at top, rgba(251, 113, 133, 0.16), transparent 24%),
                        linear-gradient(180deg, #020617 0%, #0b1227 100%);
            color: var(--text);
            font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }

        .container {
            width: min(1380px, calc(100% - 40px));
            margin: 0 auto;
            padding: 30px 0;
        }

        .topbar {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-start;
            margin-bottom: 24px;
        }

        .title-group {
            display: grid;
            gap: 10px;
        }

        h1 {
            margin: 0;
            font-size: clamp(2rem, 2.4vw, 2.7rem);
            line-height: 1.05;
        }

        .subtitle {
            color: var(--muted);
            font-size: 1rem;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 0.65rem;
            padding: 12px 18px;
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.04);
            color: var(--text);
            font-weight: 600;
            white-space: nowrap;
        }

        .badge.live { color: var(--success); }
        .badge.paused { color: var(--warning); }

        .panel {
            background: rgba(15, 23, 42, 0.96);
            border: 1px solid var(--border);
            border-radius: 28px;
            padding: 28px;
            box-shadow: 0 34px 90px rgba(0, 0, 0, 0.18);
        }

        .controls {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 18px;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            border: 1px solid transparent;
            border-radius: 999px;
            padding: 12px 18px;
            font-size: 0.98rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
            color: var(--text);
            background: rgba(255, 255, 255, 0.05);
        }

        .btn:hover { transform: translateY(-1px); }
        .btn.primary { background: var(--primary); border-color: rgba(251, 113, 133, 0.35); }
        .btn.primary:hover { background: #f43f67; }
        .btn.secondary { background: rgba(255, 255, 255, 0.05); border-color: rgba(255, 255, 255, 0.08); }
        .btn.danger { background: var(--danger); border-color: rgba(248, 113, 113, 0.3); }

        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 18px;
            margin-top: 24px;
        }

        .status-card {
            padding: 22px;
            border-radius: 24px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .status-card strong {
            display: block;
            font-size: 1.9rem;
            color: #ffffff;
            margin-bottom: 8px;
        }

        .status-card span {
            color: var(--muted);
            font-size: 0.95rem;
        }

        .search-area {
            margin-top: 26px;
            display: grid;
            gap: 14px;
        }

        .search-row {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 12px;
        }

        .search-input {
            width: 100%;
            min-height: 52px;
            padding: 0 18px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.04);
            color: var(--text);
            font-size: 1rem;
        }

        .search-input:focus {
            outline: 2px solid rgba(251, 113, 133, 0.35);
        }

        .pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }

        .pill {
            padding: 10px 16px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.04);
            color: var(--text);
            cursor: pointer;
            transition: transform 0.15s ease, background-color 0.15s ease;
            white-space: nowrap;
        }

        .pill.active {
            background: rgba(251, 113, 133, 0.15);
            border-color: rgba(251, 113, 133, 0.35);
        }

        .pill:hover { transform: translateY(-1px); }

        .event-log {
            margin-top: 18px;
            max-height: 560px;
            overflow-y: auto;
            display: grid;
            gap: 14px;
            padding: 14px;
            border-radius: 22px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03);
        }

        .event-item {
            display: grid;
            grid-template-columns: minmax(120px, 180px) 1fr;
            gap: 14px;
            align-items: center;
            padding: 18px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.04);
        }

        .event-item.high {
            border-color: rgba(251, 113, 133, 0.35);
            background: rgba(251, 113, 133, 0.08);
        }

        .event-time {
            color: var(--muted);
            font-size: 0.95rem;
        }

        .event-detail {
            color: var(--text);
            font-size: 0.96rem;
            line-height: 1.6;
            word-break: break-word;
        }

        .event-severity {
            display: inline-flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            margin-bottom: 8px;
        }

        .event-severity.high {
            color: #ffe4e6;
            background: rgba(251, 113, 133, 0.16);
        }

        .event-severity.info {
            color: #d1fae5;
            background: rgba(52, 211, 153, 0.16);
        }

        .footer-note {
            margin-top: 28px;
            color: var(--muted);
            font-size: 0.95rem;
            text-align: center;
        }

        @media (max-width: 840px) {
            .topbar, .controls, .search-row { flex-direction: column; }
            .event-item { grid-template-columns: 1fr; }
            .status-grid { grid-template-columns: 1fr 1fr; }
        }

        @media (max-width: 560px) {
            .status-grid { grid-template-columns: 1fr; }
            .pill-row { justify-content: stretch; }
            .pill { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="topbar">
            <div class="title-group">
                <h1>GuardWatch Dashboard</h1>
                <div class="subtitle">Live event monitoring, evidence access, and quick action controls.</div>
            </div>
            <div class="badge live" id="live-badge">Live updates on</div>
        </div>

        <div class="panel">
            <div class="status-grid">
                <div class="status-card">
                    <strong id="session-id">Loading...</strong>
                    <span>Session</span>
                </div>
                <div class="status-card">
                    <strong id="uptime">0h 0m 0s</strong>
                    <span>Uptime</span>
                </div>
                <div class="status-card">
                    <strong id="total-events">0</strong>
                    <span>Total Events</span>
                </div>
                <div class="status-card">
                    <strong id="high-priority">0</strong>
                    <span>High Priority</span>
                </div>
            </div>

            <div class="controls">
                <button class="btn primary" onclick="togglePause()" id="pause-btn">⏸️ Pause</button>
                <button class="btn secondary" onclick="takeScreenshot()">📷 Screenshot</button>
                <button class="btn secondary" onclick="exportEvidence('json')">Export JSON</button>
                <button class="btn secondary" onclick="exportEvidence('html')">Export HTML</button>
                <button class="btn secondary" onclick="exportEvidence('csv')">Export CSV</button>
                <button class="btn secondary" onclick="openFolder()">Open Folder</button>
                <button class="btn danger" onclick="stopMonitoring()">⏹️ Stop</button>
            </div>

            <div class="search-area">
                <div class="search-row">
                    <input id="search-input" class="search-input" type="text" placeholder="Search events, alerts, or evidence..." onkeyup="handleSearch(event)">
                    <button class="btn primary" onclick="searchEvents()">Search</button>
                </div>
                <div class="pill-row">
                    <div class="pill active" onclick="filterEvents('all', this)">All Events</div>
                    <div class="pill" onclick="filterEvents('HIGH', this)">High Priority</div>
                    <div class="pill" onclick="filterEvents('WAKE_FROM_IDLE', this)">Wake Events</div>
                    <div class="pill" onclick="filterEvents('USB_INSERTED', this)">USB</div>
                    <div class="pill" onclick="filterEvents('FILE_CREATED', this)">Files</div>
                    <div class="pill" onclick="toggleAutoRefresh()" id="refresh-pill">Auto-refresh: On</div>
                </div>
            </div>

            <div class="status-grid" style="margin-top: 22px;">
                <div class="status-card">
                    <strong id="health-status">Checking...</strong>
                    <span>Dashboard Health</span>
                </div>
                <div class="status-card">
                    <strong id="event-count">0</strong>
                    <span>Loaded Events</span>
                </div>
                <div class="status-card">
                    <strong id="filter-label">All</strong>
                    <span>Active Filter</span>
                </div>
                <div class="status-card">
                    <strong id="health-update">—</strong>
                    <span>Last Refresh</span>
                </div>
            </div>

            <div style="margin-top: 28px;">
                <h2 style="margin-bottom: 14px; color: #f8fafc;">Live Event Stream</h2>
                <div class="event-log" id="event-log">
                    <div class="event-item">
                        <div class="event-time">Loading…</div>
                        <div class="event-detail">Live events will appear here shortly.</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="footer-note">Tip: use the search field and filters to narrow event details quickly.</div>
    </div>

    <script>
        let currentFilter = 'all';
        let autoRefresh = true;

        function loadStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('session-id').textContent = data.session_id || 'Unknown';
                    document.getElementById('uptime').textContent = formatUptime(data.uptime_secs || 0);
                    document.getElementById('total-events').textContent = data.total_events || 0;
                    document.getElementById('high-priority').textContent = data.high_priority || 0;
                })
                .catch(() => {
                    document.getElementById('health-status').textContent = 'Unavailable';
                });
        }

        function loadHealth() {
            fetch('/api/health')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('health-status').textContent = data.status || 'Healthy';
                    document.getElementById('health-update').textContent = new Date().toLocaleTimeString();
                    document.getElementById('live-badge').textContent = autoRefresh ? 'Live updates on' : 'Live updates paused';
                })
                .catch(() => {
                    document.getElementById('health-status').textContent = 'Offline';
                    document.getElementById('health-update').textContent = '—';
                });
        }

        function loadEvents() {
            let url = '/api/events';
            if (currentFilter === 'HIGH') {
                url = '/api/high_priority';
            } else if (currentFilter !== 'all') {
                url = `/api/events?type=${encodeURIComponent(currentFilter)}`;
            }

            fetch(url)
                .then(r => r.json())
                .then(data => {
                    const events = data.events || [];
                    const log = document.getElementById('event-log');
                    document.getElementById('event-count').textContent = events.length;
                    document.getElementById('filter-label').textContent = currentFilter === 'all' ? 'All' : currentFilter;

                    if (!events.length) {
                        log.innerHTML = '<div class="event-item"><div class="event-time">—</div><div class="event-detail">No events found.</div></div>';
                        return;
                    }

                    log.innerHTML = events.map(e => `
                        <div class="event-item ${e.priority === 'HIGH' ? 'high' : ''}">
                            <div class="event-time">${formatTimestamp(e.timestamp)}</div>
                            <div class="event-detail"><span class="event-severity ${e.priority?.toLowerCase() || 'info'}">${e.priority || 'INFO'}</span> <strong>${e.event_type}</strong>: ${e.detail}</div>
                        </div>
                    `).join('');
                })
                .catch(() => {
                    document.getElementById('event-log').innerHTML = '<div class="event-item"><div class="event-time">—</div><div class="event-detail">Unable to load events.</div></div>';
                });
        }

        function filterEvents(filter, button) {
            currentFilter = filter;
            document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
            if (button) button.classList.add('active');
            loadEvents();
        }

        function toggleAutoRefresh() {
            autoRefresh = !autoRefresh;
            document.getElementById('refresh-pill').textContent = `Auto-refresh: ${autoRefresh ? 'On' : 'Off'}`;
            document.getElementById('live-badge').textContent = autoRefresh ? 'Live updates on' : 'Live updates paused';
            if (autoRefresh) {
                loadStats();
                loadHealth();
                loadEvents();
            }
        }

        function togglePause() {
            fetch('/api/pause', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    const paused = data.paused;
                    document.getElementById('pause-btn').textContent = paused ? '▶️ Resume' : '⏸️ Pause';
                });
        }

        function takeScreenshot() {
            fetch('/api/screenshot', { method: 'POST' })
                .then(r => r.json())
                .then(data => alert(data.success ? 'Screenshot captured!' : data.error || 'Screenshot failed'));
        }

        function exportEvidence(format) {
            fetch('/api/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ format })
            })
                .then(r => r.json())
                .then(data => alert(data.success ? `Exported to ${data.path}` : data.error || 'Export failed'));
        }

        function openFolder() {
            fetch('/api/open_folder')
                .then(r => r.json())
                .then(data => { if (!data.success) alert(data.error || 'Unable to open folder'); });
        }

        function stopMonitoring() {
            if (!confirm('Stop monitoring?')) return;
            fetch('/api/stop', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        alert('Monitoring stopped.');
                        window.close();
                    }
                });
        }

        function searchEvents() {
            const query = document.getElementById('search-input').value.trim();
            if (!query) {
                return loadEvents();
            }

            fetch(`/api/search?q=${encodeURIComponent(query)}`)
                .then(r => r.json())
                .then(data => {
                    const events = data.events || [];
                    const log = document.getElementById('event-log');
                    document.getElementById('event-count').textContent = events.length;
                    document.getElementById('filter-label').textContent = `Search: ${query}`;

                    if (!events.length) {
                        log.innerHTML = '<div class="event-item"><div class="event-time">—</div><div class="event-detail">No search results.</div></div>';
                        return;
                    }

                    log.innerHTML = events.map(e => `
                        <div class="event-item ${e.priority === 'HIGH' ? 'high' : ''}">
                            <div class="event-time">${formatTimestamp(e.timestamp)}</div>
                            <div class="event-detail"><span class="event-severity ${e.priority?.toLowerCase() || 'info'}">${e.priority || 'INFO'}</span> <strong>${e.event_type}</strong>: ${e.detail}</div>
                        </div>
                    `).join('');
                })
                .catch(() => {
                    document.getElementById('event-log').innerHTML = '<div class="event-item"><div class="event-time">—</div><div class="event-detail">Search failed.</div></div>';
                });
        }

        function handleSearch(e) {
            if (e.key === 'Enter') searchEvents();
        }

        function formatTimestamp(timestamp) {
            if (!timestamp) return '--:--:--';
            const parts = timestamp.split('T');
            return parts[1] ? parts[1].split('.')[0] : timestamp;
        }

        function formatUptime(seconds) {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = seconds % 60;
            return `${h}h ${m}m ${s}s`;
        }

        setInterval(() => {
            if (autoRefresh) {
                loadStats();
                loadHealth();
                loadEvents();
            }
        }, 3000);

        loadStats();
        loadHealth();
        loadEvents();
    </script>
</body>
</html>
"""
    
    def set_screenshot_callback(self, callback) -> None:
        """Set callback for taking screenshots"""
        self._screenshot_callback = callback
    
    def set_export_callback(self, callback) -> None:
        """Set callback for exporting evidence"""
        self._export_callback = callback
    
    def set_stop_callback(self, callback) -> None:
        """Set callback for stopping monitoring"""
        self._stop_callback = callback
    
    def set_pause_callback(self, callback) -> None:
        """Set callback for pausing/resuming monitoring"""
        self._pause_callback = callback
    
    def start(self) -> None:
        """Start dashboard server"""
        if not config.dashboard.get("enabled", True):
            print("[Dashboard] Dashboard disabled in config")
            return
        
        self._running = True
        host = config.dashboard.get("host", "0.0.0.0")
        port = config.dashboard.get("port", 5555)
        
        use_websockets = config.dashboard.get("use_websockets", False)
        if use_websockets and not SOCKETIO_OK:
            print("[Dashboard] WebSocket support unavailable ; fallback to HTTP")
            use_websockets = False
        use_https = config.dashboard.get("use_https", False)
        
        ssl_context = None
        if use_https:
            ssl_cert = config.dashboard.get("ssl_cert", "")
            ssl_key = config.dashboard.get("ssl_key", "")
            if ssl_cert and ssl_key:
                ssl_context = (ssl_cert, ssl_key)
                print(f"[Dashboard] HTTPS enabled with SSL certificate")
        
        if use_websockets and self.socketio:
            # Run with SocketIO
            self._dashboard_thread = threading.Thread(
                target=self.socketio.run,
                kwargs={
                    "app": self.app,
                    "host": host,
                    "port": port,
                    "use_reloader": False,
                    "ssl_context": ssl_context
                },
                daemon=True
            )
        else:
            # Run with regular Flask
            self._dashboard_thread = threading.Thread(
                target=self.app.run,
                kwargs={
                    "host": host,
                    "port": port,
                    "use_reloader": False,
                    "ssl_context": ssl_context
                },
                daemon=True
            )
        
        self._dashboard_thread.start()
        
        protocol = "https" if use_https else "http"
        url = f"{protocol}://localhost:{port}"
        ws_status = "with WebSockets" if use_websockets else "with polling"
        remote_status = "Remote access enabled" if config.dashboard.get("allow_remote", True) else "Local only"
        print(f"[Dashboard] Dashboard running at {url} {ws_status} ({remote_status})")
        
        # Auto-open browser only if local
        if host in ["127.0.0.1", "localhost"] or not config.dashboard.get("allow_remote", True):
            try:
                webbrowser.open(url)
            except Exception:
                pass
    
    def stop(self) -> None:
        """Stop dashboard server"""
        self._running = False
        # Flask's built-in server has no clean stop; daemon thread dies with main process