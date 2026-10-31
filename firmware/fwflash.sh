#!/usr/bin/env bash
#
# fwflash.sh — fetch and flash an OpenWrt image for a JIDU router.
#
#   ./fwflash.sh 6j01            unlock if needed, then flash a JIDU6J01
#   ./fwflash.sh 6j11            unlock if needed, then flash a JIDU6J11
#   ./fwflash.sh 6j11 --smallbuffers
#                                ...using the reduced-buffer sysupgrade build
#   ./fwflash.sh 6j01 --download-only
#                                cache the images, flash nothing
#   ./fwflash.sh 6101            downloads only: no SSH flasher for 6101
#
# Options:
#   --router HOST   stock unit address (default 192.168.31.1)
#   --cache DIR     where images are kept (default ./downloads, next to this script)
#   --image PATH    use a local sysupgrade file instead of downloading one
#   --image-sha256 HEX
#                   the sha256 of --image; without it you must still confirm
#   --smallbuffers  6j11 only: flash the small-buffers sysupgrade build
#   --download-only cache the images and stop
#   --dry-run       print what would run, touch nothing
#   --yes           skip the confirmation prompt
#   -v, --verbose   show the per-command detail
#
# Images land in ./downloads/<model>/ next to this script and stay there. On the
# next run anything already present is reused, so nothing is downloaded twice.
# Every file is checked against the sha256 in manifest.json before use, including
# files already on disk, so a corrupt or half-written download is never flashed.
#
# If the unit has no root SSH yet, this runs the unlocker in the repo root
# (./flash.sh unlock) and asks for the router admin password - so the whole
# install is one command. Back the unit up if you can: ./flash.sh backup keeps a
# copy of every partition, and flashing is not reversible over the network.
#
# Only run against equipment you own or are explicitly authorised to test.
# Provided as is, without warranty, without liability — see the README.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$HERE/manifest.json"
STOCK="192.168.31.1"
OPENWRT="192.168.1.1"
CACHE="$HERE/downloads"
IMAGE=""
IMAGE_SHA=""
MODEL=""
SMALLBUFFERS=0
DOWNLOAD_ONLY=0
DRY_RUN=0
ASSUME_YES=0
VERBOSE=0

say()  { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
bad()  { printf '\033[1;31m[-]\033[0m %s\n' "$*" >&2; }
die()  { bad "$*"; exit 1; }

usage() { sed -n '3,32p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    6j01|6j11|6101)  MODEL="$1"; shift ;;
    --router)        STOCK="$2"; shift 2 ;;
    --cache)         CACHE="$2"; shift 2 ;;
    --image)         IMAGE="$2"; shift 2 ;;
    --image-sha256)  IMAGE_SHA="$2"; shift 2 ;;
    --smallbuffers)  SMALLBUFFERS=1; shift ;;
    --download-only) DOWNLOAD_ONLY=1; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --yes|-y)        ASSUME_YES=1; shift ;;
    -v|--verbose)    VERBOSE=1; shift ;;
    -h|--help)       usage; exit 0 ;;
    *)               bad "unknown argument: $1"; usage; exit 2 ;;
  esac
done

[ -n "$MODEL" ] || { usage; exit 2; }
command -v python3 >/dev/null || die "python3 is required (it reads the manifest)"

# One hash tool, picked once. Fail loudly instead of comparing empty strings.
if command -v sha256sum >/dev/null; then
  SHA_CMD=(sha256sum)
elif command -v shasum >/dev/null; then
  SHA_CMD=(shasum -a 256)
else
  die "sha256sum or shasum is required to verify the images"
fi
sha_of() { "${SHA_CMD[@]}" "$1" 2>/dev/null | awk '{print $1}'; }

# --- manifest ---------------------------------------------------------------
# One line per image: role|name|sha256|size|url
manifest_rows() {
  python3 - "$MANIFEST" "$MODEL" <<'PY'
import json, sys
path, model = sys.argv[1], sys.argv[2]
data = json.load(open(path))
entry = data["models"].get(model)
if entry is None:
    sys.exit(f"model {model} is not in the manifest")
for role, img in entry["images"].items():
    print("|".join([role, img["name"], img["sha256"], str(img["size"]), img["url"]]))
PY
}

