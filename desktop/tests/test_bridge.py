import base64
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from desktop.bridge import CHUNK_BYTES, DownloadBridge


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.window = Mock()
        self.destination = self.directory / "chosen.txt"
        self.window.create_file_dialog.return_value = (str(self.destination),)
        self.bridge = DownloadBridge()
        self.bridge._attach(self.window)
        self.module = patch.dict("sys.modules", {"webview": SimpleNamespace(FileDialog=SimpleNamespace(SAVE="save"))})
        self.module.start()

    def tearDown(self):
        self.bridge._close()
        self.module.stop()
        self.temporary.cleanup()

    def transfer(self, data, filename="result.txt"):
        start = self.bridge.begin_download(filename, len(data))
        self.assertNotIn("error", start)
        token = start["id"]
        for sequence, offset in enumerate(range(0, len(data), CHUNK_BYTES)):
            result = self.bridge.write_download(token, sequence, base64.b64encode(data[offset:offset + CHUNK_BYTES]).decode("ascii"))
            self.assertEqual(result, {"ok": True})
        self.assertEqual(self.bridge.finish_download(token), {"ok": True})
        self.assertEqual(self.destination.read_bytes(), data)

    def test_txt_and_multichunk_zip_preserve_bytes(self):
        self.transfer("100\t1\n200\t2\n".encode("utf-8"))
        self.destination = self.directory / "chosen.zip"
        self.window.create_file_dialog.return_value = (str(self.destination),)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("spectra/data.txt", b"100\t1\n" * 100000)
        self.transfer(buffer.getvalue(), "spectra.zip")
        with zipfile.ZipFile(self.destination) as archive:
            self.assertIsNone(archive.testzip())

    def test_empty_download_and_string_dialog_result(self):
        self.window.create_file_dialog.return_value = str(self.destination)
        self.transfer(b"")

    def test_dialog_cancellation_does_not_create_files(self):
        self.window.create_file_dialog.return_value = None
        self.assertEqual(self.bridge.begin_download("result.txt", 10), {"cancelled": True})
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_filename_is_only_a_sanitized_dialog_suggestion(self):
        self.transfer(b"data", "C:\\folder\\../danger?.txt")
        self.window.create_file_dialog.assert_called_with("save", save_filename="danger.txt")

    def test_incomplete_download_keeps_existing_file_and_removes_partial(self):
        self.destination.write_bytes(b"existing")
        token = self.bridge.begin_download("result.txt", 100)["id"]
        with self.assertLogs("desktop.bridge", level="ERROR"):
            self.assertIn("error", self.bridge.finish_download(token))
        self.assertEqual(self.destination.read_bytes(), b"existing")
        self.assertEqual(list(self.directory.iterdir()), [self.destination])

    def test_out_of_order_and_invalid_base64_fail_loudly(self):
        for sequence, encoded in ((1, "YQ=="), (0, "not base64!")):
            token = self.bridge.begin_download("result.txt", 10)["id"]
            with self.assertLogs("desktop.bridge", level="ERROR"):
                self.assertIn("error", self.bridge.write_download(token, sequence, encoded))
            self.assertEqual(list(self.directory.iterdir()), [])

    def test_oversize_and_overflow_rejected(self):
        with self.assertLogs("desktop.bridge", level="ERROR"):
            self.assertIn("error", self.bridge.begin_download("too-big.zip", 3 * 1024**3))
            self.assertIn("error", self.bridge.begin_download("bool.txt", True))
        token = self.bridge.begin_download("result.txt", 1)["id"]
        with self.assertLogs("desktop.bridge", level="ERROR"):
            self.assertIn("error", self.bridge.write_download(token, 0, "YWJj"))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_atomic_rename_failure_is_reported_and_cleaned(self):
        token = self.bridge.begin_download("result.txt", 0)["id"]
        with patch.object(Path, "replace", side_effect=PermissionError("destination is read-only")):
            with self.assertLogs("desktop.bridge", level="ERROR"):
                self.assertIn("read-only", self.bridge.finish_download(token)["error"])
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
