import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import idu


OPENSSL = shutil.which("openssl")
KEY = "/etc/server.key"


def encrypt(source, target):
    subprocess.run(
        ["openssl", "enc", "-pbkdf2", "-e", "-aes256", "-k", KEY,
         "-in", str(source), "-out", str(target)],
        check=True, capture_output=True)
    return target


def decrypt(source, target):
    subprocess.run(
        ["openssl", "enc", "-pbkdf2", "-d", "-aes256", "-k", KEY,
         "-in", str(source), "-out", str(target)],
        check=True, capture_output=True)
    return target


def unpack(archive, destination):
    with tarfile.open(archive, "r:gz") as handle:
        handle.extractall(destination)


def make_config_backup(base, mwan3=True, rc_local=True, firewall_include=True,
                       rc_local_link=False):
    source = pathlib.Path(base) / "source"
    (source / "etc" / "config").mkdir(parents=True)
    (source / "etc" / "shadow").write_text(
        "root:$1$old$abcd:19000:0:99999:7:::\n"
        "guest:x:0:0:99999:7:::\n")
    os.chmod(source / "etc" / "shadow", 0o600)
    if mwan3:
        (source / "etc" / "mwan3.user").write_text("#!/bin/sh\n")
    if rc_local_link:
        (source / "etc" / "rc.local").symlink_to("/tmp/outside-rc.local")
    elif rc_local:
        (source / "etc" / "rc.local").write_text(
            "#!/bin/sh\n"
            "echo boot\n"
            "exit 0\n")
    (source / "etc" / "config" / "firewall").write_text(
        "config defaults\n"
        "\toption input 'ACCEPT'\n")
    if firewall_include:
        with open(source / "etc" / "config" / "firewall", "a") as handle:
            handle.write("\nconfig include\n\toption path '/etc/firewall.user'\n")
    (source / "etc" / "resolv.conf").symlink_to("/tmp/resolv.conf.auto")

    plain = pathlib.Path(base) / "plain.tar.gz"
    with tarfile.open(plain, "w:gz") as handle:
        handle.add(source, arcname=".")
    return encrypt(plain, pathlib.Path(base) / "config_backup.tar.gz")


