@echo off
REM GuardWatch v4.0 — Auto-Start Script
REM This file is in the Windows Startup folder

REM Change directory to where main.py is located
cd /d "c:\Users\AY ADVANCE TECH\Documents\guardwatch"

REM Run GuardWatch silently in background
REM Web dashboard will be available at http://localhost:5555
start "" pythonw main.py

REM Exit without showing a window
exit
