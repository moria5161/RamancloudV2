import json
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np
import torch
from scipy.interpolate import interp1d

from .model import Fast2PeakRPE


MAX_BATCH_SIZE = 64
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / 'models' / 'f2p_rpe_best.pth'
_inference_lock = Lock()


@lru_cache(maxsize=1)
def load_model():
    model_path = Path(os.environ.get('RAMANCLOUD_F2P_MODEL', DEFAULT_MODEL_PATH))
    if not model_path.is_file():
        raise ValueError('F2P model is unavailable; configure RAMANCLOUD_F2P_MODEL with the pretrained weights.')
    config = json.loads(Path(__file__).with_name('config.json').read_text(encoding='utf-8'))
    torch.set_num_threads(2)
    device = torch.device('cpu')
    model = Fast2PeakRPE(**config)
    state = torch.load(model_path, map_location=device, weights_only=True)
    state = state.get('model_state_dict', state)
    state = {key.removeprefix('module.'): value for key, value in state.items()}
    model.load_state_dict(state, strict=True)
    model.to(device)
    model.eval()
    return model, device


def resample_spectra(matrix, target_length):
    if matrix.shape[1] == target_length:
        return matrix
    old_axis = np.linspace(0, 1, matrix.shape[1])
    new_axis = np.linspace(0, 1, target_length)
    return interp1d(old_axis, matrix, kind='cubic', axis=1)(new_axis)


def correct_intensity(raw, denoised):
    corrected = np.zeros_like(denoised)
    for index in range(len(raw)):
        values = denoised[index]
        design = np.vstack([values, np.ones(len(values))]).T
        slope, intercept = np.linalg.lstsq(design, raw[index], rcond=None)[0]
        output = slope * values + intercept
        output += np.mean(raw[index]) - np.mean(output)
        corrected[index] = output
    return corrected


def denoise_batch(matrix):
    raw = np.asarray(matrix, dtype=np.float32)
    if raw.ndim != 2 or not len(raw) or raw.shape[1] < 4 or not np.isfinite(raw).all():
        raise ValueError('F2P requires finite spectra with at least 4 points')
    result = raw.astype(float)
    varying = np.flatnonzero(np.ptp(raw, axis=1) != 0)
    if not len(varying):
        return result

    # Serialize inference and align only one batch at a time to bound memory.
    with _inference_lock, torch.inference_mode():
        model, device = load_model()
        target_length = model.num_patches * model.patch_size
        for offset in range(0, len(varying), MAX_BATCH_SIZE):
            indices = varying[offset:offset + MAX_BATCH_SIZE]
            original = raw[indices]
            aligned = resample_spectra(original, target_length)
            minimum = np.min(aligned, axis=1, keepdims=True)
            span = np.max(aligned, axis=1, keepdims=True) - minimum + 1e-8
            normalized = (aligned - minimum) / span
            if not np.isfinite(normalized).all():
                raise ValueError('F2P could not normalize the input intensity range')
            tensor = torch.from_numpy(normalized).unsqueeze(1).to(device, dtype=torch.float32)
            prediction = model(tensor).cpu().numpy().squeeze(1)
            restored = prediction * span + minimum
            recovered = resample_spectra(restored, original.shape[1])
            result[indices] = correct_intensity(original, recovered)
    if not np.isfinite(result).all():
        raise ValueError('F2P produced non-finite intensities')
    return result
