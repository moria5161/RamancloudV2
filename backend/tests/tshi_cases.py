"""TSHI integration cases reuse the existing isolated server/database."""
import io
import json

import numpy as np
from scipy.io import loadmat
from test_tshi import sample, mat_bytes


class TSHICases:
    def upload_tshi(self, **options):
        wave, cube = sample()
        fields = dict(height=8, width=9, layout='bands_pixels', pixel_order='F', mode='imaging')
        fields.update(options)
        boundary = 'raman-tshi-test-boundary'
        body = b''
        for name, value in fields.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="sample.mat"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
        body += mat_bytes(cube.reshape(-1, len(wave), order='F').T, wave) + f'\r\n--{boundary}--\r\n'.encode()
        return self.request('/api/upload-hyperspectral', raw=body, token=self.auth['token'], content_type=f'multipart/form-data; boundary={boundary}')

    def test_tshi_http_process_history_download_rerun(self):
        import app as backend
        code, response = self.upload_tshi()
        self.assertEqual(code, 200, response)
        source = response['data']
        wave, cube = sample()
        np.testing.assert_array_equal(backend.DATASETS[source['dataset_id']]['data'], cube)
        payload = dict(dataset_id=source['dataset_id'], wavenumber=source['wavenumber'], save_history=True,
                       steps=[dict(type='denoise', method='tshi', params=dict(center_wavenumber=float(wave[7]), half_width=4, windowsize=3))])
        code, result = self.call('/api/process-hyperspectral', payload)
        self.assertEqual(code, 200, result)
        out = result['data']
        self.assertEqual(out['shape'], [8, 9, 8])
        self.assertEqual(out['preview_wavenumber'], wave[7])
        np.testing.assert_array_equal(backend.DATASETS[source['dataset_id']]['data'], cube)
        run = out['analysis_run']
        self.assertEqual(run['history'][0]['method'], 'tshi')
        self.assertEqual(len(run['versions']), 3)
        code, content = self.call('/api/download', dict(dataset_id=out['processed_dataset_id'], wavenumber=out['wavenumber'], format='mat', filename='tshi.mat'))
        self.assertEqual(code, 200)
        loaded = loadmat(io.BytesIO(content))
        self.assertEqual(loaded['cube'].shape, (8, 9, 8))
        self.assertEqual(json.loads(loaded['history_json'][0])[0]['method'], 'tshi')
        pixel = self.call(f"/api/hyperspectral-pixel/{out['processed_dataset_id']}?x=3&y=2")[1]['data']
        np.testing.assert_allclose(pixel['intensity'], loaded['cube'][2, 3], atol=1e-5)
        self.assertEqual(self.request(f"/api/analysis-runs/{run['id']}/download", token=self.other['token'])[0], 404)
        self.assertEqual(self.call(f"/api/analysis-runs/{run['id']}/download")[0], 200)
        code, rerun = self.call(f"/api/analysis-runs/{run['id']}/rerun", {})
        self.assertEqual(code, 200, rerun)
        self.assertEqual(rerun['data']['run']['history'][0]['details']['center_wavenumber'], wave[7])

    def test_tshi_http_invalid_input_and_mode(self):
        code, result = self.upload_tshi(height=7)
        self.assertEqual(code, 400, result)
        self.assertIn('像素数量', result['detail'])
        code, response = self.upload_tshi()
        source = response['data']
        code, result = self.call('/api/process-hyperspectral', dict(dataset_id=source['dataset_id'], wavenumber=source['wavenumber'],
                                      steps=[dict(type='denoise', method='tshi', params=dict(windowsize=4))]))
        self.assertEqual(code, 400, result)
        demo = self.request('/api/demo-hyperspectral/timeseries_horiba')[1]['data']
        code, result = self.call('/api/process-hyperspectral', dict(dataset_id=demo['dataset_id'], wavenumber=demo['wavenumber'],
                                      steps=[dict(type='denoise', method='tshi', params={})]))
        self.assertEqual(code, 400, result)

    def test_tshi_pipeline_baseline_crop_and_following_steps(self):
        import app as backend
        wave, cube = sample()
        steps = [backend.Step(type='baseline', method='airpls', params=dict(lam=1e4, diff_order=2)),
                 backend.Step(type='cut', params=dict(start=wave[1], end=wave[-2])),
                 backend.Step(type='denoise', method='tshi', params=dict(center_wavenumber=float(wave[7]), half_width=4, windowsize=3, thr2=-100)),
                 backend.Step(type='denoise', method='sg', params=dict(window_size=5, order=2))]
        out_wave, result, baseline, history = backend.apply_pipeline(wave, cube.reshape(-1, len(wave)), steps, cube.shape[:2])
        self.assertEqual(result.shape, baseline.shape)
        self.assertEqual(result.shape[-1], len(out_wave))
        self.assertEqual(history[-2]['method'], 'tshi')
        self.assertTrue(np.isfinite(result).all())
