@echo off
setlocal
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.10 or newer from python.org with Tcl/Tk and Add Python to PATH.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist ".env" copy /y ".env.example" ".env" >nul
echo Ready. Edit .env locally to add your ElevenLabs key, then double-click run.cmd.
pause
exit /b 0
:fail
echo Setup failed. Read the error above, check your internet, and try again.
pause
exit /b 1

