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
        self.assertEqual(idu._release("ARCNJIO_JIDU6101_R3.0.3"), (3, 0, 3))
        self.assertEqual(
            idu._release("JIO_JIDU6701_R2.0.19.5_build42"),
            (2, 0, 19, 5),
        )

    def test_rejects_unrecognised_version(self):
        self.assertIsNone(idu._release("ARCNJIO_JIDU6101"))
        self.assertIsNone(idu._release(""))


class CompatibilityTests(unittest.TestCase):
    def assert_release(self, version, test_required):
        verdict = idu.check(FakeApi(version))
        self.assertEqual(verdict.test_required, test_required)
        self.assertEqual(verdict.unlockable, not test_required)
        self.assertEqual(verdict.vectors, [idu.PasswordVector.name])

    def test_r2_release_is_confirmed(self):
        self.assert_release("JIO_JIDU6701_R2.0.19.5", False)

    def test_r3_0_3_is_confirmed(self):
        self.assert_release("ARCNJIO_JIDU6101_R3.0.3", False)

    def test_r3_0_4_requires_api_test(self):
        self.assert_release("ARCNJIO_JIDU6101_R3.0.4", True)

    def test_later_patch_requires_api_test(self):
        self.assert_release("ARCNJIO_JIDU6101_R3.0.3.1", True)

    def test_unknown_version_requires_api_test(self):
        self.assert_release("ARCNJIO_JIDU6101", True)


if __name__ == "__main__":
    unittest.main()
