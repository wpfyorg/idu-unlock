# Backups

```bash
./flash.sh backup
```

The tool unlocks the router if necessary, then writes a directory named after the
router's Wi-Fi network — `AirFiber-XXXXXX/`, or the model and serial when the SSID
cannot be read.

## What is in it

```text
AirFiber-XXXXXX/
├── credentials.txt        u-boot + web + Wi-Fi + ACS + serial + MAC
├── uboot_credentials.env  UBOOT_USERNAME=… / UBOOT_PASSWORD=…
├── partitions.txt         cat /proc/mtd
├── uboot_env.txt          fw_printenv, both environments
├── factory_env.txt        the raw MFG key=value block
└── backup/
    ├── mtd1_BL2.bin
    ├── mtd2_u-boot-env.bin
    ├── mtd3_Factory.bin
    ├── mtd4_FIP.bin
    ├── mtd5_ubi.bin
    ├── mtd6_ubi2.bin
    ├── mtd7_MFG.bin
    └── mtd8_Jio-Reserved.bin
```

That covers:

- every MTD flash partition
- factory configuration
- web credentials
- Wi-Fi credentials
- u-boot environment
- u-boot credentials
- serial / MAC information

`mtd0` (the whole SPI chip) is skipped by default because it is large and mostly a
superset of the rest; pass `--full-chip` to include it.

## Sizes

Expect a few hundred megabytes. `mtd5` is roughly 140 MB and `mtd6` roughly 90 MB
on a `6701`; the rest are small. `--full-chip` adds more.

## Treat it like a password

> [!IMPORTANT]
> **Do not upload the backup to GitHub or share it publicly.**

It contains the router's factory passwords, its Wi-Fi PSK, its web credentials,
and its u-boot credentials — everything needed to take the device over. Some of
that data is unique to your unit and cannot be regenerated.

## Restoring a single partition

Only if you understand the implications. This writes to flash:

```bash
scp backup/mtd1_BL2.bin root@192.168.31.1:/tmp/
ssh root@192.168.31.1 'mtd write /tmp/mtd1_BL2.bin BL2'
```

A wrong image in a bootloader partition bricks the unit. If you are heading for
OpenWrt, keep the backup intact and read [OPENWRT.md](../OPENWRT.md) instead — the
backup is your only way back.

## Why it is worth doing first

If a flash goes wrong, the original partitions are the only route back, and they
hold device-specific factory data that cannot necessarily be recreated later. Run
the backup before you do anything else, and keep it somewhere other than the
machine you are working from.
