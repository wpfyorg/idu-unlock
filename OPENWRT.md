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

`flash.sh` stops at **root SSH + a backup**. It deliberately does not write
firmware. This page is what comes next, for when you want to go further.

**It is manual, and it is the risky part.** Read it end to end once before you
type anything.

## Read this before anything else

- **You need your backup.** If you don't have it, stop and run
  `./flash.sh backup` now. It contains every partition, the factory
  credentials, and the original u-boot environment — the three things that get
  you out of trouble.
- **You need root SSH.** If `ssh -i ~/.ssh/idu_rsa root@192.168.31.1` doesn't
  work yet, stop and run `./flash.sh unlock`.
- **Two stages, and you need both.** OpenWrt is installed in two steps: a
  temporary system that runs in RAM (*initramfs*), then the permanent one
  (*sysupgrade*). The reason is simple — a running stock firmware can't be
  safely overwritten from underneath itself. Booting the RAM version first
  gives you something with nothing to lose while the real write happens.
- **The router's address changes.** Stock firmware lives at `192.168.31.1`.
  Once OpenWrt boots it is at `192.168.1.1`. Don't sit there hitting the old
  address.
- **Use a cable.** Wi-Fi on the temporary system is unreliable or absent. Plug
  in Ethernet.
- **Never pull the power** during `ubiformat` or `sysupgrade`. That is the one
  action that turns a recoverable mistake into a brick.

## Which router do you have?

| Family | Models | What flashing takes |
| --- | --- | --- |
| MediaTek 6j01 | JIDU 6101 / 6201 / 6401 / 6601 / **6701** | SSH only — no extra hardware |
| Qualcomm 6j11 | JIDU 6111 / 6411 / 6611 / 6811 / 6911 | SSH **plus a UART adapter** and opening the case |

Not sure? `./flash.sh detect` prints the model and family.

