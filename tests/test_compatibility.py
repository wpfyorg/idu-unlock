import contextlib
import errno
import io
import os
import unittest
from unittest import mock

import idu


class FakeApi:
    def __init__(self, version, model="JIDU6101"):
        self.device = idu.Device(model, "Arcadyan", "test", {})
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


class ApiLoginTests(unittest.TestCase):
    """The two login quirks: an unusable cookie Path, and a sitting session."""

    FLAGS = {"DEVICE_MODEL": "JIDU6401", "DEVICE_SYSTEM_NAME": "Archadyan",
             "BOARD_NAME": "MTK"}
    OK = {"status": "OK", "code": "OK"}

    def _api(self, replies):
        api = idu.Api("https://192.168.31.1")
        api.calls = []

        def fake_call(method, params=None):
            api.calls.append((method, params))
            return replies.pop(0)

        api.call = fake_call
        return api

    def _login(self, token="BEARER-SESSION"):
        return {"status": "OK", "code": "OK_LOGIN",
                "results": {"token": token, "deviceFlags": self.FLAGS}}

    @staticmethod
    def _cookies(api):
        return {cookie.name: cookie.value for cookie in api.http.cookies}

    def test_two_part_token_splits_between_header_and_cookie(self):
        api = self._api([self.OK, self._login(), self.OK])
        api.connect("admin", "pw")
        self.assertEqual(api.token, "BEARER")
        self.assertEqual(self._cookies(api), {"sysauth": "SESSION"})

    def test_cookie_set_with_an_unusable_path_is_restored(self):
        class Response:
            headers = {"Set-Cookie": "sysauth=SID123; Secure; SameSite=Strict; "
                                     "HttpOnly; path=https://192.168.31.1"}

        api = self._api([])
        api._absorb_auth_cookie(Response())
        self.assertEqual(self._cookies(api), {"sysauth": "SID123"})

    def test_duplicate_admin_is_taken_over_not_waited_out(self):
        refusal = {"status": "ERROR", "code": "ERR_LOGIN_DUPLICATE_ADMIN",
                   "results": {"token": "BEARER-SESSION", "loggedId": "HELD"}}
        api = self._api([self.OK, refusal, self.OK])
        with contextlib.redirect_stdout(io.StringIO()):
            api.connect("admin", "pw")

        # preLogin, login, postLogin — no retry loop, so no sleep to outlast
        self.assertEqual([method for method, _ in api.calls],
                         ["preLogin", "login", "postLogin"])
        self.assertEqual(api.calls[-1][1],
                         {"loggedId": "HELD", "authHeader": "Bearer BEARER"})

    def test_duplicate_admin_without_a_logged_id_still_waits(self):
        refusal = {"status": "ERROR", "code": "ERR_LOGIN_DUPLICATE_ADMIN",
                   "results": {}}
        api = self._api([self.OK, refusal])
        with self.assertRaises(idu.IduError):
            api.connect("admin", "pw", patience=0)


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
    @staticmethod
    def verdict_for(version, model="JIDU6101"):
        return idu.check(FakeApi(version, model))

    def assert_state(self, version, state, model="JIDU6101"):
        verdict = self.verdict_for(version, model)
        actual = ("NO" if verdict.method_closed
                  else "TEST" if verdict.test_required else "YES")
        self.assertEqual(actual, state, f"{version}: {verdict.evidence}")
        self.assertEqual(verdict.unlockable, state == "YES")
        if state == "NO":
            self.assertEqual(verdict.vectors, [])
        else:
            self.assertEqual(verdict.vectors, [idu.PasswordVector.name])

    def test_r2_0_18_is_method_closed(self):
        # a stock R2.0.18.2 rootfs has no savePasswdHistory(): setPassword()
        # wraps the password in single quotes, so $(...) is never evaluated
        self.assert_state("ARCNJIO_JIDU6101_R2.0.18.2", "NO")
        self.assert_state("SRCMJIO_JIDU6401_R2.0.9", "NO", model="JIDU6401")

    def test_r2_0_19_window_requires_api_test(self):
        # the password-history shell-out landed somewhere in this window
        self.assert_state("JIO_JIDU6701_R2.0.19.0", "TEST", model="JIDU6701")
        self.assert_state("JIO_JIDU6701_R2.0.19.5", "TEST", model="JIDU6701")

    def test_r2_0_19_6_is_confirmed(self):
        # the oldest stock rootfs confirmed to carry the vulnerable hash
        self.assert_state("JIO_JIDU6701_R2.0.19.6", "YES", model="JIDU6701")

    def test_r3_2_0_is_confirmed(self):
        # a member-confirmed working build on the MTK family
        self.assert_state("ARCNJIO_JIDU6101_R3.2.0", "YES")

    def test_r3_2_1_requires_api_test(self):
        # the fix had landed by R3.2.3 on MTK (stock 6701 rootfs): somewhere
        # between R3.2.0 and there, so anything in between stays a TEST
        self.assert_state("ARCNJIO_JIDU6101_R3.2.1", "TEST")

    def test_r3_2_2_requires_api_test(self):
        self.assert_state("ARCNJIO_JIDU6101_R3.2.2", "TEST")

    def test_r3_2_3_is_method_closed(self):
        # read from a stock 6701 rootfs: luci.sys.user.setpasswd replaced the
        # unescaped shell-out
        self.assert_state("ARCNJIO_JIDU6101_R3.2.3", "NO")

    def test_later_patch_requires_api_test(self):
        self.assert_state("ARCNJIO_JIDU6101_R3.2.0.1", "TEST")

    def test_unknown_version_requires_api_test(self):
        self.assert_state("ARCNJIO_JIDU6101", "TEST")

    def test_qualcomm_r3_2_6_is_confirmed(self):
        # a member report on a JIDU6611: the password bug still ran on R3.2.6
        self.assert_state("SRCMJIO_JIDU6611_R3.2.6", "YES", model="JIDU6611")

    def test_jidu6711_needs_device_verification(self):
        self.assertEqual(idu.Device("JIDU6711", "", "", {}).family, "qualcomm")
        self.assert_state("JIO_JIDU6711_R3.2.6", "TEST", model="JIDU6711")

    def test_qualcomm_beyond_report_requires_api_test(self):
        # nothing beyond the R3.2.6 datapoint is known for the 6j11 builds
        self.assert_state("SRCMJIO_JIDU6611_R3.2.7", "TEST", model="JIDU6611")


