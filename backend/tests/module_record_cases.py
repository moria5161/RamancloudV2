"""Module input isolation, source preservation and persistent named result records."""
import copy
import json
from unittest.mock import patch

import app as backend
import ssnet
import structure_generation as sg
from test_wxd_single import wxd_fixture


class ModuleRecordCases:
    def test_analysis_records_unfinished_completed_and_owner_isolation(self):
        self.assertEqual(self.request('/api/analysis-records/tasks')[0], 401)
        task = self.task()
        tasks = self.call('/api/analysis-records/tasks')[1]['items']
        self.assertIn(task['id'], [item.get('workflow_id') for item in tasks])
        other = self.request('/api/analysis-records/tasks', token=self.other['token'])[1]
        self.assertNotIn(task['id'], [item.get('workflow_id') for item in other['items']])
        version = self.plan(task)
        pending = next(item for item in self.call('/api/analysis-records/tasks')[1]['items'] if item.get('workflow_id') == task['id'])
        self.assertEqual(pending['version_id'], version['id'])
        self.call('/api/ai-workflows/' + task['id'] + '/versions/' + version['id'] + '/execute', {})
        done = self.wait_version(task, version['id'])
        self.assertEqual(done['status'], 'completed', done.get('error'))
        self.assertNotIn(task['id'], [item.get('workflow_id') for item in self.call('/api/analysis-records/tasks')[1]['items']])
        runs = self.call('/api/analysis-runs')[1]['data']['runs']
        self.assertEqual(sum(run['id'] == done['analysis_run_id'] for run in runs), 1)
        with backend.db_connect() as conn:
            old = json.loads(conn.execute('SELECT result_json FROM analysis_runs WHERE id=?', (done['analysis_run_id'],)).fetchone()['result_json'])
            old.pop('ai_version_number')
            conn.execute('UPDATE analysis_runs SET result_json=? WHERE id=?', (json.dumps(old), done['analysis_run_id']))
        restored = self.call('/api/analysis-runs/' + done['analysis_run_id'])[1]['data']['run']
        self.assertEqual(restored['result']['ai_version_number'], 1)

    def test_analysis_records_revoked_project_tasks_are_hidden(self):
        pid = self.project()
        self.join(pid)
        task = self.task()
        with backend.db_connect() as conn:
            conn.execute('UPDATE ai_workflows SET project_id=?,user_id=? WHERE id=?', (pid, self.other['user']['id'], task['id']))
        before = self.request('/api/analysis-records/tasks', token=self.other['token'])[1]
        self.assertIn(task['id'], [item.get('workflow_id') for item in before['items']])
        self.call(f"/api/projects/{pid}/members/{self.other['user']['id']}", method='DELETE')
        after = self.request('/api/analysis-records/tasks', token=self.other['token'])[1]
        self.assertNotIn(task['id'], [item.get('workflow_id') for item in after['items']])

    def test_analysis_records_batches_recover_without_the_old_sidebar(self):
        code, batch = self.batch_upload()
        self.assertEqual(code, 200, batch)
        summary = next(item for item in self.call('/api/analysis-records/tasks')[1]['batches'] if item['id'] == batch['id'])
        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['counts']['ready'], 2)
        tasks = self.call('/api/analysis-records/tasks')[1]['items']
        self.assertEqual(sum(item.get('batch_id') == batch['id'] for item in tasks), 2)
        self.assertNotIn(batch['id'], [item['id'] for item in self.request('/api/analysis-records/tasks', token=self.other['token'])[1]['batches']])

    def test_analysis_records_batch_members_keep_source_and_latest_processing_state(self):
        _, batch = self.batch_upload()
        member = batch['items'][0]
        task = dict(id=member['workflow_id'])
        pending = next(item for item in self.call('/api/analysis-records/tasks')[1]['items'] if item.get('workflow_id') == task['id'])
        self.assertEqual((pending['batch_id'], pending['batch_name']), (batch['id'], batch['name']))
        version = self.plan(task)
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/execute", {})
        done = self.wait_version(task, version['id'])
        self.assertEqual(done['status'], 'completed')
        feed = self.call('/api/analysis-records/tasks')[1]
        summary = next(item for item in feed['batches'] if item['id'] == batch['id'])
        self.assertEqual(summary['counts'], dict(completed=1, ready=1))
        self.assertNotIn(task['id'], [item.get('workflow_id') for item in feed['items']])
        record = next(item for item in self.call('/api/analysis-runs?summary=true')[1]['data']['runs'] if item['id'] == done['analysis_run_id'])
        self.assertEqual(record['batch_id'], batch['id'])
        self.assertTrue(record['batch_owned'])
        # Sharing a batch result preserves its category, but grants no access to
        # the owner's batch or its other, unshared files.
        pid = self.project()
        self.join(pid)
        code, shared = self.call(f"/api/analysis-runs/{record['id']}/warehouse", dict(project_id=pid, confirm_sharing=True))
        self.assertEqual(code, 200, shared)
        peer = self.request('/api/analysis-runs?summary=true&project_id=' + pid, token=self.other['token'])[1]['data']['runs']
        visible = next(item for item in peer if item['id'] == record['id'])
        self.assertEqual(visible['batch_id'], batch['id'])
        self.assertFalse(visible['batch_owned'])
        self.assertEqual(self.request('/api/ai-workflow-batches/' + batch['id'], token=self.other['token'])[0], 404)

    modules = ('ssnet', 'library-matching', 'structure-generation')

    def module_input(self, module, fields=None, name='module_spectrum.txt'):
        content = b'RamanShift(cm^-1)\tIntensity\n' + b'\n'.join(f'{200 + n * 100}\t{n*n + 1}'.encode() for n in range(41))
        code, data = self.format_upload(f'/api/{module}/sources/upload', name, content, fields)
        self.assertEqual(code, 200, data)
        return data, content

    def save_module(self, module, job):
        code, saved = self.call(f'/api/{module}/saved-results', dict(job_id=job['id'], title='QA named result'))
        self.assertEqual(code, 200, saved)
        return saved

    def test_module_records_uploads_never_create_preprocessing_tasks(self):
        before = self.call('/api/ai-workflows')[1]
        original_task = self.task()
        for module in self.modules:
            source, content = self.module_input(module)
            self.assertEqual(self.call('/api/ai-workflows/' + source['id'])[0], 404)
            records = self.call(f'/api/{module}/sources')[1]
            self.assertIn(source['id'], [item['id'] for item in records])
            self.assertEqual(self.call(f'/api/{module}/sources/{source["id"]}/download')[1], content)
            for other in self.modules:
                if other != module:
                    self.assertEqual(self.call(f'/api/{other}/sources/{source["id"]}')[0], 404)
        self.assertEqual({i['id'] for i in self.call('/api/ai-workflows')[1]}, {i['id'] for i in before} | {original_task['id']})

    def test_module_records_conversion_requires_confirmation_and_preserves_original(self):
        content, _, _ = wxd_fixture()
        for module in self.modules:
            path = f'/api/{module}/sources'
            before = self.call(path)[1]
            code, preview = self.format_upload(path + '/upload', 'sample.wxd', content)
            self.assertEqual(code, 200, preview)
            self.assertTrue(preview['requires_confirmation'])
            self.assertEqual(self.call(path)[1], before)
            code, source = self.format_upload(path + '/upload', 'sample.wxd', content, dict(confirm_conversion='true'))
            self.assertEqual(code, 200, source)
            self.assertTrue(source['diagnostics']['source_check']['conversion_confirmed'])
            self.assertEqual(self.call(path + '/' + source['id'] + '/download')[1], content)
            self.assertEqual(self.call(path + '/' + source['id'] + '/download?kind=standardized')[0], 200)

    def test_module_records_private_sources_and_explicit_copy_to_preprocessing(self):
        source, content = self.module_input('ssnet')
        route = '/api/ssnet/sources/' + source['id']
        self.assertEqual(self.request(route)[0], 401)
        self.assertEqual(self.request(route, token=self.other['token'])[0], 404)
        self.assertEqual(self.request(route + '/download', token=self.other['token'])[0], 404)
        before = len(self.call('/api/ai-workflows')[1])
        code, task = self.call(route + '/preprocess', {})
        self.assertEqual(code, 200, task)
        self.assertNotEqual(task['id'], source['id'])
        self.assertEqual(task['original'], source['original'])
        self.assertEqual(len(self.call('/api/ai-workflows')[1]), before + 1)
        self.call('/api/ai-workflows/' + task['id'], method='DELETE')
        self.assertEqual(self.call(route + '/download')[1], content, 'Deleting the copy must retain the module original')

    def test_module_records_retired_import_routes_are_unavailable(self):
        task = self.task()
        before = self.call('/api/ai-workflows')[1]
        self.assertEqual(self.call('/api/ai-workflows?scope=legacy')[0], 400)
        self.assertEqual(self.call('/api/ai-workflows/source', dict(legacy_workflow_id=task['id']))[0], 400)
        for module in self.modules:
            self.assertIn(self.call('/api/' + module + '/sources/from-legacy', dict(workflow_id=task['id']))[0], (404,405))
        self.assertEqual(self.call('/api/ai-workflows')[1], before)
        self.assertEqual(self.call('/api/ai-workflows/' + task['id'])[0], 200)

    def test_module_records_library_snapshot_save_is_idempotent_and_private(self):
        source, _ = self.module_input('library-matching')
        before = self.call('/api/ai-workflows')[1]
        with self.library_runtime():
            code, created = self.call('/api/library-matching/jobs', dict(source_id=source['id'], unit_confirmed=True, preprocessing_mode='prepared'))
            self.assertEqual(code, 200, created)
            job = self.wait_match(created['id'])
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertEqual(job['input']['source']['spectrum'], source['original'])
        saved = self.save_module('library-matching', job)
        self.assertEqual(self.save_module('library-matching', job)['id'], saved['id'])
        route = '/api/library-matching/saved-results/' + saved['id']
        value = self.call(route)[1]
        self.assertEqual(value['job']['input'], job['input'])
        self.assertEqual(value['job']['settings'], job['settings'])
        self.assertEqual(value['job']['result'], job['result'])
        self.assertEqual(self.request(route, token=self.other['token'])[0], 404)
        self.assertEqual(self.call('/api/ssnet/saved-results/' + saved['id'])[0], 404)
        self.assertEqual(self.call('/api/ai-workflows')[1], before)
        self.assertEqual(self.call('/api/library-matching/jobs/' + job['id'] + '/download?format=csv')[0], 200)

    def test_module_records_structure_save_reopens_full_candidates(self):
        source, _ = self.module_input('structure-generation')
        fixture = dict(inference_performed=True, duration_seconds=.01, dropped={}, ranking='matching_score',
                       candidates=[dict(id='1', rank=1, smiles='c1ccccc1', formula='C6H6', inchikey='key',
                                        matching_score=.2, generation_score=-5, image_png='fixture', sdf='fixture molblock')])
        with patch.object(sg, 'public_configuration', return_value={'ready': True}), patch.object(sg.RUNTIME, 'infer', side_effect=lambda *args: copy.deepcopy(fixture)):
            code, created = self.call('/api/structure-generation/jobs', dict(source_id=source['id'], unit_confirmed=True))
            self.assertEqual(code, 200, created)
            job = self.wait_structure(created['id'])
        self.assertEqual(job['status'], 'completed', job['error'])
        saved = self.save_module('structure-generation', job)
        # The analysis snapshot is independent of the upload record after freezing.
        with backend.db_connect() as conn:
            conn.execute('DELETE FROM structure_sources WHERE id=?', (source['id'],))
        reopened = self.call('/api/structure-generation/saved-results/' + saved['id'])[1]['job']
        self.assertEqual(reopened['result']['candidates'], job['result']['candidates'])
        self.assertEqual(reopened['input']['source']['spectrum'], source['original'])
        self.assertEqual(self.call('/api/structure-generation/jobs/' + job['id'] + '/download?format=sdf')[0], 200)

    def test_module_records_ssnet_retains_replicates_model_and_saved_extraction(self):
        first, _ = self.module_input('ssnet', name='standard_R1.txt')
        second, _ = self.module_input('ssnet', name='standard_R2.txt')
        train = dict(name='QA standard', standards=[dict(source_id=first['id']), dict(source_id=second['id'])], unit_confirmed=True,
                     points=128, epochs=1, samples_per_epoch=32, rf_samples=32, trees=10)
        fixture = dict(artifacts={'unet.pth':'hash','forest.joblib':'hash'}, network_sha256='network', loss_history=[.1], duration_seconds=.1)
        with patch.object(ssnet, 'execute_local', return_value=fixture):
            code, created = self.call('/api/ssnet/train', train)
            self.assertEqual(code, 200, created)
            model = self.wait_ssnet(created['id'])
        self.assertEqual(len(model['input']['sources']), 2)
        self.assertEqual(self.call('/api/ssnet/saved-results', dict(job_id=model['id'], title='Not an extraction'))[0], 409)
        output = dict(wavenumber=[200,4200], mixture=[1,2], extracted=[.2,.4], background=[.8,1.6], rf_score=.5, inference_performed=True)
        with patch.object(ssnet, 'execute_local', return_value=output):
            code, created = self.call('/api/ssnet/predict', dict(source_id=first['id'], model_id=model['id'], unit_confirmed=True))
            self.assertEqual(code, 200, created)
            job = self.wait_ssnet(created['id'])
        self.assertEqual(job['status'], 'completed', job['error'])
        saved = self.save_module('ssnet', job)
        self.assertTrue(job['analysis_run_id'])
        record = self.call('/api/analysis-runs/' + job['analysis_run_id'])[1]['data']['run']
        self.assertEqual(record['analysis_type'], 'mixture_analysis')
        self.assertEqual(record['result']['intensity'], output['extracted'])
        self.assertEqual(self.request('/api/analysis-runs/' + job['analysis_run_id'], token=self.other['token'])[0], 404)
        self.assertEqual(self.call('/api/analysis-runs/' + job['analysis_run_id'] + '/resources/data')[0], 200)
        reopened = self.call('/api/ssnet/saved-results/' + saved['id'])[1]['job']
        self.assertEqual(reopened['input']['model_id'], model['id'])
        self.assertEqual(reopened['result'], output)
        self.assertEqual(self.call('/api/ssnet/jobs/' + job['id'] + '/download?format=csv')[0], 200)

    def test_module_records_project_revocation_hides_inputs_and_saved_results(self):
        pid = self.project()
        self.join(pid)
        source, _ = self.module_input('library-matching', dict(project_id=pid))
        with backend.db_connect() as conn:
            conn.execute('UPDATE library_match_sources SET user_id=? WHERE id=?', (self.other['user']['id'], source['id']))
        with self.library_runtime():
            code, created = self.request('/api/library-matching/jobs', dict(source_id=source['id'], unit_confirmed=True, preprocessing_mode='prepared'), token=self.other['token'])
            self.assertEqual(code, 200, created)
            job = self.wait_match(created['id'], token=self.other['token'])
        code, saved = self.request('/api/library-matching/saved-results', dict(job_id=job['id'], title='Project result'), token=self.other['token'])
        self.assertEqual(code, 200, saved)
        self.call('/api/projects/' + pid + '/members/' + self.other['user']['id'], method='DELETE')
        for suffix in ['/sources/' + source['id'], '/sources/' + source['id'] + '/download', '/saved-results/' + saved['id']]:
            self.assertEqual(self.request('/api/library-matching' + suffix, token=self.other['token'])[0], 404)
        self.assertEqual(self.request('/api/library-matching/saved-results', token=self.other['token'])[1]['items'], [])
