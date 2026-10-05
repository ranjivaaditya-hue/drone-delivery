@echo off
rem Demo without a drone: starts the backend and the bridge in demo mode, in two windows.
cd /d "%~dp0.."
start "Delivery backend (FastAPI)" cmd /k .venv\Scripts\python.exe backend\app.py
timeout /t 3 /nobreak >nul
start "PC bridge - DEMO" cmd /k .venv\Scripts\python.exe pc_bridge\main.py --demo
