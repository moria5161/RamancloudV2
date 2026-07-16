import os
import numpy as np
import pandas as pd
import time
import uuid

import math

import numpy as np


def basic_smooth(n, c, arry):
    def gen_sg_coefficient(m, s, n):
        if n == 2:
            molecular = 3 * (3 * m**2 + 3 * m - 1 - 5 * s**2)
            denominator = (2 * m + 3) * (2 * m + 1) * (2 * m - 1)
        elif n == 4 or n == 5:
            molecular = (15 * m**4 + 30 * m**3 - 35 * m**2 - 50 *
                         m + 12) - 35 * (2 * m**2 + 2 * m - 3) * s**2 + 63 * s**4
            denominator = (2 * m + 5) * (2 * m + 3) * \
                (2 * m + 1) * (2 * m - 1) * (2 * m - 3)
            molecular *= 15
            molecular /= 4
        else:
            return 0
        return molecular / denominator

    def move_average(arry, weight):
        n = len(arry)
        k = len(weight)
        m = (k - 1) // 2
        len_arry = len(arry)
        smoothed_values = np.zeros(len_arry)
        orign = arry.copy()

        for i in range(n):
            if i <= m - 1:
                lx = 0
                ly = i + m
            elif i >= n - m:
                lx = i - m
                ly = n
            else:
                lx = i - m
                ly = i + m
            sum_y = 0
            if i <= m - 1:
                for j in range(m - i):
                    sum_y += orign[0] * weight[j]
            elif i >= n - m:
                for j in range(m - n + i + 1):
                    sum_y += orign[n - 1] * weight[n - i + j + m]
            for j in range(lx, ly):
                sum_y += orign[j] * weight[j - i + m]
            smoothed_values[i] = sum_y
        return smoothed_values

    m = (c - 1) // 2
    weights = np.array([gen_sg_coefficient(m, i, n) for i in range(-m, m + 1)])
    arry = np.array(arry)
    smoothed_values = move_average(arry, weights)
    return smoothed_values.tolist()


def noise_removal(arry):
    return basic_smooth(5, 100, arry)


def get_mbk(linear_data, cum, pl, pr):
    for i in range(pl, pr+1):
        linear_data[i] += cum[i]


def cumsum(arry, pl, pr):
    cum = [0]*len(arry)
    temp = 0
    for i in range(pl, pr+1):
        temp += arry[i]
        cum[i] = temp
    return cum


def Cal_mean(pl, pr, arry):
    temp = 0
    for i in range(pl, pr+1):
        temp += arry[i]
    return temp / (pr - pl + 1)


def diffline(arry, pl, pr):
    mean = Cal_mean(pl, pr, arry)
    diff = [0]*len(arry)
    for i in range(pl, pr+1):
        diff[i] = arry[i] - mean
    return diff


def linear(data, a, index):
    return a * index + data


def adjust(peaks, regions, background, peak_sum, Ln):
    i = 0
    while i < peak_sum:
        if (regions[i][1] - regions[i][0]) < Ln:
            if i < peak_sum - 1:
                for j in range(i, peak_sum-1):
                    regions[j] = regions[j+1]
                    peaks[j] = peaks[j+1]
            peak_sum -= 1
        i += 1

    for i in range(peak_sum):
        min_val = 0
        min_x = 0
        a = (background[regions[i][1]]-background[regions[i][0]]
             )/(regions[i][1] - regions[i][0])
        for j in range(regions[i][0], regions[i][1]+1):
            pline = linear(background[regions[i][0]], a, j-regions[i][0])
            if (background[j] - pline) < min_val:
                min_val = background[j] - pline
                min_x = j
            if min_val < 0 and j == peaks[i]:
                regions[i][0] = min_x
                min_val = 0
                min_x = 0
        if min_val < 0:
            regions[i][1] = min_x

    i = 0
    while i < peak_sum:
        if (regions[i][1] - regions[i][0]) < Ln:
            if i < peak_sum - 1:
                for j in range(i, peak_sum-1):
                    regions[j] = regions[j+1]
                    peaks[j] = peaks[j+1]
            peak_sum -= 1
        i += 1
    return peak_sum


def snds(ds, Lb):
    temp1 = basic_smooth(2, Lb, ds)
    temp2 = basic_smooth(2, Lb, temp1)
    ds_3 = basic_smooth(2, Lb, temp2)
    return ds_3


def derivative(data):
    deriva = [0]*len(data)
    for i in range(1, len(data)):
        deriva[i] = data[i] - data[i-1]
    deriva[0] = deriva[1]
    return deriva


def dg(background, Ln, Lb):
    data = basic_smooth(2, Ln, background)
    deriva = derivative(data)
    ds = basic_smooth(2, Ln, deriva)
    ds_3 = snds(ds, Lb)
    dgs = np.array(ds) - np.array(ds_3)
    return dgs


def peak_region(background, Ln, Lb):
    lens = len(background)
    dgs = dg(background, Ln, Lb)

    peaks = np.where(np.diff(np.sign(dgs)) < 0)[0] + 1
    
    if len(peaks) == 0:
        return np.array([]), [], []

    regions = np.zeros((len(peaks), 2), dtype=int).tolist()
    
    for p in range(len(peaks)):
        i = peaks[p] - 1
        while i > 0 and dgs[i - 1] >= 0:
            i -= 1
        regions[p][0] = i

        i = peaks[p] + 1
        while i < lens - 1 and dgs[i + 1] <= 0:
            i += 1
        if i == lens - 1:
            regions[p][1] = i
        else:
            regions[p][1] = i + 1

    peak_sum = adjust(peaks, regions, background, len(peaks), Ln)
    
    final_peaks = peaks[:peak_sum]
    final_regions = regions[:peak_sum]
    
    is_smoothed = [1 if abs(dgs[p - 1] - dgs[p]) < 0.01 else 0 for p in final_peaks]

    return final_peaks, final_regions, is_smoothed


def get_background(regions, is_smoothed, smoothed_values,  show, peak_sum, Ln, Lb):
    temp1 = basic_smooth(2, Ln, smoothed_values)
    temp2 = derivative(temp1)
    temp1 = basic_smooth(2, Ln, temp2)
    s3ds = snds(temp1, Lb)
    for i in range(peak_sum):
        if is_smoothed[i] == 0:
            a = (smoothed_values[regions[i][1]] -
                 smoothed_values[regions[i][0]])/(regions[i][1] - regions[i][0])
            for j in range(regions[i][0], regions[i][1]+1):
                smoothed_values[j] = linear(
                    smoothed_values[regions[i][0]], a, j-regions[i][0])
    if show:
        for i in range(peak_sum):
            diff = diffline(s3ds, regions[i][0], regions[i][1])
            cum = cumsum(diff, regions[i][0], regions[i][1])
            get_mbk(smoothed_values, cum, regions[i][0], regions[i][1])


def repeat(smoothed_values, Ln, Lb):
    background = list(smoothed_values)
    i = 0
    sig = 0

    while not sig:
        peaks, regions, is_smoothed = peak_region(background, Ln, Lb)
        i += 1
        if i > 5:
            sig = 1
        else:
            flag = all(is_smoothed)
            if flag:
                sig = 1
        get_background(regions, is_smoothed, background, sig, len(peaks), Ln, Lb)
    return background


def aabs(wave, y, Ln=6, Lb=140):
    if type(y) != np.ndarray:
        y = np.array(y)
    res_y = y.copy()
    smoothed_values = noise_removal(res_y)
    background = repeat(smoothed_values, Ln, Lb)
    background_smooth = basic_smooth(5, Lb, background)
    res_y -= background_smooth
    return  res_y
