import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipIf(os.name == "nt", "the stubs below are POSIX scripts")
@unittest.skipUnless(PWSH, "PowerShell is not installed")
class WindowsLauncherTests(unittest.TestCase):
    def test_backup_uses_root_ssh_without_the_web_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "bin").mkdir()

            ssh = root / "bin" / "ssh"
            ssh.write_text("#!/usr/bin/env bash\necho JIDU6711\n")
            ssh.chmod(0o755)

            python = root / "bin" / "python3"
            python.write_text(
                "#!/usr/bin/env bash\n"
                'if [ "$1" = "-" ]; then cat >/dev/null 2>&1 || true; fi\n'
                'case "$*" in *idu.py*) printf "PY %s\\n" "$*" >> "$TRACE";; esac\n'
                "exit 0\n")
            python.chmod(0o755)

            # The launcher tries py, then python, then python3. Fail the first
            # two explicitly so discovery cannot pick a host interpreter.
            for name in ("py", "python"):
                decoy = root / "bin" / name
                decoy.write_text(
                    "#!/usr/bin/env bash\n"
                    "cat >/dev/null 2>&1 || true\n"
                    "exit 1\n")
                decoy.chmod(0o755)

            trace = root / "calls"
            env = dict(os.environ,
                       PATH=f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}",
                       TRACE=str(trace))
            result = subprocess.run(
                [PWSH, "-NoProfile", "-File", str(ROOT / "flash.ps1"),
                 "backup", "--router", "https://192.168.31.77"],
                cwd=root, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            calls = trace.read_text()
            self.assertIn("--ssh-only", calls)
            self.assertIn("backup", calls)
            self.assertNotIn("--password", calls)


if __name__ == "__main__":
    unittest.main()
