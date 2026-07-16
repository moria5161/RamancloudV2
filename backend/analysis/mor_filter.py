import numpy as np
from scipy.ndimage import label

def morphological_filter(data_map_dict, min_size):
    if not data_map_dict:
        return {}

    ref_key = 'peak_area' if 'peak_area' in data_map_dict else next(iter(data_map_dict))
    base_mask = data_map_dict[ref_key] > 0

    structure = np.ones((3, 3))
    labeled_array, _ = label(base_mask, structure=structure)
    
    component_sizes = np.bincount(labeled_array.ravel())
    valid_mask = (component_sizes >= min_size)[labeled_array]
    valid_mask[labeled_array == 0] = False

    cleaned_dict = {}
    for key, arr in data_map_dict.items():
        cleaned_dict[key] = np.where(valid_mask, arr, 0)
    
    return cleaned_dict