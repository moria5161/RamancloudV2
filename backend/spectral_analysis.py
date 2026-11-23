"""Deterministic Raman spectrum summaries for the AI assistant."""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.signal import find_peaks, peak_widths, savgol_filter


def _safe_float(value: Any, digits: int = 6) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return round(number, digits)


def _clean_pair(wavenumber: Any, intensity: Any) -> Tuple[np.ndarray, np.ndarray]:
    wave = np.asarray(wavenumber, dtype=float).reshape(-1)
    values = np.asarray(intensity, dtype=float).reshape(-1)
    length = min(wave.size, values.size)
    wave = wave[:length]
    values = values[:length]
    mask = np.isfinite(wave) & np.isfinite(values)
    wave = wave[mask]
    values = values[mask]
    if wave.size < 3:
        raise ValueError("At least three finite spectrum points are required.")
    order = np.argsort(wave)
    return wave[order], values[order]


def _noise_proxy(values: np.ndarray) -> float:
    if values.size < 7:
        return float(np.std(np.diff(values)) / np.sqrt(2.0))
    window = min(31, values.size if values.size % 2 else values.size - 1)
    window = max(5, window)
    if window >= values.size:
        window = values.size - 1 if values.size % 2 == 0 else values.size
    if window <= 3:
        return float(np.std(np.diff(values)) / np.sqrt(2.0))
    smooth = savgol_filter(values, window, min(3, window - 1))
    return float(np.std(values - smooth))


