# Вход в Claude Code: находит его (даже если Windows «не видит» команду claude),
# прописывает в PATH и открывает для входа в аккаунт.
$bin = Join-Path $env:USERPROFILE ".local\bin"
$exe = Join-Path $bin "claude.exe"
if (-not (Test-Path $exe)) {
    $found = Get-Command claude -ErrorAction SilentlyContinue
    if ($found) { $exe = $found.Source }
}
if (-not (Test-Path $exe)) {
    Write-Host "Claude Code не найден — устанавливаю..." -ForegroundColor Cyan
    irm https://claude.ai/install.ps1 | iex
}
if (-not (Test-Path $exe)) {
    Write-Host "Не получилось установить Claude Code. Сфотографируйте это окно и пришлите Claude." -ForegroundColor Red
    return
}
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$bin*") {
    [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $bin), "User")
    Write-Host "Прописал Claude Code в PATH — в новых окнах команда claude будет работать." -ForegroundColor Green
}
Write-Host ""
Write-Host "Сейчас откроется Claude Code." -ForegroundColor Cyan
Write-Host "  1. Наберите  /login  и нажмите Enter — откроется браузер, войдите в аккаунт Claude."
Write-Host "  2. Когда вход завершится, наберите  /exit  и закройте окно."
Write-Host ""
& $exe

Write-Host ""
Write-Host "Проверяю, работает ли Claude Code..." -ForegroundColor Cyan
$env:ANTHROPIC_API_KEY = $null
$out = & $exe -p "Ответь одним словом: ок" --output-format json 2>&1 | Out-String
try { $j = ($out.Trim() -split "`n")[-1] | ConvertFrom-Json } catch { $j = $null }
if ($j -and -not $j.is_error) {
    Write-Host "✅ Claude Code работает! Можно запускать Джарвиса." -ForegroundColor Green
} else {
    Write-Host "❌ Claude Code не работает. Вот что он ответил:" -ForegroundColor Red
    Write-Host $out
    $low = $out.ToLower()
    if ($low -match "country|region|not available") {
        Write-Host "→ Anthropic не пускает из вашего региона. Включите VPN в режиме TUN / «для всех приложений» и запустите этот файл снова." -ForegroundColor Yellow
    } elseif ($low -match "403|forbidden") {
        Write-Host "→ Доступ запрещён: либо VPN не охватывает программы (нужен режим TUN), либо на аккаунте нет подписки Pro/Max." -ForegroundColor Yellow
    } elseif ($low -match "401|login|auth") {
        Write-Host "→ Вход не сохранился. Запустите этот файл ещё раз и в окне Claude наберите /login." -ForegroundColor Yellow
    }
    Write-Host "Сфотографируйте это окно и пришлите Claude."
}
