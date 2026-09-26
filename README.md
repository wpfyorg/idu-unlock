# idu-unlock

**Unlock and back up Jio AirFiber routers.**

Get persistent root SSH and take complete flash backups for supported `6j01` and
`6j11` models.

`idu-unlock` uses the router's own web interface to:

- enable **persistent root SSH**
- back up **every flash partition**
- save factory credentials and environment data
- identify the router model and hardware family

Supports **macOS, Linux, and Windows**.

> [!WARNING]
> Use this only on hardware you own or have explicit permission to modify.
> Unlocking or replacing firmware may void warranties, violate service terms, or brick the device.
> This project is provided without warranty.

---

## Supported routers

| Family          | Models                                | Unlock | Backup |
| --------------- | ------------------------------------- | :----: | :----: |
| MediaTek `6j01` | JIDU 6101 / 6201 / 6401 / 6601 / 6701 |    ✅   |    ✅   |
| Qualcomm `6j11` | JIDU 6111 / 6411 / 6611 / 6811 / 6911 |    ✅   |    ✅   |

Not sure which one you have?

```bash
./flash.sh detect
```

Or on Windows:

```powershell
.\flash.ps1 detect
```

Firmware matters. This tool has exactly one method, `changeUserPassword`, so the
verdict is about that handler:

- **`R3.2.0` and earlier** — the check reports `YES`; the password field is
  injectable.
