# Windows

Use **`flash.ps1`** — `flash.sh` is a bash script and will not run natively.
Every command in [the README](../README.md) works the same way; only the leading
`.\` differs. If you prefer bash, `flash.sh` runs in **Git Bash**, which uses the
Windows Python and the Windows network. **WSL2 is not suitable for `unlock` or
`backup`** by default; see [WSL and Git Bash](#wsl-and-git-bash).

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
.\flash.ps1 backup --key $HOME\.ssh\idu_rsa   # unlock + backup
```

If root SSH is already live on the unit (a `breeze` restore, a UART setup, or an
earlier unlock), `backup` uses that session and skips the web login, the
compatibility check and the unlock. No admin password is needed, and no key is
needed while root is passwordless.

Create the key first, as shown in [There is no `expect` on
Windows](#there-is-no-expect-on-windows); `backup` needs it to verify the login.

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

This applies to the web-API unlock path. When root SSH is already live, `backup`
drives that session, so a passwordless unit needs no key.

Use RSA: the stock Dropbear on these units rejects Ed25519.

On Windows, pass the key to `unlock` as well. The web-API injection itself needs
no key, but the persistence check is a scripted SSH login: without a key,
`unlock` can enable SSH and still report failure. Passing `--key` also installs
the public key on the router.

## Firewall and port 80

To unlock, the tool starts a small web server on your PC that the *router*
downloads the installer from. On the first unlock, Windows Firewall will ask for
permission — click **Allow** for **Private** networks (your home network;
*Public* is for cafés and similar).

If an unlock ends with *the router did not call back*, allow `python.exe` through
the firewall, or run PowerShell as administrator so the rule can be created.

If it says `cannot listen on port 80: permission denied`, run PowerShell as
Administrator and retry. If it says `already in use`, another program owns the
port — IIS and the *World Wide Web Publishing Service* are common holders:

```powershell
netstat -ano | findstr :80
```

A reboot clears a stuck holder.

The tool prints the address it expects the router to call:

```text
[*] Callback: http://192.168.31.51:80/ (the router fetches the installer here)
```

If that is not your LAN address (a VPN, Hyper-V or a second adapter can win the
route), pass the correct one:

```powershell
.\flash.ps1 --address 192.168.31.51 --key $HOME\.ssh\idu_rsa unlock
```

## WSL and Git Bash

**Git Bash** runs the Windows Python, so `flash.sh` works there normally.

**WSL2** is different. Its default NAT puts the distribution on a private
`172.16.0.0/12` network (`172.16`–`172.31`), while the router is on the Windows
LAN. The router cannot dial into the VM. When the router is outside that range,
`unlock` rejects the address before it starts the callback server, instead of
waiting for a callback that cannot arrive. Running as root inside WSL does not
fix the route. Use `flash.ps1` natively for `unlock` and `backup`. `detect` and
`check` are fine in WSL because they only make outbound requests.

If you need WSL2, enable mirrored networking in `%UserProfile%\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

Then run `wsl --shutdown`, reopen the distribution, and allow Python through
Windows Firewall. A port proxy plus `--address` with the Windows LAN address also
works, but has more moving parts.

## Single-dash options

PowerShell users can use single-dash forms (`-Router`, `-Password`, `-Key`,
`-Address`, `-Force` instead of `--router`, `--password`, `--key`, `--address`,
`--force`).
