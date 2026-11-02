#!/usr/bin/env pwsh
<#
fwflash.ps1 - fetch and flash an OpenWrt image for a JIDU router, on Windows.

  .\fwflash.ps1 6j01                 unlock if needed, then flash a JIDU6J01
  .\fwflash.ps1 6j11                 unlock if needed, then flash a JIDU6J11
  .\fwflash.ps1 6j11 -Smallbuffers   ...using the reduced-buffer sysupgrade build
  .\fwflash.ps1 6j01 -DownloadOnly   cache the images, flash nothing
  .\fwflash.ps1 6101                 unlock if needed, then flash a JIDU6101

Options:
  -Router HOST     stock unit address (default 192.168.31.1)
  -Key PATH        RSA private key used for stock root SSH and automatic unlock
  -Cache DIR       where images are kept (default .\downloads, next to this script)
  -Image PATH      use a local sysupgrade file instead of downloading one
  -ImageSha256 HEX the sha256 of -Image; without it you must still confirm
  -Smallbuffers    6j11 only: flash the small-buffers sysupgrade build
  -DownloadOnly    cache the images and stop
  -DryRun          print what would run, touch nothing
  -Yes             skip the confirmation prompt

Images land in .\downloads\<model>\ next to this script and stay there. On the
next run anything already present is reused, so nothing is downloaded twice.
Every file is checked against the sha256 in manifest.json before use, including
files already on disk, so a corrupt or half-written download is never flashed.

If the unit has no root SSH yet, this runs the unlocker in the repo root
(.\flash.ps1 unlock) and asks for the router admin password - so the whole
install is one command. Back the unit up if you can: .\flash.ps1 backup keeps a
copy of every partition, and flashing is not reversible over the network.

Only run against equipment you own or are explicitly authorised to test.
Provided as is, without warranty, without liability - see the README.
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet('6j01', '6j11', '6101')]
    [string]$Model,

    [string]$Router = '192.168.31.1',
    [string]$Key,
    [string]$Cache,
    [string]$Image,
    [string]$ImageSha256,
    [switch]$Smallbuffers,
    [switch]$DownloadOnly,
    [switch]$DryRun,
    [switch]$Yes,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

$Here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Manifest = Join-Path $Here 'manifest.json'
$OpenWrt = '192.168.1.1'

function Say  ($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok   ($m) { Write-Host "[+] $m" -ForegroundColor Green }
function Warn ($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Bad  ($m) { Write-Host "[-] $m" -ForegroundColor Red }
function Die  ($m) { Bad $m; exit 1 }

if ($Help -or -not $Model) {
    Get-Content $PSCommandPath | Select-Object -Skip 1 -First 28 |
        ForEach-Object { $_ -replace '^# ?', '' }
    exit ([int](-not $Model))
}

if (-not $Cache) { $Cache = Join-Path $Here 'downloads' }
if (-not $Key -and $env:KEY) { $Key = $env:KEY }

if (-not (Test-Path $Manifest)) { Die "missing $Manifest" }
$Data = Get-Content $Manifest -Raw | ConvertFrom-Json
$Spec = $Data.models.$Model
if (-not $Spec) { Die "model $Model is not in the manifest" }

$Dest = Join-Path $Cache $Model
if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $Dest | Out-Null }

Say $Spec.title
Say "images: $Dest"

function Test-Image ($Role) {
    $img = $Spec.images.$Role
    if (-not $img) { return $null }
    $path = Join-Path $Dest $img.name
    if (-not (Test-Path $path)) { return $null }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -eq $img.sha256.ToUpper()) { return $path }
    if ($DryRun) {
        Warn "cached $($img.name) does not match the manifest (a real run would replace it)"
    }
    else {
        Warn "cached $($img.name) does not match the manifest, re-downloading"
        Remove-Item $path -Force
    }
    return $null
}

