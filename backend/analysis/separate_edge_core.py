import numpy as np
import scipy.ndimage as ndi


def separate_edge_core(data, layers=2, roi=None):
    if roi:
        y1, y2, x1, x2 = roi
    else:
        y1, y2, x1, x2 = 0, data.shape[0], 0, data.shape[1]

    sub_data = data[y1:y2, x1:x2]
    mask = sub_data > 0

    dist_map = ndi.distance_transform_edt(mask)

    is_edge = (dist_map > 0) & (dist_map <= layers)
    is_core = dist_map > layers

    edge_matrix = np.zeros_like(data)
    core_matrix = np.zeros_like(data)

    edge_matrix[y1:y2, x1:x2] = np.where(is_edge, sub_data, 0)
    core_matrix[y1:y2, x1:x2] = np.where(is_core, sub_data, 0)

    return edge_matrix, core_matrix