import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi import HTTPException
from pybaselines import Baseline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from algorithms.processing import correct_baseline, denoise, denoise_batch, validated_parameters


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        app.DATASETS.clear()
        self.wave = np.linspace(100, 2000, 400)
        x = np.arange(400)
        self.y = 100 + .03 * x + .0003 * x ** 2 + 30 * np.exp(-((x - 170) / 12) ** 2)
        self.y += np.random.default_rng(42).normal(0, 2, 400)

    def test_pybaselines_methods_match_v1_library_contract(self):
        for name, api in [('airpls', 'airpls'), ('aspls', 'aspls'), ('imodpoly', 'imodpoly'), ('penalizedpoly', 'penalized_poly'), ('rollingball', 'rolling_ball'), ('mormol', 'mormol'), ('irsqr', 'irsqr'), ('snip', 'snip')]:
            with self.subTest(name=name):
                params = validated_parameters(name, {})
                if name == 'snip':
                    params['decreasing'] = True
                expected, _ = getattr(Baseline(x_data=np.linspace(0, 400, 400)), api)(self.y, **params)
                corrected, baseline = correct_baseline(self.y, {}, name)
                np.testing.assert_allclose(baseline, expected)
                np.testing.assert_allclose(corrected + baseline, self.y)

    def test_parameters_change_results(self):
        cases = [('airpls', {'lam': 100}), ('aspls', {'lam': 100}), ('aabs', {'Ln': 10, 'Lb': 80}), ('imodpoly', {'poly_order': 1}), ('penalizedpoly', {'poly_order': 1}), ('airpls_old', {'diff_order': 2}), ('rollingball', {'half_window': 10}), ('mormol', {'half_window': 10}), ('irsqr', {'quantile': .3}), ('snip', {'max_half_window': 8, 'smooth_half_window': 0})]
        cases += [('aabs', {'Ln': 10}), ('aabs', {'Lb': 80}), ('airpls', {'diff_order': 1}), ('aspls', {'diff_order': 2}), ('airpls_old', {'lam': 1000}), ('snip', {'smooth_half_window': 0})]
        for method, params in cases:
            with self.subTest(method=method):
                self.assertGreater(np.max(np.abs(correct_baseline(self.y, {}, method)[0] - correct_baseline(self.y, params, method)[0])), 1e-5)
        for method, params in [('sg', {'window_size': 15}), ('sg', {'order': 2}), ('wtd', {'level': 2}), ('wtd', {'wavelet': 'db4'}), ('peer', {'loops': 1}), ('peer', {'half_k_threshold': 0})]:
            with self.subTest(method=method):
                self.assertGreater(np.max(np.abs(denoise(self.y, {}, method) - denoise(self.y, params, method))), 1e-5)

    def test_zero_and_alias_parameters(self):
        self.assertEqual(validated_parameters('snip', {'smooth_half_window': 0})['smooth_half_window'], 0)
        self.assertEqual(validated_parameters('airpls', {'lambda_': 200, 'order_': 2}), {'lam': 200., 'diff_order': 2})

    def test_invalid_parameters_rejected(self):
        for method, params in [('sg', {'window_size': 8}), ('sg', {'order': 7}), ('wtd', {'level': 20}), ('peer', {'loops': 0}), ('airpls', {'lam': float('nan')}), ('aabs', {'unknown': 1}), ('snip', {'max_half_window': 300})]:
            with self.subTest(method=method, params=params), self.assertRaises(ValueError):
                if method in ('sg', 'wtd', 'peer'):
                    denoise(self.y, params, method)
                else:
                    correct_baseline(self.y, params, method)

    def test_tsvd_curvature_filter_and_parameter(self):
        matrix = np.random.default_rng(2).normal(size=(8, 400)) + self.y
        u, s, vh = np.linalg.svd(matrix, full_matrices=False)
        mask = np.ones(len(s), dtype=bool)
        mask[1:-1] = np.abs(np.diff(np.log1p(s), n=2)) > .001
        np.testing.assert_allclose(denoise_batch(matrix, {}, 'tsvd'), (u * np.where(mask, s, 0)) @ vh)
        self.assertGreater(np.max(np.abs(denoise_batch(matrix, {}, 'tsvd') - denoise_batch(matrix, {'threshold': 100}, 'tsvd'))), .01)

    def test_baseline_then_cut_and_multiple_baselines(self):
        steps = [app.Step(type='baseline', method='imodpoly'), app.Step(type='baseline', method='rollingball'), app.Step(type='cut', params={'start': 300, 'end': 1600})]
        wave, out, baseline, history = app.apply_pipeline(self.wave, self.y, steps)
        mask = (self.wave >= 300) & (self.wave <= 1600)
        np.testing.assert_allclose(out + baseline, self.y[mask])
        self.assertEqual(len(wave), len(baseline))
        self.assertEqual(history[0]['params']['poly_order'], 3)

    def test_batch_results_and_joint_tsvd(self):
        spectra = [app.BatchSpectrum(filename=str(i), wavenumber=self.wave.tolist(), intensity=(self.y + np.random.default_rng(i).normal(size=400)).tolist()) for i in range(5)]
        steps = [app.Step(type='denoise', method='tsvd', params={'threshold': 100})]
        result = app.process_batch(app.BatchPayload(spectra=spectra, steps=steps))['data']['spectra']
        expected = denoise_batch(np.array([item.intensity for item in spectra]), {'threshold': 100}, 'tsvd')
        np.testing.assert_allclose([item['intensity'] for item in result], expected)
        spectra[1].wavenumber[0] += 1
        with self.assertRaisesRegex(ValueError, 'identical'):
            app.process_batch(app.BatchPayload(spectra=spectra, steps=steps))
        result = app.process_batch(app.BatchPayload(spectra=spectra, steps=[app.Step(type='denoise', method='sg')]))['data']['spectra']
        self.assertEqual(result[1]['wavenumber'][0], spectra[1].wavenumber[0])

    def test_baseline_cube_export_preserves_coordinates_and_raw(self):
        matrix = np.stack([self.y, self.y + 10])
        coordinates = {'time': [2.5, 9]}
        dataset_id = app.register_dataset(self.wave, matrix, 'time_series', 'sample.txt', coordinates)
        result = app.process_cube(app.CubePayload(wavenumber=self.wave.tolist(), dataset_id=dataset_id, steps=[app.Step(type='baseline', method='imodpoly')]))['data']
        baseline = app.get_dataset(result['baseline_dataset_id'])
        np.testing.assert_array_equal(app.get_dataset(dataset_id)['data'], matrix)
        np.testing.assert_allclose(app.get_dataset(result['processed_dataset_id'])['data'] + baseline['data'], matrix)
        exported = app.download(app.DownloadPayload(wavenumber=result['wavenumber'], dataset_id=result['baseline_dataset_id'], format='mapping'))
        wave, data, coords = app.read_time_series(exported.body, 'Horiba')
        np.testing.assert_allclose(data, baseline['data'])
        self.assertEqual(coords['time'], coordinates['time'])

    def test_cache_expiry_and_release(self):
        with patch('app.time.monotonic', return_value=100):
            dataset_id = app.register_dataset(self.wave, self.y[None], 'time_series', 'sample.txt', {})
        with patch('app.time.monotonic', return_value=1901), self.assertRaises(HTTPException):
            app.get_dataset(dataset_id)
        self.assertEqual(app.delete_dataset(dataset_id)['code'], 0)


if __name__ == '__main__':
    unittest.main()
