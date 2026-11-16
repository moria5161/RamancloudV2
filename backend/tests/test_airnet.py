import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from algorithms.processing import correct_baseline_batch, validated_parameters


class AirNetContractTests(unittest.TestCase):
    def test_no_adjustable_parameters(self):
        self.assertEqual(validated_parameters('airnet', {}), {})
        with self.assertRaisesRegex(ValueError, 'unsupported parameters'):
            validated_parameters('airnet', {'itermax': 10})

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'Optional PyTorch is not installed')
    def test_batch_pipeline_reconstructs_raw_and_tracks_cuts(self):
        matrix = np.arange(40., dtype=float).reshape(2, 20)
        wave = np.arange(20.)
        with patch('algorithms.baseline_cor.airnet.airnet_process', return_value=matrix - 3) as infer:
            out_wave, corrected, baseline, history = app.apply_pipeline(wave, matrix, [
                app.Step(type='baseline', method='airnet'),
                app.Step(type='cut', params={'start': 3, 'end': 12}),
            ])
        infer.assert_called_once()
        np.testing.assert_allclose(corrected + baseline, matrix[:, 3:13])
        np.testing.assert_array_equal(out_wave, wave[3:13])
        self.assertEqual(history[0], {'type': 'baseline', 'method': 'airnet', 'params': {}})

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'Optional PyTorch is not installed')
    def test_invalid_input_and_constant_spectra(self):
        from algorithms.baseline_cor.airnet import airnet_process
        for matrix in [np.zeros((1, 3)), np.array([[1, 2, 3, float('nan')]])]:
            with self.assertRaises(ValueError):
                airnet_process(matrix)
        raw = np.array([[0.] * 10, [15.] * 10])
        corrected, baseline = correct_baseline_batch(raw, {}, 'airnet')
        np.testing.assert_array_equal(corrected, np.zeros_like(raw))
        np.testing.assert_array_equal(baseline, raw)

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'Optional PyTorch is not installed')
    def test_missing_weights_are_explicit(self):
        from algorithms.baseline_cor.airnet import load_model
        load_model.cache_clear()
        with patch.dict('os.environ', {'RAMANCLOUD_AIRNET_MODEL': '/nonexistent/airnet.pth'}):
            with self.assertRaisesRegex(ValueError, 'model is unavailable'):
                load_model()

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'Optional PyTorch is not installed')
    def test_default_weights_belong_to_baseline_algorithms(self):
        from algorithms.baseline_cor.airnet import DEFAULT_MODEL_PATH
        expected = Path(__file__).resolve().parents[1] / 'algorithms' / 'baseline_cor' / 'models' / 'airnet.pth'
        self.assertEqual(DEFAULT_MODEL_PATH, expected)


if __name__ == '__main__':
    unittest.main()
