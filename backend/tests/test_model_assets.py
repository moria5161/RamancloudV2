"""Exercise local LFS files, pointer fallback and HTTP range resume without large downloads."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import model_assets


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='model-assets-test-')
        self.root = Path(self.temp.name)
        (self.root / 'model-assets').mkdir()
        self.payload = b'checked model test payload' * 32
        self.name = 'test.zip'
        self.local = self.root / 'model-assets' / self.name
        meta = dict(bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest())
        (self.local.parent / 'manifest.json').write_text(json.dumps({self.name: meta}), encoding='utf-8')
        self.patch_root = patch.object(model_assets, 'ROOT', self.root)
        self.patch_root.start()

    def tearDown(self):
        self.patch_root.stop()
        self.temp.cleanup()

    def test_existing_full_asset_needs_no_download(self):
        self.local.write_bytes(self.payload)
        self.assertEqual(model_assets.ensure_asset(self.name), self.local)
        self.assertFalse((self.root / '.runtime').exists())

    def test_modified_asset_is_preserved(self):
        self.local.write_bytes(b'user local changes')
        with self.assertRaisesRegex(RuntimeError, 'differs'):
            model_assets.ensure_asset(self.name)
        self.assertEqual(self.local.read_bytes(), b'user local changes')

    def test_pointer_download_and_resume_do_not_replace_git_pointer(self):
        pointer = b'version https://git-lfs.github.com/spec/v1\noid sha256:test\nsize 832\n'
        self.local.write_bytes(pointer)
        partial = self.root / '.runtime/downloads/test.zip.part'
        partial.parent.mkdir(parents=True)
        partial.write_bytes(self.payload[:19])
        received = []
        payload = self.payload
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                received.append(self.headers.get('Range'))
                start = int(self.headers.get('Range', 'bytes=0-').split('=')[1].split('-')[0])
                self.send_response(206 if start else 200)
                if start:
                    self.send_header('Content-Range', f'bytes {start}-{len(payload)-1}/{len(payload)}')
                self.send_header('Content-Length', str(len(payload)-start))
                self.end_headers()
                self.wfile.write(payload[start:])
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(model_assets, 'ASSET_BASE', f'http://127.0.0.1:{server.server_port}/'):
                downloaded = model_assets.ensure_asset(self.name)
            self.assertEqual(downloaded.read_bytes(), self.payload)
            self.assertEqual(received, ['bytes=19-'])
            self.assertEqual(self.local.read_bytes(), pointer)
            self.assertFalse(partial.exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


if __name__ == '__main__':
    unittest.main()