manifest_field() {
  python3 - "$MANIFEST" "$MODEL" "$1" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(data["models"][sys.argv[2]].get(sys.argv[3], ""))
PY
}

rows="$(manifest_rows)" || die "cannot read $MANIFEST for $MODEL"

image_line() { printf '%s\n' "$rows" | awk -F'|' -v r="$1" '$1==r'; }
has_role()   { printf '%s\n' "$rows" | awk -F'|' -v r="$1" '$1==r{found=1} END{exit !found}'; }

TITLE="$(manifest_field title)"
DEST="$CACHE/$MODEL"

say "$TITLE"
say "images: $DEST"

if [ "$DRY_RUN" = 0 ]; then
  mkdir -p "$DEST" || die "cannot create $DEST"
fi

# --- cache ------------------------------------------------------------------
have_image() {  # role -> prints path on stdout, 0 if already cached and verified
  local line role name sha size url path
  line="$(image_line "$1")"; [ -n "$line" ] || return 1
  IFS='|' read -r role name sha size url <<<"$line"
  path="$DEST/$name"
  [ -f "$path" ] || return 1
  if [ "$(sha_of "$path")" = "$sha" ]; then echo "$path"; return 0; fi
  if [ "$DRY_RUN" = 1 ]; then
    warn "cached $name does not match the manifest (a real run would replace it)" >&2
  else
    warn "cached $name does not match the manifest, re-downloading" >&2
    rm -f "$path"
  fi
  return 1
}

fetch_image() {
  local role="$1" line name sha size url path part
  line="$(image_line "$role")"
  [ -n "$line" ] || die "the manifest has no '$role' image for $MODEL"
  IFS='|' read -r role name sha size url <<<"$line"
  path="$DEST/$name"

  if got="$(have_image "$role")"; then
    ok "$name (cached)" >&2
    printf '%s\n' "$got"
    return 0
  fi

  part="$path.part"
  say "downloading $name ($((size / 1048576)) MiB)" >&2
  if [ "$DRY_RUN" = 1 ]; then
    printf '    would run: curl -fL --retry 3 -C - -o %s %s\n' "$part" "$url" >&2
    printf '%s\n' "$path"
    return 0
  fi
  if command -v curl >/dev/null; then
    curl -fL --retry 3 --retry-delay 2 -C - -o "$part" "$url" >&2 || { rm -f "$part"; die "download failed: $url"; }
  else
    wget -q -O "$part" "$url" || { rm -f "$part"; die "download failed: $url"; }
  fi
  [ "$(sha_of "$part")" = "$sha" ] || { rm -f "$part"; die "$name: sha256 mismatch, refusing to use it"; }
  mv "$part" "$path"
  ok "$name (verified)" >&2
  printf '%s\n' "$path"
}

# --- what do we need? -------------------------------------------------------
FACTORY_PATH=""
SYSUPGRADE_PATH=""

if [ -n "$IMAGE" ]; then
  [ -f "$IMAGE" ] || die "no such file: $IMAGE"
  SYSUPGRADE_PATH="$(cd "$(dirname "$IMAGE")" && pwd)/$(basename "$IMAGE")"
  if [ -n "$IMAGE_SHA" ]; then
    [ "$(sha_of "$SYSUPGRADE_PATH")" = "$IMAGE_SHA" ] \
      || die "$IMAGE: sha256 mismatch, refusing to use it"
    ok "$(basename "$IMAGE") (matches the hash you supplied)"
  else
    warn "$(basename "$IMAGE") is not checked against the manifest"
    printf '    its sha256 is %s\n' "$(sha_of "$SYSUPGRADE_PATH")"
    ASSUME_YES=0   # a hand-picked image always gets the typed confirmation
  fi
fi

if [ "$DOWNLOAD_ONLY" = 0 ]; then
  has_role factory || die "the manifest has no factory image for $MODEL"
fi

FACTORY_PATH="$(fetch_image factory)" || exit 1

