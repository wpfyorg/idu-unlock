# Offline root SSH from a configuration backup

Some early builds cannot be unlocked over the network. On both hardware
families, units on **`R2.0.19.0` and older** usually predate the
password-history shell-out that `./flash.sh unlock` uses, so `./flash.sh check`
reports `NO` and the API route stops before sending a payload.

If that unit's web UI still offers **Backup Settings** and **Restore Settings**,
you do not need UART yet. You can download the encrypted configuration backup,
let this project modify it, restore it, and get root SSH without opening the
router. This is the same idea as the community
[`breeze.sh`](https://github.com/abhigyan17/Airfiber_Unlock/blob/main/scripts/breeze.sh)
from [abhigyan17/Airfiber_Unlock](https://github.com/abhigyan17/Airfiber_Unlock),
built into `./flash.sh` with key support and a persistent SSH init script.

> [!WARNING]
> Use this only on hardware you own or are explicitly authorized to modify.
> Restoring a modified configuration can make the router unreachable, and the
> modified file still contains the unit's Wi-Fi passwords and factory
> credentials. Keep it private. This route is for recovery, not for resale or
> for devices you do not control.

## When to use it

Use `breeze` when all of these are true:

- `./flash.sh check` reports `NO` for an older build, or `unlock` stops with
  *this build does not record password history*;
- the web UI still has **Administration → Management → Backup Settings** and
  **Restore Settings**;
- you have Ethernet access to the router and can log in to its web UI.

Do **not** use it when the normal network unlock already works. `check` reporting
`YES` means `./flash.sh unlock` is the simpler and safer route.

| Unit | Typical result | What to use |
| --- | --- | --- |
| MediaTek `6j01`, `R2.0.19.0` and older | `NO` | This page |
| MediaTek `6j01`, `R2.0.19.6`–`R3.2.0` | `YES` | `./flash.sh unlock` |
| Qualcomm `6j11`, early `R2.x` builds | probe decides, often `NO` | This page |
| Qualcomm `6j11`, `R3.2.6` and earlier | `YES` | `./flash.sh unlock` |
| Either family, `R3.2.3`+/fixed builds | `NO` | UART is the remaining route |

## How it works

The stock firmware exports its configuration as a `tar.gz` encrypted with the
vendor's fixed passphrase. The same firmware accepts that archive back through
the restore page. `breeze` works entirely on the file:

1. decrypt the backup with OpenSSL and the stock key;
2. set the root password hash in `etc/shadow`, or install your SSH public key;
3. add `dropbear -p 0.0.0.0:22` to `etc/mwan3.user`, which stock firmware sources
   when Dual WAN starts;
4. add `/etc/init.d/idu-ssh` plus `S99`/`K01` links, so SSH survives later boots;
5. repack and re-encrypt the archive as `encrypted_backup_mod.tar.gz`.

Nothing is sent to the router until you upload the file in the web UI. No
callback server, port 80, or admin API session is involved.

## Step 1 — Confirm the web UI can back up and restore

Connect the router to your Mac or Ubuntu machine with an Ethernet cable, then
open:

```text
https://192.168.31.1
```

Go to **Administration → Management** and check that both **Backup Settings**
and **Restore Settings** are present.

| What you see | What it means |
| --- | --- |
| Backup + Restore | Use this page |
| Firmware File + Signature File only | Downgrade to a matching build first, or use UART |
| Firmware File only | No configuration backup route; UART is required |

A firmware downgrade needs files that exactly match the model. If the web UI
does not offer restore at all, stop and use the UART route on your model page.

## Step 2 — Download the configuration backup

In **Administration → Management → Backup Settings**, download the current
configuration. Save it in `~/Downloads`.

```text
~/Downloads/
├── YOUR_BACKUP_FILE
```

Keep an untouched copy. It contains Wi-Fi passwords, factory credentials, and
serial data, so do not upload it anywhere.

## Step 3 — Prepare the machine

The command runs locally and needs `openssl`.

Ubuntu:

```bash
sudo apt update
sudo apt install -y openssl bash
```

macOS ships OpenSSL and Bash. If `openssl` is missing:

```bash
brew install openssl
```

Clone this project if you have not already:

```bash
git clone https://github.com/wpfyorg/idu-unlock.git
cd idu-unlock
```

Windows users can run the same command inside WSL: `breeze` is offline, so the
WSL2 callback limitation does not apply. Keep the backup file under `/mnt/c/...`
so WSL can see it. `flash.ps1` does not expose this command yet.

## Step 4 — Rebuild the backup

From the project directory, with the backup file path:

```bash
./flash.sh breeze ~/Downloads/YOUR_BACKUP_FILE
```

You will be asked for a new root password twice. To avoid the prompt:

```bash
./flash.sh breeze ~/Downloads/YOUR_BACKUP_FILE --root-password 'your-new-password'
```

Or install an RSA public key instead of setting a password:

```bash
./flash.sh breeze ~/Downloads/YOUR_BACKUP_FILE --key ~/.ssh/id_rsa
```

`--key` reads `~/.ssh/id_rsa.pub` and writes it to both
`/etc/dropbear/authorized_keys` and `/root/.ssh/authorized_keys` inside the
backup. The stock Dropbear build may reject Ed25519 keys, so RSA is the safe
choice. You can pass both `--key` and `--root-password`.

The command writes `encrypted_backup_mod.tar.gz` in the current directory:

```text
encrypted_backup_mod.tar.gz
```

Use `--out PATH` to write somewhere else, and `--force` to replace an existing
file. The output is created with mode `0600`.

The command refuses to continue if:

- the file cannot be decrypted with the stock key;
- the archive is not a valid `tar.gz` or has no `etc/shadow`;
- the password is shorter than eight characters;
- the output already exists without `--force`.

The rebuilt archive is decrypted again after encryption and checked before the
command reports success.

## Step 5 — Restore the modified backup

Open the router web UI:

```text
https://192.168.31.1
```

Go to **Administration → Management → Restore Settings**, choose
`encrypted_backup_mod.tar.gz`, and confirm.

The router restarts. Wait for it to come back and log in to the web UI again
with the existing administrator password. Restoring the configuration does not
change that web password; `breeze` changes only the **root** account used for
SSH.

## Step 6 — Start Dropbear with Dual WAN

Some stock builds do not start Dropbear from the restored init script until a
service reload. Dual WAN forces `mwan3` to run, and `mwan3` sources
`/etc/mwan3.user`, which now starts Dropbear.

Log in to the web UI, then open:

```text
https://192.168.31.1/#/WAN/DualWan
```

or navigate to **WAN → Dual WAN**. Enable Dual WAN, save, and let the router
restart. It may restart more than once; wait for Ethernet to reconnect.

After SSH works, **disable Dual WAN again**. It is only used to start Dropbear
once and can interfere with normal WAN behavior.

> If your build started SSH directly from the restored init script, you can skip
> this step. Try Step 7 first; only enable Dual WAN if the connection is refused.

## Step 7 — Log in as root

With a root password:

```bash
ssh root@192.168.31.1
```

Enter the root password you set in Step 4, not the web administrator password.

With a key:

```bash
ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes root@192.168.31.1
```

Accept the host key only if the address is your router. Verify:

```bash
whoami
```

Expected output:

```text
root
```

The stock Dropbear may regenerate its host key on every start, so a later
connection can warn that the host key changed. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Step 8 — Confirm SSH survives a reboot

The rebuilt backup includes `/etc/init.d/idu-ssh` and its `S99`/`K01` links.
Check that the restore kept them:

```bash
ls -l /etc/rc.d/S99idu-ssh
```

If the link is present, reboot and connect again:

```bash
reboot
```

If the restore dropped the init script, recreate it while still connected:

```bash
cat >/etc/init.d/idu-ssh <<'EOF'
#!/bin/sh /etc/rc.common
START=99
STOP=01
start() { dropbear -R -p 0.0.0.0:22; }
stop()  { killall dropbear; }
reload() { start; }
EOF
chmod +x /etc/init.d/idu-ssh
ln -sf ../init.d/idu-ssh /etc/rc.d/S99idu-ssh
ln -sf ../init.d/idu-ssh /etc/rc.d/K01idu-ssh
```

Do not rely on `/etc/rc.local` on these builds. The stock firmware has no
`/etc/init.d/rc.local`, so an `exit 0` edit there does nothing.

## Step 9 — Back up, then install OpenWrt

Root SSH is now available, so the normal project route works:

```bash
./flash.sh backup
./flash.sh flash
```

`backup` detects the existing root session instead of re-running the exploit.
`flash` performs a fresh backup, downloads and verifies the matching images,
and installs OpenWrt. Read [OPENWRT.md](../OPENWRT.md) before flashing.

## Manual `breeze.sh` route

The integrated command is the recommended path because it adds the persistent
init script, supports keys, and safely extracts the archive. To use the original
community script directly:

```bash
cd ~/Downloads
curl -LO https://raw.githubusercontent.com/abhigyan17/Airfiber_Unlock/main/scripts/breeze.sh
chmod +x breeze.sh
bash breeze.sh YOUR_BACKUP_FILE
```

It prompts for a desired root password and a salt, then writes
`encrypted_backup_mod.tar.gz`. The salt is only used to build the password hash;
it is not the router administrator password. The script appends Dropbear to
`/etc/mwan3.user` (or `/etc/firewall.user`) and leaves persistence to you.

Project and script:

- [abhigyan17/Airfiber_Unlock](https://github.com/abhigyan17/Airfiber_Unlock)
- [`scripts/breeze.sh`](https://github.com/abhigyan17/Airfiber_Unlock/blob/main/scripts/breeze.sh)

## Troubleshooting

**`could not decrypt ...`**
The file is not the encrypted configuration backup. Use the file from
**Backup Settings**, not a firmware image or a partition dump.

**The web UI rejects `encrypted_backup_mod.tar.gz`**
Confirm the file was produced by this command and was not renamed or edited
afterwards. Re-run with `--force` if a stale output was reused.

**SSH connection refused after the restore**
Enable Dual WAN once (Step 6). If it still fails, connect over UART and start
`dropbear -p 0.0.0.0:22` by hand.

**SSH asks for a password but the root password is rejected**
Use the password set in Step 4. The web administrator password is separate.
Wait a minute between attempts; the stock login handler blocks after repeated
failures.

**`Permission denied (publickey)` with `--key`**
The stock build may reject Ed25519. Create and re-run with an RSA key:

```bash
ssh-keygen -t rsa -b 2048 -f ~/.ssh/idu_rsa
./flash.sh breeze ~/Downloads/YOUR_BACKUP_FILE --key ~/.ssh/idu_rsa --force
```

**SSH works now but not after a reboot**
Check the `S99idu-ssh` link and recreate it with the block in Step 8.

## Safety notes

- Keep both the original and modified backups private; they contain credentials.
- Do not use `0.0.0.0:22` with SSH exposed to the WAN. The stock firewall should
  block it, but verify before putting the unit on an untrusted network.
- Restore the untouched backup if you need to return to the exact previous
  configuration.
- The route is only for units whose web UI offers configuration restore. Units
  without it still need UART or a supported network unlock.
