import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from web_security import WebSecurityMiddleware


class BatchDownloadTests(unittest.TestCase):
    def setUp(self):
        application = FastAPI()
        application.include_router(app.app.router)
        application.add_middleware(WebSecurityMiddleware, enabled=True, secret=b'x' * 32,
                                   cookie_path='/', origins=['https://ramancloud.xmu.edu.cn'])
        self.client = TestClient(application, base_url='https://ramancloud.xmu.edu.cn')
        self.headers = {'X-RamanCloud-CSRF': self.client.get('/api/session').json()['csrf_token']}
        self.spectrum = {'wavenumber': [4184.123456789, 1000, 484.6],
                         'intensity': [1.234567891, -2e-10, 3e10], 'baseline': [0, -1, 2]}

    def post(self, spectra):
        return self.client.post('/api/download-batch', json={'spectra': spectra}, headers=self.headers)

    def test_batch_output_exactly_matches_existing_download_format(self):
        spectra = [self.spectrum, {'wavenumber': [200, 100], 'intensity': [2, 1]}] * 32
        response = self.post(spectra)
        self.assertEqual(response.status_code, 200, response.text)
        results = response.json()['data']['spectra']
        self.assertEqual(len(results), 64)
        for source, result in zip(spectra, results):
            expected = app.download(app.DownloadPayload(wavenumber=source['wavenumber'], intensity=source['intensity']))
            self.assertEqual(result['content'], expected.body.decode())
            if 'baseline' in source:
                expected = app.download(app.DownloadPayload(wavenumber=source['wavenumber'], intensity=source['baseline']))
                self.assertEqual(result['baseline'], expected.body.decode())
            else:
                self.assertIsNone(result['baseline'])

    def test_request_count_and_numeric_size_are_bounded(self):
        for count in [0, 65]:
            self.assertEqual(self.post([self.spectrum] * count).status_code, 422)
        with patch('app.MAX_NUMERIC_VALUES', 8):
            self.assertEqual(self.post([self.spectrum]).status_code, 413)

    def test_download_requires_session_and_csrf(self):
        payload = {'spectra': [self.spectrum]}
        self.assertEqual(self.client.post('/api/download-batch', json=payload).status_code, 403)
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/download-batch', json=payload, headers=self.headers).status_code, 401)


if __name__ == '__main__':
    unittest.main()
