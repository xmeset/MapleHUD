@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  py -m venv .venv || exit /b 1
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" maple_hud.py
