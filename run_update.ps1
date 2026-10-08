# Windows counterpart to run_update.sh -- invoked every 15 minutes by the
# "ShopScheduleUpdate" scheduled task (see install.ps1). Loads .env, stages
# any SMB-dropped PDFs, then regenerates the schedule.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir 'dotenv.ps1')
Import-DotEnv (Join-Path $ScriptDir '.env')

$VenvPython = Join-Path $ScriptDir 'venv\Scripts\python.exe'
$Python = if (Test-Path $VenvPython) {
    $VenvPython
} elseif ($env:FOREMAN_PYTHON) {
    $env:FOREMAN_PYTHON
} else {
    'python'
}

$LogFile = Join-Path $ScriptDir 'shop-schedule.log'

# Non-fatal if this fails (mirrors run_update.sh's `|| true`) -- a bad drop
# shouldn't block the regeneration below. Native-exe exit codes don't raise
# PowerShell errors on their own, so no explicit try/catch is needed here.
& $Python (Join-Path $ScriptDir 'process_drop.py') --no-regen *>> $LogFile

& $Python (Join-Path $ScriptDir 'update_schedule.py') @args *>> $LogFile
exit $LASTEXITCODE
