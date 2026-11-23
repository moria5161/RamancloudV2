"""Import regression fixtures are synthetic; not claims about every vendor version."""
import dataclasses
import io
import struct
import sys
import unittest
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from scipy.io import savemat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spectral_formats import parse_dataset, parse_single, standard_spectrum_content


def teaching_spectrum():
    header = 'Instrument:  EduRaman Pro\r\nThe Light Source Type:  531.82nm laser\r\n'
    header += 'pixel(2026/09/30 10:37:58)\twavelength(2026/09/30 10:37:58)\twavenumber(2026/09/30 10:37:58)\tramanshift(2026/09/30 10:37:58)\tintensity(2026/09/30 10:37:58)\r\n'
    rows = [f'{i+1}\t535.153\t{18686.25-i*2.5}\t{117.10+i*2.5}\t{2181+i}' for i in range(16)]
    return (header + '\r\n'.join(rows) + '\r\n').encode('utf-8-sig')


def xlsx(rows, second=False):
    book = Workbook()
    for row in rows:
        book.active.append(row)
    if second:
        book.create_sheet('second')
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def wdf_fixture(spectra=1, unit=1, mapping=False):
    from wdf.wdf import WdfHeader
    defaults = {field.name: b'' if field.type is bytes else 0 for field in dataclasses.fields(WdfHeader) if not field.name.startswith('_')}
    defaults.update(signature=int.from_bytes(b'WDF1', 'little'), size=512, version=1, ntracks=1,
                    npoints=8, nspectra=spectra, ncollected=spectra, xlistcount=8, type=3 if mapping else 1 if spectra == 1 else 2)
    header = struct.pack(WdfHeader._PACKSTR, *defaults.values())
    def block(name, payload):
        return struct.pack('<4sIQ', name, 0, 16 + len(payload)) + payload
    wave = np.arange(8, dtype='<f4')
    data = np.arange(8 * spectra, dtype='<f4')
    result = header + block(b'DATA', data.tobytes()) + block(b'XLST', struct.pack('<II', 1, unit) + wave.tobytes())
    if mapping:
        values = struct.pack('<I', 2)
        for kind, coords in ((3, [0, 1, 0, 1]), (4, [0, 0, 1, 1])):
            values += struct.pack('<II16s', kind, 5, b'coordinate') + struct.pack('<4d', *coords)
        result += block(b'ORGN', values)
    return result


