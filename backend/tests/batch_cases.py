"""Batch HTTP cases run inside the same isolated app fixture as workflows."""
import io
import json
import threading
import time
import zipfile
from unittest.mock import patch


class BatchCases:
    def batch_upload(self, entries=None, confirm_conversion=False, **request):
        entries = entries or [('folder/a.csv', self.spectrum_bytes()), ('folder/sub/a.csv', self.spectrum_bytes(1.1))]
        boundary, pieces = 'raman-batch-test-boundary', []
        if confirm_conversion:
            pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="confirm_conversion"\r\n\r\ntrue\r\n'.encode())
        for path, content in entries:
            pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="paths"\r\n\r\n{path}\r\n'.encode())
            pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="spectrum.csv"\r\nContent-Type: text/plain\r\n\r\n'.encode() + content + b'\r\n')
        pieces.append(f'--{boundary}--\r\n'.encode())
        return self.call('/api/ai-workflow-batches/upload', raw=b''.join(pieces), content_type='multipart/form-data; boundary=' + boundary, **request)

    def spectrum_bytes(self, scale=1., points=40):
        return b'wave,intensity\n' + b'\n'.join(f'{i},{scale * (i * i + i % 3)}'.encode() for i in range(points))

    def batch_plan(self, batch):
        task = next(item['workflow_id'] for item in batch['items'] if item['workflow_id'])
        result = self.call(f'/api/ai-workflows/{task}/recommend', dict(goal='默认预处理', phase='preprocess'))[1]
        return dict(template_workflow_id=task, template_version_id=result['version']['id'], workflow_ids=[item['workflow_id'] for item in batch['items'] if item['workflow_id']])

    def wait_batch(self, bid):
        for _ in range(200):
            code, result = self.call('/api/ai-workflow-batches/' + bid)
            self.assertEqual(code, 200, result)
            if not result['active']:
                return result
            time.sleep(.03)
        self.fail('Batch did not finish')

    def test_batch_folder_import_validation_paths_and_permissions(self):
        code, batch = self.batch_upload([('folder/a.csv', self.spectrum_bytes()), ('folder/sub/a.csv', self.spectrum_bytes()), ('folder/readme.md', b'notes'), ('folder/bad.csv', b'no numeric rows')])
        self.assertEqual(code, 200, batch)
        self.assertEqual(batch['counts']['ready'], 2)
        self.assertEqual(batch['counts']['invalid'], 2)
        self.assertNotEqual(batch['items'][0]['workflow_id'], batch['items'][1]['workflow_id'])
        self.assertEqual(batch['items'][1]['relative_path'], 'folder/sub/a.csv')
        self.assertEqual(self.request('/api/ai-workflow-batches/' + batch['id'], token=self.other['token'])[0], 404)
        self.assertEqual(self.request('/api/ai-workflow-batches/' + batch['id'] + '/download', token=self.other['token'])[0], 404)
        self.assertEqual(self.request('/api/ai-workflow-batches')[0], 401)
        self.assertTrue(any(row['id'] == batch['id'] for row in self.call('/api/ai-workflow-batches')[1]))
        for name in ['../private.csv', '/absolute.csv', 'C:\\secret.csv']:
            self.assertEqual(self.batch_upload([(name, self.spectrum_bytes())])[0], 400)
        self.assertEqual(self.batch_upload([('same/a.csv', self.spectrum_bytes()), ('same/a.csv', self.spectrum_bytes())])[0], 400)

    def test_batch_limits_and_original_bytes(self):
        import ai_batch
        with patch.object(ai_batch, 'MAX_BATCH_FILES', 1):
            self.assertEqual(self.batch_upload()[0], 400)
        with patch.object(ai_batch, 'MAX_BATCH_BYTES', 20):
            self.assertEqual(self.batch_upload()[0], 400)
        code, batch = self.batch_upload([('folder/large.csv', b'1' * (4 * 1024 * 1024 + 1)), ('folder/good.csv', self.spectrum_bytes())])
        self.assertEqual(code, 200, batch)
        self.assertEqual(batch['counts']['invalid'], 1)
        item = batch['items'][1]
        self.assertEqual(self.call(f"/api/ai-workflows/{item['workflow_id']}/download?kind=original")[1], self.spectrum_bytes())

    def test_batch_process_history_download_and_new_versions(self):
        _, batch = self.batch_upload()
        body = self.batch_plan(batch)
        source = self.call(f"/api/ai-workflows/{body['template_workflow_id']}/versions/{body['template_version_id']}")[1]
        self.assertEqual(self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)[0], 200)
        result = self.wait_batch(batch['id'])
        self.assertEqual(result['counts']['completed'], 2, result)
        originals = []
        for item in result['items']:
            version = self.call(f"/api/ai-workflows/{item['workflow_id']}/versions/{item['version_id']}")[1]
            originals.append(version)
            self.assertIsNotNone(version['analysis_run_id'])
            self.assertEqual(version['metadata']['template_version_id'], body['template_version_id'])
        self.assertEqual(self.call(f"/api/ai-workflows/{body['template_workflow_id']}/versions/{body['template_version_id']}")[1], source)
        archive = self.call(f"/api/ai-workflow-batches/{batch['id']}/download")[1]
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            self.assertEqual(sum(name.endswith('/result.txt') for name in bundle.namelist()), 2)
            self.assertEqual(json.loads(bundle.read('manifest.json'))['counts']['completed'], 2)
        self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)
        rerun = self.wait_batch(batch['id'])
        self.assertEqual(rerun['counts']['completed'], 2)
        for previous, item in zip(originals, rerun['items']):
            self.assertNotEqual(item['version_id'], previous['id'])
            self.assertEqual(self.call(f"/api/ai-workflows/{item['workflow_id']}/versions/{previous['id']}")[1], previous)

    def test_batch_invalid_target_does_not_block_others(self):
        _, batch = self.batch_upload([('folder/long.csv', self.spectrum_bytes()), ('folder/short.csv', self.spectrum_bytes(points=8))])
        task = batch['items'][0]['workflow_id']
        steps = [dict(type='denoise', method='sg', params=dict(window_size=11, order=3))]
        plan = self.call(f'/api/ai-workflows/{task}/versions', dict(goal='降噪', steps=steps))[1]
        body = dict(template_workflow_id=task, template_version_id=plan['id'], workflow_ids=[item['workflow_id'] for item in batch['items']])
        self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)
        result = self.wait_batch(batch['id'])
        self.assertEqual(result['counts']['completed'], 1)
        self.assertEqual(result['counts']['failed'], 1)
        self.assertIn('SG', result['items'][1]['error'])

    def test_batch_owner_and_membership_checked_before_any_mutation(self):
        _, batch = self.batch_upload()
        body = self.batch_plan(batch)
        endpoint = f"/api/ai-workflow-batches/{batch['id']}/execute"
        self.assertEqual(self.request(endpoint, body, token=self.other['token'])[0], 404)
        stranger = self.task()
        self.assertEqual(self.call(endpoint, dict(body, workflow_ids=[stranger['id']]))[0], 404)
        self.assertEqual(self.call(endpoint, dict(body, workflow_ids=[body['workflow_ids'][0]] * 2))[0], 400)
        self.assertEqual(self.call('/api/ai-workflow-batches/' + batch['id'])[1]['counts']['ready'], 2)

    def test_batch_stop_pending_blocks_active_delete_and_duplicate_run(self):
        import app as backend
        _, batch = self.batch_upload([('folder/a.csv', self.spectrum_bytes()), ('folder/b.csv', self.spectrum_bytes()), ('folder/c.csv', self.spectrum_bytes())])
        body = self.batch_plan(batch)
        started, release = threading.Event(), threading.Event()
        original = backend.apply_pipeline
        def slow(*args):
            started.set()
            release.wait(8)
            return original(*args)
        try:
            with patch.dict(backend.__dict__, {'apply_pipeline': slow}):
                self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)
                self.assertTrue(started.wait(3))
                self.assertEqual(self.call(f"/api/ai-workflow-batches/{batch['id']}", method='DELETE')[0], 409)
                self.assertEqual(self.call(f"/api/ai-workflow-batches/{batch['id']}/items/{body['workflow_ids'][0]}", method='DELETE')[0], 409)
                self.assertEqual(self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)[0], 409)
                self.assertEqual(self.call(f"/api/ai-workflows/{body['workflow_ids'][1]}", method='DELETE')[0], 409)
                self.assertEqual(self.call(f"/api/ai-workflow-batches/{batch['id']}/download")[0], 409)
                stopped = self.call(f"/api/ai-workflow-batches/{batch['id']}/cancel", {})[1]
                self.assertEqual(stopped['counts']['cancelled'], 2)
                release.set()
                finished = self.wait_batch(batch['id'])
                self.assertEqual(finished['counts']['completed'], 1)
        finally:
            release.set()

    def test_batch_task_delete_clears_membership_but_keeps_history(self):
        _, batch = self.batch_upload()
        body = self.batch_plan(batch)
        self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)
        finished = self.wait_batch(batch['id'])
        item = finished['items'][0]
        version = self.call(f"/api/ai-workflows/{item['workflow_id']}/versions/{item['version_id']}")[1]
        self.assertEqual(self.call(f"/api/ai-workflows/{item['workflow_id']}", method='DELETE')[0], 200)
        report = self.call('/api/ai-workflow-batches/' + batch['id'])[1]
        self.assertEqual(report['items'][0]['status'], 'deleted')
        self.assertIsNone(report['items'][0]['workflow_id'])
        self.assertEqual(self.call(f"/api/analysis-runs/{version['analysis_run_id']}")[0], 200)

    def test_batch_subset_leaves_unselected_sources_unchanged(self):
        _, batch = self.batch_upload()
        body = self.batch_plan(batch)
        body['workflow_ids'] = body['workflow_ids'][:1]
        self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)
        result = self.wait_batch(batch['id'])
        self.assertEqual(result['counts']['completed'], 1)
        self.assertEqual(result['counts']['ready'], 1)
        other = result['items'][1]
        self.assertIsNone(other['version_id'])
        self.assertEqual(self.call(f"/api/ai-workflows/{other['workflow_id']}")[1]['versions'], [])

    def test_batch_records_read_completed_versions_after_result_rows_are_deleted(self):
        _, batch = self.batch_upload([('folder/a.csv',self.spectrum_bytes()), ('folder/b.csv',self.spectrum_bytes()), ('folder/notes.txt',b'invalid')])
        body = self.batch_plan(batch)
        self.call(f"/api/ai-workflow-batches/{batch['id']}/execute",body)
        done = self.wait_batch(batch['id'])
        for item in done['items'][:2]:
            version = self.call(f"/api/ai-workflows/{item['workflow_id']}/versions/{item['version_id']}")[1]
            self.assertEqual(self.call('/api/analysis-runs/'+version['analysis_run_id'],method='DELETE')[0],200)
        before = self.call('/api/analysis-runs')[1]
        feed = self.call('/api/analysis-records/tasks')[1]
        files = [item for item in feed['items'] if item.get('batch_id') == batch['id']]
        self.assertEqual(len(files),3)
        self.assertEqual(sum(item.get('result_available',False) for item in files),2)
        self.assertTrue(all(item['result'].get('intensity') for item in files if item.get('result_available')))
        self.assertEqual(sum(item['kind'] == 'batch_item' for item in files),1)
        self.assertEqual(self.call('/api/analysis-runs')[1],before,'Reading versions must not recreate deleted result rows')

    def test_batch_delete_and_selected_member_deletion_are_guarded_and_complete(self):
        _, batch = self.batch_upload([('folder/a.csv',self.spectrum_bytes()),('folder/b.csv',self.spectrum_bytes()),('folder/notes.txt',b'notes')])
        body = self.batch_plan(batch)
        self.call(f"/api/ai-workflow-batches/{batch['id']}/execute",body)
        done = self.wait_batch(batch['id'])
        first, second, invalid = done['items']
        first_version = self.call(f"/api/ai-workflows/{first['workflow_id']}/versions/{first['version_id']}")[1]
        rid = first_version['analysis_run_id']
        pid = self.project()
        self.call('/api/analysis-runs/'+rid+'/warehouse',dict(project_id=pid,confirm_sharing=True))
        endpoint = '/api/ai-workflow-batches/'+batch['id']
        self.assertEqual(self.request(endpoint,method='DELETE',token=self.other['token'])[0],404)
        self.assertEqual(self.call(endpoint,method='DELETE')[0],409)
        self.assertEqual(self.call('/api/ai-workflows/'+second['workflow_id'])[0],200,'Blocked deletion must not remove earlier members')
        self.assertEqual(self.call('/api/analysis-runs/'+rid+'/warehouse',method='DELETE')[0],200)
        self.assertEqual(self.call(endpoint+'/items/'+first['workflow_id'],method='DELETE')[0],200)
        self.assertEqual(self.call('/api/analysis-runs/'+rid)[0],404)
        self.assertEqual(self.call('/api/ai-workflows/'+first['workflow_id'])[0],404)
        self.assertEqual(self.call('/api/ai-workflows/'+second['workflow_id'])[0],200)
        self.assertEqual(self.call(endpoint+'/items/'+invalid['id'],method='DELETE')[0],200)
        self.assertFalse(any(item.get('item_id') == invalid['id'] for item in self.call('/api/analysis-records/tasks')[1]['items']))
        self.assertEqual(self.call(endpoint,method='DELETE')[0],200)
        self.assertEqual(self.call(endpoint)[0],404)
        self.assertEqual(self.call('/api/ai-workflows/'+second['workflow_id'])[0],404)

    def test_batch_runtime_failure_preserves_other_results(self):
        import app as backend
        _, batch = self.batch_upload([('folder/a.csv', self.spectrum_bytes()), ('folder/b.csv', self.spectrum_bytes()), ('folder/c.csv', self.spectrum_bytes())])
        body = self.batch_plan(batch)
        original, calls = backend.apply_pipeline, []
        template = self.call(f"/api/ai-workflows/{body['template_workflow_id']}/versions/{body['template_version_id']}")[1]
        first_file_steps = sum(step['enabled'] for step in template['steps'])
        def fail_middle(*args):
            calls.append(1)
            if len(calls) == first_file_steps + 1:
                raise ValueError('Injected middle-file failure')
            return original(*args)
        with patch.dict(backend.__dict__, {'apply_pipeline': fail_middle}):
            self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)
            result = self.wait_batch(batch['id'])
        self.assertEqual(result['counts']['completed'], 2, result)
        self.assertEqual(result['counts']['failed'], 1)
        self.assertIn('Injected middle-file failure', result['items'][1]['error'])

    def test_batch_feedback_revision_reaches_every_new_version_without_overwriting_results(self):
        _, batch = self.batch_upload()
        body = self.batch_plan(batch)
        self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)
        completed = self.wait_batch(batch['id'])
        originals = [self.call(f"/api/ai-workflows/{item['workflow_id']}/versions/{item['version_id']}")[1] for item in completed['items']]
        parent = originals[0]
        feedback = '峰变弱了，减小平滑窗口，其他步骤保持不变'
        response = self.call(f"/api/ai-workflows/{body['template_workflow_id']}/recommend", dict(
            goal=parent['goal'], feedback=feedback, parent_id=parent['id'], phase='refine'))[1]
        revised = response['version']
        self.assertEqual(revised['feedback'], feedback)
        revised_noise = next(step for step in revised['steps'] if step['method'] == 'sg')
        parent_noise = next(step for step in parent['steps'] if step['method'] == 'sg')
        self.assertEqual(revised_noise['params']['window_size'], parent_noise['params']['window_size'] - 2)
        self.assertEqual(revised['steps'][0]['params'], parent['steps'][0]['params'])
        preview = self.call(f"/api/ai-workflows/{body['template_workflow_id']}/versions/{revised['id']}/preview", {})[1]
        self.assertEqual(preview['status'], 'preview')
        self.assertEqual(preview['reused_steps'], 1)
        body['template_version_id'] = revised['id']
        self.assertEqual(self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", body)[0], 200)
        result = self.wait_batch(batch['id'])
        self.assertEqual(result['counts']['completed'], 2)
        for old, item in zip(originals, result['items']):
            new = self.call(f"/api/ai-workflows/{item['workflow_id']}/versions/{item['version_id']}")[1]
            self.assertEqual(new['feedback'], feedback)
            self.assertEqual(new['steps'], revised['steps'])
            self.assertEqual(new['metadata']['template_version_id'], revised['id'])
            self.assertNotEqual(new['id'], old['id'])
            self.assertEqual(self.call(f"/api/ai-workflows/{item['workflow_id']}/versions/{old['id']}")[1], old)
