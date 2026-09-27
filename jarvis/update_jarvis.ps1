# Обновление Джарвиса: скачивает свежую версию с GitHub и заменяет файлы.
# Ваши настройки (.env), дела и память (data), установленные библиотеки (.venv) не трогаются.
$ErrorActionPreference = "Stop"
# папка Джарвиса — текущая (если команду запустили из неё) или та, где лежит этот скрипт
$root = (Get-Location).Path
if (-not (Test-Path (Join-Path $root "main.py")) -and $PSScriptRoot) { $root = $PSScriptRoot }
if (-not (Test-Path (Join-Path $root "main.py"))) {
    Write-Host "Это не папка Джарвиса. Откройте папку jarvis и запустите команду оттуда." -ForegroundColor Red
    return
}
$url = "https://github.com/Sspector2323/---/archive/refs/heads/claude/nice-bell-d8d047.zip"
$tmp = Join-Path $env:TEMP "jarvis_update"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item $tmp -ItemType Directory | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "1/3 Скачиваю свежую версию Джарвиса..." -ForegroundColor Cyan
Invoke-WebRequest $url -OutFile "$tmp\j.zip" -UseBasicParsing
Expand-Archive "$tmp\j.zip" "$tmp\x" -Force
$src = Join-Path (Get-ChildItem "$tmp\x" -Directory | Select-Object -First 1).FullName "jarvis"

Write-Host "2/3 Заменяю файлы (настройки, дела и память сохраняются)..." -ForegroundColor Cyan
robocopy $src $root /E /XD .venv data /XF .env /NFL /NDL /NJH /NJS /NP | Out-Null

Write-Host "3/3 Обновляю библиотеки..." -ForegroundColor Cyan
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Джарвис ещё не установлен — запустите install_windows.bat" -ForegroundColor Yellow
    return
}
& $py -m pip install --upgrade -r (Join-Path $root "requirements.txt")
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Готово! Запускайте start_jarvis.bat" -ForegroundColor Green
