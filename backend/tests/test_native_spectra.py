"""Synthetic native-container fixtures; no private measurement files are shipped."""
import io
import json
import struct
import sys
import unittest
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spectral_formats import parse_dataset, parse_single, standard_spectrum_content, standard_spectra_archive


def labspec_fixture():
    wave = np.linspace(1800, 200, 16).astype('<f4')
    xs, ys = np.array([-4., 0.]), np.array([1., 2., 3.])
    native = np.arange(6 * len(wave), dtype='<f4').reshape(2, 3, len(wave))
    def block(name, values, unit, kind):
        values = np.asarray(values, dtype='<f4').ravel()
        offset = 80 if kind in ('signal', 'x') else 56
        result = bytearray(32 + offset)
        pos = 32
        struct.pack_into('<I', result, pos - 20, len(values))
        result[pos - 8:pos] = b'typm\0\0\0\0'
        result[pos:pos + 8] = name.ljust(8, b'\0')
        result[pos + 16:pos + 20] = b'uni|'
        result[pos + 24:pos + 32] = unit.ljust(8, b'\0')
        if kind == 'signal':
            struct.pack_into('<I', result, pos + 32, 0x1006)
            struct.pack_into('<I', result, pos + 52, len(values))
            struct.pack_into('<I', result, pos + 56, 0x1009)
            struct.pack_into('<I', result, pos + 76, 4)
        elif kind == 'spectral':
            struct.pack_into('<I', result, pos + 32, 0x1009)
            result[pos + 40:pos + 44] = b'\xe3tam'
            struct.pack_into('<I', result, pos + 52, 1)
        else:
            result[pos + 40:pos + 44] = b'\xd8abm'
            result[pos + 48:pos + 56] = name[:1].ljust(8, b'\0')
            if kind == 'x':
                struct.pack_into('<I', result, pos + 56, 0x1009)
                struct.pack_into('<I', result, pos + 76, 1)
        return bytes(result) + values.tobytes()
    header = b'LabSpec6\0' + b'\0' * 32 + b'typm\0\0\0\0SpIm\0\0\0\0' + b'\0' * 32
    content = header + block(b'Intens', native, b'Cnt', 'signal') + block(b'Spectr', wave, b'1/cm', 'spectral')
    content += block(b'XA', xs, b'\xb5m', 'x') + block(b'YA', ys, b'\xb5m', 'y')
    return content, wave.astype(float), native.transpose(1, 0, 2).astype(float)


def npg_fixture():
    laser = 532.
    wavelength = np.linspace(532, 560, 16)
    signal = np.arange(16, dtype=float) ** 2 - 10
    header = bytearray(0xe0)
    header[:20] = 'MultiGraph'.encode('utf-16-le')
    for pos, value in ((20, 2), (24, 1), (28, 1), (0xb7, 1), (0xbb, 1), (0xb3, len(signal))):
        struct.pack_into('<I', header, pos, value)
    for pos in (0x38, 0xd4):
        struct.pack_into('<d', header, pos, laser)
    for pos, value in ((0x59, signal.max()), (0x61, signal.min()), (0x69, wavelength.max()), (0x71, wavelength.min())):
        struct.pack_into('<d', header, pos, value)
    date = '2026/1/1 12:00:00'.encode('utf-16-le')
    struct.pack_into('<I', header, 0xdc, len(date))
    metadata = ('Excitation Wavelength: 532.00 nm\r\nMeasurement Mode: Point\r\n'
                'X axis (wavenumber): Not Calibrated\r\n').encode('utf-16-le')
    trailer = bytearray(64)
    struct.pack_into('<II', trailer, 8, 2, 3)
    content = bytes(header) + date + struct.pack('<I', len(metadata)) + metadata + b'\0' * 4
    content += signal.astype('<f8').tobytes() + wavelength.astype('<f8').tobytes() + trailer + b'\0' * 24
    return content, 1e7 * (1 / laser - 1 / wavelength), signal


class NativeFormatsTests(unittest.TestCase):
    def test_labspec_axes_pixel_order_and_explicit_selection(self):
        content, wave, cube = labspec_fixture()
        x, values, metadata = parse_dataset(content, 'map.l6m')
        np.testing.assert_array_equal(x, wave)
        np.testing.assert_array_equal(values, cube)
        self.assertEqual(metadata['x_coordinates'], [-4., 0.])
        self.assertEqual(metadata['y_coordinates'], [1., 2., 3.])
        with self.assertRaisesRegex(ValueError, '6 条光谱'):
            parse_single(content, 'map.l6m')
        x, first, preview = parse_single(content, 'map.l6m', allow_selection_preview=True)
        self.assertTrue(preview['selection_required'])
        self.assertEqual(len(preview['spectrum_choices']), 6)
        for i in range(6):
            x, y, meta = parse_single(content, 'map.l6m', spectrum_index=i)
            np.testing.assert_array_equal(y, cube.reshape(6, 16)[i])
            self.assertFalse(meta['selection_required'])
            self.assertEqual(meta['selected_position']['row'], i // 2)
            self.assertEqual(meta['selected_position']['column'], i % 2)
        for index in (-1, 6, True):
            with self.assertRaises(ValueError): parse_single(content, 'map.l6m', spectrum_index=index)

    def test_npg_unit_conversion_and_signal_preservation(self):
        content, expected, signal = npg_fixture()
        x, y, meta = parse_single(content, 'point.npg')
        np.testing.assert_array_equal(x, expected)
        np.testing.assert_array_equal(y, signal)
        self.assertEqual(x[0], 0.)
        self.assertEqual(meta['axis_conversion'], 'wavelength_nm_to_raman_shift')
        self.assertEqual(meta['laser_wavelength_nm'], 532.)
        self.assertTrue(meta['conversion_required'])
        self.assertIn('未校准', meta['warnings'][0])
        xx, yy, _ = parse_single(standard_spectrum_content(x, y), 'standard.txt')
        np.testing.assert_array_equal(xx, x); np.testing.assert_array_equal(yy, y)

    def test_corrupt_and_unsupported_native_containers_reject(self):
        npg, _, _ = npg_fixture()
        lab, _, _ = labspec_fixture()
        bad_laser = bytearray(npg); struct.pack_into('<d', bad_laser, 0x38, 785.)
        bad_size = bytearray(npg); struct.pack_into('<I', bad_size, 0xb3, 2**30)
        for content, name in [(bytes(bad_laser), 'test.npg'), (bytes(bad_size), 'test.npg'),
                (npg[:-1], 'test.npg'), (npg.replace('Point'.encode('utf-16-le'), 'Image'.encode('utf-16-le')), 'test.npg'),
                (lab[:-24], 'test.l6m'), (lab.replace(b'1/cm', b'1/nm'), 'test.l6m'),
                (b'not an instrument file', 'test.npg'), (b'400,1\n401,2\n402,3', 'test.l6m')]:
            with self.subTest(name=name, length=len(content)), self.assertRaises(ValueError):
                parse_dataset(content, name)

    def test_archive_preserves_all_positions_and_numeric_precision(self):
        content, wave, cube = labspec_fixture()
        with zipfile.ZipFile(io.BytesIO(standard_spectra_archive(content, 'map.l6m'))) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['spectrum_count'], 6)
            for record in manifest['spectra']:
                x, y, _ = parse_single(archive.read(record['file']), record['file'])
                np.testing.assert_array_equal(x, wave)
                np.testing.assert_array_equal(y, cube[record['row'], record['column']])


if __name__ == '__main__': unittest.main()
