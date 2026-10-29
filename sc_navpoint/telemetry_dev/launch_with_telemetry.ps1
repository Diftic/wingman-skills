<#
.SYNOPSIS
  Start the RSI Launcher with Star Citizen's gRPC client server switched on, then report what the game opens.

.DESCRIPTION
  Dev probe only. The two settings below were found in StarCitizen.exe 4.10.2 (CIGServices config:
  grpc.client.server.enabled / grpc.client.server.address, env names GRPC_CLIENT_SERVER_*). They are set
  ONLY for the launcher process started here, so the game inherits them if the launcher passes its
  environment on. Nothing is written to the registry, user environment or game files.
  Unverified: that the game reads these env vars, which boolean spelling it accepts, and whether the
  telemetry service registers on that server.

.EXAMPLE
  .\launch_with_telemetry.ps1
  .\launch_with_telemetry.ps1 -Enabled 1
#>
param(
    [string]$Launcher = 'D:\Roberts Space Industries\RSI Launcher\RSI Launcher.exe',
    [string]$GameLog = 'D:\Roberts Space Industries\StarCitizen\LIVE\Game.log',
    [string]$Enabled = 'true',
    [string]$Address = '127.0.0.1:2942',
    [int]$WaitMinutes = 15
)

$ErrorActionPreference = 'Stop'
$PollSeconds = 5

if (-not (Test-Path $Launcher)) { throw "RSI Launcher not found at '$Launcher'. Pass -Launcher <path>." }
if (-not $Address.StartsWith('127.0.0.1:')) { throw "Refusing a non-loopback address '$Address'." }

# A launcher left running (also in the tray) would just be focused and never see the new variables.
$running = Get-Process -Name 'RSI Launcher', 'StarCitizen' -ErrorAction SilentlyContinue
if ($running) {
    throw "Quit the RSI Launcher (including the tray icon) and Star Citizen first: $($running.Name -join ', ')"
}

$psi = [System.Diagnostics.ProcessStartInfo]::new($Launcher)
$psi.UseShellExecute = $false
$psi.Environment['GRPC_CLIENT_SERVER_ENABLED'] = $Enabled
$psi.Environment['GRPC_CLIENT_SERVER_ADDRESS'] = $Address
[void][System.Diagnostics.Process]::Start($psi)
Write-Host "Launcher started with GRPC_CLIENT_SERVER_ENABLED=$Enabled GRPC_CLIENT_SERVER_ADDRESS=$Address"
Write-Host "Start the game from the launcher. Waiting up to $WaitMinutes min for StarCitizen.exe ..."

$deadline = (Get-Date).AddMinutes($WaitMinutes)
$game = $null
while (-not $game -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds $PollSeconds
    $game = Get-Process -Name 'StarCitizen' -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $game) { throw 'StarCitizen.exe did not start in time.' }
Write-Host "StarCitizen.exe running (pid $($game.Id)). Watching its listening ports and Game.log ..."

$port = [int]($Address.Split(':')[1])
$seen = @{}
while (-not $game.HasExited -and (Get-Date) -lt $deadline.AddMinutes($WaitMinutes)) {
    $listening = Get-NetTCPConnection -OwningProcess $game.Id -State Listen -ErrorAction SilentlyContinue
    foreach ($entry in $listening) {
        $key = "$($entry.LocalAddress):$($entry.LocalPort)"
        if (-not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            $mark = if ($entry.LocalPort -eq $port) { '  <-- expected telemetry port' } else { '' }
            Write-Host "listening: $key$mark"
        }
    }
    if ($seen.Keys -match ":$port$") {
        Write-Host "Port $port is open. Run: python probe.py"
        break
    }
    Start-Sleep -Seconds $PollSeconds
}
if (-not ($seen.Keys -match ":$port$")) { Write-Host "Port $port never opened." }

if (Test-Path $GameLog) {
    Write-Host '--- Game.log lines about gRPC services / telemetry ---'
    Select-String -Path $GameLog -Pattern "Register Service|Service '.*' registered|Server Channel Arg|GameTelemetry|Client connected|grpc" |
        Select-Object -Last 20 | ForEach-Object { $_.Line }
}
