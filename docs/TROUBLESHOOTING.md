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
<summary><strong><code>check</code> reports TEST</strong></summary>

`check` reports `TEST` for `R3.2.1` or newer firmware. That is not a failure — but
do not expect `unlock` to succeed either. This tool's only method is
`changeUserPassword`, and that handler is **fixed as of `R3.2.3`**: the vendor
replaced its unescaped shell-out with `luci.sys.user.setpasswd`.

So on `R3.2.3` and newer, expect `unlock` to fail with the password method.
`detect` and `backup` still work, and the backup is worth taking either way.
Whether `R3.2.1` or `R3.2.2` still unlocks has not been determined — see
[INTERNALS.md](INTERNALS.md#firmware-compatibility).

</details>

<details>
<summary><strong>The router did not call back / nothing arrives at the callback</strong></summary>

The router has to fetch the installer from your machine, so your machine must be
reachable from the router on port 80 and on the router's subnet.

Check:

- your local firewall — on Windows, allow `python.exe` (Private networks), or run
  PowerShell as administrator so the rule can be created
- that port 80 is free — IIS and the *World Wide Web Publishing Service* are
  common holders:

  ```powershell
  netstat -ano | findstr :80
  ```

  A reboot clears a stuck holder.
- that both devices are on the same network

Alternatively, `flash.sh` runs unchanged under **WSL** or **Git Bash**.

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

If it is missing, run `./flash.sh unlock` again (or `.\flash.ps1 unlock`) and watch
for `[+] SSH persistence enabled` in the output — if that line says the
persistence is *missing* instead, follow the by-hand recipe it prints.

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
