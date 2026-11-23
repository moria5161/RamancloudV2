"""Restricted reader for the supplied WiRE WXD single-spectrum profile.

Derived from the user's 17 WXD examples and 10 corresponding WiRE TXT exports.
This is not a general MetaKit/WXD implementation. Only the observed container,
typed arrays, metadata and single-scan layout are accepted. Repeated identical
snapshots are allowed; different snapshots are ambiguous and must be exported
with WiRE. Embedded XML/scripts are inspected as data and never executed.
"""
import re
import struct
import zlib
from xml.etree import ElementTree

import numpy as np

MAGIC = b'#WXD' + b'0' * 40 + b'.\n#\x1aJL\x1a\x00'
END = bytes.fromhex('c0ffee01')
ARRAY_CLASS = bytes.fromhex('89bdba220816d41188e30050045536d2')
MAX_FILE = 4 * 1024 * 1024
MAX_BLOCK = 2 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_STREAMS = 256
PROFILE_ERROR = '当前仅支持已验证结构的 Renishaw WXD 单条光谱；请从 WiRE 导出波数—强度 TXT 或受支持的 WDF。'


def _fail(reason):
    raise ValueError('WXD：' + reason + ' ' + PROFILE_ERROR)


def _key(name):
    value = (name + '\0').encode('utf-16-le')
    return struct.pack('<I', len(value)) + value


def _value(raw, pos, kind):
    if pos + 2 > len(raw) or struct.unpack_from('<H', raw, pos)[0] != kind:
        _fail('属性类型或长度不符。')
    pos += 2
    if kind in (3, 7):
        size, fmt = (4, '<i') if kind == 3 else (8, '<d')
        if pos + size > len(raw):
            _fail('属性被截断。')
        value = struct.unpack_from(fmt, raw, pos)[0]
        if not np.isfinite(value):
            _fail('属性含非有限数值。')
        return value, pos + size
    if pos + 4 > len(raw):
        _fail('字符串属性被截断。')
    length = struct.unpack_from('<I', raw, pos)[0]
    start, stop = pos + 4, pos + 4 + length
    if length < 2 or length % 2 or length > 4096 or stop > len(raw) or raw[stop - 2:stop] != b'\0\0':
        _fail('字符串属性长度不符。')
    try:
        return raw[start:stop - 2].decode('utf-16-le'), stop
    except UnicodeError:
        _fail('字符串编码损坏。')


def _property(raw, name, kind):
    marker = _key(name)
    pos = raw.find(marker)
    if pos < 0:
        return None
    if raw.find(marker, pos + len(marker)) >= 0:
        _fail('同一属性重复出现，无法确认数据来源。')
    return _value(raw, pos + len(marker), kind)[0]


def _vector(raw, pos=0):
    if pos + 8 > len(raw):
        _fail('光谱数组缺少点数。')
    count = struct.unpack_from('<Q', raw, pos)[0]
    if not 1 <= count <= 20000:
        _fail('光谱点数超出支持范围。')
    start, end = pos + 8, pos + 8 + count * 10
    if end + 4 > len(raw) or raw[end:end + 4] != END:
        _fail('光谱数组长度或结束标记不符。')
    records = np.frombuffer(raw, dtype=np.dtype([('tag', '<u2'), ('value', '<f8')]), count=count, offset=start)
    if not np.all(records['tag'] == 5) or not np.isfinite(records['value']).all():
        _fail('光谱数组类型不符或含 NaN/Inf。')
    return records['value'].copy(), end + 4


def _signal(raw):
    marker = _key('DataList2')
    if raw[8:8 + len(marker)] != marker:
        return None
    if raw[:8] != struct.pack('<Q', 6):
        _fail('强度数据对象结构不符。')
    pos = 8 + len(marker)
    if raw[pos:pos + 18] != b'\x0d\x00' + ARRAY_CLASS:
        _fail('强度数组类型不受支持。')
    values, pos = _vector(raw, pos + 18)
    for name, kind, expected in [('OriginalDate', 7, None), ('ScanCompletionStatus', 8, 'Normal'),
                                  ('dataListLabels2', 8, 'Counts'), ('dataListType2', 3, 2),
                                  ('dataListUnits2', 3, 6)]:
        marker = _key(name)
        if raw[pos:pos + len(marker)] != marker:
            _fail('强度数据缺少必要属性。')
        value, pos = _value(raw, pos + len(marker), kind)
        if expected is not None and value != expected:
            _fail('强度单位不符或采集未正常完成。')
    if raw[pos:] != END + struct.pack('<I', 3):
        _fail('强度对象结束标记不符。')
    return values


def _relevant_prefix(raw):
    # Recognize enough of a damaged stream to reject bad checksums/truncation,
    # without treating incidental 78 9c bytes inside other binary data as blocks.
    if raw[12:].startswith('<?xml'.encode('utf-16-le')) or _key('DataList2') in raw:
        return True
    if len(raw) >= 10 and raw[8:10] == b'\x05\x00' and 1 <= struct.unpack_from('<Q', raw)[0] <= 20000:
        return True
    return 'AccumulationsCollected'.encode('utf-16-le') in raw


