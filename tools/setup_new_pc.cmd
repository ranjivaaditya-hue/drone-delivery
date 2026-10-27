@echo off
rem One-time setup on a new Windows PC: Python virtual environment, packages, .env, self-test.
rem Run it from anywhere:  tools\setup_new_pc.cmd
setlocal
cd /d "%~dp0.."

set PY=
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python is not installed. Install Python 3.11+ from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer, then run this again.
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo [1/4] Creating the Python virtual environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Could not create .venv. Install Python 3.11+ from python.org, not the Microsoft Store stub.
    exit /b 1
  )
) else (
  echo [1/4] .venv already exists
)

echo [2/4] Installing packages (fastapi, uvicorn, pymavlink, requests, twilio, pytest) ...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements-dev.txt
if errorlevel 1 exit /b 1

if not exist .env (
  copy .env.example .env >nul
  echo [3/4] Created .env from .env.example ^(same settings as the original PC^)
) else (
  echo [3/4] .env already exists - left unchanged
)

echo [4/4] Running the self-test ...
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -p no:warnings pc_bridge\tests backend\tests
if errorlevel 1 (
  echo Self-test FAILED - see the output above.
  exit /b 1
)
echo.
echo Setup complete. Next: tools\start_demo.cmd   (see MOVING_TO_A_NEW_LAPTOP.md)
