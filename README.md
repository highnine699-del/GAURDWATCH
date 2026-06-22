# GuardWatch v4.0 — PC Intruder Evidence Suite (Refactored)

**Captures timestamped proof of unauthorized access on YOUR OWN PC.**
**MAJOR REFACTOR: Modular architecture, SQLite storage, health monitoring, risk engine, enhanced dashboard**

---

## What's New in v4.0

GuardWatch v4.0 is a complete architectural overhaul addressing engineering maturity concerns:

### Architecture Improvements
- **Modular Design**: Split from 1000+ line monolith into 14 focused modules
- **Event Bus**: Decoupled communication using pub/sub pattern
- **SQLite Database**: Replaced JSON files with queryable evidence storage
- **Configuration System**: All settings configurable via `config.json`
- **Health Monitoring**: Automatic module health checks with recovery

### New Features
- **Risk Engine**: Correlates events to calculate threat levels
- **Enhanced Dashboard**: Pause, screenshot, export, search, filter, download controls
- **Multiple Export Formats**: HTML, JSON, CSV, ZIP, PDF (optional)
- **Evidence Integrity**: SHA256 verification for all files
- **Session Summaries**: Detailed shutdown reports with risk assessment
- **Search Functionality**: Full-text search across all events
- **AES Encryption**: Optional encryption for sensitive evidence
- **Dashboard Authentication**: Optional password protection

### Reliability
- **Automatic Recovery**: Failed modules auto-restart with configurable retry logic
- **Log Rotation**: Automatic cleanup of old sessions (configurable retention)
- **Structured Logging**: JSON-formatted events for easier analysis

---

## Installation

### Step 1: Install Python Dependencies

**Double-click `setup.bat`** to install all required packages automatically.

Or manually run:
```cmd
pip install mss Pillow pyperclip pynput opencv-python pywin32 flask watchdog cryptography
```

**Required packages:**
- `mss` — Fast screenshot capture
- `Pillow` — Image processing for annotated screenshots
- `pyperclip` — Clipboard monitoring
- `pynput` — Keyboard & mouse tracking
- `opencv-python` — Webcam capture
- `pywin32` — Windows API (for event log, window titles)
- `flask` — Web dashboard server
- `watchdog` — File activity monitoring
- `cryptography` — AES encryption for sensitive evidence

---

## Quick Start

### Option 1: Monitor Now with Web Dashboard (Recommended)
```cmd
python main.py
```
GuardWatch starts monitoring and launches a live web dashboard at `http://localhost:5555`. Press **Ctrl+C** to stop.

### Option 2: Run Silent (No Console)
```cmd
pythonw main.py
```
Runs completely in background — no visible window. Dashboard still available at `http://localhost:5555`.

### Option 3: View Evidence from Previous Sessions
```cmd
python main.py --report
```
Lists all sessions with metadata.

### Option 4: Delete All Evidence
```cmd
python main.py --clear
```
Securely wipes all evidence (asks for confirmation).

---

## Configuration

All settings are in `config.json`. Key sections:

### Module Control
```json
"modules": {
  "idle_wake": true,
  "webcam": true,
  "screenshots": true,
  "keystrokes": true,
  ...
}
```

### Dashboard Settings
```json
"dashboard": {
  "enabled": true,
  "port": 5555,
  "require_auth": false,
  "username": "",
  "password": ""
}
```

### Storage & Retention
```json
"storage": {
  "use_sqlite": true,
  "verify_integrity": true,
  "encrypt_sensitive": false
},
"retention": {
  "enabled": true,
  "retain_days": 30,
  "max_size_gb": 50
}
```

### Risk Engine
```json
"risk_engine": {
  "enabled": true,
  "correlation_window_sec": 300,
  "high_priority_threshold": 3,
  "critical_threshold": 5
}
```

---

## Architecture

### Module Structure
```
guardwatch/
├── main.py              # Application entry point
├── config.py            # Configuration management
├── config.json          # Configuration file
├── event_bus.py         # Central event bus
├── database.py          # SQLite evidence storage
├── health_monitor.py    # Module health & recovery
├── hashing.py           # SHA256 integrity verification
├── encryption.py        # AES encryption
├── session_manager.py   # Session lifecycle
├── risk_engine.py       # Correlated threat analysis
├── dashboard.py         # Enhanced web dashboard
├── report.py            # Multi-format report generator
├── webcam.py            # Webcam capture module
├── keyboard.py          # Keystroke logger
├── clipboard.py         # Clipboard monitor
├── steps.py             # Steps recorder
├── screenshots.py       # Timed screenshots
├── usb.py               # USB detection
├── browser.py           # Browser history
├── file_monitor.py      # File activity monitoring
├── monitor.py           # Idle/wake detector
├── window_tracker.py    # Window title tracking
└── failed_logins.py     # Failed login counter
```

### Event Flow
```
Module → Event Bus → Dashboard
                  → Database
                  → Risk Engine
                  → Health Monitor
```

---

## Enhanced Dashboard Features

The v4.0 dashboard includes:

