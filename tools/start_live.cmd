@echo off
rem Real drone: starts the backend and the MAVLink bridge, in two windows.
rem Mission Planner must forward a copy of MAVLink to UDP 127.0.0.1:14551 (README section 5).
cd /d "%~dp0.."
start "Delivery backend (FastAPI)" cmd /k .venv\Scripts\python.exe backend\app.py
timeout /t 3 /nobreak >nul
start "PC bridge - LIVE MAVLink" cmd /k .venv\Scripts\python.exe pc_bridge\main.py
