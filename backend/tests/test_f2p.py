import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from algorithms.processing import DENOISE_METHODS, denoise, denoise_batch, validated_parameters


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Optional PyTorch is not installed')
class F2PTests(unittest.TestCase):
    def setUp(self):
        from algorithms.denoising.f2p import inference
        self.inference = inference
        app.DATASETS.clear()

    def identity_model(self):
        import torch

        class RecordingIdentity(torch.nn.Module):
            num_patches = 100
            patch_size = 16

            def __init__(self):
                super().__init__()
                self.calls = []

            def forward(self, tensor):
                if not torch.is_inference_mode_enabled():
                    raise AssertionError('Inference must disable gradients')
                self.calls.append(len(tensor))
                return tensor

        return RecordingIdentity().eval(), torch.device('cpu')

    def test_registered_without_training_parameters(self):
        self.assertIn('f2p', DENOISE_METHODS)
        self.assertEqual(validated_parameters('f2p', {}), {})
        with self.assertRaisesRegex(ValueError, 'unsupported parameters'):
            validated_parameters('f2p', {'mask_ratio': .05})

    def test_batches_are_at_most_64_and_leave_input_unchanged(self):
        raw = np.tile(np.linspace(1, 10, 1600), (65, 1)) + np.arange(65)[:, None]
        original = raw.copy()
        model, device = self.identity_model()
        with patch.object(self.inference, 'load_model', return_value=(model, device)):
            output = denoise_batch(raw, {}, 'f2p')
        self.assertEqual(model.calls, [64, 1])
        np.testing.assert_array_equal(raw, original)
        np.testing.assert_allclose(output, raw, rtol=1e-6, atol=1e-5)

    def test_constant_and_invalid_spectra(self):
        raw = np.array([[0.] * 10, [15.] * 10])
        with patch.object(self.inference, 'load_model') as load:
            np.testing.assert_array_equal(denoise_batch(raw, {}, 'f2p'), raw)
            load.assert_not_called()
        for invalid in [np.zeros((1, 3)), np.ones(10), np.array([[1, 2, 3, np.nan]])]:
            with self.assertRaisesRegex(ValueError, 'finite spectra'):
                self.inference.denoise_batch(invalid)

    def test_cut_and_hyperspectral_processing_keep_axes_coordinates(self):
        wave = np.arange(100., 500.)
        raw = np.stack([np.sin(wave / 25) + 10, np.cos(wave / 30) + 20])
        original = raw.copy()
        dataset_id = app.register_dataset(wave, raw, 'time_series', 'electrolyte.txt', {'time': [2.5, 9.]})
        model, device = self.identity_model()
        with patch.object(self.inference, 'load_model', return_value=(model, device)):
            output = app.process_cube(app.CubePayload(wavenumber=wave.tolist(), dataset_id=dataset_id,
                steps=[app.Step(type='cut', params={'start': 200, 'end': 350}),
                       app.Step(type='denoise', method='f2p')]))['data']
        processed = app.get_dataset(output['processed_dataset_id'])
        np.testing.assert_array_equal(output['wavenumber'], wave[100:251])
        self.assertEqual(processed['data'].shape, (2, 151))
        self.assertEqual(processed['coordinates'], {'time': [2.5, 9.]})
        np.testing.assert_array_equal(app.get_dataset(dataset_id)['data'], original)
        self.assertEqual(output['history'][-1], {'type': 'denoise', 'method': 'f2p', 'params': {}})

    def test_online_budget_uses_fixed_model_input_length(self):
        with patch('app.current_owner', return_value='workspace'), patch('app.MAX_NUMERIC_VALUES', 1600):
            with self.assertRaises(HTTPException) as error:
                app.apply_pipeline(np.arange(4.), np.ones((2, 4)), [app.Step(type='denoise', method='f2p')])
        self.assertEqual(error.exception.status_code, 413)

    def test_missing_weights_are_explicit(self):
        self.inference.load_model.cache_clear()
        try:
            with patch.dict('os.environ', {'RAMANCLOUD_F2P_MODEL': '/nonexistent/f2p.pth'}):
                with self.assertRaisesRegex(ValueError, 'F2P model is unavailable'):
                    self.inference.load_model()
        finally:
            self.inference.load_model.cache_clear()

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / 'algorithms/denoising/f2p/models/f2p_rpe_best.pth').is_file(), 'Private F2P weights are not installed')
    def test_pretrained_weights_are_inference_only_and_output_is_deterministic(self):
        import torch
        state = torch.load(self.inference.DEFAULT_MODEL_PATH, map_location='cpu', weights_only=True)
        self.assertTrue(all(isinstance(value, torch.Tensor) for value in state.values()))
        self.assertNotIn('optimizer_state_dict', state)
        self.assertNotIn('scheduler_state_dict', state)
        model, _ = self.inference.load_model()
        self.assertFalse(model.training)
        x = np.linspace(0, 1, 400)
        raw = 10 + 4 * x + 5 * np.exp(-((x - .5) / .02) ** 2)
        raw += np.random.default_rng(42).normal(0, .5, len(x))
        output = denoise(raw, {}, 'f2p')
        repeated = denoise(raw, {}, 'f2p')
        self.assertEqual(output.shape, raw.shape)
        self.assertTrue(np.isfinite(output).all())
        self.assertGreater(np.max(np.abs(output - raw)), 1e-4)
        np.testing.assert_allclose(repeated, output)
        np.testing.assert_allclose(output.mean(), raw.astype(np.float32).mean(), rtol=1e-6)


if __name__ == '__main__':
    unittest.main()
