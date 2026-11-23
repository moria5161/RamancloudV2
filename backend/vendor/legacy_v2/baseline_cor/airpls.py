import numpy as np
from pybaselines import Baseline


def airpls(y, lam, diff_order):
    fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    baseline, _ = fitter.airpls(y, lam=lam, diff_order=diff_order)
    return y - baseline, baseline
