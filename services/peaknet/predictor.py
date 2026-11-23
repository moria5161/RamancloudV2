"""Strictly loaded PeakNet + supplied AirNet/PEER processing; no training or file loops."""
import hashlib
import importlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from scipy.interpolate import interp1d


class PeakNetPredictor:
    def __init__(self, profile, paths):
        self.profile, self.root = profile, Path(paths['source'])
        torch.set_num_threads(profile['threads'])
        self._verified = set()
        for name in ('process_and_predict.py', 'model/ResUNet_2500.py', 'model/cnnpeak_net_new.py', 'label_mapping_2805.json'):
            self.verify(name)
        sys.path.insert(0, str(self.root))
        self.labels = json.loads((self.root / 'label_mapping_2805.json').read_text(encoding='utf-8-sig'))
        if set(self.labels) != {str(i) for i in range(profile['classes'])}:
            raise ValueError('模型类别与标签数量不一致。')
        self.classifier = None
        self.airnet = None
        self.references = None

    def verify(self, name):
        if name not in self._verified:
            digest = hashlib.sha256()
            with (self.root / name).open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != self.profile['artifact_hashes'].get(name):
                raise ValueError('模型文件校验失败：' + name)
            self._verified.add(name)

    def load_classifier(self):
        if self.classifier is None:
            name = 'model/1223_Ep10_a20_220-1800_750_en5.pth'
            self.verify(name)
            module = importlib.import_module('model.cnnpeak_net_new')
            model = module.peaknet(1, self.profile['classes'], a=20)
            state = torch.load(self.root / name, map_location='cpu', weights_only=True)
            model.load_state_dict(state, strict=True)
            self.classifier = model.eval()
        return self.classifier

    def load_airnet(self):
        if self.airnet is None:
            name = 'model/1208AirNet.pth'
            self.verify(name)
            module = importlib.import_module('model.ResUNet_2500')
            allowed = [module.ResUNet_2500, module.BasicConv, module.ResUNetConv, module.UNetLinear,
                       torch.nn.Sequential, torch.nn.Conv1d, torch.nn.PReLU, torch.nn.BatchNorm1d,
                       torch.nn.Linear, torch.nn.MaxPool1d, torch.nn.Upsample, set]
            # This pinned checkpoint contains a complete nn.Module. Only reviewed
            # classes are allowlisted; never fall back to weights_only=False.
            previous = torch.serialization.get_safe_globals()
            try:
                torch.serialization.add_safe_globals(allowed)
                loaded = torch.load(self.root / name, map_location='cpu', weights_only=True)
            finally:
                torch.serialization.clear_safe_globals()
                torch.serialization.add_safe_globals(previous)
            state = loaded.state_dict() if isinstance(loaded, torch.nn.Module) else loaded
            model = module.ResUNet_2500(num_convs=4, batch_norm=True)
            model.load_state_dict(state, strict=True)
            self.airnet = model.eval()
        return self.airnet

    def load_references(self):
        if self.references is None:
            self.verify('cached_augmented_data.npz')
            with np.load(self.root / 'cached_augmented_data.npz', allow_pickle=False) as cache:
                names = cache['names']
                all_data = cache['data']
                label_names = set(self.labels.values())
                lookup = {str(name): i for i, name in enumerate(names) if str(name) in label_names}
                if len(lookup) != self.profile['classes'] or all_data.shape != (len(names), self.profile['points']):
                    raise ValueError('缓存参考曲线不能与 2805 类标签一一对应。')
                self.references = np.asarray([all_data[lookup[self.labels[str(i)]]] for i in range(self.profile['classes'])], dtype=np.float32)
                if not np.isfinite(self.references).all():
                    raise ValueError('参考缓存包含无效数值。')
        return self.references

    def reference(self, class_id):
        class_id = int(class_id)
        if not 0 <= class_id < self.profile['classes']:
            raise ValueError('物质编号不在当前库中。')
        values = self.load_references()[class_id]
        return dict(class_id=class_id, name=self.labels[str(class_id)],
                    wavenumber=np.linspace(self.profile['start'], self.profile['end'], self.profile['points']).tolist(),
                    intensity=values.tolist(), source='non_augmented_training_cache',
                    description='包内非增强训练/验证缓存曲线；非独立实测鉴定证据。')

    def prepare(self, spectrum, mode):
        x, y = np.asarray(spectrum['wavenumber'], dtype=np.float64), np.asarray(spectrum['intensity'], dtype=np.float64)
        if x.ndim != 1 or y.shape != x.shape or len(x) < 8 or not np.isfinite(x).all() or not np.isfinite(y).all() or not np.all(np.diff(x) > 0):
            raise ValueError('匹配输入不是有效的单条光谱。')
        p = self.profile
        grid = np.linspace(p['start'], p['end'], p['points'])
        if x[0] > grid[0] or x[-1] < grid[-1]:
            raise ValueError('模型波段覆盖不足，禁止外推。')
        before = interp1d(x, y, kind='cubic', bounds_error=True)(grid)
        trace = None
        if mode == 'auto':
            # Reuse only reviewed pure algorithm functions; never call the
            # package's directory-clearing or unsafe model-loading entry points.
            algorithm = importlib.import_module('process_and_predict')
            dense_x = np.linspace(p['start'], p['end'], p['airnet_points'])
            dense = interp1d(x, y, kind='cubic', bounds_error=True)(dense_x)
            scale = float(dense.max())
            if scale <= 0:
                raise ValueError('AirNet 输入需要正的强度最大值。')
            denoised = dense / scale
            for _ in range(p['peer_iterations']):
                denoised = algorithm.PEER(denoised.tolist(), p['peer_window'])
                denoised = np.asarray(denoised, dtype=np.float32)
            with torch.inference_mode():
                weights = self.load_airnet()(torch.as_tensor(denoised).reshape(1, 1, -1))[0, 0].numpy().copy()
            if not np.isfinite(weights).all():
                raise ValueError('AirNet 权重包含非有限数值。')
            iterations = 0
            for index in range(p['baseline_iterations']):
                baseline = algorithm.WhittakerSmooth(denoised, weights, p['baseline_lambda'], 2)
                residual = denoised - baseline
                negative = residual < 0
                iterations = index + 1
                if not np.any(negative) or abs(float(np.sum(residual[negative]))) < 1e-6:
                    break
                deviations = np.abs(residual[negative])
                weights[negative] *= 1 + deviations / deviations.max()
                weights[0] = weights[-1] = weights.max()
                if not np.isfinite(weights).all():
                    raise ValueError('基线迭代数值不稳定，请检查输入或使用已处理版本。')
            baseline = algorithm.WhittakerSmooth(denoised, weights, p['baseline_lambda'], 2)
            corrected = (denoised - baseline) * scale
            values = interp1d(dense_x, corrected, kind='cubic', bounds_error=True)(grid)
            trace = dict(wavenumber=dense_x.tolist(), denoised=(denoised * scale).tolist(),
                         baseline=(baseline * scale).tolist(), corrected=corrected.tolist(), iterations=iterations)
        elif mode == 'prepared':
            values = before.copy()
        else:
            raise ValueError('不支持的预处理模式。')
        scale = float(np.max(np.abs(values)))
        if not np.isfinite(values).all() or scale <= 1e-12 or np.ptp(values) <= 1e-12:
            raise ValueError('处理后的光谱无有效变化或包含非有限数值。')
        return dict(model_input=dict(wavenumber=grid.tolist(), intensity=(values / scale).astype(np.float32).tolist()),
                    input_preview=dict(wavenumber=grid.tolist(), intensity=(before / max(float(np.max(np.abs(before))), 1e-12)).tolist()),
                    preprocessing=trace, normalization_scale=scale, preprocessing_mode=mode)

    def run(self, payload):
        torch.set_num_threads(self.profile['threads'])
        if payload.get('action') == 'reference':
            return self.reference(payload['class_id'])
        started = time.monotonic()
        result = self.prepare(payload['spectrum'], payload['preprocessing_mode'])
        model = self.load_classifier()
        with torch.inference_mode():
            tensor = torch.tensor(result['model_input']['intensity'], dtype=torch.float32).reshape(1, 1, -1)
            logits = model(tensor)
            if logits.shape != (1, self.profile['classes']) or not torch.isfinite(logits).all():
                raise ValueError('模型输出维度或数值异常。')
            probabilities = torch.softmax(logits[0], dim=0)
            scores, indices = probabilities.topk(int(payload['top_k']))
        result.update(candidates=[dict(rank=i + 1, class_id=int(class_id), name=self.labels[str(int(class_id))],
                                       model_score=float(score), reference=self.reference(int(class_id)))
                                  for i, (score, class_id) in enumerate(zip(scores, indices))],
                      score_type='closed_set_softmax', inference_performed=True,
                      duration_seconds=round(time.monotonic() - started, 3))
        return result
