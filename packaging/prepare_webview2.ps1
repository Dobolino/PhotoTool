# Obtain Microsoft's small, signed Evergreen bootstrapper for the installer.
# The full browser runtime is installed only when it is missing on the machine.
param([switch]$InstallRuntime)
$ErrorActionPreference = 'Stop'
$runtimeKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'

function Test-WebView2Runtime {
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
            $root = $null
            $key = $null
            try {
                $root = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
                $key = $root.OpenSubKey($runtimeKey)
                if ($key) {
                    $version = [string]$key.GetValue('pv', '')
                    if ($version -and $version -ne '0.0.0.0') { return $true }
                }
            } finally {
                if ($key) { $key.Dispose() }
                if ($root) { $root.Dispose() }
            }
        }
    }
    return $false
}

$destination = Join-Path (Split-Path $PSScriptRoot -Parent) 'dist\prerequisites'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$bootstrapper = Join-Path $destination 'MicrosoftEdgeWebview2Setup.exe'
Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $bootstrapper
$signature = Get-AuthenticodeSignature -LiteralPath $bootstrapper
if ($signature.Status -ne 'Valid' -or !$signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') {
    Remove-Item -LiteralPath $bootstrapper -Force
    throw 'WebView2 bootstrapper is not validly signed by Microsoft Corporation'
}
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $bootstrapper).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $destination 'webview2-bootstrapper.sha256') -Value $hash -Encoding ascii
Write-Output "Verified Microsoft WebView2 bootstrapper ($hash)"

if ($InstallRuntime -and !(Test-WebView2Runtime)) {
    $process = Start-Process -FilePath $bootstrapper -ArgumentList '/silent', '/install' -PassThru
    if (!$process.WaitForExit(240000)) {
        $process.Kill()
        throw 'Microsoft WebView2 runtime installation timed out'
    }
    if (!(Test-WebView2Runtime)) {
        throw "Microsoft WebView2 runtime is unavailable after setup (exit $($process.ExitCode))"
    }
}
Write-Output "WebView2 runtime present: $(Test-WebView2Runtime)"
