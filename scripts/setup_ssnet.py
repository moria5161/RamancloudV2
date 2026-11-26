"""Install the environment for SSnet training and inference."""
import argparse
from pathlib import Path
import subprocess
from model_environment import ensure_environment, require_installer_python

def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy')
    parser.add_argument('--cuda', action='store_true', help='Install the CUDA build in .venv-ssnet.')
    args=parser.parse_args()
    require_installer_python(parser)
    if args.cuda:
        python=ensure_environment(root, '.venv-ssnet')
        torch_version, wheel_index = '2.5.1', 'cu124'
    else:
        python=ensure_environment(root)
        torch_version, wheel_index = '2.4.1', 'cpu'
    pip=[str(python),'-m','pip','install']+(['--proxy',args.proxy] if args.proxy else [])
    subprocess.run(pip+[f'torch=={torch_version}', '--index-url',
                       f'https://download.pytorch.org/whl/{wheel_index}'], check=True)
    subprocess.run(pip+['-r',str(root/'services/ssnet/requirements.txt')],check=True)
    print('SSnet dependencies installed. Start the website normally; no training has been launched.')


if __name__ == '__main__':
    main()
