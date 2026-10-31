#!/usr/bin/env pwsh
<#
fwflash.ps1 - fetch and flash an OpenWrt image for a JIDU router, on Windows.

  .\fwflash.ps1 6j01                 flash a JIDU6J01 over stock root SSH
  .\fwflash.ps1 6j11                 flash a JIDU6J11 over stock root SSH
  .\fwflash.ps1 6j11 -Smallbuffers   ...using the reduced-buffer sysupgrade build
  .\fwflash.ps1 6j01 -DownloadOnly   cache the images, flash nothing
  .\fwflash.ps1 6101                 downloads only: no SSH flasher for 6101

Options:
  -Router HOST     stock unit address (default 192.168.31.1)
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

The router must already have root SSH. Get that with .\flash.ps1 unlock (or the
password trick documented upstream). Back the unit up before flashing: this
writes over the boot chain and is not reversible over the network.

Only run against equipment you own or are explicitly authorised to test.
Provided as is, without warranty, without liability - see the README.
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet('6j01', '6j11', '6101')]
    [string]$Model,

    [string]$Router = '192.168.31.1',
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
    Get-Content $PSCommandPath | Select-Object -Skip 1 -First 27 |
        ForEach-Object { $_ -replace '^# ?', '' }
    exit ([int](-not $Model))
}

if (-not $Cache) { $Cache = Join-Path $Here 'downloads' }

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
    exit 0
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

$stockOpts = @('-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=10')
$scpOpts = @('-O', '-o', 'StrictHostKeyChecking=accept-new')

# OpenWrt on 192.168.1.1 has just booted a fresh initramfs: it makes a new host
# key every time, and that address may already be in known_hosts from another
# unit. Give it a throwaway known_hosts file so a stale key cannot block it.
$owrtKh = $null
$sshErr = $null
$owrtOpts = @()
if (-not $DryRun) {
    $owrtKh = [System.IO.Path]::GetTempFileName()
    $sshErr = [System.IO.Path]::GetTempFileName()
    $owrtOpts = @('-o', 'StrictHostKeyChecking=accept-new',
                  '-o', "UserKnownHostsFile=$owrtKh",
                  '-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=5')
}
$owrtScpOpts = @('-O', '-o', 'StrictHostKeyChecking=accept-new',
                 '-o', "UserKnownHostsFile=$owrtKh",
                 '-o', 'LogLevel=ERROR')

# Native commands write to stderr as they go, and Windows PowerShell 5.1 turns a
# native stderr line into a terminating error while $ErrorActionPreference is
# Stop. Every ssh and scp call goes through these three helpers: they relax the
# preference for the duration, send output to the console rather than the
# pipeline, and return nothing but the exit code - so a caller comparing $rc
# always compares a number, not an array of output lines plus a number.
function Invoke-Ssh ($Options, $Target, $Command) {
    if ($DryRun) {
        $shown = if ($Options) { ($Options -join ' ') + ' ' } else { '' }
        Write-Host "    would run: ssh $shown$Target $Command"
        return 0
    }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & ssh @Options $Target $Command | Out-Host
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
}

function Test-Ssh ($Options, $Target, $ErrorFile, $Command = 'true') {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & ssh @Options $Target $Command 2>$ErrorFile | Out-Null
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
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
    if ($DryRun) {
        Say "would check root SSH on $Router"
    }
    else {
        Say "checking root SSH on $Router"
        $rc = Test-Ssh $stockOpts "root@$Router" $sshErr 'cat /proc/mtd >/dev/null>'
        if ($rc -ne 0) {
            Bad "no root SSH on $Router"
            Die 'unlock first: .\flash.ps1 unlock  (and run .\flash.ps1 backup)'
        }
        Ok 'root SSH is live'
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
        Warn 'dry run: nothing was downloaded, written or flashed'
    }
    else {
        Ok "done. The unit reboots into OpenWrt at http://$OpenWrt - LuCI, root, no password."
        Write-Host '    If it does not come back, recovery is UART + TFTP: docs/models/ and firmware/README.md'
    }
}
finally {
    foreach ($tmp in @($owrtKh, $sshErr)) {
        if ($tmp -and (Test-Path $tmp)) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    }
}
