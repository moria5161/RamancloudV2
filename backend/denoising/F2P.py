import numpy as np
from scipy.signal import resample
import torch
import torch.nn as nn
from numpy import linalg as la
from scipy.interpolate import interp1d

def spectra_resample(y, target_len):
    original_len = y.shape[1]
    
    x_old = np.linspace(0, 1, original_len)
    x_target = np.linspace(0, 1, target_len)
    
    f_expand = interp1d(x_old, y, kind='cubic', axis=1)
    y_target = f_expand(x_target)
    
    return y_target


# =====================================================================================
# 1. 模型定义
# =====================================================================================
def position_embedding(embed_dim, num_patches):
    pos = np.arange(num_patches, dtype=np.float64).reshape(-1, 1)
    dim_t = np.arange(embed_dim // 2, dtype=np.float64)
    dim_t = 1. / (10000.**(dim_t / (embed_dim // 2)))
    pos_times_dim = pos * dim_t
    emb = np.concatenate((np.sin(pos_times_dim), np.cos(pos_times_dim)), axis=1)
    if embed_dim % 2 != 0:
        emb = np.concatenate((emb, np.zeros((num_patches, 1))), axis=1)
    return torch.from_numpy(emb).float()


class PatchEmbedding(nn.Module):
    def __init__(self, patch_size, embed_dim):
        super().__init__()
        self.proj = nn.Conv1d(1, embed_dim, kernel_size=patch_size, stride=patch_size)

    def forward(self, x):
        return self.proj(x).transpose(1, 2)


class Attention(nn.Module):
    def __init__(self, dim, heads=8):
        super().__init__()
        self.heads = heads
        self.scale = (dim // heads)**-0.5
        self.to_qkv = nn.Linear(dim, dim * 3, bias=False)
        self.to_out = nn.Linear(dim, dim)

    def forward(self, x):
        qkv = self.to_qkv(x).chunk(3, dim=-1)
        q, k, v = map(lambda t: t.reshape(t.shape[0], t.shape[1], self.heads, -1).transpose(1, 2), qkv)
        dots = (q @ k.transpose(-2, -1)) * self.scale
        attn = dots.softmax(dim=-1)
        out = (attn @ v).transpose(1, 2).reshape(x.shape)
        return self.to_out(out)


class TransformerBlock(nn.Module):
    def __init__(self, dim, heads):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = Attention(dim, heads)
        self.norm2 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(nn.Linear(dim, dim * 4), nn.GELU(), nn.Linear(dim * 4, dim))

    def forward(self, x):
        x = x + self.attn(self.norm1(x))
        x = x + self.ffn(self.norm2(x))
        return x


class SpecTransformer(nn.Module):
    def __init__(self, spectrum_length, patch_size, embed_dim, depth, heads):
        super().__init__()
        if spectrum_length % patch_size != 0:
            raise ValueError("光谱长度必须能被patch大小整除")
        self.num_patches = spectrum_length // patch_size
        self.patch_embed = PatchEmbedding(patch_size, embed_dim)
        self.pos_embed = nn.Parameter(position_embedding(embed_dim, self.num_patches), requires_grad=False)
        self.transformer_blocks = nn.ModuleList([TransformerBlock(embed_dim, heads) for _ in range(depth)])
        self.decoder = nn.Sequential(
                            nn.Linear(embed_dim, embed_dim * 2),
                            nn.GELU(),
                            nn.Linear(embed_dim * 2, patch_size)
                                    )
        # self.head = nn.Linear(embed_dim, patch_size)
        self.patch_size = patch_size

    def unpatchify(self, patches):
        B, n_patches, p = patches.shape
        C = 1
        L = n_patches * p
        return patches.reshape(B, n_patches, C, p).permute(0, 2, 1, 3).reshape(B, C, L)

    def forward(self, x):
        patches = self.patch_embed(x) + self.pos_embed
        for blk in self.transformer_blocks:
            patches = blk(patches)
        # pred_patches = self.head(patches)
        pred_patches = self.decoder(patches)
        return self.unpatchify(pred_patches)

# =====================================================================================
# 2. 辅助函数 (Utilities)
# =====================================================================================
def spectra_correction(original_spectra, denoised_spectra):
    corrected_results = []
    
    # 遍历批次中的每一行 (即每一条光谱)
    for i in range(original_spectra.shape[0]):
        raw_spec = original_spectra[i]      # 得到1D原始光谱
        denoised_spec = denoised_spectra[i]  # 得到1D去噪光谱
        
        # --- 以下是您提供的单谱处理逻辑 ---
        A = np.vstack([denoised_spec, np.ones(len(denoised_spec))]).T
        a, b = la.lstsq(A, raw_spec, rcond=None)[0]
        corrected_spec = a * denoised_spec + b
        mean_shift = np.mean(raw_spec) - np.mean(corrected_spec)
        final_spec = corrected_spec + mean_shift
        # --- 原始逻辑结束 ---
        
        corrected_results.append(final_spec)
    
    # 将校正后的光谱列表重新堆叠成一个2D NumPy数组
    return np.array(corrected_results)


# =====================================================================================
# 3. f2p单谱去噪处理函数
# =====================================================================================
def load_model(model_path='/media/ramancloud/api/denoising/model_pt/F2P_ps16_dp8_mr0.25.pth'):
    spectrum_length = 1600
    patch_size = 16
    embed_dim = 256
    depth = 8
    heads = 8
    device = torch.device("cpu")

    model = SpecTransformer(spectrum_length, patch_size, embed_dim, depth, heads)
    state_dict = torch.load(model_path, map_location=device)
    if any(key.startswith("module.") for key in state_dict.keys()):
        state_dict = {key.replace("module.", ""): value for key, value in state_dict.items()}
    model.load_state_dict(state_dict)
    model.to(device).eval()
    print("F2P model loaded successfully.")
    return model, device


def f2p_process(spectra, model, device, target_length=1600, max_batch_size=1024):  # 
    model.eval()

    is_single_input = isinstance(spectra, np.ndarray) and spectra.ndim == 1
    if is_single_input:
        spectra = [spectra]

    if not spectra:
        return np.array([])

    num_spectra = len(spectra)
    processed_chunks = []

    for i in range(0, num_spectra, max_batch_size):
        chunk_list = spectra[i : i + max_batch_size]
        chunk = np.asarray(chunk_list, dtype=np.float32)
        
        original_length = chunk.shape[1]
        processing_mode = 'none'
        pad_left = 0
        
        if original_length > target_length:
            processing_mode = 'resample'
            print(f"光谱长度 ({original_length}) > 目标长度 ({target_length})，将使用 resample 进行降采样。")
            spectra_processed = spectra_resample(chunk, target_length)
            # spectra_processed = resample(chunk, target_length, axis=1)
        elif original_length < target_length:
            processing_mode = 'resample'
            print(f"光谱长度 ({original_length}) > 目标长度 ({target_length})，将使用 resample 进行降采样。")
            spectra_processed = spectra_resample(chunk, target_length)
            # processing_mode = 'pad'
            # total_padding = target_length - original_length
            # pad_left = total_padding // 2
            # pad_right = total_padding - pad_left
            # padding_width = ((0, 0), (pad_left, pad_right))
            # spectra_processed = np.pad(chunk, padding_width, mode='edge')
        else:
            spectra_processed = chunk.copy()

        min_vals = np.min(spectra_processed, axis=1, keepdims=True)
        max_vals = np.max(spectra_processed, axis=1, keepdims=True)
        ranges = max_vals - min_vals + 1e-8
        spectra_norm = (spectra_processed - min_vals) / ranges
        
        input_tensor = torch.from_numpy(spectra_norm).unsqueeze(1).to(device, dtype=torch.float32)
        
        with torch.no_grad():
            denoised_norm_tensor = model(input_tensor)

        denoised_norm = denoised_norm_tensor.squeeze(1).cpu().numpy()
        denoised_extended = denoised_norm * ranges + min_vals
        
        if processing_mode == 'resample':
            denoised_final_chunk = spectra_resample(denoised_extended, original_length)
        elif processing_mode == 'pad':
            crop_end = pad_left + original_length
            denoised_final_chunk = denoised_extended[:, pad_left:crop_end]
        else:
            denoised_final_chunk = denoised_extended

        denoised_corrected = spectra_correction(chunk, denoised_final_chunk)
        final_chunk_result = np.round(denoised_corrected, 6)
        processed_chunks.append(final_chunk_result)

    final_result = np.concatenate(processed_chunks, axis=0)

    return final_result[0] if is_single_input else final_result