# -*- coding: utf-8 -*-
"""
Cosmic ray (spike/ghost peak) removal for Raman spectra.

Implements a four-step method:
1. Peak finding - detect peaks by comparing with neighbors
2. Cosmic ray identification - identify by narrow FWHM
3. Cosmic ray marking - mark positions and ranges
4. Spectrum correction - interpolate to replace cosmic ray data

宇宙射线在拉曼光谱谱图中表现为随机分布的强且峰宽极窄的信号，
其出峰位置随光栅位置而变，因此常常被称为鬼峰。
"""

import numpy as np
from scipy.interpolate import interp1d
from typing import Optional, Tuple, List, Dict, Any

# -------------------------------------------------------------
# 全局默认参数配置
# -------------------------------------------------------------
DEFAULT_FWHM_THRESHOLD = 4.0      # 默认半峰宽阈值
DEFAULT_THRESHOLD = None          # 默认峰检测阈值配置


def find_peaks(spectrum: np.ndarray, threshold: Optional[float] = None) -> List[Tuple[int, str]]:
    """
    Find peaks in spectrum by comparing each point with its neighbors.
    
    寻峰：比较每个数据点与其相邻数据点间的数值差异，
    根据所设定的阈值确定谱峰位置。支持正峰（max）和倒峰（min）。
    
    Args:
        spectrum: 1D array of intensity values
        threshold: minimum difference between peak and neighbors
                   If None, automatically calculated as:
                   mean + 3 * std of local differences
    
    Returns:
        List of tuples (peak_idx, peak_type) where peak_type is 'max' or 'min'
    """
    spectrum = np.asarray(spectrum, dtype=np.float64)
    n = len(spectrum)
    
    if n < 3:
        return []
    
    # Calculate local differences
    # A peak should be higher than both its left and right neighbors
    peaks = []
    
    # Calculate first derivative
    diff = np.diff(spectrum)
    
    # Find local maxima and minima: sign change in derivative
    for i in range(len(diff) - 1):
        if diff[i] > 0 and diff[i + 1] < 0:
            peaks.append((i + 1, 'max'))
        elif diff[i] < 0 and diff[i + 1] > 0:
            peaks.append((i + 1, 'min'))
    
    if not peaks:
        return []
    
    # Calculate peak heights (difference from neighbors)
    peak_heights = []
    for idx, ptype in peaks:
        if ptype == 'max':
            # Local maximum: compare with local minima on both sides
            left_min = spectrum[idx]
            right_min = spectrum[idx]
            
            # Search left for local minimum
            for j in range(idx - 1, max(0, idx - 10), -1):
                if spectrum[j] < left_min:
                    left_min = spectrum[j]
                if j > 0 and spectrum[j] < spectrum[j - 1]:
                    break
            
            # Search right for local minimum
            for j in range(idx + 1, min(n, idx + 10)):
                if spectrum[j] < right_min:
                    right_min = spectrum[j]
                if j < n - 1 and spectrum[j] < spectrum[j + 1]:
                    break
            
            height = min(spectrum[idx] - left_min, spectrum[idx] - right_min)
            peak_heights.append((idx, height, ptype))
            
        else:
            # Local minimum: compare with local maxima on both sides
            left_max = spectrum[idx]
            right_max = spectrum[idx]
            
            # Search left for local maximum
            for j in range(idx - 1, max(0, idx - 10), -1):
                if spectrum[j] > left_max:
                    left_max = spectrum[j]
                if j > 0 and spectrum[j] > spectrum[j - 1]:
                    break
                    
            # Search right for local maximum
            for j in range(idx + 1, min(n, idx + 10)):
                if spectrum[j] > right_max:
                    right_max = spectrum[j]
                if j < n - 1 and spectrum[j] > spectrum[j + 1]:
                    break
                    
            height = min(left_max - spectrum[idx], right_max - spectrum[idx])
            peak_heights.append((idx, height, ptype))
    
    if not peak_heights:
        return []
        
    heights_array = np.array([h for _, h, _ in peak_heights])
    
    # 1. 计算全局平缓区域的基础阈值 (挡掉大部分毫无意义的微小波动)
    if threshold is None:
        median_height = np.median(heights_array)
        mad = np.median(np.abs(heights_array - median_height))
        # 倍数可以低一点，作为最基础的全局初筛门槛
        global_threshold = median_height + 5 * mad if mad > 0 else median_height
    else:
        global_threshold = threshold
        
    valid_peaks = []
    
    # 2. 逐一检查每个候选峰是否在其【局部】环境中真正的鹤立鸡群
    for idx, height, ptype in peak_heights:
        # 必须先过得了全局基础分界线
        if height < global_threshold:
            continue
            
        # === 核心改进：计算局部动态噪声 ===
        # 提取前后各 50 个数据点作为局部观测窗口
        window_size = 50
        start_idx = max(0, idx - window_size)
        end_idx = min(n, idx + window_size)
        local_window = spectrum[start_idx:end_idx]
        
        if len(local_window) < 5:
            valid_peaks.append(idx)
            continue
            
        # 用局部一阶差分的【绝对值中位数】评估该区域真正的噪音背景水平
        # 优势：中位数极其抗干扰！真正的鬼峰数值哪怕上万，也只影响两三个差分点，绝不会拉高局部中位数
        local_diffs = np.abs(np.diff(local_window))
        local_noise = np.median(local_diffs)
        
        # 如果局部过于平滑导致中位数为 0，退一步用局部均差
        if local_noise == 0:
            local_noise = np.mean(local_diffs)
            
        # ★ 动态智能门槛：该凸起的绝对高度，必须至少大于等于当前局部基础噪声的 8 倍
        # (普通密集锯齿噪声通常只有局部中位噪声的 2~4 倍；而真实鬼峰通常是局部噪声的 20 倍以上)
        if height > 8 * local_noise:
            valid_peaks.append((idx, ptype))
            
    return valid_peaks


