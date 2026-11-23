"""Prepare the existing independent model environment for original V2 algorithms."""
import os
import argparse
import subprocess
import sys
import venv
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--proxy')
args=parser.parse_args()
root = Path(__file__).resolve().parents[1]
target = root/'.venv-vib2mol'
python = target/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
if sys.version_info < (3, 9):
    raise SystemExit('Use Python 3.11/3.12 for this installer, not the legacy backend Python.')
if not python.is_file():
    venv.create(str(target), with_pip=True)
command=[str(python), '-m', 'pip', 'install', 'numpy>=1.24,<3', 'scipy>=1.11,<2', 'PyWavelets>=1.5,<2', 'pybaselines==1.2.1']
if args.proxy:command += ['--proxy',args.proxy]
subprocess.check_call(command)
if subprocess.call([str(python),'-c','import torch; assert tuple(map(int,torch.__version__.split("+")[0].split(".")[:2])) >= (2,5)']) != 0:
    command=[str(python),'-m','pip','install','torch>=2.5,<3','--index-url','https://download.pytorch.org/whl/cpu']
    if args.proxy:command+=['--proxy',args.proxy]
    subprocess.check_call(command)
command=[str(python),str(root/'scripts/fetch_preprocessing_models.py')]
if args.proxy:command+=['--proxy',args.proxy]
subprocess.check_call(command)
airnet = Path(os.environ.get('RAMANCLOUD_AIRNET_MODEL') or root/'backend/baseline_cor/model_pt/0925RU_statedict.pth')
if not airnet.is_file():
    raise SystemExit('AirNet weights are missing. Set RAMANCLOUD_AIRNET_MODEL to the approved checkpoint path.')
print('All preprocessing runtimes prepared. Restart backend; model integrity and real inference must still be verified.')
