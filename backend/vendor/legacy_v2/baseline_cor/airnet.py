import torch
from torch import nn
import numpy as np
from scipy.stats import kurtosis
from scipy.sparse import csc_matrix, eye, diags
from scipy.sparse.linalg import spsolve
import os
from pathlib import Path
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

_inference_lock = Lock()
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / 'models' / 'airnet.pth'

# =====================================================================================
# 1. 模型定义
# =====================================================================================

class BasicConv(nn.Module):
    def __init__(self, channels_in, channels_out, batch_norm):
        super(BasicConv, self).__init__()
        basic_conv = [nn.Conv1d(channels_in, channels_out, kernel_size = 3, stride = 1, padding = 1, bias = True)]
        basic_conv.append(nn.PReLU())
        if batch_norm:
            basic_conv.append(nn.BatchNorm1d(channels_out))     
        self.body = nn.Sequential(*basic_conv)

    def forward(self, x):
        return self.body(x)

class ResUNetConv(nn.Module):
    def __init__(self, num_convs, channels, batch_norm):
        super(ResUNetConv, self).__init__()
        unet_conv = []
        for _ in range(num_convs):
            unet_conv.append(nn.Conv1d(channels, channels, kernel_size = 3, stride = 1, padding = 1, bias = True))
            unet_conv.append(nn.PReLU())
            if batch_norm:
                unet_conv.append(nn.BatchNorm1d(channels))       
        self.body = nn.Sequential(*unet_conv)

    def forward(self, x):
        res = self.body(x)
        res += x
        return res

class UNetLinear(nn.Module):
    def __init__(self, repeats, channels_in, channels_out):
        super().__init__()
        modules = []
        for i in range(repeats):
            modules.append(nn.Linear(channels_in, channels_out))
            modules.append(nn.PReLU())       
        self.body = nn.Sequential(*modules)

    def forward(self, x):
        x = self.body(x)
        return x

class ResUNet_2500(nn.Module):
    def __init__(self, num_convs, batch_norm):
        super(ResUNet_2500, self).__init__()
        res_conv1 = [BasicConv(1, 64, batch_norm)]
        res_conv1.append(ResUNetConv(num_convs, 64, batch_norm))
        self.conv1 = nn.Sequential(*res_conv1)
        self.pool1 = nn.MaxPool1d(5)

        res_conv2 = [BasicConv(64, 128, batch_norm)]
        res_conv2.append(ResUNetConv(num_convs, 128, batch_norm))
        self.conv2 = nn.Sequential(*res_conv2)
        self.pool2 = nn.MaxPool1d(5)

        res_conv3 = [BasicConv(128, 256, batch_norm)]
        res_conv3.append(ResUNetConv(num_convs, 256, batch_norm))
        res_conv3.append(BasicConv(256, 128, batch_norm))
        self.conv3 = nn.Sequential(*res_conv3)       
        self.up3 = nn.Upsample(scale_factor = 5)

        res_conv4 = [BasicConv(256, 128, batch_norm)]
        res_conv4.append(ResUNetConv(num_convs, 128, batch_norm))
        res_conv4.append(BasicConv(128, 64, batch_norm))
        self.conv4 = nn.Sequential(*res_conv4)     
        self.up4 = nn.Upsample(scale_factor = 5)

        res_conv5 = [BasicConv(128, 64, batch_norm)]
        res_conv5.append(ResUNetConv(num_convs,64, batch_norm))
        self.conv5 = nn.Sequential(*res_conv5)

        res_conv6 = [BasicConv(64, 1, batch_norm)]
        self.conv6 = nn.Sequential(*res_conv6) 
        self.linear7 = UNetLinear(3, 2500, 2500)   
                
    def forward(self, x):
        x = self.conv1(x)
        x1 = self.pool1(x)       
        x2 = self.conv2(x1)
        x3 = self.pool2(x2)       
        x3 = self.conv3(x3)
        x3 = self.up3(x3)      
        x4 = torch.cat((x2, x3), dim = 1)
        x4 = self.conv4(x4)
        x5 = self.up4(x4)
        x6 = torch.cat((x, x5), dim = 1)
        x6 = self.conv5(x6)
        x7 = self.conv6(x6)      
        out = self.linear7(x7)
        output = torch.sigmoid(out)
        return output
    
# =====================================================================================
# 2. 加载模型
# =====================================================================================

@lru_cache(maxsize=1)
def load_model():
    model_path = Path(os.environ.get('RAMANCLOUD_AIRNET_MODEL', DEFAULT_MODEL_PATH))
    if not model_path.is_file():
        raise ValueError('AirNet model is unavailable; configure RAMANCLOUD_AIRNET_MODEL with the pretrained weights.')
    torch.set_num_threads(2)
    device = torch.device(os.environ.get('RAMANCLOUD_LEGACY_DEVICE', 'cpu'))
    model = ResUNet_2500(num_convs=4, batch_norm=True)
    state_dict = torch.load(model_path, map_location='cpu', weights_only=True)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model, device

# =====================================================================================
# 辅助函数（自动选择平滑度）
# =====================================================================================
def WhittakerSmooth(x, w, lambda_, differences=2):
    X = np.matrix(x)
    m = X.size
    E = eye(m, format='csc')
    for i in range(differences):
        E = E[1:] - E[:-1]
    W = diags(w, 0, shape=(m, m))
    A = csc_matrix(W + (lambda_ * E.T * E))
    B = csc_matrix(W * X.T)
    background = spsolve(A, B)
    return np.array(background)

    
