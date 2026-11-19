import contextlib
import io
import tempfile
import unittest
from unittest import mock

import idu


class SshOnlyCliTests(unittest.TestCase):
    """A unit opened by breeze or UART backs up over SSH, not the web API."""

    def test_backup_skips_the_web_api_login(self):
        with mock.patch.object(idu, "Api") as api_cls, \
                mock.patch.object(idu, "backup") as backup_fn, \
                tempfile.TemporaryDirectory() as out:
            code = idu.main(["--ssh-only", "--no-banner", "backup",
                             "--outdir", out])
        self.assertEqual(code, 0)
        self.assertFalse(api_cls.return_value.session.called)
        backup_fn.assert_called_once()
        self.assertEqual(str(backup_fn.call_args.args[1]), out)

    def test_ssh_only_is_rejected_for_other_commands(self):
        stderr = io.StringIO()
        with mock.patch.object(idu, "Api"), \
                contextlib.redirect_stderr(stderr), \
                self.assertRaises(SystemExit) as raised:
            idu.main(["--ssh-only", "detect"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--ssh-only", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
