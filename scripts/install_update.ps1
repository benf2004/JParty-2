param([int]$AppPid, [string]$Target, [string]$Staged, [string]$Backup, [string]$Platform)
$ErrorActionPreference = 'Stop'
$process = Get-Process -Id $AppPid -ErrorAction SilentlyContinue
if ($process) { $process | Wait-Process -Timeout 120 }
if (!(Test-Path -LiteralPath $Target -PathType Container) -or !(Test-Path -LiteralPath $Staged -PathType Container) -or (Test-Path -LiteralPath $Backup)) {
    throw 'The installation folders changed; keeping the existing installation.'
}
# Antivirus and the physical buzzer process may briefly retain file handles.
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try { [IO.Directory]::Move($Target, $Backup); break }
    catch { if ($attempt -eq 29) { throw }; Start-Sleep -Seconds 1 }
}
try {
    [IO.Directory]::Move($Staged, $Target)
    Start-Process -FilePath (Join-Path $Target 'JParty.exe') -WorkingDirectory $Target
} catch {
    if (Test-Path -LiteralPath $Target) { [IO.Directory]::Move($Target, $Staged) }
    [IO.Directory]::Move($Backup, $Target)
    Start-Process -FilePath (Join-Path $Target 'JParty.exe') -WorkingDirectory $Target
    throw
}
