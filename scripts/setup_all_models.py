"""Install all three model runtimes and the Agent; obtain required assets automatically."""
import argparse
from pathlib import Path
import subprocess
import sys
from model_environment import require_installer_python


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy', help='Optional HTTP proxy used only by this invocation.')
    parser.add_argument('--skip-agent', action='store_true', help='Install only the three base features.')
    args = parser.parse_args()
    require_installer_python(parser)
    root = Path(__file__).resolve().parents[1]
    scripts = ['setup_vib2mol.py', 'setup_peaknet.py', 'setup_ssnet.py', 'setup_legacy_algorithms.py']
    if not args.skip_agent:
        scripts.append('setup_vib2mol_agent.py')
    for script in scripts:
        print('\nInstalling ' + script, flush=True)
        command = [sys.executable, str(root / 'scripts' / script)]
        if args.proxy:
            command += ['--proxy', args.proxy]
        subprocess.run(command, check=True)
    print('All selected model runtimes are installed. Restart the web backend and refresh/rebuild the frontend. SSnet training has not been started.')


if __name__ == '__main__':
    main()
