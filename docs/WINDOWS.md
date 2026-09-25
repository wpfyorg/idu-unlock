# Windows

Use **`flash.ps1`** — `flash.sh` is a bash script and will not run natively.
Every command in [the README](../README.md) works the same way; only the leading
`.\` differs. If you prefer bash, `flash.sh` runs unchanged under **WSL** or
**Git Bash**.

## One-time setup

1. **Python 3**

   ```powershell
   winget install Python.Python.3.12
   ```

   Tick *Add python.exe to PATH* if the installer offers it, then reopen
   PowerShell.

   If `python` prints *Python was not found* from the Microsoft Store, Python is
   installed but the Store's `python.exe` / `python3.exe` **App execution aliases**
   are shadowing it. Turn both off in **Settings → Apps → Advanced app settings →
   App execution aliases**, or just let the tool use the `py` launcher, which it
   prefers automatically.

2. **OpenSSH Client**

   Check with `ssh -V`. If it is unrecognised, open PowerShell **as administrator**
   and run:

   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
   ```

## Running the tool

```powershell
.\flash.ps1 check      # read-only compatibility check
.\flash.ps1 backup     # unlock + backup
```

The leading `.\` is required — PowerShell does not run scripts from the current
folder by name alone.

If it reports *running scripts is disabled on this system*, permit scripts for the
current window only and retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This expires when the window closes and changes nothing permanently.

## There is no `expect` on Windows

The unlock leaves root passwordless. Signing in to that account automatically is
driven by `expect` on macOS and Linux, and Windows has no `expect` — so any step
that needs a *scripted* SSH login (`backup`, and the persistence check) requires a
key. Create one once and pass it:

```powershell
ssh-keygen -t rsa -b 2048 -f $HOME\.ssh\idu_rsa
.\flash.ps1 backup --key $HOME\.ssh\idu_rsa
```

`unlock` itself needs no key: it is pure web-API injection.

## Firewall and port 80

To unlock, the tool starts a small web server on your PC that the *router*
downloads the installer from. On the first unlock, Windows Firewall will ask for
permission — click **Allow** for **Private** networks (your home network;
*Public* is for cafés and similar).

If an unlock ends with *the router did not call back*, allow `python.exe` through
the firewall, or run PowerShell as administrator so the rule can be created. If
another program already occupies port 80 (IIS and the *World Wide Web Publishing
Service* are common), check with:

```powershell
netstat -ano | findstr :80
```

A reboot clears a stuck holder.

## Single-dash options

PowerShell users can use single-dash forms (`-Router`, `-Password`, `-Key`
instead of `--router`, `--password`, `--key`).
