#!/usr/bin/env bash
#
# flash.sh — one entry point for JIDU root access, backup, and OpenWrt.
#
#   ./flash.sh                 verify the router -> unlock root SSH -> back it up
#   ./flash.sh check           can this unit be unlocked? (read-only, safe to run in bulk)
#   ./flash.sh unlock          root SSH only (persistent, survives reboots)
#   ./flash.sh backup          unlock if needed, then save the stock device data
#   ./flash.sh download        detect the model, download + verify its OpenWrt images
#   ./flash.sh flash           backup first, then download + install OpenWrt
#   ./flash.sh detect          identify the model, change nothing
#
# Options:
#   --router URL    router base URL (default https://192.168.31.1)
#   --password P    router admin password (prompted if omitted)
#   --key PATH      Optional SSH key. A new unlock clears the root password
#                   whether or not a key is supplied, and installs persistent
#                   SSH. Existing root SSH is left as found.
#   --address IP    local address the router should call back on (VPN/WSL)
#   --force         send the payloads even when check says NO (advanced)
#   -v, --verbose   show the per-command detail behind each method
#
# The router must be SET UP, not factory-fresh: a reset IDU keeps its API locked
# until the setup wizard is completed in the web UI. Reset it, finish the wizard
# (which sets the admin password), then run this and supply that password.
#
# On Linux and macOS, unlock/backup/flash may listen on port 80, which is
# privileged. If binding fails, run the affected command with sudo. On Linux you can instead
# allow unprivileged low ports for this boot:
#   sudo sysctl net.ipv4.ip_unprivileged_port_start=80
# On Windows, use .\flash.ps1 for unlock and backup: WSL2's default NAT cannot
# receive the router's callback. For OpenWrt downloads and flashing, use
# .\firmware\fwflash.ps1; see the README for model-specific commands.
#
# Only run against equipment you own or are explicitly authorised to test.
# Provided as is, without warranty, without liability — see the README.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROUTER="${ROUTER:-https://192.168.31.1}"
PASSWORD="${PASSWORD:-}"
KEY="${KEY:-}"
ADDRESS="${ADDRESS:-}"
FORCE=0
VERBOSE=0
NOBANNER=0
CMD=""

# Progress prefixes: [*] working, [+] success, [-] failed.
say()  { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
bad()  { printf '\033[1;31m[-]\033[0m %s\n' "$*" >&2; }

usage() {
  sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    unlock|backup|download|flash|detect|check) CMD="$1"; shift ;;
    --router)   ROUTER="$2";   shift 2 ;;
    --password) PASSWORD="$2"; shift 2 ;;
    --key)      KEY="$2";      shift 2 ;;
    --address)  ADDRESS="$2";  shift 2 ;;
    --force)    FORCE=1;       shift ;;
    -v|--verbose) VERBOSE=1;   shift ;;
    -h|--help)  usage; exit 0 ;;
    -*)         bad "unknown option: $1"; usage; exit 2 ;;
    *)          bad "unexpected argument: $1"; usage; exit 2 ;;
  esac
done
[ -n "$CMD" ] || CMD="auto"

DETECTED_MODEL=""
DETECTED_FAMILY=""

# ---- an interpreter that has `requests` ---------------------------------- #
#
# urllib3 v2 requires OpenSSL 1.1.1+ and complains on anything else — which
# includes every Python Apple ships, linked against LibreSSL. This tool only
# ever talks to the router with verification off, so the still-maintained
# urllib3 1.x costs nothing and keeps the output clean.
tls_ok() {
  "$1" -c 'import ssl, sys
sys.exit(0 if ssl.OPENSSL_VERSION.startswith("OpenSSL ")
         and ssl.OPENSSL_VERSION_INFO >= (1, 1, 1) else 1)' >/dev/null 2>&1
}

deps_ok() {
  "$1" -c 'import ssl, sys
try:
    import requests, urllib3
except ImportError:
    sys.exit(1)
tls = (ssl.OPENSSL_VERSION.startswith("OpenSSL ")
       and ssl.OPENSSL_VERSION_INFO >= (1, 1, 1))
sys.exit(0 if tls or urllib3.__version__.startswith("1.") else 1)' >/dev/null 2>&1
}

PIN=""
tls_ok python3 || PIN="urllib3<2"

PY=""
if deps_ok python3; then
  PY="python3"
elif [ -x "$HERE/.venv/bin/python" ] && deps_ok "$HERE/.venv/bin/python"; then
  PY="$HERE/.venv/bin/python"
else
  say "installing dependencies into $HERE/.venv ..."
  python3 -m venv "$HERE/.venv" || { bad "could not create a venv"; exit 1; }
  "$HERE/.venv/bin/pip" -q install --upgrade pip requests $PIN || { bad "pip failed"; exit 1; }
  PY="$HERE/.venv/bin/python"