if [ -z "$SYSUPGRADE_PATH" ]; then
  if [ "$MODEL" = "6j11" ] && [ "$SMALLBUFFERS" = 1 ]; then
    SYSUPGRADE_PATH="$(fetch_image smallbuffers)" || exit 1
  else
    SYSUPGRADE_PATH="$(fetch_image sysupgrade)" || exit 1
  fi
fi

# The TFTP images are not needed for the SSH method, but people ask for them.
if [ "$DOWNLOAD_ONLY" = 1 ] && has_role initramfs; then
  fetch_image initramfs >/dev/null || exit 1
fi

if [ "$DOWNLOAD_ONLY" = 1 ]; then
  ok "cached in $DEST"
  exit 0
fi

# --- flash ------------------------------------------------------------------
if [ "$(manifest_field flasher)" != "True" ]; then
  warn "there is no SSH flasher for $MODEL: the documented route for this board is UART + TFTP"
  warn "images are cached in $DEST; see docs/models/ for the install route"
  exit 0
fi

printf '\n'
say "about to flash:"
printf '      unit      %s (stock) -> %s (OpenWrt)\n' "$STOCK" "$OPENWRT"
printf '      model     %s\n' "$MODEL"
printf '      factory   %s\n' "$(basename "$FACTORY_PATH")"
printf '      sysupgrade %s\n' "$(basename "$SYSUPGRADE_PATH")"
printf '\n'
if [ "$ASSUME_YES" = 0 ] && [ "$DRY_RUN" = 0 ]; then
  printf 'This overwrites the boot chain and cannot be undone over the network.\n'
  printf 'Type the model (%s) to continue: ' "$MODEL"
  read -r answer
  [ "$answer" = "$MODEL" ] || die "aborted"
fi

# Stock Dropbear can regenerate host keys on boot, so use a per-run known_hosts
# file instead of letting a stale personal entry look like a locked router.
# OpenWrt initramfs also gets a fresh key at 192.168.1.1 on each boot.
if [ "$DRY_RUN" = 1 ]; then
  STOCK_KNOWN_HOSTS=/dev/null
  OWRT_KNOWN_HOSTS=/dev/null
  SSH_ERR=/dev/null
else
  STOCK_KNOWN_HOSTS="$(mktemp "${TMPDIR:-/tmp}/jidu-stock-kh.XXXXXX")" || die "cannot create a temp file"
  OWRT_KNOWN_HOSTS="$(mktemp "${TMPDIR:-/tmp}/jidu-kh.XXXXXX")" || die "cannot create a temp file"
  SSH_ERR="$(mktemp "${TMPDIR:-/tmp}/jidu-err.XXXXXX")" || die "cannot create a temp file"
  trap 'rm -f "$STOCK_KNOWN_HOSTS" "$OWRT_KNOWN_HOSTS" "$SSH_ERR"' EXIT
fi

