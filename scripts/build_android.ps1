param([string]$JavaHome)
$ErrorActionPreference = 'Stop'
$pactoMobile = Join-Path (Split-Path -Parent $PSScriptRoot) 'mobile'
if ($JavaHome) { $env:JAVA_HOME = $JavaHome }
if (-not $env:JAVA_HOME -and (Test-Path -LiteralPath 'C:\Program Files\Java\jdk-17.0.4')) {
    $env:JAVA_HOME = 'C:\Program Files\Java\jdk-17.0.4'
}
Push-Location $pactoMobile
try {
    & flutter --no-version-check analyze
    if ($LASTEXITCODE -ne 0) { throw 'Flutter analysis failed.' }
    & flutter --no-version-check test
    if ($LASTEXITCODE -ne 0) { throw 'Flutter tests failed.' }
    Push-Location (Join-Path $pactoMobile 'android')
    try {
        & .\gradlew.bat :app:testDebugUnitTest --console=plain
        if ($LASTEXITCODE -ne 0) { throw 'Native tests failed.' }
    } finally { Pop-Location }
    & flutter --no-version-check build apk --release --target-platform android-arm64 --split-per-abi
    if ($LASTEXITCODE -ne 0) { throw 'Android build failed.' }
    $pactoDistribution = Join-Path $pactoMobile 'dist'
    New-Item -ItemType Directory -Force -Path $pactoDistribution | Out-Null
    Copy-Item -LiteralPath (Join-Path $pactoMobile 'build\app\outputs\flutter-apk\app-arm64-v8a-release.apk') `
        -Destination (Join-Path $pactoDistribution 'PactoBridge-S22Plus-validation.apk')
    Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $pactoDistribution 'PactoBridge-S22Plus-validation.apk')
} finally { Pop-Location }
