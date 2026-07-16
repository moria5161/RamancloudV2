import numpy as np
from typing import Tuple, Union
import torch

class SVDD:
    def __init__(self, threshold: float = 0.0001, random_state: int = 1):
        """Initialize the SVDD denoiser with second derivative threshold and random seed"""
        self.threshold = threshold
        self.random_state = random_state
        
    def _reshape_to_matrix(self, data: np.ndarray) -> torch.Tensor:
        """Convert input to torch tensor (no reshape needed)"""
        return torch.from_numpy(data)
    
    def _apply_svd(self, matrix: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Perform SVD decomposition on the matrix"""
        U, S, Vh = torch.linalg.svd(matrix, full_matrices=False)
        return U, S, Vh
    
    def _threshold_singular_values(self, S: torch.Tensor) -> torch.Tensor:
        """Log-transform and threshold each row of singular values"""
        log_S = torch.log1p(S)

        diff1 = torch.diff(log_S)
        diff2 = torch.diff(diff1)

        mask = torch.ones_like(S, dtype=torch.bool)
        mask[1:-1] = torch.abs(diff2) > self.threshold

        S_filtered = S.clone()
        S_filtered[~mask] = 0
        return S_filtered
    
    def denoise(self, data: np.ndarray) -> np.ndarray:
        """Apply denoising to 2D spectral data (batch × spectrum_length)"""
        matrix = self._reshape_to_matrix(data)
        U, S, Vh = self._apply_svd(matrix)
        S_filtered = self._threshold_singular_values(S)
        reconstructed_matrix = U @ torch.diag(S_filtered) @ Vh
        return reconstructed_matrix.cpu().numpy()

def tsvd(data: np.ndarray, threshold: float = 0.001, random_state: int = 1) -> np.ndarray:
    denoiser = SVDD(threshold=threshold, random_state=random_state)
    return denoiser.denoise(data)
