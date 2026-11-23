"""Resolve checksummed model files from Git LFS or download them automatically."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
ASSET_REF = 'algorithm-assets-2026-10-29'
ASSET_BASE = f'https://media.githubusercontent.com/media/hzh040518/Ramancloud/{ASSET_REF}/model-assets/'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def is_pointer(path):
    with Path(path).open('rb') as stream:
        return stream.read(100).startswith(b'version https://git-lfs.github.com/spec/v1\n')


def checkout_lfs_asset(name, proxy=None):
    """Use normal Git LFS authentication; never extract a credential for HTTP."""
    if not (ROOT / '.git').exists() or not shutil.which('git'):
        return False
    git = ['git', '-C', str(ROOT)]
    if os.name == 'nt':
        git += ['-c', 'http.sslBackend=schannel']
    if proxy:
        git += ['-c', 'http.proxy=' + proxy]
    available = subprocess.run(git + ['lfs', 'version'], capture_output=True)
    if available.returncode:
        return False
    print(name + ': retrieving through the existing Git repository login', flush=True)
    fetched = subprocess.run(git + ['lfs', 'fetch', 'origin', ASSET_REF,
        '--include=model-assets/' + name, '--exclude='])
    if fetched.returncode:
        return False
    checked_out = subprocess.run(git + ['lfs', 'checkout', '--', 'model-assets/' + name])
    return checked_out.returncode == 0


def download(url, target, expected, proxy=None):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.part')
    opener = build_opener(ProxyHandler({'http': proxy, 'https': proxy}) if proxy else ProxyHandler())
    for attempt in range(3):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset >= expected['bytes']:
                offset = 0
            request = Request(url, headers={'User-Agent': 'Ramancloud-model-installer', **({'Range': f'bytes={offset}-'} if offset else {})})
            print(f"Downloading {target.name} ({expected['bytes']/1e6:.1f} MB)", flush=True)
            with opener.open(request, timeout=120) as response:
                resume = offset and response.status == 206 and response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')
                if response.status == 206 and not resume:
                    raise RuntimeError('Server returned an unexpected byte range.')
                with partial.open('ab' if resume else 'wb') as stream:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        stream.write(block)
            if partial.stat().st_size != expected['bytes'] or digest(partial) != expected['sha256']:
                raise RuntimeError('Size or SHA-256 mismatch for ' + target.name + '; file was not installed.')
            partial.replace(target)
            return target
        except (OSError, RuntimeError) as exc:
            if attempt == 2:
                raise RuntimeError(f'Automatic download failed for {target.name}. Retry with --proxy if needed, or run git lfs pull. {exc}') from exc
            time.sleep(attempt + 1)


def ensure_asset(name, proxy=None, fallback_url=None):
    manifest = json.loads((ROOT / 'model-assets/manifest.json').read_text(encoding='utf-8'))
    if name not in manifest or Path(name).name != name:
        raise ValueError('Unknown model asset: ' + name)
    expected = manifest[name]
    local = ROOT / 'model-assets' / name
    if local.is_file() and not is_pointer(local):
        if local.stat().st_size == expected['bytes'] and digest(local) == expected['sha256']:
            print(name + ': verified local Git LFS asset', flush=True)
            return local
        raise RuntimeError('Local model-assets file differs from the manifest; preserve changes and check git lfs pull: ' + name)
    if checkout_lfs_asset(name, proxy) and local.is_file() and not is_pointer(local):
        if local.stat().st_size == expected['bytes'] and digest(local) == expected['sha256']:
            return local
        raise RuntimeError('Git LFS object does not match the pinned manifest: ' + name)
    cached = ROOT / '.runtime/downloads' / name
    if cached.is_file() and cached.stat().st_size == expected['bytes'] and digest(cached) == expected['sha256']:
        return cached
    try:
        return download(ASSET_BASE + quote(name), cached, expected, proxy)
    except RuntimeError:
        if not fallback_url:
            raise RuntimeError('Cannot retrieve ' + name + '. For a repository that requires login, update it with your authorized Git account and run git lfs install / git lfs pull. Source ZIP downloads cannot use the Git login. No separate archive or new access token is required.') from None
        print(name + ': trying the official upstream source', flush=True)
        # A partial object from a different host must never be appended to it.
        return download(fallback_url, cached.with_name('upstream-' + name), expected, proxy)
