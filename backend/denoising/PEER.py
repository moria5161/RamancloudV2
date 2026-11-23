from __future__ import division
import numpy as np
import copy


def distance_Reciprocal(a, b):
    d_all = a**2 + b**2
    d = d_all**0.5
    d = 1 / d
    return d


def weight_result(data, c):
    m = (c - 1) // 2
    n = len(data)
    new_data = [0 for x in range(n)]
    for i in range(0, n):
        w_sum = 0
        if i <= m - 1:  # 左端不完整的几个点
            lx = 0
            ly = i + m
            p_sum = 0
            w_sum = w_sum + data[0] * (m - i)
            a = 0
            happens = [0 for x in range(ly - lx + 1)]
            for j in range(lx, ly + 1):
                w_sum = w_sum + data[j]
            avg = w_sum / c
            if avg in data[lx : ly + 1]:
                new_data[i] = avg
            else:
                for k in range(lx, ly + 1):
                    p_sum = p_sum + distance_Reciprocal(data[k], avg)
                for k in range(lx, ly + 1):
                    happens[a] = data[k] * (distance_Reciprocal(data[k], avg) / p_sum)
                    new_data[i] = new_data[i] + happens[a]
                    a = a + 1
        elif i >= n - m:  # 右端不完整的几个点
            lx = i - m
            ly = n - 1
            p_sum = 0
            w_sum = w_sum + data[n - 1] * (m - n + i)
            a = 0
            happens = [0 for x in range(ly - lx + 1)]
            for j in range(lx, ly + 1):
                w_sum = w_sum + data[j]
            avg = w_sum / c
            if avg in data[lx : ly + 1]:
                new_data[i] = avg
            else:
                for k in range(lx, ly + 1):
                    p_sum = p_sum + distance_Reciprocal(data[k], avg)
                for k in range(lx, ly + 1):
                    happens[a] = data[k] * (distance_Reciprocal(data[k], avg) / p_sum)
                    new_data[i] = new_data[i] + happens[a]
                    a = a + 1
        else:
            lx = i - m
            ly = i + m
            p_sum = 0
            happens = [0 for x in range(ly - lx + 1)]
            a = 0
            for j in range(lx, ly + 1):
                w_sum = w_sum + data[j]
            avg = w_sum / c
            if avg in data[lx : ly + 1]:
                new_data[i] = avg
            else:
                for k in range(lx, ly + 1):
                    p_sum = p_sum + distance_Reciprocal(data[k], avg)
                for k in range(lx, ly + 1):
                    happens[a] = data[k] * (distance_Reciprocal(data[k], avg) / p_sum)
                    new_data[i] = new_data[i] + happens[a]
                    a = a + 1
    return new_data


def derivative(data):
    data = weight_result(data, 3)  # 识别用窗口参数
    result = [data[i] - data[i - 1] for i in range(1, len(data))]
    result.insert(0, result[0])
    result2 = [result[i] - result[i - 1] for i in range(1, len(result))]
    return result, result2


def move_average(data, weight):
    k = len(weight)
    if k == 0:
        return data
    m = (k - 1) // 2
    orign = data
    n = len(orign)
    result = []
    for i in range(0, n):
        lx = 0
        ly = 0
        if i <= m - 1:  # 左端不完整的几个点
            lx = 0
            ly = i + m
        elif i >= n - m:  # 右端不完整的几个点
            lx = i - m
            ly = n
        else:
            lx = i - m
            ly = i + m
        sum_y = 0
        if i <= m - 1:
            for k in range(m - i):  # 左端缺少的点的补算
                sum_y += orign[0] * weight[k]
        elif i >= n - m:
            for k in range(m - n + i + 1):  # 右边缺少的点的补算
                sum_y += orign[n - 1] * weight[n - i + k + m]

        for j in range(lx, ly):
            sum_y += orign[j] * weight[j - i + m]
        average_y = sum_y
        result.append(average_y)
    return result


