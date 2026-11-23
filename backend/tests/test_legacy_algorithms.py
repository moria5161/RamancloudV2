import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import legacy_algorithms as legacy


class LegacyAlgorithmTests(unittest.TestCase):
    def test_registry_keeps_every_distinct_original_method(self):
        self.assertEqual({s['original_method'] for s in legacy.CATALOG},{'sg','wtd','peer','tsvd','f2p','airnet','airpls','aabs','imodpoly','snip'})
        self.assertEqual(len(legacy.METHODS),10)

    def test_missing_models_never_fall_back_to_another_algorithm(self):
        with patch.dict('os.environ',{'RAMANCLOUD_F2P_MODEL':'missing-weight','RAMANCLOUD_AIRNET_MODEL':'missing-weight'}):
            for method in ('f2p','airnet'):
                self.assertFalse(legacy.availability(legacy.METHODS[method])[0])
                with self.assertRaises(ValueError):legacy.process(np.ones((2,16)),{},method)

    def test_real_single_and_mapping_numerics_and_baseline_reconstruction(self):
        if not all(legacy.availability(s)[0] for s in legacy.CATALOG if s['original_method'] not in ('f2p','airnet')):
            self.skipTest('Run setup_legacy_algorithms.py to enable original numeric integration tests')
        import app
        x=np.linspace(200,2000,256)
        y=100+.02*x+300*np.exp(-((x-1004)/25)**2)+np.sin(x/13)
        matrix=np.stack([y,1.1*y+3,0.8*y+6])
        for spec in legacy.CATALOG:
            if spec['original_method'] in ('f2p','airnet'):continue
            method=spec['method']
            params={k:r['default'] for k,r in spec['params'].items()}
            for data in [y,matrix]:
                wave,out,baseline,history=app.apply_pipeline(x,data,[app.Step(type=spec['type'],method=method,params=params)])
                self.assertEqual(out.shape,data.shape,method)
                self.assertTrue(np.isfinite(out).all(),method)
                np.testing.assert_array_equal(wave,x)
                self.assertEqual(history[0]['method'],method)
                if spec['type']=='baseline':np.testing.assert_allclose(out+baseline,data,rtol=1e-10,atol=1e-10)
        out,_=legacy.process(matrix,{},'tsvd')
        u,s,vh=np.linalg.svd(matrix,full_matrices=False)
        keep=np.ones(len(s),dtype=bool);keep[1:-1]=np.abs(np.diff(np.log1p(s),n=2))>.001
        np.testing.assert_allclose(out,(u*np.where(keep,s,0))@vh,rtol=1e-8,atol=1e-8)

    def test_unsupported_and_nonfinite_parameters_are_rejected(self):
        with patch.object(legacy,'availability',return_value=(True,'')):
            for method,params in [('airpls',{'quantile':.1}),('peer',{'loops':0}),('snip',{'max_half_window':1000}),('airpls',{'lam':float('nan')})]:
                with self.assertRaises(ValueError):legacy.process(np.ones((1,128)),params,method)

    def test_real_f2p_and_airnet_vector_and_mapping(self):
        if not all(legacy.availability(legacy.METHODS[m])[0] for m in ('f2p','airnet')):
            self.skipTest('Install author checkpoints to enable real neural inference tests')
        x=np.linspace(0,1,256);y=100+10*x+200*np.exp(-((x-.4)/.03)**2)+np.sin(x*90)
        matrix=np.vstack([y,1.1*y])
        for method in ('f2p','airnet'):
            output,baseline=legacy.process(matrix,{},method)
            self.assertEqual(output.shape,matrix.shape)
            self.assertTrue(np.isfinite(output).all())
            self.assertGreater(float(np.max(np.abs(output-matrix))),0)
            if method=='airnet':np.testing.assert_allclose(output+baseline,matrix,rtol=1e-6,atol=1e-6)