function Get-Image ($Role) {
    $img = $Spec.images.$Role
    if (-not $img) { Die "the manifest has no '$Role' image for $Model" }

    $cached = Test-Image $Role
    if ($cached) { Ok "$($img.name) (cached)"; return $cached }

    $path = Join-Path $Dest $img.name
    $part = "$path.part"
    $mib = [math]::Round($img.size / 1MB)
    Say "downloading $($img.name) ($mib MiB)"

    if ($DryRun) {
        Write-Host "    would run: Invoke-WebRequest $($img.url) -> $path"
        return $path
    }

    try {
        Invoke-WebRequest -Uri $img.url -OutFile $part -UseBasicParsing
    }
    catch {
        if (Test-Path $part) { Remove-Item $part -Force }
        Die "download failed: $($img.url)"
    }

    if ((Get-FileHash $part -Algorithm SHA256).Hash -ne $img.sha256.ToUpper()) {
        Remove-Item $part -Force
        Die "$($img.name): sha256 mismatch, refusing to use it"
    }
    Move-Item -Force $part $path
    Ok "$($img.name) (verified)"
    return $path
}

# --- what do we need? -------------------------------------------------------
$Sysupgrade = $null
if ($Image) {
    if (-not (Test-Path $Image)) { Die "no such file: $Image" }
    $Sysupgrade = (Resolve-Path $Image).Path
    $actual = (Get-FileHash $Sysupgrade -Algorithm SHA256).Hash
    if ($ImageSha256) {
        if ($actual -ne $ImageSha256.ToUpper()) { Die "$Image`: sha256 mismatch, refusing to use it" }
        Ok "$(Split-Path $Sysupgrade -Leaf) (matches the hash you supplied)"
    }
    else {
        Warn "$(Split-Path $Sysupgrade -Leaf) is not checked against the manifest"
        Write-Host "    its sha256 is $actual"
        $Yes = $false   # a hand-picked image always gets the typed confirmation
    }
}

$Factory = Get-Image 'factory'
if (-not $Sysupgrade) {
    if ($Model -eq '6j11' -and $Smallbuffers) { $Sysupgrade = Get-Image 'smallbuffers' }
    else { $Sysupgrade = Get-Image 'sysupgrade' }
}

if ($DownloadOnly) {
    if ($Spec.images.initramfs) { Get-Image 'initramfs' | Out-Null }
    Ok "cached in $Dest"
    exit 0
}

if (-not $Spec.flasher) {
    Warn "there is no SSH flasher for $Model`: the documented route is UART + TFTP"
    Warn "images are cached in $Dest; see docs/models/ for the install route"
    exit 2
}

Write-Host ''
Say 'about to flash:'
Write-Host "      unit      ${Router} (stock) -> ${OpenWrt} (OpenWrt)"
Write-Host "      model     $Model"
Write-Host "      factory   $(Split-Path $Factory -Leaf)"
Write-Host "      sysupgrade $(Split-Path $Sysupgrade -Leaf)"
Write-Host ''
if (-not $Yes -and -not $DryRun) {
    Write-Host 'This overwrites the boot chain and cannot be undone over the network.'
    $answer = Read-Host "Type the model ($Model) to continue"
    if ($answer -ne $Model) { Die 'aborted' }
}

$onrouter = Join-Path (Join-Path $Here 'onrouter') "$Model.sh"
if (-not (Test-Path $onrouter)) { Die "missing $onrouter" }

