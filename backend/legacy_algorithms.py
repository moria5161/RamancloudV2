"""Canonical preprocessing adapters backed by the original algorithm implementations."""
import json
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'legacy_algorithm_catalog.json').read_text(encoding='utf-8'))
METHODS = {s['method']: s for s in CATALOG}
_SLOT = threading.BoundedSemaphore(1)
TSVD_MAX_WORK = int(os.getenv('RAMANCLOUD_TSVD_MAX_WORK', '20000000000'))


class TSVDWorkLimitError(ValueError):
    pass


def python_path():
    configured = os.environ.get('RAMANCLOUD_LEGACY_PYTHON')
    if configured:
        return Path(configured)
    env = ROOT / '.venv-vib2mol'
    return env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def availability(spec):
    if spec['method'] in ('sg','wtd'):return True,''
    if not python_path().is_file():
        return False, '请先运行 scripts/setup_legacy_algorithms.py 准备独立环境'
    env = python_path().parent.parent if python_path().parent.name.lower() in ('scripts','bin') else python_path().parent
    sites = [env/'Lib/site-packages'] + list((env/'lib').glob('python*/site-packages'))
    for package in ('numpy', 'scipy', 'pywt', 'pybaselines'):
        if not any((site/package).is_dir() for site in sites):
            return False, '独立环境缺少 '+package+'，请运行 scripts/setup_legacy_algorithms.py'
    original = spec.get('original_method',spec['method'])
    weight = {'f2p': 'RAMANCLOUD_F2P_MODEL', 'airnet': 'RAMANCLOUD_AIRNET_MODEL'}.get(original)
    if weight and not model_path(original).is_file():
        return False, '需配置原版兼容模型权重：' + weight
    if weight and not any((site/'torch').is_dir() for site in sites):
        return False, '原版模型需要在独立环境安装 PyTorch 2.5 或更新兼容版本'
    return True, ''


def catalog():
    return [dict(s, available=availability(s)[0], unavailable_reason=availability(s)[1]) for s in CATALOG]


def process(matrix, params, method):
    method = method.removeprefix('v2_') if hasattr(method,'removeprefix') else method[3:] if method.startswith('v2_') else method
    spec = METHODS.get(method)
    if spec is None:
        raise ValueError('不支持的算法')
    ready, reason = availability(spec)
    if not ready:
        raise ValueError(reason)
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or not values.size:
        raise ValueError('算法需要有限的二维光谱矩阵')
    if method == 'tsvd':
        rows, bands = values.shape
        if rows * bands * min(rows, bands) > TSVD_MAX_WORK:
            raise TSVDWorkLimitError('TSVD 超出在线计算上限。请将裁剪步骤放在 TSVD 前并缩小波段，或使用较小的数据集。')
    if not np.isfinite(values).all():
        raise ValueError('算法需要有限的二维光谱矩阵')
    allowed = spec['params']
    if set(params) - set(allowed):
        raise ValueError('算法包含不支持的参数')
    normalized = {}
    for key, rule in allowed.items():
        value = params.get(key, rule['default'])
        if 'options' in rule:
            if value not in rule['options']:raise ValueError('不支持的算法选项：'+key)
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not rule['min'] <= value <= rule['max'] or rule.get('integer') and value != int(value):
            raise ValueError('算法参数超出范围：' + key)
        normalized[key] = value if 'options' in rule else int(value) if rule.get('integer') else float(value)
    if method == 'snip' and normalized['max_half_window'] > (values.shape[1]-1)//2:
        raise ValueError('SNIP半窗口不能超过当前光谱长度的一半')
    if method == 'aabs' and values.shape[1] < max(100, normalized['Ln'], normalized['Lb']):
        raise ValueError('AABS数据点数不足，请减小窗口或使用更完整波段')
    if method == 'imodpoly' and normalized['poly_order'] >= values.shape[1]:
        raise ValueError('多项式阶数必须小于数据长度')
    if method in ('sg','wtd'):
        if method=='sg':
            from vendor.legacy_v2.denoising.sg import sg as function
        else:
            from vendor.legacy_v2.denoising.wtd import wtd as function
        return np.vstack([function(row,**normalized) for row in values]),None
    with _SLOT, tempfile.TemporaryDirectory(prefix='raman-v2-') as directory:
        directory = Path(directory)
        np.save(directory/'input.npy', values, allow_pickle=False)
        (directory/'request.json').write_text(json.dumps(dict(method=spec['original_method'], kind=spec['type'], params=normalized)), encoding='utf-8')
        try:
            result = subprocess.run([str(python_path()), str(ROOT/'backend/legacy_algorithm_worker.py'), str(directory)], capture_output=True, timeout=600,
                env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',RAMANCLOUD_F2P_MODEL=str(model_path('f2p')),RAMANCLOUD_AIRNET_MODEL=str(model_path('airnet'))))
        except subprocess.TimeoutExpired:
            raise ValueError('算法运行超时，请减少输入规模')
        if result.returncode:
            logging.getLogger(__name__).warning('Legacy worker failed (%s): %s',method,result.stderr.decode('utf-8','replace')[-2000:])
            if method=='airpls' and b'not positive definite' in result.stderr:
                raise ValueError('AirPLS数值求解失败，请减小平滑系数或差分阶数后重试；未生成替代结果')
            raise ValueError('算法运行失败，请检查独立环境、参数及原版权重；未生成替代结果')
        with np.load(directory/'output.npz', allow_pickle=False) as data:
            output = data['corrected'].copy()
            baseline = data['baseline'].copy() if 'baseline' in data else None
        if output.shape != values.shape or not np.isfinite(output).all() or baseline is not None and (baseline.shape != values.shape or not np.isfinite(baseline).all()):
            raise ValueError('算法输出无效，未保存结果')
        return output, baseline


def model_path(method):
    variable={'f2p':'RAMANCLOUD_F2P_MODEL','airnet':'RAMANCLOUD_AIRNET_MODEL'}[method]
    if os.environ.get(variable):return Path(os.environ[variable])
    return ROOT/'.runtime/preprocessing-models/f2p/best_checkpoint.pth' if method=='f2p' else ROOT/'backend/baseline_cor/model_pt/0925RU_statedict.pth'
