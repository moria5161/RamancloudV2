import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from desktop.launcher import require_webview2

ROOT = Path(__file__).resolve().parents[2]


class LauncherTests(unittest.TestCase):
    def test_webview2_missing_runtime_fails_without_ie_fallback(self):
        registry = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_READ=4, KEY_WOW64_32KEY=8,
                                   OpenKey=Mock(side_effect=FileNotFoundError()))
        with patch.dict("sys.modules", {"winreg": registry}):
            with self.assertRaisesRegex(RuntimeError, "Evergreen Standalone Installer"):
                require_webview2()

    def test_webview2_registry_version_is_detected(self):
        handle = Mock()
        context = Mock()
        context.__enter__ = Mock(return_value=handle)
        context.__exit__ = Mock(return_value=False)
        registry = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_READ=4, KEY_WOW64_32KEY=8,
                                   OpenKey=Mock(return_value=context), QueryValueEx=Mock(return_value=("140.0.100.0", 1)))
        with patch.dict("sys.modules", {"winreg": registry}):
            require_webview2()
        registry.QueryValueEx.assert_called_once_with(handle, "pv")

    def test_require_frozen_rejects_source_launcher_with_failure_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "smoke.json"
            result = subprocess.run([sys.executable, "-m", "desktop", "--smoke-test", "--require-frozen", "--smoke-report", str(report)],
                                    cwd=ROOT.parent, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(data["ok"])
            self.assertFalse(data["frozen"])
            self.assertIn("frozen", data["error"])

    @unittest.skipIf(os.name == "nt", "Windows terminate is not a graceful signal; RuntimeTests cover Windows shutdown")
    def test_serve_ready_file_and_signal_shutdown_without_gui_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            frontend = directory / "frontend"
            frontend.mkdir()
            (frontend / "index.html").write_text('<html><head></head><div id="root"></div></html>', encoding="utf-8")
            ready = directory / "ready.json"
            process = subprocess.Popen([sys.executable, "-m", "desktop", "--serve", "--frontend-dist", str(frontend),
                                        "--ready-file", str(ready), "--data-dir", str(directory / "data")],
                                       cwd=ROOT.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 30
                while not ready.is_file() and time.monotonic() < deadline and process.poll() is None:
                    time.sleep(0.1)
                self.assertTrue(ready.is_file(), "Server did not write its readiness file")
                data = json.loads(ready.read_text(encoding="utf-8"))
                self.assertTrue(data["url"].endswith("/preprocessing/"))
                self.assertEqual(data["pid"], process.pid)
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertIn(data["url"], stdout)
                self.assertFalse(ready.exists())
                self.assertIn("Application shutdown complete", stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
