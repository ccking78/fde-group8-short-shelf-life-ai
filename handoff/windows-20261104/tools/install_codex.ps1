# Uses a reviewed, SHA256-pinned copy of the official installer.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$packageRoot = Split-Path -Parent $PSScriptRoot
$portablePython = Join-Path $packageRoot '.runtime\python\python.exe'
$launcher = Join-Path $PSScriptRoot 'handoff.py'
$existingCli = & $portablePython -X utf8 -B $launcher cli --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host 'An existing native Codex CLI was found. Keeping its installation and configuration.'
    Write-Host $existingCli
    exit 0
}
if ($LASTEXITCODE -ne 3) {
    throw 'CLI discovery failed. Correct the reported path/configuration before installing.'
}
$officialInstaller = Join-Path $PSScriptRoot 'codex-install-official.ps1'
$expectedInstallerHash = 'B3664171771FF083EE95F74030070CF23FD13797472D84E387653C0DF36042C3'
if ((Get-FileHash -LiteralPath $officialInstaller -Algorithm SHA256).Hash -ne $expectedInstallerHash) {
    throw 'Official installer SHA256 mismatch. Re-extract the original handoff package.'
}
Write-Host 'Installing official Codex CLI 0.166.0 for the current Windows user. Network access is required.'
Write-Host 'The official installer writes its runtime and User PATH. It does not log in for you.'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
& $officialInstaller -Release '0.166.0'
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
exit 0
