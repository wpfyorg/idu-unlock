> ## Legal notice and disclaimer
>
> The full notice at the top of [README.md](README.md) applies here, and it
> applies *harder*: **this page walks you through replacing your router's
> operating system.** Get it wrong and the router will not boot.
>
> - **Back up first.** Everything here assumes you already ran
>   `./flash.sh backup`. That backup is the only way back.
> - **Only on hardware you own**, and only where it's lawful. These are normally
>   carrier-supplied units; replacing the firmware can breach your service terms
>   and will void any warranty.
> - **Match the image to your exact model.** Flashing the wrong one is how
>   routers die.
> - **No warranty, no liability.** Provided as is — see the README.
>
> The procedure below is the community's method, worked out by
> [the-diy-daddy](https://github.com/the-diy-daddy/6j01_6j11) — see
> *Where this comes from* at the end. This project only writes it down more
> slowly; it does not automate it, and cannot do any of it for you.

---

# Installing OpenWrt by hand

`flash.sh` stops at **root SSH + a backup**. It deliberately does not write firmware. This page is what comes next, if you want to go further.

**It is manual, and it is the risky part.** Read the whole page once before typing anything.

## Contents

- [Quick reference](#quick-reference)
- [Before you start](#before-you-start)
- [Get the images](#get-the-images)
- [MediaTek 6j01](#mediatek-6j01-jidu-6201--6401--6601--6701)
- [Qualcomm 6j11](#qualcomm-6j11-jidu-6111--6411--6611--6811--6911)
- [FAQ](#faq)
- [Where this comes from](#where-this-comes-from)

## Quick reference

| Family | Models | Flashing needs | Stage 1 file | Stage 2 file |
| --- | --- | --- | --- | --- |
| MediaTek 6j01 | JIDU 6101 / 6201 / 6401 / 6601 / **6701** | SSH only | `…-jidu6j01-initramfs-factory.ubi` | `…-jidu6j01-squashfs-sysupgrade.bin` |
| Qualcomm 6j11 | JIDU 6111 / 6411 / 6611 / 6811 / 6911 | SSH **+ UART adapter** + open case | `…-jidu6j11-initramfs-uImage.itb` | `…-jidu6j11-squashfs-sysupgrade.bin` |

Key facts:

- Two stages, always: **initramfs** (temporary, runs in RAM) then **sysupgrade** (permanent). Stock firmware cannot overwrite itself safely.
- Address change: stock is `192.168.31.1`, OpenWrt is `192.168.1.1`.
- Use Ethernet, not Wi-Fi — Wi-Fi on the temporary system is unreliable or absent.
- **Never pull power** during `ubiformat` or `sysupgrade`.
- Unsure of your family? `./flash.sh detect` prints model and family.

> The upstream flashing guide lists 6j01 as 6201 / 6401 / 6601 / 6701. The 6101 unlocks with `flash.sh` but is unverified for flashing — do not expect a tested path.

## Before you start

- [ ] `./flash.sh backup` completed — folder with one `.bin` per partition exists.
- [ ] Root SSH works: `ssh -i ~/.ssh/idu_rsa root@192.168.31.1`.
- [ ] Both image files downloaded (see below), filenames checked against your family.
- [ ] Ethernet cable ready. For 6j11: UART adapter (CH340 / PL2303 / CP2102) at **3.3 V**, jumper wires, terminal program.

Download images from the [**firmware download folder**](https://drive.google.com/drive/folders/16OvJoZeZFTx4dXRZWfGMlsy-RXDB54_h).

## Get the images

You need **two** files, both matching your family (`6j01` or `6j11`):

```
…-jidu6j01-initramfs-factory.ubi        ← 6j01, stage 1
…-jidu6j01-squashfs-sysupgrade.bin      ← 6j01, stage 2
```

```
…-jidu6j11-initramfs-uImage.itb         ← 6j11, stage 1
…-jidu6j11-squashfs-sysupgrade.bin      ← 6j11, stage 2
```

Put both in one folder and open a terminal there. From here on, "the folder" means the image folder, usually **not** the `idu-unlock` folder. Commands below use example filenames — **substitute your actual filenames** every time.

---

## MediaTek 6j01 (JIDU 6201 / 6401 / 6601 / 6701)

### 1. Inspect partitions

On the router:

```sh
ssh -i ~/.ssh/idu_rsa root@192.168.31.1
cat /proc/mtd
```

Expect `BL2`, `u-boot-env`, `Factory`, `FIP`, `ubi`, `ubi2`, `MFG`, `Jio_Reserved`. `mtd6` (`ubi2`) is where OpenWrt will live. This output is also in your backup as `partitions.txt`.

Confirm the backup from your **PC**:

```sh
ls */backup/
```

One `.bin` per partition. If missing, stop and run `./flash.sh backup` first.

### 2. Send the stage-1 image

From your **PC**, in the image folder:

```sh
scp -O openwrt-mediatek-filogic-jiorouter_ax6000-jidu6j01-initramfs-factory.ubi root@192.168.31.1:/tmp/
```

> `unknown option -- O` means your `scp` is old — drop `-O` and retry.

### 3. Write it and set boot variables

On the **router**:

```sh
ubidetach -m 6
ubiformat /dev/mtd6 -y -f /tmp/openwrt-mediatek-filogic-jiorouter_ax6000-jidu6j01-initramfs-factory.ubi
```

**Point of no return** — stock firmware on `mtd6` is gone after this; the backup is the way back.

```sh
fw_setenv bootcmd 'ubi detach; ubi part ubi2; ubi read 46000000 kernel; fdt addr $(fdtcontroladdr); fdt rm /signature; bootm 0x46000000'
fw_setenv dual_boot.current_slot 1
fw_setenv dual_boot.slot_0_invalid 1
fw_setenv dual_boot.slot_1_invalid 1
fw_setenv ipaddr
```

What this does: `bootcmd` boots the new kernel instead of stock (`fdt rm /signature` drops the vendor signature check); the three `dual_boot` lines stop stock A/B logic from reverting it; bare `fw_setenv ipaddr` deletes the sticky stock IP. Keep the **single quotes** — `$(fdtcontroladdr)` must reach u-boot literally.

### 4. Boot the temporary system

```sh
reboot
```

Wait about a minute, then from your PC:

```sh
ssh root@192.168.1.1
```

Note the new address. If SSH fails, try `http://192.168.1.1` — the LuCI login page means it booted.

### 5. Write the permanent system

From your **PC**:

```sh
scp -O openwrt-mediatek-filogic-jiorouter_ax6000-jidu6j01-squashfs-sysupgrade.bin root@192.168.1.1:/tmp/
```

On the **router**:

```sh
sysupgrade /tmp/openwrt-mediatek-filogic-jiorouter_ax6000-jidu6j01-squashfs-sysupgrade.bin
```

It writes and reboots itself. **Do not touch it until it returns** at `192.168.1.1`. Set a root password on first login. GUI alternative: `http://192.168.1.1` → **System → Backup / Flash Firmware → Flash image…**, do not tick *Keep settings*.

---

## Qualcomm 6j11 (JIDU 6111 / 6411 / 6611 / 6811 / 6911)

Flashing happens from u-boot over UART — not avoidable for this family.

### 1. Back up and copy factory data

On the **router**:

```sh
ssh -i ~/.ssh/idu_rsa root@192.168.31.1
cat /proc/mtd
jioMfgData get all
```

Copy the `jioMfgData` output somewhere safe and offline (serial, MACs, Wi-Fi keys). Your `flash.sh backup` already saved it as `credentials.txt` — this is a second copy.

### 2. Reset vendor data

On the **router**:

```sh
jioMfgData init
```

Your backup is now the only copy of that data.

### 3. Connect UART

Power off. Open the case, find the UART header (photos in upstream [`uart_pins`](https://github.com/the-diy-daddy/6j01_6j11/tree/main/uart_pins) — match your model). Wire **adapter TX → router RX, adapter RX → router TX, GND → GND**. Jumper on **3.3 V**, never 5 V.

Open a terminal on the serial port at **115200 baud, 8N1**, then power on. Press a key repeatedly to interrupt boot and reach the u-boot prompt. Log in with your unit's credentials from `<backup-folder>/uboot_credentials.env`.

### 4. Load OpenWrt over TFTP

Serve the image folder over TFTP from your PC at `192.168.1.2`, Ethernet to a router LAN port, UART still attached. At the u-boot prompt:

```
setenv ipaddr 192.168.1.1
setenv serverip 192.168.1.2
tftpboot openwrt-qualcommbe-ipq95xx-jiorouter-ax6000-jidu6j11-initramfs-uImage.itb
bootm
```

Use your actual filename. The router now runs OpenWrt in RAM at `192.168.1.1`.

### 5. Install the permanent system

Via browser: `http://192.168.1.1` → **System → Backup / Flash Firmware → Flash image…** with the `squashfs-sysupgrade.bin`.

Or via SSH from your PC:

```sh
scp -O openwrt-qualcommbe-ipq95xx-jiorouter-ax6000-jidu6j11-squashfs-sysupgrade.bin root@192.168.1.1:/tmp/
ssh root@192.168.1.1 sysupgrade /tmp/openwrt-qualcommbe-ipq95xx-jiorouter-ax6000-jidu6j11-squashfs-sysupgrade.bin
```

---

## FAQ

<details>
<summary><strong>No Kernel Found on first OpenWrt boot (6j11)</strong></summary>

At the u-boot prompt, set and boot again:

```
setenv mtdids nand0=nand0
setenv mtdparts 'mtdparts=nand0:0xE100000@0x1700000(rootfs)'
```

Single quotes again — the `( )` must reach u-boot untouched.

</details>

<details>
<summary><strong>Going back to stock — 6j11 (documented upstream)</strong></summary>

Get saved `mtd23`/`mtd24` images onto the router, then:

```sh
mtd -e /dev/mtd23 write /tmp/mtd23_rootfs.bin /dev/mtd23
mtd -e /dev/mtd24 write /tmp/mtd24_rootfs1.bin /dev/mtd24
```

In the u-boot console:

```
setenv bootcmd 'bootipq'
```

If UART shell access is lost, also:

```
setenv bootargs 'console=ttyMSM0,115200n8 cnss2.bdf_pci1=0xb7 cnss2.bdf_integrated=0x30'
```

</details>

<details>
<summary><strong>Going back to stock — 6j01 (reconstructed from backup)</strong></summary>

Upstream documents no revert for this family; all pieces are in your backup:

1. `uboot_env.txt` — original `bootcmd` and `ipaddr`. Restore with `fw_setenv`, and drop the three `dual_boot.*` variables you set.
2. `backup/mtd6_ubi2.bin` — the stock system image:
   ```sh
   ubidetach -m 6
   ubiformat /dev/mtd6 -y -f /tmp/mtd6_ubi2.bin
   ```
3. Reboot.

Do this from **initramfs** (stage 1), not installed OpenWrt. If it will not boot at all, enter via UART.

</details>

<details>
<summary><strong>It will not boot at all</strong></summary>

Stop power-cycling. Use the u-boot console over UART — it works when Linux cannot start. For 6j01, buy the adapter before you start flashing.

</details>

<details>
<summary><strong>192.168.31.1 is unreachable</strong></summary>

You are probably past stage 1 — try `192.168.1.1`.

</details>

<details>
<summary><strong>ssh/scp refused after stage 1</strong></summary>

Give it a minute to finish booting; check the LuCI page in a browser as a sanity check.

</details>

<details>
<summary><strong>ubiformat errors out</strong></summary>

`ubidetach -m 6` must succeed first, and the image must be the `-factory.ubi` file — not the `sysupgrade` one. Mixing them up is the most common mistake.

</details>

<details>
<summary><strong>Power cut mid-write</strong></summary>

The bad one. Enter via UART and the u-boot console; for 6j11 the `bootcmd`/`bootargs` lines above are what you need.

</details>

## Where this comes from

The procedure is the community's, worked out by **[the-diy-daddy](https://github.com/the-diy-daddy/6j01_6j11)** — 6j01 steps from that repository's README, 6j11 steps from its `6j11_instructions.md`. Credit belongs there. If stuck, that repository and its videos are the better place to look than this page.

This page is this project's own wording, written to be followed slowly. That repository ships no licence, so nothing from it is copied here, and neither is the PoC this project started from.

**One deliberate omission:** the 6j11 u-boot console's default credentials are published upstream but not repeated here — this project's [stated position](README.md) is that it carries no vendor secrets, and your own unit's credentials are in your backup anyway.
