#!/usr/bin/env bash
#
# flash.sh — root access + full backup for JIDU routers. No firmware is written.
#
#   ./flash.sh                 verify the router -> unlock root SSH -> back it up
#   ./flash.sh check           can this unit be unlocked? (read-only, safe to run in bulk)
#   ./flash.sh unlock          root SSH only (persistent, survives reboots)
#   ./flash.sh backup          factory credentials + a copy of every partition
#   ./flash.sh detect          identify the model, change nothing
#
# Options:
#   --router URL    router base URL (default https://192.168.31.1)
#   --password P    router admin password (prompted if omitted)
#   --key PATH      SSH key. Optional: with no key root is left passwordless and
#                   nothing of ours is installed on the router
#   -v, --verbose   show the per-command detail behind each method
#
# The router must be SET UP, not factory-fresh: a reset IDU keeps its API locked
# until the setup wizard is completed in the web UI. Reset it, finish the wizard
# (which sets the admin password), then run this and supply that password.
#
# Only run against equipment you own or are explicitly authorised to test.
# Provided as is, without warranty, without liability — see the README.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROUTER="${ROUTER:-https://192.168.31.1}"
PASSWORD="${PASSWORD:-}"
KEY="${KEY:-}"
VERBOSE=0
NOBANNER=0
CMD=""

# Progress prefixes: [*] working, [+] success, [-] failed.
say()  { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
bad()  { printf '\033[1;31m[-]\033[0m %s\n' "$*" >&2; }

usage() {
  sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    unlock|backup|detect|check) CMD="$1"; shift ;;
    --router)   ROUTER="$2";   shift 2 ;;
    --password) PASSWORD="$2"; shift 2 ;;
    --key)      KEY="$2";      shift 2 ;;
    -v|--verbose) VERBOSE=1;   shift ;;
    -h|--help)  usage; exit 0 ;;
    flash)      bad "this tool no longer writes firmware — use it for root access and backups."; exit 2 ;;
    -*)         bad "unknown option: $1"; usage; exit 2 ;;
    *)          bad "unexpected argument: $1"; usage; exit 2 ;;
  esac
done
[ -n "$CMD" ] || CMD="auto"

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
# Optional, and never generated: with no --key the unlock leaves root
# passwordless and installs nothing on the router.

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
  [ "$VERBOSE" -eq 1 ] && _args+=( --verbose )
  [ "$NOBANNER" -eq 1 ] && _args+=( --no-banner )
  "$PY" -u "$HERE/idu.py" "${_args[@]}" "$@"
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
  # MODEL=/FAMILY= are how this driver reads the family; the user gets the two
  # human-readable lines instead.
  printf '%s\n' "$out" | grep -v -e '^MODEL=' -e '^FAMILY='
  NOBANNER=1        # shown once, above - don't repeat it on every later call
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

  auto)
    describe
    idu unlock || exit 1
    idu backup --outdir "$PWD" || exit 1
    ;;
esac
