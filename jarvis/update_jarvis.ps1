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
# Закрываем работающего Джарвиса (в т.ч. свёрнутого из автозапуска) — иначе останется старая версия
$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($root.ToLower()) -and $_.Name -match "python" }
if ($running) {
    Write-Host "Закрываю запущенного Джарвиса..." -ForegroundColor Yellow
    $running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}
$old = (Select-String -Path (Join-Path $root "core\__init__.py") -Pattern 'VERSION = "(.+?)"' -ErrorAction SilentlyContinue).Matches.Groups[1].Value

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
$new = (Select-String -Path (Join-Path $root "core\__init__.py") -Pattern 'VERSION = "(.+?)"').Matches.Groups[1].Value
Write-Host ""
if ($old -and $old -eq $new) { Write-Host "Версия $new — у вас уже была самая свежая." -ForegroundColor Green }
else { Write-Host "Обновлено: $(if ($old) { $old } else { 'старая версия' }) → $new" -ForegroundColor Green }
Write-Host "Папка Джарвиса: $root"
Write-Host "Готово! Запускайте start_jarvis.bat — в первой строке окна будет версия $new" -ForegroundColor Green
