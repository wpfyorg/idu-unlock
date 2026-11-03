# Jio AirFiber IDU Unlock & JIDU OpenWrt

Unlock root SSH, back up the stock firmware, download verified images, and
install OpenWrt on supported **Jio AirFiber IDU / JIDU AX6000 routers**.

`idu-unlock` is a network-based Jio AirFiber IDU unlock and OpenWrt toolkit. It
can identify the router, check firmware compatibility, enable persistent
**Jio IDU root SSH**, save the factory data and flash partitions, and install
**JIDU OpenWrt** on supported models without opening the router.

`./flash.sh` is the main entry point. It can detect the router, check the
firmware, unlock root SSH, make a backup, download the right OpenWrt images,
or run the complete OpenWrt install:

```bash
./flash.sh detect
./flash.sh check
./flash.sh unlock
./flash.sh backup
./flash.sh download
./flash.sh flash
```

`./flash.sh flash` detects the model, unlocks root SSH if needed, saves a stock
backup, downloads and verifies the matching images, asks for a model
confirmation, and then starts writing OpenWrt. JIDU6101 uses its own matching
factory stage, so it follows the same two-stage flow as the other 6J01 models.

## Demo

[▶ Watch the full unlock + OpenWrt flash demo](docs/assets/idu-unlock-cli-demo.mp4)

The demo shows the end-to-end CLI flow: compatibility check, root SSH unlock,
persistent SSH setup, stock backup, verified OpenWrt image download, factory
image flash, initramfs boot, and permanent sysupgrade.

> [!IMPORTANT]
> **Use the e-waste you already have at home.** This project exists to give an
> unused Jio IDU a second life, not to create a buy/sell market around unlocked
> routers. Please do not buy hardware just to flip it at a markup.

