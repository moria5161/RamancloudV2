"""Content-based Raman import adapters. Unknown/ambiguous layouts fail closed."""
import csv
import io
import json
import re
import struct
import zipfile
from pathlib import Path
from xml.etree.ElementTree import ParseError

import numpy as np
from hyperspectral_io import read_mat, MAX_UPLOAD, MAX_ELEMENTS
from spectral_quality import quality_report

TEXT_EXTENSIONS = {'.txt', '.csv', '.tsv', '.dat', '.asc', '.xy', '.prn'}
SPECTRAL_EXTENSIONS = TEXT_EXTENSIONS | {'.mat', '.xlsx', '.jdx', '.dx', '.wdf', '.wxd', '.l6m', '.npg'}
UNSUPPORTED = {'.wip': 'WITec 工程', '.spc': 'Galactic SPC', '.ngs': 'Thermo GRAMS',
               '.sp': '厂商二进制', '.l6s': 'LabSpec', '.l6p': 'LabSpec 工程',
               '.l6v': 'LabSpec 显微图像',
               '.spa': 'OMNIC 光谱', '.spg': 'OMNIC 光谱组', '.czi': 'CZI', '.xls': '旧版 Excel'}


def _fail(message):
    raise ValueError(message)


def _array(values, label):
    try:
        # Fortran D exponents and decimal-comma exports are common ASCII variants.
        result = np.asarray([[str(v).strip().replace('D', 'E').replace('d', 'e').replace(',', '.') for v in row]
                             for row in values], dtype=float)
    except (ValueError, TypeError):
        _fail(f'{label}存在空白或非数值内容，请检查文件和列选择。')
    if not np.isfinite(result).all():
        _fail(f'{label}含缺失值、NaN 或 Inf；请先处理无效数据，平台不会静默删除。')
    return result


def validate(wave, data):
    wave, data = np.asarray(wave, dtype=float), np.asarray(data, dtype=float)
    if wave.ndim != 1 or not 3 <= wave.size <= 20000 or not data.size or data.shape[-1] != wave.size:
        _fail('波数必须为 3～20000 个点，并与每条光谱的长度一致。')
    if data.size > MAX_ELEMENTS:
        _fail('数据超过 8000 万个数值，请分块导出。')
    if not np.isfinite(wave).all() or not np.isfinite(data).all():
        _fail('波数或强度含缺失值、NaN 或 Inf。')
    delta = np.diff(wave)
    if not ((delta > 0).all() or (delta < 0).all()):
        _fail('波数轴必须严格递增或递减，不能重复；平台不会自动排序或合并。')
    return wave, data


def _finish(wave, data, actual_mode, meta, requested):
    wave, data = validate(wave, data)
    if requested not in {'auto', actual_mode}:
        _fail(f'检测到 {actual_mode} 数据，与当前 {requested} 模式不符，请切换数据模式。')
    meta.update(detected_mode=actual_mode, shape=list(data.shape), finite=True, monotonic=True, parser_version=1)
    meta.setdefault('warnings', [])
    meta.setdefault('axis_unit', 'cm^-1 (not declared)')
    if 'not declared' in meta['axis_unit']:
        meta['warnings'].append('文件未声明轴单位，请确认横轴为拉曼位移 cm⁻¹，而非波长、像素或其他物理量。')
    meta['quality_check'] = quality_report(wave, data)
    return wave, data, meta


def _unit(label):
    label = str(label).casefold()
    if any(word in label for word in ('wavelength', '波长', 'nm', 'pixel', '像素', 'ev')):
        _fail('检测到波长、像素或能量轴；当前流程需要拉曼位移 cm⁻¹，请在仪器软件中转换后导出。')
    return 'cm^-1' if any(word in label for word in ('cm', '波数', 'raman', 'shift', '1/cm')) else 'cm^-1 (not declared)'


