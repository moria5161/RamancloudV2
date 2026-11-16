import numpy as np


def tsvd(matrix, threshold):
    u, s, vh = np.linalg.svd(matrix, full_matrices=False)
    mask = np.ones(len(s), dtype=bool)
    # Filter by the curvature of log1p singular values, not a relative-rank cutoff.
    mask[1:-1] = np.abs(np.diff(np.log1p(s), n=2)) > threshold
    return (u * np.where(mask, s, 0)) @ vh