def auto_select_lambda(spectrum_batch, weights_batch, differences=2, 
                      lambda_range=(1e2, 1e11)):

    min_lambda, max_lambda = lambda_range
    log_min = np.log10(min_lambda)
    log_max = np.log10(max_lambda)
    log_lambdas = np.arange(log_min, log_max + 1, 1.0) 
    lambda_candidates = [10**log_lambda for log_lambda in log_lambdas]
    spectrum_np = spectrum_batch.cpu().numpy()
    weights_np = weights_batch.cpu().numpy()
    batch_size = spectrum_np.shape[0]
    best_lambdas = []
    
    for i in range(batch_size):
        spectrum = spectrum_np[i]
        weights = weights_np[i]
        best_lambda_for_spectrum = lambda_candidates[0]
        best_score = float('inf')
        lambda_scores = []

        for current_lambda in lambda_candidates:
            baseline_temp = WhittakerSmooth(spectrum, weights, current_lambda, differences)
            corrected_temp = spectrum - baseline_temp
            
            neg_points = corrected_temp[corrected_temp < 0]
            neg_ratio = len(neg_points) / len(corrected_temp) if len(corrected_temp) > 0 else 0
            neg_penalty = np.mean(np.abs(neg_points)) if len(neg_points) > 0 else 0
            
            baseline_diff2 = np.diff(baseline_temp, n=2)
            smoothness_penalty = np.sum(np.abs(baseline_diff2))
            
            kurtosis_score = kurtosis(corrected_temp, fisher=False)

            lambda_scores.append({
                'lambda': current_lambda,
                'neg_ratio': neg_ratio,
                'neg_penalty': neg_penalty,
                'smoothness_penalty': smoothness_penalty,
                'kurtosis_score': kurtosis_score,
            })

        neg_penalties = [s['neg_penalty'] for s in lambda_scores]
        smoothness_penalties = [s['smoothness_penalty'] for s in lambda_scores]
        kurtosis_scores = [s['kurtosis_score'] for s in lambda_scores]
        
        min_neg_p = min(neg_penalties)
        max_neg_p = max(neg_penalties) if len(neg_penalties) > 1 else min_neg_p
        min_smooth_p = min(smoothness_penalties)
        max_smooth_p = max(smoothness_penalties) if len(smoothness_penalties) > 1 else min_smooth_p
        min_kurtosis = min(kurtosis_scores)
        max_kurtosis = max(kurtosis_scores) if len(kurtosis_scores) > 1 else min_kurtosis

        for score_info in lambda_scores:
            norm_neg_p = (score_info['neg_penalty'] - min_neg_p) / (max_neg_p - min_neg_p) if (max_neg_p - min_neg_p) > 0 else 0
            norm_smooth_p = (score_info['smoothness_penalty'] - min_smooth_p) / (max_smooth_p - min_smooth_p) if (max_smooth_p - min_smooth_p) > 0 else 0
            norm_kurtosis = (score_info['kurtosis_score'] - min_kurtosis) / (max_kurtosis - min_kurtosis) if (max_kurtosis - min_kurtosis) > 0 else 0
            under_subtraction_penalty = 1 - norm_kurtosis
            
            w_neg_ratio, w_neg_penalty, w_smoothness, w_under_subtraction = 1.0, 1.0, 1.0, 1.0
            score = (score_info['neg_ratio'] * w_neg_ratio + norm_neg_p * w_neg_penalty +
                     norm_smooth_p * w_smoothness + under_subtraction_penalty * w_under_subtraction)
            
            if score < best_score:
                best_score = score
                best_lambda_for_spectrum = score_info['lambda']
        
        best_lambdas.append(best_lambda_for_spectrum)
        
    return best_lambdas

def _refine_spectrum(args):
    spectrum, weights, smoothing = args
    weights = weights.copy()
    for _ in range(500):
        baseline = WhittakerSmooth(spectrum, weights, smoothing, 2)
        residual = spectrum - baseline
        negative = residual < 0
        if not negative.any() or abs(residual[negative].sum()) < 1e-6:
            break
        deviations = np.abs(residual[negative])
        weights[negative] *= 1 + deviations / deviations.max()
        weights[0] = weights[-1] = weights.max()
    return spectrum - WhittakerSmooth(spectrum, weights, smoothing, 2)


def airnet_process(matrix):
    """V1 network and automatic smoothing, bounded batches and per-spectrum convergence."""
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] < 4 or not np.isfinite(matrix).all():
        raise ValueError('AirNet requires finite spectra with at least 4 points')
    result = np.zeros_like(matrix)
    varying = np.flatnonzero(np.ptp(matrix, axis=1) != 0)
    if not len(varying):
        return result
    # Bound inference memory when multiple web requests arrive together.
    with _inference_lock:
        model, device = load_model()
        target = np.linspace(0, 1, 2500)
        original = np.linspace(0, 1, matrix.shape[1])
        with ThreadPoolExecutor(max_workers=4) as pool:
            for offset in range(0, len(varying), 16):
                indices = varying[offset:offset + 16]
                chunk = np.array([np.interp(target, original, matrix[index]) for index in indices])
                scales = chunk.max(axis=1, keepdims=True)
                scales = np.where(scales == 0, np.abs(chunk).max(axis=1, keepdims=True), scales)
                inputs = torch.from_numpy(chunk / scales).unsqueeze(1).to(device, dtype=torch.float32)
                with torch.inference_mode():
                    weights = model(inputs).squeeze(1)
                smoothing = auto_select_lambda(inputs.squeeze(1), weights, differences=2)
                corrected = list(pool.map(_refine_spectrum, zip(inputs.squeeze(1).cpu().numpy(), weights.cpu().numpy(), smoothing)))
                for index, row, scale in zip(indices, corrected, scales[:, 0]):
                    result[index] = np.interp(original, target, row * scale)
    if not np.isfinite(result).all():
        raise ValueError('AirNet produced non-finite values')
    return result
