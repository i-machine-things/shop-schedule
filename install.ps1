# Windows counterpart to install.sh -- server role only (DB polling, HTTP
# server, drop-folder share, local kiosk display). Run once from the cloned
# repo directory, as Administrator (scheduled tasks and the SMB share both
# need it -- the opposite of install.sh's "do not run as root", because
# Windows's privilege model works the other way around).
#
# JobBoss DB is the only source this installer sets up -- Gmail/PDF polling
# is deprecated (see README.md) and isn't offered here even though it's
# still technically supported by update_schedule.py for existing installs.

$ErrorActionPreference = 'Stop'
$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Run this as Administrator -- right-click PowerShell -> 'Run as Administrator', then re-run install.ps1."
    exit 1
}

Write-Host "=== Shop Schedule Installer (Windows) ==="
Write-Host "Install directory: $InstallDir"
Write-Host ""

# --- Dependencies ----------------------------------------------------------

function Resolve-SystemPython {
    foreach ($cmd in @('python', 'python3')) {
        $c = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
    }
    if (Get-Command 'py' -ErrorAction SilentlyContinue) {
        $resolved = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($resolved) { return $resolved.Trim() }
    }
    return $null
}

$SystemPython = Resolve-SystemPython
if (-not $SystemPython) {
    Write-Error "Python 3 not found. Install it from https://www.python.org/downloads/ (check 'Add python.exe to PATH') and re-run."
    exit 1
}

& $SystemPython -m venv (Join-Path $InstallDir 'venv')
$VenvPython = Join-Path $InstallDir 'venv\Scripts\python.exe'
& $VenvPython -m pip install --quiet --upgrade pip
# Same pin as install.sh (python-tds 1.14+ needs typing.Protocol/TypedDict,
# unavailable on the Pi's old Python 3.7) -- kept identical here too so a
# shared .env/venv story stays simple, even though a Windows install is
# unlikely to hit that specific constraint itself.
& $VenvPython -m pip install --quiet pdfplumber reportlab "python-tds==1.13.0" pyOpenSSL

# --- .env --------------------------------------------------------------

$EnvPath = Join-Path $InstallDir '.env'
if (-not (Test-Path $EnvPath)) {
    Copy-Item (Join-Path $InstallDir '.env.example') $EnvPath
}

. (Join-Path $InstallDir 'dotenv.ps1')
Import-DotEnv $EnvPath

function Set-EnvFileValue {
    param([string]$Key, [string]$Value, [string]$Path)
    $line = "$Key='$Value'"
    $content = @(if (Test-Path $Path) { Get-Content $Path } else { @() })
    if ($content -match "^$Key=") {
        $content = $content | ForEach-Object { if ($_ -match "^$Key=") { $line } else { $_ } }
    } else {
        $content += $line
    }
    Set-Content -Path $Path -Value $content -Encoding utf8
}

Write-Host ""
Write-Host "=== Configure .env ==="

if (-not $env:SHOP_NAME -or $env:SHOP_NAME -eq 'Your Shop Name') {
    $shopName = Read-Host '  Shop name (shown in schedule header)'
    if ($shopName) { Set-EnvFileValue -Key 'SHOP_NAME' -Value $shopName -Path $EnvPath }
}

Write-Host "  Fill in JOBBOSS_DB_HOST/NAME/USER/PASS in .env before the first scheduled run -- see README.md."

# Restrict .env to this account + SYSTEM, parallel to install.sh's `chmod 600`.
icacls $EnvPath /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):F" "SYSTEM:F" | Out-Null

# --- Placeholder pages (schedule + kiosk) shown before first run -----------

$PublicDir = Join-Path $InstallDir 'public'
New-Item -ItemType Directory -Force -Path $PublicDir | Out-Null
$WaitingHtml = @'
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta http-equiv="refresh" content="60">
<style>body{background:#07070f;color:#4af;font-family:monospace;
display:flex;align-items:center;justify-content:center;height:100vh;font-size:24px}</style>
</head><body>Waiting for Foreman's Report...</body></html>
'@
foreach ($name in @('schedule.html', 'kiosk.html')) {
    $p = Join-Path $PublicDir $name
    if (-not (Test-Path $p)) { Set-Content -Path $p -Value $WaitingHtml -Encoding utf8 }
}

