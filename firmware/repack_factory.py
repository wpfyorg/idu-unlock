#!/usr/bin/env python3
"""Replace the kernel payload in a stock-compatible JIDU factory UBI.

The MediaTek factory image is a dynamic UBI volume named ``kernel``.  Dynamic
volume blocks do not carry a data CRC, so the container headers/layout can stay
unchanged while the FIT payload is replaced with a fixed OpenWrt initramfs.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct


PEB_SIZE = 131072
EC_FORMAT = ">4sB3sQIII32sI"
VID_FORMAT = ">4sBBBBII4sIIII4sQ12sI"


def repack(template_path: Path, initramfs_path: Path, output_path: Path) -> None:
    image = bytearray(template_path.read_bytes())
    fit = initramfs_path.read_bytes()

    if fit[:4] != b"\xd0\x0d\xfe\xed":
        raise ValueError("initramfs is not a FIT/FDT image")
    fit_size = struct.unpack(">I", fit[4:8])[0]
    if fit_size != len(fit):
        raise ValueError(f"FIT totalsize {fit_size} does not match file size {len(fit)}")
    if len(image) % PEB_SIZE:
        raise ValueError("template is not a whole number of 128 KiB PEBs")

    kernel_lebs: dict[int, tuple[int, int]] = {}
    leb_size = None

    for peb in range(len(image) // PEB_SIZE):
        base = peb * PEB_SIZE
        if image[base : base + 4] != b"UBI#":
            continue

        ec = struct.unpack_from(EC_FORMAT, image, base)
        vid_offset, data_offset = ec[4], ec[5]
        if image[base + vid_offset : base + vid_offset + 4] != b"UBI!":
            continue

        vid = struct.unpack_from(VID_FORMAT, image, base + vid_offset)
        vol_type, vol_id, lnum = vid[2], vid[5], vid[6]
        data_size, data_crc = vid[8], vid[11]
        if vol_id != 0:
            continue
        if vol_type != 1 or data_size != 0 or data_crc != 0:
            raise ValueError(f"PEB {peb}: kernel volume is not the expected dynamic UBI volume")

        current_leb_size = PEB_SIZE - data_offset
        if leb_size is None:
            leb_size = current_leb_size
        elif leb_size != current_leb_size:
            raise ValueError("template has inconsistent kernel LEB sizes")
        kernel_lebs[lnum] = (base + data_offset, current_leb_size)

    if not kernel_lebs or leb_size is None:
        raise ValueError("template has no kernel volume")
    if sorted(kernel_lebs) != list(range(len(kernel_lebs))):
        raise ValueError("kernel LEB numbers are not contiguous from zero")

    capacity = len(kernel_lebs) * leb_size
    if len(fit) > capacity:
        raise ValueError(f"initramfs is too large for kernel volume: {len(fit)} > {capacity}")

    for lnum in range(len(kernel_lebs)):
        offset, size = kernel_lebs[lnum]
        chunk = fit[lnum * size : (lnum + 1) * size]
        image[offset : offset + size] = chunk + b"\xff" * (size - len(chunk))

    output_path.write_bytes(image)
    digest = hashlib.sha256(image).hexdigest()
    print(f"{output_path}: {len(image)} bytes sha256={digest}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path, help="existing stock-compatible factory UBI")
    parser.add_argument("initramfs", type=Path, help="fixed OpenWrt initramfs-kernel.bin")
    parser.add_argument("output", type=Path, help="factory UBI to create")
    args = parser.parse_args()
    repack(args.template, args.initramfs, args.output)


if __name__ == "__main__":
    main()
