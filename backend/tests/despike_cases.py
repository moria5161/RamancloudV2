import copy
import io
import json
import zipfile

import numpy as np
from test_despike import spectrum


class DespikeCases:
    def test_despike_updated_policy_does_not_reuse_old_correction(self):
        import app as backend
        task, x, clean, noisy = self.despike_task()
        base = '/api/ai-workflows/' + task['id']
        steps = [dict(type='despike', method='despike', params={})]
        code, version = self.call(base + '/versions', dict(goal='去鬼峰', steps=steps))
        self.assertEqual(code, 200, version)
        self.call(base + '/versions/' + version['id'] + '/execute', {})
        done = self.wait_version(task, version['id'])
        old_trace = copy.deepcopy(done['trace'])
        old_trace[0]['details'].pop('repair_policy')
        old_trace[0]['after']['intensity'][100] = -9999
        with backend.db_connect() as conn:
            conn.execute('UPDATE ai_plan_versions SET trace_json=? WHERE id=?', (json.dumps(old_trace), version['id']))
        code, child = self.call(base + '/versions', dict(goal='去鬼峰', steps=done['steps'], parent_id=version['id']))
        self.assertEqual(code, 200, child)
        code, preview = self.call(base + '/versions/' + child['id'] + '/preview', {})
        self.assertEqual(code, 200, preview)
        self.assertEqual(preview['reused_steps'], 0)
        self.assertAlmostEqual(preview['preview'][0]['after']['intensity'][100], done['trace'][0]['after']['intensity'][100])

    def test_despike_saved_raw_and_result_downloads_keep_full_precision(self):
        from spectral_formats import parse_single
        task, x, clean, noisy = self.despike_task()
        base = '/api/ai-workflows/' + task['id']
        code, version = self.call(base + '/versions', dict(goal='去鬼峰', steps=[dict(type='despike', method='despike', params={})]))
        self.assertEqual(code, 200, version)
        self.call(base + '/versions/' + version['id'] + '/execute', {})
        done = self.wait_version(task, version['id'])
        raw = self.call(base + '/download?kind=standardized')[1]
        result = self.call(base + '/download?kind=result&version_id=' + version['id'])[1]
        rx, ry, _ = parse_single(raw, 'raw.txt')
        px, py, _ = parse_single(result, 'result.txt')
        np.testing.assert_array_equal(rx, x); np.testing.assert_array_equal(ry, noisy)
        np.testing.assert_array_equal(px, done['trace'][-1]['after']['wavenumber'])
        np.testing.assert_array_equal(py, done['trace'][-1]['after']['intensity'])

    def despike_task(self):
        x, clean, noisy = spectrum()
        content = ('RamanShift(cm^-1)\tIntensity\n' + '\n'.join(f'{a:.17g}\t{b:.17g}' for a, b in zip(x, noisy))).encode()
        code, task = self.format_upload('/api/ai-workflows/upload', 'spikes.txt', content)
        self.assertEqual(code, 200, task)
        return task, x, clean, noisy

    def test_despike_default_order_details_execution_and_reproduction(self):
        task, x, clean, noisy = self.despike_task()
        code, proposed = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal='默认预处理', phase='preprocess'))
        self.assertEqual(code, 200, proposed)
        version = proposed['version']
        self.assertEqual([step['type'] for step in version['steps']], ['despike', 'denoise', 'baseline'])
        path = f"/api/ai-workflows/{task['id']}/versions/{version['id']}"
        code, preview = self.call(path + '/preview', {})
        self.assertEqual(code, 200, preview)
        trace = preview['preview']
        self.assertEqual(trace[0]['details']['num_cosmic_rays'], 2)
        self.assertEqual(trace[0]['details']['cosmic_rays'][0]['peak_idx'], 100)
        self.assertEqual(trace[0]['after']['wavenumber'], x.tolist())
        np.testing.assert_array_equal(trace[1]['before']['intensity'], trace[0]['after']['intensity'])
        self.assertEqual(self.call(path + '/execute', {})[0], 200)
        done = self.wait_version(task, version['id'])
        self.assertEqual(done['status'], 'completed', done['error'])
        self.assertEqual(done['trace'][0]['details'], trace[0]['details'])
        code, bundle = self.call(f"/api/ai-workflows/{task['id']}/download?version_id={version['id']}")
        self.assertEqual(code, 200)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertIn('step_1_despike.txt', archive.namelist())
            self.assertEqual(json.loads(archive.read('workflow.json'))['version']['trace'][0]['details']['num_cosmic_rays'], 2)
        replay = self.call(f"/api/ai-workflows/{task['id']}/versions", dict(goal=version['goal'], steps=version['steps'], parent_id=version['id']))[1]
        self.call(f"/api/ai-workflows/{task['id']}/versions/{replay['id']}/execute", dict(recompute_all=True))
        repeated = self.wait_version(task, replay['id'])
        np.testing.assert_array_equal(repeated['trace'][-1]['after']['intensity'], done['trace'][-1]['after']['intensity'])
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}")[1]['original'], task['original'])

    def test_despike_skip_order_and_threshold_contract(self):
        task, _, _, noisy = self.despike_task()
        base = f"/api/ai-workflows/{task['id']}"
        spike = dict(type='despike', method='despike', params={'threshold': None, 'fwhm_threshold': 4}, enabled=False)
        code, version = self.call(base + '/versions', dict(goal='跳过去鬼峰', steps=[spike]))
        self.assertEqual(code, 200, version)
        preview = self.call(base + '/versions/' + version['id'] + '/preview', {})[1]['preview'][0]
        self.assertEqual(preview['status'], 'skipped')
        np.testing.assert_array_equal(preview['after']['intensity'], noisy)
        noise = dict(type='denoise', method='sg', params={'window_size': 7, 'order': 3})
        self.assertEqual(self.call(base + '/versions', dict(goal='错误顺序', steps=[noise, dict(spike, enabled=True)]))[0], 400)
        invalid = copy.deepcopy(spike); invalid['params']['threshold'] = -1
        self.assertEqual(self.call(base + '/versions', dict(goal='错误参数', steps=[invalid]))[0], 400)

    def test_despike_batch_keeps_per_spectrum_detection_results(self):
        x, _, y = spectrum()
        encode = lambda values: ('RamanShift(cm^-1)\tIntensity\n' + '\n'.join(f'{a:.17g}\t{b:.17g}' for a, b in zip(x, values))).encode()
        code, batch = self.batch_upload([('folder/spikes.txt', encode(y)), ('folder/flat.txt', encode(np.ones(len(x))))])
        self.assertEqual(code, 200, batch)
        first = batch['items'][0]['workflow_id']
        code, version = self.call(f'/api/ai-workflows/{first}/versions', dict(goal='仅去鬼峰', steps=[dict(type='despike', method='despike', params={})]))
        self.assertEqual(code, 200, version)
        self.call(f"/api/ai-workflow-batches/{batch['id']}/execute", dict(template_workflow_id=first, template_version_id=version['id'], workflow_ids=[item['workflow_id'] for item in batch['items']]))
        completed = self.wait_batch(batch['id'])
        self.assertEqual(completed['counts']['completed'], 2)
        details = [self.call(f"/api/ai-workflows/{item['workflow_id']}/versions/{item['version_id']}")[1]['trace'][0]['details'] for item in completed['items']]
        self.assertEqual([item['num_cosmic_rays'] for item in details], [2, 0])

    def test_despike_time_series_api_history_and_rerun(self):
        import app as backend
        x, _, y = spectrum()
        data = np.vstack([y, np.ones(len(x))])
        dataset = backend.register_dataset(x, data, 'time_series', 'spikes.txt')
        code, response = self.call('/api/process-hyperspectral', dict(dataset_id=dataset, wavenumber=x.tolist(), save_history=True,
            steps=[dict(type='despike', method='despike', params={})]))
        self.assertEqual(code, 200, response)
        out = response['data']
        self.assertEqual(out['shape'], [2, len(x)])
        np.testing.assert_array_equal(backend.DATASETS[dataset]['data'], data)
        self.assertEqual(out['analysis_run']['history'][0]['details']['num_cosmic_rays'], 2)
        code, rerun = self.call(f"/api/analysis-runs/{out['analysis_run']['id']}/rerun", {})
        self.assertEqual(code, 200, rerun)
        self.assertEqual(rerun['data']['run']['history'][0]['details']['num_cosmic_rays'], 2)
