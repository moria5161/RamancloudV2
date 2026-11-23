"""Synthetic error fixtures; private instrument files are never committed."""
import os
import struct
import sys
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spectral_formats import parse_dataset, parse_single, standard_spectrum_content


def wxd_fixture(x=None, y=None, properties=None, status='Normal', extra_axis=None, extra_signal=None,
                duplicate=False, xml='<WiREXMLDoc/>', corrupt_crc=False):
    """Synthetic envelope of the supported profile, not a vendor-generated file."""
    def key(name):
        text = (name + '\0').encode('utf-16-le')
        return struct.pack('<I', len(text)) + text
    def value(data):
        return b'\x08\x00' + key(data) if isinstance(data, str) else struct.pack('<Hi', 3, data)
    def vector(values):
        return struct.pack('<Q', len(values)) + b''.join(struct.pack('<Hd', 5, v) for v in values) + bytes.fromhex('c0ffee01')
    def signal(vals):
        result = (struct.pack('<Q', 6) + key('DataList2') + b'\x0d\x00'
                  + bytes.fromhex('89bdba220816d41188e30050045536d2') + vector(vals)
                  + key('OriginalDate') + struct.pack('<Hd', 7, 45000.))
        for k, v in [('ScanCompletionStatus', status), ('dataListLabels2', 'Counts'), ('dataListType2', 2), ('dataListUnits2', 6)]:
            result += key(k) + value(v)
        return result + bytes.fromhex('c0ffee01') + struct.pack('<I', 3)
    x = np.array([410.1234567890123 - i * 1.125 for i in range(16)]) if x is None else np.asarray(x)
    y = np.array([-1.560000000000001 + i * 3.123456789012345 for i in range(len(x))]) if y is None else np.asarray(y)
    props = dict(dataListLabels0='Pixels', dataListType0=4, dataListUnits0=16, dataListLabels1='Raman shift / cm-1',
                 dataListType1=1, dataListUnits1=1, MeasurementType='SingleScan', NumberOfPoints=1)
    props.update(properties or {})
    xml_bytes = ('<?xml version="1.0"?>' + xml + '\0').encode('utf-16-le')
    blocks = [b'\0' * 8 + struct.pack('<I', len(xml_bytes)) + xml_bytes, vector([192.]), vector(x), signal(y),
              b''.join(key(k) + value(v) for k, v in props.items())]
    if duplicate:
        blocks += [vector(x), signal(y)]
    if extra_axis is not None:
        blocks.append(vector(extra_axis))
    if extra_signal is not None:
        blocks.append(signal(extra_signal))
    compressed = [zlib.compress(b) for b in blocks]
    if corrupt_crc:
        broken = bytearray(compressed[2]); broken[-1] ^= 1; compressed[2] = bytes(broken)
    data = bytearray(b'#WXD' + b'0' * 40 + b'.\n#\x1aJL\x1a\x00' + b'\0' * 4 + b'<root>')
    data += b'\0' * 96 + b''.join(compressed) + b'\0' * 16
    struct.pack_into('>I', data, 52, len(data) - 48)
    data[-16:] = struct.pack('>Q', (1 << 63) + len(data) - 64) + bytes.fromhex('80000077') + b'\0' * 4
    return bytes(data), x, y


class WxdTests(unittest.TestCase):
    def test_lossless_conversion_and_content_detection(self):
        source, x, y = wxd_fixture(duplicate=True)
        for name in ('sample.wxd', 'renamed.txt'):
            xx, yy, meta = parse_single(source, name)
            np.testing.assert_array_equal(x, xx); np.testing.assert_array_equal(y, yy)
            self.assertTrue(meta['conversion_required'])
            self.assertEqual(meta['axis_unit'], 'cm^-1')
            rx, ry, standard = parse_single(standard_spectrum_content(xx, yy), 'standard.txt')
            np.testing.assert_array_equal(x, rx); np.testing.assert_array_equal(y, ry)
            self.assertFalse(standard['conversion_required'])

    def test_rejects_units_mapping_and_incomplete_acquisition(self):
        for props in [dict(dataListUnits1=3), dict(dataListLabels1='Wavelength / nm'), dict(MeasurementType='Mapping'), dict(NumberOfPoints=2)]:
            with self.subTest(props=props), self.assertRaises(ValueError):
                parse_single(wxd_fixture(properties=props)[0], 'sample.wxd')
        for mode in ('imaging', 'time_series'):
            with self.assertRaisesRegex(ValueError, '模式不符'):
                parse_dataset(wxd_fixture()[0], 'sample.wxd', mode)
        with self.assertRaises(ValueError):
            parse_single(wxd_fixture(status='Interrupted')[0], 'sample.wxd')

    def test_different_snapshots_are_not_silently_selected(self):
        _, x, y = wxd_fixture()
        for args in [dict(extra_axis=x + .001), dict(extra_signal=y + 1)]:
            with self.assertRaisesRegex(ValueError, '多个不同'):
                parse_single(wxd_fixture(**args)[0], 'sample.wxd')

    def test_corrupt_files_and_invalid_arrays(self):
        source, x, y = wxd_fixture()
        bad_header = bytearray(source); bad_header[52] ^= 1
        for data in [source[:-1], source + b'\0', bytes(bad_header), b'plain text', wxd_fixture(corrupt_crc=True)[0],
                     wxd_fixture(corrupt_crc=True, duplicate=True)[0],
                     wxd_fixture(y=y[:-1])[0], wxd_fixture(x=np.repeat(400., 16))[0], wxd_fixture(y=np.full(16, np.nan))[0]]:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                parse_single(data, 'sample.wxd')

    def test_xml_and_decompression_are_bounded(self):
        for xml in ['<!DOCTYPE WiREXMLDoc><WiREXMLDoc/>', '<WrongDocument/>', '<WiREXMLDoc>']:
            with self.assertRaises(ValueError):
                parse_single(wxd_fixture(xml=xml)[0], 'sample.wxd')
        with patch('wxd_single.MAX_BLOCK', 32), self.assertRaisesRegex(ValueError, '上限'):
            parse_single(wxd_fixture()[0], 'sample.wxd')

    @unittest.skipUnless(os.getenv('RAMANCLOUD_WXD_FIXTURE_ZIP'), 'private instrument fixtures are not in Git')
    def test_supplied_archive_and_ten_txt_pairs(self):
        stem = lambda n: Path(n).stem.replace(',', '.').casefold()
        files, pairs = 0, 0
        with ZipFile(os.environ['RAMANCLOUD_WXD_FIXTURE_ZIP']) as z:
            for name in z.namelist():
                if not name.endswith('.wxd'):
                    continue
                x, y, meta = parse_single(z.read(name), name)
                self.assertEqual(len(x), 574)
                self.assertTrue(meta['conversion_required'])
                rx, ry, _ = parse_single(standard_spectrum_content(x, y), 'standard.txt')
                np.testing.assert_array_equal(x, rx); np.testing.assert_array_equal(y, ry)
                ref = next((n for n in z.namelist() if n.endswith('.txt') and n.split('/')[0] == name.split('/')[0] and stem(n) == stem(name)), None)
                if ref:
                    tx, ty, _ = parse_single(z.read(ref), ref)
                    np.testing.assert_array_equal([float(format(v, '.6g')) for v in x], tx)
                    np.testing.assert_array_equal([float(format(v, '.6g')) for v in y], ty)
                    pairs += 1
                files += 1
        self.assertEqual((files, pairs), (17, 10))


if __name__ == '__main__':
    unittest.main()