> [!NOTE]
> **Want the technical disclosure?** For Jio, researchers, or anyone curious
> about why the unlock works, the
> [Jio AirFiber whitepaper](https://github.com/wpfyorg/jio-airfiber-whitepaper)
> documents the stock `changeUserPassword` command injection, affected builds,
> the fixed builds, and the reasoning behind publishing it.

> [!WARNING]
> Use this only on hardware you own or have explicit permission to modify.
> Unlocking may void a warranty or breach your service terms, and replacing
> firmware can brick the device. This project is provided without warranty.

The normal flow is:

```text
Jio stock firmware
        |
        v
Check compatibility
        |
        v
Unlock root SSH
        |
        v
Back up factory data + flash partitions
        |
        v
Install OpenWrt (optional)
```

Everything runs over the network. For supported firmware, you do not need to
open the router, solder anything, or connect a serial cable just to get root
SSH and make a backup.

## What this project does

`idu-unlock` can:

- identify the JIDU model and hardware family;
- check whether the stock firmware is likely to be unlockable;
- enable persistent root SSH;
- save factory credentials, bootloader data, and flash partitions;
- download and verify the correct OpenWrt images;
- automatically flash supported models over SSH.

It does **not** remove a SIM/network lock, change IMEI/operator settings, or
bypass a forgotten router-admin password.

## Supported models

| Model | Family | Root SSH + backup | Automated OpenWrt install |
| --- | --- | :---: | :---: |
| JIDU6101 | MediaTek `6j01` | Yes | Yes |
| JIDU6201 | MediaTek `6j01` | Yes | Yes |
| JIDU6401 | MediaTek `6j01` | Yes | Yes |
| JIDU6601 | MediaTek `6j01` | Yes | Yes |
| JIDU6701 | MediaTek `6j01` | Yes | Yes |
| JIDU6111 | Qualcomm `6j11` | Yes | Yes |
| JIDU6411 | Qualcomm `6j11` | Yes | Yes |
| JIDU6611 | Qualcomm `6j11` | Yes | Yes |
| JIDU6811 | Qualcomm `6j11` | Yes | Yes |
| JIDU6911 | Qualcomm `6j11` | Yes | Yes |

Not sure which model you have?

```bash
./flash.sh detect
```

Windows:

```powershell
.\flash.ps1 detect
```

Per-model notes are in [docs/models](docs/models/README.md).

## Quick start

You need the router admin password that was set during the normal Jio setup
wizard. The router must already be set up; a factory-reset unit keeps the API
locked until setup is completed.

### macOS / Linux

```bash
git clone https://github.com/wpfyorg/idu-unlock.git
cd idu-unlock
chmod +x flash.sh firmware/fwflash.sh

./flash.sh check
./flash.sh backup
./flash.sh download     # optional: cache + verify the OpenWrt images
# ./flash.sh flash      # destructive: backup, then install OpenWrt
```

`backup` checks the router, unlocks root SSH if needed, and then saves the
backup in the current directory. `download` only caches verified firmware;
`flash` performs the complete install after making a fresh backup on models
with an automated SSH flash path.

On macOS and Linux, unlocking uses a temporary HTTP callback on port 80. If the
script says it cannot bind that port, run the command with `sudo`:

```bash
sudo ./flash.sh backup
```

On Linux you can instead allow unprivileged programs to use low ports for the
current boot:

```bash
sudo sysctl net.ipv4.ip_unprivileged_port_start=80
./flash.sh backup
```

### Windows

```powershell
git clone https://github.com/wpfyorg/idu-unlock.git
cd idu-unlock

.\flash.ps1 check
ssh-keygen -t rsa -b 2048 -f $HOME\.ssh\idu_rsa
.\flash.ps1 backup --key $HOME\.ssh\idu_rsa
```

Windows needs an RSA key for the scripted SSH verification step. Create it once
as shown above and reuse it for `unlock` and `backup`.

Windows Firewall must allow Python to receive the router's callback. If Windows
refuses port 80, run PowerShell as Administrator.

WSL2's normal NAT setup cannot receive this callback reliably, so use
`flash.ps1` from Windows instead of running `flash.sh` inside WSL2.

More Windows notes: [docs/WINDOWS.md](docs/WINDOWS.md).

## Main commands

| Command | What it does | Changes the router? |
| --- | --- | :---: |
| `./flash.sh detect` | Show model and hardware family | No |
| `./flash.sh check` | Check firmware compatibility | No |
| `./flash.sh unlock` | Enable persistent root SSH | Yes |
| `./flash.sh backup` | Unlock if needed, then save a device backup | Yes |
| `./flash.sh download` | Detect the model, download and verify its OpenWrt images | No firmware writes |
| `./flash.sh flash` | Detect, unlock, back up, download, verify, and install OpenWrt | Yes — destructive |
| `./flash.sh` | Same as `backup` | Yes |

On Windows, `.\flash.ps1` handles detect/check/unlock/backup. OpenWrt download
and flashing use `.\firmware\fwflash.ps1` directly.

Common options:

```text
--router URL       Router URL. Default: https://192.168.31.1
--password PW      Router admin password. Prompted if omitted.
--key PATH         Existing RSA private key to install for root SSH.
--address IP       Local IPv4 address used for the router callback.
--force            Try the unlock even when the version check says NO.
-v, --verbose      Show more detail.
```

The launchers create a local Python virtual environment and install the required
Python packages on first run if needed.

## Checking firmware compatibility

Run:

```bash
./flash.sh check
```

The result is one of three states:

- `YES` — this firmware is in a range known to work;
- `TEST` — the exact build is not confirmed, so the unlocker will verify the
  vulnerable behavior before sending the real payload;
- `NO` — the known `changeUserPassword` route is closed on this build.

Current compatibility knowledge:

| Family | Firmware | Result |
| --- | --- | :---: |
| MediaTek `6j01` | `R2.0.18.x` and older | `NO` |
| MediaTek `6j01` | `R2.0.19.0`–`R2.0.19.5` | `TEST` |
| MediaTek `6j01` | `R2.0.19.6`–`R3.2.0` | `YES` |
| MediaTek `6j01` | `R3.2.1`–`R3.2.2` | `TEST` |
| MediaTek `6j01` | `R3.2.3` and newer | `NO` |
| Qualcomm `6j11` | `R3.2.6` and earlier | `YES`* |
| Qualcomm `6j11` | `R3.2.7` and newer | `TEST` |

\* `6j11` has confirmed working units through `R3.2.6`. Very old releases may
predate the password-history behavior, so the runtime probe is still the final
check.

The version table is only a first filter. During `unlock`, the tool makes one
normal password change on the **guest account** and checks whether the expected
password-history entry appears. If it does not, the script stops before sending
the exploit payload. The admin account is not changed.

`--force` skips the version-based refusal, but the runtime probe still runs and
prints a warning if the expected behavior is missing.

Technical details are in
[docs/INTERNALS.md](docs/INTERNALS.md#firmware-compatibility).

## Unlock root SSH

```bash
./flash.sh unlock
```

The script logs into the router's web API, uses the vulnerable password-history
code path to run a small installer as root, starts Dropbear on port 22, and adds
a startup script so SSH returns after reboot.

If you already have root SSH, the script detects it and does not try the exploit
again.

### SSH without a key

If you do not pass `--key`, root SSH is left with an empty password:

```bash
ssh root@192.168.31.1
```

Press Enter when SSH asks for the password.

### SSH with a key

Create an RSA key first:

```bash
ssh-keygen -t rsa -b 2048 -f ~/.ssh/idu_rsa
```

Then unlock with it:

```bash
./flash.sh unlock --key ~/.ssh/idu_rsa
```

Connect with:

```bash
ssh -i ~/.ssh/idu_rsa -o IdentitiesOnly=yes root@192.168.31.1
```

The stock Dropbear build on these routers may reject Ed25519 keys, so RSA is the
safe choice.

The router can generate a new SSH host key when Dropbear restarts. If your SSH
client reports a changed host key after a reboot, see
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Make a backup

Run this before flashing OpenWrt:

```bash
./flash.sh backup
```

The wrapper unlocks the router first if necessary, then saves a directory named
after the router's Wi-Fi network. A typical backup looks like this:

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

The default backup skips `mtd0`, the full SPI-chip image. The lower-level Python
command supports `--full-chip` if you specifically need it.

> [!IMPORTANT]
> The backup contains sensitive device data: Wi-Fi passwords, factory
> credentials, serial information, bootloader data, and raw flash partitions.
> Keep it private. Do not upload it to GitHub or share it publicly.

More detail: [docs/BACKUP.md](docs/BACKUP.md).

## Install OpenWrt

On macOS/Linux, the normal path is one command:

```bash
./flash.sh flash
```

That command detects the model, enables root SSH if needed, creates the stock
backup, downloads and verifies the correct images, then hands off to the
firmware installer. If you only want the files, run `./flash.sh download`.

Windows uses the lower-level firmware launcher directly:

```powershell
# JIDU6101
.\firmware\fwflash.ps1 6101 -Key $HOME\.ssh\idu_rsa
# JIDU6201 / 6401 / 6601 / 6701
.\firmware\fwflash.ps1 6j01 -Key $HOME\.ssh\idu_rsa
# JIDU6111 / 6411 / 6611 / 6811 / 6911
.\firmware\fwflash.ps1 6j11 -Key $HOME\.ssh\idu_rsa
```

The lower-level `firmware/fwflash.*` tools still work directly on every
platform. They check root SSH and run the repo unlocker automatically if the
stock unit is still locked.

Before anything is written, the flasher shows the model and image names and asks
you to type the model name as confirmation.

JIDU6101 uses a JIDU6101-specific 25.12.6 factory stage followed by the
official JIDU6101 sysupgrade. Both stages identify as
`jiorouter_ax6000-jidu6101`, so normal `sysupgrade -n` works without `-F`.
The factory stage contains the same fixed 25.12.6 initramfs payload as the
official image, including the September 2026 SPI-NAND pinctrl fix.

### Useful firmware options

```text
--download-only       Download and verify images, then stop.
--dry-run             Show what would happen without downloading or flashing.
--cache DIR           Store downloaded images somewhere else.
--image PATH          Use a local sysupgrade image.
--image-sha256 HASH   Verify a local image against a hash you provide.
--smallbuffers        6J11 only: use the reduced-buffer sysupgrade build.
--yes                 Skip the typed model confirmation.
-v, --verbose         Show more detail.
```

Downloaded files are cached under `firmware/downloads/<model>/`. Every cached
file is checked against the SHA-256 in `firmware/manifest.json` before use. A
bad or partial download is refused.

The automated flash flow is:

1. Pick the images from `firmware/manifest.json`.
2. Download anything missing and verify SHA-256.
3. Check root SSH, unlocking the stock firmware if needed.
4. Upload the factory image and the matching on-router flashing script.
5. Write the idle UBI slot and reboot into OpenWrt initramfs.
6. Wait for OpenWrt at `192.168.1.1`.
7. Upload the sysupgrade image and run `sysupgrade -n`.

After a successful install, OpenWrt comes up at:

```text
http://192.168.1.1
```

The fresh image uses the normal OpenWrt initial state: root account with no
password until you set one.

Read [firmware/README.md](firmware/README.md) for image provenance, cache
behavior, and recovery notes. The longer manual guide is in
[OPENWRT.md](OPENWRT.md).

## Where the OpenWrt images come from

The firmware manifest is the source of truth for filenames, download URLs,
sizes, and SHA-256 hashes.

- **6J01 / 6101 sysupgrade and initramfs:** official OpenWrt 25.12.6
  `mediatek/filogic` builds.
- **6J01 / 6101 factory UBI:** project-packaged UBI wrappers around the official
  OpenWrt 25.12.6 initramfs payloads. The payloads include the JioRouter
  SPI-NAND fix; filenames, sizes, and SHA-256 hashes are pinned in the manifest.
- **6J11:** community builds from
  [themayankraut/JIO-AX6000-6J11-OpenWRT-SSH](https://github.com/themayankraut/JIO-AX6000-6J11-OpenWRT-SSH).

The project release mirrors the files used by the manifest so a moved upstream
asset does not silently change what the script downloads.

## Requirements

For unlock and backup:

- Python 3;
- network access to the router;
- an SSH client;
- port 80 available on the computer running the unlock;
- the router admin password.

macOS/Linux password-based SSH automation uses `expect`. If it is missing,
install it with your package manager or use an SSH key. Windows should use an
RSA key because `expect` is not available there.

For OpenWrt flashing, the shell script also needs standard tools such as `ssh`,
`scp`, `curl` or `wget`, and `sha256sum` or `shasum`.

## Common problems

**The router cannot be detected**

Make sure you can open `https://192.168.31.1`, finish the setup wizard, and use
the correct admin password. The router allows only one admin session at a time,
so log out of the web UI before running the tool if needed.

**I entered the wrong password several times**

The stock firmware can temporarily block logins after roughly five failed
attempts. Stop retrying and wait for the lockout to clear.

**The router never calls back during unlock**

A firewall, VPN, multiple network interfaces, or the wrong source address can
block the callback. Use `--address <your-LAN-IP>` when automatic detection picks
the wrong interface.

**Port 80 is already in use**

Stop the program using it, or use the platform-specific advice in the Quick
start section.

**`check` says `NO`**

The known network exploit is closed on that firmware. If the unit already has
root SSH from another route, backup still works. Otherwise use the UART/u-boot
route documented for the model.

More fixes: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Project layout

```text
README.md                  this guide
flash.sh                   macOS / Linux unlock + backup launcher
flash.ps1                  Windows unlock + backup launcher
idu.py                     core unlock, compatibility, SSH, and backup engine
OPENWRT.md                 detailed/manual OpenWrt guide

docs/
  BACKUP.md                backup contents and restore notes
  INTERNALS.md             exploit and compatibility internals
  TROUBLESHOOTING.md       common failures and fixes
  WINDOWS.md               Windows-specific setup
  models/                  per-model OpenWrt notes

firmware/
  fwflash.sh               macOS / Linux OpenWrt installer
  fwflash.ps1              Windows OpenWrt installer
  manifest.json            image metadata, URLs, sizes, SHA-256
  onrouter/                scripts run on the stock router during flashing
  downloads/               verified image cache (git-ignored)

requirements.txt           Python dependencies
tests/                     automated tests
```

## Safety notes

A few rules are worth following every time:

1. Run `./flash.sh check` before relying on the network unlock.
2. Run `./flash.sh backup` before flashing.
3. Keep the backup somewhere private and off the router.
4. Do not interrupt power while flash is being written.
5. Keep the per-model UART recovery guide available before installing OpenWrt.

If the stock network route is unavailable or a flash fails, UART/TFTP may be the
only recovery path.

## Legal

This project is intended for security research and modification of hardware you
own or are explicitly authorized to test.

It is provided **as-is and without warranty**. The authors and contributors are
not responsible for hardware damage, data loss, service interruption, warranty
loss, contractual issues, or other consequences resulting from its use.

The project is independent and is not affiliated with or endorsed by Jio,
router manufacturers, carriers, OpenWrt, or other vendors mentioned here.

## License

Licensed under **PolyForm Noncommercial 1.0.0** with the project's attribution
requirements. Commercial use is not granted.

See [LICENSE](LICENSE) for the complete terms.

## Credits

The router research and tooling in this repository are implemented
independently.

Thanks to **AK Sharma** for identifying and fixing two `/WCGI` authentication
quirks while working on a JIDU6611: an invalid cookie path that caused Python
`requests` to discard the session cookie, and a persistent admin session that
could block a new login.

Thanks to **Cyborg**, [**DIY Daddy**](https://github.com/the-diy-daddy/6j01_6j11),
and [**Mayank Raut**](https://github.com/themayankraut/JIO-AX6000-6J11-OpenWRT-SSH)
for sharing their Jio router flashing work and resources.

If this project helped you, consider starring the repository.
