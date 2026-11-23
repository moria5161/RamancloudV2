"""Numerical regression and MAT round-trip tests; no private sample files."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pywt
from scipy.io import loadmat, savemat
from scipy.linalg import svd
from scipy.signal import savgol_filter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from denoising import tshi
from hyperspectral_io import read_mat, mat_result


def sample(height=8, width=9, bands=16):
    rng = np.random.default_rng(421)
    wave = np.linspace(400, 1800, bands)
    y, x = np.mgrid[:height, :width]
    cube = (20 + y[:, :, None] + x[:, :, None] * .3) * (1 + np.exp(-((wave - 1000) / 180) ** 2))
    return wave, cube + rng.normal(0, .4, cube.shape)


def mat_bytes(cube, wave):
    target = io.BytesIO()
    savemat(target, dict(cube=cube, x=wave.reshape(1, -1)))
    return target.getvalue()


def reference(cube, size=3, count=5, thr1=1e-5, thr2=.3):
    """Direct loops / full reconstructions from the supplied IIALRMA equations."""
    h, w, bands = cube.shape
    nim = cube.mean(axis=2)
    positions, scores = [], []
    for row in range(h - size + 1):
        for col in range(w - size + 1):
            tile = nim[row:row + size, col:col + size]
            a = tile - tile.mean()
            scores.append((a @ a).mean() / tile.mean() ** 2)
            positions.append((row, col))
    chosen_patches = [positions[i] for i in np.argsort(scores, kind='stable')[:count]]
    refs = np.array([cube[r:r + size, c:c + size].mean(axis=(0, 1)) for r, c in chosen_patches])
    refs = np.array([pywt.threshold(row, np.std(row) / 3, 'soft') for row in refs])
    u, s, vh = svd(cube.reshape(-1, bands).T, full_matrices=False)
    ds = savgol_filter(np.diff(np.log(s), n=2), 9, 3)
    hits = np.where(np.abs(ds) <= thr1)[0]
    considered = int(hits[0]) + 2 if len(hits) else len(s)
    snrs = []
    for n in range(1, considered + 1):
        recon = ((u[:, :n] * s[:n]) @ vh[:n]).T.reshape(h, w, bands)
        avg = np.array([recon[r:r + size, c:c + size].mean(axis=(0, 1)) for r, c in chosen_patches])
        snrs.append(10 * np.log10(np.mean(refs ** 2, axis=1) / np.mean((refs - avg) ** 2, axis=1)))
    gains = np.diff(np.column_stack([np.zeros(count), np.array(snrs).T]), axis=1).mean(axis=0)
    components = np.flatnonzero(gains >= thr2)
    result = ((u[:, components] * s[components]) @ vh[components]).T.reshape(h, w, bands)
    return result, components, gains


class TSHITests(unittest.TestCase):
    def test_matches_original_equations(self):
        wave, cube = sample()
        expected, components, gains = reference(cube)
        _, result, details = tshi.denoise(wave, cube, dict(half_width=20, windowsize=3, count=5))
        np.testing.assert_allclose(result, expected, rtol=1e-10, atol=1e-10)
        np.testing.assert_array_equal(details['selected_components'], components)
        np.testing.assert_allclose(details['mean_snr_gain_db'], gains, atol=1e-9)

    def test_center_bounds_and_no_mutation(self):
        wave, cube = sample()
        old = cube.copy()
        selected, result, d = tshi.denoise(wave, cube, dict(center_wavenumber=float(wave[7]), half_width=3, windowsize=3))
        np.testing.assert_array_equal(selected, wave[4:10])
        self.assertEqual(d['center_local_index'], 3)
        self.assertEqual(d['center_index'], 7)
        np.testing.assert_allclose(d['center_raw'], cube[:, :, 7])
        np.testing.assert_allclose(d['center_tshi'], result[:, :, 3])
        np.testing.assert_array_equal(cube, old)

    def test_zero_and_rank_deficient_and_tied_patches(self):
        wave = np.arange(4.)
        for cube in (np.zeros((5, 5, 4)), np.ones((5, 5, 4)), np.ones((5, 5, 4)) * np.arange(4)):
            _, result, d = tshi.denoise(wave, cube, dict(windowsize=3, count=100))
            self.assertTrue(np.isfinite(result).all())
            self.assertLessEqual(d['effective_rank'], 1)
            self.assertEqual(d['actual_count'], 9)
            self.assertEqual(len({(p['row'], p['column']) for p in d['smooth_regions']}), 9)
            json.dumps(d, allow_nan=False)

    def test_descending_and_standard_variance(self):
        wave, cube = sample()
        out, _, d = tshi.denoise(wave[::-1], cube[:, :, ::-1], dict(smoothness='variance', windowsize=3))
        self.assertTrue((np.diff(out) < 0).all())
        self.assertEqual(d['smoothness'], 'variance')

    def test_invalid_parameters(self):
        wave, cube = sample()
        for params in (dict(windowsize=4), dict(count=0), dict(half_width=2.5), dict(thr1=float('nan')),
                       dict(bm3d_enabled='true'), dict(center_wavenumber=5000), dict(unknown=1), dict(windowsize=31)):
            with self.subTest(params=params), self.assertRaises(ValueError):
                tshi.denoise(wave, cube, params)
        with self.assertRaises(ValueError):
            tshi.denoise(wave, cube[:, :, 0], {})
        with self.assertRaises(ValueError):
            tshi.denoise(wave, cube * 1e101, {})

    def test_no_components_is_explicit_error(self):
        wave, cube = sample()
        with self.assertRaisesRegex(ValueError, 'thr2'):
            tshi.denoise(wave, cube, dict(thr2=100, windowsize=3))

    def test_concurrency_gate_released(self):
        wave, cube = sample()
        tshi._GATE.acquire()
        try:
            with self.assertRaisesRegex(ValueError, '已有'):
                tshi.denoise(wave, cube, {})
        finally:
            tshi._GATE.release()
        tshi.denoise(wave, cube, {})

    def test_bm3d_missing_and_separate_result(self):
        wave, cube = sample()
        with patch.object(tshi, 'bm3d_available', return_value=False), self.assertRaisesRegex(ValueError, '可选依赖'):
            tshi.denoise(wave, cube, dict(bm3d_enabled=True))
        if not tshi.bm3d_available():
            self.skipTest('optional BM3D not installed')
        _, plain, _ = tshi.denoise(wave, cube, {})
        _, result, d = tshi.denoise(wave, cube, dict(bm3d_enabled=True, bm3d_sigma=.4))
        np.testing.assert_allclose(plain, result)
        self.assertEqual(np.asarray(d['bm3d_center_image']).shape, (8, 9))
        self.assertTrue(np.isfinite(d['bm3d_center_image']).all())


class MatTests(unittest.TestCase):
    def test_2d_orders_and_orientations(self):
        wave, cube = sample()
        for order in ('C', 'F'):
            for layout in ('bands_pixels', 'pixels_bands', 'auto'):
                flat = cube.reshape(-1, len(wave), order=order)
                values = flat if layout == 'pixels_bands' else flat.T
                result_wave, result, _ = read_mat(mat_bytes(values, wave), 8, 9, layout, order)
                np.testing.assert_array_equal(result_wave, wave)
                np.testing.assert_array_equal(result, cube)

    def test_3d_and_export_round_trip(self):
        wave, cube = sample()
        for values in (cube, np.moveaxis(cube, -1, 0)):
            _, result, _ = read_mat(mat_bytes(values, wave))
            np.testing.assert_array_equal(result, cube)
        wn, processed, details = tshi.denoise(wave, cube, {})
        content = mat_result(wn, processed, [dict(method='tshi', details=details)])
        out_wave, out, _ = read_mat(content, layout='rows_cols_bands')
        np.testing.assert_array_equal(out_wave, wn)
        np.testing.assert_array_equal(out, processed)
        self.assertIn('history_json', loadmat(io.BytesIO(content)))

    def test_mat_validation(self):
        wave, cube = sample()
        for content, options in ((b'MATLAB 7.3', {}), (b'broken', {}), (mat_bytes(cube[:, :, 0], wave), {}),
                                 (mat_bytes(cube.reshape(-1, 16).T, wave), {}),
                                 (mat_bytes(cube.reshape(-1, 16).T, wave), dict(height=7, width=8)),
                                 (mat_bytes(cube.astype(complex) + 1j, wave), {}),
                                 (mat_bytes(np.full(cube.shape, np.nan), wave), {}),
                                 (mat_bytes(cube, wave * 0), {})):
            with self.subTest(options=options), self.assertRaises(ValueError):
                read_mat(content, **options)

    def test_ambiguous_layout_is_not_guessed(self):
        wave = np.arange(8.)
        content = mat_bytes(np.ones((8, 9, 8)), wave)
        with self.assertRaisesRegex(ValueError, '无法唯一'):
            read_mat(content)
        self.assertEqual(read_mat(content, layout='rows_cols_bands')[1].shape, (8, 9, 8))


if __name__ == '__main__':
    unittest.main()
