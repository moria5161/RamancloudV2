"""Authenticated loopback transport and lifetime management for local model workers."""
import argparse
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve(service, profile_id, predict):
    token = os.environ['RAMANCLOUD_INFERENCE_TOKEN']
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body):
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if not hmac.compare_digest(self.headers.get('X-Worker-Token', ''), token):
                self.respond(403, {'error': 'Forbidden'})
                return False
            return True

        def do_GET(self):
            if self.authorized():
                self.respond(200, dict(service=service, profile_id=profile_id))

        def do_POST(self):
            if not self.authorized():
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2 * 1024 * 1024:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(size))
                with lock:
                    result = predict(payload)
                self.respond(200, result)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                self.respond(500, {'error': str(exc)[:500]})

    parent = os.getppid()

    def watch_parent():
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            handle = kernel.OpenProcess(0x100000, False, parent)
            if handle:
                kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
                os._exit(0)
        else:
            while os.getppid() == parent:
                time.sleep(2)
            os._exit(0)

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    threading.Thread(target=watch_parent, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
