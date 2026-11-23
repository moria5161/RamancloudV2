"""Install the supplied library matching package without changing the web backend environment."""
import argparse
import subprocess
import sys
from pathlib import Path
from model_environment import ensure_environment, require_installer_python
from model_assets import ensure_asset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from peaknet_package import install_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', help='Optional local package; defaults to the repository model asset.')
    parser.add_argument('--proxy')
    args = parser.parse_args()
    require_installer_python(parser)
    python = ensure_environment(ROOT)
    archive = args.archive or ensure_asset('peaknet-package.zip', args.proxy)
    manifest = install_package(archive)
    print(f"Verified {len(manifest['files'])} runtime artifacts. No training is required.", flush=True)
    pip = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check']
    if args.proxy:
        pip += ['--proxy', args.proxy]
    subprocess.run(pip + ['torch==2.4.1', 'torchvision==0.19.1', '--index-url', 'https://download.pytorch.org/whl/cpu'], check=True)
    subprocess.run(pip + ['-r', str(ROOT / 'services/peaknet/requirements.txt')], check=True)
    print('Restart the backend and open the library matching page.')


if __name__ == '__main__':
    main()
