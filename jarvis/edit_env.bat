@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
start "" notepad "%~dp0.env"
