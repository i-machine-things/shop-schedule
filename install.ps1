# Windows counterpart to install.sh -- server role only (DB polling, HTTP
# server, local kiosk display). Run once from the cloned repo directory, as
# Administrator (scheduled tasks need it -- the opposite of install.sh's
# "do not run as root", because Windows's privilege model works the other
# way around).
#
# JobBoss DB is the only source this installer sets up -- PDFs can still be
# dropped into incoming/ or uploaded via options.html as a fallback.

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
# $ErrorActionPreference = 'Stop' does NOT catch a native command's non-zero
# exit code on its own (that's a PowerShell/.NET error, not a process exit
# status) -- without checking $LASTEXITCODE explicitly here, a failed pip
# install wouldn't stop the script, and the scheduled tasks registered below
# would still get created and started with a venv that can't actually import
# its own dependencies. CodeRabbit catch on PR #277.
& $VenvPython -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip upgrade failed (exit $LASTEXITCODE) -- aborting install."
    exit 1
}
# Same pin as install.sh (python-tds 1.14+ needs typing.Protocol/TypedDict,
# unavailable on the Pi's old Python 3.7) -- kept identical here too so a
# shared .env/venv story stays simple, even though a Windows install is
# unlikely to hit that specific constraint itself.
& $VenvPython -m pip install --quiet pdfplumber reportlab "python-tds==1.13.0" pyOpenSSL pywin32
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install of dependencies failed (exit $LASTEXITCODE) -- aborting install."
    exit 1
}

# --- .env --------------------------------------------------------------

$EnvPath = Join-Path $InstallDir '.env'
if (-not (Test-Path $EnvPath)) {
    Copy-Item (Join-Path $InstallDir '.env.example') $EnvPath
}

. (Join-Path $InstallDir 'dotenv.ps1')
Import-DotEnv $EnvPath

Write-Host ""
Write-Host "=== Configure .env ==="

if (-not $env:SHOP_NAME -or $env:SHOP_NAME -eq 'Your Shop Name') {
    $shopName = Read-Host '  Shop name (shown in schedule header)'
    if ($shopName) { Set-DotEnvValue -Key 'SHOP_NAME' -Value $shopName -Path $EnvPath }
}

Write-Host "  Fill in JOBBOSS_DB_HOST/NAME/USER/PASS in .env before the first scheduled run -- see README.md."
Write-Host "  Once JOBBOSS_DB_PASS is set, run .\protect-db-password.ps1 to encrypt it at rest (optional but recommended)."

# Restrict .env to this account + SYSTEM, parallel to install.sh's `chmod 600`.
# /reset first, THEN apply the restriction -- /inheritance:r only strips
# INHERITED ACEs and /grant:r only replaces the grant for the named accounts;
# neither removes other pre-existing EXPLICIT ACEs an existing .env (this
# installer reuses one if present) might already have, which could leave a
# broader-than-intended grant readable alongside these two. /reset clears
# back to default inherited ACLs first so the explicit grant below is the
# only one left standing. CodeRabbit security catch on PR #277, confirmed
# against Microsoft's icacls docs (semantics of /inheritance:r and /grant:r
# are each scoped as described, not a full ACL wipe).
icacls $EnvPath /reset | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "icacls /reset on .env failed (exit $LASTEXITCODE)"; exit 1 }
icacls $EnvPath /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):F" "SYSTEM:F" | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "icacls restriction on .env failed (exit $LASTEXITCODE)"; exit 1 }

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

$IncomingPath = Join-Path $InstallDir 'incoming'
New-Item -ItemType Directory -Force -Path (Join-Path $PublicDir 'raw') | Out-Null
New-Item -ItemType Directory -Force -Path $IncomingPath | Out-Null
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

# --- Retire a legacy SMB drop share from a pre-removal install -------------
# Only touch it if it's still pointing at this install's incoming/ (not
# repointed/renamed) -- and only remove the share plus the EXACT Everyone
# grant this installer itself added (icacls /grant 'Everyone:(OI)(CI)M' in
# older versions), not smbd/discovery services wholesale, since this PC may
# use SMB for something unrelated to this app.
#
# RemoveAccessRuleSpecific(), not RemoveAccessRule(), is required here --
# verified directly (not just reasoned about): RemoveAccessRule() does a
# rights SUBTRACTION against any rule for the same identity, so on a folder
# with only an unrelated Everyone:(OI)(CI)(R) grant (not the legacy Modify
# one), it still returns $true and rewrites that grant down to a near-empty
# Everyone:(OI)(CI)(S) ACE -- corrupting an admin's unrelated grant instead
# of leaving it alone. RemoveAccessRuleSpecific() only removes a rule that
# matches identity+rights+inheritance+propagation+type exactly, with no
# partial-match mutation, confirmed by comparing $Acl.Access counts
# before/after against both an exact-match folder and an unrelated-grant one.
$LegacyShare = Get-SmbShare -Name 'schedule-drop' -ErrorAction SilentlyContinue
if ($LegacyShare -and (Test-Path $LegacyShare.Path) -and
        ((Get-Item $LegacyShare.Path).FullName -eq (Get-Item $IncomingPath).FullName)) {
    Remove-SmbShare -Name 'schedule-drop' -Force
    $Acl = Get-Acl $IncomingPath
    $CountBefore = $Acl.Access.Count
    $EveryoneSid = New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')
    $LegacyRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $EveryoneSid, 'Modify', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $Acl.RemoveAccessRuleSpecific($LegacyRule)
    if ($Acl.Access.Count -lt $CountBefore) {
        Set-Acl -Path $IncomingPath -AclObject $Acl
        Write-Host "Removed legacy 'schedule-drop' SMB share and its ACL grant -- SMB drop is no longer supported (see README.md)."
    } else {
        Write-Warning "Removed legacy 'schedule-drop' SMB share, but found no matching Everyone:(OI)(CI)M grant on $IncomingPath to clean up -- check its ACL manually if needed."
    }
}

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
