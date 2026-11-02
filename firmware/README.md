# firmware — download and flash OpenWrt

Two scripts, one per platform, that fetch the right OpenWrt image for a JIDU
router, verify it, cache it, and flash it over the stock root shell.

```
firmware/
├── manifest.json      models, files, sha256, download URLs (the single source of truth)
├── fwflash.sh         macOS / Linux
├── fwflash.ps1        Windows
└── onrouter/          scripts uploaded to the stock unit and run there
    ├── 6101.sh
    ├── 6j01.sh
    └── 6j11.sh
```

## Use

```bash
./firmware/fwflash.sh 6101      # JIDU6101
./firmware/fwflash.sh 6j01      # JIDU6201 / 6401 / 6601 / 6701
./firmware/fwflash.sh 6j11      # JIDU6111 / 6411 / 6611 / 6811 / 6911
```

On Windows:

```powershell
.\firmware\fwflash.ps1 6101
.\firmware\fwflash.ps1 6j01
.\firmware\fwflash.ps1 6j11
```

The unit does not need to be unlocked first. If root SSH does not answer,
`fwflash` runs the same unlocker as `./flash.sh unlock` and asks for the router
admin password, then carries on with the flash. One command does both. A backup
is still worth taking — `./flash.sh backup` — because flashing is not reversible
over the network.

## What it actually does

1. Reads `manifest.json`, picks the images for that model.
2. Checks `firmware/downloads/<model>/`. A file that is already there **and
   matches its sha256** is reused, so the second run downloads nothing.
3. Downloads anything missing into that folder, verifies sha256, and deletes the
   partial file on failure.
4. Proves it can reach the unit over root SSH. If it cannot, it unlocks the unit
   first (`flash.sh unlock`, asking for the admin password) and checks again.
5. Uploads the factory image and `onrouter/<model>.sh` to the stock unit.
6. Runs the on-router script, which rewrites the idle UBI slot and reboots.
7. Waits for the OpenWrt initramfs on `192.168.1.1`, uploads the sysupgrade, and
   runs `sysupgrade -n`.

Images are stored inside the repo, in `firmware/downloads/<model>/`:

```
firmware/downloads/
├── 6j01/   factory.ubi, initramfs-kernel.bin, squashfs-sysupgrade.bin
├── 6101/   ...
└── 6j11/   ...
```

That folder is git-ignored, so a download never ends up in a commit. Keep it
around: the next run reuses it, and only the sha256 is checked — not the date.
Delete a file to force a fresh download, or move the whole folder to another
machine and the images travel with it.

Useful flags: `--download-only` (download and stop), `--dry-run` (print every
command), `--cache DIR` (store elsewhere), `--image PATH` (flash a local
sysupgrade instead), `--smallbuffers` (6J11 reduced-buffer build), `--yes`.

## 6101

JIDU6101 is automated over SSH. Its factory image wraps the official OpenWrt
25.12.6 JIDU6101 initramfs in the UBI layout expected by the stock boot chain.
The embedded device tree contains the fixed SPI-NAND pull-up/pull-down settings,
and both the temporary system and permanent sysupgrade identify as
`jiorouter_ax6000-jidu6101`, so no forced `sysupgrade -F` is needed.

`./flash.sh flash` detects 6101, unlocks root SSH if needed, backs up the stock
partitions, downloads and verifies the matching images, writes the `ubi2` spare
slot, then installs the official 25.12.6 sysupgrade. UART + TFTP remains the
recovery path.

## Where the images come from

| Model | Source | Note |
| --- | --- | --- |
| 6J01, 6101 | OpenWrt 25.12.6, `mediatek/filogic` | Official. Upstream ships `-initramfs-kernel.bin` and `-squashfs-sysupgrade.bin` only. |
| 6J01 / 6101 factory `.ubi` | project-packaged OpenWrt 25.12.6 initramfs | UBI wrapper uses the stock-compatible `kernel` volume layout; embedded payload is the fixed official 25.12.6 initramfs. SHA-256 is pinned in the manifest. |
| 6J11 | [`themayankraut/JIO-AX6000-6J11-OpenWRT-SSH` v1.0.0](https://github.com/themayankraut/JIO-AX6000-6J11-OpenWRT-SSH/releases/tag/v1.0.0) | OpenWrt has no `qualcommbe` target and no Jio profile, so this is a community build. Assets are byte-identical to that release. |

All files are mirrored as assets of the `fw-2026.10` release on this repo, so a
download cannot break because an upstream tag moved. The manifest pins both the
URL and the sha256.

### Rebuilding the MediaTek factory wrapper

OpenWrt 25.12.6 publishes the fixed `initramfs-kernel.bin`, but does not publish
the stock-compatible `initramfs-factory.ubi` artifact. `repack_factory.py`
reuses only the known-good UBI container layout and replaces the entire dynamic
`kernel` volume payload with the official fixed initramfs:

```bash
python3 firmware/repack_factory.py \
  old-factory.ubi \
  openwrt-25.12.6-...-initramfs-kernel.bin \
  openwrt-25.12.6-...-initramfs-factory.ubi
```

The resulting 6J01 and 6101 images keep the stock-compatible 128 KiB PEB / 2 KiB
I/O UBI layout while booting the official 25.12.6 FIT payload. The release
artifacts were verified by extracting the UBI volume back out and comparing it
byte-for-byte with the official initramfs, then checking the embedded DTB for
the fixed SPI-NAND pull-up/pull-down settings.

## Risk

Flashing replaces the boot chain on hardware with a signed stock bootloader. A
failed write means UART recovery at best. Back the unit up first, and read the
per-model page in `docs/models/` before running anything.

Only use this on equipment you own or are explicitly authorised to test. Provided
as is, without warranty, without liability — see the [LICENSE](../LICENSE).
