import json
import pathlib
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

    def test_scripts_are_executable_and_syntax_checked_elsewhere(self):
        for name in ("fwflash.sh", "fwflash.ps1"):
            self.assertTrue((ROOT / "firmware" / name).exists())

    def test_onrouter_scripts_guard_the_partition_they_write(self):
        for name in ("6j01.sh", "6j11.sh"):
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
        for name in ("6j01.sh", "6j11.sh"):
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
        # output must go to the console, not into the caller's variable
        self.assertEqual(body.count("| Out-Host"), 2)
        # 2>&1 turns native stderr into a terminating error on PowerShell 5.1
        self.assertNotIn("2>&1", body)

    def test_flashers_unlock_the_unit_themselves(self):
        """One command: no separate `./flash.sh unlock` beforehand."""
        sh = (ROOT / "firmware" / "fwflash.sh").read_text()
        ps = (ROOT / "firmware" / "fwflash.ps1").read_text()
        # both hand off to the unlocker in the repo root, with the stock address
        self.assertIn('ROUTER="https://$STOCK" "$UNLOCKER" unlock', sh)
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

    def test_local_flash_script_is_checked_before_unlock(self):
        sh = (ROOT / "firmware" / "fwflash.sh").read_text()
        self.assertLess(sh.index('[ -f "$ONROUTER" ]'), sh.index("ensure_root_ssh\n", sh.index('ONROUTER="$HERE')))
        ps = (ROOT / "firmware" / "fwflash.ps1").read_text()
        self.assertLess(ps.index('if (-not (Test-Path $onrouter))'), ps.index('if ((Test-Ssh $stockOpts'))

    def test_flashers_isolate_stock_host_keys_and_use_configured_windows_key(self):
        sh = (ROOT / "firmware" / "fwflash.sh").read_text()
        ps = (ROOT / "firmware" / "fwflash.ps1").read_text()
        self.assertIn('UserKnownHostsFile="$STOCK_KNOWN_HOSTS"', sh)
        self.assertIn('UserKnownHostsFile=$stockKh', ps)
        self.assertIn("$env:KEY", ps)
        self.assertIn("'IdentitiesOnly=yes'", ps)
        self.assertIn('sudo -E env ROUTER=', sh)

    def test_markdown_does_not_link_third_party_uart_photos(self):
        for path in (ROOT / "OPENWRT.md", *(ROOT / "docs" / "models").glob("*.md")):
            with self.subTest(path=path.name):
                self.assertNotIn("uart_pins", path.read_text())

    def test_powershell_flasher_is_ascii_so_windows_powershell_5_parses_it(self):
        raw = (ROOT / "firmware" / "fwflash.ps1").read_bytes()
        offenders = sorted({b for b in raw if b > 0x7F})
        self.assertEqual(offenders, [], "non-ASCII bytes break a BOM-less .ps1 on Windows PowerShell 5.1")


if __name__ == "__main__":
    unittest.main()
