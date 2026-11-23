"""Bounded multi-peak fitting, adapted from xbb's 4-Voigt_Fitting_改进.py.

Keep the original area-normalized Voigt and width/eta parameterization. Report
the measured composite FWHM separately; the original width is NOT that FWHM.
No input interpolation, baseline subtraction or peak-count inference is done.
"""
import time
import warnings
import numpy as np
from scipy.optimize import brentq, curve_fit, OptimizeWarning
from scipy.special import voigt_profile

IMPLEMENTATION = 'xbb-voigt-web-v1'


def voigt(x, center, area, width, eta):
    sigma = (1 - eta) * width / (2 * np.sqrt(2 * np.log(2)))
    gamma = eta * width / 2
    return area * voigt_profile(np.asarray(x) - center, sigma, gamma)


def prepare(spectrum, settings):
    x, y = (np.asarray(spectrum.get(k, []), dtype=float) for k in ('wavenumber', 'intensity'))
    if x.ndim != 1 or y.shape != x.shape or not 8 <= x.size <= 20000 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Use 8–20000 finite wavenumber–intensity pairs.')
    delta = np.diff(x)
    if not (np.all(delta > 0) or np.all(delta < 0)):
        raise ValueError('The wavenumber axis must be strictly monotonic.')
    start, end = settings['start'], settings['end']
    if not np.isfinite([start, end]).all() or start >= end or start < x.min() or end > x.max():
        raise ValueError('The fitting range must lie within the spectrum.')
    keep = (x >= start) & (x <= end)
    x, y = x[keep], y[keep]
    rows = settings['peaks']
    if not 1 <= len(rows) <= 12:
        raise ValueError('Choose between 1 and 12 peaks.')
    initial, lower, upper = [], [], []
    for row in rows:
        center, width, eta = row['center'], row['width'], row['eta']
        shape = row.get('shape', 'voigt')
        if shape not in ('voigt', 'gaussian', 'lorentzian'):
            raise ValueError('Unknown peak shape.')
        area = row.get('area')
        if area is None:
            area = max(float(np.max(y)), np.finfo(float).eps) * width * .5
        eta_lo, eta_hi = row['eta_min'], row['eta_max']
        if shape != 'voigt':
            eta = 0.0 if shape == 'gaussian' else 1.0
            eta_lo = eta_hi = eta
        vals = [center, area, width, eta]
        lo = [row['center_min'], row['area_min'], row['width_min'], eta_lo]
        hi = [row['center_max'], row['area_max'] if row['area_max'] is not None else np.inf, row['width_max'], eta_hi]
        if not np.isfinite(vals + lo + hi[:1] + hi[2:]).all() or not (np.isfinite(hi[1]) or hi[1] == np.inf):
            raise ValueError('Peak parameters must be finite.')
        if lo[0] < start or hi[0] > end or lo[1] < 0 or area <= 0 or lo[2] <= 0 or not 0 <= lo[3] <= hi[3] <= 1:
            raise ValueError('Keep centers within the fitting range, area positive, width above zero and eta in [0, 1].')
        if any(a > b or v < a or v > b for v, a, b in zip(vals, lo, hi)):
            raise ValueError('Initial values must lie inside their bounds; equal bounds fix a parameter.')
        initial.extend(vals); lower.extend(lo); upper.extend(hi)
    initial, lower, upper = map(lambda v: np.asarray(v, dtype=float), (initial, lower, upper))
    free = lower < upper
    if x.size <= max(4, int(free.sum())):
        raise ValueError('The fitting range needs more data points than free parameters.')
    if np.ptp(y) <= np.finfo(float).eps * max(1., float(np.max(np.abs(y)))):
        raise ValueError('A constant spectrum cannot support peak fitting.')
    return x, y, initial, lower, upper, free


def fit(spectrum, settings, timeout=45):
    x, y, initial, lower, upper, free = prepare(spectrum, settings)
    started = time.monotonic()
    def model(axis, *values):
        if time.monotonic() - started > timeout:
            raise ValueError('Fitting timed out. Narrow the range, reduce peaks or improve initial values.')
        full = initial.copy(); full[free] = values
        return sum((voigt(axis, *p) for p in full.reshape(-1, 4)), np.zeros_like(axis, dtype=float))
    notices = []
    errors = np.zeros_like(initial)
    if free.any():
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', OptimizeWarning)
            values, covariance = curve_fit(model, x, y, p0=initial[free], bounds=(lower[free], upper[free]),
                                           maxfev=10000, x_scale='jac')
        params = initial.copy(); params[free] = values
        errors[free] = np.sqrt(np.maximum(0, np.diag(covariance)))
        if caught or not np.isfinite(errors).all():
            notices.append(dict(code='uncertainty'))
        if covariance.shape[0] > 1 and np.isfinite(covariance).all():
            sd = np.sqrt(np.maximum(np.diag(covariance), 1e-300))
            correlation = covariance / np.outer(sd, sd)
            np.fill_diagonal(correlation, 0)
            if np.max(np.abs(correlation)) > .98:
                notices.append(dict(code='correlated'))
    else:
        params = initial.copy()
    components = [voigt(x, *p) for p in params.reshape(-1, 4)]
    total = np.sum(components, axis=0)
    residual = y - total
    if not np.isfinite(total).all() or not np.isfinite(residual).all():
        raise ValueError('Fitting produced invalid values. Review the peak settings.')
    ss_res, ss_tot = float(residual @ residual), float(np.sum((y - y.mean()) ** 2))
    peaks = []
    for i, (center, area, width, eta) in enumerate(params.reshape(-1, 4)):
        height = float(voigt(0., 0., area, width, eta))
        half = brentq(lambda offset: float(voigt(offset, 0., 1., width, eta) - voigt(0., 0., 1., width, eta) / 2), 0, width * 2)
        hit = [name for j, name in enumerate(('center', 'area', 'width', 'eta'))
               if free[i * 4 + j] and (np.isclose(params[i * 4 + j], lower[i * 4 + j], rtol=0, atol=1e-5 * max(1, abs(params[i * 4 + j])))
               or np.isclose(params[i * 4 + j], upper[i * 4 + j], rtol=0, atol=1e-5 * max(1, abs(params[i * 4 + j]))))]
        if hit:
            notices.append(dict(code='bound', peak=i + 1, parameters=hit))
        peaks.append(dict(index=i + 1, shape=settings['peaks'][i]['shape'], center=float(center), area=float(area),
                          height=height, width_parameter=float(width), fwhm=float(half * 2), eta=float(eta),
                          standard_errors={name: float(v) if np.isfinite(v) else None for name, v in zip(
                              ('center', 'area', 'width_parameter', 'eta'), errors[i * 4:i * 4 + 4])}))
    return dict(implementation=IMPLEMENTATION, wavenumber=x.tolist(), observed=y.tolist(), intensity=total.tolist(),
                residual=residual.tolist(), components=[v.tolist() for v in components], peaks=peaks,
                r_squared=1 - ss_res / ss_tot, rmse=float(np.sqrt(ss_res / len(x))), free_parameters=int(free.sum()),
                points=len(x), duration_seconds=round(time.monotonic() - started, 4), warnings=notices)
