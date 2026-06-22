# GuardWatch v3.0 — PC Intruder Evidence Suite + Web Dashboard

**Captures timestamped proof of unauthorized access on YOUR OWN PC.**
**NEW: File Activity Monitoring + Live Web Dashboard**

---

## What It Does

GuardWatch monitors 11 different evidence channels and saves everything to a hidden folder with timestamps. If someone is using your PC without permission while you sleep, GuardWatch will document exactly what they did.

### 11 Evidence Modules

| Module | What It Captures | Why It Matters |
|--------|------------------|---|
| **Idle/Wake Detector** | Exact moment PC wakes from idle | Proves someone started using your PC while you were asleep |
| **Webcam Snapshot** | Photo of whoever sits down on wake event | **STRONGEST PROOF** — identity of the intruder |
| **Steps Recorder** | Annotated screenshot on every mouse click | Visual proof of every action they took |
| **Timed Screenshots** | Desktop every 90–240 seconds | Context of what was on screen |
| **Keystroke Logger** | Everything typed, organized by minute | What they typed (passwords, searches, etc.) |
| **Clipboard Monitor** | Every copy/paste in full | Sensitive data they may have copied |
| **Window Title Tracker** | Which app had focus and when | What programs they opened and used |
| **Browser History Diff** | Before/after snapshots of browsing | Which new URLs they visited |
| **USB Device Detection** | Any drive inserted or removed | Whether they tried to steal files |
| **Failed Login Counter** | Wrong password attempts from Security log | How they bypassed your password |
| **File Activity Monitor (NEW)** | Tracks all file changes in key folders | Detects suspicious file creation/deletion |

### 🆕 Live Web Dashboard

GuardWatch v3.0 now includes a real-time web dashboard accessible at `http://localhost:5555`:
- Live event stream with auto-refresh every 2 seconds
- Evidence statistics (webcam photos, steps, screenshots, file changes)
- High-priority event highlighting
- One-click controls (open evidence folder, stop monitoring)
- Accessible from any device on your network

---

## Installation

### Step 1: Install Python Dependencies

**Double-click `setup.bat`** to install all required packages automatically.

Or manually run:
```cmd
pip install mss Pillow pyperclip pynput opencv-python pywin32 flask watchdog
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

---

## Quick Start

### Option 1: Monitor Now with Web Dashboard (Recommended)
```cmd
python guardwatch.py
```
GuardWatch starts monitoring and launches a live web dashboard at `http://localhost:5555`. Open this URL in your browser to see real-time evidence collection. Press **Ctrl+C** to stop.

### Option 2: Run Silent (No Console)
```cmd
pythonw guardwatch.py
```
Runs completely in background — no visible window. Evidence is still collected. Dashboard still available at `http://localhost:5555`.

### Option 3: View Evidence from Previous Sessions
```cmd
python guardwatch.py --report
```
Prints a text summary of all sessions and what was captured.

### Option 4: Delete All Evidence
```cmd
python guardwatch.py --clear
```
Securely wipes all evidence. (Asks for confirmation first.)

---

## How to Use It

### Scenario: Someone is using your PC while you sleep

1. **Open Command Prompt** (Win+R → `cmd` → Enter)
2. **Navigate to where you saved guardwatch.py:**
   ```cmd
   cd C:\Users\YourName\Desktop
   ```
3. **Start monitoring:**
   ```cmd
   python guardwatch.py
   ```
4. **Open the web dashboard** at `http://localhost:5555` in your browser to see live evidence collection.
5. **Leave it running.** It will monitor all 11 channels silently.
6. **The next morning, check the evidence:**
   ```cmd
   python guardwatch.py --report
   ```

---

## Auto-Start on Boot (So You Never Forget)

You can set GuardWatch to run automatically every time Windows starts, even before you log in.

### Option A: Windows Startup Folder (Easiest)

1. Press **Win+R** and type: `shell:startup`
2. Create a text file called `guardwatch.bat` with this content:
   ```batch
   @echo off
   pythonw "C:\full\path\to\guardwatch.py"
   ```
   (Replace `C:\full\path\to\guardwatch.py` with the actual path where you saved guardwatch.py)
3. Save and close. Done — it will run automatically on next boot.

### Option B: Task Scheduler (More Reliable)

1. Press **Win+R** → `taskschd.msc` → Enter
2. **Create Basic Task...**
   - Name: `GuardWatch`
   - Trigger: **At startup**
   - Action: **Start a program**
   - Program: `pythonw.exe`
   - Arguments: `"C:\full\path\to\guardwatch.py"`
3. Check the box **Run with highest privileges**
4. Click **Finish**

Now GuardWatch will run silently every time Windows boots.

---

## Understanding the Evidence

### Where It's Saved
```
C:\Users\YourName\AppData\Roaming\Microsoft\CLR\gw_evidence\
    └── 20260622_011500/           ← Session ID (date + time started)
        ├── webcam/                ← Webcam photos (WHO sat at the PC)
        ├── steps/                 ← Annotated click screenshots
        ├── screenshots/           ← Timed desktop captures
        ├── file_activity/         ← File change logs (NEW in v3.0)
        ├── keystrokes.txt         ← Everything typed
        ├── clipboard.txt          ← Every copy/paste
        ├── window_titles.txt      ← Apps in focus
        ├── file_activity.json     ← File monitoring events (NEW)
        ├── browser_history_before.json
        ├── browser_history_after.json
        ├── events.json            ← Full event log with timestamps
        └── evidence_report.html   ← Open in browser for full report
```