class UnlockGateTests(unittest.TestCase):
    class Shell:
        def __init__(self, alive):
            self._alive = alive

        def alive(self):
            return self._alive

    @staticmethod
    def closed_verdict():
        return idu.Verdict(
            model="JIDU6101", firmware="R2.0.18.2", vectors=[],
            evidence=["release < R2.0.19: no password-history shell-out"],
            method_closed=True)

    def test_method_closed_stops_when_no_shell_is_already_open(self):
        api = mock.Mock(host="192.168.31.1")
        with mock.patch.object(idu, "_shell_for", return_value=self.Shell(False)):
            with self.assertRaises(idu.UnsupportedFirmware):
                idu.unlock(api, None, "pw", verdict=self.closed_verdict(),
                           hint=False)
        api.session.assert_not_called()

    def test_existing_root_shell_is_used_despite_closed_method(self):
        # a UART-unlocked unit can still be backed up on NO firmware
        api = mock.Mock(host="192.168.31.1")
        with (mock.patch.object(idu, "_shell_for", return_value=self.Shell(True)),
              contextlib.redirect_stdout(io.StringIO())):
            idu.unlock(api, None, "pw", verdict=self.closed_verdict(), hint=False)
        api.session.assert_not_called()


class CallbackAddressTests(unittest.TestCase):
    def test_override_is_used(self):
        self.assertEqual(
            idu.callback_address("192.168.31.1", "192.168.31.51"),
            "192.168.31.51")

    def test_loopback_is_rejected(self):
        with self.assertRaises(idu.IduError):
            idu.callback_address("192.168.31.1", "127.0.0.1")

    def test_wsl_nat_address_is_rejected(self):
        with (mock.patch.object(idu, "_running_in_wsl", return_value=True),
              mock.patch.object(idu.socket, "gethostbyname",
                                return_value="192.168.31.1")):
            with self.assertRaises(idu.IduError):
                idu.callback_address("192.168.31.1", "172.20.0.2")

    def test_wsl_with_a_lan_override_is_allowed(self):
        with mock.patch.object(idu, "_running_in_wsl", return_value=True):
            self.assertEqual(
                idu.callback_address("192.168.31.1", "192.168.31.51"),
                "192.168.31.51")


class InjectorTests(unittest.TestCase):
    def test_literal_password_fits_the_policy(self):
        password = idu.Injector("Aa1").literal()
        self.assertGreaterEqual(len(password), idu.PASSWORD_MIN)
        self.assertLessEqual(len(password), idu.PASSWORD_MAX)
        self.assertNotIn("|", password)
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))
        # JIDU6101 R3.2 rejects an all-alphanumeric password with
        # ERR_WEB_USER_INVALID_PASSWORD, so the probe has to carry a symbol.
        self.assertIn("!", password)
        self.assertTrue(all(c.isalnum() or c == "!" for c in password))


