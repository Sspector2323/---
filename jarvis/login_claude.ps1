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
