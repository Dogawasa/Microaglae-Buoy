@echo off
cd /d "%~dp0"

echo Starting Modular Algae Buoy AI Server...
echo.

python -c "import flask, flask_cors" >nul 2>nul
if errorlevel 1 (
  echo Installing Flask requirements...
  python -m pip install flask flask-cors
)

echo.
echo Dashboard will open at:
echo http://localhost:5000
echo.

python modular_ai_server.py
pause
