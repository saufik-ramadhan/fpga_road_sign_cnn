@echo off
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
  echo Create the environment using the instructions in apps\README.md
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8765 in your browser.
echo Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" "apps\traffic_sign_visualizer\visualizer.py" %*
if errorlevel 1 pause
