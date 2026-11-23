"""Own and reuse one isolated, authenticated local inference process."""
import json
import os
import secrets
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from structure_profiles import ROOT


class LocalRuntime:
    def __init__(self, service='ramancloud-vib2mol', script='services/vib2mol/server.py', log_name='vib2mol-worker.log'):
        self.service, self.script, self.log_name = service, script, log_name
        self.process = None
        self.signature = None
        self.opener = build_opener(ProxyHandler({}))

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    def infer(self, profile, paths, payload):
        signature = json.dumps([profile, paths], sort_keys=True)
        if not self.process or self.process.poll() is not None or signature != self.signature:
            self.close()
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            self.url = f'http://127.0.0.1:{port}'
            self.token = secrets.token_hex(32)
            env = dict(os.environ, RAMANCLOUD_VIB2MOL_CONFIG=json.dumps(dict(profile=profile, paths=paths)),
                       RAMANCLOUD_VIB2MOL_TOKEN=self.token, PYTHONUTF8='1', HF_HUB_OFFLINE='1',
                       RAMANCLOUD_INFERENCE_CONFIG=json.dumps(dict(profile=profile, paths=paths)),
                       RAMANCLOUD_INFERENCE_TOKEN=self.token, MPLBACKEND='Agg',
                       MPLCONFIGDIR=str(ROOT / 'logs/matplotlib-cache'),
                       HF_HOME=str(ROOT / '.runtime/vib2mol/hf-cache'), TOKENIZERS_PARALLELISM='false',
                       OMP_NUM_THREADS=str(profile['threads']), MKL_NUM_THREADS=str(profile['threads']))
            log_dir = ROOT / 'logs'
            log_dir.mkdir(exist_ok=True)
            with (log_dir / self.log_name).open('ab') as log:
                self.process = subprocess.Popen([paths['python'], str(ROOT / self.script), '--port', str(port)],
                                                cwd=str(ROOT), env=env, stdout=log, stderr=log,
                                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.signature = signature
            for _ in range(100):
                if self.process.poll() is not None:
                    raise RuntimeError('模型进程启动失败，请查看 logs/' + self.log_name + '。')
                try:
                    info = self.request(None, timeout=1)
                    if info.get('service') == self.service and info.get('profile_id') == profile['id']:
                        break
                except (URLError, OSError):
                    time.sleep(.1)
            else:
                self.close()
                raise RuntimeError('模型进程启动超时。')
        try:
            return self.request(payload, timeout=1200)
        except HTTPError as exc:
            detail = json.loads(exc.read()).get('error', '模型执行失败。')
            raise RuntimeError(detail) from exc
        except (URLError, OSError) as exc:
            self.close()
            raise RuntimeError('模型进程连接中断，请重试。') from exc

    def request(self, payload, timeout):
        request = Request(self.url, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={'X-Worker-Token': self.token, 'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=timeout) as response:
            return json.load(response)
