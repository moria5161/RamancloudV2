import ast
import copy
import sys
import unittest
from pathlib import Path
import numpy as np
from scipy.special import wofz
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from peak_fitting import Peak
from peak_fitting_core import fit, prepare, voigt


def row(center, width, **extra):
    return Peak(center=center, center_min=center-1, center_max=center+1, width=width,
                width_min=.9*width, width_max=1.1*width, **extra).dict()


class PeakFittingTests(unittest.TestCase):
    def setUp(self):
        self.x = np.linspace(2000., 2250., 501)
        self.truth = [(2090., 6000., 60., .35), (2140., 2200., 25., .5), (2160., 3500., 38., .65)]
        self.y = sum((voigt(self.x, *p) for p in self.truth), np.zeros_like(self.x))
        self.spectrum = dict(wavenumber=self.x.tolist(), intensity=self.y.tolist())
        self.settings = dict(start=2000, end=2250, peaks=[row(p[0], p[2]) for p in self.truth])

    def test_source_script_profile_parity_including_both_pure_limits(self):
        source = next(Path(__file__).resolve().parents[2].glob('4-Voigt_Fitting_*.py'), None)
        # Keep the source formula available in clean checkouts where the user's
        # original standalone script is not tracked. Use that script if present.
        def reference(x, center, area, width, eta):
            gamma=eta*width/2
            sigma=(1-eta)*width/(2*np.sqrt(2*np.log(2)))
            if sigma==0:return area/np.pi*gamma/((x-center)**2+gamma**2)
            return area*np.real(wofz(((x-center)+1j*gamma)/(sigma*np.sqrt(2))))/(sigma*np.sqrt(2*np.pi))
        scope = dict(np=np, wofz=wofz, Voigt=reference)
        if source:
            tree = ast.parse(source.read_text(encoding='utf-8-sig'))
            original = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'Voigt')
            exec(compile(ast.Module(body=[original], type_ignores=[]), str(source), 'exec'), scope)
        for eta in (0, .2, .5, .99, 1):
            np.testing.assert_allclose(voigt(self.x, 2100, 500, 20, eta), scope['Voigt'](self.x, 2100, 500, 20, eta), rtol=1e-13, atol=1e-13)

    def test_recovers_overlapping_peaks_without_mutating_or_resampling_input(self):
        original = copy.deepcopy(self.spectrum)
        result = fit(self.spectrum, self.settings)
        self.assertEqual(self.spectrum, original)
        self.assertEqual(result['wavenumber'], self.spectrum['wavenumber'])
        self.assertGreater(result['r_squared'], 1-1e-12)
        for actual, truth in zip(result['peaks'], self.truth):
            np.testing.assert_allclose([actual['center'], actual['area'], actual['width_parameter'], actual['eta']], truth, rtol=1e-7, atol=1e-7)
        np.testing.assert_allclose(np.sum(result['components'], axis=0), result['intensity'])
        np.testing.assert_allclose(np.array(result['observed'])-result['intensity'], result['residual'])

    def test_actual_fwhm_differs_from_source_width_and_both_pure_limits_work(self):
        x=np.linspace(-300,300,601)
        for shape, eta in [('voigt',.5),('gaussian',0),('lorentzian',1)]:
            p=row(0,100,shape=shape,eta=eta)
            p.update(center_min=0,center_max=0,width_min=100,width_max=100,area=1000,area_min=1000,area_max=1000,eta_min=eta,eta_max=eta)
            result=fit(dict(wavenumber=x.tolist(),intensity=voigt(x,0,1000,100,eta).tolist()),dict(start=-300,end=300,peaks=[p]))
            self.assertEqual(result['free_parameters'],0)
            self.assertAlmostEqual(result['peaks'][0]['fwhm'],81.8797679814 if eta==.5 else 100,places=7)
            self.assertAlmostEqual(result['peaks'][0]['eta'],eta)

    def test_descending_nonuniform_axis_and_crop_keep_exact_pairs(self):
        x=self.x.copy(); x[1:-1] += .03*np.sin(np.arange(len(x)-2))
        y=voigt(x,2090,1000,60,.5)
        result=fit(dict(wavenumber=x[::-1].tolist(),intensity=y[::-1].tolist()),dict(start=2050,end=2200,peaks=[row(2090,60)]))
        keep=(x>=2050)&(x<=2200)
        self.assertEqual(result['wavenumber'],x[keep][::-1].tolist())
        self.assertEqual(result['observed'],y[keep][::-1].tolist())

    def test_invalid_bounds_sparse_flat_and_nonfinite_spectra_are_rejected(self):
        cases=[]
        for key,value in [('width_min',0),('center_min',1900),('center_max',2080),('eta_max',1.1),('area',-1),('center',float('nan'))]:
            s=copy.deepcopy(self.settings);s['peaks'][0][key]=value;cases.append((self.spectrum,s))
        cases += [(dict(wavenumber=self.x.tolist(),intensity=[1]*len(self.x)),self.settings),
                  (dict(wavenumber=[2000]*8,intensity=list(range(8))),self.settings),
                  (dict(wavenumber=np.linspace(2000,2250,8).tolist(),intensity=list(range(8))),self.settings)]
        for spectrum,settings in cases:
            with self.assertRaises(ValueError):prepare(spectrum,settings)

    def test_a_deadline_aborts_the_solver(self):
        with self.assertRaisesRegex(ValueError,'timed out'):
            fit(self.spectrum,self.settings,timeout=-1)