fi

# ---- ssh key ------------------------------------------------------------- #
# Optional, and never generated: a new unlock clears root's password with or without a key.

# ---- password ------------------------------------------------------------ #
if [ -z "$PASSWORD" ]; then
  printf 'Router admin password: '
  read -rs PASSWORD
  echo
fi
[ -n "$PASSWORD" ] || { bad "no password given"; exit 2; }

# -u keeps Python's output unbuffered: piped through the driver it would
# otherwise sit in a block buffer and make a slow login look like a hang.
idu() {
  local _args=( --router "$ROUTER" --password "$PASSWORD" )
  [ -n "$KEY" ] && _args+=( --key "$KEY" )
  [ -n "$ADDRESS" ] && _args+=( --address "$ADDRESS" )
  [ "$VERBOSE" -eq 1 ] && _args+=( --verbose )
  [ "$NOBANNER" -eq 1 ] && _args+=( --no-banner )
  # --force belongs to the unlock subcommand, so it goes after the command name.
  # backup's inner `idu unlock` still gets it.
  if [ "$FORCE" -eq 1 ] && [ "${1:-}" = "unlock" ]; then
    "$PY" -u "$HERE/idu.py" "${_args[@]}" "$@" --force
  else
    "$PY" -u "$HERE/idu.py" "${_args[@]}" "$@"
  fi
}

describe() {
  say "Connecting to ${ROUTER#*//}"
  local out
  if ! out="$(idu detect)"; then
    bad "could not take over the router. Usual causes:"
    bad "  * it is unreachable, or an admin session is already open;"
    bad "  * it is factory-reset - finish the setup wizard in the web UI first;"
    bad "  * the password is wrong (the router locks out after ~5 tries)."
    exit 1
  fi
  DETECTED_MODEL="$(printf '%s\n' "$out" | sed -n 's/^MODEL=//p' | tail -n 1)"
  DETECTED_FAMILY="$(printf '%s\n' "$out" | sed -n 's/^FAMILY=//p' | tail -n 1)"
  # MODEL=/FAMILY= are how this driver reads the family; the user gets the two
  # human-readable lines instead.
  printf '%s\n' "$out" | grep -v -e '^MODEL=' -e '^FAMILY='
  NOBANNER=1        # shown once, above - don't repeat it on every later call
}

firmware_model() {
  case "$DETECTED_MODEL" in
    JIDU6101) echo "6101" ;;
    JIDU6J01|JIDU6201|JIDU6401|JIDU6601|JIDU6701) echo "6j01" ;;
    JIDU6J11|JIDU6111|JIDU6411|JIDU6611|JIDU6811|JIDU6911) echo "6j11" ;;
    *)
      bad "no OpenWrt image set is registered for model: ${DETECTED_MODEL:-unknown}"
      return 1
      ;;
  esac
}

run_firmware() {
  local action="$1" model host
  local flasher="$HERE/firmware/fwflash.sh"

  [ -x "$flasher" ] || {
    bad "missing firmware flasher: $flasher"
    return 1
  }

  model="$(firmware_model)" || return 1
  host="$("$PY" -c 'from urllib.parse import urlparse; import sys; print(urlparse(sys.argv[1]).hostname or sys.argv[1])' "$ROUTER")" \
    || { bad "could not parse router URL: $ROUTER"; return 1; }

  local args=( "$model" --router "$host" )
  [ "$VERBOSE" -eq 1 ] && args+=( --verbose )
  [ "$action" = "download" ] && args+=( --download-only )

  PASSWORD="$PASSWORD" KEY="$KEY" ADDRESS="$ADDRESS" \
    "$flasher" "${args[@]}"
}

case "$CMD" in
  detect)
    idu detect || exit 1
    ;;

  check)
    idu check
    exit $?
    ;;

  unlock)
    describe
    idu unlock || exit 1
    ;;

  backup)
    describe
    idu unlock || exit 1
    idu backup --outdir "$PWD" || exit 1
    ;;

  download)
    describe
    run_firmware download || exit 1
    ;;

  flash)
    [ -x "$HERE/firmware/fwflash.sh" ] || {
      bad "missing firmware flasher: $HERE/firmware/fwflash.sh"
      exit 1
    }
    describe
    firmware_model >/dev/null || exit 1
    say "Unlock enables persistent root SSH. If flashing fails, stock may remain unlocked."
    say "Backing up stock firmware before flashing..."
    idu unlock || exit 1
    idu backup --outdir "$PWD" || exit 1
    run_firmware flash || exit 1
    ;;

  auto)
    describe
    idu unlock || exit 1
    idu backup --outdir "$PWD" || exit 1
    ;;
esac
