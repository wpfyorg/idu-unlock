# 🚀 Jio AirFiber IDU Unlock and OpenWrt Guide

A complete, beginner-friendly walkthrough to unlock a **Jio AirFiber IDU / JIDU AX6000 router**, keep persistent root SSH, save a full device backup, and install OpenWrt — all over the network, without opening the case or soldering a UART header.

`./flash.sh` is the entry point for detect, check, unlock, and backup. `./flash.sh flash` is the one that downloads verified images and installs OpenWrt.

> [!IMPORTANT]
> **Use the e-waste you already have at home.** This project exists to give an unused Jio IDU a second life, not to create a buy/sell market around unlocked routers. Please do not buy hardware just to flip it at a markup.

> [!WARNING]
> Use this only on hardware you own or have explicit permission to modify. Unlocking may void a warranty or breach your service terms, and replacing firmware can brick the device. This project is provided without warranty.

---

## 📺 Supported Devices and Firmware

| Router Model | Hardware Family | Root SSH + Backup | Automated OpenWrt Install |
| :--- | :--- | :---: | :---: |
| **JIDU6101** | MediaTek `6j01` | Verified | Verified |
| **JIDU6201** | MediaTek `6j01` | Verified | Verified |
| **JIDU6401** | MediaTek `6j01` | Verified | Verified |
| **JIDU6601** | MediaTek `6j01` | Verified | Verified |
| **JIDU6701** | MediaTek `6j01` | Verified | Verified |
| **JIDU6111** | Qualcomm `6j11` | Verified | Verified |
| **JIDU6411** | Qualcomm `6j11` | Verified | Verified |
| **JIDU6611** | Qualcomm `6j11` | Verified | Verified |
| **JIDU6711** | Qualcomm `6j11` | Verified | Verified |
| **JIDU6811** | Qualcomm `6j11` | Verified | Verified |
| **JIDU6911** | Qualcomm `6j11` | Verified | Verified |

> [!NOTE]
> **JIDU6711:** root SSH, backup, and the OpenWrt install are verified on this model. It uses the same `6j11` community image set as its siblings.

Not sure which model is sitting under your desk?

```bash
./flash.sh detect
```

Per-model notes live in [docs/models](docs/models/README.md).

### ✨ What This Unlock Does

- **Detects the model and hardware family:** tells you which install path applies before anything is changed.
- **Checks firmware compatibility:** `check` reports whether an injection route is present.
- **Enables persistent root SSH:** survives reboots, not just the current session.
- **Saves factory credentials and the flash partitions:** an imaged backup you can restore from. The default skips `mtd0`, the full SPI-chip image.
- **Rebuilds a web-UI config backup offline:** for early builds where the live API route is closed.
- **Downloads and verifies OpenWrt images:** every file is SHA-256 checked against a pinned manifest.
- **Installs OpenWrt automatically:** two-stage flash over SSH, no serial console needed.
- **Never needs the router to reach the internet:** the exploit callback is on your own LAN.

It does **not** remove a SIM/network lock, change IMEI or operator settings, or recover a forgotten router-admin password.

---

## 🧰 Main Commands

| Command | What It Does | Changes the Router? |
| :--- | :--- | :---: |
| **`./flash.sh detect`** | Show model and hardware family | No |
| **`./flash.sh check`** | Check firmware compatibility, read-only | No |
| **`./flash.sh unlock`** | Enable persistent root SSH | Yes |
| **`./flash.sh backup`** | Unlock if needed, then save a device backup | Yes |
| **`./flash.sh download`** | Detect the model, download and verify its OpenWrt images | No firmware writes |
| **`./flash.sh flash`** | Detect, unlock, back up, download, verify, install OpenWrt | Yes — destructive |
| **`./flash.sh`** | Same as `backup` | Yes |
| **`./flash.sh breeze FILE`** | Offline: rebuild a web-UI config backup with root SSH | File only |

On Windows, `.\flash.ps1` handles detect/check/unlock/backup. OpenWrt download and flashing use `.\firmware\fwflash.ps1` directly.

---

## 🌐 Critical Rules (Read First!)

### 1. The Same Network Rule

Your computer and the router **must be on the same L2 network and subnet**. During `unlock`, the router fetches a small installer script from your machine on port 80. If traffic has to cross a NAT, a guest network, or a second router's firewall, the callback never arrives.

- Connect both the PC and the router to the same switch or Wi-Fi.
- Turn **off** AP isolation / client isolation on the network you use.
- If you run a second router behind the Jio gateway, put it in **Access Point (AP) mode** so everything shares one IP pool.

### 2. Port 80 Must Be Free