### Reading the Evidence Report

**Open `evidence_report.html` in any web browser.** It's formatted like Windows Steps Recorder — each step shows:
- 📷 Webcam photo of the intruder
- 🖱️ Every click with visual crosshair marking where they clicked
- ⏰ Exact timestamp
- All embedded in one portable file (no external links)

You can print it or send it to prove unauthorized access.

### Key File: events.json

This JSON file lists every logged event in order with timestamps:

```json
[
  {"time": "2026-06-22T01:15:00", "priority": "HIGH", "event": "WAKE_FROM_IDLE", "detail": "PC active after 47 min idle — POSSIBLE INTRUDER"},
  {"time": "2026-06-22T01:15:02", "priority": "HIGH", "event": "WEBCAM_PHOTO", "detail": "Saved → cam_intruder_011502_1.jpg"},
  {"time": "2026-06-22T01:15:08", "priority": "INFO", "event": "WINDOW_FOCUS", "detail": "Firefox - Google Search"},
  ...
]
```

**HIGH priority events are the smoking gun — highlighted with ⚠️ in reports.**

---

## What If They Bypass Your Password?

GuardWatch logs failed login attempts from Windows Security logs. If someone tried 10+ times before getting in, the `--report` output will show:

```
⚠️  FAILED_LOGINS: 8 failed login attempt(s) found — someone was trying passwords!
```

This is strong evidence they didn't have your password and had to brute-force it.

---

## Troubleshooting

### "No camera found"
- GuardWatch skips webcam if no camera is detected. Other modules still work.
- Verify your camera works in Camera app first.

### "wevtutil access denied"
- Failed login counter needs **Admin** privileges to read Security logs.
- Run Command Prompt as Administrator before starting GuardWatch.

### "Missing dependencies"
- Run `setup.bat` again or manually install:
  ```cmd
  pip install mss Pillow pyperclip pynput opencv-python pywin32 flask watchdog
  ```

### "Evidence folder not found"
- Check: `C:\Users\YourName\AppData\Roaming\Microsoft\CLR\gw_evidence\`
- Make sure the path exists (run `mkdir` if needed)

### No evidence after stopping
- Press **Ctrl+C** cleanly to let GuardWatch save files
- Don't force-kill the process (Task Manager kill = data loss)
- Wait 2–3 seconds after pressing Ctrl+C for HTML report to generate

---

## Privacy & Legal Notes

✓ **This is YOUR PC** — you own it  
✓ **You can monitor it however you want** — it's your device  
✓ **Evidence is admissible** — timestamped, documented, self-contained  

**Do not use this on anyone else's computer without their knowledge.** Monitoring someone else's device without consent is illegal in most jurisdictions.

---

## Sample Output

When you run `python guardwatch.py`:

```
╔═══════════════════════════════════════════════════════════╗
║          GUARDWATCH v3.0 — ACTIVE + WEB DASHBOARD         ║
║                                                           ║
║  Session : 20260622_011500                                ║
║  Dashboard: http://localhost:5555                          ║
║                                                           ║
║  Modules:                                                 ║
║  ✓ Idle/wake       ✓ Webcam          ✓ File Monitor       ║
║  ✓ Screenshots     ✓ Window titles   ✓ USB detector       ║
║  ✓ Click recorder  ✓ Clipboard       ✓ Failed logins      ║
║  ✓ Keystrokes      ✓ Browser hist.                        ║
║                                                           ║
║  Press Ctrl+C to stop and save evidence                  ║
╚═══════════════════════════════════════════════════════════╝

✓ Dashboard live at: http://localhost:5555
  Open in your browser (or any device on your network)

[01:15:02] SESSION_START: GuardWatch v3.0 monitoring started
[01:15:12] PC_IDLE: No activity for 300s — standby
[01:16:47] WAKE_FROM_IDLE: PC active after 2 min idle — POSSIBLE INTRUDER
⚠️  [01:16:49] WEBCAM_PHOTO: Saved → cam_intruder_011649_1.jpg
[01:16:51] WINDOW_FOCUS: Firefox - Google Search
    [01:16:58] STEP: Step 1 — Left-click at (872, 445)
    [01:17:03] STEP: Step 2 — Left-click at (556, 120)
    [01:17:09] KEYSTROKES: [ Typed search query ]
    [01:17:15] FILE_MONITOR_START: Monitoring 5 folders
    [01:17:20] FILE_CREATED: Created → suspicious.exe (45212 bytes)
```

---

## Need Help?

**Questions about using GuardWatch?**
- Check the text summary: `python guardwatch.py --report`
- Open the HTML report in your browser: `evidence_report.html`
- All files are timestamped and self-documenting

---

**GuardWatch v3.0** — Catch intruders with proof + live web dashboard.
"# GAURDWATCH" 
