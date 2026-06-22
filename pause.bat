@echo off
REM GuardWatch v4.0 — Start in Paused Mode
REM Saves CPU/battery by not starting monitoring modules
REM Use dashboard to resume when needed

cd /d "c:\Users\AY ADVANCE TECH\Documents\guardwatch"
"C:\Users\AY ADVANCE TECH\AppData\Local\Python\pythoncore-3.14-64\python.exe" main.py --pause
pause