The unlock serves one installer over HTTP and then shuts the listener down. On macOS/Linux, binding port 80 needs `sudo` unless unprivileged low ports are enabled for the current boot:

```bash
sudo ./flash.sh backup
```

```bash
# Linux alternative: allow low ports for this boot only
sudo sysctl net.ipv4.ip_unprivileged_port_start=80
```

### 3. The Router Must Be Set Up, Not Factory-Fresh

A factory-reset JIDU accepts the login but keeps its whole API locked (`ERR_POSTLOGIN_FACTORY_RESET`) until the setup wizard is finished in the web UI. If your router is already in that state, complete the wizard (which sets the admin password), then hand that password to this tool. Do not reset a configured router to reach this step.

### 4. One Admin Session at a Time

The stock firmware allows a single admin session. Log out of the web UI before running the tool, or the login can be refused.

### 5. The Firmware Window Decides the Route

There are **two** independent command-injection routes in the stock web API. `unlock` tries them in order and stops at the first one that lands:

1. **`changeUserPassword`** — the original bug. Live on older builds, patched on newer ones.
2. **`setDosPreventions`** — the DoS-prevention settings. Still live on builds where the password route is closed.

You do not choose between them; `check` and `unlock` work it out.

### 6. Keep the Backup Private

The saved backup contains Wi-Fi passwords, factory credentials, serial information, bootloader data, and raw flash partitions. Never upload it to GitHub or share it.

---

## 🛠️ Step 0: Requirements

Install these before starting:

1. **Python 3** — the launchers create a local virtual environment and install Python dependencies on first run.
2. **An SSH client** — `ssh`, `scp`, and `ssh-keygen`.
3. **Network access to the router** — the default management URL is `https://192.168.31.1`.
4. **Port 80 available** on your computer for the unlock callback.
5. **The router admin password** set during the Jio setup wizard.

For password-based SSH automation on macOS/Linux, the tool uses `expect`. If it is missing, install it with your package manager, or unlock with an SSH key instead. Windows has no `expect`, so use an RSA key there.

For OpenWrt flashing, the shell wrappers also need standard tools such as `ssh`, `scp`, `curl` or `wget`, and `sha256sum` or `shasum`.

---

## ⚡ Step 1: Get the Tool

### macOS / Linux

```bash
git clone https://github.com/wpfyorg/idu-unlock.git
cd idu-unlock
chmod +x flash.sh firmware/fwflash.sh
```

### Windows

```powershell
git clone https://github.com/wpfyorg/idu-unlock.git
cd idu-unlock
```

Windows Firewall must allow Python to receive the router's callback. If Windows refuses port 80, run PowerShell as Administrator.

> [!WARNING]
> **Do not run this inside WSL2.** WSL2's default NAT cannot receive the router's callback reliably. Use `.\flash.ps1` from Windows itself. More notes: [docs/WINDOWS.md](docs/WINDOWS.md).

---

## 🔍 Step 2: Detect and Check

Read-only, nothing is changed:

```bash
./flash.sh check
```

`check` returns one of three states:

| State | Meaning |
| :--- | :--- |
| **`YES`** | At least one injection route is registered on this build. `unlock` confirms it live. |
| **`TEST`** | No route is confirmed for this exact build. `unlock` probes the API before sending any payload. |
| **`NO`** | Neither the password-history route nor the DoS route is available. |

### 📋 Password-Route Compatibility

The version table below is a first filter for the **`changeUserPassword`** route only. The DoS route is detected live and is not tied to these ranges.

| Family | Firmware | Password Route |
| :--- | :--- | :---: |
| MediaTek `6j01` | `R2.0.18.x` and older | Closed — predates password history |
| MediaTek `6j01` | `R2.0.19.0` – `R2.0.19.5` | Unconfirmed — runtime probe decides |
| MediaTek `6j01` | `R2.0.19.6` – `R3.2.0` | Open |
| MediaTek `6j01` | `R3.2.1` – `R3.2.2` | Unconfirmed — runtime probe decides |
| MediaTek `6j01` | `R3.2.3` and newer | Closed — fixed to `luci.sys.user.setpasswd` |
| Qualcomm `6j11` | `R3.2.6` and earlier | Open* |
| Qualcomm `6j11` | `R3.2.7` and newer | Unconfirmed — runtime probe decides |

\* `6j11` has confirmed working units through `R3.2.6`. Very old releases may predate the password-history behavior, so the runtime probe is still the final check.

### 🧪 What `unlock` Does When the Password Route Is Unconfirmed

