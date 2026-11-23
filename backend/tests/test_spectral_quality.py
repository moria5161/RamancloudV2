import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spectral_quality import quality_report, MAX_LOCATIONS, MAX_SPECTRA
from spectral_formats import parse_single


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.x = np.arange(256, dtype=float) + 400
        self.y = np.exp(-((np.arange(256) - 128) / 25) ** 2)

    def test_clean_smooth_spectrum_is_not_certified(self):
        report = quality_report(self.x, self.y)
        self.assertEqual(report['status'], 'no_obvious_issue')
        self.assertEqual(report['issues'], [])
        self.assertTrue(report['advisory'])
        self.assertFalse(report['blocking'])

    def test_spikes_are_candidates_with_original_positions_no_repair(self):
        y = self.y.copy()
        y[70], y[180] = 20, -15
        original = y.copy()
        report = quality_report(self.x, y)
        spikes = next(item for item in report['issues'] if item['code'] == 'narrow_spike')
        self.assertTrue({70, 180}.issubset({p['index'] for p in spikes['locations']}))
        for point in spikes['locations']:
            self.assertEqual(point['intensity'], y[point['index']])
            self.assertEqual(point['wavenumber'], self.x[point['index']])
        np.testing.assert_array_equal(y, original)

    def test_flat_top_not_confirmed_saturation_and_constant_is_separate(self):
        y = np.minimum(self.y, .65)
        flat = next(item for item in quality_report(self.x, y)['issues'] if item['code'] == 'flat_top')
        self.assertGreaterEqual(flat['locations'][0]['end_index'] - flat['locations'][0]['start_index'], 2)
        for signal in (np.zeros(256), np.full(256, -3.)):
            report = quality_report(self.x, signal)
            self.assertEqual([item['code'] for item in report['issues']], ['constant_signal'])

    def test_spacing_checks_ascending_descending_without_sorting(self):
        x = self.x.copy()
        x[150:] += 5
        a = quality_report(x, self.y)
        b = quality_report(x[::-1], self.y[::-1])
        self.assertEqual(a['spacing_cv'], b['spacing_cv'])
        self.assertIn('uneven_spacing', [item['code'] for item in a['issues']])
        self.assertEqual(quality_report(self.x[::-1], self.y[::-1])['issues'], [])

    def test_bounded_samples_locations_and_json_values(self):
        data = np.tile(self.y, (8, 10, 1))
        data[0, 0, 70] = 20
        report = quality_report(self.x, data)
        self.assertTrue(report['sampled'])
        self.assertEqual(report['spectra_checked'], MAX_SPECTRA)
        self.assertEqual(report['spectra_total'], 80)
        self.assertEqual(report['sampled_indices'][0], 0)
        self.assertEqual(report['sampled_indices'][-1], 79)
        self.assertEqual(quality_report(self.x, np.asfortranarray(data)), report)
        self.assertEqual(next(i for i in report['issues'] if i['code'] == 'narrow_spike')['locations'][0]['row'], 0)
        y = np.tile([0., 1.] + [0.] * 18, 200)
        many = next(i for i in quality_report(np.arange(len(y)), y)['issues'] if i['code'] == 'narrow_spike')
        self.assertGreater(many['count'], MAX_LOCATIONS)
        self.assertEqual(len(many['locations']), MAX_LOCATIONS)
        self.assertTrue(many['truncated'])
        json.dumps(report, allow_nan=False)

    def test_scale_invariance_and_extreme_finite_input(self):
        codes = lambda y: [item['code'] for item in quality_report(self.x, y)['issues']]
        y = self.y.copy()
        y[70] = 20
        self.assertEqual(codes(y), codes(y * 1e-200))
        self.assertEqual(codes(y), codes(y * 1e200))
        report = quality_report([1e-308, 2e-308, 1e308], [1., 2., 1.])
        json.dumps(report, allow_nan=False)

    def test_invalid_values_still_fail_format_check(self):
        for data in (b'400,1\n401,NaN\n402,3', b'400,1\n400,2\n402,3'):
            with self.assertRaises(ValueError):
                parse_single(data, 'invalid.csv')
        x, y, meta = parse_single(b'400,1\n401,1\n402,1', 'constant.csv')
        self.assertEqual(meta['quality_check']['status'], 'review')
        np.testing.assert_array_equal(y, [1, 1, 1])
