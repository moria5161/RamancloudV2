import asyncio
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi import HTTPException, UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class SpectralBatchTests(unittest.TestCase):
    def payload(self, count, steps=None):
        wave = np.arange(32.)
        return app.BatchPayload(spectra=[app.BatchSpectrum(filename=f'{i}.txt',
            wavenumber=wave.tolist(), intensity=(np.sin(wave) + i).tolist())
            for i in range(count)], steps=steps or [])

    def test_512_spectra_preserve_order_and_chunk_size(self):
        payload = self.payload(512, [app.Step(type='denoise', method='sg')])
        with patch('app.denoise_matrix', wraps=app.denoise_matrix) as denoise:
            results = app.process_batch(payload)['data']['spectra']
        self.assertEqual([call.args[0].shape[0] for call in denoise.call_args_list], [64] * 8)
        self.assertEqual([item['filename'] for item in results], [item.filename for item in payload.spectra])
        for index in [0, 63, 64, 511]:
            expected = app.process_spectrum(app.SpectrumPayload(wavenumber=payload.spectra[index].wavenumber,
                intensity=payload.spectra[index].intensity, steps=payload.steps))['data']
            np.testing.assert_allclose(results[index]['intensity'], expected['intensity'])

    def test_baseline_blocks_and_final_single_row(self):
        payload = self.payload(65, [app.Step(type='baseline', method='imodpoly', params={'poly_order': 1})])
        with patch('app.correct_baseline_batch', wraps=app.correct_baseline_batch) as baseline:
            results = app.process_batch(payload)['data']['spectra']
        self.assertEqual([call.args[0].shape[0] for call in baseline.call_args_list], [64, 1])
        for source, result in zip(payload.spectra, results):
            np.testing.assert_allclose(np.array(result['intensity']) + result['baseline'], source.intensity)

    def test_tsvd_is_joint_with_independent_steps_chunked(self):
        steps = [app.Step(type='denoise', method='sg'), app.Step(type='denoise', method='tsvd', params={'threshold': 1}),
                 app.Step(type='baseline', method='imodpoly', params={'poly_order': 1})]
        payload = self.payload(129, steps)
        matrix = np.array([item.intensity for item in payload.spectra])
        expected = app.apply_pipeline(np.array(payload.spectra[0].wavenumber), matrix, steps)
        with patch('app.denoise_matrix', wraps=app.denoise_matrix) as denoise:
            results = app.process_batch(payload)['data']['spectra']
        self.assertEqual([(call.args[2], len(call.args[0])) for call in denoise.call_args_list],
                         [('sg', 64), ('sg', 64), ('sg', 1), ('tsvd', 129)])
        np.testing.assert_allclose([r['intensity'] for r in results], expected[1], atol=1e-12)
        np.testing.assert_allclose([r['baseline'] for r in results], expected[2], atol=1e-12)

    def test_mixed_axes_and_lengths_remain_supported(self):
        payload = self.payload(65)
        payload.spectra[-1].wavenumber = payload.spectra[-1].wavenumber[:10]
        payload.spectra[-1].intensity = payload.spectra[-1].intensity[:10]
        results = app.process_batch(payload)['data']['spectra']
        self.assertEqual(len(results), 65)
        self.assertEqual(len(results[-1]['intensity']), 10)
        payload.steps = [app.Step(type='denoise', method='tsvd')]
        with self.assertRaisesRegex(ValueError, 'identical'):
            app.process_batch(payload)

    def test_upload_512_and_reject_513_before_archiving(self):
        files = [UploadFile(filename=f'{i}.txt', file=io.BytesIO(b'100 1\n200 2\n')) for i in range(513)]
        with patch('app.archive_uploads', return_value={'status': 'disabled'}) as archive:
            result = asyncio.run(app.upload(files[:512], share_data=False))
            self.assertEqual(len(result['data']['spectra']), 512)
            self.assertEqual(len(archive.call_args.args[0]), 512)
            archive.reset_mock()
            with self.assertRaises(HTTPException) as error:
                asyncio.run(app.upload(files, share_data=False))
            self.assertEqual(error.exception.status_code, 400)
            archive.assert_not_called()

    def test_empty_and_over_limit_processing_are_rejected(self):
        for count in [0, 513]:
            with self.assertRaisesRegex(ValueError, '512'):
                app.process_batch(self.payload(count))


if __name__ == '__main__':
    unittest.main()