### Active Controls
- **Pause/Resume**: Temporarily stop monitoring
- **Screenshot**: Trigger immediate screenshot
- **Export**: Download evidence in JSON/HTML/CSV/ZIP
- **Open Folder**: Open evidence directory
- **Stop**: Shutdown GuardWatch

### Search & Filter
- Full-text search across all events
- Filter by event type (Wake, USB, Files, etc.)
- Filter by priority (High priority only)
- Real-time event stream

### Statistics
- Session uptime
- Total events count
- High-priority events count
- Evidence file counts (webcam, steps, screenshots, files)

---

## Evidence Storage

### SQLite Database
Evidence is now stored in SQLite for fast querying:
- Sessions table (metadata, duration, event counts)
- Events table (all events with timestamps, priority, data)
- Files table (evidence file metadata)
- Evidence hashes table (SHA256 integrity verification)

### File Structure
```
gw_evidence/
└── 20260622_011500/
    ├── evidence.db              # SQLite database
    ├── evidence_hashes.json     # SHA256 hashes
    ├── webcam/                  # Webcam photos
    ├── steps/                   # Annotated screenshots
    ├── screenshots/             # Timed captures
    ├── file_activity/           # File change logs
    ├── keystrokes.txt           # Keystrokes
    ├── clipboard.txt            # Clipboard content
    ├── window_titles.txt        # Window focus history
    ├── browser_history_before.json
    ├── browser_history_after.json
    ├── evidence_report.html     # HTML report
    ├── evidence_report.json     # JSON report
    └── evidence_report.csv     # CSV report
```

---

## Risk Engine

The risk engine correlates events to calculate threat levels:

### Pattern Detection
- **Wake + USB**: Critical (potential data theft)
- **Wake + Clipboard**: High (password stealing)
- **Multiple USB**: Critical (bulk data exfiltration)
- **Failed Logins**: High (brute force attempt)
- **Suspicious Files**: High (malware installation)

### Risk Levels
- **LOW**: 0-1 high-priority events
- **MEDIUM**: 1-2 high-priority events
- **HIGH**: 3-4 high-priority events
- **CRITICAL**: 5+ high-priority events or dangerous patterns

---

## Health Monitoring & Recovery

### Module Health
Each module reports health status:
- **HEALTHY**: Operating normally
- **DEGRADED**: No recent heartbeat
- **FAILED**: Error occurred
- **RESTARTING**: Recovery in progress

### Automatic Recovery
Configurable automatic recovery for failed modules:
- Maximum retry attempts (default: 3)
- Retry delay (default: 10 seconds)
- Configurable per module

---

## Evidence Integrity

### SHA256 Verification
All evidence files are automatically hashed:
- Hashes stored in `evidence_hashes.json`
- Verification on shutdown
- Integrity report generated

### Encryption (Optional)
AES-256 encryption for sensitive files:
- Keystrokes
- Clipboard content
- Configurable via `config.json`

---

## Export Formats

### Available Formats
- **HTML**: Browser-friendly report with styling
- **JSON**: Machine-readable structured data
- **CSV**: Spreadsheet-compatible format
- **ZIP**: Complete evidence archive
- **PDF**: Professional report (requires weasyprint)

### Export via Dashboard
Use the dashboard export buttons or API:
```bash
curl -X POST http://localhost:5555/api/export -H "Content-Type: application/json" -d '{"format":"json"}'
```

---

## Auto-Start on Boot

### Windows Startup Folder
1. Press **Win+R** and type: `shell:startup`
2. Copy `autostart.bat` to that folder
3. Done — runs automatically on boot

### Task Scheduler
1. Press **Win+R** → `taskschd.msc` → Enter
2. Create Basic Task → Name: `GuardWatch`
3. Trigger: **At startup**
4. Action: **Start a program**
5. Program: `pythonw.exe`
6. Arguments: `"C:\path\to\main.py"`
7. Check **Run with highest privileges**

---

## Troubleshooting

### Module Not Starting
- Check health status in dashboard
- Review console output for errors
- Verify dependencies installed
- Check config.json module settings

### Database Locked
- Ensure only one GuardWatch instance running
- Check for zombie processes
- Restart GuardWatch cleanly

### Dashboard Not Accessible
- Verify port 5555 not in use
- Check firewall settings
- Review dashboard config in config.json

### Evidence Not Saving
- Check disk space
- Verify write permissions to evidence directory
- Review session manager logs

---

## Privacy & Legal Notes

✓ **This is YOUR PC** — you own it  
✓ **You can monitor it however you want** — it's your device  
✓ **Evidence is admissible** — timestamped, documented, integrity-verified  

**Do not use this on anyone else's computer without their knowledge.** Monitoring someone else's device without consent is illegal in most jurisdictions.

---

## Migration from v3.0

### Breaking Changes
- Entry point changed from `guardwatch.py` to `main.py`
- Configuration moved to `config.json`
- Evidence storage uses SQLite instead of JSON files
- Some command-line options changed

### Data Migration
- v3.0 JSON evidence files remain readable
- New sessions use SQLite
- Old sessions can be viewed with `--report`

---

**GuardWatch v4.0** — Engineering maturity meets comprehensive evidence collection.
