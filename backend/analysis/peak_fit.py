from scipy.optimize import curve_fit
from scipy.special import wofz
from scipy.signal import find_peaks
import numpy as np
from functools import partial
from concurrent.futures import ProcessPoolExecutor


def Voigt(x, x0, A, sigma, gamma):
    z = ((x - x0) + 1j*gamma) / (sigma * np.sqrt(2))
    return A * np.real(wofz(z)) / (sigma * np.sqrt(2*np.pi))

def fit_voigt_peak(spectrum, wavenumbers, search_range, prominence_threshold=0.01, left_offset=5, right_offset=30):
    nan_return = (np.nan, np.nan, np.nan, np.nan, (np.nan,)*4)
    
    mask = (wavenumbers >= search_range[0]) & (wavenumbers <= search_range[1])
    if not np.any(mask): 
        return nan_return

    x_roi, y_roi = wavenumbers[mask], spectrum[mask]

    peak_indices, properties = find_peaks(y_roi, prominence=prominence_threshold)
    
    if peak_indices.size == 0:
        return nan_return

    most_prominent_idx_of_peaks = np.argmax(properties['prominences'])
    peak_idx_in_roi = peak_indices[most_prominent_idx_of_peaks]
    
    peak_center_wavenumber = x_roi[peak_idx_in_roi]
    peak_idx_global = np.where(wavenumbers == peak_center_wavenumber)[0][0]
    init_amplitude_guess = y_roi[peak_idx_in_roi]

    fit_start_idx = max(0, peak_idx_global - left_offset)
    fit_end_idx = min(len(wavenumbers), peak_idx_global + right_offset)
    x_fit, y_fit = wavenumbers[fit_start_idx:fit_end_idx], spectrum[fit_start_idx:fit_end_idx]

    p0 = [peak_center_wavenumber, init_amplitude_guess * 10, 5.0, 5.0] 
    bounds = ([peak_center_wavenumber - 15, 0, 0.1, 0.1], [peak_center_wavenumber + 15, np.inf, 30, 30])

    try:
        fit_params, _ = curve_fit(Voigt, x_fit, y_fit, p0=p0, bounds=bounds, maxfev=5000)
    except (RuntimeError, ValueError):
        return nan_return
        
    x0, A, sigma, gamma = fit_params
    if not (search_range[0] <= x0 <= search_range[1]):
        return nan_return
        
    peak_amplitude = Voigt(x0, *fit_params)
    peak_center = x0
    fwhm = 0.5346 * (2 * gamma) + np.sqrt(0.2166 * (2 * gamma)**2 + (2.3548 * sigma)**2)
    peak_area = A

    return peak_center, peak_amplitude, fwhm, peak_area, fit_params

def filter_and_zero_results(results_list):
    filtered_results = []
    for res in results_list:
        if np.isnan(res[0]):
            filtered_results.append([0.0, 0.0, 0.0, 0.0])
        else:
            filtered_results.append(res[:4])
    return np.array(filtered_results)


### new

def _perform_voigt_fitting(data):
    required_keys = ['waves', 'x', 'y', 'spectra', 'search_range', 'prominence_threshold']
    if not data or not all(key in data for key in required_keys):
        return None, None, None, 'Missing required data keys or empty data.'

    waves = np.array(data['waves'])
    spectra = np.array(data['spectra'])
    x = np.array(data['x'])
    y = np.array(data['y'])
    
    h, w = len(x), len(y)
    if h * w != spectra.shape[0]:
        return None, None, None, f'Data dimensions mismatch: {h}x{w} != {spectra.shape[0]}.'

    fit_function = partial(
        fit_voigt_peak, 
        wavenumbers=waves, 
        search_range=data['search_range'],
        prominence_threshold=data['prominence_threshold'],
        left_offset=data.get('left_offset', 5),
        right_offset=data.get('right_offset', 30)
    )
    
    with ProcessPoolExecutor() as executor:
        results_list = list(executor.map(fit_function, spectra))
        
    return waves, (h, w), results_list, None

def calculate_reconstructed_spectra(wavenumbers, results_list, shape):
    h, w = shape
    fit_params = np.array([res[4] for res in results_list])
    
    nan_mask = np.isnan(fit_params[:, 0])
    safe_params = fit_params.copy()
    safe_params[nan_mask] = [wavenumbers[0], 0, 1.0, 1.0]
    
    x_grid = wavenumbers[np.newaxis, :]
    x0 = safe_params[:, 0, np.newaxis]
    A = safe_params[:, 1, np.newaxis]
    sigma = safe_params[:, 2, np.newaxis]
    gamma = safe_params[:, 3, np.newaxis]
    
    z = ((x_grid - x0) + 1j * gamma) / (sigma * np.sqrt(2))
    y_calc = A * np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi))
    
    y_calc[nan_mask, :] = 0.0
    return y_calc.reshape(h, w, len(wavenumbers))