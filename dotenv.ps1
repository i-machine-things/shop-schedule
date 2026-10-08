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
    # Explicit -Encoding UTF8 -- Windows PowerShell 5.1's Get-Content defaults
    # to the system ANSI codepage for a BOM-less file, not UTF-8. A .env saved
    # as UTF-8 without a BOM (common from most editors) with any non-ASCII
    # character (e.g. in SHOP_NAME) would otherwise decode wrong. CodeRabbit
    # catch on PR #277.
    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        if ($trimmed -notmatch '^([^=]+)=(.*)$') { continue }
        $key = $Matches[1].Trim()
        $val = $Matches[2]
        if ($val.Length -ge 2) {
            $first = $val[0]; $last = $val[$val.Length - 1]
            if ((($first -eq "'") -and ($last -eq "'")) -or (($first -eq '"') -and ($last -eq '"'))) {
                $val = $val.Substring(1, $val.Length - 2)
                if ($first -eq "'") {
                    # Reverse install.ps1's Set-EnvFileValue / install.sh's
                    # _set_env() escaping for an embedded single quote
                    # (close-quote, double-quoted literal quote, reopen-
                    # quote) back to a literal ' -- so a value written by
                    # either platform's installer round-trips correctly
                    # through this reader too, not just through bash's own
                    # eval-based one in _get_env().
                    $dq = [char]34
                    $val = $val -replace "'$dq'$dq'", "'"
                }
            }
        }
        Set-Item -Path "Env:$key" -Value $val
    }
}
