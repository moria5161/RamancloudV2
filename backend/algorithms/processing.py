import numpy as np
import pywt
from pybaselines import Baseline
from scipy.signal import savgol_filter

from .v1_aabs import aabs
from .v1_airpls import ZhangFit
from .v1_peer import peer_process


# Defaults match the V1 parameterized API where that API has an equivalent.
PARAMETERS = {
    'sg': {'window_size': (7, int, 3, 10001), 'order': (3, int, 0, 20)},
    'wtd': {'wavelet': ('db3', str, None, None), 'level': (3, int, 1, 20)},
    'peer': {'loops': (3, int, 1, 20), 'half_k_threshold': (2, int, 0, 7)},
    'tsvd': {'threshold': (0.001, float, 0, 100)},
    'airpls': {'lam': (1e7, float, 1e-12, 1e12), 'diff_order': (3, int, 1, 3)},
    'aspls': {'lam': (1e7, float, 1e-12, 1e12), 'diff_order': (3, int, 1, 3)},
    'aabs': {'Ln': (6, int, 2, 100), 'Lb': (140, int, 5, 1000)},
    'imodpoly': {'poly_order': (3, int, 0, 10)},
    'penalizedpoly': {'poly_order': (3, int, 0, 10)},
    'airpls_old': {'lam': (100, float, 1e-12, 1e12), 'diff_order': (1, int, 1, 3)},
    'rollingball': {'half_window': (40, int, 1, 1000)},
    'mormol': {'half_window': (40, int, 1, 1000)},
    'irsqr': {'lam': (50, float, 1e-12, 1e12), 'quantile': (0.05, float, 0.001, 0.999)},
    'snip': {'max_half_window': (20, int, 1, 1000), 'smooth_half_window': (7, int, 0, 1000)},
    'skip': {},
}
DENOISE_METHODS = ('sg', 'wtd', 'peer', 'tsvd', 'skip')
BASELINE_METHODS = ('airpls', 'aspls', 'aabs', 'imodpoly', 'penalizedpoly', 'airpls_old', 'rollingball', 'mormol', 'irsqr', 'snip', 'skip')


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
        if p['window_size'] % 2 != 1 or p['window_size'] > len(y) or p['order'] >= p['window_size']:
            raise ValueError('SG window must be odd, no longer than the spectrum, and greater than polynomial order')
        return savgol_filter(y, p['window_size'], p['order'])
    if method == 'wtd':
        maximum = pywt.dwt_max_level(len(y), pywt.Wavelet(p['wavelet']).dec_len)
        if p['level'] > maximum:
            raise ValueError('WTD level exceeds the maximum {} for this spectrum and wavelet'.format(maximum))
        coeffs = pywt.wavedec(y, p['wavelet'], level=p['level'])
        threshold = 0.8 * np.sqrt(2 * np.log(len(y))) * np.median(np.abs(coeffs[-1])) / 0.6745
        coeffs = [c if i == 0 else pywt.threshold(c, threshold, mode='soft') for i, c in enumerate(coeffs)]
        return pywt.waverec(coeffs, p['wavelet'])[:len(y)]
    if method == 'peer':
        if len(y) < 7:
            raise ValueError('PEER requires at least 7 spectral points')
        return peer_process(y, np.arange(len(y)), **p)[0].astype(float)
    return denoise_batch(y.reshape(1, -1), p, method)[0]


def denoise_batch(matrix, params, method):
    if method == 'tsvd':
        p = validated_parameters(method, params)
        u, s, vh = np.linalg.svd(matrix, full_matrices=False)
        mask = np.ones(len(s), dtype=bool)
        # Match V1's second derivative of log1p singular values, not a relative-rank cutoff.
        mask[1:-1] = np.abs(np.diff(np.log1p(s), n=2)) > p['threshold']
        return (u * np.where(mask, s, 0)) @ vh
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
    if method == 'aabs':
        if len(y) < max(100, p['Ln'], p['Lb']):
            raise ValueError('AABS requires at least max(100, Ln, Lb) spectral points')
        corrected = aabs(np.arange(len(y)), y.copy(), **p)
        return corrected, y - corrected
    if method == 'airpls_old':
        # V1 ignored its difference-order parameter; V2 fixes that while retaining its weights.
        corrected = ZhangFit(y, lambda_=p['lam'], porder=p['diff_order'])
        return corrected, y - corrected
    fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    names = {'penalizedpoly': 'penalized_poly', 'rollingball': 'rolling_ball'}
    if method == 'snip':
        if p['max_half_window'] > (len(y) - 1) // 2:
            raise ValueError('SNIP maximum half window exceeds half the spectral length')
        p['decreasing'] = True
    baseline, _ = getattr(fitter, names.get(method, method))(y, **p)
    return y - baseline, baseline
