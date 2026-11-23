"""Numerical and integration contracts for the imported despike algorithm."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preprocessing.despike import despike_matrix, validate_order
from ai_workflow import validate_steps, local_plan, diagnostics


def spectrum():
    x = np.linspace(400, 1800, 501)
    samples = np.arange(501)
    clean = 20 + 80 * np.exp(-((samples - 320) / 25) ** 2) + .2 * np.sin(samples * .71)
    noisy = clean.copy()
    noisy[100] += 800
    noisy[200] -= 700
    return x, clean, noisy


class DespikeTests(unittest.TestCase):
    def test_removes_positive_and_negative_spikes_without_smoothing_real_broad_peak(self):
        x, clean, noisy = spectrum()
        original = noisy.copy()
        output, details = despike_matrix(x, noisy[None, :], {})
        self.assertEqual(details['num_cosmic_rays'], 2)
        self.assertEqual([p['peak_idx'] for p in details['cosmic_rays']], [100, 200])
        self.assertEqual([p['ptype'] for p in details['cosmic_rays']], ['max', 'min'])
        self.assertLess(abs(output[0, 100] - clean[100]), .5)
        self.assertLess(abs(output[0, 200] - clean[200]), .5)
        np.testing.assert_array_equal(output[0, 250:], noisy[250:])
        np.testing.assert_array_equal(noisy, original)
        self.assertEqual(output.shape, (1, len(x)))

    def test_repairs_only_the_impulse_and_uses_the_physical_axis(self):
        x, _, noisy = spectrum()
        output, details = despike_matrix(x[::-1], noisy[None, :], {'threshold': 100, 'fwhm_threshold': 4})
        expected = noisy.copy()
        for index in [100, 200]: expected[index] = (noisy[index - 1] + noisy[index + 1]) / 2
        np.testing.assert_allclose(output[0], expected, rtol=0, atol=1e-12)
        self.assertEqual(details['cosmic_rays'][0]['wavenumber'], x[::-1][100])

    def test_preserves_a_resolved_narrow_peak_and_repairs_a_separate_impulse(self):
        # The peak shape matches the measured silicon example, without encoding
        # a protected chemical identity or a special 520 cm-1 exclusion window.
        axis = np.linspace(1200, 200, 160)
        signal = np.full(160, 120.)
        signal[74:85] = [1306.8, 1715.9, 2475.5, 4820.9, 13516.3, 21792.7,
                         19435.2, 13733.2, 7410.6, 2497.2, 1134.3]
        original = signal.copy()
        signal[30] += 8000
        out, details = despike_matrix(axis, signal[None, :], {})
        np.testing.assert_array_equal(out[0, 74:85], signal[74:85])
        self.assertEqual(out[0, 30], original[30])
        self.assertGreater(details['protected_candidates'], 0)
        self.assertEqual(details['repaired_spikes'], 1)

    def test_nonuniform_axis_interpolation_is_not_index_interpolation(self):
        axis = np.linspace(1., 2., 100) ** 3
        clean = 3 * axis + 20
        signal = clean.copy(); signal[40] += 1000
        out, _ = despike_matrix(axis, signal[None, :], {})
        np.testing.assert_allclose(out[0], clean, atol=1e-12)

    def test_flat_spectrum_and_batch_are_independent(self):
        x, _, noisy = spectrum()
        data = np.vstack([noisy, np.ones(len(x)), noisy * 2])
        output, details = despike_matrix(x, data, {})
        self.assertEqual(details['spectra_count'], 3)
        self.assertEqual(details['num_cosmic_rays'], 4)
        np.testing.assert_array_equal(output[1], data[1])
        np.testing.assert_allclose(output[2], output[0] * 2)

    def test_invalid_values_parameters_and_tiny_inputs_are_rejected(self):
        x, _, noisy = spectrum()
        for params in ({'threshold': True}, {'threshold': -1}, {'threshold': float('nan')}, {'fwhm_threshold': 0},
                       {'fwhm_threshold': None}, {'interpolation': 'cubic'}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                despike_matrix(x, noisy[None, :], params)
        with self.assertRaises(ValueError):
            despike_matrix(x[:4], noisy[None, :4], {})
        invalid = noisy.copy(); invalid[0] = np.inf
        with self.assertRaises(ValueError):
            despike_matrix(x, invalid[None, :], {})

    def test_order_nullable_defaults_skipping_and_duplicate_validation(self):
        x, _, _ = spectrum()
        spike = dict(type='despike', method='despike', params={}, enabled=True)
        noise = dict(type='denoise', method='sg', params={'window_size': 7, 'order': 3})
        validated = validate_steps([spike, noise], x)
        self.assertIsNone(validated[0]['params']['threshold'])
        self.assertEqual(validated[0]['params']['fwhm_threshold'], 4)
        with self.assertRaisesRegex(ValueError, '降噪之前'):
            validate_steps([noise, spike], x)
        with self.assertRaisesRegex(ValueError, '只能包含一个'):
            validate_steps([spike, spike], x)
        validate_steps([noise, dict(spike, enabled=False)], x)
        validate_order([dict(noise, method='skip'), spike])

    def test_explicit_despike_only_goal_does_not_add_denoising(self):
        x, _, noisy = spectrum()
        plan = local_plan('只去鬼峰，不降噪，不去基线', '', diagnostics(x, noisy))
        self.assertEqual([s['type'] for s in plan['steps']], ['despike'])


if __name__ == '__main__':
    unittest.main()
