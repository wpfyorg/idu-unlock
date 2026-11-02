import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "firmware" / "manifest.json"


class FirmwareManifestTest(unittest.TestCase):
    """The flashers trust manifest.json blindly, so it has to be well formed."""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MANIFEST.read_text())

    def test_models_present(self):
        self.assertEqual(sorted(self.data["models"]), ["6101", "6j01", "6j11"])

    def test_every_model_has_a_title_and_aliases(self):
        for name, spec in self.data["models"].items():
            with self.subTest(model=name):
                self.assertTrue(spec["title"].startswith("JIDU"))
                self.assertTrue(spec["aliases"])
                self.assertTrue(
                    any(alias.startswith("JIDU" + name.upper()) for alias in spec["aliases"]),
                    f"{name}: no alias names this model itself",
                )

    def test_roles_are_the_ones_the_flashers_ask_for(self):
        for name, spec in self.data["models"].items():
            with self.subTest(model=name):
                roles = set(spec["images"])
                self.assertIn("factory", roles)
                self.assertTrue({"sysupgrade", "initramfs"} & roles)

    def test_flasher_flag_matches_what_has_an_onrouter_script(self):
        for name, spec in self.data["models"].items():
            with self.subTest(model=name):
                script = ROOT / "firmware" / "onrouter" / f"{name}.sh"
                self.assertEqual(spec["flasher"], script.exists())

    def test_images_are_fully_described(self):
        base = self.data["base_url"]
        for name, spec in self.data["models"].items():
            for role, image in spec["images"].items():
                with self.subTest(model=name, role=role):
                    self.assertRegex(image["sha256"], r"^[0-9a-f]{64}$")
                    self.assertGreater(image["size"], 1_000_000)
                    self.assertEqual(image["url"], f"{base}/{image['name']}")
                    self.assertTrue(image["name"].endswith((".bin", ".ubi", ".itb")))
                    self.assertNotIn(" ", image["name"])

    def test_release_url_is_pinned_to_a_tag_not_a_moving_branch(self):
        self.assertRegex(
            self.data["base_url"],
            r"^https://github\.com/wpfyorg/idu-unlock/releases/download/[^/]+$",
        )


