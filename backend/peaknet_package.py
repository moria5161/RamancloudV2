"""Pinned, local PeakNet package installation and model input contract."""
import hashlib
import json
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA256 = '9fbebabbfa8a9183da99968d70923b69e60d6329f676d14be9b3ec9b6a6ac4cb'
FILES = ['process_and_predict.py', 'model/ResUNet_2500.py', 'model/cnnpeak_net_new.py',
         'model/1208AirNet.pth', 'model/1223_Ep10_a20_220-1800_750_en5.pth',
         'label_mapping_2805.json', 'cached_augmented_data.npz', 'README.md']


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def install_package(archive):
    source = ROOT / '.runtime/peaknet/source'
    source.mkdir(parents=True, exist_ok=True)
    if file_hash(archive) != ARCHIVE_SHA256:
        raise ValueError('压缩包与已验证的 PeakNet 版本不一致，请先检查新版模型契约。')
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            relative = PurePosixPath(item.filename)
            target = (source / Path(*relative.parts)).resolve()
            if relative.is_absolute() or '..' in relative.parts or source.resolve() not in target.parents or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('压缩包包含越界路径或符号链接。')
        for name in FILES:
            target = source / name
            if target.exists():
                digest = hashlib.sha256()
                with zipped.open(name) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
                if file_hash(target) != digest.hexdigest():
                    raise ValueError('保留本地修改，未覆盖文件：' + str(target))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(name) as src, target.open('wb') as dest:
                    shutil.copyfileobj(src, dest, length=1024 * 1024)
    manifest = dict(archive_sha256=ARCHIVE_SHA256, files={name: file_hash(source / name) for name in FILES})
    (source.parent / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


def configuration():
    source = ROOT / '.runtime/peaknet/source'
    manifest_path = source.parent / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    profile = dict(id='pers-peaknet-2805-v1', label='普识纳米 · PeakNet 2805', library_id='pers-2805',
                   classes=2805, start=220., end=1800., points=750, airnet_points=2500,
                   interpolation='cubic_no_extrapolation', normalization='max_abs',
                   peer_window=11, peer_iterations=3, baseline_lambda=1e8, baseline_iterations=500,
                   device='cpu', threads=1, archive_sha256=ARCHIVE_SHA256, artifact_hashes=manifest.get('files', {}),
                   reference_source='non_augmented_training_cache', score_type='closed_set_softmax')
    paths = dict(source=str(source), python=str(ROOT / '.venv-vib2mol' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')))
    ready = (manifest.get('archive_sha256') == ARCHIVE_SHA256 and Path(paths['python']).is_file()
             and all((source / name).is_file() for name in FILES))
    return profile, paths, ready


def catalog():
    profile, paths, ready = configuration()
    if not ready:
        return {}
    labels = json.loads((Path(paths['source']) / 'label_mapping_2805.json').read_text(encoding='utf-8-sig'))
    if set(labels) != {str(i) for i in range(profile['classes'])}:
        raise ValueError('物质标签与模型的 2805 类不一致。')
    return labels


def prepare_source(spectrum, profile):
    import numpy as np
    x = np.asarray(spectrum.get('wavenumber', []), dtype=float)
    y = np.asarray(spectrum.get('intensity', []), dtype=float)
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or not 8 <= len(x) <= 20000:
        raise ValueError('需要 8–20000 个波数—强度数据点。')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('光谱包含非有限数值。')
    descending = bool(np.all(np.diff(x) < 0))
    if descending:
        x, y = x[::-1], y[::-1]
    elif not np.all(np.diff(x) > 0):
        raise ValueError('波数必须严格单调，不能包含重复点。')
    start, end = profile['start'], profile['end']
    if x[0] > start or x[-1] < end:
        raise ValueError(f'此模型需要完整覆盖 {start:g}–{end:g} cm⁻¹；当前仅覆盖 {x[0]:g}–{x[-1]:g} cm⁻¹。')
    inside = (x > start) & (x < end)
    cropped_x = np.concatenate(([start], x[inside], [end]))
    cropped_y = np.concatenate(([np.interp(start, x, y)], y[inside], [np.interp(end, x, y)]))
    if len(cropped_x) < 8 or np.ptp(cropped_y) <= np.finfo(float).eps * max(1., np.max(np.abs(cropped_y))):
        raise ValueError('匹配波段内数据点不足或强度恒定，不能进行有效匹配。')
    if cropped_y.max() <= 0:
        raise ValueError('匹配波段内需要正的强度最大值，请检查光谱或基线校正结果。')
    warnings = []
    if np.diff(cropped_x).max() > 20:
        warnings.append('波段内采样间距超过 20 cm⁻¹，插值不能恢复缺失的峰。')
    if np.any(cropped_y < 0):
        warnings.append('已保留负强度，请结合图形检查基线校正结果。')
    digest = hashlib.sha256(json.dumps(spectrum, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return dict(wavenumber=cropped_x.tolist(), intensity=cropped_y.tolist(), warnings=warnings,
                preparation=dict(input_sha256=digest, reversed=descending, range=[start, end],
                                 original_points=len(x), cropped_points=len(cropped_x),
                                 endpoints='linear_interpolation_between_measured_neighbors'))
