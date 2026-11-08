# Native Windows validation of a fresh installation and in-place update/restart.
param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
$installer = (Resolve-Path "dist/PhotoTool-Setup-$Version.exe").Path
$installDir = Join-Path $env:RUNNER_TEMP 'PhotoTool installer smoke'
$installedExe = Join-Path $installDir 'Fotobuch.exe'

function Get-InstalledProcesses {
    Get-Process -Name Fotobuch -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $installedExe }
}

function Invoke-Installer([string]$Stage) {
    $log = Join-Path $env:RUNNER_TEMP "PhotoTool-install-$Stage.log"
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/CLOSEAPPLICATIONS', '/NORESTART',
                   "/DIR=`"$installDir`"", "/LOG=`"$log`"")
    $setup = Start-Process -FilePath $installer -ArgumentList $arguments -PassThru
    if (!$setup.WaitForExit(120000)) { $setup.Kill(); throw "Installer $Stage timed out" }
    if ($setup.ExitCode -ne 0) { throw "Installer $Stage failed ($($setup.ExitCode)); see $log" }
    if (!(Test-Path $installedExe)) { throw 'Installed executable missing' }

    # [Run] must relaunch the installed application after silent in-app updates.
    $deadline = (Get-Date).AddSeconds(30)
    do {
        $launched = @(Get-InstalledProcesses)
        if ($launched.Count -gt 0) { break }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $deadline)
    if ($launched.Count -eq 0) { throw "Application did not restart after $Stage" }
    foreach ($application in $launched) {
        if (!$application.WaitForInputIdle(30000)) { throw 'Installed GUI did not become ready' }
    }
    Get-InstalledProcesses | Stop-Process -Force
    $smoke = Start-Process -FilePath $installedExe -ArgumentList '--smoke-test' -PassThru
    if (!$smoke.WaitForExit(60000)) { $smoke.Kill(); throw 'Installed executable smoke test timed out' }
    if ($smoke.ExitCode -ne 0) { throw 'Installed executable smoke test failed' }
    $reviewResult = Join-Path $env:RUNNER_TEMP "PhotoTool-native-$Stage.json"
    Remove-Item -LiteralPath $reviewResult -ErrorAction SilentlyContinue
    $reviewArgs = @('--review-smoke', "`"$reviewResult`"")
    $review = Start-Process -FilePath $installedExe -ArgumentList $reviewArgs -PassThru
    if (!$review.WaitForExit(90000)) { $review.Kill(); throw "Installed native review $Stage timed out" }
    if ($review.ExitCode -ne 0 -or !(Test-Path $reviewResult)) { throw "Installed native review $Stage failed" }
    $native = Get-Content $reviewResult -Raw | ConvertFrom-Json
    if (!$native.success) { throw "Installed native review $Stage did not render" }
}

try {
    Invoke-Installer 'fresh'
    $sentinel = Join-Path $installDir 'preserved-user-file.txt'
    Set-Content -LiteralPath $sentinel -Value 'preserve across in-place update'
    Invoke-Installer 'update'
    if ((Get-Content -LiteralPath $sentinel) -ne 'preserve across in-place update') {
        throw 'In-place update did not preserve unrelated files'
    }
} finally {
    Get-InstalledProcesses | Stop-Process -Force
}