class FormatTests(unittest.TestCase):
    def test_teaching_export_uses_raman_shift_instead_of_absolute_wavenumber(self):
        x, y, meta = parse_single(teaching_spectrum(), 'teaching.txt')
        np.testing.assert_array_equal(x, [117.10 + i * 2.5 for i in range(16)])
        np.testing.assert_array_equal(y, np.arange(2181, 2197))
        self.assertEqual(meta['wavenumber_column'], 4)
        self.assertEqual(meta['intensity_column'], 5)
        self.assertEqual(meta['instrument'], 'EduRaman Pro')
        self.assertTrue(meta['conversion_required'])
        self.assertEqual(meta['axis_unit'], 'cm^-1')
        for invalid in (teaching_spectrum().replace(b'117.1\t', b'nan\t'),
                        teaching_spectrum().replace(b'119.6\t', b'117.1\t')):
            with self.assertRaises(ValueError):
                parse_single(invalid, 'teaching.txt')

    def test_ocean_style_blank_column_is_already_two_columns(self):
        content = b'RamanShift:203\t\t\r\n' + b'\r\n'.join(f'{-100+i*2.75}\t{-1.56+i}\t'.encode() for i in range(16))
        x, y, meta = parse_single(content, 'ocean.txt')
        self.assertEqual(len(x), 16)
        self.assertEqual(x[0], -100)
        self.assertEqual(y[0], -1.56)
        self.assertFalse(meta['conversion_required'])
        self.assertEqual(meta['effective_columns'], 2)
        self.assertTrue(meta['warnings'])

    def test_standard_export_round_trips_values_and_point_order(self):
        x = np.array([403.1234567890123, 402.0000000000001, 400.1234567890123])
        y = np.array([-1.560000000000001, 123456.7890123456, 1e-17])
        exported = standard_spectrum_content(x, y)
        xx, yy, meta = parse_single(exported, 'standard.txt')
        np.testing.assert_array_equal(xx, x)
        np.testing.assert_array_equal(yy, y)
        self.assertFalse(meta['conversion_required'])
        self.assertEqual(meta['axis_unit'], 'cm^-1')

    def test_encodings_and_named_columns(self):
        text = '# 仪器导出\n波数(cm-1);强度;备注\n400;1;A\n401;2;B\n402;3;C\n'
        for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
            x, y, meta = parse_single(text.encode(encoding), 'sample.csv')
            np.testing.assert_array_equal(x, [400, 401, 402])
            np.testing.assert_array_equal(y, [1, 2, 3])
            self.assertEqual(meta['intensity_column'], 2)

    def test_numeric_variants_and_sparse_unused_column(self):
        for source in (b'400,5;1D1\n401,5;2D1\n402,5;3D1', b'400.5,,10\n401.5,,20\n402.5,,30'):
            x, y, _ = parse_single(source)
            np.testing.assert_array_equal(x, [400.5, 401.5, 402.5])
            np.testing.assert_array_equal(y, [10, 20, 30])
        x, y, _ = parse_single(b',Wavenumber,Intensity\n,400,1\n,401,2\n,402,3')
        np.testing.assert_array_equal(x, [400, 401, 402])
        np.testing.assert_array_equal(y, [1, 2, 3])

    def test_nanophoton_auto_overrides_stale_instrument_selection(self):
        source = b'Wavenumber\tx0_y0\tx1_y0\tx0_y1\tx1_y1\n400\t1\t2\t3\t4\n401\t5\t6\t7\t8\n402\t9\t10\t11\t12'
        x, cube, meta = parse_dataset(source, 'map.txt', mode='imaging', hint='Horiba')
        self.assertEqual(cube.shape, (2, 2, 3))
        np.testing.assert_array_equal(cube[1, 0], [3, 7, 11])
        self.assertEqual(meta['detected_format'], 'nanophoton_columns')

    def test_long_table_and_coordinate_integrity(self):
        header = 'X,Y,Raman shift (cm-1),Intensity\n'
        rows = [f'{x},{y},{wave},{10*x+100*y+wave}' for y in range(2) for x in range(3) for wave in (400, 401, 402)]
        _, cube, _ = parse_dataset((header + '\n'.join(rows)).encode(), mode='imaging')
        self.assertEqual(cube.shape, (2, 3, 3))
        self.assertEqual(cube[1, 2, 0], 520)
        for bad in (rows[:-3], rows + rows[:3], rows[:-1]):
            with self.assertRaises(ValueError):
                parse_dataset((header + '\n'.join(bad)).encode(), mode='imaging')

    def test_matrix_requires_layout_and_spatial_shape(self):
        source = b'400,1,2,3,4\n401,5,6,7,8\n402,9,10,11,12'
        with self.assertRaisesRegex(ValueError, '多列'):
            parse_dataset(source)
        with self.assertRaisesRegex(ValueError, '行数'):
            parse_dataset(source, mode='imaging', hint='columns')
        _, cube, _ = parse_dataset(source, mode='imaging', hint='columns', height=2, width=2, pixel_order='C')
        self.assertEqual(cube.shape, (2, 2, 3))
        np.testing.assert_array_equal(cube[1, 0], [3, 7, 11])
        source = b'Unused,,Wavenumber,Spectrum A,Spectrum B\n1,,400,10,20\n2,,401,11,21\n3,,402,12,22'
        with self.assertRaisesRegex(ValueError, '多列'):
            parse_dataset(source, mode='time_series')
        wave, series, _ = parse_dataset(source, mode='time_series', hint='columns')
        np.testing.assert_array_equal(wave, [400, 401, 402])
        self.assertEqual(series.shape, (3, 3))

    def test_reject_invalid_signal_not_silently_skip(self):
        for source in (b'400,1\n401,nan\n402,3', b'400,1\n401,inf\n402,3', b'400,1\n401,\n402,3',
                       b'400,1\nbad,2\n402,3', b'400,1\n400,2\n402,3', b'400,1\n402,2\n401,3'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_single(source)
        with self.assertRaisesRegex(ValueError, '波长'):
            parse_single(b'Wavelength(nm),Intensity\n400,1\n401,2\n402,3')

    def test_xlsx_real_data_and_rejected_formula_multisheet(self):
        rows = [['Wavenumber', 'Intensity'], [400, 1], [401, 2], [402, 3]]
        x, y, meta = parse_single(xlsx(rows), 'sample.xlsx')
        self.assertEqual(meta['container'], 'XLSX')
        np.testing.assert_array_equal(y, [1, 2, 3])
        with self.assertRaisesRegex(ValueError, '公式'):
            parse_single(xlsx([['Wavenumber', 'Intensity'], [400, '=1+1']]), 'sample.xlsx')
        with self.assertRaisesRegex(ValueError, '多个工作表'):
            parse_single(xlsx(rows, True), 'sample.xlsx')
        with self.assertRaises(ValueError):
            parse_single(b'400,1\n401,2\n402,3', 'renamed.xlsx')

    def test_jcamp_real_reader_scaling_units_and_mode(self):
        source = b'##TITLE=Synthetic Raman\n##JCAMP-DX=4.24\n##DATA TYPE=RAMAN SPECTRUM\n##XUNITS=1/CM\n##YUNITS=COUNTS\n##XFACTOR=1\n##YFACTOR=2\n##FIRSTX=400\n##LASTX=407\n##NPOINTS=8\n##XYDATA=(X++(Y..Y))\n400 1 2 3 4 5 6 7 8\n##END=\n'
        x, y, meta = parse_single(source, 'sample.jdx')
        np.testing.assert_array_equal(x, np.arange(400, 408))
        np.testing.assert_array_equal(y, np.arange(1, 9) * 2)
        self.assertEqual(meta['detected_format'], 'jcamp_dx')
        for bad in (source.replace(b'RAMAN', b'INFRARED'), source.replace(b'1/CM', b'NM'), source + source,
                    source.replace(b'NPOINTS=8', b'NPOINTS=9'), source.replace(b'NPOINTS=8', b'NPOINTS=999999999')):
            with self.assertRaises(ValueError):
                parse_single(bad, 'sample.jdx')

    def test_wdf_actual_library_and_malformed_blocks(self):
        x, y, meta = parse_single(wdf_fixture(), 'sample.wdf')
        np.testing.assert_array_equal(x, np.arange(8))
        np.testing.assert_array_equal(y, np.arange(8))
        self.assertEqual(meta['reader'], 'renishaw-wdf 1.3.1')
        _, data, _ = parse_dataset(wdf_fixture(2), mode='time_series')
        self.assertEqual(data.shape, (2, 8))
        _, cube, _ = parse_dataset(wdf_fixture(4, mapping=True), mode='imaging')
        self.assertEqual(cube.shape, (2, 2, 8))
        np.testing.assert_array_equal(cube[1, 0], np.arange(16, 24))
        for bad in (wdf_fixture(unit=3), wdf_fixture()[:-2], b'WDF1' + b'\0' * 508):
            with self.assertRaises(ValueError):
                parse_single(bad, 'sample.wdf')

    def test_native_unsupported_and_mat_magic(self):
        for extension in ('.spc', '.wip', '.ngs', '.l6s', '.l6m', '.l6v', '.spa', '.spg', '.0'):
            with self.assertRaisesRegex(ValueError, '导出'):
                parse_dataset(b'400,1\n401,2\n402,3', 'sample' + extension)
        stream = io.BytesIO()
        savemat(stream, dict(cube=np.ones((2, 4, 5)), x=np.arange(5).reshape(1, -1)))
        _, cube, meta = parse_dataset(stream.getvalue(), 'renamed.txt', mode='imaging')
        self.assertEqual(cube.shape, (2, 4, 5))
        self.assertEqual(meta['detected_format'], 'mat_cube')

    def test_bundled_legacy_samples_still_import(self):
        root = Path(__file__).resolve().parents[1] / 'samples'
        for name, mode in [('tutorial_raman.txt', 'spectrum'), ('Bacteria.txt', 'spectrum'), ('ULF.txt', 'spectrum'),
                           ('imaging_Horiba.txt', 'imaging'), ('time_series_Horiba.txt', 'time_series'), ('time_series_Nanophoton.txt', 'time_series')]:
            with self.subTest(name=name):
                wave, data, meta = parse_dataset((root / name).read_bytes(), name, mode)
                self.assertEqual(data.shape[-1], len(wave))
                self.assertEqual(meta['detected_mode'], mode)


if __name__ == '__main__':
    unittest.main()
