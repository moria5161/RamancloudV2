import numpy as np

from .baseline_cor.aabs import correct_baseline as aabs_correct_baseline
from .baseline_cor.airpls import airpls
from .baseline_cor.imodpoly import imodpoly
from .baseline_cor.snip import snip
from .denoising.peer import denoise as peer_denoise
from .denoising.sg import sg
from .denoising.tsvd import tsvd
from .denoising.wtd import wtd


# Defaults match the V1 parameterized API where that API has an equivalent.
PARAMETERS = {
    'sg': {'window_size': (7, int, 3, 10001), 'order': (3, int, 0, 20)},
    'wtd': {'wavelet': ('db3', str, None, None), 'level': (3, int, 1, 20)},
    'peer': {'loops': (3, int, 1, 20), 'half_k_threshold': (2, int, 0, 7)},
    'f2p': {},
    'tsvd': {'threshold': (0.001, float, 0, 100)},
    'airnet': {},
    'airpls': {'lam': (1e7, float, 1e-12, 1e12), 'diff_order': (3, int, 1, 3)},
    'aabs': {'Ln': (6, int, 2, 100), 'Lb': (140, int, 5, 1000)},
    'imodpoly': {'poly_order': (3, int, 0, 10)},
    'snip': {'max_half_window': (20, int, 1, 1000), 'smooth_half_window': (7, int, 0, 1000)},
    'skip': {},
}
DENOISE_METHODS = ('sg', 'wtd', 'peer', 'tsvd', 'f2p', 'skip')
BASELINE_METHODS = ('airnet', 'airpls', 'aabs', 'imodpoly', 'snip', 'skip')


def validated_parameters(method, params):
    if method not in PARAMETERS:
        raise ValueError('Unknown algorithm: ' + str(method))
    supplied = dict(params or {})
    for alias, key in {'lambda_': 'lam', 'order_': 'diff_order'}.items():
        if alias in supplied:
            if key in supplied:
                raise ValueError('Specify only one of ' + key + ' and ' + alias)
            supplied[key] = supplied.pop(alias)
    unknown = set(supplied) - set(PARAMETERS[method])
    if unknown:
        raise ValueError(method + ': unsupported parameters: ' + ', '.join(sorted(unknown)))
    result = {}
    for key, (default, kind, minimum, maximum) in PARAMETERS[method].items():
        value = supplied.get(key, default)
        if kind is str:
            if not isinstance(value, str) or value not in ['db' + str(i) for i in range(1, 10)]:
                raise ValueError('wavelet must be db1 through db9')
        else:
            if isinstance(value, bool):
                raise ValueError(key + ' must be numeric')
            try:
                numeric = float(value)
            except (ValueError, TypeError):
                raise ValueError(key + ' must be numeric')
            if not np.isfinite(numeric) or not minimum <= numeric <= maximum:
                raise ValueError('{} must be between {} and {}'.format(key, minimum, maximum))
            if kind is int and numeric != int(numeric):
                raise ValueError(key + ' must be an integer')
            value = kind(numeric)
        result[key] = value
    return result


def denoise(y, params, method):
    method = 'sg' if method == 'savitzky_golay' else method or 'skip'
    if method not in DENOISE_METHODS:
        raise ValueError('Unknown denoise method: ' + method)
    p = validated_parameters(method, params)
    if method == 'skip':
        return y.copy()
    if method == 'sg':
        return sg(y, **p)
    if method == 'wtd':
        return wtd(y, **p)
    if method == 'peer':
        return peer_denoise(y, **p)
    return denoise_batch(y.reshape(1, -1), p, method)[0]


def denoise_batch(matrix, params, method):
    if method == 'f2p':
        validated_parameters(method, params)
        try:
            from .denoising.f2p import denoise_batch as f2p_denoise_batch
        except ImportError as exc:
            raise ValueError('F2P requires the optional PyTorch dependency; install torch>=2.5,<3.') from exc
        return f2p_denoise_batch(matrix)
    if method == 'tsvd':
        p = validated_parameters(method, params)
        return tsvd(matrix, **p)
    return np.vstack([denoise(row, params, method) for row in matrix])


def correct_baseline(y, params, method):
    method = method or 'skip'
    if method not in BASELINE_METHODS:
        raise ValueError('Unknown baseline method: ' + method)
    p = validated_parameters(method, params)
    if method == 'skip':
        return y.copy(), None
    if len(y) < 4 or p.get('poly_order', 0) >= len(y) or p.get('diff_order', 1) >= len(y):
        raise ValueError('Too few spectral points for the baseline parameters')
    if method == 'airnet':
        corrected, baseline = correct_baseline_batch(y.reshape(1, -1), p, method)
        return corrected[0], baseline[0]
    if method == 'aabs':
        return aabs_correct_baseline(y, **p)
    if method == 'airpls':
        return airpls(y, **p)
    if method == 'imodpoly':
        return imodpoly(y, **p)
    return snip(y, **p)


def correct_baseline_batch(matrix, params, method):
    if method == 'airnet':
        validated_parameters(method, params)
        try:
            from .baseline_cor.airnet import airnet_process
        except ImportError as exc:
            raise ValueError('AirNet requires the optional PyTorch dependency; install ramancloud[airnet].') from exc
        corrected = airnet_process(matrix)
        return corrected, matrix - corrected
    rows = [correct_baseline(row, params, method) for row in matrix]
    return np.vstack([row[0] for row in rows]), (None if rows[0][1] is None else np.vstack([row[1] for row in rows]))
