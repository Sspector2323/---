@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== Установка J.A.R.V.I.S. =====
rem Предпочитаем Python 3.12 (под него точно есть все библиотеки, включая микрофон)
set "PY=python"
py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if "%PY%"=="python" py -3.11 --version >nul 2>nul && set "PY=py -3.11"
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] Python не найден. Скачайте Python 3.12 с https://www.python.org/downloads/
  echo     При установке ОБЯЗАТЕЛЬНО отметьте галочку "Add python.exe to PATH".
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% --version
%PY% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo [!] Ошибка установки библиотек. Сфотографируйте текст выше и пришлите Claude.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env >nul
echo.
echo ===== Готово! =====
echo Сейчас откроется файл настроек .env — вставьте ANTHROPIC_API_KEY и сохраните (Ctrl+S).
echo Потом запускайте Джарвиса файлом start_jarvis.bat
notepad .env
pause