SSH=(ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$STOCK_KNOWN_HOSTS" -o ConnectTimeout=10 "root@$STOCK")
SCP=(scp -O -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$STOCK_KNOWN_HOSTS")
SSH_NEW=(ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$OWRT_KNOWN_HOSTS" \
             -o LogLevel=ERROR -o ConnectTimeout=5 "root@$OPENWRT")
SCP_NEW=(scp -O -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$OWRT_KNOWN_HOSTS" \
             -o LogLevel=ERROR)

run_must() {  # must exit 0
  local what="$1"; shift
  if [ "$DRY_RUN" = 1 ]; then printf '    would run: %s\n' "$*"; return 0; fi
  if ! "$@"; then bad "$what failed"; return 1; fi
}

run_until_reboot() {  # 0 or 255: the unit drops the connection as it reboots
  local what="$1"; shift
  if [ "$DRY_RUN" = 1 ]; then printf '    would run: %s\n' "$*"; return 0; fi
  local rc=0
  "$@" || rc=$?
  case "$rc" in
    0|255) return 0 ;;
    *) bad "$what failed (exit $rc)"; return 1 ;;
  esac
}

# One command: unlock the unit here rather than making the user run
# ./flash.sh unlock first. The unlocker prompts for the admin password itself,
# and PASSWORD/ROUTER in the environment are passed straight through to it.
UNLOCKER="$HERE/../flash.sh"

ensure_root_ssh() {
  if [ "$DRY_RUN" = 1 ]; then
    say "would check root SSH on $STOCK, unlocking it first if it does not answer"
    return 0
  fi
  say "checking root SSH on $STOCK"
  if "${SSH[@]}" 'cat /proc/mtd >/dev/null' 2>/dev/null; then
    ok "root SSH is live"
    return 0
  fi
  warn "no root SSH yet: unlocking the unit now (it asks for the admin password)"
  [ -x "$UNLOCKER" ] || die "this unit is locked and $UNLOCKER is missing"
  if [ "$(id -u)" -eq 0 ]; then
    ROUTER="https://$STOCK" "$UNLOCKER" unlock || die "the unlock failed; nothing was flashed"
  elif command -v sudo >/dev/null 2>&1; then
    warn "unlock needs local port 80; requesting elevated permission for the unlock step only"
    sudo -E env ROUTER="https://$STOCK" "$UNLOCKER" unlock || die "the unlock failed; nothing was flashed"
  else
    die "unlock needs local port 80; run the unlock step with elevated privileges, then rerun this flasher"
  fi
  "${SSH[@]}" 'cat /proc/mtd >/dev/null' 2>/dev/null \
    || die "the unit unlocked, but root SSH still does not answer"
  ok "root SSH is live"
}

ONROUTER="$HERE/onrouter/$MODEL.sh"
[ -f "$ONROUTER" ] || die "missing $ONROUTER"

ensure_root_ssh

say "uploading the factory image and the on-router script"
run_must "uploading $(basename "$FACTORY_PATH")" \
  "${SCP[@]}" "$FACTORY_PATH" "root@$STOCK:/tmp/jidu-factory.ubi" \
  || die "the image never reached the router, nothing was written"
run_must "uploading the on-router script" \
  "${SCP[@]}" "$ONROUTER" "root@$STOCK:/tmp/jidu-flash.sh" \
  || die "the script never reached the router, nothing was written"

say "writing the idle UBI slot (the unit reboots itself)"
run_until_reboot "the on-router script" "${SSH[@]}" 'sh /tmp/jidu-flash.sh' \
  || die "the slot was not written; the unit is still on stock firmware"

if [ "$DRY_RUN" = 1 ]; then
  say "would wait for OpenWrt on $OPENWRT"
else
  say "waiting for OpenWrt on $OPENWRT (up to 3 minutes)"
  sshed=0
  for _ in $(seq 1 40); do
    if "${SSH_NEW[@]}" 'true' 2>"$SSH_ERR"; then sshed=1; break; fi
    sleep 5
  done
  if [ "$sshed" != 1 ]; then
    bad "no SSH on $OPENWRT after 200s"
    [ -s "$SSH_ERR" ] && bad "last error: $(tail -n 1 "$SSH_ERR")"
    die "the unit may need UART recovery: docs/models/ and firmware/README.md"
  fi
  ok "initramfs is up"
fi

say "uploading the permanent sysupgrade"
run_must "uploading the sysupgrade" \
  "${SCP_NEW[@]}" "$SYSUPGRADE_PATH" "root@$OPENWRT:/tmp/sysupgrade.bin" \
  || die "the sysupgrade never reached the unit; it is still in initramfs"

say "flashing it (sysupgrade -n, settings are not kept)"
run_until_reboot "sysupgrade" "${SSH_NEW[@]}" 'sysupgrade -n /tmp/sysupgrade.bin' \
  || die "sysupgrade refused the image; the unit is still in initramfs"

printf '\n'
if [ "$DRY_RUN" = 1 ]; then
  warn "dry run: nothing was downloaded, written or flashed"
else
  ok "done. The unit reboots into OpenWrt at http://$OPENWRT — LuCI, root, no password."
  printf '    If it does not come back, recovery is UART + TFTP: docs/models/ and firmware/README.md\n'
fi
