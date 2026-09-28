@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pip install -q "telethon>=1.36"
python -m core.tg_reader login
pause