# Populate the schedule on first run if a PDF is already sitting in incoming/
# or last_report.pdf (mirrors install.sh's bootstrap step).
& $VenvPython (Join-Path $InstallDir 'process_drop.py') --no-regen 2>$null
$LastReport = Join-Path $InstallDir 'last_report.pdf'
if (Test-Path $LastReport) {
    Write-Host "Regenerating schedule from existing PDF..."
    Import-DotEnv $EnvPath
    & $VenvPython (Join-Path $InstallDir 'update_schedule.py')
}

$PagesJson = Join-Path $PublicDir 'pages.json'
if (-not (Test-Path $PagesJson)) {
    Copy-Item (Join-Path $InstallDir 'pages.json.example') $PagesJson
}

New-Item -ItemType Directory -Force -Path (Join-Path $PublicDir 'raw') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir 'incoming') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir 'processed') | Out-Null

# --- HTTP server: scheduled task, starts at boot, restarts on failure ------

$ServerAction = New-ScheduledTaskAction -Execute (Join-Path $InstallDir 'venv\Scripts\pythonw.exe') `
    -Argument "`"$(Join-Path $InstallDir 'server.py')`"" -WorkingDirectory $InstallDir
$ServerTrigger = New-ScheduledTaskTrigger -AtStartup
$ServerSettings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'ShopScheduleServer' -Action $ServerAction -Trigger $ServerTrigger `
    -Settings $ServerSettings -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName 'ShopScheduleServer'

# --- Schedule updater: scheduled task, every 15 minutes --------------------

$UpdateAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallDir 'run_update.ps1')`"" `
    -WorkingDirectory $InstallDir
# RepetitionDuration needs a concrete (not MaxValue -- that can fail to
# serialize into Task Scheduler's XML) span for "repeats indefinitely"; 10
# years is the conventional stand-in for that.
$UpdateTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName 'ShopScheduleUpdate' -Action $UpdateAction -Trigger $UpdateTrigger `
    -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName 'ShopScheduleUpdate'

# --- Local kiosk display: scheduled task, at logon -------------------------

$ChromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
)
$EdgePaths = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
)
$Browser = ($ChromePaths + $EdgePaths) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Browser) {
    Write-Warning "Neither Chrome nor Edge found -- skipping the local kiosk display task. Install one and re-run, or set it up manually."
} else {
    $KioskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $InstallDir 'kiosk-launch.ps1')`" -BrowserPath `"$Browser`"")
    $KioskTrigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $KioskSettings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Days 0)
    Register-ScheduledTask -TaskName 'ShopScheduleKiosk' -Action $KioskAction -Trigger $KioskTrigger `
        -Settings $KioskSettings -Force | Out-Null
    Write-Host "Kiosk display ($Browser) will launch on next login -- log off/on to start it now."
}

# --- SMB drop share ----------------------------------------------------

$ShareName = 'schedule-drop'
$IncomingPath = Join-Path $InstallDir 'incoming'
if (-not (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue)) {
    New-SmbShare -Name $ShareName -Path $IncomingPath -FullAccess 'Everyone' | Out-Null
}
# Modern Windows removed true anonymous/guest SMB access (the 1709 update
# dropped the SMB1 guest fallback) -- there's no equivalent to install.sh's
# `map to guest = bad user` Samba setting here. The share above still
# requires connecting machines to authenticate with a real Windows account
# on this PC; see README.md for what that means in practice.

# --- Done --------------------------------------------------------------

$IpAddress = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.InterfaceAlias -notmatch 'Loopback' } | Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "=== Done ==="
Write-Host "1. Edit $EnvPath -- fill in JOBBOSS_DB_HOST/NAME/USER/PASS (see README.md)"
Write-Host "2. Drop a PDF into $IncomingPath to test"
Write-Host "3. View at:    http://${IpAddress}:8080/"
Write-Host "4. Upload at:  http://${IpAddress}:8080/options.html"
Write-Host "5. Edit $PagesJson to manually add URLs to the kiosk rotation"
Write-Host "6. Drop PDFs via SMB: \\$IpAddress\$ShareName  (requires a Windows account on this PC -- see README.md)"
