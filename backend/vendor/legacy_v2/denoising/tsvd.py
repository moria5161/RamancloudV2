import os

import numpy as np


def tsvd(matrix, threshold):
    if os.environ.get('RAMANCLOUD_LEGACY_DEVICE') == 'cuda':
        import torch

        factors = torch.linalg.svd(torch.as_tensor(matrix, device='cuda'), full_matrices=False, driver='gesvd')
        u, s, vh = (factor.cpu().numpy() for factor in factors)
    else:
        u, s, vh = np.linalg.svd(matrix, full_matrices=False)
    mask = np.ones(len(s), dtype=bool)
    # Filter by the curvature of log1p singular values, not a relative-rank cutoff.
    mask[1:-1] = np.abs(np.diff(np.log1p(s), n=2)) > threshold
    return (u * np.where(mask, s, 0)) @ vh
