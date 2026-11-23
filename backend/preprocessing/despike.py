"""Conservative array despiking, retaining the source algorithm's FWHM measurement."""
import numpy as np
from scipy.signal import find_peaks

from .despike_core import calculate_fwhm


DEFAULT_PARAMS = dict(threshold=None, fwhm_threshold=4.0)
MAX_REPORTED_SPIKES = 256
REPAIR_POLICY = 'isolated_sample_v1'


def validate_params(params):
    if not isinstance(params, dict) or set(params) - set(DEFAULT_PARAMS):
        raise ValueError('去鬼峰参数不受支持。')
    values = dict(DEFAULT_PARAMS, **params)
    for name, minimum, maximum in [('threshold', 0., 1e12), ('fwhm_threshold', .1, 50.)]:
        value = values[name]
        if name == 'threshold' and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError('去鬼峰检测阈值或半高宽阈值无效。')
        values[name] = float(value)
    return values


def validate_order(steps):
    """Prevent smoothing from broadening the spikes before detection."""
    seen_denoise, count = False, 0
    for step in steps:
        get = step.get if isinstance(step, dict) else lambda key, default=None: getattr(step, key, default)
        if get('type') == 'despike':
            count += 1
            if count > 1:
                raise ValueError('每个处理方案只能包含一个去鬼峰步骤。')
        if not get('enabled', True) or get('method') == 'skip':
            continue
        if get('type') == 'despike' and seen_denoise:
            raise ValueError('去鬼峰应在降噪之前，请调整处理步骤顺序。')
        if get('type') == 'denoise':
            seen_denoise = True


def despike_matrix(wave, data, params):
    values = validate_params(params)
    axis, matrix = np.asarray(wave, dtype=float), np.asarray(data, dtype=float)
    if axis.ndim != 1 or matrix.ndim != 2 or matrix.shape[1] != len(axis) or len(axis) < 8 or not len(matrix):
        raise ValueError('去鬼峰需要至少 8 个数据点，且波数与强度长度一致。')
    if not np.isfinite(axis).all() or not np.isfinite(matrix).all():
        raise ValueError('去鬼峰输入含 NaN 或 Inf。')
    if not ((np.diff(axis) > 0).all() or (np.diff(axis) < 0).all()):
        raise ValueError('去鬼峰需要严格单调的波数轴。')
    corrected = matrix.copy()
    count, changed, repaired, spikes = 0, 0, 0, []
    for row_index, row in enumerate(matrix):
        # Estimate noise independently of the heights of the spectral peaks.
        # A median over peak heights can reject all candidates when a spectrum
        # contains only a few strong peaks.
        second = np.diff(row, n=2)
        noise = np.median(np.abs(second - np.median(second))) / (.67448975 * np.sqrt(6))
        threshold = values['threshold']
        if threshold is None:
            threshold = max(8 * noise, np.max(np.abs(row)) * 1e-12, 1e-12)
        candidates = []
        for sign, ptype in ((1, 'max'), (-1, 'min')):
            indices, _ = find_peaks(sign * row, prominence=threshold)
            for index in indices:
                fwhm, left, right = calculate_fwhm(row, int(index), ptype)
                if fwhm <= values['fwhm_threshold']:
                    candidates.append(dict(peak_idx=int(index), ptype=ptype, fwhm=fwhm,
                        left_idx=left, right_idx=right, detection_threshold=float(threshold)))
        candidates.sort(key=lambda spike: spike['peak_idx'])
        decisions, mask = [], np.zeros(len(row), dtype=bool)
        for spike in candidates:
            index = int(spike['peak_idx'])
            signed = row if spike.get('ptype', 'max') == 'max' else -row
            baseline = np.min(signed[max(0, index - 10):min(len(row), index + 11)])
            height = signed[index] - baseline
            support = max(signed[index - 1] - baseline, signed[index + 1] - baseline) / height if height > 0 else 1.
            # Width alone also flags genuine resolved Raman peaks. Automatically
            # repair only isolated one-sample impulses, never their shoulders.
            repair = bool(spike['fwhm'] <= 1.5 and support <= .2)
            decisions.append((spike, repair))
            if repair:
                mask[index] = True
        output = row.copy()
        if mask.any():
            xp, yp = axis[~mask], row[~mask]
            if axis[0] > axis[-1]:
                xp, yp = xp[::-1], yp[::-1]
            output[mask] = np.interp(axis[mask], xp, yp)
        corrected[row_index] = output
        changed += int(np.count_nonzero(output != row))
        count += len(candidates)
        repaired += sum(repair for _, repair in decisions)
        for spike, repair in decisions[:max(0, MAX_REPORTED_SPIKES - len(spikes))]:
            index = int(spike['peak_idx'])
            spikes.append(dict(spectrum_index=row_index, peak_idx=index, wavenumber=float(axis[index]),
                               intensity=float(row[index]), corrected_intensity=float(output[index]),
                               fwhm=float(spike['fwhm']), ptype=spike.get('ptype', 'max'),
                               left_idx=index if repair else int(spike['left_idx']),
                               right_idx=index if repair else int(spike['right_idx']), repaired=repair))
    details = dict(algorithm='despike', num_cosmic_rays=count, corrected_points=changed, spectra_count=len(matrix),
                   cosmic_rays=spikes, reported_spikes=len(spikes), details_truncated=count > len(spikes),
                   repaired_spikes=repaired, protected_candidates=count - repaired,
                   repair_policy=REPAIR_POLICY, interpolation='linear_wavenumber', **values)
    return corrected, details
