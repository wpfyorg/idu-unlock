# firmware — download and flash OpenWrt

Two scripts, one per platform, that fetch the right OpenWrt image for a JIDU
router, verify it, cache it, and flash it over the stock root shell.

```
firmware/
├── manifest.json      models, files, sha256, download URLs (the single source of truth)
├── fwflash.sh         macOS / Linux
├── fwflash.ps1        Windows
└── onrouter/          scripts uploaded to the stock unit and run there
    ├── 6j01.sh
    └── 6j11.sh
```

## Use

```bash
./firmware/fwflash.sh 6j01      # JIDU6201 / 6401 / 6601 / 6701
./firmware/fwflash.sh 6j11      # JIDU6111 / 6411 / 6611 / 6811 / 6911
```

On Windows:

```powershell
.\firmware\fwflash.ps1 6j01
.\firmware\fwflash.ps1 6j11
```

The router needs root SSH first — `./flash.sh unlock`, then `./flash.sh backup`.
`fwflash` does not unlock anything and does not take a router password.

## What it actually does

1. Reads `manifest.json`, picks the images for that model.
2. Checks `firmware/downloads/<model>/`. A file that is already there **and
   matches its sha256** is reused, so the second run downloads nothing.
3. Downloads anything missing into that folder, verifies sha256, and deletes the
   partial file on failure.
4. Uploads the factory image and `onrouter/<model>.sh` to the stock unit.
5. Runs the on-router script, which rewrites the idle UBI slot and reboots.
6. Waits for the OpenWrt initramfs on `192.168.1.1`, uploads the sysupgrade, and
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

There is no SSH flasher for JIDU6101: the documented route is UART + TFTP, then
LuCI. `fwflash.sh 6101 --download-only` still fetches and verifies the images,
which is the part worth automating.

## Where the images come from

| Model | Source | Note |
| --- | --- | --- |
| 6J01, 6101 | OpenWrt 25.12.6, `mediatek/filogic` | Official. Upstream ships `-initramfs-kernel.bin` and `-squashfs-sysupgrade.bin` only. |
| 6J01, 6101 factory `.ubi` | community build, 2026-07-28 | **Not covered by OpenWrt checksums.** OpenWrt does not build a factory `.ubi` for these boards, and the SSH method needs one. sha256 is pinned in the manifest. |
| 6J11 | [`themayankraut/JIO-AX6000-6J11-OpenWRT-SSH` v1.0.0](https://github.com/themayankraut/JIO-AX6000-6J11-OpenWRT-SSH/releases/tag/v1.0.0) | OpenWrt has no `qualcommbe` target and no Jio profile, so this is a community build. Assets are byte-identical to that release. |

All files are mirrored as assets of the `fw-2026.10` release on this repo, so a
download cannot break because an upstream tag moved. The manifest pins both the
URL and the sha256.

## Risk

Flashing replaces the boot chain on hardware with a signed stock bootloader. A
failed write means UART recovery at best. Back the unit up first, and read the
per-model page in `docs/models/` before running anything.

Only use this on equipment you own or are explicitly authorised to test. Provided
as is, without warranty, without liability — see the [LICENSE](../LICENSE).
