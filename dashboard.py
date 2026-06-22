"""
Enhanced Web Dashboard with Active Controls
Real-time monitoring with pause, screenshot, export, search, filter, download
WebSockets support for real-time updates
"""
import threading
import webbrowser
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request, send_file
from flask_socketio import SocketIO, emit
from event_bus import event_bus
from config import config
from database import EvidenceDatabase
from datetime import datetime


class Dashboard:
    """Enhanced web dashboard for GuardWatch"""
    
    def __init__(self, db: EvidenceDatabase, session_id: str, session_dir: Path):
        self.db = db
        self.session_id = session_id
        self.session_dir = session_dir
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = 'guardwatch-secret-key'
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self._running = False
        self._dashboard_thread: threading.Thread = None
        self._paused = False
        self._screenshot_callback = None
        self._export_callback = None
        self._stop_callback = None
        self._pause_callback = None
        
        self._setup_routes()
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
                    username = config.dashboard.get("username", "")
                    password = config.dashboard.get("password", "")
                    
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
        
        @self.app.route('/api/events')
    @require_auth
        def get_events():
            """Get recent events"""
            limit = request.args.get('limit', 50, type=int)
            event_type = request.args.get('type')
            priority = request.args.get('priority')
            
            events = self.db.get_events(
                session_id=self.session_id,
                event_type=event_type,
                priority=priority,
                limit=limit
            )
            return jsonify({"events": events})
        
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
                subprocess.Popen(['explorer', str(self.session_dir)])
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
        * { margin:0; padding:0; box-sizing:border-box }
        body { background:#0a0e27; color:#e0e0e0; font-family:'Courier New',monospace; padding:20px }
        .container { max-width:1600px; margin:0 auto }
        .header { border-bottom:2px solid #ff3333; padding-bottom:15px; margin-bottom:25px }
        h1 { color:#ff3333; font-size:28px; margin-bottom:5px }
        .status { display:flex; gap:40px; margin-top:15px; font-size:13px }
        .status-item { display:flex; gap:10px }
        .status-label { color:#888 }
        .status-value { color:#ff8888; font-weight:bold }
        
        .controls { display:flex; gap:10px; margin-bottom:25px; flex-wrap:wrap }
        .btn { padding:10px 20px; border:none; border-radius:4px; cursor:pointer; font-weight:bold; transition:all 0.2s }
        .btn-primary { background:#ff3333; color:white }
        .btn-primary:hover { background:#cc0000 }
        .btn-secondary { background:#1a1f3a; color:#e0e0e0; border:1px solid #333 }
        .btn-secondary:hover { background:#2a2f4a }
        .btn-danger { background:#ff0000; color:white }
        .btn-danger:hover { background:#cc0000 }
        .btn:disabled { opacity:0.5; cursor:not-allowed }
        
        .search-bar { display:flex; gap:10px; margin-bottom:25px }
        .search-input { flex:1; padding:10px; background:#1a1f3a; border:1px solid #333; color:#e0e0e0; border-radius:4px }
        .search-input:focus { outline:none; border-color:#ff3333 }
        
        .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:25px }
        .card { background:#1a1f3a; border:1px solid #333; border-radius:6px; padding:15px }
        .card h2 { color:#ff6666; font-size:14px; text-transform:uppercase; margin-bottom:12px; border-bottom:1px solid #333; padding-bottom:8px }
        
        .event-log { background:#1a1f3a; border:1px solid #333; border-radius:6px; padding:15px; max-height:600px; overflow-y:auto }
        .event { padding:8px; border-bottom:1px solid #222; font-size:12px; line-height:1.4 }
        .event:last-child { border-bottom:none }
        .event.HIGH { background:#4a0000; color:#ff9999; border-left:3px solid #ff3333 }
        .event.INFO { color:#b0b0b0 }
        .event-time { color:#888; font-size:11px }
        .event-detail { margin-left:10px }
        
        .stat-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:15px }
        .stat-item { background:#2a2f4a; padding:15px; border-radius:6px; text-align:center }
        .stat-value { font-size:24px; font-weight:bold; color:#ff6666 }
        .stat-label { font-size:12px; color:#888; margin-top:5px }
        
        .filter-bar { display:flex; gap:10px; margin-bottom:15px; flex-wrap:wrap }
        .filter-btn { padding:5px 15px; background:#2a2f4a; border:1px solid #333; color:#e0e0e0; border-radius:4px; cursor:pointer; font-size:12px }
        .filter-btn.active { background:#ff3333; color:white }
        
        .paused-banner { background:#ff0000; color:white; padding:10px; text-align:center; margin-bottom:20px; display:none }
        .paused-banner.visible { display:block }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ GuardWatch v4.0 — Enhanced Dashboard</h1>
            <div class="status">
                <div class="status-item">
                    <span class="status-label">Session:</span>
                    <span class="status-value" id="session-id">Loading...</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Uptime:</span>
                    <span class="status-value" id="uptime">0s</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Total Events:</span>
                    <span class="status-value" id="total-events">0</span>
                </div>
                <div class="status-item">
                    <span class="status-label">High Priority:</span>
                    <span class="status-value" id="high-priority">0</span>
                </div>
            </div>
        </div>
        
        <div class="paused-banner" id="paused-banner">
            ⏸️ MONITORING PAUSED
        </div>
        
        <div class="controls">
            <button class="btn btn-primary" onclick="togglePause()" id="pause-btn">⏸️ Pause</button>
            <button class="btn btn-secondary" onclick="takeScreenshot()">📷 Screenshot</button>
            <button class="btn btn-secondary" onclick="exportEvidence('json')">📦 Export JSON</button>
            <button class="btn btn-secondary" onclick="exportEvidence('html')">📄 Export HTML</button>
            <button class="btn btn-secondary" onclick="exportEvidence('csv')">📊 Export CSV</button>
            <button class="btn btn-secondary" onclick="openFolder()">📁 Open Folder</button>
            <button class="btn btn-danger" onclick="stopMonitoring()">⏹️ Stop</button>
        </div>
        
        <div class="search-bar">
            <input type="text" class="search-input" id="search-input" placeholder="Search events..." onkeyup="handleSearch(event)">
            <button class="btn btn-primary" onclick="searchEvents()">🔍 Search</button>
        </div>
        
        <div class="filter-bar">
            <button class="filter-btn active" onclick="filterEvents('all', this)">All</button>
            <button class="filter-btn" onclick="filterEvents('HIGH', this)">⚠️ High Priority</button>
            <button class="filter-btn" onclick="filterEvents('WAKE_FROM_IDLE', this)">Wake Events</button>
            <button class="filter-btn" onclick="filterEvents('USB_INSERTED', this)">USB</button>
            <button class="filter-btn" onclick="filterEvents('FILE_CREATED', this)">Files</button>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>📊 Statistics</h2>
                <div class="stat-grid" id="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value" id="stat-webcam">0</div>
                        <div class="stat-label">Webcam Photos</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="stat-steps">0</div>
                        <div class="stat-label">Steps</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="stat-screenshots">0</div>
                        <div class="stat-label">Screenshots</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="stat-files">0</div>
                        <div class="stat-label">File Events</div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>📡 Live Event Stream</h2>
                <div class="event-log" id="event-log">
                    <div class="event">Loading events...</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentFilter = 'all';
        let autoRefresh = true;
        
        function loadStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('session-id').textContent = data.session_id;
                    document.getElementById('uptime').textContent = formatUptime(data.uptime_secs);
                    document.getElementById('total-events').textContent = data.total_events;
                    document.getElementById('high-priority').textContent = data.high_priority;
                    
                    document.getElementById('stat-webcam').textContent = data.files?.webcam || 0;
                    document.getElementById('stat-steps').textContent = data.files?.steps || 0;
                    document.getElementById('stat-screenshots').textContent = data.files?.screenshots || 0;
                    document.getElementById('stat-files').textContent = data.files?.file_activity || 0;
                });
        }
        
        function loadEvents() {
            const url = currentFilter === 'HIGH' ? '/api/high_priority' : 
                        currentFilter === 'all' ? '/api/events' :
                        `/api/events?type=${currentFilter}`;
            
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    const log = document.getElementById('event-log');
                    log.innerHTML = data.events.map(e => `
                        <div class="event ${e.priority}">
                            <span class="event-time">[${e.timestamp.split('T')[1].split('.')[0]}]</span>
                            <span class="event-detail"><strong>${e.event_type}</strong>: ${e.detail}</span>
                        </div>
                    `).join('');
                });
        }
        
        function filterEvents(filter, btn) {
            currentFilter = filter;
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadEvents();
        }
        
        function togglePause() {
            fetch('/api/pause', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    document.getElementById('pause-btn').textContent = data.paused ? '▶️ Resume' : '⏸️ Pause';
                    document.getElementById('paused-banner').classList.toggle('visible', data.paused);
                });
        }
        
        function takeScreenshot() {
            fetch('/api/screenshot', { method: 'POST' })
                .then(r => r.json())
                .then(data => alert(data.success ? 'Screenshot captured!' : data.error));
        }
        
        function exportEvidence(format) {
            fetch('/api/export', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({format}) })
                .then(r => r.json())
                .then(data => alert(data.success ? `Exported to ${data.path}` : data.error));
        }
        
        function openFolder() {
            fetch('/api/open_folder')
                .then(r => r.json())
                .then(data => { if (!data.success) alert(data.error); });
        }
        
        function stopMonitoring() {
            if (confirm('Stop monitoring?')) {
                fetch('/api/stop', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            alert('Monitoring stopped. Dashboard will close.');
                            window.close();
                        }
                    });
            }
        }
        
        function searchEvents() {
            const query = document.getElementById('search-input').value;
            if (!query) return loadEvents();
            
            fetch(`/api/search?q=${encodeURIComponent(query)}`)
                .then(r => r.json())
                .then(data => {
                    const log = document.getElementById('event-log');
                    log.innerHTML = data.events.map(e => `
                        <div class="event ${e.priority}">
                            <span class="event-time">[${e.timestamp.split('T')[1].split('.')[0]}]</span>
                            <span class="event-detail"><strong>${e.event_type}</strong>: ${e.detail}</span>
                        </div>
                    `).join('');
                });
        }
        
        function handleSearch(e) {
            if (e.key === 'Enter') searchEvents();
        }
        
        function formatUptime(seconds) {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = seconds % 60;
            return `${h}h ${m}m ${s}s`;
        }
        
        // Auto-refresh
        setInterval(() => {
            if (autoRefresh) {
                loadStats();
                loadEvents();
            }
        }, 2000);
        
        // Initial load
        loadStats();
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
        use_https = config.dashboard.get("use_https", False)
        
        ssl_context = None
        if use_https:
            ssl_cert = config.dashboard.get("ssl_cert", "")
            ssl_key = config.dashboard.get("ssl_key", "")
            if ssl_cert and ssl_key:
                ssl_context = (ssl_cert, ssl_key)
                print(f"[Dashboard] HTTPS enabled with SSL certificate")
        
        if use_websockets:
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