import numpy as np
import pywt


def wtd(y, wavelet, level):
    maximum = pywt.dwt_max_level(len(y), pywt.Wavelet(wavelet).dec_len)
    if level > maximum:
        raise ValueError('WTD level exceeds the maximum {} for this spectrum and wavelet'.format(maximum))
    coeffs = pywt.wavedec(y, wavelet, level=level)
    threshold = 0.8 * np.sqrt(2 * np.log(len(y))) * np.median(np.abs(coeffs[-1])) / 0.6745
    coeffs = [c if i == 0 else pywt.threshold(c, threshold, mode='soft') for i, c in enumerate(coeffs)]
    return pywt.waverec(coeffs, wavelet)[:len(y)]
