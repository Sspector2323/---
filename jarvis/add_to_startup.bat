@echo off
chcp 65001 >nul
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
(
  echo @echo off
  echo chcp 65001 ^>nul
  echo cd /d "%~dp0"
  echo start "J.A.R.V.I.S." /min "%~dp0.venv\Scripts\python.exe" main.py --no-browser
) > "%STARTUP%\Jarvis.bat"
echo Готово: Джарвис будет запускаться вместе с Windows.
echo Чтобы отключить — удалите файл "%STARTUP%\Jarvis.bat"
pause
