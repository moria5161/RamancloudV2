import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from web_security import COOKIE_NAME, DATA_OWNER, WebSecurityMiddleware


def secured_app():
    application = FastAPI()
    application.include_router(app.app.router)
    application.add_middleware(WebSecurityMiddleware, enabled=True, secret=b'x' * 32,
                               cookie_path='/', origins=['https://ramancloud.xmu.edu.cn'])
    return application


class WebSecurityTests(unittest.TestCase):
    def setUp(self):
        app.DATASETS.clear()
        self.application = secured_app()
        self.client = TestClient(self.application, base_url='https://ramancloud.xmu.edu.cn')
        self.other = TestClient(self.application, base_url='https://ramancloud.xmu.edu.cn')
        self.headers = {'X-RamanCloud-CSRF': self.client.get('/api/session').json()['csrf_token']}
        self.other_headers = {'X-RamanCloud-CSRF': self.other.get('/api/session').json()['csrf_token']}
        self.content = b'\t\t100\t200\n0\t0\t1\t2\n'

    def upload(self):
        response = self.client.post('/api/upload-hyperspectral', headers=self.headers,
                                    files={'file': ('security-test.txt', self.content)},
                                    data={'mode': 'imaging', 'instrument': 'Horiba', 'share_data': 'false'})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']['dataset_id']

    def test_anonymous_upload_requires_session(self):
        client = TestClient(self.application, base_url='https://ramancloud.xmu.edu.cn')
        response = client.post('/api/upload-hyperspectral', files={'file': ('test.txt', self.content)})
        self.assertEqual(response.status_code, 401)

    def test_session_cookie_and_csrf_protection(self):
        cookie = self.client.get('/api/session').headers['set-cookie']
        self.assertIn('Secure', cookie)
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=strict', cookie)
        response = self.client.post('/api/process', json={'wavenumber': [1], 'intensity': [2]})
        self.assertEqual(response.status_code, 403)
        response = self.client.post('/api/process', headers=self.other_headers,
                                    json={'wavenumber': [1], 'intensity': [2]})
        self.assertEqual(response.status_code, 403)

    def test_cross_session_read_download_process_and_delete_rejected(self):
        dataset_id = self.upload()
        self.assertEqual(self.client.get(f'/api/hyperspectral-pixel/{dataset_id}').status_code, 200)
        self.assertEqual(self.other.get(f'/api/hyperspectral-pixel/{dataset_id}').status_code, 404)
        self.assertEqual(self.other.get(f'/api/hyperspectral-slice/{dataset_id}').status_code, 404)
        payload = {'dataset_id': dataset_id, 'wavenumber': [100, 200], 'steps': []}
        self.assertEqual(self.other.post('/api/process-hyperspectral', headers=self.other_headers, json=payload).status_code, 404)
        self.assertEqual(self.other.post('/api/download', headers=self.other_headers, json=payload).status_code, 404)
        self.assertEqual(self.other.delete(f'/api/datasets/{dataset_id}', headers=self.other_headers).status_code, 404)
        downloaded = self.client.post('/api/download', headers=self.headers,
                                      json={**payload, 'format': 'mapping'})
        self.assertEqual(downloaded.status_code, 200)
        _, data, coordinates = app.read_imaging(downloaded.content, 'Horiba')
        np.testing.assert_array_equal(data, [[[1, 2]]])
        self.assertEqual(coordinates, {'x': [0.0], 'y': [0.0]})
        self.assertEqual(self.client.delete(f'/api/datasets/{dataset_id}', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(f'/api/hyperspectral-pixel/{dataset_id}').status_code, 404)

    def test_processed_dataset_inherits_owner(self):
        dataset_id = self.upload()
        result = self.client.post('/api/process-hyperspectral', headers=self.headers,
                                  json={'dataset_id': dataset_id, 'wavenumber': [100, 200], 'steps': []})
        self.assertEqual(result.status_code, 200, result.text)
        processed = result.json()['data']['processed_dataset_id']
        self.assertEqual(self.client.get(f'/api/hyperspectral-pixel/{processed}').status_code, 200)
        self.assertEqual(self.other.get(f'/api/hyperspectral-pixel/{processed}').status_code, 404)

    def test_forged_cookie_rejected(self):
        cookie = self.client.cookies.get(COOKIE_NAME)
        self.client.cookies.set(COOKIE_NAME, cookie[:-1] + ('0' if cookie[-1] != '0' else '1'),
                                domain='ramancloud.xmu.edu.cn', path='/')
        self.assertEqual(self.client.get('/api/demo/bacteria').status_code, 401)

    def test_cross_site_and_untrusted_origin_rejected(self):
        for headers in ({'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.client.get('/api/session', headers=headers).status_code, 403)

    def test_size_limit_checks_content_length_and_streamed_body(self):
        payload = {'wavenumber': [1], 'intensity': [2]}
        with patch('web_security.MAX_BODY_BYTES', 20):
            self.assertEqual(self.client.post('/api/process', headers=self.headers, json=payload).status_code, 413)
            headers = {**self.headers, 'Content-Type': 'application/json'}
            self.assertEqual(self.client.post('/api/process', headers=headers, content=iter([b'{' + b' ' * 30, b'}'])).status_code, 413)

    def test_global_quota_does_not_evict_another_workspace(self):
        dataset_id = self.upload()
        with patch('app.DATASET_MAX_BYTES', 32):
            response = self.other.post('/api/upload-hyperspectral', headers=self.other_headers,
                                       files={'file': ('other.txt', self.content)}, data={'share_data': 'false'})
            self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(f'/api/hyperspectral-pixel/{dataset_id}').status_code, 200)

    def test_small_form_limit_applies_before_parsing_and_to_streamed_bodies(self):
        @self.application.post('/api/structure/form-probe')
        async def probe(request: Request):
            return {'fields': len(await request.form())}

        headers = {**self.headers, 'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'}
        with patch('web_security.MAX_FORM_BODY_BYTES', 20):
            self.assertEqual(self.client.post('/api/structure/form-probe', headers=headers,
                                             content=b'smiles=CCO').status_code, 200)
            for body in (b'smiles=' + b'C' * 30, iter([b'smiles=', b'C' * 30])):
                self.assertEqual(self.client.post('/api/structure/form-probe', headers=headers,
                                                 content=body).status_code, 413)

    def test_urlencoded_parser_enforces_field_count(self):
        @self.application.post('/api/structure/form-probe')
        async def probe(request: Request):
            return {'fields': len(await request.form(max_fields=10, max_part_size=8))}

        headers = {**self.headers, 'Content-Type': 'application/x-www-form-urlencoded'}
        response = self.client.post('/api/structure/form-probe', headers=headers,
                                    content='&'.join(f'f{i}=x' for i in range(11)))
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/structure/form-probe', headers=headers, content='f=123456789')
        self.assertEqual(response.status_code, 400)

    def test_multi_dataset_registration_is_atomic(self):
        token = DATA_OWNER.set('atomic-test')
        try:
            entries = [(np.array([1, 2]), np.array([[1, 2]]), 'time_series', 'test.txt', {})] * 2
            with patch('app.DATASET_OWNER_MAX_BYTES', 40), self.assertRaises(HTTPException):
                app.register_datasets(entries)
            self.assertEqual(app.DATASETS, {})
        finally:
            DATA_OWNER.reset(token)

    def test_session_signature_and_expiry(self):
        middleware = WebSecurityMiddleware(None, enabled=True, secret=b'x' * 32)
        self.assertIsNone(middleware.owner('a' * 43 + '.100.' + '\u00e9' * 64))
        with patch('web_security.time.time', return_value=100):
            token = middleware.token('a' * 43)
        with patch('web_security.time.time', return_value=101):
            self.assertEqual(middleware.owner(token), 'a' * 43)
        with patch('web_security.time.time', return_value=50_000):
            self.assertIsNone(middleware.owner(token))


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_workspace_cannot_start_two_heavy_tasks(self):
        for endpoint in ('/api/process-probe', '/api/download', '/api/download-batch'):
            with self.subTest(endpoint=endpoint):
                await self.check_heavy_task(endpoint)

    async def check_heavy_task(self, endpoint):
        application = FastAPI()
        started = asyncio.Event()
        finish = asyncio.Event()

        @application.post(endpoint)
        async def probe():
            started.set()
            await finish.wait()
            return {'ok': True}

        application.add_middleware(WebSecurityMiddleware, enabled=True, secret=b'x' * 32, cookie_path='/')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='https://ramancloud.xmu.edu.cn') as client:
            csrf = (await client.get('/api/session')).json()['csrf_token']
            headers = {'X-RamanCloud-CSRF': csrf}
            first = asyncio.create_task(client.post(endpoint, headers=headers))
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                second = await client.post(endpoint, headers=headers)
                self.assertEqual(second.status_code, 429)
                self.assertEqual(second.headers['retry-after'], '2')
            finally:
                finish.set()
            self.assertEqual((await first).status_code, 200)
            self.assertEqual((await client.post(endpoint, headers=headers)).status_code, 200)


if __name__ == '__main__':
    unittest.main()
