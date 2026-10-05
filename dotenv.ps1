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

# Shared .env writer -- single-quotes the value (matching Import-DotEnv's
# read side above) and replaces the key's existing line if present, appends
# otherwise. Used by install.ps1 (initial prompts) and protect-db-password.ps1
# (rewriting JOBBOSS_DB_PASS in place after encrypting it).
function Set-DotEnvValue {
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