**6j01 → [jump to the MediaTek steps](#mediatek-6j01-jidu-6201--6401--6601--6701).**
**6j11 → [jump to the Qualcomm steps](#qualcomm-6j11-jidu-6111--6411--6611--6811--6911).**

## Get the image files

Download the OpenWrt images for your router from the
[**firmware download folder**](https://drive.google.com/drive/folders/16OvJoZeZFTx4dXRZWfGMlsy-RXDB54_h).

You want **two** files, and both must say your family:

```
…-jidu6j01-initramfs-factory.ubi        ← 6j01, stage 1
…-jidu6j01-squashfs-sysupgrade.bin      ← 6j01, stage 2
```

```
…-jidu6j11-initramfs-uImage.itb         ← 6j11, stage 1
…-jidu6j11-squashfs-sysupgrade.bin      ← 6j11, stage 2
```

> **Read the filenames and check the `6j01`/`6j11` part matches your unit.**
> The commands below use those names as examples — **use whatever your files
> are actually called**, every time you see a filename. The upstream guide
> says the same thing, and it means it.

Put both files somewhere convenient and open a terminal in that folder. From
here on, "the folder" means *the one holding the images*, which is usually
**not** the `idu-unlock` folder.

---

## MediaTek 6j01 (JIDU 6201 / 6401 / 6601 / 6701)

> The upstream instructions these steps come from list **6201, 6401, 6601 and
> 6701**. The **6101** is unlocked by `flash.sh`, but it does *not* appear in the
> upstream flashing guide — so treat the steps below as unverified for a 6101 and
> don't expect anyone to have tested that combination.

### Step 1 — look at the partition table

```sh
ssh -i ~/.ssh/idu_rsa root@192.168.31.1
```

You're now on the router. Note the prompt changes; commands from here until you
`exit` run *on the router*, not on your PC.

```sh
cat /proc/mtd
```

This lists the flash layout. You should see `BL2`, `u-boot-env`, `Factory`,
`FIP`, `ubi`, `ubi2`, `MFG` and `Jio_Reserved`. Keep this output — it's also in
your backup as `partitions.txt`.

The two that matter later are **`mtd6` (`ubi2`)** — where OpenWrt will live —
and **`mtd1`–`mtd8`**, which you already have copies of.

### Step 2 — confirm you have the backup

Skip this if `./flash.sh backup` ran successfully. The backup is a folder named
after the router's Wi-Fi network, so check it from **your PC**, not the router:

```sh
ls */backup/
```

You want one `.bin` per partition. If the folder is empty or missing, back out
and do that first — this is the step that makes everything else reversible.

*(If you'd rather dump them by hand, the commands are
`ssh root@192.168.31.1 "cat /dev/mtd1" > mtd1_BL2.bin`, and so on for `mtd2`
through `mtd8`. That's exactly what `flash.sh backup` already did for you.)*

### Step 3 — send the temporary image to the router

Back on **your PC**, in the folder with the images:

```sh
scp -O openwrt-mediatek-filogic-jiorouter_ax6000-jidu6j01-initramfs-factory.ubi root@192.168.31.1:/tmp/
```

> **If you get `unknown option -- O`**, your `scp` is older and doesn't need it
> — run the same command with `-O` removed.

### Step 4 — write it, and tell u-boot to use it

Back on the **router** (your first SSH session, or a new one):

```sh
ubidetach -m 6
ubiformat /dev/mtd6 -y -f /tmp/openwrt-mediatek-filogic-jiorouter_ax6000-jidu6j01-initramfs-factory.ubi
```

Line by line, that detaches the existing UBI volume on `mtd6` so it can be
rewritten, then erases `mtd6` and writes the OpenWrt image into it. **This is
the point of no return** — the stock firmware on `mtd6` is gone from here, and
your backup is what brings it back.

Now the boot settings:

```sh
fw_setenv bootcmd 'ubi detach; ubi part ubi2; ubi read 46000000 kernel; fdt addr $(fdtcontroladdr); fdt rm /signature; bootm 0x46000000'
fw_setenv dual_boot.current_slot 1
fw_setenv dual_boot.slot_0_invalid 1
fw_setenv dual_boot.slot_1_invalid 1
fw_setenv ipaddr
```

- `bootcmd` — replaces "boot the stock system" with "load the kernel out of the
  new UBI volume and boot it". The `fdt rm /signature` part drops the vendor's
  signature check, which stock firmware would otherwise fail.
- the three `dual_boot` lines — these stop the stock A/B slot logic from
  deciding your install is invalid and booting/reverting around it.
- `fw_setenv ipaddr` with **nothing after it** — deletes the sticky IP address
  the stock system left in u-boot's environment. Without this the router can
  come up at an address you're not expecting.

> **Keep the single quotes exactly as shown.** `'…'` stops *your* shell from
> expanding `$(fdtcontroladdr)` — that has to reach u-boot literally so *u-boot*
> expands it. Use double quotes or retype it and you'll store a broken boot
> command.

### Step 5 — reboot into the temporary system

```sh
reboot
```

The router goes down and comes back on the **initramfs** — a complete OpenWrt
running entirely in RAM, so nothing is permanent yet and there's nothing to
break. Give it a minute, then from your PC:

```sh
ssh root@192.168.1.1
```

**Note the address: `192.168.1.1`, not `192.168.31.1`.** If SSH won't answer,
try `http://192.168.1.1` in a browser — the LuCI login page means it came up
fine.

### Step 6 — write the permanent system

From **your PC**, in the folder with the images:

```sh
scp -O openwrt-mediatek-filogic-jiorouter_ax6000-jidu6j01-squashfs-sysupgrade.bin root@192.168.1.1:/tmp/
```

Then **on the router**:

```sh
sysupgrade /tmp/openwrt-mediatek-filogic-jiorouter_ax6000-jidu6j01-squashfs-sysupgrade.bin
```

The router writes the real system and reboots on its own. **Do not touch it
until it's back.** When it returns you have OpenWrt at `192.168.1.1` — the
default LuCI login is the usual OpenWrt one, and you'll be asked to set a root
password.

*Prefer clicking?* Browse to `http://192.168.1.1` → **System → Backup / Flash
Firmware** → *Flash image…* → pick the `sysupgrade.bin`. Same result, and it
double-checks the image for you. Don't tick *Keep settings* on this first flash.

**That's it.** Over SSH you're done after this step.

---

## Qualcomm 6j11 (JIDU 6111 / 6411 / 6611 / 6811 / 6911)

This family is harder: **you must open the case and connect a serial (UART)
adapter.** Flashing happens from u-boot, not from Linux, because the stock
firmware's own update path is what has to be replaced. This is not avoidable.

### What you need

A **USB-to-TTL (UART) adapter** — CH340, PL2303 or CP2102 all work — plus jumper
wires, and a terminal program on your PC. Any of them will do; the upstream
guide links to specific ones if you'd rather not shop around.

> **Check the adapter's voltage jumper is on 3.3 V, not 5 V.** Router UART pins
> are 3.3 V, and 5 V can damage the board.

### Step 1 — back up, and read the factory data

From **your PC**:

```sh
ssh -i ~/.ssh/idu_rsa root@192.168.31.1
```

On the **router**:

```sh
cat /proc/mtd
jioMfgData get all
```

`jioMfgData get all` prints the factory data — serial, MACs, Wi-Fi keys,
passwords. **Copy the whole output somewhere safe and offline**, and don't post
it anywhere. Your `flash.sh backup` already captured the same thing (see
`credentials.txt` in the backup folder), so this is a second copy rather than a
replacement.

Do you have `mtd23` (`rootfs`) and `mtd24` (`rootfs1`)? They're in your backup
too — `flash.sh backup` images every partition it finds. If you'd rather dump
them by hand, it's the same `ssh root@192.168.31.1 "cat /dev/mtd23" > mtd23_rootfs.bin`
pattern.

### Step 2 — reset the vendor data

On the **router**:

```sh
jioMfgData init
```

Upstream calls this "Reset Existing Data": it resets the vendor data store so
it can't interfere with the install. **Your backup is now the only copy** —
which is why step 1 came first.

### Step 3 — open the case and connect UART

**Power the router off.** Open the case, find the UART header, and connect it to
your USB-to-TTL adapter. **Adapter TX → router RX, adapter RX → router TX, and
GND → GND.** Cross TX and RX, don't cross GND.

There are board photos in the upstream repository's
[`uart_pins`](https://github.com/the-diy-daddy/6j01_6j11/tree/main/uart_pins)
folder — match your model.

Open your terminal program on the adapter's serial port at **115200 baud,
8 data bits, no parity, 1 stop bit** (the stock firmware's own boot arguments
say `115200n8`). Then power the router on.

### Step 4 — stop the boot and log in

Watch the wall of text. You need to **interrupt the boot sequence** — press a
key repeatedly as soon as it starts. You'll land at a u-boot prompt asking for
a username and password.

The upstream guide documents the default credentials for these units, and **your
own unit's are in the backup**:

```
<your-backup-folder>/uboot_credentials.env
```

Use those if they differ from the documented default — a carrier or a firmware
revision can change them.

### Step 5 — load OpenWrt over TFTP

You need a TFTP server on your PC serving **the folder with the images**, and
your PC's IP set to `192.168.1.2` — with an Ethernet cable from your PC to one
of the router's LAN ports. Leave the UART connection in place so you can watch
each step.

At the u-boot prompt:

```
setenv ipaddr 192.168.1.1
setenv serverip 192.168.1.2
```

Then — **with your actual filename**, not the example:

```
tftpboot openwrt-qualcommbe-ipq95xx-jiorouter-ax6000-jidu6j11-initramfs-uImage.itb
```

That pulls the temporary system into RAM over the network. Then boot it:

```
bootm
```

### Step 6 — install the permanent system

The router is now running OpenWrt in RAM at `192.168.1.1`.

**Either** browse to `http://192.168.1.1`, log into LuCI, and use **System →
Backup / Flash Firmware → Flash image…** with the `squashfs-sysupgrade.bin`.

**Or** do it over SSH from your PC:

```sh
scp -O openwrt-qualcommbe-ipq95xx-jiorouter-ax6000-jidu6j11-squashfs-sysupgrade.bin root@192.168.1.1:/tmp/
ssh root@192.168.1.1 sysupgrade /tmp/openwrt-qualcommbe-ipq95xx-jiorouter-ax6000-jidu6j11-squashfs-sysupgrade.bin
```

### Step 7 — if it reports "No Kernel Found"

Some IDU models hit this on first boot into OpenWrt. At the u-boot prompt, set
these two and boot again:

```
setenv mtdids nand0=nand0
setenv mtdparts 'mtdparts=nand0:0xE100000@0x1700000(rootfs)'
```

*(Single quotes again — the `( )` must reach u-boot untouched.)*

---

## Going back to stock

**Read this before you flash, not after.** Knowing the exit exists is what makes
the rest of this safe.

### 6j11 — documented by upstream

Get your saved `mtd23`/`mtd24` images onto the router, then from its shell:

```sh
mtd -e /dev/mtd23 write /tmp/mtd23_rootfs.bin /dev/mtd23
mtd -e /dev/mtd24 write /tmp/mtd24_rootfs1.bin /dev/mtd24
```

Then restore the boot behaviour in the u-boot console:

```
setenv bootcmd 'bootipq'
```

And, if you've lost UART shell access, the stock boot arguments:

```
setenv bootargs 'console=ttyMSM0,115200n8 cnss2.bdf_pci1=0xb7 cnss2.bdf_integrated=0x30'
```

### 6j01 — reconstruct it from your backup

Upstream doesn't document a revert for this family. The pieces you need are all
in your backup, though:

1. **`uboot_env.txt`** — your original u-boot environment, captured *before* you
   changed anything. It holds the stock `bootcmd` and the original `ipaddr`.
   Put them back with `fw_setenv` (and drop the three `dual_boot.*` variables
   you set).
2. **`backup/mtd6_ubi2.bin`** — the stock system image. Write it back the same
   way you wrote OpenWrt in:

   ```sh
   ubidetach -m 6
   ubiformat /dev/mtd6 -y -f /tmp/mtd6_ubi2.bin
   ```

3. Reboot.

Do this from the **initramfs** (stage 1), not from the installed OpenWrt — the
same reason the install works that way. If the router won't boot at all, the
u-boot console over UART is the way in.

## When it goes wrong

- **It won't boot at all.** Don't panic and don't keep power-cycling it. The
  u-boot console over UART still works when Linux can't start, and that's where
  you undo things. For 6j01 you'll need a UART adapter you may not have bought
  yet — worth having before you start.
- **You can't reach `192.168.31.1` any more.** You're probably past stage 1 —
  try `192.168.1.1`.
- **`scp` or `ssh` refuses the connection after stage 1.** Give it a minute to
  finish booting, and use the LuCI page in a browser as a sanity check.
- **`ubiformat` errors out.** Stop. Re-read the step: `ubidetach -m 6` must
  succeed *before* `ubiformat`, and the image must be the `-factory.ubi` file,
  not the `sysupgrade` one. Mixing those two up is the most common mistake here.
- **Power cut mid-write.** This is the bad one. UART and the u-boot console; for
  6j11 the `bootcmd`/`bootargs` lines above are what you'll need.
- **You want out.** See *Going back to stock*. That's what the backup is for.

## Where this comes from

The procedure on this page is the community's, worked out by
**[the-diy-daddy](https://github.com/the-diy-daddy/6j01_6j11)** — the 6j01 steps
come from that repository's README, and the 6j11 steps from its
`6j11_instructions.md`. Credit for working it out belongs there. If you get
stuck, that repository and its videos are the better place to look than this
page.

This page is this project's own wording of it, written to be followed slowly.
That repository ships no licence, so nothing from it is copied here, and
neither is the PoC this project started from.

**One deliberate omission:** the 6j11 u-boot console's default credentials are
published in the upstream guide, but not repeated here — this project's
[stated position](README.md) is that it carries no vendor secrets, and your own
unit's credentials are in your own backup anyway. If you want the defaults,
they're in the upstream document linked above.