class FlashScriptTest(unittest.TestCase):
    """The shell entrypoints must stay runnable and reference real models."""

    def test_flash_command_passes_url_hostname_to_ssh_flasher(self):
        python = shutil.which("python3")
        if not python:
            self.skipTest("python3 is not installed")

        cases = (
            ("https://192.168.31.1", "192.168.31.1"),
            ("http://192.168.31.1:8080/WCGI", "192.168.31.1"),
            ("https://router.local", "router.local"),
            ("192.168.31.1", "192.168.31.1"),
        )
        for router_url, ssh_host in cases:
            with self.subTest(router_url=router_url), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                fake_bin = root / "bin"
                firmware = root / "firmware"
                fake_bin.mkdir()
                firmware.mkdir()
                shutil.copy2(ROOT / "flash.sh", root / "flash.sh")
                python_stub = fake_bin / "python3"
                python_stub.write_text(
                    "#!/usr/bin/env bash\n"
                    "if [ \"$1\" = '-c' ]; then\n"
                    "  case \"$2\" in *urlparse*) exec \"$REAL_PYTHON\" \"$@\" ;; esac\n"
                    "  exit 0\n"
                    "fi\n"
                    "if [ \"$1\" = '-u' ]; then\n"
                    "  shift; script=$1; shift\n"
                    "  case \"$script\" in */idu.py)\n"
                    "    printf '%s\\n' \"$@\" > \"$DETECT_ARGS\"\n"
                    "    printf 'MODEL=JIDU6101\\nFAMILY=mediatek\\n'\n"
                    "    exit 0 ;;\n"
                    "  esac\n"
                    "fi\n"
                    "exit 90\n"
                )
                os.chmod(python_stub, 0o755)
                flasher = firmware / "fwflash.sh"
                flasher.write_text(
                    "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$FLASH_ARGS\"\n"
                )
                os.chmod(flasher, 0o755)

                detect_args = root / "detect.args"
                flash_args = root / "flash.args"
                env = os.environ.copy()
                env.update(
                    PATH=f"{fake_bin}{os.pathsep}{env['PATH']}",
                    REAL_PYTHON=python,
                    DETECT_ARGS=str(detect_args),
                    FLASH_ARGS=str(flash_args),
                    PASSWORD="test-password",
                )
                result = subprocess.run(
                    ["bash", str(root / "flash.sh"), "download", "--router", router_url],
                    text=True,
                    capture_output=True,
                    env=env,
                    cwd=root,
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(flash_args.read_text().splitlines()[1:3], ["--router", ssh_host])
                self.assertEqual(
                    detect_args.read_text().splitlines()[0:2], ["--router", router_url]
                )

    def _bash_fixture(self, root):
        firmware = root / "firmware"
        onrouter = firmware / "onrouter"
        cache = root / "cache" / "6101"
        fake_bin = root / "bin"
        onrouter.mkdir(parents=True)
        cache.mkdir(parents=True)
        fake_bin.mkdir()

        flasher = firmware / "fwflash.sh"
        shutil.copy2(ROOT / "firmware" / "fwflash.sh", flasher)
        (onrouter / "6101.sh").write_text("#!/bin/sh\nexit 0\n")

        factory = cache / "factory.ubi"
        sysupgrade = cache / "sysupgrade.bin"
        factory.write_bytes(b"factory fixture")
        sysupgrade.write_bytes(b"sysupgrade fixture")

        def image(path):
            return {
                "name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
                "url": f"https://invalid.example/{path.name}",
            }

        (firmware / "manifest.json").write_text(
            json.dumps(
                {
                    "models": {
                        "6101": {
                            "title": "JIDU6101 test fixture",
                            "aliases": ["JIDU6101"],
                            "flasher": True,
                            "images": {
                                "factory": image(factory),
                                "sysupgrade": image(sysupgrade),
                            },
                        }
                    }
                }
            )
        )
        return flasher, cache.parent, fake_bin

    def _run_bash_fixture(self, flasher, cache, fake_bin, trace):
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
        env["TRACE"] = str(trace)
        return subprocess.run(
            ["bash", str(flasher), "6101", "--cache", str(cache), "--yes"],
            text=True,
            capture_output=True,
            env=env,
            cwd=flasher.parent.parent,
        )

    def test_scripts_are_executable_and_syntax_checked_elsewhere(self):
        for name in ("fwflash.sh", "fwflash.ps1"):
            self.assertTrue((ROOT / "firmware" / name).exists())

    def test_onrouter_scripts_guard_the_partition_they_write(self):
        for name in ("6101.sh", "6j01.sh", "6j11.sh"):
            body = (ROOT / "firmware" / "onrouter" / name).read_text()
            with self.subTest(script=name):
                # the partition is looked up, never hard-coded...
                self.assertIn("/proc/mtd", body)
                self.assertNotIn("ubiformat /dev/mtd", body)
                # ...and an empty lookup must stop the script before ubiformat
                self.assertIn('[ -z "$DEV" ]', body)
                # a failed ubiformat must not be followed by fw_setenv + reboot
                self.assertIn("set -e", body)
                self.assertLess(body.index("set -e"), body.index("\nubiformat "))

    def test_onrouter_scripts_use_the_exact_uploaded_image(self):
        """A glob over /tmp can pick another model's factory image."""
        for name in ("6101.sh", "6j01.sh", "6j11.sh"):
            body = (ROOT / "firmware" / "onrouter" / name).read_text()
            with self.subTest(script=name):
                self.assertIn("/tmp/jidu-factory.ubi", body)
                self.assertNotIn("ls /tmp/*factory.ubi", body)

    def test_bash_flasher_checks_the_result_of_every_remote_step(self):
        body = (ROOT / "firmware" / "fwflash.sh").read_text()
        self.assertIn("run_must", body)
        self.assertIn("run_until_reboot", body)
        self.assertIn("sysupgrade refused the image", body)

    def test_powershell_native_calls_go_through_the_exit_code_helpers(self):
        """`& ssh ...` returns output, so $rc would be an array, not a status."""
        body = (ROOT / "firmware" / "fwflash.ps1").read_text()
        self.assertNotIn("Invoke-Remote", body)
        for call in ("$rc = Invoke-Ssh", "$rc = Invoke-Scp", "(Test-Ssh "):
            self.assertIn(call, body)
        self.assertEqual(body.count('$payload = $Command + "`n#"'), 3)
        self.assertEqual(body.count("$payload | & ssh @Options $Target 'sh -s'"), 3)
        # output must go to the console, not into the caller's variable
        self.assertEqual(body.count("| Out-Host"), 2)
        # 2>&1 turns native stderr into a terminating error on PowerShell 5.1
        self.assertNotIn("2>&1", body)

    def test_flashers_unlock_the_unit_themselves(self):
        """One command: no separate `./flash.sh unlock` beforehand."""
        sh = (ROOT / "firmware" / "fwflash.sh").read_text()
        ps = (ROOT / "firmware" / "fwflash.ps1").read_text()
        # both hand off to the unlocker in the repo root, with the stock address
        self.assertIn('local unlock_args=(unlock --router "https://$STOCK")', sh)
        self.assertIn('"$UNLOCKER" "${unlock_args[@]}"', sh)
        self.assertIn("unlock --router \"https://$Router\"", ps)
        # the two hosts call out to each other's script, not to a copy
        self.assertIn('UNLOCKER="$HERE/../flash.sh"', sh)
        self.assertIn("'flash.ps1'", ps)
        # the old "unlock first" refusal must not come back
        for body, name in ((sh, "fwflash.sh"), (ps, "fwflash.ps1")):
            with self.subTest(script=name):
                self.assertNotIn("unlock first:", body)
        # a dry run reaches neither the unit nor the unlocker
        self.assertIn("would check root SSH", sh)
        self.assertIn("would check root SSH", ps)

    def test_flashers_isolate_stock_host_keys(self):
        sh = (ROOT / "firmware" / "fwflash.sh").read_text()
        ps = (ROOT / "firmware" / "fwflash.ps1").read_text()
        self.assertIn('UserKnownHostsFile="$STOCK_KNOWN_HOSTS"', sh)
        self.assertIn('UserKnownHostsFile=$stockKh', ps)

    def test_windows_flasher_forwards_the_stock_ssh_key(self):
        ps = (ROOT / "firmware" / "fwflash.ps1").read_text()
        self.assertIn('[string]$Key', ps)
        self.assertIn("--key $Key", ps)
        self.assertIn("'-i', $Key", ps)
        self.assertIn('automatic unlock on Windows needs an RSA key', ps)

    def test_bash_flasher_forwards_the_stock_ssh_key(self):
        sh = (ROOT / "firmware" / "fwflash.sh").read_text()
        self.assertIn('--key)           KEY="$2"', sh)
        self.assertIn('-i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes', sh)
        self.assertIn('unlock_args+=(--key "$KEY")', sh)

    def test_flashers_verify_the_connected_model_before_uploading(self):
        sh = (ROOT / "firmware" / "fwflash.sh").read_text()
        ps = (ROOT / "firmware" / "fwflash.ps1").read_text()
        for body, name in ((sh, "fwflash.sh"), (ps, "fwflash.ps1")):
            with self.subTest(script=name):
                self.assertIn("/tmp/deviceModel", body)
                self.assertIn("aliases", body)
                self.assertIn("but the selected image set is", body)
        self.assertLess(sh.index("\nverify_connected_model\n"), sh.index("uploading the factory image"))
        self.assertLess(ps.index("but the selected image set is"), ps.index("uploading the factory image"))

    def test_bash_flasher_rejects_wrong_model_before_any_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            flasher, cache, fake_bin = self._bash_fixture(root)
            trace = root / "scp.log"

            (fake_bin / "ssh").write_text(
                "#!/usr/bin/env bash\n"
                "for arg in \"$@\"; do last=\"$arg\"; done\n"
                "if [ \"$last\" = 'sh -s' ]; then IFS= read -r last || last=''; fi\n"
                "case \"$last\" in\n"
                "  'cat /proc/mtd >/dev/null') exit 0 ;;\n"
                "  'cat /tmp/deviceModel 2>/dev/null') printf 'JIDU6J01\\n'; exit 0 ;;\n"
                "  *) exit 90 ;;\n"
                "esac\n"
            )
            (fake_bin / "scp").write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$TRACE\"\nexit 0\n"
            )
            os.chmod(fake_bin / "ssh", 0o755)
            os.chmod(fake_bin / "scp", 0o755)

            result = self._run_bash_fixture(flasher, cache, fake_bin, trace)
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("connected router is JIDU6J01, but the selected image set is 6101", output)
            self.assertFalse(trace.exists(), "model mismatch must stop before scp")

    def test_powershell_flasher_rejects_wrong_model_before_any_upload(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _, cache, fake_bin = self._bash_fixture(root)
            flasher = root / "firmware" / "fwflash.ps1"
            shutil.copy2(ROOT / "firmware" / "fwflash.ps1", flasher)
            trace = root / "scp.log"

            (fake_bin / "ssh").write_text(
                "#!/usr/bin/env bash\n"
                "for arg in \"$@\"; do last=\"$arg\"; done\n"
                "if [ \"$last\" = 'sh -s' ]; then IFS= read -r last || last=''; fi\n"
                "case \"$last\" in\n"
                "  'cat /proc/mtd >/dev/null') exit 0 ;;\n"
                "  'cat /tmp/deviceModel 2>/dev/null') printf 'JIDU6J01\\n'; exit 0 ;;\n"
                "  *) exit 90 ;;\n"
                "esac\n"
            )
            (fake_bin / "scp").write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$TRACE\"\nexit 0\n"
            )
            os.chmod(fake_bin / "ssh", 0o755)
            os.chmod(fake_bin / "scp", 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["TRACE"] = str(trace)
            result = subprocess.run(
                [powershell, "-NoProfile", "-File", str(flasher), "6101", "-Cache", str(cache), "-Yes"],
                text=True,
                capture_output=True,
                env=env,
                cwd=root,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("connected router is JIDU6J01, but the selected image set is 6101", output)
            self.assertFalse(trace.exists(), "model mismatch must stop before scp")

    def test_powershell_flasher_rejects_different_initramfs_before_sysupgrade_upload(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _, cache, fake_bin = self._bash_fixture(root)
            flasher = root / "firmware" / "fwflash.ps1"
            shutil.copy2(ROOT / "firmware" / "fwflash.ps1", flasher)
            trace = root / "scp.log"
            stock_hash = "d" * 64
            other_hash = "e" * 64

            (fake_bin / "ssh").write_text(
                "#!/usr/bin/env bash\n"
                "target=''\nlast=''\n"
                "for arg in \"$@\"; do case \"$arg\" in root@*) target=\"$arg\" ;; esac; last=\"$arg\"; done\n"
                "if [ \"$last\" = 'sh -s' ]; then IFS= read -r last || last=''; fi\n"
                "case \"$last\" in\n"
                "  'cat /proc/mtd >/dev/null') exit 0 ;;\n"
                "  'cat /tmp/deviceModel 2>/dev/null') printf 'JIDU6101\\n'; exit 0 ;;\n"
                "  'sh /tmp/jidu-flash.sh') exit 255 ;;\n"
                "  'true') exit 0 ;;\n"
                "esac\n"
                "case \"$last\" in *sha256sum*)\n"
                f"  if [ \"$target\" = 'root@192.168.31.1' ]; then printf '{stock_hash}\\n'; else printf '{other_hash}\\n'; fi\n"
                "  exit 0 ;;\n"
                "esac\n"
                "exit 90\n"
            )
            (fake_bin / "scp").write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$TRACE\"\nexit 0\n"
            )
            os.chmod(fake_bin / "ssh", 0o755)
            os.chmod(fake_bin / "scp", 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["TRACE"] = str(trace)
            result = subprocess.run(
                [powershell, "-NoProfile", "-File", str(flasher), "6101", "-Cache", str(cache), "-Yes"],
                text=True,
                capture_output=True,
                env=env,
                cwd=root,
            )
            output = result.stdout + result.stderr
            uploads = trace.read_text() if trace.exists() else ""
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("different router; refusing to upload sysupgrade", output)
            self.assertIn("root@192.168.31.1:/tmp/jidu-factory.ubi", uploads)
            self.assertNotIn("root@192.168.1.1:/tmp/sysupgrade.bin", uploads)

    def test_bash_flasher_rejects_different_initramfs_before_sysupgrade_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            flasher, cache, fake_bin = self._bash_fixture(root)
            trace = root / "scp.log"

            stock_hash = "a" * 64
            other_hash = "b" * 64
            (fake_bin / "ssh").write_text(
                "#!/usr/bin/env bash\n"
                "target=''\nlast=''\n"
                "for arg in \"$@\"; do case \"$arg\" in root@*) target=\"$arg\" ;; esac; last=\"$arg\"; done\n"
                "if [ \"$last\" = 'sh -s' ]; then IFS= read -r last || last=''; fi\n"
                "case \"$last\" in\n"
                "  'cat /proc/mtd >/dev/null') exit 0 ;;\n"
                "  'cat /tmp/deviceModel 2>/dev/null') printf 'JIDU6101\\n'; exit 0 ;;\n"
                "  'sh /tmp/jidu-flash.sh') exit 255 ;;\n"
                "  'true') exit 0 ;;\n"
                "esac\n"
                "case \"$last\" in *sha256sum*)\n"
                f"  if [ \"$target\" = 'root@192.168.31.1' ]; then printf '{stock_hash}\\n'; else printf '{other_hash}\\n'; fi\n"
                "  exit 0 ;;\n"
                "esac\n"
                "exit 90\n"
            )
            (fake_bin / "scp").write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$TRACE\"\nexit 0\n"
            )
            os.chmod(fake_bin / "ssh", 0o755)
            os.chmod(fake_bin / "scp", 0o755)

            result = self._run_bash_fixture(flasher, cache, fake_bin, trace)
            output = result.stdout + result.stderr
            uploads = trace.read_text() if trace.exists() else ""
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("different router; refusing to upload sysupgrade", output)
            self.assertIn("root@192.168.31.1:/tmp/jidu-factory.ubi", uploads)
            self.assertNotIn("root@192.168.1.1:/tmp/sysupgrade.bin", uploads)

    def test_bash_flasher_requires_persistent_overlay_after_sysupgrade_disconnect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            flasher, cache, fake_bin = self._bash_fixture(root)
            trace = root / "scp.log"
            mounts = root / "mounts"
            mfg_hash = "c" * 64

            (fake_bin / "ssh").write_text(
                "#!/usr/bin/env bash\n"
                "target=''\nlast=''\npayload=''\n"
                "for arg in \"$@\"; do case \"$arg\" in root@*) target=\"$arg\" ;; esac; last=\"$arg\"; done\n"
                "if [ \"$last\" = 'sh -s' ]; then payload=$(cat); last=${payload%%$'\\n'*}; else payload=$last; fi\n"
                "case \"$last\" in\n"
                "  'cat /proc/mtd >/dev/null') exit 0 ;;\n"
                "  'cat /tmp/deviceModel 2>/dev/null') printf 'JIDU6101\\n'; exit 0 ;;\n"
                "  'sh /tmp/jidu-flash.sh') exit 255 ;;\n"
                "  'true') exit 0 ;;\n"
                "  'sysupgrade -n /tmp/sysupgrade.bin') exit 255 ;;\n"
                "  *overlayfs:/overlay*)\n"
                "    payload=${payload//\\/proc\\/mounts/$MOUNTS_FIXTURE}\n"
                "    bash -c \"$payload\"\n"
                "    exit $? ;;\n"
                "esac\n"
                "case \"$last\" in *sha256sum*)\n"
                f"  printf '{mfg_hash}\\n'; exit 0 ;;\n"
                "esac\n"
                "exit 90\n"
            )
            (fake_bin / "scp").write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$TRACE\"\nexit 0\n"
            )
            (fake_bin / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")
            for command in ("ssh", "scp", "sleep"):
                os.chmod(fake_bin / command, 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["TRACE"] = str(trace)
            env["MOUNTS_FIXTURE"] = str(mounts)
            mounts.write_text(
                "/dev/ubi0_1 /overlay ubifs rw,noatime 0 0\n"
                "overlayfs:/tmp/root / overlay rw,lowerdir=/,upperdir=/tmp/root/upper 0 0\n"
            )
            failed = subprocess.run(
                ["bash", str(flasher), "6101", "--cache", str(cache), "--yes"],
                text=True,
                capture_output=True,
                env=env,
                cwd=root,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("permanent OpenWrt did not come up", failed.stdout + failed.stderr)

            mounts.write_text(
                "/dev/ubi0_1 /overlay ubifs rw,noatime 0 0\n"
                "overlayfs:/overlay / overlay rw,lowerdir=/rom,upperdir=/overlay/upper 0 0\n"
            )
            passed = subprocess.run(
                ["bash", str(flasher), "6101", "--cache", str(cache), "--yes"],
                text=True,
                capture_output=True,
                env=env,
                cwd=root,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("Permanent OpenWrt is up on the same router", passed.stdout)

    def test_powershell_flasher_requires_persistent_overlay_after_sysupgrade_disconnect(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _, cache, fake_bin = self._bash_fixture(root)
            flasher = root / "firmware" / "fwflash.ps1"
            shutil.copy2(ROOT / "firmware" / "fwflash.ps1", flasher)
            trace = root / "scp.log"
            mounts = root / "mounts"
            mfg_hash = "f" * 64

            (fake_bin / "ssh").write_text(
                "#!/usr/bin/env bash\n"
                "last=''\npayload=''\n"
                "for arg in \"$@\"; do last=\"$arg\"; done\n"
                "if [ \"$last\" = 'sh -s' ]; then payload=$(cat); last=${payload%%$'\\n'*}; else payload=$last; fi\n"
                "case \"$last\" in\n"
                "  'cat /proc/mtd >/dev/null') exit 0 ;;\n"
                "  'cat /tmp/deviceModel 2>/dev/null') printf 'JIDU6101\\n'; exit 0 ;;\n"
                "  'sh /tmp/jidu-flash.sh') exit 255 ;;\n"
                "  'true') exit 0 ;;\n"
                "  'sysupgrade -n /tmp/sysupgrade.bin') exit 255 ;;\n"
                "  *overlayfs:/overlay*)\n"
                "    payload=${payload//\\/proc\\/mounts/$MOUNTS_FIXTURE}\n"
                "    bash -c \"$payload\"\n"
                "    exit $? ;;\n"
                "esac\n"
                "case \"$last\" in *sha256sum*)\n"
                f"  printf '{mfg_hash}\\n'; exit 0 ;;\n"
                "esac\n"
                "exit 90\n"
            )
            (fake_bin / "scp").write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$TRACE\"\nexit 0\n"
            )
            os.chmod(fake_bin / "ssh", 0o755)
            os.chmod(fake_bin / "scp", 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["TRACE"] = str(trace)
            env["MOUNTS_FIXTURE"] = str(mounts)
            quoted_flasher = str(flasher).replace("'", "''")
            quoted_cache = str(cache).replace("'", "''")
            command = (
                "function Start-Sleep { param([int]$Seconds) }; "
                f"& '{quoted_flasher}' 6101 -Cache '{quoted_cache}' -Yes"
            )

            mounts.write_text(
                "/dev/ubi0_1 /overlay ubifs rw,noatime 0 0\n"
                "overlayfs:/tmp/root / overlay rw,lowerdir=/,upperdir=/tmp/root/upper 0 0\n"
            )
            failed = subprocess.run(
                [powershell, "-NoProfile", "-Command", command],
                text=True,
                capture_output=True,
                env=env,
                cwd=root,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("permanent OpenWrt did not come up", failed.stdout + failed.stderr)

            mounts.write_text(
                "/dev/ubi0_1 /overlay ubifs rw,noatime 0 0\n"
                "overlayfs:/overlay / overlay rw,lowerdir=/rom,upperdir=/overlay/upper 0 0\n"
            )
            passed = subprocess.run(
                [powershell, "-NoProfile", "-Command", command],
                text=True,
                capture_output=True,
                env=env,
                cwd=root,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("Permanent OpenWrt is up on the same router", passed.stdout)

    def test_flashers_bind_both_openwrt_stages_to_the_stock_router(self):
        sh = (ROOT / "firmware" / "fwflash.sh").read_text()
        ps = (ROOT / "firmware" / "fwflash.ps1").read_text()
        for body, name in ((sh, "fwflash.sh"), (ps, "fwflash.ps1")):
            with self.subTest(script=name):
                self.assertIn("sha256sum", body)
                self.assertIn("MFG", body)
                self.assertIn("different router", body)
                self.assertIn("persistent OpenWrt", body)
                self.assertIn('overlayfs:/overlay / overlay ', body)
                self.assertNotIn('^[^ ]+ /overlay ', body)
                self.assertLess(body.index("different router"), body.index("uploading the permanent sysupgrade"))
                self.assertGreater(body.rindex("persistent OpenWrt"), body.index("sysupgrade -n"))

    def test_onrouter_scripts_are_forced_to_lf_on_checkout(self):
        attrs = (ROOT / ".gitattributes").read_text()
        self.assertIn("firmware/onrouter/*.sh text eol=lf", attrs)

    def test_top_level_bash_launcher_exposes_download_and_flash(self):
        body = (ROOT / "flash.sh").read_text()
        self.assertIn("unlock|backup|download|flash|detect|check", body)
        self.assertIn("run_firmware download", body)
        self.assertIn("run_firmware flash", body)
        self.assertIn('idu backup --outdir "$PWD"', body)
        self.assertIn("firmware/fwflash.sh", body)

    def test_powershell_flasher_is_ascii_so_windows_powershell_5_parses_it(self):
        raw = (ROOT / "firmware" / "fwflash.ps1").read_bytes()
        offenders = sorted({b for b in raw if b > 0x7F})
        self.assertEqual(offenders, [], "non-ASCII bytes break a BOM-less .ps1 on Windows PowerShell 5.1")


if __name__ == "__main__":
    unittest.main()
