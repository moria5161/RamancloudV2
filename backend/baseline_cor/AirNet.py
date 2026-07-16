import torch
from torch import nn
import numpy as np
from scipy.stats import kurtosis
from scipy.sparse import csc_matrix, eye, diags
from scipy.sparse.linalg import spsolve
from scipy.interpolate import interp1d
import multiprocessing as mp # 导入多进程库

# =====================================================================================
# 0. 为多进程创建的顶层 Worker 函数
# =====================================================================================
def whittaker_smooth_worker(args):
    """一个简单的包装函数，以便被多进程池调用"""
    x, w, lambda_, differences = args
    return WhittakerSmooth(x, w, lambda_, differences)

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

def load_model(model_path='/media/ramancloud/api/baseline_cor/model_pt/0925RU_statedict.pth'):
    device = torch.device("cpu")
    model = ResUNet_2500(num_convs=4, batch_norm=True)
    state_dict = torch.load(model_path, map_location=device, weights_only=False)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    print("AirNet model loaded successfully.")
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

def AirNet_process(spectra, model, device, itermax=500, max_batch_size=1024):
    model, device = load_model()
    model.eval()
    spectra_np = np.asarray(spectra)
    if spectra_np.ndim == 1:
        spectra_to_process = [spectra_np]
        is_single_input = True
    else:
        spectra_to_process = spectra_np 
        is_single_input = False

    all_corrected_spectra = []
    
    interpolated_spectra = []
    spectra = np.array(spectra_to_process)
    for spectrum in spectra:
        original_length = len(spectrum)
        original_indices = np.linspace(0, 1, original_length) 
        target_indices = np.linspace(0, 1, 2500) 
        interp_func = interp1d(original_indices, spectrum, kind='linear', bounds_error=False, fill_value='extrapolate')
        interpolated_spectrum = interp_func(target_indices)
        interpolated_spectra.append(interpolated_spectrum)
    
    spectra_np = np.array(interpolated_spectra)
    num_spectra = spectra_np.shape[0]
    
    num_cores = max(1, mp.cpu_count() - 48)
    pool = mp.Pool(processes=num_cores)

    for i in range(0, num_spectra, max_batch_size):
        chunk_np = spectra_np[i : i + max_batch_size]

        max_vals = np.max(chunk_np, axis=1, keepdims=True)
        chunk_norm_np = chunk_np / max_vals

        input_tensor = torch.from_numpy(chunk_norm_np).unsqueeze(1).to(device, dtype=torch.float32)        
        with torch.no_grad():
            weights_batch = model(input_tensor).squeeze(1) 

        spectrum_np_batch = input_tensor.squeeze(1).cpu().numpy()
        weights_np_batch = weights_batch.cpu().numpy()
        max_vals_np = max_vals[i : i + max_batch_size]

        best_lambdas = auto_select_lambda(input_tensor.squeeze(1), weights_batch, differences=2)
        
        a4_np = weights_np_batch.copy()
        
        for m in range(1, itermax + 1):
            tasks = [(spectrum_np_batch[j], a4_np[j], best_lambdas[j], 2) for j in range(a4_np.shape[0])]
            
            z_np_list = pool.map(whittaker_smooth_worker, tasks)
            z_np = np.array(z_np_list)

            d_np = spectrum_np_batch - z_np
            neg_indices_np = d_np < 0
            
            if not np.any(neg_indices_np):
                break
            
            dssn = np.abs(np.sum(d_np[neg_indices_np]))
            if dssn < 1e-6:
                break

            for j in range(a4_np.shape[0]):
                if np.any(neg_indices_np[j]):
                    devs_j = np.abs(d_np[j][neg_indices_np[j]])
                    max_dev = np.max(devs_j)
                    if max_dev > 0:
                        normalized_devs = devs_j / max_dev
                        increment = 1.0 + normalized_devs
                        a4_np[j][neg_indices_np[j]] *= increment

            max_weights_per_spectrum = np.max(a4_np, axis=1, keepdims=True)
            a4_np[:, 0] = max_weights_per_spectrum.squeeze()
            a4_np[:, -1] = max_weights_per_spectrum.squeeze()

        final_tasks = [(spectrum_np_batch[j], a4_np[j], best_lambdas[j], 2) for j in range(a4_np.shape[0])]
        baseline_corrected_list = pool.map(whittaker_smooth_worker, final_tasks)
        baseline_corrected_np = np.array(baseline_corrected_list)
      
        spectrum_peer_denorm = spectrum_np_batch * max_vals_np
        baseline_corrected_denorm = baseline_corrected_np * max_vals_np
        output_corrected_np = spectrum_peer_denorm - baseline_corrected_denorm
        original_corrected_spectra = []
        for j, spectrum in enumerate(chunk_np):
            original_length = len(spectra[i + j])  
            target_indices = np.linspace(0, 1, 2500) 
            original_indices = np.linspace(0, 1, original_length)  
            
            interp_func = interp1d(target_indices, output_corrected_np[j], kind='linear', bounds_error=False, fill_value='extrapolate')
            original_corrected_spectrum = interp_func(original_indices)
            original_corrected_spectra.append(original_corrected_spectrum)

        output_corrected_np = np.array(original_corrected_spectra)
        all_corrected_spectra.append(output_corrected_np)

    pool.close()
    pool.join()
    
    final_results = np.concatenate(all_corrected_spectra, axis=0)
    
    return final_results[0] if is_single_input else final_results