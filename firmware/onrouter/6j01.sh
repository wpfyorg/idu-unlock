#!/bin/sh
# onrouter/6j01.sh — runs ON the stock JIDU6J01 as root, uploaded by fwflash.sh.
#
# Replaces the idle UBI partition (ubi2 / mtd6) with the OpenWrt initramfs, then
# points U-Boot at it. The unit reboots into OpenWrt on 192.168.1.1, where
# fwflash.sh writes the permanent sysupgrade.
#
# The slot layout this expects is the MediaTek one used by every 6x01 board:
#
#   mtd5 "ubi"    stock firmware
#   mtd6 "ubi2"   the second slot, which is what gets rewritten
#
# If /proc/mtd does not have a partition literally named ubi2, the script stops
# instead of writing to a partition it cannot identify.

set -e

find_mtd() {
  sed -n 's/^\(mtd[0-9]*\):.*"'"$1"'"$/\1/p' /proc/mtd
}

FACTORY=$(ls /tmp/*factory.ubi 2>/dev/null | head -n 1)
if [ -z "$FACTORY" ] || [ ! -f "$FACTORY" ]; then
  echo "[-] no *factory.ubi in /tmp"
  exit 1
fi
echo "[+] factory image: $FACTORY"

DEV=$(find_mtd ubi2)
if [ -z "$DEV" ]; then
  echo "[-] no partition named ubi2 in /proc/mtd — refusing to guess"
  cat /proc/mtd
  exit 1
fi
NUM=${DEV#mtd}
echo "[+] target: /dev/$DEV ($NUM)"

ubidetach -m "$NUM" 2>/dev/null || true
ubiformat "/dev/$DEV" -y -f "$FACTORY"

echo "[+] pointing U-Boot at the new slot"
fw_setenv bootcmd 'ubi detach; ubi part ubi2; ubi read 46000000 kernel; fdt addr $(fdtcontroladdr); fdt rm /signature; bootm 0x46000000'
fw_setenv dual_boot.current_slot 1
fw_setenv dual_boot.slot_0_invalid 1
fw_setenv dual_boot.slot_1_invalid 1
fw_setenv ipaddr

sync
echo "[+] rebooting in 3 seconds"
sleep 3
reboot
