@echo off
REM VIPER demonstrator - starts backend + UI on http://127.0.0.1:8000
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
start "" http://127.0.0.1:8000
python backend\main.py
pause