def _role(label):
    label = re.sub(r'^.*?[_\s](?=(?:wavenumber|wavelength|intens|ramanshift))', '', str(label), flags=re.I)
    label = re.sub(r'[\s#%_()\[\]{}^/\\.\-]+', '', str(label).casefold())
    if label.startswith(('wavelength', '波长')):
        return 'wavelength'
    if label.startswith(('ramanshift', '拉曼位移', '拉曼频移')):
        return 'raman_shift'
    if label.startswith(('wavenumber', 'shift', '波数')) or label == 'wave':
        return 'wave'
    if label.startswith(('intensity', 'intens', 'counts', 'signal', '强度', '光谱强度')):
        return 'intensity'
    if label in {'x', 'xum', 'xµm', 'positionx', 'xposition', '横坐标'}:
        return 'x'
    if label in {'y', 'yum', 'yµm', 'positiony', 'yposition', '纵坐标'}:
        return 'y'
    if label.startswith(('time', '时间')) or label in {'t', 'seconds'}:
        return 'time'
    return ''


def _decode(content):
    encodings = ['utf-16'] if content.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'gb18030']
    for encoding in encodings:
        try:
            text = content.decode(encoding)
            if '\x00' in text or any(ord(char) < 9 for char in text):
                break
            return text, encoding
        except UnicodeError:
            continue
    _fail('文件不是可识别的文本编码，或属于二进制格式；请导出 UTF-8/GB18030 文本或支持的原始格式。')


def _table(content):
    text, encoding = _decode(content)
    lines = [line for line in text.splitlines() if line.strip()]
    numeric = re.compile(r'^\s*[+-]?(?:\d|\.\d)')
    sample = next((line for line in lines if numeric.match(line) or line.startswith(('\t', ','))), '')
    sep = next((value for value in ('\t', ';', ',') if value in sample), None)
    def split(line):
        return next(csv.reader([line], delimiter=sep)) if sep else re.split(r'\s+', line.strip())
    rows, header, started, ignored = [], None, False, 0
    for line in lines:
        if line.lstrip().startswith(('#', '%', '//', ';')):
            candidate = split(line.lstrip().lstrip('#%').strip())
            if not started and any(_role(cell) for cell in candidate):
                header = candidate
            ignored += 1
            continue
        cells = split(line)
        first = next((cell.strip() for cell in cells if cell.strip()), '')
        if first.casefold() in {'nan', 'inf', '+inf', '-inf', 'infinity'}:
            _fail('数据行出现 NaN/Inf 波数，不能作为表头跳过。')
        if not started and not numeric.match(first):
            header = cells
            ignored += 1
            continue
        started = True
        if len(cells) < 2 or rows and len(cells) != len(rows[0]):
            _fail('数据行列数不一致或缺少强度列，不能自动跳过损坏行。')
        rows.append(cells)
        if len(rows) * len(cells) > MAX_ELEMENTS + 100000:
            _fail('文本矩阵规模超出限制。')
    if not rows:
        _fail('没有找到光谱数值表，请导出带横轴的原始数据而非截图或峰表。')
    if header:
        while len(header) > len(rows[0]) and not header[-1].strip():
            header.pop()
    if header and len(header) != len(rows[0]):
        header = None
    meta = dict(encoding=encoding, delimiter={'\t': 'tab', ';': 'semicolon', ',': 'comma', None: 'whitespace'}[sep], ignored_lines=ignored)
    instrument = re.search(r'^\s*Instrument\s*:\s*(.+)$', text, re.I | re.M)
    if instrument:
        meta['instrument'] = instrument[1].strip()[:120]
    return rows, header, meta


