# Shared .env loader for install.ps1 and run_update.ps1 (Windows counterparts
# to install.sh/run_update.sh, which load .env via bash `source`).
#
# Strips exactly one layer of matching quotes and does NOT interpret escapes
# inside them, matching bash single-quote semantics -- so a named SQL Server
# instance like JOBBOSS_DB_HOST='SRV\INSTANCE' survives intact instead of
# losing its backslash. See .env.example's comment on this; it's the same
# reason run_update.sh requires single-quoting that value.
function Import-DotEnv {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path $Path)) { return }
    foreach ($line in Get-Content -Path $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        if ($trimmed -notmatch '^([^=]+)=(.*)$') { continue }
        $key = $Matches[1].Trim()
        $val = $Matches[2]
        if ($val.Length -ge 2) {
            $first = $val[0]; $last = $val[$val.Length - 1]
            if ((($first -eq "'") -and ($last -eq "'")) -or (($first -eq '"') -and ($last -eq '"'))) {
                $val = $val.Substring(1, $val.Length - 2)
            }
        }
        Set-Item -Path "Env:$key" -Value $val
    }
}
