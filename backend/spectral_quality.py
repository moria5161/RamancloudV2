"""Bounded, non-mutating screening of already validated Raman arrays, not certification."""
import numpy as np
from scipy.signal import find_peaks

MAX_SPECTRA = 16
MAX_LOCATIONS = 32
RULES = dict(spacing_cv=0.01, spike_width_points=2.5, spike_noise_multiplier=8,
             spike_span_fraction=0.05, plateau_min_points=3, plateau_span_tolerance=0.0001)


def quality_report(wave, data):
    x, values = np.asarray(wave, dtype=float), np.asarray(data, dtype=float)
    if (x.ndim != 1 or len(x) < 3 or values.ndim not in (1, 2, 3)
            or values.shape[-1] != len(x) or not values.size
            or not np.isfinite(x).all() or not np.isfinite(values).all()):
        raise ValueError('质量检查需要已通过格式校验的有限数值光谱。')
    if not ((x[1:] > x[:-1]).all() or (x[1:] < x[:-1]).all()):
        raise ValueError('质量检查需要严格单调的波数轴。')
    scaled_x = x / max(float(np.max(np.abs(x))), np.finfo(float).tiny)
    diff = np.diff(scaled_x)
    spacing = np.abs(diff)
    cv = float(np.std(spacing) / np.mean(spacing))
    total = int(np.prod(values.shape[:-1])) if values.ndim > 1 else 1
    sample = np.unique(np.linspace(0, total - 1, min(MAX_SPECTRA, total), dtype=int))
    issues = {}

    def spectrum(row):
        if values.ndim == 1:
            return values
        return values[row] if values.ndim == 2 else values[row // values.shape[1], row % values.shape[1]]

    def add(code, location=None):
        item = issues.setdefault(code, dict(code=code, severity='warning', count=0, locations=[]))
        item['count'] += 1
        if location is not None and len(item['locations']) < MAX_LOCATIONS:
            item['locations'].append(location)

    def location(row, index, **extra):
        item = dict(index=int(index), wavenumber=float(x[index]), intensity=float(spectrum(row)[index]),
                    spectrum_index=int(row), **extra)
        if values.ndim == 3:
            item.update(row=int(row // values.shape[1]), column=int(row % values.shape[1]))
        return item

    if cv > RULES['spacing_cv']:
        median = max(float(np.median(spacing)), np.finfo(float).tiny)
        abnormal = np.flatnonzero(np.abs(spacing / median - 1) > 0.01)
        if not len(abnormal):
            abnormal = np.array([int(np.argmax(np.abs(spacing / median - 1)))])
        for i in abnormal:
            add('uneven_spacing', dict(index=int(i), wavenumber=float(x[i]), end_wavenumber=float(x[i + 1])))

    for row_index in sample:
        y = spectrum(row_index)
        scale = float(np.max(np.abs(y)))
        normalized = y / scale if scale else y.copy()
        span = float(np.ptp(normalized))
        if span <= 1e-12:
            add('constant_signal', location(row_index, 0))
            continue
        second = np.diff(normalized, n=2)
        noise = float(np.median(np.abs(second - np.median(second))) / (0.6745 * np.sqrt(6)))
        prominence = max(RULES['spike_noise_multiplier'] * noise, RULES['spike_span_fraction'] * span, 1e-12)
        for sign in (1, -1):
            peaks, properties = find_peaks(sign * normalized, prominence=prominence,
                                           width=(None, RULES['spike_width_points']), plateau_size=(None, 2))
            for i, width in zip(peaks, properties['widths']):
                add('narrow_spike', location(row_index, i, width_points=round(float(width), 4)))
        # A flat segment near the maximum is a candidate only: ADC limits are unknown.
        top = normalized >= normalized.max() - span * RULES['plateau_span_tolerance']
        edges = np.diff(np.r_[False, top, False].astype(int))
        for start, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            if stop - start >= RULES['plateau_min_points']:
                add('flat_top', location(row_index, (start + stop - 1) // 2,
                                        start_index=int(start), end_index=int(stop - 1),
                                        start_wavenumber=float(x[start]), end_wavenumber=float(x[stop - 1])))
    for item in issues.values():
        item['truncated'] = item['count'] > len(item['locations'])
    return dict(version=1, status='review' if issues else 'no_obvious_issue', advisory=True, blocking=False,
                points=len(x), spectra_total=total, spectra_checked=len(sample),
                sampled=len(sample) < total, sampled_indices=sample.tolist(),
                axis_checked='full', spacing_cv=round(cv, 6), rules=dict(RULES), issues=list(issues.values()))
