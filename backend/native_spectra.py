"""Bounded readers for the supplied LabSpec6 map and Nanophoton MultiGraph profiles.

Layouts were inspected from local instrument examples. These are deliberately
profile-specific readers, not general vendor-project decoders.
"""
import re
import struct

import numpy as np


NPG_MAGIC = 'MultiGraph'.encode('utf-16-le')
MAX_VALUES = 8_000_000


def _fail(message):
    raise ValueError(message + ' 请从仪器软件导出波数—强度 TXT 核对或使用。')


def _u32(data, pos):
    if pos < 0 or pos + 4 > len(data):
        _fail('原生文件字段被截断。')
    return struct.unpack_from('<I', data, pos)[0]


def _floats(data, pos, count, dtype):
    size = np.dtype(dtype).itemsize
    if not 1 <= count <= MAX_VALUES or pos < 0 or pos + count * size > len(data):
        _fail('原生文件数组长度无效或被截断。')
    values = np.frombuffer(data, dtype=dtype, count=count, offset=pos).astype(float)
    if not np.isfinite(values).all():
        _fail('原生文件含 NaN 或 Inf。')
    return values


def _monotonic(values):
    delta = np.diff(values)
    return len(values) > 1 and ((delta > 0).all() or (delta < 0).all())


def read_labspec6(data):
    if not data.startswith(b'LabSpec6\0') or len(data) > 32 * 1024 * 1024:
        _fail('不是受支持的 LabSpec6 文件。')
    def tag(name):
        return b'typm\0\0\0\0' + name.ljust(8, b'\0')
    spectral = [m.start() + 8 for m in re.finditer(re.escape(tag(b'Spectr')), data)]
    if len(spectral) != 1 or tag(b'SpIm') not in data[:512]:
        _fail('暂只支持单组 LabSpec6 光谱成像数据。')
    sp = spectral[0]
    if data[sp + 16:sp + 20] != b'uni|' or data[sp + 24:sp + 32] != b'1/cm\0\0\0\0':
        _fail('LabSpec6 横轴未声明为 1/cm。')
    n = _u32(data, sp - 20)
    if not 8 <= n <= 20000 or _u32(data, sp + 32) != 0x1009 or data[sp + 41:sp + 44] != b'tam' or _u32(data, sp + 52) != 1:
        _fail('LabSpec6 波数数组结构不符。')
    wave = _floats(data, sp + 56, n, '<f4')
    if not _monotonic(wave):
        _fail('LabSpec6 波数轴无效。')
    raw = [m.start() + 8 for m in re.finditer(re.escape(tag(b'Intens')), data[:sp])]
    if len(raw) != 1:
        _fail('无法唯一确定 LabSpec6 原始强度数据。')
    ip = raw[0]
    if data[ip + 16:ip + 20] != b'uni|' or data[ip + 24:ip + 32] != b'Cnt\0\0\0\0\0' or _u32(data, ip + 32) != 0x1006 or _u32(data, ip + 56) != 0x1009 or _u32(data, ip + 76) != 4:
        _fail('LabSpec6 强度数组结构不符。')
    count = _u32(data, ip + 52)
    if count % n or count // n > 10000 or ip + 80 + count * 4 > sp:
        _fail('LabSpec6 强度尺寸与波数不符。')
    axes = []
    for label in (b'XA', b'YA'):
        pos = data.find(tag(label), sp + 56 + n * 4)
        if pos < 0:
            _fail('LabSpec6 缺少成像坐标。')
        pos += 8
        size = _u32(data, pos - 20)
        if not 1 <= size <= 4096 or data[pos + 16:pos + 20] != b'uni|' or data[pos + 24:pos + 32] != b'\xb5m\0\0\0\0\0\0' or data[pos + 40:pos + 44] != b'\xd8abm' or data[pos + 48:pos + 56] != label[:1].ljust(8, b'\0'):
            _fail('LabSpec6 成像坐标结构或单位不符。')
        # XA carries a mat record; the supplied YA stores the vector directly.
        offset = 80 if _u32(data, pos + 56) == 0x1009 else 56
        if offset == 80 and _u32(data, pos + 76) != 1:
            _fail('LabSpec6 坐标数组不是一维。')
        values = _floats(data, pos + offset, size, '<f4')
        if size > 1 and not _monotonic(values):
            _fail('LabSpec6 成像坐标存在重复或乱序。')
        axes.append(values)
    xs, ys = axes
    if len(xs) * len(ys) * n != count:
        _fail('LabSpec6 空间网格与光谱数量不符。')
    values = _floats(data, ip + 80, count, '<f4')
    cube = values.reshape(len(xs), len(ys), n).transpose(1, 0, 2)
    return wave, cube, dict(detected_format='horiba_labspec6', container='LabSpec6 L6M',
        instrument='Horiba', axis_unit='cm^-1', native_profile='labspec6_spim_float32_v1',
        x_coordinates=xs.tolist(), y_coordinates=ys.tolist(), coordinate_unit='µm',
        native_acquisition_order='X outer, Y inner', warnings=[])


