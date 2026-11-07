# Troubleshooting

Work through this list before opening an issue. It covers almost every failure we
have seen.

## Before anything else

Two conditions cause most failures:

1. **The router must be fully set up.** A factory-reset unit accepts the login but
   keeps its whole web API locked until its setup wizard has been completed in the
   browser. Reset it, finish the wizard, then retry.
2. **Only one admin session may exist.** The tool takes a sitting one over rather
   than waiting for it, so this normally looks after itself — see below.

The router also temporarily blocks logins after roughly five wrong passwords.
Verify the password instead of retrying blindly.

---

<details>
<summary><strong>Another admin session is already open</strong></summary>

The tool answers `ERR_LOGIN_DUPLICATE_ADMIN` by **taking the sitting session
over** — the way the vendor's own web UI does — and says
`[*] another admin session is open - taking it over`. That does log the other
session out, so save anything you had open in the router web UI first.

If you see it fall back to the retry loop instead, the refusal arrived without a
`loggedId` to take over, so waiting is all that is left. Logging out of the web
UI will not help on units where the slot never expires (a `6j11`, for one) —
reboot the router, or run with `--patience` and let it wait.

</details>

<details>
<summary><strong>The router is factory-reset</strong></summary>

Complete the setup wizard in a browser first, then return. Until it is finished,
the API the tool needs stays locked.

</details>

<details>
<summary><strong>Wrong password / logins blocked</strong></summary>

The router locks out after ~5 failures. Wait, then double-check the password.

</details>

<details>
<summary><strong><code>check</code> reports NO</strong></summary>

`NO` means the firmware is outside the vulnerable range — not that the router is
unreachable. There are two cases:

- **Older than `R2.0.19` (MediaTek):** the build has no password-history hash at
  all. The API still accepts a password change, but no shell evaluates it, which
  is why a run can look successful and produce no callback.
- **`R3.2.3` or newer (MediaTek):** the vendor replaced the shell-out with
  `luci.sys.user.setpasswd`.

`unlock` refuses before sending a payload. On builds where the web UI still has
**Backup Settings** and **Restore Settings**, use the offline
[`breeze` configuration-backup route](BREEZE.md) instead:

```bash
./flash.sh breeze ~/Downloads/YOUR_BACKUP_FILE
```

It works on both families and needs no network route into the router. Restore
the modified file, enable Dual WAN once to start Dropbear, then run
`./flash.sh backup`. If the web UI has no restore page, the UART/u-boot console
is the fallback.

`NO` is a verdict about `changeUserPassword`, not a security audit of the
firmware. `--force` is not a fix for a genuinely fixed build. It only helps when
the version table is wrong about a hybrid build, and the runtime probe still
warns when no history appears. `check` exits `2` for `NO`, so scripts can test
it.

</details>

<details>
<summary><strong><code>check</code> reports TEST</strong></summary>

`TEST` means the version is in a window where the answer is not known: the
password-history feature may or may not be present. It is not a failure.

`unlock` decides at runtime by changing the guest password once and looking for
a new history entry. If none appears, it stops with *this build does not record
password history* and sends no payload. The guest password is now a random value;
the admin password is untouched.