def calculate_fwhm(spectrum: np.ndarray, peak_idx: int, ptype: str = 'max') -> Tuple[float, int, int]:
    """
    Calculate Full Width at Half Maximum (FWHM) for a peak.
    
    计算半高宽：测量峰在半高处的宽度。
    
    Args:
        spectrum: 1D array of intensity values
        peak_idx: index of the peak position
        ptype: 'max' for positive peaks, 'min' for negative (inverted) peaks
    
    Returns:
        Tuple of (fwhm_value, left_idx, right_idx)
        - fwhm_value: FWHM in number of data points
        - left_idx: left boundary index at half maximum
        - right_idx: right boundary index at half maximum
    """
    spectrum = np.asarray(spectrum, dtype=np.float64)
    n = len(spectrum)
    
    if peak_idx < 0 or peak_idx >= n:
        return 0.0, peak_idx, peak_idx
    
    peak_value = spectrum[peak_idx]
    
    # Estimate baseline as the minimum value in the spectrum
    # For cosmic rays, we want to measure the width at half the peak height
     # 获取局部窗口内的最小值作为基线，而不是全局
    window_size = 50
    start_idx = max(0, peak_idx - window_size)
    end_idx = min(len(spectrum), peak_idx + window_size)
    
    if ptype == 'max':
        baseline = np.min(spectrum[start_idx:end_idx])
    else:
        baseline = np.max(spectrum[start_idx:end_idx])
    
    # Half maximum level (halfway between baseline and peak)
    half_max = baseline + (peak_value - baseline) / 2
    
    # Find left half-max position
    left_idx = peak_idx
    for i in range(peak_idx - 1, -1, -1):
        if (ptype == 'max' and spectrum[i] <= half_max) or (ptype == 'min' and spectrum[i] >= half_max):
            # Linear interpolation for more accurate position
            if spectrum[i + 1] != spectrum[i]:
                frac = (half_max - spectrum[i]) / (spectrum[i + 1] - spectrum[i])
                left_idx = i + frac
            else:
                left_idx = i
            break
    
    # If we didn't find half-max on left, use edge
    if left_idx == peak_idx:
        left_idx = 0
    
    # Find right half-max position
    right_idx = peak_idx
    for i in range(peak_idx + 1, n):
        if (ptype == 'max' and spectrum[i] <= half_max) or (ptype == 'min' and spectrum[i] >= half_max):
            # Linear interpolation for more accurate position
            if spectrum[i - 1] != spectrum[i]:
                frac = (half_max - spectrum[i]) / (spectrum[i - 1] - spectrum[i])
                right_idx = i - frac
            else:
                right_idx = i
            break
    
    # If we didn't find half-max on right, use edge
    if right_idx == peak_idx:
        right_idx = n - 1
    
    fwhm = right_idx - left_idx
    
    return fwhm, int(left_idx), int(right_idx)


