import unittest

import idu


class FakeApi:
    def __init__(self, version):
        self.device = idu.Device("JIDU6101", "Arcadyan", "test", {})
        self.version = version

    def call(self, method, params=None):
        if method == "getFirmwareDetails":
            return {"results": {"firmwareVersion": self.version}}
        raise AssertionError(f"unexpected API call: {method}")


class ReleaseParsingTests(unittest.TestCase):
    def test_parses_patch_and_long_release_versions(self):
        self.assertEqual(idu._release("ARCNJIO_JIDU6101_R3.2.0"), (3, 2, 0))
        self.assertEqual(
            idu._release("JIO_JIDU6701_R2.0.19.5_build42"),
            (2, 0, 19, 5),
        )

    def test_parses_real_version_strings(self):
        # taken from flash dumps: a 6401 on R3.0.1 and a 6101 on R3.2.3. The
        # OEM prefix before "JIO" varies, so nothing may depend on it.
        self.assertEqual(idu._release("SRCMJIO_JIDU6401_R3.0.1"), (3, 0, 1))
        self.assertEqual(idu._release("ARCNJIO_JIDU6101_R3.2.3"), (3, 2, 3))

    def test_rejects_unrecognised_version(self):
        self.assertIsNone(idu._release("ARCNJIO_JIDU6101"))
        self.assertIsNone(idu._release(""))


class MfgLayoutTests(unittest.TestCase):
    """The same slot table arrives in two encodings; both must parse."""

    @staticmethod
    def _slot_blob(entries, wide=False):
        width = idu.MFG_SLOT_BYTES * (2 if wide else 1)
        magic = "mfg.data".encode("utf-16-le") if wide else b"mfg.data"
        blob = bytearray((b"\xff\xfe" if wide else b"") + magic
                         + len(entries).to_bytes(4, "little"))
        blob += b"\x00" * ((2 if wide else 0) + idu.MFG_TABLE_OFFSET * (2 if wide else 1)
                           - len(blob))
        for value in entries:
            encoding = "utf-16-le" if wide else "ascii"
            slot = value.encode(encoding) if value else b"\xff" * width
            blob += slot[:width].ljust(width, b"\x00")
        return bytes(blob)

    ROWS = ["010", "RSABCDEF0123456", "I.DVS00A0000", "GxTEbl6DK6XiNsYr",
            "AirFiber-Test01", "2ue2n5p2P8npCpeC", "*q7:zn]E]X?]D4Y0",
            "0", "JIDU6401"]

    def assert_rows(self, data):
        self.assertEqual(data["WiFi-SSID"], "AirFiber-Test01")
        self.assertEqual(data["WiFi-Password"], "2ue2n5p2P8npCpeC")
        self.assertEqual(data["sn"], "RSABCDEF0123456")
        self.assertEqual(data["device_model"], "JIDU6401")
        self.assertNotIn("mfg_slot_5", data)

    def test_ascii_table(self):
        self.assert_rows(idu.parse_mfg_blob(self._slot_blob(self.ROWS)))

    def test_wide_utf16_table(self):
        # a byte-widened dump, where every offset is doubled
        self.assert_rows(idu.parse_mfg_blob(self._slot_blob(self.ROWS, wide=True)))

    def test_unreadable_partition_still_yields_the_model(self):
        blob = (b"\xff\xfe" + b"junk" * 8 + b"\x00" * 64
                + "JIDU6101".encode("utf-16-le") + b"\x00" * 32)
        self.assertEqual(idu.parse_mfg_blob(blob)["device_model"], "JIDU6101")


class CompatibilityTests(unittest.TestCase):
    def assert_release(self, version, test_required):
        verdict = idu.check(FakeApi(version))
        self.assertEqual(verdict.test_required, test_required)
        self.assertEqual(verdict.unlockable, not test_required)
        self.assertEqual(verdict.vectors, [idu.PasswordVector.name])

    def test_r2_release_is_confirmed(self):
        self.assert_release("JIO_JIDU6701_R2.0.19.5", False)

    def test_r3_2_0_is_confirmed(self):
        self.assert_release("ARCNJIO_JIDU6101_R3.2.0", False)

    def test_r3_2_1_requires_api_test(self):
        self.assert_release("ARCNJIO_JIDU6101_R3.2.1", True)

    def test_later_patch_requires_api_test(self):
        self.assert_release("ARCNJIO_JIDU6101_R3.2.0.1", True)

    def test_unknown_version_requires_api_test(self):
        self.assert_release("ARCNJIO_JIDU6101", True)


if __name__ == "__main__":
    unittest.main()
