#!/bin/sh
# onrouter/6j11.sh — runs ON the stock JIDU6J11 as root, uploaded by fwflash.sh.
#
# Finds the idle rootfs slot, writes the OpenWrt factory image into it with
# ubiformat, repoints U-Boot at that slot, and reboots. The unit comes up as
# OpenWrt initramfs on 192.168.1.1, where fwflash.sh writes the sysupgrade.
#
# rootfs_data is never touched.
#
# set -e matters here: a failed ubiformat must not be followed by fw_setenv and
# a reboot, which would point the bootloader at a half-written slot.

set -e

# fwflash.sh uploads the verified image under this exact name. Do not glob for
# *factory.ubi: a leftover image for another model could sort first.
FACTORY=/tmp/jidu-factory.ubi
if [ ! -f "$FACTORY" ]; then
  echo "[-] $FACTORY is missing; nothing uploaded, nothing written"
  exit 1
fi
echo "[+] factory image: $FACTORY"

# Detect the active slot. Anything other than the two known names means the
# layout is not what this script expects, so stop rather than pick a slot.
ACT=$(grep -oE 'ubi\.mtd=[^ ]+' /proc/cmdline | cut -d= -f2) || ACT=""
case "$ACT" in
  rootfs)   IDLE=rootfs_1 ;;
  rootfs_1) IDLE=rootfs ;;
  *)
    echo "[-] unexpected ubi.mtd='$ACT' in /proc/cmdline - cannot tell active from idle"
    cat /proc/cmdline
    exit 1
    ;;
esac
echo "[+] active slot: $ACT, idle slot: $IDLE"

DEV=$(grep "\"$IDLE\"" /proc/mtd | cut -d: -f1)
if [ -z "$DEV" ]; then
  echo "[-] no partition named $IDLE in /proc/mtd - refusing to write"
  cat /proc/mtd
  exit 1
fi
NUM=$(echo "$DEV" | tr -dc '0-9')
echo "[+] target: /dev/$DEV ($NUM)"

OFF=$(printf "0x%x" "$(cat /sys/class/mtd/$DEV/offset)")
SIZ=$(printf "0x%x" "$(cat /sys/class/mtd/$DEV/size)")
echo "[+] offset: $OFF, size: $SIZ"

echo "[+] formatting and flashing $FACTORY to /dev/$DEV"
ubidetach -m "$NUM" 2>/dev/null || true
ubiformat "/dev/$DEV" -y -f "$FACTORY"

echo "[+] updating the U-Boot environment"
fw_setenv mtdids 'nand0=nand0'
fw_setenv mtdparts "mtdparts=nand0:${SIZ}@${OFF}(${IDLE})"
fw_setenv bootcmd "ubi detach; ubi part ${IDLE}; ubi read 0x46000000 kernel; bootm 0x46000000"

echo "[+] success, rebooting in 3 seconds"
sleep 3
reboot
