param(
    [ValidateSet('log-reader', 'navpoint', 'accountant')]
    [string]$Skill = 'log-reader'
)
$ErrorActionPreference = 'Stop'
& 'C:\Users\larse\AppData\Local\Programs\Python\Python313\python.exe' (Join-Path $PSScriptRoot 'check_contribution.py') (Join-Path $PSScriptRoot "sc-$Skill.allowlist.json")
exit $LASTEXITCODE
