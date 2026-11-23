"""Create or check the shared model environment without replacing existing files."""
import json
import os
from pathlib import Path
import subprocess
import sys


def require_installer_python(parser):
    if sys.version_info[:2] not in ((3, 11), (3, 12)):
        parser.error('Use Python 3.11 or 3.12 (recommended: py -3.12). The model wheels are pinned for these versions.')


def ensure_environment(root):
    folder = Path(root) / '.venv-vib2mol'
    python = folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(folder)], check=True)
    version = json.loads(subprocess.check_output([str(python), '-c',
        'import json,sys; print(json.dumps(list(sys.version_info[:2])))'], text=True))
    if version not in ([3, 11], [3, 12]):
        raise RuntimeError('Existing .venv-vib2mol uses unsupported Python ' + '.'.join(map(str, version)) +
                           '. Preserve/rename that environment, then rerun with Python 3.12. No environment was deleted.')
    return python