@unittest.skipUnless(OPENSSL, "openssl is required for the offline backup route")
class BreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp)

    def run_breeze(self, backup, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            idu.breeze(str(backup), **kwargs)
        return captured.getvalue()

    def rebuilt(self, output):
        decrypted = self.temp / "rebuilt.tar.gz"
        decrypt(output, decrypted)
        root = self.temp / "rebuilt"
        root.mkdir()
        unpack(decrypted, root)
        return root

    def test_sets_root_password_and_dropbear_hooks(self):
        backup = make_config_backup(self.temp)
        output = self.temp / "encrypted_backup_mod.tar.gz"

        instructions = self.run_breeze(
            backup, out=str(output), root_password="CorrectHorse9", salt="abcdefgh")
        self.assertIn("ssh root@192.168.31.1", instructions)

        self.assertTrue(output.exists())
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        root = self.rebuilt(output)

        shadow = (root / "etc" / "shadow").read_text()
        self.assertIn("root:$1$abcdefgh$", shadow)
        self.assertIn("guest:x:0:0:99999:7:::", shadow)

        mwan3 = (root / "etc" / "mwan3.user").read_text()
        self.assertIn(idu.DROPBEAR_START, mwan3)
        self.assertTrue(mwan3.startswith("#!/bin/sh\n"))

        # rc.local is the hook that does not depend on Dual WAN, and the restore
        # must not swallow the vendor's own `exit 0`.
        rc_local = (root / "etc" / "rc.local").read_text()
        self.assertIn(idu.DROPBEAR_START, rc_local)
        self.assertLess(rc_local.index(idu.DROPBEAR_START),
                        rc_local.index("exit 0"))
        self.assertIn("echo boot", rc_local)

        firewall_user = (root / "etc" / "firewall.user").read_text()
        self.assertIn(idu.DROPBEAR_START, firewall_user)

        init = root / "etc" / "init.d" / "idu-ssh"
        self.assertTrue(init.exists())
        self.assertIn("START=99", init.read_text())
        self.assertTrue(os.access(init, os.X_OK))
        self.assertEqual(
            os.readlink(root / "etc" / "rc.d" / "S99idu-ssh"), "../init.d/idu-ssh")
        self.assertEqual(
            os.readlink(root / "etc" / "rc.d" / "K01idu-ssh"), "../init.d/idu-ssh")

    def test_installs_a_key_without_touching_the_password(self):
        backup = make_config_backup(self.temp)
        public = self.temp / "id_rsa.pub"
        public.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC7 test@example\n")
        output = self.temp / "mod.tar.gz"

        self.run_breeze(backup, out=str(output), key=str(public))

        root = self.rebuilt(output)
        self.assertIn("root:$1$old$abcd:", (root / "etc" / "shadow").read_text())
        for relative in ("etc/dropbear/authorized_keys", "root/.ssh/authorized_keys"):
            text = (root / relative).read_text()
            self.assertIn("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC7", text)
            self.assertEqual((root / relative).stat().st_mode & 0o777, 0o600)

    def test_key_and_password_can_both_be_set(self):
        backup = make_config_backup(self.temp)
        public = self.temp / "id_rsa.pub"
        public.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC7 test@example\n")
        output = self.temp / "mod.tar.gz"

        self.run_breeze(backup, out=str(output), key=str(public),
                        root_password="CorrectHorse9", salt="abcdefgh")

        root = self.rebuilt(output)
        self.assertIn("root:$1$abcdefgh$", (root / "etc" / "shadow").read_text())
        self.assertIn("ssh-rsa", (root / "root" / ".ssh" / "authorized_keys").read_text())

    def test_creates_mwan3_user_when_the_backup_has_none(self):
        backup = make_config_backup(self.temp, mwan3=False)
        output = self.temp / "mod.tar.gz"

        self.run_breeze(backup, out=str(output), root_password="CorrectHorse9")

        root = self.rebuilt(output)
        self.assertIn(idu.DROPBEAR_START,
                      (root / "etc" / "mwan3.user").read_text())

    def test_creates_rc_local_when_the_backup_has_none(self):
        backup = make_config_backup(self.temp, rc_local=False)
        output = self.temp / "mod.tar.gz"

        self.run_breeze(backup, out=str(output), root_password="CorrectHorse9")

        rc_local = (self.rebuilt(output) / "etc" / "rc.local").read_text()
        self.assertIn(idu.DROPBEAR_START, rc_local)

    def test_refuses_a_symlinked_start_hook(self):
        backup = make_config_backup(self.temp, rc_local_link=True)
        output = self.temp / "mod.tar.gz"

        with self.assertRaises(idu.IduError) as raised:
            self.run_breeze(backup, out=str(output),
                            root_password="CorrectHorse9")
        self.assertIn("symlink", str(raised.exception))
        self.assertFalse(output.exists(), "a rejected rebuild must leave no file")

    def test_leaves_firewall_user_alone_when_firewall_does_not_include_it(self):
        backup = make_config_backup(self.temp, firewall_include=False)
        output = self.temp / "mod.tar.gz"

        self.run_breeze(backup, out=str(output), root_password="CorrectHorse9")

        root = self.rebuilt(output)
        self.assertFalse((root / "etc" / "firewall.user").exists())
        self.assertIn(idu.DROPBEAR_START,
                      (root / "etc" / "rc.local").read_text())

    def test_rebuilt_entries_belong_to_root(self):
        backup = make_config_backup(self.temp)
        output = self.temp / "mod.tar.gz"

        self.run_breeze(backup, out=str(output), root_password="CorrectHorse9")

        decrypted = self.temp / "owned.tar.gz"
        decrypt(output, decrypted)
        with tarfile.open(decrypted, "r:gz") as archive:
            members = archive.getmembers()
        self.assertTrue(members)
        for member in members:
            self.assertEqual((member.uid, member.gid), (0, 0), member.name)

    def test_refuses_to_overwrite_the_original_backup(self):
        backup = make_config_backup(self.temp)
        with self.assertRaises(idu.IduError) as raised:
            idu.breeze(str(backup), out=str(backup), root_password="CorrectHorse9",
                       force=True)
        self.assertIn("overwrite the original", str(raised.exception))

    def test_refuses_to_replace_an_existing_output(self):
        backup = make_config_backup(self.temp)
        output = self.temp / "mod.tar.gz"
        output.write_text("keep me")

        with self.assertRaises(idu.IduError) as raised:
            self.run_breeze(backup, out=str(output), root_password="CorrectHorse9")
        self.assertIn("already exists", str(raised.exception))
        self.assertEqual(output.read_text(), "keep me")

    def test_force_replaces_an_existing_output(self):
        backup = make_config_backup(self.temp)
        output = self.temp / "mod.tar.gz"
        output.write_text("replace me")

        self.run_breeze(backup, out=str(output), root_password="CorrectHorse9",
                        force=True)
        self.assertNotEqual(output.read_bytes(), b"replace me")

    def test_rejects_a_short_root_password(self):
        backup = make_config_backup(self.temp)
        with self.assertRaises(idu.IduError):
            idu.breeze(str(backup), out=str(self.temp / "mod.tar.gz"),
                       root_password="short")

    def test_rejects_a_file_that_is_not_an_encrypted_backup(self):
        bogus = self.temp / "firmware.bin"
        bogus.write_bytes(b"\x00" * 64)
        with self.assertRaises(idu.IduError) as raised:
            idu.breeze(str(bogus), out=str(self.temp / "mod.tar.gz"),
                       root_password="CorrectHorse9")
        self.assertIn("could not decrypt", str(raised.exception))

    def test_rejects_a_path_traversal_member(self):
        archive = self.temp / "evil.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            info = tarfile.TarInfo("../escaped")
            info.size = 0
            handle.addfile(info)
        with tarfile.open(archive, "r:gz") as handle:
            with self.assertRaises(idu.IduError) as raised:
                idu._safe_extract(handle, str(self.temp / "out"))
        self.assertIn("unsafe path", str(raised.exception))
        self.assertFalse((self.temp / "escaped").exists())

    def test_ignores_macos_metadata_members(self):
        source = self.temp / "with_metadata"
        (source / "etc").mkdir(parents=True)
        (source / "etc" / "shadow").write_text("root:x:0:0:99999:7:::\n")
        (source / "._etc").write_bytes(b"junk")
        (source / "etc" / "._shadow").write_bytes(b"junk")
        plain = self.temp / "plain.tar.gz"
        with tarfile.open(plain, "w:gz") as handle:
            handle.add(source, arcname=".")
        backup = encrypt(plain, self.temp / "config_backup.tar.gz")
        output = self.temp / "mod.tar.gz"

        self.run_breeze(backup, out=str(output), root_password="CorrectHorse9")

        root = self.rebuilt(output)
        self.assertFalse((root / "._etc").exists())
        self.assertFalse((root / "etc" / "._shadow").exists())
