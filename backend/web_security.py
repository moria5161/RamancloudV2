"""Web-only session isolation and bounded request admission. Local tools stay offline."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import OrderedDict
from contextvars import ContextVar
from pathlib import Path
from threading import Lock

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

DATA_OWNER = ContextVar('ramancloud_data_owner', default=None)
COOKIE_NAME = '__Secure-ramancloud-session'
MAX_BODY_BYTES = 200 * 1024 * 1024
MAX_FORM_BODY_BYTES = 64 * 1024
MAX_NUMERIC_VALUES = 32_000_000
SESSION_SECONDS = 12 * 60 * 60


def web_security_enabled():
    return os.environ.get('RAMANCLOUD_WEB_SECURITY', '0') == '1'


def current_owner():
    return DATA_OWNER.get()


class WebSecurityMiddleware:
    def __init__(self, app, enabled=None, secret=None, secure=True, cookie_path=None, origins=None):
        self.app = app
        self.enabled = web_security_enabled() if enabled is None else enabled
        self.secure = secure
        self.cookie_path = cookie_path or os.environ.get('RAMANCLOUD_SESSION_COOKIE_PATH', '/ramancloud-api/')
        self.origins = set(origins or os.environ.get('RAMANCLOUD_WEB_ORIGINS', 'https://ramancloud.xmu.edu.cn').split(','))
        self.secret = secret
        if self.enabled and self.secret is None:
            path = Path(os.environ.get('RAMANCLOUD_SESSION_SECRET_FILE', Path(__file__).parent / 'runtime' / 'session-secret'))
            self.secret = path.read_bytes().strip()
        if self.enabled and len(self.secret or b'') < 32:
            raise RuntimeError('Web sessions require a private secret of at least 32 bytes')
        self.lock = Lock()
        self.rates = OrderedDict()
        self.active = {}
        self.heavy = 0
        self.requests = 0

    def sign(self, value):
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    def token(self, owner):
        value = f'{owner}.{int(time.time())}'
        return f'{value}.{self.sign(value)}'

    def owner(self, cookie):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}\.\d{1,12}\.[0-9a-f]{64}', cookie or ''):
            return None
        try:
            owner, issued, signature = cookie.split('.')
            if len(owner) != 43 or len(signature) != 64:
                return None
            age = time.time() - int(issued)
            if not 0 <= age <= SESSION_SECONDS:
                return None
            if not hmac.compare_digest(signature, self.sign(f'{owner}.{issued}')):
                return None
            return owner
        except (ValueError, AttributeError):
            return None

    def limited(self, key, limit):
        now = time.monotonic()
        with self.lock:
            tokens, updated = self.rates.pop(key, (float(limit), now))
            tokens = min(float(limit), tokens + (now - updated) * limit / 60)
            allowed = tokens >= 1
            self.rates[key] = (tokens - 1 if allowed else tokens, now)
            while len(self.rates) > 10_000:
                self.rates.popitem(last=False)
            return not allowed

    async def reject(self, scope, receive, send, status, detail):
        headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
        if status in (429, 503):
            headers['Retry-After'] = '2'
        await JSONResponse({'detail': detail}, status_code=status, headers=headers)(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if not self.enabled or scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        path = scope['path'].removeprefix(scope.get('root_path', ''))
        if not path.startswith('/api/'):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        method = scope['method']
        origin = request.headers.get('origin')
        if (origin and origin not in self.origins) or request.headers.get('sec-fetch-site') == 'cross-site':
            await self.reject(scope, receive, send, 403, 'Cross-site API access is not allowed')
            return
        ip = scope.get('client', ('unknown',))[0]
        ip_key = self.sign('ip:' + ip)
        if self.limited('ip:' + ip_key, 1800):
            await self.reject(scope, receive, send, 429, 'API request rate exceeded')
            return
        try:
            length = int(request.headers.get('content-length', '0'))
            if length < 0:
                raise ValueError()
        except ValueError:
            await self.reject(scope, receive, send, 400, 'Invalid content length')
            return
        # Text forms only carry small structure inputs, never spectral files.
        content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
        body_limit = min(MAX_BODY_BYTES, MAX_FORM_BODY_BYTES) if content_type == 'application/x-www-form-urlencoded' else MAX_BODY_BYTES
        size_error = 'Form exceeds the 64 KiB size limit' if body_limit < MAX_BODY_BYTES else 'Request exceeds the 200 MiB size limit'
        if length > body_limit:
            await self.reject(scope, receive, send, 413, size_error)
            return
        owner = self.owner(request.cookies.get(COOKIE_NAME))
        if path == '/api/session' and method == 'GET':
            if self.limited('bootstrap:' + ip_key, 60):
                await self.reject(scope, receive, send, 429, 'Session request rate exceeded')
                return
            owner = owner or base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
            response = JSONResponse({'csrf_token': self.sign('csrf:' + owner)}, headers={
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
            response.set_cookie(COOKIE_NAME, self.token(owner), max_age=SESSION_SECONDS,
                                httponly=True, secure=self.secure, samesite='strict', path=self.cookie_path)
            await response(scope, receive, send)
            return
        public = (path in ('/api/health', '/api/visits/summary') and method == 'GET') or path == '/api/visits/pageview'
        if not public:
            if owner is None:
                await self.reject(scope, receive, send, 401, 'A RamanCloud workspace session is required. Reload the page.')
                return
            if method not in ('GET', 'HEAD', 'OPTIONS'):
                csrf = request.headers.get('x-ramancloud-csrf', '')
                if not hmac.compare_digest(csrf.encode('utf-8'), self.sign('csrf:' + owner).encode('ascii')):
                    await self.reject(scope, receive, send, 403, 'Invalid workspace request token')
                    return
            if self.limited('session:' + owner, 1200):
                await self.reject(scope, receive, send, 429, 'Workspace request rate exceeded')
                return
        heavy = (method == 'POST' and path.startswith((
            '/api/process', '/api/upload', '/api/tools/', '/api/structure/', '/api/download',
        ))) or path.startswith('/api/demo-hyperspectral/')
        if heavy and self.limited('compute:' + owner, 120):
            await self.reject(scope, receive, send, 429, 'Workspace task rate exceeded')
            return
        with self.lock:
            overloaded = self.requests >= 64 or (heavy and (self.heavy >= 2 or self.active.get(owner, 0) >= 1))
            if not overloaded:
                self.requests += 1
                if heavy:
                    self.heavy += 1
                    self.active[owner] = self.active.get(owner, 0) + 1
        if overloaded:
            await self.reject(scope, receive, send, 429, 'Processing capacity is busy. Please retry shortly.')
            return
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > body_limit:
                    raise HTTPException(413, size_error)
            return message

        async def private_send(message):
            if message['type'] == 'http.response.start':
                message = dict(message)
                headers = [(key, value) for key, value in message.get('headers', []) if key.lower() != b'cache-control']
                headers.extend([(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff')])
                message['headers'] = headers
            await send(message)

        context = DATA_OWNER.set(owner)
        try:
            await self.app(scope, bounded_receive, private_send)
        finally:
            DATA_OWNER.reset(context)
            with self.lock:
                self.requests -= 1
                if heavy:
                    self.heavy -= 1
                    self.active[owner] -= 1
                    if not self.active[owner]:
                        del self.active[owner]
