from pybaselines import Baseline
import numpy as np


def imod_poly(y, poly_order=3):
    baseline_fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    bkg, _ = baseline_fitter.imodpoly(y, poly_order=poly_order)
    return y - bkg

def penalized_poly(y, poly_order=3):
    baseline_fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    bkg, _ = baseline_fitter.penalized_poly(y, poly_order=poly_order)
    return y - bkg


def airpls(y, lam=1e7, diff_order=3):
    baseline_fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    bkg, _ = baseline_fitter.airpls(y, lam=lam, diff_order=diff_order)
    return y - bkg


def aspls(y, lambda_=1e7, order_=3):
    baseline_fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    bkg, _ = baseline_fitter.aspls(y, lam=lambda_, diff_order=order_)
    return y - bkg


def mormol(y, half_window=40):
    baseline_fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    bkg, _ = baseline_fitter.mormol(y, half_window=half_window)
    return y - bkg


def rolling_ball(y, half_window=40):
    baseline_fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    bkg, _ = baseline_fitter.rolling_ball(y, half_window=half_window)
    return y - bkg


def irsqr(y, lam=50, quantile=0.05):
    baseline_fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    bkg, _ = baseline_fitter.irsqr(y, lam=lam, quantile=quantile)
    return y - bkg


def snip(y, max_half_window=20, smooth_half_window=7):
    baseline_fitter = Baseline(x_data=np.linspace(0, len(y), len(y)))
    bkg, _ = baseline_fitter.snip(y, max_half_window=max_half_window, decreasing=True, smooth_half_window=smooth_half_window)
    return y - bkg