- **`R3.2.1` and newer** — the check reports `TEST`. Do not expect much: the
  handler is **fixed as of `R3.2.3`**, so `unlock` cannot work on that build or
  newer — `detect` and `backup` still do. Which release between `R3.2.1` and
  `R3.2.3` carries the fix is not known. See
  [docs/INTERNALS.md](docs/INTERNALS.md#firmware-compatibility).

---

## Quick start

### macOS / Linux

```bash
git clone https://github.com/wpfyorg/idu-unlock.git
cd idu-unlock
chmod +x flash.sh idu.py

./flash.sh check
./flash.sh backup
```

### Windows

```powershell
git clone https://github.com/wpfyorg/idu-unlock.git
cd idu-unlock

.\flash.ps1 check
.\flash.ps1 backup
```

The launcher creates a local Python environment and installs its dependencies
automatically. See [docs/WINDOWS.md](docs/WINDOWS.md) for the Windows specifics.

---

## Commands

| Command             | What it does                      | Router modified? |
| ------------------- | --------------------------------- | :--------------: |
| `./flash.sh detect` | Detect model and hardware family  |        No        |
| `./flash.sh check`  | Check firmware/API compatibility  |        No        |
| `./flash.sh unlock` | Enable persistent root SSH        |        Yes       |
| `./flash.sh backup` | Unlock + create a complete backup |        Yes       |
| `./flash.sh`        | Unlock + backup                   |        Yes       |

Windows users can replace `./flash.sh` with `.\flash.ps1`.

### Options

```text
--router URL       Router address
                   default: https://192.168.31.1

--password PW      Router admin password
                   prompted securely when omitted

--key PATH         SSH key. Optional — with no key, root is left passwordless
                   and nothing of ours is installed on the router

-v, --verbose      Show the per-command detail behind each method
```

Nothing is ever generated for you: with no `--key`, no keypair is created and
none is left behind on the router. In PowerShell, single-dash forms
(`-Router`, `-Password`, `-Key`) also work.

---

## Unlock

```bash
./flash.sh unlock
```

Typical output, when a key is passed with `--key ~/.ssh/idu_rsa`:

```text
Router admin password:

[*] Connecting to 192.168.31.1
[+] Device: JIDU6101 (Arcadyan / MTK)
[+] Family: mediatek

[*] Unlocking...
    Method 1/1: success

[+] Root SSH enabled
    ssh -i ~/.ssh/idu_rsa -o IdentitiesOnly=yes root@192.168.31.1
[*] Router reported:
    id: uid=0(root) gid=0(root)
    key: 1 line(s)
    persist: K01idu-ssh S99idu-ssh
    sshd: 1
[+] SSH persistence enabled
```

With no `--key`, the hint is `ssh root@192.168.31.1` — root is left passwordless,
so you just press Enter at the password prompt.

**Step by step:**

0. **Prepare.** Open a terminal in the project folder. If you are logged in to the
   router's web page, expect to be logged out — it permits only one admin session,
   and the tool takes a sitting one over rather than waiting for it.
1. **Identify** (read-only): `./flash.sh detect`.
2. **Back up** (do not skip) — see [Backup](#backup) below.
3. **Connect** with the `ssh` command printed at the end. The unlock also
   installs a startup script, so SSH survives reboots.

The router temporarily blocks logins after roughly five wrong passwords. If it
rejects yours, verify the password rather than retrying.

---

## Backup

```bash
./flash.sh backup
```

The tool unlocks the router if necessary, then writes a directory named after the
router's Wi-Fi network:

```text
AirFiber-XXXXXX/
├── credentials.txt
├── uboot_credentials.env
├── partitions.txt
├── uboot_env.txt
├── factory_env.txt
└── backup/
    ├── mtd1_BL2.bin
    ├── mtd5_ubi.bin
    └── ...
```

> [!IMPORTANT]
> Treat the backup directory like a password or private key.
> **Do not upload it to GitHub or share it publicly.**

See [docs/BACKUP.md](docs/BACKUP.md) for what each file holds, expected sizes, and
how to restore a single partition.

---

## SSH access

After unlocking, with a key:

```bash
ssh -i ~/.ssh/idu_rsa -o IdentitiesOnly=yes root@192.168.31.1
```

or, without one:

```bash
ssh root@192.168.31.1        # no password — just press Enter
```

If you do use a key, make it RSA: the stock Dropbear on these routers rejects
Ed25519.

Because the unlock starts dropbear with `-R`, the router regenerates its host keys
on every boot and every unlock — so SSH will warn that the host key changed. That
is expected here. See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## OpenWrt

`idu-unlock` itself **does not write firmware**. It gets the router to the useful
starting point:

```text
Stock firmware
      │
      ▼
Root SSH
      │
      ▼
Full backup
      │
      ▼
Ready for OpenWrt
```

OpenWrt installation is documented separately:

**[Installing OpenWrt →](OPENWRT.md)**

Read that guide completely before flashing anything. The procedure differs by
family: `6j01` installs over SSH, while `6j11` needs UART + U-Boot.

---

## Requirements

The router must be powered on, reachable, and **fully set up** — setup wizard
completed and an admin password configured. A factory-reset unit keeps its web
API locked until the wizard is finished.

Your computer needs:

- **Python 3** — macOS: `xcode-select --install`; Linux: your package manager;
  Windows: `winget install Python.Python.3.12` (tick *Add python.exe to PATH*)
- an **SSH client**, and network access to the router
- **Linux only:** `expect` (`sudo apt install expect`). macOS includes it. It is
  what lets the tool drive password-based SSH; without it, pass `--key`.

---

## Project layout

```text
README.md            this file
OPENWRT.md           OpenWrt installation guide
docs/
  BACKUP.md          what a backup contains
  INTERNALS.md       how the unlock works
  TROUBLESHOOTING.md problems and fixes
  WINDOWS.md         Windows specifics
flash.sh             macOS / Linux launcher
flash.ps1            Windows PowerShell launcher
idu.py               core engine used by both launchers
requirements.txt     Python dependencies
tests/               tests
```

---

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

---

## Safety

Before doing anything beyond unlocking:

```bash
./flash.sh backup
```

Keep that backup somewhere safe. If you plan to install OpenWrt, having the
original partitions matters — they hold device-specific factory data that cannot
necessarily be recreated later, and they are the only way back if a flash goes
wrong.

---

## Legal

This project is intended for security research and modification of hardware you
own or are explicitly authorized to test.

It is provided **as-is and without warranty**. The authors and contributors are
not responsible for hardware damage, data loss, service interruption, warranty
loss, contractual issues, or other consequences resulting from its use.

The project is independent and is not affiliated with or endorsed by Jio,
Skyworth, router manufacturers, carriers, or other vendors mentioned here.

Product and company names are used only for identification.

<details>
<summary>Full disclaimer</summary>

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
>   supported by any manufacturer, carrier, or vendor.
> - **Rights-holder requests are welcome.** If you hold rights in something you
>   believe this project touches, say so via this repository's issues and it
>   will be dealt with promptly — including removal of anything that should not
>   be here.
> - **No support, and no promised outcome.** It is shared for security research
>   and personal use.
>
> By downloading, running, or otherwise using any part of this project, you
> accept these terms. If you do not accept them, do not use it.

</details>

---

## License

Licensed under **PolyForm Noncommercial 1.0.0** with the project's attribution
requirements.

Commercial use is not granted. You may use, modify, and share this project for
noncommercial purposes — but not sell it, resell it, or ship it inside a
commercial product or service. If you publish a video, stream, or tutorial
featuring this project, credit it and link back to this repository.

See [LICENSE](LICENSE) for the complete terms. That makes this project
*source-available*, not open source in the OSI sense.

---

## Credits

The router research and tooling in this repository are implemented independently.

Thanks to **AK Sharma**, who found and fixed two `/WCGI` authentication quirks
that stall a run — the session cookie is set with a `path` that is not a legal
cookie path, so `requests` throws it away, and a sitting admin session never
expires on a `6j11` unit, so waiting for it cannot work. Both fixes are in
`idu.py`, and they came out of rooting a JIDU6611.

The community OpenWrt flashing procedure documented in [OPENWRT.md](OPENWRT.md)
builds on work by:

**[the-diy-daddy/6j01_6j11](https://github.com/the-diy-daddy/6j01_6j11)**

If this project helped you, consider starring the repository ⭐