The windows are MediaTek `R2.0.19.0`–`R2.0.19.5` and `R3.2.1`–`R3.2.2`, and
Qualcomm `R3.2.7` and newer. See
[INTERNALS.md](INTERNALS.md#firmware-compatibility).

If you are testing a hybrid build on purpose, `--force` skips the version-based
refusal; the probe still runs, but only warns.

</details>

<details>
<summary><strong>Cannot listen on port 80: permission denied or address in use</strong></summary>

The callback server must own port 80. The error tells you which failure it is:

- **Permission denied on Linux, macOS, or WSL:** port 80 is privileged, so
  binding it needs root. Re-run with `sudo`:

  ```bash
  sudo ./flash.sh unlock
  ```

  On Linux, you can instead allow unprivileged low ports for the current boot,
  which keeps the backup files owned by you:

  ```bash
  sudo sysctl net.ipv4.ip_unprivileged_port_start=80
  ```

  That sysctl is Linux-only; on macOS, use `sudo`.

- **Address already in use:** something else holds port 80. Find it with
  `sudo lsof -nP -iTCP:80 -sTCP:LISTEN` on macOS/Linux, or
  `netstat -ano | findstr :80` on Windows. Stop that service, or reboot if it is
  stuck.

On Windows, a refused bind is often an HTTP.sys reservation rather than a real
listener. Run PowerShell as Administrator and retry.

</details>

<details>
<summary><strong>WSL: the callback address starts with 172.</strong></summary>

WSL2's default NAT puts the Linux distribution on a private `172.16.0.0/12`
network (`172.16`–`172.31`), which the router usually cannot dial. If the router
is outside that range, `unlock` rejects the address before starting the callback
server. Running as root inside WSL fixes the port-80 permission but not the
route.

Use `.\flash.ps1` natively on Windows (recommended), or Git Bash with the Windows
Python. If you need WSL, enable mirrored networking in
`%UserProfile%\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

Then run `wsl --shutdown`, reopen the distribution, and allow Python through
Windows Firewall. A port proxy plus `--address` with the Windows LAN address also
works, but is more moving parts.

</details>

<details>
<summary><strong>The router did not call back / nothing arrives at the callback</strong></summary>

The tool prints the exact URL first:

```text
[*] Callback: http://192.168.31.51:80/ (the router fetches the installer here)
```

Test it from a phone or another computer on the same Wi-Fi: open that URL in a
browser. You should see the installer script as plain text, starting with
`#!/bin/sh`. If that works, the server and firewall are fine and the problem is
the router side.

If it does not:

- allow `python.exe` through the firewall (on Windows, **Private** networks), or
  run PowerShell as administrator so the rule can be created;
- check that the address is on the router's subnet. A VPN or a second network
  card can make the automatic choice wrong; pass the LAN address explicitly:

  ```bash
  ./flash.sh --address 192.168.31.51 backup
  ```

- confirm both devices are on the same network and that guest Wi-Fi isolation is
  not separating them.

If the tool says the router **accepted the payloads but never fetched** the URL,
that only means the callback did not arrive. It does not prove whether the shell
evaluated them: an executed fetch can still fail on routing or firewall rules,
so finish the reachability checks above. Separately, on a build where `check`
reports `NO`, `unlock` stops before sending a payload unless `--force` was used;
a forced run can accept payloads that cannot execute — see *`check` reports NO*
above.

</details>

<details>
<summary><strong>Permission denied running <code>./flash.sh</code></strong></summary>

ZIP downloads drop the executable bit. Run this once inside the folder:

```bash
chmod +x flash.sh idu.py
```

</details>

<details>
<summary><strong>Windows: running scripts is disabled</strong></summary>

Permit scripts for the current window only, then retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This expires when the window closes and changes nothing permanently.

</details>

<details>
<summary><strong>Windows: ssh is not recognized</strong></summary>

Install the OpenSSH Client — see [WINDOWS.md](WINDOWS.md).

</details>

<details>
<summary><strong>SSH refused after a reboot</strong></summary>

The persistence step did not land. Check for the marker on the device:

```bash
ssh root@192.168.31.1 'ls -l /etc/rc.d/S99idu-ssh'
```

If it is missing, run `./flash.sh unlock` again (on Windows,
`.\flash.ps1 unlock --key $HOME\.ssh\idu_rsa`) and watch for
`[+] SSH persistence enabled` in the output. If that line says the persistence is
*missing* instead, follow the by-hand recipe it prints.

</details>

<details>
<summary><strong>SSH warns that the host key changed</strong></summary>

Expected. The unlock starts dropbear with `-R`, which regenerates the router's
host keys on every boot and every unlock, so `192.168.31.1` presents a different
fingerprint each time.

Clear the stale entry and reconnect:

```bash
ssh-keygen -R 192.168.31.1
ssh root@192.168.31.1
```

Note that a changed host key is normally the thing you should *stop* and think
about — it is what a man-in-the-middle looks like. It is benign here only because
you were the one who just replaced sshd on the device.

</details>

<details>
<summary><strong>Can I back up before unlocking?</strong></summary>

Not unless root SSH is already enabled, for example through UART. The backup
reads `/dev/mtd*` over SSH as root, and `flash.sh backup` runs `unlock` first;
`unlock` uses the existing SSH login if it finds one.

On an early build where `unlock` cannot work, the web-UI configuration backup is
still enough to get root SSH first: download it, rebuild it with
`./flash.sh breeze`, restore it, and then run `./flash.sh backup`. See
[BREEZE.md](BREEZE.md). If the web UI has no restore page, the UART/u-boot
console is the fallback. Do not install OpenWrt first and plan to back up
afterwards; the stock image is gone by then.

</details>

<details>
<summary><strong>Backup folder is very large</strong></summary>

Expected. Every partition is imaged; `mtd5` and `mtd6` alone are roughly 140 MB and
90 MB. `--full-chip` adds more. See [BACKUP.md](BACKUP.md).

</details>

<details>
<summary><strong>Everything else</strong></summary>

Re-run with `--verbose` (or `-v`) — that prints the per-command detail behind each
method, including why a payload was refused:

```bash
./flash.sh --verbose unlock
```
</details>
