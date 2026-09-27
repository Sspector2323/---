@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== Подключаю Джарвиса к Cursor и Codex =====
call .venv\Scripts\activate.bat
python -m core.integrations
pause
