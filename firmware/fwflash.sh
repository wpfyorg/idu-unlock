#!/usr/bin/env bash
#
# fwflash.sh — fetch and flash an OpenWrt image for a JIDU router.
#
#   ./fwflash.sh 6j01            flash a JIDU6J01 over stock root SSH
#   ./fwflash.sh 6j11            flash a JIDU6J11 over stock root SSH
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
# The router must already have root SSH. Get that with ./flash.sh unlock (or the
# password trick documented upstream). Back the unit up before flashing: this
# writes over the boot chain and is not reversible over the network.
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
run()  { if [ "$DRY_RUN" = 1 ]; then printf '    would run: %s\n' "$*"; else eval "$@"; fi; }

usage() { sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    6j01|6j11|6101) MODEL="$1"; shift ;;
    --router)        STOCK="$2"; shift 2 ;;
    --cache)         CACHE="$2"; shift 2 ;;
    --image)         IMAGE="$2"; shift 2 ;;
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

mkdir -p "$DEST" || die "cannot create $DEST"

# --- cache ------------------------------------------------------------------
sha_of() { shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'; }

have_image() {  # role -> prints path on stdout, 0 if already cached and verified
  local line role name sha size url path
  line="$(image_line "$1")"; [ -n "$line" ] || return 1
  IFS='|' read -r role name sha size url <<<"$line"
  path="$DEST/$name"
  [ -f "$path" ] || return 1
  if [ "$(sha_of "$path")" = "$sha" ]; then echo "$path"; return 0; fi
  warn "cached $name does not match the manifest, re-downloading" >&2
  rm -f "$path"
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
  warn "using $SYSUPGRADE_PATH — not checked against the manifest"
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
  warn "images are cached in $DEST; see docs/models/JIDU$MODEL.md"
  exit 0
fi

if [ "$MODEL" = "6101" ]; then
  die "6101 has no SSH flasher yet"
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

SSH=(ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "root@$STOCK")
SCP=(scp -O -o StrictHostKeyChecking=accept-new "root@$STOCK")
SSH_NEW=(ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 "root@$OPENWRT")
SCP_NEW=(scp -O -o StrictHostKeyChecking=accept-new "root@$OPENWRT")

say "checking root SSH on $STOCK"
if [ "$DRY_RUN" = 0 ]; then
  "${SSH[@]}" 'cat /proc/mtd >/dev/null' 2>/dev/null || {
    bad "no root SSH on $STOCK"
    die "unlock first: ./flash.sh unlock  (and run ./flash.sh backup)"
  }
fi
ok "root SSH is live"

ONROUTER="$HERE/onrouter/$MODEL.sh"
[ -f "$ONROUTER" ] || die "missing $ONROUTER"

say "uploading the factory image and the on-router script"
run '"${SCP[@]}" "$FACTORY_PATH" "$ONROUTER" root@"$STOCK":/tmp/'

say "writing the idle UBI slot (the unit reboots itself)"
run '"${SSH[@]}" "sed -i \"s/\\r\$//\" /tmp/'"$(basename "$ONROUTER")"'; sh /tmp/'"$(basename "$ONROUTER")"'"'

say "waiting for OpenWrt on $OPENWRT (up to 5 minutes)"
if [ "$DRY_RUN" = 0 ]; then
  for _ in $(seq 1 60); do
    if ping -c 1 -W 1000 "$OPENWRT" >/dev/null 2>&1; then break; fi
    sleep 5
  done
  sleep 5
  sshed=0
  for _ in $(seq 1 12); do
    if "${SSH_NEW[@]}" 'true' 2>/dev/null; then sshed=1; break; fi
    sleep 5
  done
  [ "$sshed" = 1 ] || die "OpenWrt did not answer on $OPENWRT — check the unit, it may need UART recovery"
fi
ok "initramfs is up"

say "uploading the permanent sysupgrade"
run '"${SCP_NEW[@]}" "$SYSUPGRADE_PATH" root@"$OPENWRT":/tmp/sysupgrade.bin'

say "flashing it (sysupgrade -n, settings are not kept)"
run '"${SSH_NEW[@]}" "sysupgrade -n /tmp/sysupgrade.bin"'

printf '\n'
ok "done. The unit reboots into OpenWrt at http://$OPENWRT — LuCI, root, no password."
printf '    If it does not come back, recovery is UART + TFTP: docs/models/JIDU%s.md\n' "$MODEL"