No rootfs between `R2.0.19.0` and `R2.0.19.6` has been read, so the version table cannot settle that window. `check` reports `YES` when `getDosPreventions` answers, because the DoS route is available, and `TEST` otherwise. Either way, `./flash.sh unlock` checks the password route live before sending a password payload:

1. it changes the guest password once to a random value;
2. if the guest's `passwdHistory` gains an entry, the vulnerable shell-out is present and the normal password payloads are sent;
3. if no entry appears, the password route stops there. When the DoS route is available, `unlock` still sends its payload afterwards — that request changes the DoS-prevention settings, which are put back best-effort, and can start SSH and install persistence.

The admin password is never changed, and the guest password is simply random now. `--force` makes step 3 send the password payloads anyway; they are inert on a build without the shell-out.

The DoS fallback is not a free pass: it writes the DoS-prevention settings and may leave them changed if the restore call fails. Check those settings in the router web UI after any unlock.

### 🛡️ The Second Route: `setDosPreventions`

Where the password route has been patched, the same web API still copies the DoS-prevention `icmpControl` field into an `iptables` command without validation. That field has no length limit and no character filter, so it can carry the whole installer in one shot.

`check` reads `getDosPreventions` to see whether the DoS setters are registered, and `unlock` uses that route automatically when the password route refuses. After the payload returns, `unlock` sends a second request to put the prior DoS settings back. That restore is best-effort: a failure is reported as a warning, and the settings can remain changed. Verify DoS prevention in the router web UI after an unlock.

---

## 🔓 Step 3: Unlock Root SSH

```bash
./flash.sh unlock
```

The tool logs into the router's web API, runs a small installer as root through whichever injection route lands, starts Dropbear on port 22, and installs a startup script so SSH returns after a reboot.

If root SSH is already reachable, the script detects it and does not try the exploit again.

> [!NOTE]
> **Why a callback at all?** The caps on the password field are tight (32 characters), so the installer cannot be inlined there. The router fetches it from your machine over the LAN instead. The DoS field is uncapped, but the same installer is used for both routes so there is one source of truth.

### 🔑 SSH Without a Key

If you do not pass `--key`, root SSH is left with an empty password:

```bash
ssh root@192.168.31.1
```

Press Enter when SSH asks for the password.

### 🔐 SSH With a Key

Create an RSA key first:

```bash
ssh-keygen -t rsa -b 2048 -f ~/.ssh/idu_rsa
```

Then unlock with it:

```bash
./flash.sh unlock --key ~/.ssh/idu_rsa
```

> [!WARNING]
> A new unlock clears root's password whether or not `--key` is supplied. The key is an extra way in, not a replacement: until you set a password or install a key, anyone on the LAN can sign in as root. Run `passwd` over SSH when you are done, or keep the router on a trusted network. If you still need the wrappers afterwards, pass `--key` — they sign in with a key or an empty password, not one you set by hand.

Connect with:

```bash
ssh -i ~/.ssh/idu_rsa -o IdentitiesOnly=yes root@192.168.31.1
```

> [!TIP]
> The stock Dropbear build on these routers may reject Ed25519 keys, so RSA is the safe choice. On Windows, create the key once with `ssh-keygen -t rsa -b 2048 -f $HOME\.ssh\idu_rsa` and reuse it for `unlock` and `backup`.

The router can generate a new SSH host key when Dropbear restarts. If your client reports a changed host key after a reboot, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## 💾 Step 4: Make a Backup

Run this before flashing OpenWrt:

```bash
./flash.sh backup
```

The wrapper unlocks the router first if necessary, then saves a directory named after the router's Wi-Fi network. A typical backup looks like this:

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

The default backup skips `mtd0`, the full SPI-chip image. The lower-level Python command supports `--full-chip` if you specifically need it.

> [!IMPORTANT]
> The backup contains sensitive device data: Wi-Fi passwords, factory credentials, serial information, bootloader data, and raw flash partitions. Keep it private. Do not upload it to GitHub or share it publicly.

More detail: [docs/BACKUP.md](docs/BACKUP.md).

---

## 🧯 If the API Route Is Closed: Offline Breeze

A `NO` does not always mean UART. If the web UI still offers **Backup Settings** and **Restore Settings**, rebuild a config backup with root SSH inside it — fully offline:

```bash
./flash.sh breeze ~/Downloads/YOUR_BACKUP_FILE
```

Run it with `--key` if you intend to continue with the wrappers:

```bash
./flash.sh breeze ~/Downloads/YOUR_BACKUP_FILE --key ~/.ssh/idu_rsa
```

