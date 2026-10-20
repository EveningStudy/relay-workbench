param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -c "import sys; assert sys.version_info[:2] == (3,11), 'Python 3.11 is required'"
    if ($LASTEXITCODE) { throw 'Select Python 3.11 with -Python <path-to-python.exe>' }
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE) { throw 'Could not create environment' }
    }
    & ./.venv/Scripts/python.exe -m pip install --require-hashes -r requirements.lock
    if ($LASTEXITCODE) { throw 'Dependency installation failed' }
    Write-Host 'Ready. Run .\run.ps1 smoke or .\run.ps1 test.'
} finally { Pop-Location }
