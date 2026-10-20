param([ValidateSet('smoke','test','voice','scene','operator','simulator')][string]$Task = 'smoke', [Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest)
$ErrorActionPreference = 'Stop'
$relayPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $relayPython)) { throw 'Run setup.ps1 first.' }
$relayOldPath = $env:PYTHONPATH
$env:PYTHONPATH = "$PSScriptRoot/voice/src;$PSScriptRoot/voice;$PSScriptRoot/voice/scripts;$PSScriptRoot/scene_robot"
$env:NUMBA_CACHE_DIR = "$PSScriptRoot/cache/numba"
$env:MPLCONFIGDIR = "$PSScriptRoot/cache/matplotlib"
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONUTF8 = '1'
Push-Location $PSScriptRoot
try {
    switch ($Task) {
        'smoke' { & $relayPython scripts/smoke.py @Rest }
        'test' { & $relayPython -m pytest -q @Rest }
        'voice' { Set-Location voice; New-Item -ItemType Directory -Force results | Out-Null; & $relayPython -m relay_voice.app --low-only @Rest }
        'scene' { & $relayPython scripts/prepare_scene.py @Rest }
        'operator' { Set-Location scene_robot; & $relayPython -m p2.ui.operator_ui @Rest }
        'simulator' { Set-Location scene_robot; & $relayPython -m p2.sim.sim_node @Rest }
    }
    if ($LASTEXITCODE) { throw "Task failed with exit code $LASTEXITCODE" }
} finally { Pop-Location; $env:PYTHONPATH = $relayOldPath }
