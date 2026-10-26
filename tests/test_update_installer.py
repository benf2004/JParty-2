"""Run real replacement helpers against disposable app folders on each release OS."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

@unittest.skipIf(os.name == 'nt', 'POSIX replacement helper')
class InstallerTests(unittest.TestCase):
    def test_real_helper_replaces_and_relaunches_with_spaces_in_paths(self):
        with tempfile.TemporaryDirectory(prefix='jparty update ') as temp:
            base = Path(temp)
            target, stage, backup = base / 'JParty', base / 'stage/JParty', base / 'backup'
            target.mkdir()
            stage.mkdir(parents=True)
            (target / 'old').write_text('old')
            exe = stage / 'JParty'
            exe.write_text('#!/bin/sh\nprintf launched > "$(dirname "$0")/launched"\n')
            exe.chmod(0o755)
            helper = Path(__file__).resolve().parents[1] / 'scripts/install_update.sh'
            subprocess.run(['/bin/sh', str(helper), '99999999', str(target), str(stage), str(backup), 'linux'], check=True, timeout=5)
            deadline = time.monotonic() + 3
            while not (target / 'launched').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((target / 'launched').exists())
            self.assertEqual((backup / 'old').read_text(), 'old')

    def test_real_helper_rolls_back_if_new_executable_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target, stage, backup = base / 'JParty', base / 'stage/JParty', base / 'backup'
            target.mkdir()
            stage.mkdir(parents=True)
            (target / 'old').write_text('old')
            helper = Path(__file__).resolve().parents[1] / 'scripts/install_update.sh'
            result = subprocess.run(['/bin/sh', str(helper), '99999999', str(target), str(stage), str(backup), 'linux'], timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((target / 'old').read_text(), 'old')
            self.assertFalse(backup.exists())


@unittest.skipUnless(os.name == 'nt', 'Windows replacement helper')
class WindowsInstallerTests(unittest.TestCase):
    def test_powershell_replaces_and_rolls_back(self):
        with tempfile.TemporaryDirectory(prefix='jparty update ') as temp:
            base = Path(temp)
            target, stage, backup = base / 'JParty', base / 'stage/JParty', base / 'backup'
            target.mkdir()
            stage.mkdir(parents=True)
            # A tiny executable proves Start-Process launches the new installation.
            source = r'public class App { public static void Main() { System.IO.File.WriteAllText(System.IO.Path.Combine(System.AppDomain.CurrentDomain.BaseDirectory, "launched"), "ok"); } }'
            command = 'Add-Type -TypeDefinition $env:JPARTY_TEST_SOURCE -OutputAssembly $env:JPARTY_TEST_EXE -OutputType WindowsApplication'
            env = dict(os.environ, JPARTY_TEST_SOURCE=source, JPARTY_TEST_EXE=str(stage / 'JParty.exe'))
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command], env=env, check=True, timeout=30)
            (target / 'old').write_text('old')
            helper = Path(__file__).resolve().parents[1] / 'scripts/install_update.ps1'
            args = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(helper)]
            subprocess.run(args + ['99999999', str(target), str(stage), str(backup), 'windows'], check=True, timeout=15)
            deadline = time.monotonic() + 5
            while not (target / 'launched').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((target / 'launched').exists())
            self.assertEqual((backup / 'old').read_text(), 'old')
            # A broken next update restores the current executable and relaunches it.
            stage.mkdir()
            second_backup = base / 'second-backup'
            result = subprocess.run(args + ['99999999', str(target), str(stage), str(second_backup), 'windows'], timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((target / 'JParty.exe').exists())
            self.assertFalse(second_backup.exists())


if __name__ == '__main__':
    unittest.main()