def identify_cosmic_rays(
    spectrum: np.ndarray,
    threshold: Optional[float] = DEFAULT_THRESHOLD,
    fwhm_threshold: float = DEFAULT_FWHM_THRESHOLD,
    intensity_threshold: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Identify cosmic rays (ghost peaks) based on narrow FWHM and high intensity.
    
    鬼峰判断：将半高宽小于设定阈值的谱峰定为鬼峰。
    
    Args:
        spectrum: 1D array of intensity values
        threshold: peak detection threshold (auto-calculated if None)
        fwhm_threshold: maximum FWHM for cosmic ray identification (default 4 points)
        intensity_threshold: minimum intensity for cosmic ray (optional)
    
    Returns:
        List of dicts with cosmic ray information:
        - 'peak_idx': peak position
        - 'fwhm': full width at half maximum
        - 'left_idx': left boundary
        - 'right_idx': right boundary
        - 'intensity': peak intensity
    """
    spectrum = np.asarray(spectrum, dtype=np.float64)
    
    # Find all peaks
    peaks = find_peaks(spectrum, threshold)
    
    if not peaks:
        return []
    
    cosmic_rays = []
    
    for peak_idx, ptype in peaks:
        fwhm, left_idx, right_idx = calculate_fwhm(spectrum, peak_idx, ptype)
        
        # Check FWHM criterion
        if fwhm <= fwhm_threshold:
            # Additional intensity check if specified
            if intensity_threshold is not None:
                if ptype == 'max' and spectrum[peak_idx] < intensity_threshold:
                    continue
                elif ptype == 'min' and spectrum[peak_idx] > intensity_threshold:
                    continue
            
            # Calculate spike width (region affected by cosmic ray)
            # Typically extends a bit beyond FWHM boundaries
            spike_width = max(1, int(np.ceil(fwhm)))
            left_bound = max(0, peak_idx - spike_width)
            right_bound = min(len(spectrum) - 1, peak_idx + spike_width)
            
            cosmic_rays.append({
                'peak_idx': peak_idx,
                'ptype': ptype,
                'fwhm': fwhm,
                'left_idx': left_bound,
                'right_idx': right_bound,
                'intensity': spectrum[peak_idx],
            })
    
    return cosmic_rays


def remove_cosmic_rays(
    spectrum: np.ndarray,
    cosmic_rays: List[Dict[str, Any]],
    method: str = 'linear'
) -> np.ndarray:
    """
    Remove cosmic rays by interpolation.
    
    光谱校正：根据鬼峰周边数据点的数值波动信息，
    利用插值方法生成新数值以替代鬼峰范围内的原有数据。
    
    Args:
        spectrum: 1D array of intensity values
        cosmic_rays: list of cosmic ray info dicts from identify_cosmic_rays()
        method: interpolation method - 'linear', 'quadratic', 'cubic', or 'spline'
    
    Returns:
        Corrected spectrum with cosmic rays removed
    """
    spectrum = np.asarray(spectrum, dtype=np.float64)
    corrected = spectrum.copy()
    
    if not cosmic_rays:
        return corrected
    
    # Sort cosmic rays by position (process from left to right)
    sorted_rays = sorted(cosmic_rays, key=lambda x: x['peak_idx'])
    
    # Merge overlapping cosmic ray regions
    merged_regions = []
    for ray in sorted_rays:
        left = ray['left_idx']
        right = ray['right_idx']
        
        if merged_regions and left <= merged_regions[-1][1] + 1:
            # Merge with previous region
            merged_regions[-1] = (merged_regions[-1][0], max(merged_regions[-1][1], right))
        else:
            merged_regions.append((left, right))
    
    # Interpolate each merged region
    for left_idx, right_idx in merged_regions:
        # Extend boundaries to get good interpolation anchor points
        margin = max(3, int((right_idx - left_idx) * 1.5))
        
        interp_left = max(0, left_idx - margin)
        interp_right = min(len(spectrum) - 1, right_idx + margin)
        
        # Create interpolation points (excluding the cosmic ray region)
        x_points = []
        y_points = []
        
        for i in range(interp_left, left_idx):
            x_points.append(i)
            y_points.append(spectrum[i])
        
        for i in range(right_idx + 1, interp_right + 1):
            x_points.append(i)
            y_points.append(spectrum[i])
        
        if len(x_points) < 2:
            # Not enough points for interpolation, use simple average
            avg = np.mean([spectrum[interp_left], spectrum[interp_right]])
            corrected[left_idx:right_idx + 1] = avg
            continue
        
        x_points = np.array(x_points)
        y_points = np.array(y_points)
        
        # Choose interpolation method
        if method == 'linear':
            kind = 'linear'
        elif method == 'quadratic':
            kind = 'quadratic'
        elif method == 'cubic' or method == 'spline':
            kind = 'cubic'
        else:
            kind = 'linear'
        
        # Need at least (order + 1) points for interpolation
        min_points = {'linear': 2, 'quadratic': 3, 'cubic': 4}
        if len(x_points) < min_points.get(kind, 2):
            kind = 'linear'
        
        try:
            # Create interpolation function
            interp_func = interp1d(x_points, y_points, kind=kind, fill_value='extrapolate')
            
            # Interpolate the cosmic ray region
            x_interp = np.arange(left_idx, right_idx + 1)
            corrected[left_idx:right_idx + 1] = interp_func(x_interp)
        except Exception:
            # Fallback to linear interpolation
            interp_func = interp1d(x_points, y_points, kind='linear', fill_value='extrapolate')
            x_interp = np.arange(left_idx, right_idx + 1)
            corrected[left_idx:right_idx + 1] = interp_func(x_interp)
    
    return corrected


def despike_spectrum(
    spectrum: np.ndarray,
    threshold: Optional[float] = DEFAULT_THRESHOLD,
    fwhm_threshold: float = DEFAULT_FWHM_THRESHOLD,
    interpolation: str = 'linear',
    return_info: bool = False
) -> Any:
    """
    Main function: Remove cosmic rays (ghost peaks) from Raman spectrum.
    
    一站式去鬼峰处理，包含寻峰、鬼峰判断、鬼峰标记和光谱校正四个步骤。
    
    Args:
        spectrum: 1D array of intensity values
        threshold: peak detection threshold (auto-calculated if None)
        fwhm_threshold: maximum FWHM for cosmic ray (default 2.5 points)
        interpolation: interpolation method - 'linear', 'quadratic', 'cubic'
        return_info: if True, return detailed information dict
    
    Returns:
        If return_info is False:
            corrected_spectrum (np.ndarray)
        If return_info is True:
            dict with keys:
            - 'corrected_spectrum': corrected spectrum
            - 'cosmic_rays': list of cosmic ray info
            - 'num_cosmic_rays': number of cosmic rays detected
            - 'processing_time': processing time in seconds
    """
    import time
    
    start_time = time.time()
    
    spectrum = np.asarray(spectrum, dtype=np.float64)
    
    # Step 1 & 2: Find and identify cosmic rays
    cosmic_rays = identify_cosmic_rays(spectrum, threshold, fwhm_threshold)
    
    # Step 3: Mark cosmic rays (already done in identify_cosmic_rays)
    
    # Step 4: Remove cosmic rays by interpolation
    corrected = remove_cosmic_rays(spectrum, cosmic_rays, interpolation)
    
    processing_time = time.time() - start_time
    
    if return_info:
        return {
            'corrected_spectrum': corrected,
            'cosmic_rays': cosmic_rays,
            'num_cosmic_rays': len(cosmic_rays),
            'processing_time': processing_time,
        }
    
    return corrected


def despike_spectrum_multi(
    spectra: np.ndarray,
    threshold: Optional[float] = DEFAULT_THRESHOLD,
    fwhm_threshold: float = DEFAULT_FWHM_THRESHOLD,
    interpolation: str = 'linear'
) -> Tuple[np.ndarray, List[Dict]]:
    """
    Remove cosmic rays from multiple spectra.
    
    批量处理多个光谱的去鬼峰。
    
    Args:
        spectra: 2D array of shape (n_spectra, n_points) or 1D array for single spectrum
        threshold: peak detection threshold (auto-calculated if None)
        fwhm_threshold: maximum FWHM for cosmic ray
        interpolation: interpolation method
    
    Returns:
        Tuple of (corrected_spectra, info_list)
    """
    spectra = np.asarray(spectra, dtype=np.float64)
    
    # Handle single spectrum
    if spectra.ndim == 1:
        result = despike_spectrum(spectra, threshold, fwhm_threshold, interpolation, return_info=True)
        return result['corrected_spectrum'], [result]
    
    corrected_spectra = []
    info_list = []
    
    for spectrum in spectra:
        result = despike_spectrum(spectrum, threshold, fwhm_threshold, interpolation, return_info=True)
        corrected_spectra.append(result['corrected_spectrum'])
        info_list.append(result)
    
    return np.array(corrected_spectra), info_list