# OpenWrt on 192.168.1.1 has just booted a fresh initramfs: it makes a new host
# key every time, and that address may already be in known_hosts from another
# unit. Stock units commonly reuse 192.168.31.1 too. Give both sides throwaway
# known_hosts files so stale keys from other routers cannot block this run.
$stockKh = $null
$owrtKh = $null
$finalKh = $null
$sshErr = $null
$stockOpts = @('-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=10')
$scpOpts = @('-O', '-o', 'StrictHostKeyChecking=accept-new')
$owrtOpts = @()
$finalOpts = @()
if (-not $DryRun) {
    $stockKh = [System.IO.Path]::GetTempFileName()
    $owrtKh = [System.IO.Path]::GetTempFileName()
    $finalKh = [System.IO.Path]::GetTempFileName()
    $sshErr = [System.IO.Path]::GetTempFileName()
    $stockOpts += @('-o', "UserKnownHostsFile=$stockKh")
    $scpOpts += @('-o', "UserKnownHostsFile=$stockKh")
    $owrtOpts = @('-o', 'StrictHostKeyChecking=accept-new',
                  '-o', "UserKnownHostsFile=$owrtKh",
                  '-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=5')
    $finalOpts = @('-o', 'StrictHostKeyChecking=accept-new',
                   '-o', "UserKnownHostsFile=$finalKh",
                   '-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=5')
}
$stockIdentity = @()
if ($Key) {
    if (-not (Test-Path $Key)) { Die "no SSH key at $Key" }
    $stockIdentity = @('-i', $Key, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes')
    $stockOpts += $stockIdentity
    $scpOpts += $stockIdentity
}
$owrtScpOpts = @('-O', '-o', 'StrictHostKeyChecking=accept-new',
                 '-o', "UserKnownHostsFile=$owrtKh",
                 '-o', 'LogLevel=ERROR')
$mfgIdentityCommand = 'd=$(grep -i mfg /proc/mtd | head -n1 | cut -d: -f1); [ -n "$d" ] || exit 2; command -v sha256sum >/dev/null || exit 3; h=$(sha256sum "/dev/$d") || exit 4; printf "%s\n" "${h%% *}"'

# Native commands write to stderr as they go, and Windows PowerShell 5.1 turns a
# native stderr line into a terminating error while $ErrorActionPreference is
# Stop. It also strips embedded quotes from native command arguments. Send every
# remote shell command on stdin to `sh -s` so the router receives the command
# text intact. These helpers also keep native output out of the caller's status
# variable and return only the exit code where appropriate.
function Invoke-Ssh ($Options, $Target, $Command) {
    if ($DryRun) {
        $shown = if ($Options) { ($Options -join ' ') + ' ' } else { '' }
        Write-Host "    would run: ssh $shown$Target $Command"
        return 0
    }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Windows PowerShell 5.1 terminates native-pipeline strings with CRLF.
        # End the actual command with an explicit LF, then leave the automatic
        # CRLF on a harmless comment line so the router never sees a trailing CR.
        $payload = $Command + "`n#"
        $payload | & ssh @Options $Target 'sh -s' | Out-Host
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
}

function Test-Ssh ($Options, $Target, $ErrorFile, $Command = 'true') {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $payload = $Command + "`n#"
        $payload | & ssh @Options $Target 'sh -s' 2>$ErrorFile | Out-Null
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
}

function Read-SshText ($Options, $Target, $ErrorFile, $Command) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $payload = $Command + "`n#"
        $output = $payload | & ssh @Options $Target 'sh -s' 2>$ErrorFile
        $rc = $LASTEXITCODE
        return [pscustomobject]@{ ExitCode = $rc; Text = ($output -join "`n") }
    }
    finally { $ErrorActionPreference = $previous }
}

function Read-MfgIdentity ($Options, $Target, $ErrorFile) {
    $probe = Read-SshText $Options $Target $ErrorFile $mfgIdentityCommand
    if ($probe.ExitCode -ne 0) {
        Die "could not fingerprint $Target from its MFG partition"
    }
    $hash = ([string]$probe.Text).Trim().ToLowerInvariant()
    if ($hash -notmatch '^[0-9a-f]{64}$') {
        Die "$Target returned an invalid MFG fingerprint"
    }
    return $hash
}

function Invoke-Scp ($Options, $Source, $Destination) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & scp @Options $Source $Destination | Out-Host
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
}

