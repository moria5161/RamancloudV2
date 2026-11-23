"""Validated MATLAB input and lossless MATLAB output for imaging cubes."""
import io
import json

import numpy as np
from scipy.io import loadmat, savemat, whosmat

MAX_UPLOAD = 128 * 1024 * 1024
MAX_ELEMENTS = 80_000_000
LAYOUTS = {'auto', 'bands_pixels', 'pixels_bands', 'rows_cols_bands', 'bands_rows_cols'}


def time_series_preview(wave, spectra):
    """Sample the heatmap while keeping each pixel tied to its original coordinates."""
    rows, bands = spectra.shape
    row_indices = np.linspace(0, rows - 1, min(rows, 128), dtype=int)
    band_indices = np.linspace(0, bands - 1, min(bands, 512), dtype=int)
    return spectra[np.ix_(row_indices, band_indices)], wave[band_indices], row_indices


def validate_cube(wave, cube):
    if not 3 <= len(wave) <= 20000 or cube.ndim != 3 or cube.shape[-1] != len(wave) or not cube.size or cube.size > MAX_ELEMENTS:
        raise ValueError('成像数据必须为 行×列×波段，3～20000 个波段，总数值不超过 8000 万个。')
    if not np.isfinite(cube).all() or not np.isfinite(wave).all() or not ((np.diff(wave) > 0).all() or (np.diff(wave) < 0).all()):
        raise ValueError('成像数据必须为有限数值，波数轴需严格递增或递减。')


def read_mat(content, height=None, width=None, layout='auto', pixel_order='F'):
    if not content or len(content) > MAX_UPLOAD:
        raise ValueError('MAT 文件为空或超过 128 MB。')
    if content.startswith(b'\x89HDF') or content.startswith(b'MATLAB 7.3'):
        raise ValueError('暂不支持 MATLAB v7.3/HDF5，请另存为 -v7 或 -v6 MAT 文件。')
    if layout not in LAYOUTS or pixel_order not in {'C', 'F'}:
        raise ValueError('MAT 数据布局或像素排列参数无效。')
    try:
        variables = {name: (shape, kind) for name, shape, kind in whosmat(io.BytesIO(content))}
        if 'cube' not in variables or 'x' not in variables:
            raise ValueError('MAT 文件需包含 cube（数据）和 x（波数向量）。')
        if any(variables[key][1] not in {'double', 'single', 'int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64'} for key in ('cube', 'x')):
            raise ValueError('cube 和 x 必须为数值数组，不支持结构体或单元格。')
        if np.prod(variables['cube'][0], dtype=np.float64) > MAX_ELEMENTS or np.prod(variables['x'][0], dtype=np.float64) > 20000:
            raise ValueError('MAT 声明的数据大小超出限制。')
        data = loadmat(io.BytesIO(content), variable_names=['cube', 'x'], verify_compressed_data_integrity=True)
        values, axis = data['cube'], data['x']
        if values.dtype.kind not in 'fiu' or axis.dtype.kind not in 'fiu' or axis.ndim > 2 or min(axis.shape) != 1:
            raise ValueError('cube 必须为实数矩阵，x 必须为实数向量。')
        wave = np.asarray(axis, dtype=float).reshape(-1)
        values = np.asarray(values, dtype=float)
        if layout == 'auto':
            matches = [i for i, size in enumerate(values.shape) if size == len(wave)]
            if len(matches) != 1 or values.ndim not in {2, 3}:
                raise ValueError('无法唯一识别波段轴，请手动选择 MAT 数据布局。')
            spectral_axis = matches[0]
        else:
            spectral_axis = {'bands_pixels': 0, 'pixels_bands': 1, 'rows_cols_bands': 2, 'bands_rows_cols': 0}[layout]
            expected_ndim = 2 if layout in {'bands_pixels', 'pixels_bands'} else 3
            if values.ndim != expected_ndim or values.shape[spectral_axis] != len(wave):
                raise ValueError('所选 MAT 数据布局与 cube / x 尺寸不一致。')
        if values.ndim == 2:
            if not height or not width or not 1 <= height <= 4096 or not 1 <= width <= 4096:
                raise ValueError('二维 MAT 矩阵需要填写有效的图像行数和列数。')
            flat = values.T if spectral_axis == 0 else values
            if flat.shape[0] != height * width:
                raise ValueError('图像行数×列数必须等于 MAT 矩阵的像素数量。')
            cube = flat.reshape(height, width, len(wave), order=pixel_order)
        else:
            cube = np.moveaxis(values, spectral_axis, -1)
        validate_cube(wave, cube)
        return wave, cube, dict(format='MAT', original_shape=list(values.shape), layout=layout,
            spectral_axis=spectral_axis, pixel_order=pixel_order if values.ndim == 2 else None,
            shape=list(cube.shape), original_preserved=True)
    except (NotImplementedError, OSError, TypeError, IndexError) as exc:
        raise ValueError('无法读取 MAT 文件，请检查格式或另存为 MATLAB -v7。') from exc


def mat_result(wave, cube, history):
    output = io.BytesIO()
    payload = dict(cube=np.asarray(cube), x=np.asarray(wave).reshape(1, -1),
                   layout='rows_cols_bands', history_json=json.dumps(history, ensure_ascii=False, allow_nan=False))
    for record in reversed(history):
        if record.get('method') == 'tshi':
            details = record['details']
            payload['tshi_center_wavenumber'] = details['center_wavenumber']
            if details.get('bm3d_center_image') is not None:
                payload['bm3d_center_image'] = np.asarray(details['bm3d_center_image'])
            break
    savemat(output, payload, do_compression=True)
    return output.getvalue()
