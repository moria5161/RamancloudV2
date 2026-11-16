from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib


def application_version():
    project = Path(__file__).resolve().parents[1] / 'pyproject.toml'
    if project.is_file():
        with project.open('rb') as stream:
            return tomllib.load(stream)['project']['version']
    try:
        return version('ramancloud')
    except PackageNotFoundError:
        return 'unknown'


APPLICATION_VERSION = application_version()
