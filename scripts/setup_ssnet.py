"""Install a shared local inference environment; never start model training."""
import argparse
from pathlib import Path
import subprocess
import sys
from model_environment import ensure_environment, require_installer_python

def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy')
    args=parser.parse_args()
    require_installer_python(parser)
    python=ensure_environment(root)
    pip=[str(python),'-m','pip','install']+(['--proxy',args.proxy] if args.proxy else [])
    subprocess.run(pip+['torch==2.4.1','--index-url','https://download.pytorch.org/whl/cpu'],check=True)
    subprocess.run(pip+['-r',str(root/'services/ssnet/requirements.txt')],check=True)
    print('SSnet dependencies installed. Start the website normally; no training has been launched.')


if __name__ == '__main__':
    main()
