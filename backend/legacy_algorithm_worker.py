"""Private numeric worker. Only the server supplies its temporary directory."""
import json
import os
import sys
from pathlib import Path
import numpy as np
from vendor.legacy_v2.processing import denoise_batch, correct_baseline_batch

if __name__ == '__main__':
    directory = Path(sys.argv[1])
    request = json.loads((directory/'request.json').read_text(encoding='utf-8'))
    matrix = np.load(directory/'input.npy', allow_pickle=False)
    if os.environ.get('RAMANCLOUD_LEGACY_DEVICE') == 'cuda':
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('The configured hyperspectral CUDA runtime cannot access the GPU.')
    if request['kind'] == 'denoise':
        output = denoise_batch(matrix, request['params'], request['method'])
        np.savez(directory/'output.npz', corrected=output)
    else:
        output, baseline = correct_baseline_batch(matrix, request['params'], request['method'])
        np.savez(directory/'output.npz', corrected=output, baseline=baseline)
