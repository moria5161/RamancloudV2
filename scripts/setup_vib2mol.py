"""Install the two official Raman checkpoints and isolated CPU inference runtime."""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from model_environment import ensure_environment, require_installer_python
from model_assets import ensure_asset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from structure_profiles import ARTIFACTS, SOURCE_REVISION, WEIGHTS_REVISION


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy', help='Optional HTTP(S) proxy, e.g. http://127.0.0.1:PORT')
    args = parser.parse_args()
    require_installer_python(parser)
    python = ensure_environment(ROOT)
    runtime = ROOT / '.runtime/vib2mol'
    runtime.mkdir(parents=True, exist_ok=True)
    source = runtime / 'source'
    git = ['git']
    if os.name == 'nt':
        git += ['-c', 'http.sslBackend=schannel']
    if args.proxy:
        git += ['-c', 'http.proxy=' + args.proxy]
    if not source.exists():
        subprocess.run(git + ['clone', '--no-checkout', 'https://github.com/X1nyuLu/vib2mol.git', str(source)], check=True)
        subprocess.run(git + ['-C', str(source), 'checkout', '--detach', SOURCE_REVISION], check=True)
    revision = subprocess.check_output(git + ['-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != SOURCE_REVISION:
        raise RuntimeError('Source revision differs. Preserve local changes and configure a separate runtime directory.')
    # An explicit proxy applies only to this invocation, never to system or global Git settings.
    for name, artifact in ARTIFACTS.items():
        target = runtime / (name + '.pth')
        if target.exists() and digest(target) == artifact['sha256']:
            print(name + ': verified, already installed', flush=True)
            continue
        url = f"https://huggingface.co/xinyulu/vib2mol/resolve/{WEIGHTS_REVISION}/{artifact['path']}?download=true"
        temporary = target.with_suffix('.pth.part')
        asset = ensure_asset('vib2mol-' + name + '.pth', args.proxy, fallback_url=url)
        with asset.open('rb') as src, temporary.open('wb') as stream:
            shutil.copyfileobj(src, stream, length=1024 * 1024)
        if digest(temporary) != artifact['sha256']:
            raise RuntimeError(name + ': SHA-256 mismatch; weight was not installed.')
        temporary.replace(target)
    common = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check']
    if args.proxy:
        common += ['--proxy', args.proxy]
    subprocess.run(common + ['torch==2.4.1', '--index-url', 'https://download.pytorch.org/whl/cpu'], check=True)
    subprocess.run(common + ['-r', str(ROOT / 'services/vib2mol/requirements.txt')], check=True)
    print('Installed. Restart the Ramancloud backend. No separate model terminal is required.')


if __name__ == '__main__':
    main()
