param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$InnoCompiler = "iscc.exe",
    [string]$CertificateThumbprint = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$localInno = Join-Path $projectRoot ".tools\InnoSetup6\ISCC.exe"
if ($InnoCompiler -eq "iscc.exe" -and (Test-Path -LiteralPath $localInno)) {
    $InnoCompiler = $localInno
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found: $Python"
}

& $Python -m unittest discover -s tests -v
& $Python -m PyInstaller --noconfirm --clean packaging\Yapper.spec

$appExe = Join-Path $projectRoot "dist\Yapper\Yapper.exe"
if (-not (Test-Path -LiteralPath $appExe)) {
    throw "PyInstaller did not produce $appExe"
}

if ($CertificateThumbprint) {
    $signTool = Get-Command signtool.exe -ErrorAction Stop
    & $signTool.Source sign /sha1 $CertificateThumbprint /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 $appExe
}

$compiler = Get-Command $InnoCompiler -ErrorAction Stop
& $compiler.Source "packaging\installer.iss"

$installer = Join-Path $projectRoot "release\Yapper-4.0.0-Setup.exe"
if ($CertificateThumbprint -and (Test-Path -LiteralPath $installer)) {
    $signTool = Get-Command signtool.exe -ErrorAction Stop
    & $signTool.Source sign /sha1 $CertificateThumbprint /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 $installer
}

if (Test-Path -LiteralPath $installer) {
    $hash = Get-FileHash -LiteralPath $installer -Algorithm SHA256
    $checksumPath = "$installer.sha256"
    "$($hash.Hash)  $([System.IO.Path]::GetFileName($installer))" |
        Set-Content -LiteralPath $checksumPath -Encoding ascii
}

Write-Output "Release artifacts are in $projectRoot\release"
