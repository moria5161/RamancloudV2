"""Install the user-supplied Agent archive into the existing isolated runtime."""
import argparse
import os
import subprocess
import sys
from pathlib import Path
from model_environment import ensure_environment, require_installer_python
from model_assets import ensure_asset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from vib2mol_agent_package import install_agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', help='Optional original or slim runtime ZIP; otherwise resolved automatically.')
    parser.add_argument('--proxy')
    args = parser.parse_args()
    require_installer_python(parser)
    python = ROOT / '.venv-vib2mol' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        parser.error('请先运行 scripts/setup_vib2mol.py 安装官方模型与独立环境。')
    python = ensure_environment(ROOT)
    archive = args.archive or ensure_asset('vib2mol-agent-runtime.zip', args.proxy)
    manifest = install_agent(archive, ROOT / '.runtime/vib2mol/source')
    print(f"Agent code installed and verified: {manifest['files']} files. No model weights are included.", flush=True)
    command = [str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'services/vib2mol/requirements.txt'), '--disable-pip-version-check']
    if args.proxy:
        command += ['--proxy', args.proxy]
    subprocess.run(command, check=True)
    print('Restart the backend, then choose Vib2Mol Agent on the structure generation page.')


if __name__ == '__main__':
    main()
