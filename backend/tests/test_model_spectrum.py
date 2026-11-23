import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_workflow import model_spectrum


class ModelSpectrumTests(unittest.TestCase):
    def test_small_spectrum_transmits_every_paired_value(self):
        x=np.arange(100,dtype=float);y=x*.2
        context=model_spectrum(x,y)
        np.testing.assert_allclose(context['sample'],np.column_stack([x,y]),rtol=1e-7,atol=1e-12)
        self.assertEqual(context['spectral_data']['sampling'],'full')

    def test_long_spectrum_keeps_narrow_peak_and_extrema_with_bounded_context(self):
        x=np.arange(20000,dtype=float);y=np.sin(x/100)+10
        y[12345]=900;y[17891]=-300
        context=model_spectrum(x,y);sample=np.array(context['sample'])
        self.assertLessEqual(len(sample),320)
        self.assertIn([12345.,900.],sample.tolist())
        self.assertIn([17891.,-300.],sample.tolist())
        self.assertEqual(context['spectral_data']['original_points'],20000)
        self.assertTrue(context['spectral_data']['peak_widths_points'])
        self.assertTrue(np.isfinite(sample).all())