try {
    # One command: unlock the unit here rather than making the user run
    # .\flash.ps1 unlock first. The unlocker prompts for the admin password.
    if ($DryRun) {
        Say "would check root SSH on $Router, unlocking it first if it does not answer"
    }
    else {
        Say "checking root SSH on $Router"
        if ((Test-Ssh $stockOpts "root@$Router" $sshErr 'cat /proc/mtd >/dev/null') -ne 0) {
            Warn 'no root SSH yet: unlocking the unit now (it asks for the admin password)'
            $unlocker = Join-Path (Split-Path $Here -Parent) 'flash.ps1'
            if (-not (Test-Path $unlocker)) { Die "this unit is locked and $unlocker is missing" }
            if (-not $Key) {
                Die 'automatic unlock on Windows needs an RSA key; pass -Key $HOME\.ssh\idu_rsa'
            }
            # A separate process: flash.ps1 calls exit, which would end this
            # script too if it were dot-sourced or invoked with &.
            $hostExe = (Get-Process -Id $PID).Path
            & $hostExe -NoProfile -File $unlocker unlock --router "https://$Router" --key $Key
            if ($LASTEXITCODE -ne 0) { Die 'the unlock failed; nothing was flashed' }
            if ((Test-Ssh $stockOpts "root@$Router" $sshErr 'cat /proc/mtd >/dev/null') -ne 0) {
                Die 'the unit unlocked, but root SSH still does not answer'
            }
        }
        Ok 'root SSH is live'
    }

    if ($DryRun) {
        Say "would verify the connected hardware model against $Model"
    }
    else {
        Say 'checking connected hardware model'
        $probe = Read-SshText $stockOpts "root@$Router" $sshErr 'cat /tmp/deviceModel 2>/dev/null'
        if ($probe.ExitCode -ne 0) {
            Die 'could not read /tmp/deviceModel; refusing to flash an unknown router'
        }
        $connected = ([string]$probe.Text).Trim()
        if (-not $connected) {
            Die 'could not read /tmp/deviceModel; refusing to flash an unknown router'
        }
        $aliases = @($Spec.aliases | ForEach-Object { [string]$_ })
        if ($aliases -notcontains $connected) {
            Die "connected router is $connected, but the selected image set is $Model"
        }
        Ok "connected hardware is $connected"
    }

    if ($DryRun) {
        Say "would fingerprint the stock router's MFG partition"
        $stockMfgHash = 'dry-run'
    }
    else {
        Say 'fingerprinting the stock router'
        $stockMfgHash = Read-MfgIdentity $stockOpts "root@$Router" $sshErr
        Ok 'captured the stock router identity'
    }

    Say 'uploading the factory image and the on-router script'
    Write-Host "    factory: /tmp/jidu-factory.ubi, script: /tmp/jidu-flash.sh"
    if ($DryRun) {
        Write-Host "    would run: scp $Factory root@${Router}:/tmp/jidu-factory.ubi"
        Write-Host "    would run: scp $onrouter root@${Router}:/tmp/jidu-flash.sh"
    }
    else {
        $rc = Invoke-Scp $scpOpts $Factory "root@${Router}:/tmp/jidu-factory.ubi"
        if ($rc -ne 0) { Die 'the image never reached the router, nothing was written' }
        $rc = Invoke-Scp $scpOpts $onrouter "root@${Router}:/tmp/jidu-flash.sh"
        if ($rc -ne 0) { Die 'the script never reached the router, nothing was written' }
    }

    Say 'writing the idle UBI slot (the unit reboots itself)'
    $rc = Invoke-Ssh $stockOpts "root@$Router" 'sh /tmp/jidu-flash.sh'
    # 255 means the unit dropped the connection as it rebooted, which is expected.
    if (-not $DryRun -and $rc -ne 0 -and $rc -ne 255) {
        Die "the slot was not written (exit $rc); the unit is still on stock firmware"
    }

    if ($DryRun) {
        Say "would wait for OpenWrt on $OpenWrt"
    }
    else {
        Say "waiting for OpenWrt on $OpenWrt (up to 3 minutes)"
        $sshed = $false
        $last = ''
        for ($i = 0; $i -lt 40; $i++) {
            # A fresh initramfs refuses connections until sshd starts, so a
            # failed probe is the normal case here, not an error to act on.
            if ((Test-Ssh $owrtOpts "root@$OpenWrt" $sshErr) -eq 0) { $sshed = $true; break }
            $last = Get-Content $sshErr -ErrorAction SilentlyContinue | Select-Object -Last 1
            Start-Sleep -Seconds 5
        }
        if (-not $sshed) {
            Bad "no SSH on $OpenWrt after 200s"
            if ($last) { Bad "last error: $last" }
            Die 'the unit may need UART recovery: docs/models/ and firmware/README.md'
        }
        Ok 'initramfs is up'

        $initramfsMfgHash = Read-MfgIdentity $owrtOpts "root@$OpenWrt" $sshErr
        if ($initramfsMfgHash -ne $stockMfgHash) {
            Die "OpenWrt at $OpenWrt is a different router; refusing to upload sysupgrade"
        }
        Ok 'initramfs belongs to the validated router'
    }

    Say 'uploading the permanent sysupgrade'
    if ($DryRun) {
        Write-Host "    would run: scp $Sysupgrade root@${OpenWrt}:/tmp/sysupgrade.bin"
    }
    else {
        $rc = Invoke-Scp $owrtScpOpts $Sysupgrade "root@${OpenWrt}:/tmp/sysupgrade.bin"
        if ($rc -ne 0) { Die 'the sysupgrade never reached the unit; it is still in initramfs' }
    }

    Say 'flashing it (sysupgrade -n, settings are not kept)'
    $rc = Invoke-Ssh $owrtOpts "root@$OpenWrt" 'sysupgrade -n /tmp/sysupgrade.bin'
    if (-not $DryRun -and $rc -ne 0 -and $rc -ne 255) {
        Die "sysupgrade refused the image (exit $rc); the unit is still in initramfs"
    }

    Write-Host ''
    if ($DryRun) {
        Say 'would reconnect and verify persistent OpenWrt on the same router'
        Warn 'dry run: nothing was downloaded, written or flashed'
    }
    else {
        Say "waiting for permanent OpenWrt on $OpenWrt (up to 3 minutes)"
        $permanent = $false
        for ($i = 0; $i -lt 40; $i++) {
            # A reconnect can briefly hit the initramfs before its reboot. Do
            # not pin that host key for the permanent system.
            [System.IO.File]::WriteAllText($finalKh, '')
            $probe = Read-SshText $finalOpts "root@$OpenWrt" $sshErr $mfgIdentityCommand
            if ($probe.ExitCode -eq 0) {
                $finalMfgHash = ([string]$probe.Text).Trim().ToLowerInvariant()
                if ($finalMfgHash -match '^[0-9a-f]{64}$') {
                    if ($finalMfgHash -ne $stockMfgHash) {
                        Die "OpenWrt at $OpenWrt is a different router after sysupgrade"
                    }
                    if ((Test-Ssh $finalOpts "root@$OpenWrt" $sshErr 'grep -Eq ''^overlayfs:/overlay / overlay '' /proc/mounts') -eq 0) {
                        $permanent = $true
                        break
                    }
                }
            }
            Start-Sleep -Seconds 5
        }
        if (-not $permanent) {
            Die 'permanent OpenWrt did not come up on the validated router after sysupgrade'
        }
        Ok "done. Permanent OpenWrt is up on the same router at http://$OpenWrt - LuCI, root, no password."
    }
}
finally {
    foreach ($tmp in @($stockKh, $owrtKh, $finalKh, $sshErr)) {
        if ($tmp -and (Test-Path $tmp)) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    }
}
