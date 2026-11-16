import numpy as np
from pybaselines import Baseline


def imodpoly(y, poly_order):
    fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    baseline, _ = fitter.imodpoly(y, poly_order=poly_order)
    return y - baseline, baseline
