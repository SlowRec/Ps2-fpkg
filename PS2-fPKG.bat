@echo off
cd /d "%~dp0"
python -m ps2fpkg %*
if errorlevel 1 pause
