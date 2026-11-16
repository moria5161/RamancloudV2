import numpy as np
from pybaselines import Baseline


def snip(y, max_half_window, smooth_half_window):
    if max_half_window > (len(y) - 1) // 2:
        raise ValueError('SNIP maximum half window exceeds half the spectral length')
    fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    baseline, _ = fitter.snip(y, max_half_window=max_half_window,
                            smooth_half_window=smooth_half_window, decreasing=True)
    return y - baseline, baseline
