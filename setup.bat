@echo off
REM GuardWatch v4.0 — Setup Script
REM Installs all required Python dependencies

echo.
echo ╔═══════════════════════════════════════════════╗
echo ║  GuardWatch v4.0 — Dependency Installer       ║
echo ╚═══════════════════════════════════════════════╝
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH
    echo Please install Python 3.9+ and try again
    pause
    exit /b 1
)

echo Installing required packages...
echo.

pip install -q mss Pillow pyperclip pynput opencv-python pywin32 flask watchdog cryptography flask-socketio

if errorlevel 1 (
    echo.
    echo [ERROR] Installation failed. Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo ✓ All dependencies installed successfully
echo.
echo Next steps:
echo   1. Run GuardWatch:        python main.py
echo   2. Web Dashboard:        http://localhost:5555 (auto-opens)
echo   3. View evidence:         python main.py --report
echo   4. Clear evidence:        python main.py --clear
echo   5. Configure:            Edit config.json
echo.
echo Press any key to exit...
pause >nul