def find_extreme(data, d_data, d2_data, half_k_threshold=2):
    big = []
    small = []
    big_mis = []
    data_temp = copy.deepcopy(data)
    for i in range(len(d_data) - 1):
        if d_data[i] < 0 and d_data[i + 1] > 0:
            small.append(i)
    for i in range(len(small) - 1):
        for j in range(small[i], small[i + 1]):
            if d_data[j] > 0 and d_data[j + 1] < 0:
                big.append([[small[i], small[i + 1]], j])

    big_premis = []
    big_premis_t = []
    for s in range(len(big)):
        half_k = (big[s][0][1] - big[s][0][0]) // 2
        #####################################kye#############################################################
        if half_k >= 5:  #####重要参数，二阶导的选取比例
            half_k = half_k_threshold
        for w in range(half_k):
            if big[s][1] + w < len(d2_data) and big[s][1] - w > 0:
                if d2_data[big[s][1] + w] >= 0 or d2_data[big[s][1] - w] >= 0:
                    big_premis.append(s)
    big_premis = list(set(big_premis))
    for s in big_premis:
        big_premis_t.append(big[s])
    for s in big_premis_t:
        big.remove(s)
    for m in range(len(big) - 1):
        if data[big[m][0][1]] > data[big[m][0][0]]:
            if data[big[m][0][1]] - data[big[m][0][0]] > 0:
                list1 = []
                for f in range(big[m][1], big[m][0][1]):
                    list1.append(abs(data[f] - data[big[m][0][1]]))
                big[m][0][1] = list1.index(min(list1)) + big[m][1]
                del list1
        else:
            if data[big[m][0][0]] - data[big[m][0][1]] > 0:
                list1 = []
                for f in range(big[m][0][0], big[m][1]):
                    list1.append(abs(data[f] - data[big[m][0][1]]))
                big[m][0][0] = list1.index(min(list1)) + big[m][0][0]
                del list1

    m = 4  # m-参数，调节保留峰的宽度（反比）
    for y in range(len(big) - 1):
        q = big[y][0][1] - big[y][0][0]
        rush = q // 2 - int(q // m)
        data_temp1 = data[big[y][0][0] + rush : big[y][1] + 1]
        data_temp2 = data[big[y][1] : big[y][0][1] + 1 - rush]
        flag1 = 0
        flag2 = 0

        for h in range(len(data_temp1) - 1):
            if data_temp1[h + 1] - data_temp1[h] < 0:
                flag1 = flag1 + 1
        for x in range(len(data_temp2) - 1):
            if data_temp2[x + 1] - data_temp2[x] > 0:
                flag2 = flag2 + 1
    #        if q<5 :
    #            big_mis.append(big[y])
    for s in big_mis:
        if s in big:
            big.remove(s)

    big_new = []
    small_new = []
    for b in range(len(big)):
        small_new.append(big[b][0][0])
        small_new.append(big[b][0][1])
    for u in range(len(big)):
        big_new.append(big[u][1])
    for r in range(0, len(small_new) - 1, 2):
        q = small_new[r + 1] - small_new[r]
        for t in range(1, int(q // m) + 1):
            big_new.append(big_new[r // 2] + t)
            big_new.append(big_new[r // 2] - t)
    big_new.sort()

    big_new_searching = []
    for i in big_new:
        if i > len(data) - 2 or i < 1:
            big_new_searching.append(i)
    for i in big_new_searching:
        big_new.remove(i)
    return big_new, data_temp


def weight_resultX2(data, half_k_threshold=2):  # PEER
    d_data, d2_data = derivative(data)
    big_new, data_temp = find_extreme(data, d_data, d2_data, half_k_threshold)
    new_data = weight_result(data_temp, 7)  # 窗口参数
    for l in big_new:
        new_data[l] = data[l]
    return new_data

def peer(data, loops=1, half_k_threshold=2):
    data = np.asarray(data)
    for _ in range(loops):
        data = weight_resultX2(data, half_k_threshold)
    return data


def peer_process(spectrum, wavenumbers, loops=6, half_k_threshold=3):
    # print(type(spectrum), type(wavenumbers))
    denoised_spectrum = peer(spectrum, loops=loops, half_k_threshold=half_k_threshold)
    denoised_spectrum = np.array(denoised_spectrum, dtype=np.float32)

    return denoised_spectrum, wavenumbers