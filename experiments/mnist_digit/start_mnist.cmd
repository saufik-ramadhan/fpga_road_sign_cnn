@echo off
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
  echo Follow setup in experiments\README.md first.
  pause
  exit /b 1
)
echo MNIST Visual Lab: http://127.0.0.1:8766
echo Keep this window open. Ctrl+C stops the server.
".venv\Scripts\python.exe" "experiments\mnist_digit\visualizer.py" %*
if errorlevel 1 pause
