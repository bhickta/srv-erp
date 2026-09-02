$ErrorActionPreference = "Stop"

$PluginDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $PluginDir "..")).Path
$BuildRoot = Join-Path $RepoRoot "build\tally-bridge-windows"
$ExeDir = Join-Path $BuildRoot "exe"
$WorkDir = Join-Path $BuildRoot "work"
$SpecDir = Join-Path $BuildRoot "spec"
$OutputZip = Join-Path $RepoRoot "dist\SRV-Tally-Bridge-Windows-x64.zip"

python -m pip install --disable-pip-version-check --requirement (Join-Path $PluginDir "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name SRVTallyBridge `
    --paths $RepoRoot `
    --distpath $ExeDir `
    --workpath $WorkDir `
    --specpath $SpecDir `
    (Join-Path $PluginDir "windows_entry.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Executable = Join-Path $ExeDir "SRVTallyBridge.exe"
& $Executable --help
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python (Join-Path $PluginDir "build_package.py") --output $OutputZip --executable $Executable
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ChecksumFile = "$OutputZip.sha256"
$Hash = (Get-FileHash -Algorithm SHA256 $OutputZip).Hash.ToLowerInvariant()
Set-Content -Path $ChecksumFile -Value "$Hash  SRV-Tally-Bridge-Windows-x64.zip" -Encoding ascii

Write-Host "Built $OutputZip"
Write-Host "SHA256 $Hash"
