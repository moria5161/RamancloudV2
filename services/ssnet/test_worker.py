"""Small actual CPU train/save/load/predict check, not an accuracy benchmark."""
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np
from worker import run, sha


class WorkerTests(unittest.TestCase):
    def test_tiny_training_and_frozen_model_reuse(self):
        with tempfile.TemporaryDirectory(prefix='ssnet-smoke-') as temporary:
            root=Path(temporary)
            model_dir=root/'model';model_dir.mkdir()
            prediction_dir=root/'prediction';prediction_dir.mkdir()
            x=np.linspace(200,1800,128)
            clean=np.exp(-((x-800)/40)**2)+.4*np.exp(-((x-1300)/60)**2)
            clean/=clean.max()
            prepared=dict(grid=dict(start=200.,end=1800.,points=128),spectra=[clean.tolist()])
            settings=dict(device='cpu',epochs=1,samples_per_epoch=2,batch_size=2,rf_samples=32,trees=10)
            trained=run(dict(kind='train',input=dict(settings=settings,prepared=prepared)),model_dir)
            self.assertEqual(trained['artifacts']['unet.pth'],sha(model_dir/'unet.pth'))
            self.assertEqual(len(trained['loss_history']),1)
            self.assertTrue(np.isfinite(trained['loss_history']).all())
            data=dict(model_id='smoke',model_name='Synthetic execution check',grid=prepared['grid'],
                      network_sha256=trained['network_sha256'],artifacts=trained['artifacts'],
                      prepared=dict(wavenumber=x.tolist(),intensity=clean.tolist(),scale=100.,offset=5.))
            snapshot=copy.deepcopy(data)
            result=run(dict(kind='predict',input=data,model_dir=str(model_dir)),prediction_dir)
            self.assertEqual(data,snapshot)
            self.assertTrue(result['inference_performed'])
            self.assertEqual(result['wavenumber'],x.tolist())
            self.assertTrue(np.isfinite(result['extracted']).all())
            np.testing.assert_allclose(np.asarray(result['extracted'])+result['background'],result['mixture'],rtol=1e-5,atol=1e-5)
            self.assertEqual(result['removed_offset'],5.)
            data['artifacts']['unet.pth']='wrong'
            with self.assertRaisesRegex(ValueError,'校验'):
                run(dict(kind='predict',input=data,model_dir=str(model_dir)),prediction_dir)


if __name__=='__main__':
    unittest.main()