It decrypts the stock configuration backup, installs your public key (or sets a root password when no key is passed), adds persistent Dropbear startup hooks, and re-encrypts the result as `encrypted_backup_mod.tar.gz`.

Then:

1. restore that file in the router web UI;
2. enable Dual WAN once if the build needs it to start SSH;
3. continue with `./flash.sh backup --key ~/.ssh/idu_rsa` or `./flash.sh flash --key ~/.ssh/idu_rsa`.

> [!IMPORTANT]
> Without `--key`, `breeze` sets a root password, and the wrappers authenticate with a key or an empty password — not that password. Either rebuild the backup with `--key`, or sign in to the router yourself with the password you set.

This is the same approach as the community [`breeze.sh`](https://github.com/abhigyan17/Airfiber_Unlock/blob/main/scripts/breeze.sh), built into this project. It never contacts the router and does not use the web API injection, so it also covers Qualcomm `6j11` units on early builds where the runtime probe reports no password history.

Full walkthrough: [docs/BREEZE.md](docs/BREEZE.md).

---

## 📦 Step 5: Install OpenWrt

On macOS/Linux, the normal path is one command:

```bash
./flash.sh flash
```

That command detects the model, enables root SSH if needed, creates the stock backup, downloads and verifies the correct images, then hands off to the firmware installer. If you only want the files, run `./flash.sh download`.

Windows uses the lower-level firmware launcher directly:

```powershell
# JIDU6101
.\firmware\fwflash.ps1 6101 -Key $HOME\.ssh\idu_rsa
# JIDU6201 / 6401 / 6601 / 6701
.\firmware\fwflash.ps1 6j01 -Key $HOME\.ssh\idu_rsa
# JIDU6111 / 6411 / 6611 / 6811 / 6911
.\firmware\fwflash.ps1 6j11 -Key $HOME\.ssh\idu_rsa
```

The lower-level `firmware/fwflash.*` tools work directly on every platform. They check root SSH and run the repo unlocker automatically if the stock unit is still locked.

Before anything is written, the flasher shows the model and image names and asks you to type the model name as confirmation.

### 🔬 JIDU6101 Firmware Detail

JIDU6101 uses a JIDU6101-specific 25.12.6 factory stage followed by the official JIDU6101 sysupgrade. Both stages identify as `jiorouter_ax6000-jidu6101`, so normal `sysupgrade -n` works without `-F`. The factory stage contains the same fixed 25.12.6 initramfs payload as the official image, including the September 2026 SPI-NAND pinctrl fix.

### ⚙️ Useful Firmware Options

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

Downloaded files are cached under `firmware/downloads/<model>/`. Every cached file is checked against the SHA-256 in `firmware/manifest.json` before use. A bad or partial download is refused.

### 🔄 The Automated Flash Flow

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

The fresh image uses the normal OpenWrt initial state: a root account with no password until you set one.

Read [firmware/README.md](firmware/README.md) for image provenance, cache behavior, and recovery notes. The longer manual guide is in [OPENWRT.md](OPENWRT.md).

### 🏭 Where the Images Come From

The firmware manifest is the source of truth for filenames, download URLs, sizes, and SHA-256 hashes.

- **6J01 / 6101 sysupgrade and initramfs:** official OpenWrt 25.12.6 `mediatek/filogic` builds.
- **6J01 / 6101 factory UBI:** project-packaged UBI wrappers around the official OpenWrt 25.12.6 initramfs payloads. The payloads include the JioRouter SPI-NAND fix; filenames, sizes, and hashes are pinned in the manifest.
- **6J11:** community builds from [themayankraut/JIO-AX6000-6J11-OpenWRT-SSH](https://github.com/themayankraut/JIO-AX6000-6J11-OpenWRT-SSH).

The project release mirrors the files used by the manifest, so a moved upstream asset cannot silently change what the script downloads.

---

## 🛠️ Full Command Options

```text
--router URL       Router URL. Default: https://192.168.31.1
--password PW      Router admin password. Prompted if omitted.
--key PATH         Existing RSA private key to install for root SSH. With
                   breeze, its .pub is installed in the modified backup.
--root-password PW breeze only: root password to set. Prompted if omitted.
--out PATH         breeze only: output file. Default: encrypted_backup_mod.tar.gz
--address IP       Local IPv4 address used for the router callback.
--force            Try the unlock even when the version check says NO. With
                   breeze, replace an existing output file.
-v, --verbose      Show more detail.
```

---

## 🔧 Troubleshooting and Issue Fixes

### 1. The Router Cannot Be Detected

- **Symptoms:** `detect` or `check` times out or reports an unreachable API.
- **Cause:** wrong URL, wrong password, a factory-reset unit, or another admin session still holding the login.
- **Fix:** open `https://192.168.31.1` in a browser, finish the setup wizard, log out, then re-run. Verify the URL with `--router` if the unit uses a different address.

### 2. Too Many Wrong Passwords

- **Symptoms:** login starts failing even with the correct password.
- **Cause:** the stock firmware temporarily blocks logins after roughly five failed attempts.
- **Fix:** stop retrying and wait for the lockout to clear. Do not script a retry loop against the login.

### 3. The Router Never Calls Back During Unlock

- **Symptoms:** the unlock starts and waits, then reports that the callback never arrived.
- **Cause:** a firewall, VPN, multiple network interfaces, AP isolation, or the wrong source address.
- **Fix:** use `--address <your-LAN-IP>` when automatic detection picks the wrong interface. Turn off the VPN, check that both devices share a subnet, and allow Python through the local firewall.

### 4. Port 80 Is Already in Use

- **Symptoms:** the unlock refuses to start with a bind error.
- **Cause:** another web server or a stale process owns port 80.
- **Fix:** stop the program using it, or follow the platform advice in Critical Rules above.

### 5. `check` Says `NO`

- **Symptoms:** neither route is reported as available.
- **Cause:** the build has both the password shell-out fixed and the DoS setters removed.
- **Fix:** if the unit already has root SSH from another route, backup still works. Otherwise use `breeze` when the web UI offers Backup and Restore, or the UART/u-boot route documented for the model.

### 6. SSH Host Key Changed After a Reboot

- **Symptoms:** `ssh` refuses to connect and warns about a changed host key.
- **Cause:** Dropbear generated a new host key when it restarted.
- **Fix:** remove the stale entry with `ssh-keygen -R 192.168.31.1`, then reconnect.

### 7. Password Automation Fails on macOS/Linux

- **Symptoms:** the script cannot sign in for the post-unlock check.
- **Cause:** `expect` is missing.
- **Fix:** install `expect`, or pass `--key` so the tool uses your RSA key instead of a password.

More fixes: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## 🔒 Golden Rules (Must Read!)

1. **Back up before you flash.** A verified stock backup is the difference between a bad flash and a brick.
2. **Never interrupt power while a partition is being written.** Wait for the tool to finish and reboot on its own.
3. **One route is enough.** If `unlock` succeeds over the DoS route, do not re-run it with `--force` "just to be sure".
4. **Same subnet, no VPN.** The callback is a LAN connection, not an internet one.
5. **Keep the backup off the router and out of git.** It contains credentials and raw flash data.
6. **Know your recovery path.** Read the per-model UART/TFTP notes before installing OpenWrt, not after.

---

## 🗂️ Project Layout

```text
README.md                  this guide
flash.sh                   macOS / Linux unlock + backup launcher
flash.ps1                  Windows unlock + backup launcher
idu.py                     core unlock, compatibility, SSH, and backup engine
OPENWRT.md                 detailed/manual OpenWrt guide

docs/
  BACKUP.md                backup contents and restore notes
  BREEZE.md                offline configuration-backup route
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

app/                       Android companion build
tests/                     automated tests
```

---

## ⚖️ Legal

This project is intended for security research and modification of hardware you own or are explicitly authorized to test.

It is provided **as-is and without warranty**. The authors and contributors are not responsible for hardware damage, data loss, service interruption, warranty loss, contractual issues, or other consequences resulting from its use.

The project is independent and is not affiliated with or endorsed by Jio, router manufacturers, carriers, OpenWrt, or other vendors mentioned here.

### 📄 License

Licensed under **PolyForm Noncommercial 1.0.0** with the project's attribution requirements. Commercial use is not granted.

See [LICENSE](LICENSE) for the complete terms.

---

## 🌟 Credits

The router research and tooling in this repository are implemented independently.

Thanks to **AK Sharma** for identifying and fixing two `/WCGI` authentication quirks while working on a JIDU6611: an invalid cookie path that caused Python `requests` to discard the session cookie, and a persistent admin session that could block a new login.

Thanks to **Cyborg**, [**DIY Daddy**](https://github.com/the-diy-daddy/6j01_6j11), and [**Mayank Raut**](https://github.com/themayankraut/JIO-AX6000-6J11-OpenWRT-SSH) for sharing their Jio router flashing work and resources.

Technical disclosure for researchers: the [Jio AirFiber whitepaper](https://github.com/wpfyorg/jio-airfiber-whitepaper) documents the stock API command injection, affected builds, the fixed builds, and the reasoning behind publishing it.

If this project helped you, consider starring the repository.
