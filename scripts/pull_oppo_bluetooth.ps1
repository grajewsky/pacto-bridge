# Collect only Bluetooth packet captures from the newest OPPO LogKit session.
param([string]$Serial)
$ErrorActionPreference = 'Stop'
$pactoProject = Split-Path -Parent $PSScriptRoot
$pactoAdb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
if (-not (Test-Path -LiteralPath $pactoAdb)) { throw 'ADB was not found at the inspected installation path.' }
$pactoSelector = @()
if ($Serial) { $pactoSelector = @('-s', $Serial) }
$pactoState = @(& $pactoAdb @pactoSelector get-state)
if ($LASTEXITCODE -ne 0 -or (($pactoState -join '').Trim() -ne 'device')) {
    throw 'Connect and unlock the phone, accept USB debugging, and use -Serial if multiple devices are present.'
}

$pactoRoot = '/sdcard/Android/data/com.oplus.logkit/files/Log'
$pactoDirectories = @(& $pactoAdb @pactoSelector shell ls -1 $pactoRoot)
if ($LASTEXITCODE -ne 0) { throw 'LogKit export directory is not readable. Finish logging and select local/USB export first.' }
$pactoSession = @($pactoDirectories | ForEach-Object { $_.Trim() } |
    Where-Object { $_ -match '^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}@bluetooth$' } |
    Sort-Object -Descending | Select-Object -First 1)
if ($pactoSession.Count -ne 1) { throw 'No finished Bluetooth LogKit session was found.' }
$pactoRemote = "$pactoRoot/$($pactoSession[0])/bluetooth/btsnoop_hci"
$pactoPaths = @(& $pactoAdb @pactoSelector shell find $pactoRemote -type f)
if ($LASTEXITCODE -ne 0) { throw 'Bluetooth packet files are not available in this LogKit session.' }
$pactoPrefix = [regex]::Escape($pactoRemote)
$pactoFiles = @($pactoPaths | ForEach-Object { $_.Trim() } | Where-Object {
    $_ -match ('^' + $pactoPrefix + '/(?:bthci|cached_hci)/[A-Za-z0-9_./-]+\.cfa(?:\.curf)?$') -and
    $_ -notmatch '(?:^|/)\.\.(?:/|$)'
})
if ($pactoFiles.Count -eq 0) { throw 'No Bluetooth packet captures were found. Stop and save the LogKit recording.' }

$pactoSuffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$pactoOutput = Join-Path $pactoProject "captures\android\controls-$($pactoSession[0])-$pactoSuffix"
New-Item -ItemType Directory -Path $pactoOutput | Out-Null
$pactoManifest = @()
foreach ($pactoFile in $pactoFiles) {
    $pactoRelative = $pactoFile.Substring($pactoRemote.Length + 1)
    $pactoDestination = Join-Path $pactoOutput $pactoRelative.Replace('/', '\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pactoDestination) | Out-Null
    & $pactoAdb @pactoSelector pull $pactoFile $pactoDestination
    if ($LASTEXITCODE -ne 0) { throw "Copy failed for $pactoFile; existing local captures were preserved." }
    $pactoManifest += [ordered]@{
        remote = $pactoFile
        local = $pactoRelative
        bytes = (Get-Item -LiteralPath $pactoDestination).Length
    }
}
[ordered]@{
    session = $pactoSession[0]
    collected_at = (Get-Date).ToUniversalTime().ToString('o')
    files = $pactoManifest
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $pactoOutput 'manifest.json') -Encoding UTF8
Write-Host "Bluetooth captures copied to: $pactoOutput"
Write-Host "LogKit session: $($pactoSession[0]) -- check that this is the recording you just made."