class ShellAuthTests(unittest.TestCase):
    def test_empty_password_uses_dropbear_none_auth_without_expect(self):
        """`passwd -d root` leaves dropbear accepting "none": no prompt, no expect."""
        with mock.patch.object(idu, "require_tool"):
            shell = idu.Shell("192.168.31.1", password="")
        opts = shell._opts()
        self.assertIn("PreferredAuthentications=none", opts)
        self.assertIn("BatchMode=yes", opts)
        self.assertNotIn("PreferredAuthentications=password", opts)
        with (mock.patch.object(idu, "_expect") as expect,
              mock.patch.object(idu.subprocess, "run") as run):
            run.return_value = mock.Mock(returncode=0, stdout="uid=0(root)\n", stderr="")
            self.assertEqual(shell.run("id"), "uid=0(root)\n")
        expect.assert_not_called()


class PasswordProbeTests(unittest.TestCase):
    class Api:
        def __init__(self, records_history, history=""):
            self.records_history = records_history
            self.history = history
            self.calls = []

        def guest_record(self):
            return {"recordId": "3", "passwdHistory": self.history}

        def set_password(self, record_id, password):
            self.calls.append(password)
            if self.records_history:
                self.history = "new-hash"
            return {"status": "OK", "code": "OK"}

    def run_vector(self, api, force=False):
        with (mock.patch.object(idu.time, "sleep"),
              contextlib.redirect_stdout(io.StringIO())):
            idu.PasswordVector(force=force).execute(api, "192.168.31.51")

    def test_missing_history_stops_before_the_payload(self):
        api = self.Api(records_history=False)
        with self.assertRaises(idu.UnsupportedFirmware):
            self.run_vector(api)
        self.assertEqual(len(api.calls), 1)
        self.assertNotIn("$(", api.calls[0])

    def test_missing_history_points_at_the_breeze_guide(self):
        api = self.Api(records_history=False)
        with self.assertRaises(idu.UnsupportedFirmware) as raised:
            self.run_vector(api)
        self.assertIn(idu.BREEZE_GUIDE, str(raised.exception))
        self.assertIn("./flash.sh breeze", str(raised.exception))

    def test_unchanged_history_is_not_treated_as_support(self):
        # a downgraded unit can keep an old passwdHistory in its config
        api = self.Api(records_history=False, history="old-hash")
        with self.assertRaises(idu.UnsupportedFirmware):
            self.run_vector(api)
        self.assertEqual(len(api.calls), 1)

    def test_new_history_sends_both_payloads(self):
        api = self.Api(records_history=True)
        self.run_vector(api)
        self.assertEqual(len(api.calls), 3)
        self.assertNotIn("$(", api.calls[0])
        self.assertIn("$(", api.calls[1])
        self.assertIn("$(", api.calls[2])

    def test_force_sends_payloads_without_history(self):
        api = self.Api(records_history=False)
        self.run_vector(api, force=True)
        self.assertEqual(len(api.calls), 3)
        self.assertIn("$(", api.calls[1])


@unittest.skipIf(os.name == "nt", "POSIX bind errors")
class PortErrorTests(unittest.TestCase):
    def test_permission_denied_explains_root_not_lsof(self):
        problem = PermissionError(errno.EACCES, "Permission denied")
        with mock.patch.object(idu, "_running_in_wsl", return_value=False):
            message = str(idu._port_error(80, problem))
        self.assertIn("needs root", message)
        self.assertIn("sudo", message)
        self.assertNotIn("lsof", message)

    def test_address_in_use_names_the_holder_command(self):
        problem = OSError(errno.EADDRINUSE, "Address already in use")
        message = str(idu._port_error(80, problem))
        self.assertIn("already in use", message)
        self.assertIn("lsof", message)

    def test_wsl_permission_error_mentions_nat(self):
        problem = PermissionError(errno.EACCES, "Permission denied")
        with mock.patch.object(idu, "_running_in_wsl", return_value=True):
            message = str(idu._port_error(80, problem))
        self.assertIn("WSL2", message)
        self.assertIn("flash.ps1", message)

    def test_macos_permission_error_does_not_offer_the_linux_sysctl(self):
        problem = PermissionError(errno.EACCES, "Permission denied")
        with (mock.patch.object(idu.sys, "platform", "darwin"),
              mock.patch.object(idu, "_running_in_wsl", return_value=False)):
            message = str(idu._port_error(80, problem))
        self.assertIn("sudo", message)
        self.assertNotIn("ip_unprivileged_port_start", message)


if __name__ == "__main__":
    unittest.main()
