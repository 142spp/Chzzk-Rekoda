@echo off
setlocal

REM Set the environment variable to force UTF-8 encoding
set PYTHONUTF8=1

echo Starting recorder...
start "Chzzk Recorder" cmd /c "uv run chzzk_record.py & pause"

echo Starting GUI...
start /B .venv\Scripts\pythonw.exe gui.py

endlocal
exit /b 0