@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== Обновляю библиотеки Джарвиса =====
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo [!] Ошибка обновления. Сфотографируйте текст выше и пришлите Claude.
) else (
  echo.
  echo ===== Готово! Запускайте start_jarvis.bat =====
)
pause
