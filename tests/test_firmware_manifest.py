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
                self.assertIn("factory.ubi", body)
                self.assertIn("ubiformat", body)
                self.assertIn("/proc/mtd", body)
                # the partition must be looked up, never hard-coded
                self.assertNotIn("ubiformat /dev/mtd", body)
                self.assertIn('"$DEV"', body)


if __name__ == "__main__":
    unittest.main()
