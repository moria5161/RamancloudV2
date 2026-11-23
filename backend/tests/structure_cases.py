"""Security and durable job behavior; model calls are isolated from HTTP tests."""
import copy
import time
from unittest.mock import patch

import structure_generation as sg
from structure_profiles import configuration, prepare_spectrum


class StructureCases:
    def structure_source(self):
        boundary = 'structure-test-boundary'
        text = '\n'.join(f'{400 + n * 400}\t{n + 1}' for n in range(10))
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="full_range.txt"\r\n'
                f'Content-Type: text/plain\r\n\r\n{text}\r\n--{boundary}--\r\n').encode()
        code, value = self.call('/api/ai-workflows/upload', raw=body, content_type='multipart/form-data; boundary=' + boundary)
        self.assertEqual(code, 200, value)
        return value

    def wait_structure(self, job_id):
        for _ in range(100):
            code, value = self.call('/api/structure-generation/jobs/' + job_id)
            self.assertEqual(code, 200, value)
            if value['status'] not in ('queued', 'running'):
                return value
            time.sleep(.03)
        self.fail('Structure job did not finish')

    def test_structure_input_contract_and_permissions(self):
        task = self.structure_source()
        payload = dict(workflow_id=task['id'], unit_confirmed=True)
        path = '/api/structure-generation/validate'
        self.assertEqual(self.request('/api/structure-generation/config')[0], 401)
        self.assertEqual(self.request(path, payload, token=self.other['token'])[0], 404)
        self.assertEqual(self.call(path, dict(payload, unit_confirmed=False))[0], 400)
        self.assertEqual(self.call(path, dict(payload, version_id='unrelated'))[0], 404)
        self.assertEqual(self.call(path, dict(payload, formula='Xx6H6'))[0], 400)
        self.assertEqual(self.call(path, dict(payload, engine='unsupported'))[0], 422)
        code, data = self.call(path, payload)
        self.assertEqual(code, 200, data)
        self.assertEqual(len(data['model_input']['intensity']), 1024)
        self.assertAlmostEqual(max(data['model_input']['intensity']), 1)
        short = self.task()
        code, value = self.call(path, dict(payload, workflow_id=short['id']))
        self.assertEqual(code, 400)
        self.assertIn('4000', value['detail'])
        profile = configuration()[0]
        descending = {k: list(reversed(task['original'][k])) for k in ('wavenumber', 'intensity')}
        prepared = prepare_spectrum(descending, profile)
        self.assertTrue(prepared['preparation']['reversed'])
        self.assertEqual(prepared['intensity'], data['model_input']['intensity'])

    def test_structure_job_history_export_and_snapshot_replay(self):
        task = self.structure_source()
        fixture = dict(inference_performed=True, duration_seconds=.01, dropped={}, ranking='matching_score',
                       candidates=[dict(id='1', rank=1, smiles='c1ccccc1', formula='C6H6', inchikey='UHOVQNZJYSORNB-UHFFFAOYSA-N',
                                        matching_score=.2, generation_score=-5, image_png='fixture', sdf='fixture molblock')])
        with patch.object(sg, 'public_configuration', return_value={'ready': True}), patch.object(sg.RUNTIME, 'infer', side_effect=lambda *args: copy.deepcopy(fixture)) as inference:
            code, created = self.call('/api/structure-generation/jobs', dict(workflow_id=task['id'], unit_confirmed=True, engine='agent'))
            self.assertEqual(code, 200, created)
            job = self.wait_structure(created['id'])
            self.assertEqual(job['status'], 'completed', job.get('error'))
            self.assertEqual(job['profile']['engine'], 'agent')
            self.assertEqual(job['settings']['engine'], 'agent')
            self.assertEqual(job['input']['source']['spectrum'], task['original'])
            self.assertEqual(len(inference.call_args.args[2]['intensity']), 1024)
            self.assertEqual(self.request('/api/structure-generation/jobs/' + job['id'], token=self.other['token'])[0], 404)
            self.assertEqual(self.request('/api/structure-generation/jobs/' + job['id'] + '/download', token=self.other['token'])[0], 404)
            for format in ('json', 'csv', 'sdf'):
                self.assertEqual(self.call('/api/structure-generation/jobs/' + job['id'] + '/download?format=' + format)[0], 200)
            history = self.call('/api/analysis-runs/' + job['analysis_run_id'])[1]['data']['run']
            self.assertEqual(history['analysis_type'], 'structure_generation')
            self.assertEqual(history['result']['candidates'][0]['image_png'], 'fixture')
            self.assertNotIn('sdf', history['result']['candidates'][0])
            self.assertEqual(self.call('/api/analysis-runs/' + job['analysis_run_id'] + '/download')[0], 200)
            # Frozen inputs remain usable even if the source workflow is removed.
            self.call('/api/ai-workflows/' + task['id'], method='DELETE')
            code, replay = self.call('/api/structure-generation/jobs', dict(reuse_job_id=job['id'], unit_confirmed=True))
            self.assertEqual(code, 200, replay)
            self.assertEqual(self.wait_structure(replay['id'])['status'], 'completed')

    def test_structure_worker_failure_is_persisted(self):
        task = self.structure_source()
        with patch.object(sg, 'public_configuration', return_value={'ready': True}), patch.object(sg.RUNTIME, 'infer', side_effect=RuntimeError('test worker unavailable')):
            code, created = self.call('/api/structure-generation/jobs', dict(workflow_id=task['id'], unit_confirmed=True))
            self.assertEqual(code, 200, created)
            job = self.wait_structure(created['id'])
            self.assertEqual(job['status'], 'failed')
            self.assertIn('unavailable', job['error'])
            self.assertIsNone(job['analysis_run_id'])
