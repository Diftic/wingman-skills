# Rebuilds ..\data\<system>.json (one file per system) and ..\data\index.json from the installed game
# (run after a patch). Push data\ to GitHub afterwards so installed skills pick it up.
# Extracts what it needs from Data.p4k into a temporary folder, runs walk.py and build.py,
# checks Stanton against the Aaron Halo route lengths, then deletes the temporary folder.
#
#   & .\sc_distances\tools\rebuild.ps1      (from the wingman-skills repo root)
param(
    [string]$GameDir = 'D:\Roberts Space Industries\StarCitizen\LIVE',
    [string]$StarBreaker = 'D:\PycharmProjects\sc-bridge\StarBreaker\src\StarBreaker.Cli\bin\Release\net10.0\StarBreaker.Cli.exe'
)
$ErrorActionPreference = 'Stop'
$tools = $PSScriptRoot
$target = Join-Path (Split-Path $tools) 'data'
$p4k = Join-Path $GameDir 'Data.p4k'
$work = Join-Path ([IO.Path]::GetTempPath()) ("sc-distances-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $work | Out-Null
$env:SC_DIST_WORK = $work

function Invoke-Step([string]$label, [scriptblock]$step) {
    Write-Host "== $label"
    & $step
    if ($LASTEXITCODE -ne 0) { throw "$label failed (exit $LASTEXITCODE)" }
}

try {
    # StarBreaker's -f filter treats '\' as an escape character, so '?' stands in for the path separator.
    Invoke-Step 'Extract object containers' { & $StarBreaker p4k-extract -p $p4k -o "$work\p4k_all" -f '*ObjectContainers?PU?*.socpak' | Select-Object -Last 1 }
    Invoke-Step 'Extract English localization' { & $StarBreaker p4k-extract -p $p4k -o "$work\p4k_loc" -f '*english?global.ini' | Select-Object -Last 1 }
    Invoke-Step 'Extract starmap records' { & $StarBreaker dcb-extract -p $p4k -o "$work\dcb" -f '*starmap*' | Select-Object -Last 1 }
    Invoke-Step 'Walk container trees' { python -I "$tools\walk.py" stanton pyro nyx }
    Invoke-Step 'Build system files' { python -I "$tools\build.py" "$work\systems" }
    # Mirror the fresh build: replace every system file, drop ones no longer produced.
    New-Item -ItemType Directory -Force $target | Out-Null
    $fresh = Get-ChildItem "$work\systems" -Filter *.json
    Copy-Item $fresh.FullName $target -Force
    Get-ChildItem $target -Filter *.json | Where-Object { $fresh.Name -notcontains $_.Name } | Remove-Item -Force
    Invoke-Step 'Check against Aaron Halo routes' { python -I "$tools\verify_halo.py" | Select-Object -Last 2 }
    Write-Host "Done: $target"
}
finally {
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\SC_DIST_WORK -ErrorAction SilentlyContinue
}
