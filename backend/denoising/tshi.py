"""TSHI / IIALRMA adapted from the two user-supplied research scripts.

The legacy smoothness formula and direct spectral soft threshold are retained.
BM3D is optional and produces a separate center image, never a spectral cube.
"""
import importlib
import threading
import time

import numpy as np
import pywt
from scipy.linalg import svd
from scipy.signal import savgol_filter

MAX_ELEMENTS = 8_000_000
MAX_BANDS = 256
_GATE = threading.BoundedSemaphore(1)


def bm3d_available():
    try:
        module = importlib.import_module('bm3d')
        return callable(module.bm3d)
    except (ImportError, OSError, AttributeError):
        return False


def _number(params, key, default, low, high, integer=False):
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError(f'TSHI 参数 {key} 必须是有限数值。')
    if not low <= value <= high or integer and value != int(value):
        raise ValueError(f'TSHI 参数 {key} 超出范围 [{low}, {high}]。')
    return int(value) if integer else float(value)


def _preview(image, scale):
    return image[::scale, ::scale].tolist()


def _window_means(image, size):
    integral = np.pad(image, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    return (integral[size:, size:] - integral[:-size, size:] - integral[size:, :-size] + integral[:-size, :-size]) / size ** 2


def denoise(wave, cube, params):
    wave, cube = np.asarray(wave, dtype=float), np.asarray(cube, dtype=float)
    allowed = {'center_wavenumber', 'half_width', 'windowsize', 'count', 'thr1', 'thr2', 'smoothness', 'bm3d_enabled', 'bm3d_sigma'}
    if set(params) - allowed:
        raise ValueError('TSHI 包含不支持的参数，请重新选择算法。')
    if cube.ndim != 3 or wave.ndim != 1 or cube.shape[-1] != len(wave) or len(wave) < 3:
        raise ValueError('TSHI 需要 行×列×波段 的成像数据，至少 3 个波段；不适用于时间序列。')
    if not np.isfinite(cube).all() or not np.isfinite(wave).all() or not ((np.diff(wave) > 0).all() or (np.diff(wave) < 0).all()):
        raise ValueError('TSHI 数据必须有限，波数轴需严格递增或递减。')
    height, width, bands = cube.shape
    if not height or not width or np.max(np.abs(cube)) > 1e100:
        raise ValueError('TSHI 图像不能为空，数据绝对值不能超过 1e100。')
    center = _number(params, 'center_wavenumber', float(wave[len(wave) // 2]), float(wave.min()), float(wave.max()))
    half = _number(params, 'half_width', 20, 2, 128, True)
    size = _number(params, 'windowsize', 5, 3, 31, True)
    count = _number(params, 'count', 100, 1, 1000, True)
    thr1 = _number(params, 'thr1', 1e-5, 0, 1)
    thr2 = _number(params, 'thr2', .3, -100, 100)
    sigma = _number(params, 'bm3d_sigma', 5, 0, 1e6)
    smoothness = params.get('smoothness', 'legacy')
    bm3d_enabled = params.get('bm3d_enabled', False)
    if smoothness not in {'legacy', 'variance'} or not isinstance(bm3d_enabled, bool):
        raise ValueError('TSHI 平滑度模式或 BM3D 启用状态无效。')
    if size % 2 == 0 or size > min(height, width):
        raise ValueError('TSHI 空间窗口必须为不超过图像行列数的奇数。')
    if bm3d_enabled and (min(height, width) < 8 or height * width > 65536):
        raise ValueError('BM3D 中心图像每边至少 8 像素，总像素数不超过 65536。')
    if bm3d_enabled and not bm3d_available():
        raise ValueError('BM3D 可选依赖不可用；请安装 requirements-bm3d.txt 或关闭 BM3D。')
    center_index = int(np.abs(wave - center).argmin())
    start, stop = max(0, center_index - half), min(bands, center_index + half)
    indices = np.arange(start, stop)
    if not 3 <= len(indices) <= MAX_BANDS or len(indices) * height * width > MAX_ELEMENTS:
        raise ValueError('TSHI 单次需选择 3～256 个波段，所选数据不超过 800 万个数值；请减小波段半宽。')
    if not _GATE.acquire(blocking=False):
        raise ValueError('已有 TSHI 任务在计算，请稍后重试。')
    try:
        return _compute(wave, cube, indices, center_index, size, count, thr1, thr2, smoothness, bm3d_enabled, sigma)
    finally:
        _GATE.release()


def _compute(wave, cube, indices, center_index, size, count, thr1, thr2, smoothness, use_bm3d, sigma):
    started = time.perf_counter()
    height, width, _ = cube.shape
    selected = cube[:, :, indices]
    amplitude = float(np.max(np.abs(selected)))
    normalized = selected / amplitude if amplitude else selected.copy()
    nim = normalized.mean(axis=2)
    windows = np.lib.stride_tricks.sliding_window_view(nim, (size, size))
    means = _window_means(nim, size)
    energy = np.empty_like(means)
    if smoothness == 'legacy':
        # mean(A @ A) = dot(column_sums(A), row_sums(A)) / size**2.
        # Tile the window positions to avoid allocating H*W*size*size values.
        for row in range(0, means.shape[0], 16):
            for col in range(0, means.shape[1], 64):
                tile = windows[row:row + 16, col:col + 64] - means[row:row + 16, col:col + 64, None, None]
                energy[row:row + 16, col:col + 64] = np.sum(tile.sum(-2) * tile.sum(-1), axis=-1) / size ** 2
    else:
        energy = np.maximum(_window_means(nim ** 2, size) - means ** 2, 0)
    scores = energy / np.maximum(means ** 2, 1e-24)
    effective_count = min(count, scores.size)
    flat_indices = np.argsort(scores, axis=None, kind='stable')[:effective_count]
    rows, columns = np.unravel_index(flat_indices, scores.shape)
    references = np.asarray([normalized[r:r + size, c:c + size].mean(axis=(0, 1)) for r, c in zip(rows, columns)])
    threshold = np.std(references, axis=1) / 3
    references = np.asarray([pywt.threshold(row, value, 'soft') if value > 0 else row.copy() for row, value in zip(references, threshold)])
    matrix = normalized.reshape(-1, len(indices)).T
    warnings = []
    if effective_count < count:
        warnings.append(f'可用空间窗口不足 {count} 个，实际使用 {effective_count} 个不同窗口。')
    if indices[0] == 0 or indices[-1] == len(wave) - 1:
        warnings.append('所选波段已按数据边界截取，实际范围见结果。')
    if smoothness == 'legacy':
        warnings.append('平滑度沿用源码矩阵乘法公式；非标准均方差，可切换标准方差进行对照。')
    if amplitude:
        u, singular, vh = svd(matrix, full_matrices=False, check_finite=False)
        rank = int(np.sum(singular > np.finfo(float).eps * max(matrix.shape) * singular[0]))
        u, singular, vh = u[:, :rank], singular[:rank], vh[:rank]
        curvature = np.diff(np.log(singular), n=2)
        smoothing_window = min(9, len(curvature) if len(curvature) % 2 else len(curvature) - 1)
        if smoothing_window >= 3:
            curvature = savgol_filter(curvature, smoothing_window, min(3, smoothing_window - 1))
        hit = np.flatnonzero(np.abs(curvature) <= thr1)
        considered = min(rank, int(hit[0]) + 2 if len(hit) else rank)
        reconstructed_references = np.zeros_like(references)
        signal_power = np.maximum(np.mean(references ** 2, axis=1), 1e-24)
        snrs = []
        # Averaging singular-vector images is equivalent to averaging each full reconstruction.
        for component in range(considered):
            means_map = _window_means(vh[component].reshape(height, width), size)
            coeff = means_map[rows, columns]
            reconstructed_references += singular[component] * np.outer(coeff, u[:, component])
            noise_power = np.maximum(np.mean((references - reconstructed_references) ** 2, axis=1), 1e-24)
            snrs.append(10 * (np.log10(signal_power) - np.log10(noise_power)))
        snrs = np.asarray(snrs).T
        gains = np.diff(np.column_stack([np.zeros(effective_count), snrs]), axis=1).mean(axis=0)
        chosen = np.flatnonzero(gains >= thr2)
        if not len(chosen):
            raise ValueError('TSHI 当前阈值未选中任何 SVD 成分，请降低 thr2 后重新运行。')
        reconstructed = ((u[:, chosen] * singular[chosen]) @ vh[chosen]).T.reshape(height, width, len(indices)) * amplitude
    else:
        reconstructed, singular, curvature, gains, chosen, considered, rank = selected.copy(), np.array([]), np.array([]), np.array([]), np.array([], dtype=int), 0, 0
        warnings.append('所选数据全为零，保持零值结果，未进行 SVD 筛选。')
    if not np.isfinite(reconstructed).all():
        raise ValueError('TSHI 结果含非有限数值，请检查输入数据。')
    local_center = int(np.flatnonzero(indices == center_index)[0])
    raw_center, center_image = cube[:, :, center_index], reconstructed[:, :, local_center]
    bm3d_image = None
    if use_bm3d:
        try:
            bm3d_image = np.asarray(importlib.import_module('bm3d').bm3d(center_image.copy(), sigma), dtype=float) if sigma and amplitude else center_image.copy()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError('BM3D 运行失败，请检查可选依赖或关闭 BM3D 后重试。') from exc
        if bm3d_image.shape != center_image.shape or not np.isfinite(bm3d_image).all():
            raise ValueError('BM3D 中心图像结果无效。')
        warnings.append('BM3D 仅生成独立中心图像，不改写 TSHI 光谱数据立方体。')
    scale = max(1, int(np.ceil(max(height, width) / 96)))
    details = dict(algorithm='TSHI / IIALRMA', selected_band_indices=indices.tolist(),
        center_index=center_index, center_local_index=local_center, center_wavenumber=float(wave[center_index]),
        selected_range=[float(wave[indices].min()), float(wave[indices].max())], selected_bands=len(indices),
        spatial_shape=[height, width], requested_count=count, actual_count=effective_count, windowsize=size,
        effective_rank=rank, considered_components=considered, selected_components=chosen.tolist(), component_index_base=0,
        singular_values=(singular * amplitude).tolist(), curvature=curvature.tolist(), mean_snr_gain_db=gains.tolist(),
        smoothness=smoothness, spectral_threshold='direct_soft_std_over_3',
        smooth_regions=[dict(row=int(r), column=int(c)) for r, c in zip(rows, columns)],
        center_raw=_preview(raw_center, scale), center_tshi=_preview(center_image, scale),
        center_bm3d=_preview(bm3d_image, scale) if bm3d_image is not None else None,
        bm3d_center_image=bm3d_image.tolist() if bm3d_image is not None else None,
        preview_scale=scale, bm3d_enabled=use_bm3d, bm3d_sigma=sigma,
        center_change_rmse=float(np.sqrt(np.mean(((raw_center - center_image) / max(amplitude, 1e-100)) ** 2))) * amplitude,
        warnings=warnings, duration_ms=round((time.perf_counter() - started) * 1000, 2))
    return wave[indices].copy(), reconstructed, details