def _grid(wave, spectra, coords, meta, mode):
    coords = np.asarray(coords, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2 or not np.isfinite(coords).all():
        _fail('成像坐标必须为有限的 X、Y 数值。')
    xs, ys = np.unique(coords[:, 0]), np.unique(coords[:, 1])
    count = len(coords)
    if len(np.unique(coords, axis=0)) != count:
        _fail('存在重复像素坐标；请区分重复采集、Z 层或时间点后再上传。')
    if len(xs) * len(ys) != count:
        _fail('空间网格存在缺失像素或为不规则点集；平台不会补零，请导出完整二维网格。')
    if count * len(wave) > MAX_ELEMENTS:
        _fail('成像数据规模超出限制。')
    cube = np.empty((len(ys), len(xs), len(wave)))
    cube[np.searchsorted(ys, coords[:, 1]), np.searchsorted(xs, coords[:, 0])] = spectra
    meta.update(x_coordinates=xs.tolist(), y_coordinates=ys.tolist(), coordinate_order='rows=Y, columns=X')
    return _finish(wave, cube, 'imaging', meta, mode)


def _long(matrix, roles, meta, mode):
    w, intensity = roles.index('wave'), roles.index('intensity')
    locations = [roles.index(name) for name in ('x', 'y')] if 'x' in roles and 'y' in roles else [roles.index('time')] if 'time' in roles else []
    if not locations:
        return _finish(matrix[:, w], matrix[:, intensity], 'spectrum', meta, mode)
    groups = {}
    for row in matrix:
        groups.setdefault(tuple(row[locations]), []).append(row[[w, intensity]])
    if len(groups) * len(next(iter(groups.values()))) > MAX_ELEMENTS:
        _fail('长表规模超出限制。')
    wave, spectra = None, []
    for values in groups.values():
        values = np.asarray(values)
        if wave is None:
            wave = values[:, 0]
        if not np.array_equal(wave, values[:, 0]):
            _fail('各像素/时间点的波数轴不一致，不能静默插值或截断。')
        spectra.append(values[:, 1])
    if len(locations) == 2:
        return _grid(wave, spectra, list(groups), meta, mode)
    meta['series_coordinates'] = [key[0] for key in groups]
    return _finish(wave, np.asarray(spectra), 'time_series', meta, mode)


def _matrix(wave, spectra, meta, mode, height, width, pixel_order):
    if mode == 'imaging':
        if not height or not width or height * width != len(spectra):
            _fail('此矩阵没有空间坐标；成像模式需填写行数×列数等于光谱条数，或改用时间序列模式。')
        return _finish(wave, spectra.reshape(height, width, len(wave), order=pixel_order), 'imaging', meta, mode)
    return _finish(wave, spectra[0] if len(spectra) == 1 else spectra, 'spectrum' if len(spectra) == 1 else 'time_series', meta, mode)


def _parse_table(rows, header, meta, mode, hint, height, width, pixel_order):
    cols = len(rows[0])
    meta['numeric_columns'] = cols
    meta['effective_columns'] = sum(any(str(row[i]).strip() for row in rows) for i in range(cols))
    if header:
        meta['column_names'] = [str(cell)[:160] for cell in header]
    roles = [_role(cell) for cell in header] if header else []
    # EduRaman exports both absolute wavenumber and Raman shift. They are not interchangeable.
    if 'raman_shift' in roles:
        roles = ['wave' if role == 'raman_shift' else 'absolute_wavenumber' if role == 'wave' else role for role in roles]
    pixel_names = [re.fullmatch(r'x(\d+)_y(\d+)', cell.strip(), re.I) for cell in header] if header else []
    if pixel_names and any(pixel_names):
        wave_cols = [i for i, role in enumerate(roles) if role == 'wave']
        if len(wave_cols) != 1:
            _fail('像素列存在，但缺少唯一的 Wavenumber 波数列。')
        wi = wave_cols[0]
        wave = _array([[row[wi]] for row in rows], '波数')[:, 0]
        indices = [i for i, match in enumerate(pixel_names) if match]
        data = _array([[row[i] for i in indices] for row in rows], '强度').T
        coords = [(int(pixel_names[i][1]), int(pixel_names[i][2])) for i in indices]
        meta.update(detected_format='nanophoton_columns', axis_unit=_unit(header[wi]))
        return _grid(wave, data, coords, meta, mode)
    if header and header[0].casefold().startswith('wn(') and cols % 2 == 0:
        matrix = _array(rows, '时间序列')
        if not all(np.array_equal(matrix[:, 0], matrix[:, i]) for i in range(0, cols, 2)):
            _fail('交替波数/强度列的波数轴不一致。')
        meta.update(detected_format='nanophoton_paired', axis_unit='cm^-1 (not declared)')
        return _finish(matrix[:, 0], matrix[:, 1::2].T[::-1], 'time_series', meta, mode)
    leading = next((i for i, cell in enumerate(rows[0]) if str(cell).strip()), cols)
    if (leading in {1, 2} and 'wave' not in roles) or (not header and hint == 'horiba' and mode in {'imaging', 'time_series'}):
        offset = leading if leading in {1, 2} else (2 if mode == 'imaging' else 1)
        wave = _array([rows[0][offset:]], '波数')[0]
        body = _array(rows[1:], '矩阵数据')
        meta.update(detected_format='horiba_rows', axis_unit='cm^-1 (not declared)')
        if offset == 2:
            return _grid(wave, body[:, 2:], body[:, :2], meta, mode)
        return _finish(wave, body[:, 1:], 'time_series', meta, mode)
    if 'wavelength' in roles and 'wave' not in roles:
        _unit('wavelength nm')
    if roles.count('wave') == 1 and roles.count('intensity') == 1:
        selected = [i for i, role in enumerate(roles) if role in {'wave', 'intensity', 'x', 'y', 'time'}]
        reduced_roles = [roles[i] for i in selected]
        if len(set(reduced_roles)) != len(reduced_roles):
            _fail('表头存在重复的波数、强度或坐标列，无法唯一识别。')
        matrix = _array([[row[i] for i in selected] for row in rows], '数据')
        meta.update(detected_format='labelled_long' if {'x', 'y', 'time'} & set(roles) else 'labelled_spectrum',
                    axis_unit=_unit(header[roles.index('wave')]), wavenumber_column=roles.index('wave') + 1,
                    intensity_column=roles.index('intensity') + 1)
        return _long(matrix, reduced_roles, meta, mode)
    if hint in {'renishaw', 'long'} and cols in {3, 4}:
        matrix = _array(rows, '长表')
        roles = ['x', 'y', 'wave', 'intensity'] if cols == 4 else ['time', 'wave', 'intensity']
        meta.update(detected_format='unlabelled_long', warnings=['无表头长表按手动指定的列顺序读取。'])
        return _long(matrix, roles, meta, mode)
    # Empty unused columns are permitted, but missing cells within a signal are not.
    nonempty = [i for i in range(cols) if any(str(row[i]).strip() for row in rows)]
    matrix = _array([[row[i] for i in nonempty] for row in rows], '数据')
    if len(nonempty) == 2:
        meta.update(detected_format='two_columns', wavenumber_column=nonempty[0] + 1, intensity_column=nonempty[1] + 1)
        return _finish(matrix[:, 0], matrix[:, 1], 'spectrum', meta, mode)
    if hint == 'rows':
        meta['detected_format'] = 'spectra_rows'
        return _matrix(matrix[0], matrix[1:], meta, mode, height, width, pixel_order)
    named_columns = roles and roles.count('wave') == 1 and all(roles[i] in {'wave', 'intensity'} for i in nonempty)
    if hint == 'columns' or named_columns:
        original_wi = roles.index('wave') if roles and 'wave' in roles else nonempty[0]
        if original_wi not in nonempty:
            _fail('波数列没有数值。')
        wi = nonempty.index(original_wi)
        meta.update(detected_format='spectra_columns', axis_unit=_unit(header[original_wi]) if header else 'cm^-1 (not declared)')
        return _matrix(matrix[:, wi], np.delete(matrix, wi, axis=1).T, meta, mode, height, width, pixel_order)
    _fail('多列数据没有足够的表头/坐标信息，不能猜测波数列。请指定行矩阵、列矩阵或 Renishaw 长表格式。')


def _xlsx(content):
    from openpyxl import load_workbook
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 256 * 1024 * 1024:
            _fail('Excel 解压后规模过大。')
        if 'xl/workbook.xml' not in archive.namelist() or any('vbaProject' in entry.filename for entry in entries):
            _fail('这不是无宏 XLSX 数据文件。')
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
    try:
        if len(workbook.sheetnames) != 1:
            _fail('Excel 含多个工作表，请保留一个数据表后上传，避免静默选错。')
        sheet = workbook.active
        if sheet.max_row * sheet.max_column > MAX_ELEMENTS:
            _fail('Excel 声明的矩阵过大。')
        rows = []
        for values in sheet.iter_rows():
            if any(cell.data_type == 'f' for cell in values):
                _fail('Excel 含公式，请粘贴为数值后上传，不执行也不使用缓存公式结果。')
            row = [str(cell.value) if cell.value is not None else '' for cell in values]
            if any(row):
                rows.append(row)
        if not rows:
            _fail('Excel 没有数据。')
        header = rows.pop(0) if not re.match(r'^[+-]?(?:\d|\.\d)', next((v for v in rows[0] if v), '')) else None
        return rows, header, dict(container='XLSX', ignored_lines=int(header is not None), encoding='xlsx', delimiter='cells')
    finally:
        workbook.close()


def _wdf(content, mode):
    from wdf import Wdf, WdfDataType
    blocks, position, count = {}, 0, 0
    while position < len(content):
        count += 1
        if position + 16 > len(content) or count > 20000:
            _fail('WDF 块结构损坏。')
        name, _, size = struct.unpack_from('<4sIQ', content, position)
        if size < 16 or position + size > len(content):
            _fail('WDF 块长度无效或文件未写完。')
        blocks[name] = (position, size)
        position += size
    if b'XLST' not in blocks or b'DATA' not in blocks:
        _fail('WDF 缺少波数或强度数据块。')
    reader = Wdf()
    reader.open_fd(io.BytesIO(content))
    try:
        h = reader.hdr
        if h.ntracks > 1 or h.flags_ & 9 or h.npoints != h.xlistcount:
            _fail('暂不支持多轨或各谱横轴不同的 WDF，请导出公共波数轴文本。')
        if h.nspectra != h.ncollected or not 1 <= h.nspectra or not 3 <= h.npoints <= 20000 or h.nspectra * h.npoints > MAX_ELEMENTS:
            _fail('WDF 未采集完成、尺寸无效或超出限制。')
        pos, size = blocks[b'DATA']
        if size < 16 + h.nspectra * h.npoints * 4:
            _fail('WDF 强度数据被截断。')
        xposition, xsize = blocks[b'XLST']
        if xsize < 24 + h.npoints * 4 or struct.unpack_from('<I', content, xposition + 20)[0] != 1:
            _fail('WDF 横轴不是 RamanShift cm⁻¹，或波数块损坏。')
        wave = np.asarray(reader.xlist())
        data = np.asarray([reader[i] for i in range(h.nspectra)])
        meta = dict(detected_format='renishaw_wdf', container='WDF', axis_unit='cm^-1', reader='renishaw-wdf 1.3.1')
        if h.nspectra == 1:
            return _finish(wave, data[0], 'spectrum', meta, mode)
        if h.type == 3:
            if b'ORGN' not in blocks:
                _fail('WDF 成像文件缺少空间坐标。')
            origin_pos, origin_size = blocks[b'ORGN']
            if origin_size < 20:
                _fail('WDF 空间坐标块损坏。')
            origins_count = struct.unpack_from('<I', content, origin_pos + 16)[0]
            if not 1 <= origins_count <= 128 or origin_size < 20 + origins_count * (24 + h.nspectra * 8):
                _fail('WDF 空间坐标的数量或长度不符。')
            origins = reader.origins
            if WdfDataType.Spatial_Z in origins and len(set(origins[WdfDataType.Spatial_Z][:])) > 1:
                _fail('WDF 含多个 Z 层，请导出单个二维切片。')
            coords = np.column_stack([origins[WdfDataType.Spatial_X][:], origins[WdfDataType.Spatial_Y][:]])
            return _grid(wave, data, coords, meta, mode)
        meta['warnings'] = ['WDF 多谱序列按采集索引读取，不自动推断时间单位。']
        return _finish(wave, data, 'time_series', meta, mode)
    finally:
        reader.close()


def parse_dataset(content, filename='', mode='auto', hint='auto', height=None, width=None, layout='auto', pixel_order='F'):
    if not content or len(content) > MAX_UPLOAD:
        _fail('文件为空或超过 128 MB。')
    if mode not in {'auto', 'spectrum', 'imaging', 'time_series'} or pixel_order not in {'C', 'F'}:
        _fail('数据模式或像素排列参数无效。')
    hint = hint.casefold()
    if hint not in {'auto', 'horiba', 'nanophoton', 'renishaw', 'long', 'columns', 'rows'}:
        _fail('未知解析格式，请选择自动识别或支持的结构。')
    extension = Path(filename).suffix.casefold()
    try:
        if content.startswith(b'LabSpec6') or extension == '.l6m':
            from native_spectra import read_labspec6
            wave, values, meta = read_labspec6(content)
            return _finish(wave, values, 'imaging', meta, mode)
        if content.startswith('MultiGraph'.encode('utf-16-le')) or extension == '.npg':
            from native_spectra import read_nanophoton_npg
            wave, values, meta = read_nanophoton_npg(content)
            return _finish(wave, values, 'spectrum', meta, mode)
        if content.startswith(b'WDF1'):
            return _wdf(content, mode)
        if content.startswith(b'#WXD') or extension == '.wxd':
            from wxd_single import read_wxd_single
            wave, intensity, meta = read_wxd_single(content)
            return _finish(wave, intensity, 'spectrum', meta, mode)
        if extension in UNSUPPORTED or re.fullmatch(r'\.\d+', extension):
            _fail(f'{UNSUPPORTED.get(extension, "OPUS")} 原始格式尚未验证，请从厂商软件导出带波数轴的 TXT/CSV、MAT 或 JCAMP-DX；不能只改扩展名。')
        if extension == '.mat' or content.startswith((b'MATLAB', b'\x89HDF')):
            wave, cube, meta = read_mat(content, height, width, layout, pixel_order)
            meta['detected_format'] = 'mat_cube'
            return _finish(wave, cube, 'imaging', meta, mode)
        if content.startswith(b'PK') or extension == '.xlsx':
            rows, header, meta = _xlsx(content)
        else:
            text, encoding = _decode(content)
            if '##JCAMP' in text.upper()[:4096]:
                from jcamp import jcamp_read
                if len(re.findall(r'^##\s*TITLE\s*=', text, re.I | re.M)) != 1 or 'NTUPLES' in text.upper() or len(text) > 4 * 1024 * 1024:
                    _fail('JCAMP 仅支持单条光谱，请将多块/NTUPLES 数据分别导出。')
                count = re.search(r'^##\s*NPOINTS\s*=\s*(\d+)\s*$', text, re.I | re.M)
                if not count or not 3 <= int(count[1]) <= 20000:
                    _fail('JCAMP NPOINTS 必须在 3～20000 之间。')
                parsed = jcamp_read(io.StringIO(text))
                if len(parsed.get('x', [])) != int(count[1]) or len(parsed.get('y', [])) != int(count[1]):
                    _fail('JCAMP 实际点数与 NPOINTS 声明不一致。')
                if parsed.get('children') or 'raman' not in str(parsed.get('data type', '')).casefold():
                    _fail('JCAMP 必须是单条 RAMAN 光谱，不能将红外、质谱等自动当成拉曼。')
                unit = str(parsed.get('xunits', ''))
                if not any(token in unit.casefold() for token in ('cm', 'wavenumber')):
                    _fail('JCAMP 未声明 cm⁻¹ 波数轴，请确认并导出正确单位。')
                meta = dict(detected_format='jcamp_dx', container='JCAMP-DX', encoding=encoding, axis_unit=_unit(unit))
                return _finish(parsed['x'], parsed['y'], 'spectrum', meta, mode)
            if extension and extension not in TEXT_EXTENSIONS:
                _fail('不支持此扩展名；请导出 TXT/CSV/TSV/DAT/ASC/XY/PRN、MAT、XLSX、JCAMP-DX、WDF 或受支持的单谱 WXD。')
            rows, header, meta = _table(content)
        return _parse_table(rows, header, meta, mode, hint, height, width, pixel_order)
    except ImportError as exc:
        raise ValueError('格式读取依赖不可用，请在后端安装 requirements.txt 并重启。') from exc
    except (EOFError, KeyError, IndexError, struct.error, zipfile.BadZipFile, OverflowError, TypeError, AssertionError, ZeroDivisionError, ParseError, UnicodeError) as exc:
        raise ValueError('文件结构损坏、必要字段缺失或声明尺寸不符；请重新从仪器软件导出。') from exc


def parse_single(content, filename='', spectrum_index=None, allow_selection_preview=False):
    native_map = content.startswith(b'LabSpec6') or Path(filename).suffix.lower() == '.l6m'
    wave, intensity, meta = parse_dataset(content, filename, mode='auto' if native_map else 'spectrum')
    if intensity.ndim > 1:
        flat = intensity.reshape(-1, len(wave))
        count = len(flat)
        if spectrum_index is None and not allow_selection_preview:
            _fail(f'文件含 {count} 条光谱，请在智能光谱处理单独上传并选取位置，或先拆分为双列文件。')
        index = 0 if spectrum_index is None else spectrum_index
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count:
            _fail('所选光谱编号超出文件范围。')
        meta.update(native_shape=list(intensity.shape), spectrum_count=count, spectrum_index=index,
                    selection_required=spectrum_index is None)
        row, column = divmod(index, intensity.shape[1])
        meta['selected_position'] = dict(row=row, column=column,
            x=meta['x_coordinates'][column], y=meta['y_coordinates'][row], unit=meta['coordinate_unit'])
        if spectrum_index is None:
            meta['spectrum_choices'] = [dict(index=i, row=i // intensity.shape[1], column=i % intensity.shape[1],
                x=meta['x_coordinates'][i % intensity.shape[1]], y=meta['y_coordinates'][i // intensity.shape[1]],
                preview=[[float(x), float(y)] for x, y in zip(wave[:5], values[:5])]) for i, values in enumerate(flat)]
        intensity = flat[index]
        meta.update(shape=list(intensity.shape), detected_mode='spectrum')
        # Quality flags refer to the selected point, not the rest of the map.
        meta['quality_check'] = quality_report(wave, intensity)
    elif spectrum_index is not None:
        _fail('单条光谱不需要指定位置。')
    simple = (meta.get('detected_format') in {'two_columns', 'labelled_spectrum'}
              and meta.get('effective_columns') == 2 and not meta.get('container'))
    meta.update(conversion_required=not simple, standard_format='raman_shift_intensity')
    names = meta.get('column_names', [])
    for field in ('wavenumber', 'intensity'):
        index = meta.get(field + '_column')
        if index and index <= len(names):
            meta[field + '_label'] = names[index - 1]
    return wave, intensity, meta


def standard_spectrum_content(wave, intensity):
    """Canonical two-column export; round-trip every float without resampling or rounding."""
    wave, intensity = validate(wave, intensity)
    if intensity.ndim != 1:
        _fail('标准双列导出仅支持单条光谱。')
    rows = ['RamanShift(cm^-1)\tIntensity']
    rows.extend(f'{x:.17g}\t{y:.17g}' for x, y in zip(wave, intensity))
    return ('\n'.join(rows) + '\n').encode('utf-8')


def standard_spectra_archive(content, filename, hint='auto', require_multiple=False):
    """Export each spectrum separately with positions; never average a map."""
    wave, values, metadata = parse_dataset(content, filename, hint=hint)
    flat = values.reshape(-1, len(wave))
    if require_multiple and len(flat) < 2:
        _fail('此文件只有一条光谱，无需拆分；可使用“标准双列转换”。')
    if len(flat) > 10000:
        _fail('一次最多拆分 10000 条光谱。')
    files, output = [], io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for i, spectrum in enumerate(flat):
            name = f'spectrum_{i + 1:06d}.txt'
            entry = dict(file=name, index=i)
            if values.ndim == 3 and metadata.get('x_coordinates') and metadata.get('y_coordinates'):
                row, column = divmod(i, values.shape[1])
                entry.update(row=row, column=column, x=metadata['x_coordinates'][column], y=metadata['y_coordinates'][row])
            elif metadata.get('series_coordinates') is not None:
                entry['series_coordinate'] = metadata['series_coordinates'][i]
            archive.writestr(name, standard_spectrum_content(wave, spectrum))
            files.append(entry)
        archive.writestr('manifest.json', json.dumps(dict(source_name=Path(filename).name, spectrum_count=len(flat),
            points=len(wave), metadata=metadata, spectra=files), ensure_ascii=False, allow_nan=False, indent=2))
    return output.getvalue()
