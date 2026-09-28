# Вход в Claude Code — по официальной инструкции Anthropic («Reset your login»), с проверками.
$ErrorActionPreference = "Continue"
function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }

# 0. Найти Claude Code (или установить)
$bin = Join-Path $env:USERPROFILE ".local\bin"
$exe = Join-Path $bin "claude.exe"
if (-not (Test-Path $exe)) { $found = Get-Command claude -ErrorAction SilentlyContinue; if ($found) { $exe = $found.Source } }
if (-not (Test-Path $exe)) { Say "Claude Code не найден — устанавливаю..." Cyan; irm https://claude.ai/install.ps1 | iex }
if (-not (Test-Path $exe)) { Say "Не получилось установить Claude Code. Сфотографируйте окно и пришлите Claude." Red; return }
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$bin*") { [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $bin), "User") }

# 1. Джарвис не должен работать во время входа: он запускает Claude Code в фоне, и два процесса
#    одновременно «портят» свежий вход друг другу
for ($i = 0; $i -lt 30; $i++) {
    try { Invoke-WebRequest "http://localhost:5050" -UseBasicParsing -TimeoutSec 2 | Out-Null; $running = $true } catch { $running = $false }
    if (-not $running) { break }
    Say "Джарвис сейчас запущен. Закройте его чёрное окно (и окна дашборда), потом нажмите Enter." Yellow
    Read-Host | Out-Null
}
Get-Process claude -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 2. Мешающие переменные Windows
foreach ($name in "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY") {
    foreach ($scope in "User", "Machine") {
        if ([Environment]::GetEnvironmentVariable($name, $scope)) {
            Say "Удаляю переменную Windows $name ($scope) — она перебивает вход по подписке." Yellow
            try { [Environment]::SetEnvironmentVariable($name, $null, $scope) } catch { Say "  Нужны права администратора: запустите этот файл правой кнопкой → «Запуск от имени администратора»." Yellow }
        }
    }
    Set-Item -Path "Env:$name" -Value $null -ErrorAction SilentlyContinue
}

# 3. Часы: токен входа проверяется по времени — если часы сбиты, вход не работает
try {
    $net = [DateTime]::Parse((Invoke-WebRequest "https://www.google.com" -Method Head -UseBasicParsing -TimeoutSec 8).Headers.Date).ToUniversalTime()
    $diff = [Math]::Abs(([DateTime]::UtcNow - $net).TotalMinutes)
    if ($diff -gt 3) {
        Say ("Часы компьютера сбиты на {0:N0} мин — из-за этого вход не работает. Синхронизирую..." -f $diff) Yellow
        Start-Process w32tm -ArgumentList "/resync" -Verb RunAs -Wait -ErrorAction SilentlyContinue
        Say "Если не помогло: Параметры → Время и язык → Дата и время → «Синхронизировать сейчас»." Yellow
    } else { Say "Часы в порядке." Green }
} catch { }

# 4. Свежая версия Claude Code (в старых версиях вход «слетал» при нескольких процессах)
Say "Обновляю Claude Code..." Cyan
& $exe update 2>&1 | Out-Host

# 5. Чистый вход
Say "Выхожу из старого входа..." Cyan
& $exe auth logout 2>&1 | Out-Null
Say ""
Say "Сейчас откроется браузер для входа в аккаунт Claude (с подпиской Pro/Max)." Cyan
Say "Если браузер покажет код — скопируйте его, вставьте сюда (правый клик) и нажмите Enter." Cyan
Say ""
& $exe auth login
if ($LASTEXITCODE -ne 0) {
    Say "Команда auth login не сработала — открываю Claude Code. Наберите /login, войдите, затем /exit." Yellow
    & $exe
}

# 6. Проверка
Say ""
Say "Проверяю, работает ли Claude Code..." Cyan
$out = & $exe -p "Ответь одним словом: ок" --output-format json 2>&1 | Out-String
try { $j = ($out.Trim() -split "`n")[-1] | ConvertFrom-Json } catch { $j = $null }
if ($j -and -not $j.is_error) {
    Say "✅ Claude Code работает! Можно запускать Джарвиса." Green
} else {
    $msg = if ($j -and $j.result) { $j.result } else { $out }
    Say "❌ Claude Code не работает: $msg" Red
    $low = "$msg".ToLower()
    if ($low -match "country|region|not available") { Say "→ Anthropic не пускает из вашего региона: VPN должен работать для всех программ (режим TUN)." Yellow }
    elseif ($low -match "403|forbidden") { Say "→ Доступ запрещён: проверьте подписку на claude.ai/settings и что VPN охватывает все программы (TUN)." Yellow }
    elseif ($low -match "401|oauth|auth") {
        Say "→ Вход не принят. Проверьте, что VPN включён в режиме TUN ДО входа, и запустите этот файл ещё раз." Yellow
        Say "  Если снова 401 — в окне Claude наберите /status и пришлите скриншот." Yellow
    }
    Say "Сфотографируйте это окно и пришлите Claude."
}
