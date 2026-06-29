@echo off
REM Launch Combat Robot Stress-Test Gauntlet from source (no compile needed).
REM Double-click this file, or run it from a terminal.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m gauntlet
