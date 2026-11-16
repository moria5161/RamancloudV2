from scipy.signal import savgol_filter


def sg(y, window_size, order):
    if window_size % 2 != 1 or window_size > len(y) or order >= window_size:
        raise ValueError('SG window must be odd, no longer than the spectrum, and greater than polynomial order')
    return savgol_filter(y, window_size, order)
