@echo off
cd /d "%~dp0backend"
python -m pytest -q
pause