def _blocks(content):
    total, count, consumed = 0, 0, 0
    for match in re.finditer(b'\x78[\x01\x5e\x9c\xda]', content):
        start = match.start()
        if start < consumed:
            continue
        decoder = zlib.decompressobj()
        head = b''
        try:
            head = decoder.decompress(content[start:start + 16], min(128, MAX_BLOCK + 1))
            if len(head) > MAX_BLOCK:
                _fail('解压后数据超过支持上限。')
            tail = decoder.unconsumed_tail + content[start + 16:]
            raw = head + decoder.decompress(tail, MAX_BLOCK + 1 - len(head))
        except zlib.error:
            if _relevant_prefix(head):
                _fail('压缩数据校验失败。')
            continue
        if len(raw) > MAX_BLOCK:
            _fail('解压后数据超过支持上限。')
        if not decoder.eof:
            if _relevant_prefix(raw):
                _fail('压缩数据被截断。')
            continue
        count += 1
        total += len(raw)
        if count > MAX_STREAMS or total > MAX_TOTAL:
            _fail('压缩块数量或解压总量超过支持上限。')
        consumed = len(content) - len(decoder.unused_data)
        yield raw


def read_wxd_single(content):
    if not 128 <= len(content) <= MAX_FILE:
        _fail('文件为空、被截断或超过 4 MB。')
    # These framing checks describe this profile only, not all WXD containers.
    if not content.startswith(MAGIC) or content[56:62] != b'<root>':
        _fail('文件头或保存版本不受支持。')
    if (struct.unpack_from('>I', content, 52)[0] != len(content) - 48
            or struct.unpack_from('>Q', content, len(content) - 16)[0] != (1 << 63) + len(content) - 64
            or content[-8:-4] != bytes.fromhex('80000077')):
        _fail('文件目录或结束记录不完整。')
    axes, signals = [], []
    metadata_found, xml_found = False, False
    for raw in _blocks(content):
        if raw[12:].startswith('<?xml'.encode('utf-16-le')):
            if (raw[:8] != b'\0' * 8 or struct.unpack_from('<I', raw, 8)[0] != len(raw) - 12
                    or not raw.endswith(b'\0\0')):
                _fail('XML 描述长度不符。')
            try:
                xml = raw[12:-2].decode('utf-16-le')
                if '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
                    _fail('XML 描述含不受支持的声明。')
                if ElementTree.fromstring(xml).tag != 'WiREXMLDoc':
                    _fail('不是受支持的 WiRE 描述。')
            except (UnicodeError, ElementTree.ParseError):
                _fail('XML 描述损坏。')
            xml_found = True
            continue
        measurement = _property(raw, 'MeasurementType', 8)
        if measurement is not None and measurement != 'SingleScan':
            _fail('暂不支持 WXD 成像或多谱序列。')
        axis_unit = _property(raw, 'dataListUnits1', 3)
        if axis_unit is not None:
            required = [('dataListLabels0', 8, 'Pixels'), ('dataListType0', 3, 4), ('dataListUnits0', 3, 16),
                        ('dataListLabels1', 8, 'Raman shift / cm-1'), ('dataListType1', 3, 1)]
            if axis_unit != 1 or measurement != 'SingleScan' or any(_property(raw, k, t) != v for k, t, v in required):
                _fail('横轴不是已验证的拉曼位移 cm⁻¹，或数据结构不符。')
            points = _property(raw, 'NumberOfPoints', 3)
            if points is not None:
                if points != 1:
                    _fail('数据包含多个采集位置，不能作为单条光谱。')
                metadata_found = True
        signal = _signal(raw)
        if signal is not None:
            if not any(np.array_equal(signal, old) for old in signals):
                signals.append(signal)
        elif len(raw) >= 10 and raw[8:10] == b'\x05\x00':
            axis, end = _vector(raw)
            if end != len(raw):
                _fail('横轴数组尾部包含未知数据。')
            # The observed DataList0 pixel reference is a single scalar; the
            # only non-scalar independent array is DataList1 (Raman shift).
            if len(axis) > 1 and not any(np.array_equal(axis, old) for old in axes):
                axes.append(axis)
        if len(axes) > 1 or len(signals) > 1:
            _fail('发现多个不同光谱或历史快照，无法唯一确认需要导入的结果。')
    if not xml_found or not metadata_found or len(axes) != 1 or len(signals) != 1:
        _fail('缺少可唯一确认的波数、强度或单谱元数据。')
    x, y = axes[0], signals[0]
    if not 8 <= len(x) <= 20000 or len(y) != len(x) or not (np.all(np.diff(x) > 0) or np.all(np.diff(x) < 0)):
        _fail('波数与强度点数不一致，或横轴不严格单调。')
    return x, y, dict(
        detected_format='renishaw_wxd_single', container='WXD', instrument='Renishaw / WiRE', axis_unit='cm^-1',
        reader='ramancloud-wxd-single-v1', wavenumber_source='DataList1', intensity_source='DataSet0.DataList2',
        supported_scope='已验证保存结构的 WXD 单条光谱',
        warnings=['WXD 当前仅支持已验证结构的单条光谱；成像、多谱序列和其他保存版本尚未支持。'])
