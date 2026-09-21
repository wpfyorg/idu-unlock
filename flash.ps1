#!/usr/bin/env pwsh
<#
flash.ps1 — root access + full backup for JIDU routers, on Windows. No firmware
is written. The Windows twin of flash.sh: same commands, same options.

  .\flash.ps1                 verify the router -> unlock root SSH -> back it up
  .\flash.ps1 check           can this unit be unlocked? (read-only, safe to run in bulk)
  .\flash.ps1 unlock          root SSH only (persistent, survives reboots)
  .\flash.ps1 backup          factory credentials + a copy of every partition
  .\flash.ps1 detect          identify the model, change nothing

Options:
  --router URL    router base URL (default https://192.168.31.1)
  --password P    router admin password (prompted if omitted)
  --key PATH      SSH key (default ~\.ssh\idu_rsa)

The router must be SET UP, not factory-fresh: a reset IDU keeps its API locked
until the setup wizard is completed in the web UI. Reset it, finish the wizard
(which sets the admin password), then run this and supply that password.

The router fetches the installer by calling back to this PC on port 80, so
Windows Firewall must let python.exe through on your private network — see the
"On Windows" section of the README.

Only run against equipment you own or are explicitly authorised to test.
Provided as is, without warranty, without liability — see the README.
#>

$ErrorActionPreference = 'Stop'
# `check` exits 2 for "not unlockable" - a normal answer, not a failure. Make sure
# a stricter session preference cannot turn that into a thrown error.
$PSNativeCommandUseErrorActionPreference = $false

$Here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

function Say  { param([string]$Text) Write-Host '[*] ' -ForegroundColor Blue  -NoNewline; Write-Host $Text }
function Good { param([string]$Text) Write-Host '[+] ' -ForegroundColor Green -NoNewline; Write-Host $Text }
function Bad  { param([string]$Text) Write-Host '[x] ' -ForegroundColor Red   -NoNewline; Write-Host $Text }

function Show-Usage {
  Write-Host @'
Usage: .\flash.ps1 [command] [options]

Commands:
  (none)    verify the router -> unlock root SSH -> back it up
  check     can this unit be unlocked? (read-only, safe to run in bulk)
  unlock    root SSH only (persistent, survives reboots)
  backup    factory credentials + a copy of every partition
  detect    identify the model, change nothing

Options:
  --router URL    router base URL (default https://192.168.31.1)
  --password P    router admin password (prompted if omitted)
  --key PATH      SSH key (default ~\.ssh\idu_rsa)
'@
}

# ---- arguments ----------------------------------------------------------- #
$Command  = ''
$Router   = if ($env:ROUTER)   { $env:ROUTER }   else { 'https://192.168.31.1' }
$Password = if ($env:PASSWORD) { $env:PASSWORD } else { '' }
$Key      = if ($env:KEY)      { $env:KEY }      else { '' }

$index = 0
while ($index -lt $args.Count) {
  $token = [string]$args[$index]

  if ($token -in @('-h', '--help')) {
    Show-Usage
    exit 0
  }
  elseif ($token -in @('--router', '-router')) {
    if ($index + 1 -ge $args.Count) { Bad "missing value for $token"; exit 2 }
    $index++; $Router = [string]$args[$index]
  }
  elseif ($token -in @('--password', '-password')) {
    if ($index + 1 -ge $args.Count) { Bad "missing value for $token"; exit 2 }
    $index++; $Password = [string]$args[$index]
  }
  elseif ($token -in @('--key', '-key')) {
    if ($index + 1 -ge $args.Count) { Bad "missing value for $token"; exit 2 }
    $index++; $Key = [string]$args[$index]
  }
  elseif ($token -in @('unlock', 'backup', 'detect', 'check')) {
    $Command = $token
  }
  elseif ($token -eq 'flash') {
    Bad 'this tool no longer writes firmware - use it for root access and backups.'
    exit 2
  }
  else {
    Bad "unknown option: $token"
    Show-Usage
    exit 2
  }

  $index++
}
if (-not $Command) { $Command = 'auto' }

# ---- an interpreter that has `requests` ---------------------------------- #
#
# urllib3 v2 requires OpenSSL 1.1.1+ and complains on anything else — which
# includes every Python Apple ships, linked against LibreSSL. This tool only
# ever talks to the router with verification off, so the still-maintained
# urllib3 1.x costs nothing and keeps the output clean.
function Test-Python {
  param([string]$Exe, [string[]]$Prefix = @(), [string]$Code)
  $probe = $Prefix + @('-c', $Code)
  & $Exe @probe *> $null
  return ($LASTEXITCODE -eq 0)
}

function Test-Tls {
  param([string]$Exe, [string[]]$Prefix = @())
  $code = 'import ssl, sys; sys.exit(0 if ssl.OPENSSL_VERSION.startswith("OpenSSL ") ' +
          'and ssl.OPENSSL_VERSION_INFO >= (1, 1, 1) else 1)'
  return (Test-Python -Exe $Exe -Prefix $Prefix -Code $code)
}

function Test-Deps {
  param([string]$Exe, [string[]]$Prefix = @())
  $code = @(
    'import ssl, sys'
    'try:'
    '    import requests, urllib3'
    'except ImportError:'
    '    sys.exit(1)'
    'tls = (ssl.OPENSSL_VERSION.startswith("OpenSSL ")'
    '       and ssl.OPENSSL_VERSION_INFO >= (1, 1, 1))'
    'sys.exit(0 if tls or urllib3.__version__.startswith("1.") else 1)'
  ) -join "`n"
  return (Test-Python -Exe $Exe -Prefix $Prefix -Code $code)
}

$SystemPy = $null      # a working Python 3, regardless of what it has installed
$PyExe    = $null      # the interpreter we will actually run
$PyArgs   = @()
$PyPin    = @()        # dependency pins, if this interpreter's TLS needs them

foreach ($candidate in @(
    [pscustomobject]@{ Exe = 'py';      Args = @('-3') },
    [pscustomobject]@{ Exe = 'python';  Args = @() },
    [pscustomobject]@{ Exe = 'python3'; Args = @() })) {

  if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
  if (-not (Test-Python -Exe $candidate.Exe -Prefix $candidate.Args -Code 'import sys')) { continue }

  if (-not $SystemPy) {
    $SystemPy = $candidate
    if (-not (Test-Tls -Exe $candidate.Exe -Prefix $candidate.Args)) { $PyPin = @('urllib3<2') }
  }

  if (Test-Deps -Exe $candidate.Exe -Prefix $candidate.Args) {
    $PyExe  = $candidate.Exe
    $PyArgs = $candidate.Args
    break
  }
}

if (-not $PyExe) {
  $venvPy  = Join-Path $Here '.venv\Scripts\python.exe'
  $venvPip = Join-Path $Here '.venv\Scripts\pip.exe'
  $usable  = (Test-Path $venvPy) -and (Test-Deps -Exe $venvPy)

  if ($usable) {
    $PyExe = $venvPy
  }
  else {
    if (-not $SystemPy) {
      Bad 'no Python 3 found. Install it with:  winget install Python.Python.3.12'
      Bad '(tick "Add python.exe to PATH" if the installer offers it), then reopen'
      Bad 'PowerShell and try again.'
      exit 1
    }
    Say "installing dependencies into $Here\.venv ..."
    $venvArgs = $SystemPy.Args + @('-m', 'venv', (Join-Path $Here '.venv'))
    & $SystemPy.Exe @venvArgs
    if ($LASTEXITCODE -ne 0) { Bad 'could not create a venv'; exit 1 }
    $pipArgs = @('-q', 'install', '--upgrade', 'pip', 'requests') + $PyPin
    & $venvPip @pipArgs
    if ($LASTEXITCODE -ne 0) { Bad 'pip failed'; exit 1 }
    $PyExe = $venvPy
  }
}

# ---- ssh key ------------------------------------------------------------- #
if (-not $Key) { $Key = Join-Path $HOME '.ssh\idu_rsa' }

# ---- password ------------------------------------------------------------ #
if (-not $Password) {
  $secure = Read-Host -Prompt 'Enter the router admin password (set during the router setup)' -AsSecureString
  $Password = (New-Object -TypeName System.Net.NetworkCredential -ArgumentList '', $secure).Password
}
if (-not $Password) { Bad 'no password given'; exit 2 }

function Invoke-Id {
  param([string[]]$IdArgs = @())
  $callArgs  = @()
  $callArgs += $PyArgs
  $callArgs += (Join-Path $Here 'idu.py')
  $callArgs += @('--router', $Router, '--password', $Password, '--key', $Key)
  $callArgs += $IdArgs
  # straight to the host, so the caller captures only the exit code
  & $PyExe @callArgs | Out-Host
  return $LASTEXITCODE
}

function Confirm-Device {
  Say "checking $Router ..."
  if ((Invoke-Id @('detect')) -ne 0) {
    Bad 'could not take over the router. Usual causes:'
    Bad '  * it is unreachable, or an admin session is already open;'
    Bad '  * it is factory-reset - finish the setup wizard in the web UI first;'
    Bad '  * the password is wrong (the router locks out after ~5 tries).'
    exit 1
  }
}

$RouterHost = ($Router -replace '^[A-Za-z][A-Za-z0-9+.-]*://', '') -replace '/.*$', ''
$OutDir     = (Get-Location).Path

switch ($Command) {
  'detect' {
    if ((Invoke-Id @('detect')) -ne 0) { exit 1 }
  }

  'check' {
    exit (Invoke-Id @('check'))
  }

  'unlock' {
    Confirm-Device
    if ((Invoke-Id @('unlock')) -ne 0) { exit 1 }
    Good "try: ssh -i `"$Key`" -o IdentitiesOnly=yes root@$RouterHost"
  }

  'backup' {
    Confirm-Device
    if ((Invoke-Id @('unlock')) -ne 0) { exit 1 }
    if ((Invoke-Id @('backup', '--outdir', $OutDir)) -ne 0) { exit 1 }
    Good "backup written under $OutDir"
  }

  'auto' {
    Confirm-Device
    if ((Invoke-Id @('unlock')) -ne 0) { exit 1 }
    if ((Invoke-Id @('backup', '--outdir', $OutDir)) -ne 0) { exit 1 }
    Good "backup written under $OutDir"
    Good "try: ssh -i `"$Key`" -o IdentitiesOnly=yes root@$RouterHost"
  }
}
