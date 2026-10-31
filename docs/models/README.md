# JIDU model guides

Every model this project supports has its own install page. Start with the page
for your unit: it lists the exact image files, the route that model uses, its
UART reference, and the parts that differ from its siblings.

The 6j01 pages lead with the SSH shortcut, then the official 25.12.6
sysupgrade. The UART route is the fallback. The 6j11 pages use the Mayank SSH
method; UART is recovery only.
The shared procedure, with the reasoning behind each command, is
[Installing OpenWrt by hand](../../OPENWRT.md).

| Model | Family | Official OpenWrt | Route | UART pins | Status |
| --- | --- | --- | --- | --- | --- |
| [JIDU6101](JIDU6101.md) | MediaTek `6j01` | Yes (`jidu6101`) | SSH then official, UART fallback | None published | Official image; SSH primary |
| [JIDU6201](JIDU6201.md) | MediaTek `6j01` | Yes (`jidu6j01`) | SSH then official, UART fallback | None published | Official image; SSH primary |
| [JIDU6401](JIDU6401.md) | MediaTek `6j01` | Yes (`jidu6j01`) | SSH then official, UART fallback | not hosted here | Official image; SSH primary |
| [JIDU6601](JIDU6601.md) | MediaTek `6j01` | Yes (`jidu6j01`) | SSH then official, UART fallback | None published | Official image; SSH primary |
| [JIDU6701](JIDU6701.md) | MediaTek `6j01` | Yes (`jidu6j01`) | SSH then official, UART fallback | None published | Official image; SSH primary |
| [JIDU6111](JIDU6111.md) | Qualcomm `6j11` | No (community) | SSH (Mayank, primary), UART recovery | not hosted here | SSH primary; community |
| [JIDU6411](JIDU6411.md) | Qualcomm `6j11` | No (community) | SSH (Mayank, primary), UART recovery | not hosted here | SSH primary; community |
| [JIDU6611](JIDU6611.md) | Qualcomm `6j11` | No (community) | SSH (Mayank, primary), UART recovery | not hosted here | SSH primary; community |
| [JIDU6811](JIDU6811.md) | Qualcomm `6j11` | No (community) | SSH (Mayank, primary), UART recovery | not hosted here | SSH primary; community |
| [JIDU6911](JIDU6911.md) | Qualcomm `6j11` | No (community) | SSH (Mayank, primary), UART recovery | not hosted here | SSH primary; community |

The 6101's SSH path writes the shared `jidu6j01` stage 1, then the official
`jidu6101` image with `-F`; its UART path installs the 6101 image without
forcing.

For the 6j01 official image, use 25.12.6 or newer. Older 25.12 builds could
silently fail to write the SPI-NAND; the fix is
[PR 25122](https://github.com/openwrt/openwrt/pull/25122), included in the
25.12.6 images. The community stage 1 in the SSH route performs the NAND
write, so if it predates the fix, use the UART route.

Not sure which model you have? Detection changes nothing:

```sh
./flash.sh detect
```

Whichever page you land on, back up before flashing. The backup is the only way
back to stock, and it holds the factory data that the flash does not recreate,
including `uboot_credentials.env` for the UART route.

The backup needs root SSH: either a unit that is already unlocked (for example
through UART), or a successful `unlock`. Run `./flash.sh check` first. If it
reports `NO` and SSH is not already enabled, this tool has no software-only
backup for that unit. The UART route on the model page is then the fallback, and
you need it before flashing anything. See
[Firmware matters](../../README.md#firmware-matters).
