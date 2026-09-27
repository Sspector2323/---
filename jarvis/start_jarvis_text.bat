@echo off
chcp 65001 >nul
cd /d "%~dp0"
title J.A.R.V.I.S. (текст)
call .venv\Scripts\activate.bat
python main.py --text
pause
