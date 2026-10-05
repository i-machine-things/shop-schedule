# Encrypts JOBBOSS_DB_PASS in .env at rest using Windows DPAPI, the same
# primitive behind Windows Credential Manager and how Excel/Power Query
# protect a remembered SQL login (see README.md's "Securing the DB password"
# section). Run any time after editing .env with a plaintext password,
# including to re-encrypt after rotating it.
#
# Uses DataProtectionScope.LocalMachine, not CurrentUser -- the
# ShopScheduleServer/ShopScheduleUpdate scheduled tasks run as SYSTEM (see
# install.ps1), not the account running this script, and CurrentUser-scoped
# DPAPI blobs are only decryptable by the exact account that encrypted them.
# LocalMachine trades some of DPAPI's protection for that compatibility: any
# local account on this machine can decrypt it, not just the one that ran
# this script -- still meaningfully better than the plaintext this replaces
# (decryption needs local code execution on this specific machine, not just
# read access to .env), but it is not account-level secrecy.
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $ScriptDir '.env'

. (Join-Path $ScriptDir 'dotenv.ps1')
Import-DotEnv $EnvPath

if (-not $env:JOBBOSS_DB_PASS) {
    Write-Error "JOBBOSS_DB_PASS is not set in $EnvPath -- nothing to encrypt."
    exit 1
}
if ($env:JOBBOSS_DB_PASS.StartsWith('dpapi:')) {
    Write-Host "JOBBOSS_DB_PASS is already DPAPI-encrypted -- nothing to do."
    exit 0
}

Add-Type -AssemblyName System.Security
$bytes = [System.Text.Encoding]::UTF8.GetBytes($env:JOBBOSS_DB_PASS)
$encrypted = [System.Security.Cryptography.ProtectedData]::Protect(
    $bytes, $null, [System.Security.Cryptography.DataProtectionScope]::LocalMachine)
$encoded = [Convert]::ToBase64String($encrypted)

Set-DotEnvValue -Key 'JOBBOSS_DB_PASS' -Value "dpapi:$encoded" -Path $EnvPath

Write-Host "JOBBOSS_DB_PASS is now DPAPI-encrypted in $EnvPath."
Write-Host "Decryptable only on this machine -- copying .env to another PC will require re-entering the plaintext password and running this again."
