# Run in native Windows PowerShell. Uses the same protocol bytes as WSL.
param(
    [string]$BusId,
    [ValidateRange(45, 300)]
    [int]$Duration = 90,
    [switch]$Diagnose
)

$ErrorActionPreference = 'Stop'
if ($Diagnose -and -not $PSBoundParameters.ContainsKey('Duration')) { $Duration = 180 }
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Run this script in native Windows PowerShell.'
}
$pactoProject = Split-Path -Parent $PSScriptRoot
$pactoBasePython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path -LiteralPath $pactoBasePython)) {
    throw 'Python 3.12 was not found at the inspected Windows installation path.'
}

# Detach only the exact CSR adapter observed in the WSL hardware inventory.
# Never detach every USB device or guess a BUSID.
if ($BusId) {
    if ($BusId -notmatch '^\d+-\d+$') { throw 'Invalid USB BUSID.' }
    $pactoUsbipd = Join-Path $env:ProgramFiles 'usbipd-win\usbipd.exe'
    if (-not (Test-Path -LiteralPath $pactoUsbipd)) { throw 'usbipd-win was not found.' }
    $pactoUsbList = @(& $pactoUsbipd list)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect usbipd devices.' }
    $pactoExpected = '^\s*' + [regex]::Escape($BusId) + '\s+0a12:0001\s'
    $pactoMatch = @($pactoUsbList | Where-Object { $_ -match $pactoExpected })
    if ($pactoMatch.Count -ne 1) {
        throw 'The selected BUSID does not uniquely identify the expected CSR 0a12:0001 adapter.'
    }
    & $pactoUsbipd detach --busid $BusId
    if ($LASTEXITCODE -ne 0) { throw 'Could not release the selected USB adapter from WSL.' }
    Start-Sleep -Seconds 3
}

$pactoStamp = Get-Date -Format 'yyyyMMddTHHmmss'
$pactoSuffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$pactoOutput = Join-Path $pactoProject "captures\windows-$pactoStamp-$pactoSuffix"
New-Item -ItemType Directory -Path $pactoOutput | Out-Null
$pactoDevices = @(Get-PnpDevice -PresentOnly -Class Bluetooth -ErrorAction SilentlyContinue |
    Select-Object FriendlyName, Status)
[ordered]@{
    platform = 'native Windows'
    windows_version = [Environment]::OSVersion.VersionString
    python = $pactoBasePython
    bluetooth_devices = $pactoDevices
    usb_busid_released_from_wsl = $BusId
    protocol_profile = 'pacto-status'
    duration_s = $Duration
    diagnostics = [bool]$Diagnose
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $pactoOutput 'platform.json') -Encoding UTF8
if ($pactoDevices.Count -eq 0) {
    throw "No present Bluetooth devices were found in Windows. Check usbipd and Windows drivers. Diagnostics: $pactoOutput"
}

$pactoVenv = Join-Path $pactoProject '.venv-win'
$pactoPython = Join-Path $pactoVenv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pactoPython)) {
    & $pactoBasePython -m venv $pactoVenv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated Windows Python environment.' }
}
& $pactoPython -m pip install -e $pactoProject
if ($LASTEXITCODE -ne 0) { throw 'Could not install the project into the Windows environment.' }

Push-Location $pactoProject
try {
    Write-Host "Saving native Windows test to: $pactoOutput"
    Write-Host 'Keep phone Bluetooth off. The treadmill can remain stopped.'
    $pactoArguments = @('-m', 'pactobridge', '--log', (Join-Path $pactoOutput 'app.jsonl'),
        'capture', '--decoder', 'pacto', '--polling', 'pacto-status', '--duration', "$Duration",
        '--output', (Join-Path $pactoOutput 'capture.jsonl'))
    if ($Diagnose) { $pactoArguments += '--diagnose' }
    & $pactoPython @pactoArguments
    if ($LASTEXITCODE -ne 0) { throw "Native capture failed. See files in $pactoOutput" }
    Write-Host "Finished. Diagnostic files: $pactoOutput"
} finally {
    Pop-Location
}
