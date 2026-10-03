import os
import socket
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI

from desktop.runtime import RuntimeServer, UI_ROUTES, frontend_directory
from desktop.smoke import Client


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.frontend = self.directory / "frontend"
        (self.frontend / "assets").mkdir(parents=True)
        (self.frontend / "index.html").write_text('<html><head></head><body><div id="root"></div></body></html>', encoding="utf-8")
        (self.frontend / "assets/main.js").write_text("console.log('local');", encoding="utf-8")
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.started, self.finished = False, False

        @asynccontextmanager
        async def lifespan(app):
            self.started = True
            yield
            self.finished = True

        backend = FastAPI(lifespan=lifespan)

        @backend.get("/api/health")
        def health():
            return {"code": 0, "data": {"framework": "FastAPI"}}

        self.runtime = RuntimeServer(self.frontend, self.directory / "data", backend=backend)
        self.client = Client(self.runtime.origin)

    def tearDown(self):
        self.runtime.stop()
        self.environment.stop()
        self.temporary.cleanup()

    def test_homepage_dot_and_all_deep_routes(self):
        self.runtime.start()
        for route in UI_ROUTES:
            with self.subTest(route=route):
                body, headers = self.client.request("/preprocessing/" + route)
                self.assertIn(b'<div id="root"', body)
                self.assertIn(b'data-native-downloads="true"', body)
                self.assertIn("text/html", headers["Content-Type"])
        self.assertEqual(self.client.request("/")[0], self.client.request("/preprocessing/")[0])
        self.assertEqual(self.client.request("/preprocessing")[0], self.client.request("/preprocessing/")[0])

    def test_assets_and_api_are_never_shadowed_by_spa(self):
        self.runtime.start()
        body, _ = self.client.request("/preprocessing/assets/main.js")
        self.assertEqual(body, b"console.log('local');")
        self.assertEqual(self.client.json("/api/health"), self.client.json("/preprocessing/api/health"))
        for path in ("/preprocessing/api/no-such-route", "/preprocessing/assets/no-such.js", "/preprocessing/no-such-page"):
            body, _ = self.client.request(path, expected=404)
            self.assertNotIn(b'<div id="root"', body)
        for path in ("/openapi.json", "/preprocessing/openapi.json"):
            self.assertIn("/api/health", self.client.json(path)["paths"])
        self.assertIn(b"/preprocessing/openapi.json", self.client.request("/preprocessing/docs")[0])

    def test_loopback_socket_is_reserved_before_uvicorn_and_released(self):
        address = self.runtime.socket.getsockname()
        self.assertEqual(address[0], "127.0.0.1")
        with socket.socket() as contender:
            with self.assertRaises(OSError):
                contender.bind(address)
        self.runtime.start()
        self.assertTrue(self.started)
        self.runtime.stop()
        self.assertTrue(self.finished)
        self.assertFalse(self.runtime.thread.is_alive())
        self.assertEqual(self.runtime.socket.fileno(), -1)
        with socket.socket() as connection:
            self.assertNotEqual(connection.connect_ex(address), 0)

    def test_untrusted_browser_origins_and_rebinding_are_rejected(self):
        self.runtime.start()
        for headers in ({"Origin": "https://remote.invalid"}, {"Origin": "null"}, {"Host": "remote.invalid"}, {"Sec-Fetch-Site": "cross-site"}):
            self.client.request("/preprocessing/api/health", headers=headers, expected=403)
        self.client.request("/preprocessing/api/health", headers={"Origin": self.runtime.origin})

    def test_frontend_paths_do_not_depend_on_cwd(self):
        with patch("desktop.runtime.sys.frozen", True, create=True), patch("desktop.runtime.sys._MEIPASS", str(self.directory), create=True):
            (self.directory / "frontend_dist").mkdir()
            (self.directory / "frontend_dist/index.html").write_text("frozen", encoding="utf-8")
            self.assertEqual(frontend_directory(), self.directory / "frontend_dist")
            with self.assertRaises(ValueError):
                frontend_directory(self.frontend)
        self.assertEqual(frontend_directory(self.frontend), self.frontend)
        with self.assertRaises(FileNotFoundError):
            frontend_directory(self.directory / "missing")

    def test_serve_mode_can_use_browser_downloads(self):
        self.runtime.socket.close()
        self.runtime = RuntimeServer(self.frontend, self.directory / "data", backend=self.runtime.backend, native_downloads=False)
        self.client = Client(self.runtime.origin)
        self.runtime.start()
        self.assertIn(b'data-native-downloads="false"', self.client.request("/preprocessing/")[0])


if __name__ == "__main__":
    unittest.main()