def _detect_peaks(wave: np.ndarray, values: np.ndarray, limit: int = 12) -> Tuple[int, List[Dict[str, Any]]]:
    span = float(np.ptp(values))
    scale = float(np.std(values))
    prominence = max(span * 0.02, scale * 1.5, 1e-12)
    distance = max(1, values.size // 200)
    indices, properties = find_peaks(values, prominence=prominence, distance=distance)
    if indices.size == 0 and span > 0:
        indices, properties = find_peaks(values, prominence=max(span * 0.005, 1e-12), distance=distance)
    if indices.size == 0:
        return 0, []

    widths = peak_widths(values, indices, rel_height=0.5)[0]
    spacing = float(np.median(np.diff(wave))) if wave.size > 1 else 1.0
    prominence_values = properties.get("prominences", np.zeros(indices.size))
    ranking = np.argsort(prominence_values)[::-1][:limit]
    peaks: List[Dict[str, Any]] = []
    for rank_index in ranking:
        index = int(indices[rank_index])
        peaks.append(
            {
                "position": _safe_float(wave[index], 3),
                "height": _safe_float(values[index], 5),
                "prominence": _safe_float(prominence_values[rank_index], 5),
                "width_points": _safe_float(widths[rank_index], 3),
                "width_cm1": _safe_float(widths[rank_index] * abs(spacing), 3),
            }
        )
    return int(indices.size), peaks


def analyze_spectrum(wavenumber: Any, intensity: Any, label: str = "spectrum") -> Dict[str, Any]:
    """Return compact, model-friendly metrics without returning raw arrays."""
    wave, values = _clean_pair(wavenumber, intensity)
    noise = _noise_proxy(values)
    peak_count, peaks = _detect_peaks(wave, values)
    return {
        "label": label,
        "point_count": int(values.size),
        "wavenumber_range": [_safe_float(wave[0], 3), _safe_float(wave[-1], 3)],
        "intensity_range": [_safe_float(values.min(), 5), _safe_float(values.max(), 5)],
        "intensity_mean": _safe_float(values.mean(), 5),
        "intensity_std": _safe_float(values.std(), 5),
        "noise_proxy_std": _safe_float(noise, 5),
        "signal_to_noise_proxy": _safe_float(values.std() / max(noise, 1e-12), 4),
        "peak_count": peak_count,
        "top_peaks": peaks,
    }


def compare_spectra(
    raw_wavenumber: Any,
    raw_intensity: Any,
    processed_wavenumber: Any,
    processed_intensity: Any,
) -> Dict[str, Any]:
    """Compare raw and processed spectra using deterministic metrics."""
    raw = analyze_spectrum(raw_wavenumber, raw_intensity, "raw")
    processed = analyze_spectrum(processed_wavenumber, processed_intensity, "processed")
    raw_noise = raw["noise_proxy_std"] or 0.0
    processed_noise = processed["noise_proxy_std"] or 0.0
    raw_snr = raw["signal_to_noise_proxy"] or 0.0
    processed_snr = processed["signal_to_noise_proxy"] or 0.0

    matched_peaks: List[Dict[str, Any]] = []
    processed_peaks = processed["top_peaks"]
    for raw_peak in raw["top_peaks"]:
        if not processed_peaks:
            continue
        low, high = sorted(processed["wavenumber_range"])
        if not low <= raw_peak["position"] <= high:
            continue
        nearest = min(processed_peaks, key=lambda peak: abs(peak["position"] - raw_peak["position"]))
        shift = nearest["position"] - raw_peak["position"]
        if abs(shift) > max(raw_peak["width_cm1"] or 0, nearest["width_cm1"] or 0, 1):
            continue
        matched_peaks.append(
            {
                "raw_position": raw_peak["position"],
                "processed_position": nearest["position"],
                "position_shift_cm1": _safe_float(shift, 3),
                "height_change_percent": _safe_float(
                    100.0 * (nearest["height"] - raw_peak["height"]) / max(abs(raw_peak["height"]), 1e-12),
                    3,
                ),
            }
        )

    return {
        "raw": raw,
        "processed": processed,
        "noise_change_percent": _safe_float(100.0 * (processed_noise - raw_noise) / max(raw_noise, 1e-12), 3),
        "snr_change_percent": _safe_float(100.0 * (processed_snr - raw_snr) / max(abs(raw_snr), 1e-12), 3),
        "matched_peak_changes": matched_peaks[:12],
    }


def summarize_matrix(
    data: Any,
    label: str = "matrix",
    max_samples: int = 20000,
) -> Dict[str, Any]:
    """Return compact statistics for an imaging or time-series matrix.

    The assistant should not receive a full heatmap when a few deterministic
    statistics are enough to explain its change. Sampling keeps this helper
    bounded for large time-series uploads.
    """

    try:
        array = np.asarray(data, dtype=float)
    except (TypeError, ValueError):
        return {"label": label, "available": False, "reason": "not numeric"}

    if array.size == 0:
        return {"label": label, "available": False, "reason": "empty"}

    finite = np.isfinite(array)
    values = array[finite].reshape(-1)
    if values.size == 0:
        return {"label": label, "available": False, "reason": "no finite values"}

    sample_limit = max(1, int(max_samples))
    stride = max(1, int(np.ceil(values.size / sample_limit)))
    sampled = values[::stride]
    return {
        "label": label,
        "available": True,
        "shape": list(array.shape),
        "value_count": int(values.size),
        "sampled_count": int(sampled.size),
        "sample_stride": int(stride),
        "min": _safe_float(float(sampled.min()), 5),
        "max": _safe_float(float(sampled.max()), 5),
        "mean": _safe_float(float(sampled.mean()), 5),
        "std": _safe_float(float(sampled.std()), 5),
    }


def compare_matrices(
    raw_data: Any,
    processed_data: Any,
    max_samples: int = 20000,
) -> Dict[str, Any]:
    """Compare heatmap/time-series values without returning the matrices."""

    raw_summary = summarize_matrix(raw_data, "raw_preview", max_samples)
    processed_summary = summarize_matrix(processed_data, "processed_preview", max_samples)
    result: Dict[str, Any] = {
        "raw": raw_summary,
        "processed": processed_summary,
        "shape_match": False,
    }
    if not raw_summary.get("available") or not processed_summary.get("available"):
        return result

    try:
        raw = np.asarray(raw_data, dtype=float)
        processed = np.asarray(processed_data, dtype=float)
        result["shape_match"] = list(raw.shape) == list(processed.shape)
        if not result["shape_match"]:
            return result

        raw_values = raw.reshape(-1)
        processed_values = processed.reshape(-1)
        finite = np.isfinite(raw_values) & np.isfinite(processed_values)
        raw_values = raw_values[finite]
        processed_values = processed_values[finite]
        if raw_values.size == 0:
            return result

        stride = max(1, int(np.ceil(raw_values.size / max(1, int(max_samples)))))
        raw_sample = raw_values[::stride]
        processed_sample = processed_values[::stride]
        difference = processed_sample - raw_sample
        scale = max(float(np.ptp(raw_sample)), 1e-12)
        threshold = max(scale * 0.01, 1e-12)
        result.update(
            {
                "sampled_count": int(raw_sample.size),
                "mean_absolute_change": _safe_float(float(np.mean(np.abs(difference))), 5),
                "rmse": _safe_float(float(np.sqrt(np.mean(difference ** 2))), 5),
                "max_absolute_change": _safe_float(float(np.max(np.abs(difference))), 5),
                "changed_fraction_percent": _safe_float(
                    100.0 * float(np.mean(np.abs(difference) > threshold)),
                    3,
                ),
                "change_threshold": _safe_float(threshold, 5),
            }
        )
    except (TypeError, ValueError):
        return result
    return result
