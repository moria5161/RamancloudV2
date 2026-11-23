"""HTTP coverage for library-job provenance, permissions, exports and failures."""
import copy
import time
from contextlib import contextmanager
from unittest.mock import patch

import app as backend
import library_matching as lm
from peaknet_package import configuration, prepare_source


class LibraryCases:
    def test_library_catalog_can_find_original_class_ids_without_changing_names(self):
        with patch.object(lm, 'catalog', return_value={'0': '原始中文名称', '9': '另一种物质'}):
            code, result = self.call('/api/library-matching/catalog?q=0')
        self.assertEqual(code, 200)
        self.assertEqual(result['items'], [{'class_id': 0, 'name': '原始中文名称'}])

    @contextmanager
    def library_runtime(self, fail=False):
        profile, paths, _ = configuration()
        spectrum = dict(wavenumber=[220., 1800.], intensity=[.1, 1.])
        fixture = dict(model_input=spectrum, input_preview=spectrum, preprocessing=None,
                       preprocessing_mode='prepared', normalization_scale=1., inference_performed=True,
                       duration_seconds=.01, score_type='closed_set_softmax',
                       candidates=[dict(rank=1, class_id=10, name='HTTP test fixture', model_score=.7, reference=dict(spectrum, source='non_augmented_training_cache'))])
        side_effect = RuntimeError('test matching unavailable') if fail else lambda *args: copy.deepcopy(fixture)
        with patch.object(lm, 'configuration', return_value=(profile, paths, True)), patch.object(lm, 'infer', side_effect=side_effect):
            yield

    def wait_match(self, job_id, token=None):
        for _ in range(100):
            code, value = self.request('/api/library-matching/jobs/' + job_id, token=token or self.auth['token'])
            self.assertEqual(code, 200, value)
            if value['status'] not in ('queued', 'running'):
                return value
            time.sleep(.03)
        self.fail('Matching did not finish')

    def test_library_source_permissions_and_physical_range(self):
        task = self.task()
        payload = dict(workflow_id=task['id'], unit_confirmed=True, preprocessing_mode='prepared')
        route = '/api/library-matching/validate'
        self.assertEqual(self.request('/api/library-matching/config')[0], 401)
        self.assertEqual(self.request('/api/library-matching/catalog')[0], 401)
        with self.library_runtime():
            self.assertEqual(self.request(route, payload, token=self.other['token'])[0], 404)
            self.assertEqual(self.call(route, dict(payload, unit_confirmed=False))[0], 400)
            self.assertEqual(self.call(route, dict(payload, version_id='unrelated-version'))[0], 404)
            self.assertEqual(self.call(route, dict(payload, top_k=2805))[0], 422)
            code, value = self.call(route, payload)
            self.assertEqual(code, 200, value)
            self.assertEqual(value['cropped']['wavenumber'][0], 220.)
            self.assertEqual(value['cropped']['wavenumber'][-1], 1800.)
        p = configuration()[0]
        reverse = dict(wavenumber=[1800, 1600, 1400, 1200, 1000, 800, 600, 400, 220], intensity=list(range(9)))
        self.assertTrue(prepare_source(reverse, p)['preparation']['reversed'])
        with self.assertRaises(ValueError):
            prepare_source(dict(wavenumber=list(range(400, 2000, 100)), intensity=list(range(16))), p)
        with self.assertRaises(ValueError):
            prepare_source(dict(wavenumber=list(range(200, 2000, 100)), intensity=[1.] * 18), p)

    def test_library_job_export_history_and_frozen_replay(self):
        task = self.task()
        with self.library_runtime():
            code, created = self.call('/api/library-matching/jobs', dict(workflow_id=task['id'], unit_confirmed=True, preprocessing_mode='prepared'))
            self.assertEqual(code, 200, created)
            job = self.wait_match(created['id'])
            self.assertEqual(job['status'], 'completed', job['error'])
            self.assertEqual(job['input']['source']['spectrum'], task['original'])
            self.assertEqual(self.request('/api/library-matching/jobs/' + job['id'], token=self.other['token'])[0], 404)
            self.assertEqual(self.request('/api/library-matching/jobs/' + job['id'] + '/download', token=self.other['token'])[0], 404)
            for format in ('json', 'csv', 'input'):
                self.assertEqual(self.call('/api/library-matching/jobs/' + job['id'] + '/download?format=' + format)[0], 200)
            history = self.call('/api/analysis-runs/' + job['analysis_run_id'])[1]['data']['run']
            self.assertEqual(history['analysis_type'], 'library_matching')
            self.assertEqual(history['result']['job_id'], job['id'])
            self.assertEqual(history['result']['candidates'][0]['reference'], job['result']['candidates'][0]['reference'])
            self.assertEqual(history['result']['model_input'], job['result']['model_input'])
            self.assertEqual(self.call('/api/analysis-runs/' + job['analysis_run_id'] + '/download')[0], 200)
            self.call('/api/ai-workflows/' + task['id'], method='DELETE')
            code, replay = self.call('/api/library-matching/jobs', dict(reuse_job_id=job['id'], unit_confirmed=True, preprocessing_mode='prepared'))
            self.assertEqual(code, 200, replay)
            self.assertEqual(self.wait_match(replay['id'])['status'], 'completed')

    def test_library_worker_failure_is_saved(self):
        task = self.task()
        with self.library_runtime(fail=True):
            code, created = self.call('/api/library-matching/jobs', dict(workflow_id=task['id'], unit_confirmed=True))
            self.assertEqual(code, 200, created)
            job = self.wait_match(created['id'])
            self.assertEqual(job['status'], 'failed')
            self.assertIn('unavailable', job['error'])
            self.assertIsNone(job['analysis_run_id'])

    def test_library_project_revocation_hides_saved_job(self):
        pid = self.project()
        self.join(pid)
        task = self.task()
        with backend.db_connect() as conn:
            conn.execute('UPDATE ai_workflows SET project_id=?,user_id=? WHERE id=?', (pid, self.other['user']['id'], task['id']))
        token = self.other['token']
        with self.library_runtime():
            code, created = self.request('/api/library-matching/jobs', dict(workflow_id=task['id'], unit_confirmed=True), token=token)
            self.assertEqual(code, 200, created)
            self.assertEqual(self.wait_match(created['id'], token)['status'], 'completed')
            uid = self.other['user']['id']
            self.assertEqual(self.call(f'/api/projects/{pid}/members/{uid}', method='DELETE')[0], 200)
            self.assertEqual(self.request('/api/library-matching/jobs/' + created['id'], token=token)[0], 404)
