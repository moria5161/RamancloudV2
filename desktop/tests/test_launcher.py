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
from unittest.mock import MagicMock, Mock, patch

from desktop.launcher import open_window, require_webview2

ROOT = Path(__file__).resolve().parents[2]


class LauncherTests(unittest.TestCase):
    def test_native_smoke_exports_use_a_new_directory_each_run(self):
        from desktop.gui_smoke import prepare_gui_smoke
        with tempfile.TemporaryDirectory() as directory:
            first, second = Mock(), Mock()
            prepare_gui_smoke(MagicMock(), first, directory)
            prepare_gui_smoke(MagicMock(), second, directory)
            first_path = first._attach.call_args.args[0]._directory
            second_path = second._attach.call_args.args[0]._directory
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(first_path.is_dir())
            self.assertTrue(second_path.is_dir())
            self.assertEqual(list(first_path.iterdir()), [])
            self.assertEqual(list(second_path.iterdir()), [])

    def test_native_closing_cleans_backend_before_os_termination(self):
        class Event:
            def __init__(self):
                self.handlers = []

            def __iadd__(self, handler):
                self.handlers.append(handler)
                return self

            def emit(self):
                for handler in self.handlers:
                    handler()

        window = SimpleNamespace(events=SimpleNamespace(closed=Event(), closing=Event()))
        runtime = SimpleNamespace(url="http://127.0.0.1:1234/preprocessing/", error=None,
                                  thread=Mock(), stop=Mock())
        runtime.thread.is_alive.return_value = True

        def terminate(**kwargs):
            window.events.closing.emit()
            runtime.stop.assert_called_once()
            runtime.thread.is_alive.return_value = False
            window.events.closed.emit()

        native = SimpleNamespace(settings={}, create_window=Mock(return_value=window), start=Mock(side_effect=terminate))
        with patch.dict("sys.modules", {"webview": native}), patch("sys.platform", "darwin"):
            open_window(runtime, ROOT)
        self.assertEqual(native.start.call_args.kwargs["gui"], "cocoa")

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
