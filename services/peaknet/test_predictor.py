"""Optional offline model checks; run in .venv-vib2mol after installing PeakNet."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).parent))
from peaknet_package import configuration


@unittest.skipUnless(configuration()[2], 'Install the supplied PeakNet package first')
class PeakNetModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from predictor import PeakNetPredictor
        profile, paths, _ = configuration()
        cls.predictor = PeakNetPredictor(profile, paths)

    def test_known_library_cache_identity_and_repeatability(self):
        index = next(int(i) for i, name in self.predictor.labels.items() if name == '乙醇')
        reference = self.predictor.reference(index)
        request = dict(spectrum=reference, preprocessing_mode='prepared', top_k=3)
        first, second = self.predictor.run(request), self.predictor.run(request)
        self.assertEqual(first['candidates'][0]['class_id'], index)
        self.assertEqual(first['candidates'], second['candidates'])
        self.assertEqual(len(first['model_input']['intensity']), 750)
        self.assertEqual([c['model_score'] for c in first['candidates']], sorted([c['model_score'] for c in first['candidates']], reverse=True))

    def test_airnet_processing_preserves_source_and_physical_grid(self):
        import numpy as np
        grid = np.linspace(220, 1800, 320)
        values = .2 + .0001 * grid + np.exp(-((grid - 1000) / 20) ** 2) + .4 * np.exp(-((grid - 1500) / 35) ** 2)
        source = dict(wavenumber=grid.tolist(), intensity=values.tolist())
        before = list(source['intensity'])
        result = self.predictor.prepare(source, 'auto')
        self.assertEqual(source['intensity'], before)
        self.assertEqual(len(result['preprocessing']['baseline']), 2500)
        self.assertEqual(result['model_input']['wavenumber'][0], 220)
        self.assertEqual(result['model_input']['wavenumber'][-1], 1800)
        self.assertTrue(np.isfinite(result['model_input']['intensity']).all())
        self.assertAlmostEqual(max(abs(y) for y in result['model_input']['intensity']), 1.)


if __name__ == '__main__':
    unittest.main()
