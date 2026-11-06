@echo off
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run setup.cmd in this folder first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0pump_test_app.py"
if errorlevel 1 pause
