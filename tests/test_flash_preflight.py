import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FlashPreflightTest(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Bash integration requires a POSIX host')
    def test_flash_rejects_missing_flasher_or_unknown_model_before_unlock(self):
        for missing in (True, False):
            with self.subTest(missing_flasher=missing), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                (root / 'bin').mkdir()
                (root / 'firmware').mkdir()
                shutil.copy2(ROOT / 'flash.sh', root / 'flash.sh')
                python = root / 'bin' / 'python3'
                python.write_text('''#!/usr/bin/env bash
if [ "$1" = -c ]; then exit 0; fi
printf '%s\\n' "$*" >> "$TRACE"
printf 'MODEL=UNKNOWN\\nFAMILY=unknown\\n'
''')
                python.chmod(0o755)
                if not missing:
                    flasher = root / 'firmware' / 'fwflash.sh'
                    flasher.write_text('#!/usr/bin/env bash\nexit 0\n')
                    flasher.chmod(0o755)
                trace = root / 'calls'
                env = dict(os.environ, PATH=f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}",
                           PASSWORD='test', TRACE=str(trace))
                result = subprocess.run(['bash', str(root / 'flash.sh'), 'flash'],
                                        cwd=root, env=env, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                calls = trace.read_text() if trace.exists() else ''
                self.assertNotIn('unlock', calls)
                self.assertNotIn('backup', calls)
                self.assertIn('missing firmware flasher' if missing else 'no OpenWrt image set',
                              result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
