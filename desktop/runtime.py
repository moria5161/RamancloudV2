"""Frozen-safe assets, ASGI routing, and the owned loopback server."""

import contextlib
import json
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .bridge import BRIDGE_JS

logger = logging.getLogger(__name__)
UI_ROUTES = ("", "spectral", "hyperspectral", "extra-tools", "tutorial", "contributors")
DOC_PATHS = ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json")
OFFLINE_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self' blob:; worker-src 'self' blob:; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


def frontend_directory(override=None):
    if getattr(sys, "frozen", False):
        if override is not None:
            raise ValueError("Frozen apps always use their bundled frontend")
        directory = Path(sys._MEIPASS) / "frontend_dist"
    else:
        directory = Path(override).expanduser().resolve() if override else Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if not (directory / "index.html").is_file():
        raise FileNotFoundError(f"Built frontend not found: {directory}. Build it with npm ci and npm run build, or pass --frontend-dist.")
    return directory


def local_opener():
    # Corporate proxy settings must never send local scientific data off the machine.
    return build_opener(ProxyHandler({}))


def relative_path(scope):
    path, root = scope["path"], scope.get("root_path", "")
    if root and (path == root or path.startswith(root + "/")):
        path = path[len(root):]
    return path or "/"


class Frontend(StaticFiles):
    def __init__(self, *args, native_downloads=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.native_downloads = native_downloads

    async def get_response(self, path, scope):
        route = path.replace("\\", "/").strip("/")
        if route == ".":
            route = ""
        if route in UI_ROUTES:
            index = (Path(self.directory) / "index.html").read_text(encoding="utf-8")
            if "<head>" not in index:
                raise RuntimeError("Frontend index.html has no head element")
            native = "true" if self.native_downloads else "false"
            index = index.replace("<head>", f'<head><script src="/preprocessing/__desktop__/bridge.js" data-native-downloads="{native}"></script>', 1)
            return HTMLResponse(index, headers={"Cache-Control": "no-store"})
        if route == "__desktop__/bridge.js":
            return Response(BRIDGE_JS, media_type="application/javascript", headers={"Cache-Control": "no-store"})
        return await super().get_response(path, scope)


class BackendAndFrontend:
    def __init__(self, backend, frontend, native_downloads=True):
        self.backend = backend
        self.frontend = Frontend(directory=frontend, html=False, native_downloads=native_downloads)

    async def __call__(self, scope, receive, send):
        path = relative_path(scope)
        target = self.backend if path == "/api" or path.startswith("/api/") or path in DOC_PATHS else self.frontend
        await target(scope, receive, send)


class LocalOnly:
    def __init__(self, app, origin):
        self.app, self.origin = app, origin
        self.host = origin.removeprefix("http://")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        host = headers.get(b"host", b"").decode("latin-1")
        origin = headers.get(b"origin", b"").decode("latin-1")
        fetch_site = headers.get(b"sec-fetch-site", b"")
        if host != self.host or (origin and origin != self.origin) or fetch_site == b"cross-site":
            await PlainTextResponse("Only this local RamanCloud window may access the desktop server", status_code=403)(scope, receive, send)
            return

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                extra = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")]
                # API documentation deliberately retains FastAPI's original behavior.
                if relative_path(scope) not in DOC_PATHS:
                    extra.append((b"content-security-policy", OFFLINE_CSP.encode("ascii")))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, secured_send)


def create_app(backend, frontend, origin, native_downloads=True):
    @contextlib.asynccontextmanager
    async def lifespan(app):
        # Mounted FastAPI apps do not automatically receive the parent's lifespan.
        async with backend.router.lifespan_context(backend):
            yield

    async def home(request):
        return RedirectResponse("/preprocessing/")

    wrapper = Starlette(lifespan=lifespan, routes=[
        Route("/", home),
        Route("/preprocessing", home),
        Mount("/preprocessing", app=BackendAndFrontend(backend, frontend, native_downloads)),
        Mount("/", app=backend),
    ])
    return LocalOnly(wrapper, origin)


class RuntimeServer:
    def __init__(self, frontend, data_directory, backend=None, native_downloads=True):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.thread = None
        self.error = None
        self.server = None
        try:
            if os.name == "nt":
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind(("127.0.0.1", 0))
            self.socket.listen(128)
            self.socket.setblocking(False)
            self.origin = f"http://127.0.0.1:{self.socket.getsockname()[1]}"
            os.environ["RAMANCLOUD_ANALYTICS_DIR"] = str(Path(data_directory) / "analytics")
            os.environ["RAMANCLOUD_ANALYTICS_ORIGINS"] = self.origin
            os.environ["RAMANCLOUD_ANALYTICS_TRUSTED_PROXIES"] = ""
            if backend is None:
                from ramancloud_backend.app import app as backend
            self.backend = backend
            config = uvicorn.Config(create_app(backend, frontend, self.origin, native_downloads), host="127.0.0.1", port=0,
                                    loop="asyncio", http="h11", ws="none", lifespan="on", log_config=None,
                                    access_log=False, proxy_headers=False, timeout_graceful_shutdown=10)
            self.server = uvicorn.Server(config)
        except BaseException:
            self.socket.close()
            raise

    @property
    def url(self):
        return self.origin + "/preprocessing/"

    def _run(self):
        try:
            self.server.run(sockets=[self.socket])
        except BaseException as error:
            self.error = error
            logger.exception("Desktop API server failed")

    def start(self, timeout=45):
        self.thread = threading.Thread(target=self._run, name="ramancloud-api", daemon=False)
        self.thread.start()
        deadline = time.monotonic() + timeout
        opener = local_opener()
        while time.monotonic() < deadline:
            if self.error or not self.thread.is_alive():
                raise RuntimeError("Desktop API exited before becoming ready") from self.error
            if self.server.started:
                try:
                    with opener.open(Request(self.url + "api/health"), timeout=1) as response:
                        if json.load(response).get("code") == 0:
                            logger.info("Desktop API ready at %s", self.url)
                            return self
                except (URLError, OSError, ValueError):
                    pass
            time.sleep(0.05)
        raise TimeoutError("Desktop API was not ready within 45 seconds")

    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                self.server.force_exit = True
                self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError("Desktop API did not shut down; consult the log")
        self.socket.close()
        logger.info("Desktop API stopped")