def read_nanophoton_npg(data):
    if not data.startswith(NPG_MAGIC) or len(data) < 0x108 or len(data) > 32 * 1024 * 1024:
        _fail('不是受支持的 Nanophoton NPG 文件。')
    if tuple(_u32(data, pos) for pos in (20, 24, 28, 0xb7, 0xbb)) != (2, 1, 1, 1, 1):
        _fail('暂只支持已验证的 NPG MultiGraph v2 单点结构。')
    n = _u32(data, 0xb3)
    if not 8 <= n <= 20000:
        _fail('NPG 光谱点数无效。')
    date_length = _u32(data, 0xdc)
    if not 0 < date_length <= 256 or date_length % 2:
        _fail('NPG 时间字段无效。')
    length_pos = 0xe0 + date_length
    length = _u32(data, length_pos)
    start = length_pos + 4
    if not 0 < length <= 65536 or length % 2 or start + length + 4 + n * 16 > len(data):
        _fail('NPG 测量信息或光谱数组被截断。')
    metadata = data[start:start + length].decode('utf-16-le')
    if not re.search(r'Measurement Mode:\s*Point\s*(?:\r?\n|$)', metadata) or 'X axis (wavenumber):' not in metadata:
        _fail('NPG 不是已验证的单点拉曼测量。')
    laser = struct.unpack_from('<d', data, 0x38)[0]
    second_laser = struct.unpack_from('<d', data, 0xd4)[0]
    declared = re.search(r'Excitation Wavelength:\s*(\d+(?:\.\d+)?)\s*nm', metadata)
    if not declared or not 100 < laser < 3000 or laser != second_laser or abs(laser - float(declared[1])) > .01:
        _fail('NPG 激发波长缺失或相互冲突。')
    signal_pos = start + length + 4
    if _u32(data, start + length) != 0:
        _fail('NPG 光谱分隔字段不符。')
    intensity = _floats(data, signal_pos, n, '<f8')
    wavelength = _floats(data, signal_pos + n * 8, n, '<f8')
    if not _monotonic(wavelength) or (wavelength < 100).any() or (wavelength > 10000).any():
        _fail('NPG 波长轴无效。')
    # Cross-check the graph's stored data bounds, independently of the arrays.
    for pos, expected in ((0x59, intensity.max()), (0x61, intensity.min()), (0x69, wavelength.max()), (0x71, wavelength.min())):
        if not np.isclose(struct.unpack_from('<d', data, pos)[0], expected, rtol=1e-7, atol=1e-7):
            _fail('NPG 数组与图形范围记录不符。')
    trailer = signal_pos + n * 16
    width, height = _u32(data, trailer + 8), _u32(data, trailer + 12)
    if data[trailer:trailer + 8] != b'\0' * 8 or not 1 <= width <= 4096 or not 1 <= height <= 4096 or trailer + 64 + width * height * 4 != len(data):
        _fail('NPG 附带图像结构不符或文件未保存完整。')
    wave = 1e7 * (1 / laser - 1 / wavelength)
    warnings = []
    if 'X axis (wavenumber): Not Calibrated' in metadata:
        warnings.append('仪器记录横轴未校准，请核对峰位。')
    return wave, intensity, dict(detected_format='nanophoton_npg', container='Nanophoton NPG',
        instrument='Nanophoton', axis_unit='cm^-1', native_profile='multigraph_v2_point_v1',
        source_axis_unit='nm', laser_wavelength_nm=laser, axis_conversion='wavelength_nm_to_raman_shift',
        conversion_formula='1e7 * (1 / laser_nm - 1 / wavelength_nm)', warnings=warnings)
