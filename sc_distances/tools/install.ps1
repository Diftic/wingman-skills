# Installs the skill's runtime files into Wingman AI's custom skills folder (no tools, tests or docs).
# Restart Wingman AI afterwards.
#
#   & .\sc_distances\tools\install.ps1      (from the wingman-skills repo root)
param(
    [string]$Target = (Join-Path $env:APPDATA 'ShipBit\WingmanAI\custom_skills\sc_distances')
)
$ErrorActionPreference = 'Stop'
$skill = Split-Path $PSScriptRoot
$runtime = @('__init__.py', 'main.py', 'default_config.yaml', 'dependencies', 'data')

if ((Split-Path $Target -Leaf) -ne 'sc_distances') { throw "Target must be a folder named sc_distances: $Target" }
if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }   # replace the old install completely
New-Item -ItemType Directory $Target | Out-Null
foreach ($item in $runtime) { Copy-Item (Join-Path $skill $item) $Target -Recurse -Force }
Get-ChildItem $Target -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Write-Host "Installed to $Target"
Get-ChildItem $Target -Recurse -File | ForEach-Object { '  ' + $_.FullName.Substring($Target.Length + 1) }
