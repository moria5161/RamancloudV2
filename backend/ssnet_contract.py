"""Physical-axis contracts shared by SSnet training and prediction."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv-vib2mol' / 'Scripts' / 'python.exe'
if not PYTHON.exists():
    PYTHON = ROOT / '.venv-vib2mol' / 'bin' / 'python'
ACTIVE = ('queued', 'running')


def runtime_ready():
    if not PYTHON.is_file():
        return False
    environment = PYTHON.parent.parent
    sites = [environment / 'Lib' / 'site-packages'] + list((environment / 'lib').glob('python*/site-packages'))
    return any(all((site / module / '__init__.py').is_file() for module in ('numpy','torch','sklearn','joblib')) for site in sites)


def arrays(spectrum):
    x, y = (np.asarray(spectrum.get(key, []), dtype=float) for key in ('wavenumber', 'intensity'))
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or not 8 <= len(x) <= 20000:
        raise ValueError('需要 8–20000 个一维波数—强度数据点。')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('光谱包含无效数值。')
    if np.all(np.diff(x) < 0):
        x, y = x[::-1], y[::-1]
    if not np.all(np.diff(x) > 0):
        raise ValueError('波数必须严格单调且不能重复。')
    if np.ptp(y) <= 0:
        raise ValueError('常数光谱不能用于 SSnet。')
    return x, y


def align(spectrum, grid):
    x, y = arrays(spectrum)
    if x[0] > grid['start'] or x[-1] < grid['end']:
        raise ValueError(f"光谱仅覆盖 {x[0]:g}–{x[-1]:g} cm⁻¹，需覆盖所选模型的 {grid['start']:g}–{grid['end']:g} cm⁻¹；不会外推或补零。")
    axis = np.linspace(grid['start'], grid['end'], grid['points'])
    values = np.interp(axis, x, y)
    offset = float(values.min())
    values -= offset
    scale = float(values.max())
    if scale <= 0:
        raise ValueError('所选波段没有有效强度变化。')
    return dict(wavenumber=axis.tolist(), intensity=(values / scale).tolist(), offset=offset, scale=scale)


def prepare_standards(sources, settings):
    spans = [arrays(item['spectrum'])[0] for item in sources]
    start = max(float(x[0]) for x in spans) if settings.get('start') is None else settings['start']
    end = min(float(x[-1]) for x in spans) if settings.get('end') is None else settings['end']
    if not np.isfinite([start, end]).all() or start >= end:
        raise ValueError('标准品没有共同波段，或起止波数无效。')
    grid = dict(start=float(start), end=float(end), points=settings['points'])
    prepared = [align(item['spectrum'], grid) for item in sources]
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return dict(grid=grid, spectra=[p['intensity'] for p in prepared], input_sha256=digest,
                normalization='subtract_min_then_positive_max', interpolation='linear_no_extrapolation')
