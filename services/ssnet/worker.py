"""CPU/CUDA adaptation of the supplied train_voigt_aug.py and test.py.

Uses the supplied U-Net ECA unchanged; jobs own all inputs and outputs. No plots,
global experiment folders, unsafe full-module loads, or nested worker processes.
"""
import hashlib
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
import threading
import time


def write_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def background_sample(spectrum, rng):
    """Supplied pseudo-Voigt + polynomial baseline + white noise augmentation."""
    import numpy as np
    spectrum = np.asarray(spectrum, dtype=np.float32)
    maximum = float(spectrum.max())
    if maximum > 0:
        spectrum = spectrum / maximum
    length = len(spectrum)
    keys = np.arange(length).reshape(1, length)
    count = rng.integers(10, 25)
    locs = rng.integers(0, length, size=(count, 1))
    scales = rng.integers(2, max(3, length // 20), size=(count, 1))
    intensities = rng.uniform(.1, 1, size=(count, 1))
    etas = rng.uniform(.1, .9, size=(count, 1))
    ratio = (keys - locs) / scales
    peaks = etas / (1 + ratio ** 2) + (1 - etas) * np.exp(-np.log(2) * ratio ** 2)
    peaks = (peaks / (peaks.max(axis=1, keepdims=True) + 1e-8)) * intensities
    baseline = np.polyval(rng.uniform(-1, 1, 4), np.linspace(-1, 1, length))
    baseline -= baseline.min()
    if baseline.max() > 0:
        baseline = baseline / baseline.max() * rng.uniform(.2, 1.5)
    background = peaks.sum(axis=0) + baseline + rng.normal(0, rng.uniform(.005, .03), length)
    mixed = np.clip(spectrum + background, 0, None)
    scale = mixed.max()
    return (mixed / scale).astype(np.float32), (background / scale).astype(np.float32)


def derivative(values):
    import numpy as np
    # The supplied training and testing scripts disagree on their first value.
    # Use the training convention consistently for the newly trained models.
    return np.diff(values, prepend=values[0]).astype(np.float32)


def run(request, directory):
    import joblib
    import numpy as np
    import torch
    from sklearn.ensemble import RandomForestClassifier
    from network import Unet
    torch.set_num_threads(1)
    torch.manual_seed(42)
    rng = np.random.default_rng(42)
    started = time.monotonic()
    data = request['input']
    device_name = data['settings']['device'] if request['kind'] == 'train' else data.get('device', 'cpu')
    if device_name == 'cuda' and not torch.cuda.is_available():
        raise ValueError('SSnet 的 CUDA 运行环境当前不可用，请联系管理员。')
    device = torch.device(device_name)

    def progress(percent, stage, **extra):
        write_json(directory / 'progress.json', dict(percent=round(percent, 2), stage=stage,
                                                     elapsed_seconds=round(time.monotonic()-started, 1), **extra))

    if request['kind'] == 'train':
        settings, prepared = data['settings'], data['prepared']
        model = Unet(prepared['grid']['points']).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
        amp = device.type == 'cuda'
        scaler = torch.amp.GradScaler('cuda', enabled=amp)
        bases = np.asarray(prepared['spectra'], dtype=np.float32)
        epochs, samples, batch = settings['epochs'], settings['samples_per_epoch'], settings['batch_size']
        losses = []
        for epoch in range(1, epochs+1):
            model.train()
            for group in optimizer.param_groups:
                group['lr'] = 1e-2 * .1 ** (epoch // 25)
            total, seen = 0., 0
            for offset in range(0, samples, batch):
                count = min(batch, samples-offset)
                generated = [background_sample(bases[rng.integers(len(bases))], rng) for _ in range(count)]
                inputs = torch.as_tensor(np.stack([v[0] for v in generated])[:, None], device=device)
                targets = torch.as_tensor(np.stack([v[1] for v in generated])[:, None], device=device)
                optimizer.zero_grad()
                with (torch.autocast('cuda') if amp else nullcontext()):
                    loss = torch.nn.functional.mse_loss(model(inputs), targets)
                if not torch.isfinite(loss):
                    raise ValueError('训练损失不是有限数值，请检查标准品或训练参数。')
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
                total += float(loss.detach().cpu()) * count
                seen += count
                progress(85 * ((epoch-1) + seen/samples)/epochs, 'unet', epoch=epoch, epochs=epochs,
                         batch_samples=seen, samples_per_epoch=samples, loss=total/seen)
            losses.append(total/seen)
        progress(86, 'random_forest_samples')
        features, labels = [], []
        for i in range(settings['rf_samples']):
            positive, _ = background_sample(bases[0], rng)
            negative, _ = background_sample(np.zeros(bases.shape[1], dtype=np.float32), rng)
            features.extend([derivative(positive), derivative(negative)])
            labels.extend([1, 0])
            if i % 100 == 0:
                progress(86+5*i/settings['rf_samples'], 'random_forest_samples')
        progress(92, 'random_forest_training')
        forest = RandomForestClassifier(n_estimators=settings['trees'], n_jobs=1, random_state=42)
        forest.fit(np.asarray(features), labels)
        progress(98, 'saving')
        # Save parameters, never a pickled full torch module. RF files are only
        # generated by our worker and verified against server-owned hashes.
        torch.save(model.cpu().state_dict(), directory / 'unet.pth')
        joblib.dump(forest, directory / 'forest.joblib')
        result = dict(artifacts={name:sha(directory/name) for name in ['unet.pth','forest.joblib']},
                      network_sha256=sha(Path(__file__).with_name('network.py')), loss_history=losses,
                      grid=prepared['grid'], device=str(device), validation_status='not_experimentally_validated',
                      duration_seconds=round(time.monotonic()-started, 2), algorithm='ssnet-voigt-eca-v1')
    else:
        progress(5, 'loading_model')
        model_dir = Path(request['model_dir'])
        if data.get('network_sha256') != sha(Path(__file__).with_name('network.py')):
            raise ValueError('模型结构代码版本已变化，请使用原版本或重新训练。')
        for name in ['unet.pth', 'forest.joblib']:
            if sha(model_dir/name) != data['artifacts'][name]:
                raise ValueError('模型文件校验失败，请重新训练该标准品模型。')
        model = Unet(data['grid']['points'])
        model.load_state_dict(torch.load(model_dir/'unet.pth', map_location='cpu', weights_only=True), strict=True)
        model.to(device).eval()
        # This path is server-generated, not an uploaded model or a request path.
        forest = joblib.load(model_dir/'forest.joblib')
        spectrum = np.asarray(data['prepared']['intensity'], dtype=np.float32)
        progress(35, 'extracting')
        with torch.inference_mode():
            predicted = model(torch.as_tensor(spectrum, device=device).reshape(1, 1, -1))[0, 0].cpu().numpy()
        extracted = spectrum - predicted
        score = None
        if extracted.max() > 0:
            positive_index = list(forest.classes_).index(1)
            score = float(forest.predict_proba(derivative(extracted/extracted.max()).reshape(1,-1))[0,positive_index])
        scale = data['prepared']['scale']
        result = dict(wavenumber=data['prepared']['wavenumber'], mixture=(spectrum*scale).tolist(),
                      extracted=(extracted*scale).tolist(), background=(predicted*scale).tolist(),
                      removed_offset=data['prepared']['offset'], model_name=data['model_name'],
                      model_id=data['model_id'], rf_score=score, score_type='synthetic_random_forest',
                      duration_seconds=round(time.monotonic()-started, 2), inference_performed=True, device=str(device),
                      note='目标成分提取与估计背景，不是对所有组分的联合分解；RF 得分不是浓度、检出限或经标定的鉴定概率。')
        if not all(np.isfinite(result[key]).all() for key in ['mixture','extracted','background']):
            raise ValueError('模型输出包含无效数值。')
    progress(100, 'completed')
    return result


def watch_parent():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        handle = kernel.OpenProcess(0x100000,False,os.getppid())
        if handle:
            kernel.WaitForSingleObject(handle,0xFFFFFFFF)
            os._exit(0)
    else:
        parent = os.getppid()
        while os.getppid() == parent:
            time.sleep(2)
        os._exit(0)


if __name__ == '__main__':
    path = Path(sys.argv[1])
    threading.Thread(target=watch_parent,daemon=True).start()
    try:
        write_json(path.parent/'output.json', run(json.loads(path.read_text(encoding='utf-8')),path.parent))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        write_json(path.parent/'error.json',dict(error=str(exc)[:500]))
        sys.exit(1)
