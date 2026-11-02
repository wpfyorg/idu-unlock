#!/bin/sh
# onrouter/6101.sh — runs ON the stock JIDU6101 as root, uploaded by fwflash.sh.
#
# Replaces the idle UBI partition (ubi2) with the JIDU6101-specific OpenWrt
# factory initramfs, then points U-Boot at it. The unit reboots into OpenWrt on
# 192.168.1.1, where fwflash.sh writes the matching official sysupgrade.
#
# The stock layout is expected to contain a partition literally named ubi2. If
# it does not, stop instead of guessing at a flash partition.

set -e

FACTORY=/tmp/jidu-factory.ubi
if [ ! -f "$FACTORY" ]; then
  echo "[-] $FACTORY is missing; nothing uploaded, nothing written"
  exit 1
fi
echo "[+] factory image: $FACTORY"

find_mtd() {
  sed -n 's/^\(mtd[0-9]*\):.*"'"$1"'"/\1/p' /proc/mtd
}

DEV=$(find_mtd ubi2)
if [ -z "$DEV" ]; then
  echo "[-] no partition named ubi2 in /proc/mtd - refusing to guess"
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
