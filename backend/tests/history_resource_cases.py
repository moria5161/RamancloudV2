import io
import zipfile
from unittest.mock import patch
import numpy as np
import app as backend
from history_resources import spectrum_csv

class HistoryResourceCases:
    def test_history_summary_and_rename(self):
        rid = self.collab_run(self.project())
        code, value = self.call('/api/analysis-runs/'+rid, dict(title='可识别的结果名称'), method='PATCH')
        self.assertEqual(code, 200, value)
        self.assertEqual(self.request('/api/analysis-runs/'+rid,dict(title='unauthorized'),method='PATCH',token=self.other['token'])[0],404)
        self.assertEqual(self.call('/api/analysis-runs/'+rid,dict(title='  '),method='PATCH')[0],422)
        compact = next(r for r in self.call('/api/analysis-runs?summary=true')[1]['data']['runs'] if r['id']==rid)
        self.assertEqual(compact['title'],'可识别的结果名称')
        self.assertEqual(compact['input'],{})
        self.assertEqual(compact['versions'],[])
        self.assertLessEqual(len(compact['result']['intensity']),60)
        self.assertEqual(len(self.call('/api/analysis-runs/'+rid)[1]['data']['run']['input']['intensity']),40)
    def test_warehouse_preview_archive_and_batch_provenance(self):
        pid = self.project()
        content = self.spectrum_bytes()
        code, uploaded = self.format_upload('/api/projects/'+pid+'/datasets/upload', 'sample.csv', content,
                                             dict(data_kind='raw'), file_field='files')
        self.assertEqual(code, 200, uploaded)
        did = uploaded['data']['datasets'][0]['id']
        preview = '/api/datasets/'+did+'/preview'
        archive = '/api/projects/'+pid+'/archive?ids='+did
        self.assertEqual(self.call(preview)[1]['points'], 40)
        code, standard = self.call(preview+'?download=true')
        self.assertEqual(code,200,standard)
        self.assertEqual(len(standard.decode('utf-8-sig').strip().splitlines()),41)
        self.assertEqual(self.request(preview, token=self.other['token'])[0], 404)
        self.join(pid)
        self.assertEqual(self.request(preview, token=self.other['token'])[0], 200)
        code, body = self.call(archive)
        self.assertEqual(code, 200)
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            self.assertEqual(z.read(z.namelist()[0]), content)
        self.assertEqual(self.call('/api/projects/'+self.project()+'/archive?ids='+did)[0], 404)
        self.assertEqual(self.call('/api/datasets/'+did, dict(data_kind='processed'), method='PATCH')[0], 400)
        def batch(data, asset_id=did):
            return self.format_upload('/api/ai-workflow-batches/upload', 'sample.csv', data,
                dict(project_id=pid, paths='folder/sample.csv', dataset_ids=asset_id), file_field='files')
        code, result = batch(content)
        self.assertEqual(code, 200, result)
        task = result['items'][0]['workflow_id']
        with backend.db_connect() as conn:
            self.assertEqual(conn.execute('SELECT source_dataset_id FROM ai_workflows WHERE id=?', (task,)).fetchone()['source_dataset_id'], did)
        self.assertEqual(batch(content+b'\n1,2')[0], 400)
        self.assertEqual(batch(content, 'missing')[0], 404)
        self.call('/api/projects/'+pid+'/members/'+self.other['user']['id'], method='DELETE')
        self.assertEqual(self.request(preview, token=self.other['token'])[0], 404)
        self.assertEqual(self.request(archive, token=self.other['token'])[0], 404)

    def test_history_hyperspectral_member_rerun_and_delete_cleanup(self):
        pid = self.project()
        self.join(pid)
        rid, cube = self.resource_cube()
        base = '/api/analysis-runs/'+rid
        code, result = self.call(base+'/warehouse', dict(project_id=pid, confirm_sharing=True))
        self.assertEqual(code, 200, result)
        with backend.db_connect() as conn:
            row = conn.execute('SELECT * FROM analysis_runs WHERE id=?', (rid,)).fetchone()
            source_id = backend.row_to_analysis_run(row)['input']['dataset_id']
        self.assertEqual(backend.DATASETS[source_id]['project_id'], pid)
        code, rerun = self.request(base+'/rerun', {}, token=self.other['token'])
        self.assertEqual(code, 200, rerun)
        own = rerun['data']['run']
        self.assertNotEqual(own['input']['dataset_id'], source_id)
        self.assertEqual(own['user_id'], self.other['user']['id'])
        self.assertEqual(self.call('/api/analysis-runs/'+own['id'])[0], 404)
        with backend.db_connect() as conn:
            paths = [r['storage_path'] for r in conn.execute('SELECT storage_path FROM analysis_array_files WHERE run_id=?', (own['id'],)).fetchall()]
        self.assertEqual(self.request('/api/analysis-runs/'+own['id'], method='DELETE', token=self.other['token'])[0], 200)
        with backend.db_connect() as conn:
            self.assertFalse(conn.execute('SELECT * FROM analysis_array_files WHERE run_id=?', (own['id'],)).fetchall())
        for path in paths:
            with self.assertRaises(backend.HTTPException):
                backend.read_stored_file(path)

    def test_history_time_series_persistent_preview(self):
        wave, data = np.arange(30, dtype=float), np.arange(120, dtype=float).reshape(4,30)
        a = backend.register_dataset(wave,data,'time_series','time.mat',self.auth['user'])
        run = backend.save_analysis_run(current_user=self.auth['user'],analysis_type='hyperspectral',source_name='time.mat',steps=[],input_payload={'dataset_id':a},result_payload={'processed_dataset_id':a},history=[])
        backend.DATASETS.clear()
        code, value = self.call('/api/analysis-runs/'+run['id']+'/visualization')
        self.assertEqual(code, 200, value)
        self.assertEqual(value['mode'], 'time_series')
        np.testing.assert_array_equal(value['preview'], data)

    def test_history_imaging_flat_input_preserves_spatial_dimensions(self):
        wave=np.arange(30,dtype=float)+400
        cube=np.arange(180,dtype=float).reshape(2,3,30)+np.arange(30)**2
        code,response=self.call('/api/process-hyperspectral',dict(wavenumber=wave.tolist(),spectra=cube.reshape(6,30).tolist(),shape=[2,3,30],mode='imaging',save_history=True,steps=[dict(type='baseline',method='airpls',params=dict(lam=1000,diff_order=2))]))
        self.assertEqual(code,200,response)
        run=response['data']['analysis_run']
        np.testing.assert_array_equal(run['input']['mean_spectrum'], cube.mean(axis=(0,1)))
        for role in ('original','processed'):
            value=self.call('/api/analysis-runs/'+run['id']+'/visualization?role='+role+'&x=2&y=1&wavenumber=410')[1]
            self.assertEqual(value['mode'],'imaging')
            self.assertEqual(value['shape'],[2,3,30])
            if role=='original':
                np.testing.assert_array_equal(value['pixel']['intensity'],cube[1,2])
                np.testing.assert_array_equal(value['preview'],cube[:,:,10])
        self.assertEqual(self.call('/api/process-hyperspectral',dict(wavenumber=wave.tolist(),spectra=cube.reshape(6,30).tolist(),shape=[2,4,30],mode='imaging',steps=[]))[0],400)

    def test_hyperspectral_sampled_preview_keeps_full_series_and_export(self):
        wave = np.arange(1200, 599, -1, dtype=float)
        spectra = np.arange(260)[:, None] * 1000 + wave
        source = backend.mapping_payload(wave, spectra, 'time_series', 'series.txt', self.auth['user'])
        rows = source['preview_y']
        self.assertEqual((rows[0], rows[-1]), (0, 259))
        self.assertEqual((source['preview_x'][0], source['preview_x'][-1]), (1200, 600))
        self.assertEqual(np.shape(source['preview']), (128, 512))
        np.testing.assert_array_equal(source['preview'], np.asarray(rows)[:, None] * 1000 + source['preview_x'])

        steps = [dict(type='cut', params=dict(start=630, end=1170))]
        code, response = self.call('/api/process-hyperspectral', dict(dataset_id=source['dataset_id'],
            wavenumber=source['wavenumber'], steps=steps, save_history=True))
        self.assertEqual(code, 200, response)
        result = response['data']
        rid = result['analysis_run']['id']
        self.assertEqual(result['shape'], [260, 541])
        visual = self.call(f'/api/analysis-runs/{rid}/visualization?role=processed')[1]
        self.assertEqual(visual['preview_y'], rows)
        self.assertEqual(visual['preview_x'], result['preview_x'])
        self.assertEqual(visual['preview'], result['preview'])
        self.assertEqual(result['analysis_run']['result']['preview_y'], rows)
        rerun = self.call(f'/api/analysis-runs/{rid}/rerun', {})[1]['data']['result']
        self.assertEqual(rerun['preview_x'], result['preview_x'])
        self.assertEqual(rerun['preview_y'], rows)

        index = rows[97]
        output_id = result['processed_dataset_id']
        point = self.call(f'/api/hyperspectral-spectrum/{output_id}?index={index}')[1]['data']
        expected = wave[(wave >= 630) & (wave <= 1170)]
        np.testing.assert_array_equal(point['intensity'], index * 1000 + expected)
        code, exported = self.call('/api/download', dict(dataset_id=output_id, wavenumber=result['wavenumber']))
        self.assertEqual(code, 200)
        table = np.loadtxt(io.BytesIO(exported))
        self.assertEqual(table.shape, (541, 261))
        np.testing.assert_array_equal(table[:, 0], expected)
        np.testing.assert_array_equal(table[:, index + 1], index * 1000 + expected)

    def test_hyperspectral_tsvd_limit_uses_the_shape_at_the_step(self):
        import legacy_algorithms as legacy

        wave = np.arange(401, 421, dtype=float)
        spectra = np.arange(240, dtype=float).reshape(12, 20)
        source = backend.register_dataset(wave, spectra, 'time_series', 'tsvd.txt', self.auth['user'])
        payload = dict(dataset_id=source, wavenumber=wave.tolist(), save_history=True)
        tsvd = dict(type='denoise', method='tsvd')
        with patch.object(legacy, 'availability', return_value=(True, '')), \
                patch.object(legacy, 'TSVD_MAX_WORK', 500):
            with patch.object(legacy.subprocess, 'run') as worker:
                code, response = self.call('/api/process-hyperspectral', dict(payload, steps=[tsvd]))
                self.assertEqual(code, 413, response)
                self.assertIn('裁剪', response['detail'])
                worker.assert_not_called()
        # The crop moves the matrix below the budget before calling the algorithm.
        with patch.object(legacy, 'TSVD_MAX_WORK', 500), \
                patch.object(backend, 'denoise_matrix', wraps=backend.denoise_matrix) as denoise:
            cut = dict(type='cut', params=dict(start=402, end=407))
            if legacy.availability(legacy.METHODS['tsvd'])[0]:
                code, response = self.call('/api/process-hyperspectral', dict(payload, steps=[cut, tsvd]))
                self.assertEqual(code, 200, response)
                self.assertEqual(denoise.call_args.args[0].shape, (12, 6))
                rid = response['data']['analysis_run']['id']
                with patch.object(legacy, 'TSVD_MAX_WORK', 300):
                    self.assertEqual(self.call(f'/api/analysis-runs/{rid}/rerun', {})[0], 413)

    def test_history_imaging_saves_selected_physical_slice(self):
        wave=np.arange(30,dtype=float)+400
        cube=np.arange(180,dtype=float).reshape(2,3,30)
        payload=dict(wavenumber=wave.tolist(),spectra=cube.reshape(6,30).tolist(),shape=[2,3,30],mode='imaging',save_history=True,steps=[],preview_wavenumber=411.25)
        code,value=self.call('/api/process-hyperspectral',payload)
        self.assertEqual(code,200,value)
        self.assertEqual(value['data']['preview_wavenumber'],411.)
        run=value['data']['analysis_run']
        self.assertEqual(run['result']['preview_wavenumber'],411.)
        for role in ('original','processed'):
            visual=self.call('/api/analysis-runs/'+run['id']+'/visualization?role='+role+'&wavenumber=411')[1]
            np.testing.assert_array_equal(visual['preview'],cube[:,:,11])
        self.assertEqual(self.call('/api/process-hyperspectral',dict(payload,preview_wavenumber=float('nan')))[0],422)
        code,outside=self.call('/api/process-hyperspectral',dict(payload,preview_wavenumber=99999))
        self.assertEqual(code,200,outside)
        self.assertTrue(400 <= outside['data']['preview_wavenumber'] <=429)

    def test_history_legacy_flat_imaging_arrays_are_viewed_without_rewriting(self):
        wave=np.arange(30,dtype=float)+400
        cube=np.arange(180,dtype=float).reshape(2,3,30)
        user=self.auth['user']
        source=backend.register_dataset(wave,cube.reshape(6,30),'imaging','legacy.mat',user)
        processed=backend.register_dataset(wave,cube+1,'imaging','result.mat',user)
        run=backend.save_analysis_run(user,'hyperspectral','legacy.mat',[],dict(dataset_id=source,shape=[2,3,30]),dict(processed_dataset_id=processed,shape=[2,3,30]),[])
        backend.DATASETS.clear()
        code,value=self.call('/api/analysis-runs/'+run['id']+'/visualization?role=original&x=2&y=1&wavenumber=410')
        self.assertEqual(code,200,value)
        self.assertEqual(value['shape'],[2,3,30])
        self.assertEqual(value['mode'],'imaging')
        np.testing.assert_array_equal(value['pixel']['intensity'],cube[1,2])
        original=self.call('/api/analysis-runs/'+run['id'])[1]['data']['run']['input']['dataset_id']
        self.assertEqual(backend.DATASETS[original]['data'].shape,(6,30))

    def resource_cube(self):
        cube = np.arange(140,dtype=float).reshape(4,5,7)/19
        wave = np.arange(7,dtype=float)+100.123456789012
        user = self.auth['user']
        a = backend.register_dataset(wave,cube,'mapping','input.mat',user)
        b = backend.register_dataset(wave,cube+1,'mapping','result.mat',user)
        run = backend.save_analysis_run(current_user=user,analysis_type='hyperspectral',source_name='input.mat',steps=[],input_payload={'dataset_id':a},result_payload={'processed_dataset_id':b},history=[])
        return run['id'],cube

    def test_history_resources_cube(self):
        rid,cube = self.resource_cube()
        base = '/api/analysis-runs/'+rid
        backend.DATASETS.clear()
        from scipy.io import loadmat
        code,body = self.call(base+'/resources/data')
        self.assertEqual(code,200,body)
        np.testing.assert_array_equal(loadmat(io.BytesIO(body))['cube'],cube+1)
        self.assertTrue(self.call(base+'/resources/png?wavenumber=102')[1].startswith(b'\x89PNG'))
        for role,expected in [('original',cube),('processed',cube+1)]:
            code,v = self.call(base+'/visualization?role='+role+'&x=3&y=2&wavenumber=102')
            self.assertEqual(code,200,v)
            np.testing.assert_array_equal(v['pixel']['intensity'],expected[2,3,:])
            self.assertEqual(v['shape'],[4,5,7])
        self.assertEqual(self.call(base+'/visualization?x=5&y=0')[0],422)
        for suffix in ['/resources/original','/resources/data','/visualization']:
            self.assertEqual(self.request(base+suffix,token=self.other['token'])[0],404)
        with backend.db_connect() as conn:
            conn.execute('DELETE FROM analysis_array_files WHERE run_id=?',(rid,))
        backend.DATASETS.clear()
        self.assertEqual(self.call(base+'/visualization')[0],409)

    def test_history_resources_warehouse(self):
        pid=self.project()
        self.join(pid)
        rid=self.collab_run(pid)
        base='/api/analysis-runs/'+rid
        self.assertEqual(self.call(base+'/warehouse',dict(project_id=pid))[0],400)
        self.assertEqual(self.request(base+'/resources/original',token=self.other['token'])[0],404)
        payload=dict(project_id=pid,confirm_sharing=True)
        first=self.call(base+'/warehouse',payload)
        self.assertEqual(first[0],200,first)
        self.assertEqual(self.call(base+'/warehouse',payload),first)
        self.assertEqual(self.request(base+'/resources/original',token=self.other['token'])[0],200)
        self.assertEqual(self.request(base+'/warehouse',method='DELETE',token=self.other['token'])[0],403)
        self.assertEqual(self.call(base+'/warehouse',method='DELETE')[0],200)
        self.assertEqual(self.request(base+'/resources/data',token=self.other['token'])[0],404)
        self.assertEqual(self.call(base+'/resources/data')[0],200)
        self.call(base+'/warehouse',payload)
        self.call('/api/projects/'+pid+'/members/'+self.other['user']['id'],method='DELETE')
        self.assertEqual(self.request(base+'/resources/original',token=self.other['token'])[0],404)

    def test_history_resources_report(self):
        base='/api/analysis-runs/'+self.collab_run(self.project())
        with patch.object(backend,'store_project_file',side_effect=AssertionError('GET must not persist')):
            code,body=self.call(base+'/resources/report')
            self.assertEqual(code,200,body)
            self.assertTrue(body.startswith(b'%PDF-'))
            code,body=self.call(base+'/resources/bundle')
            self.assertEqual(code,200)
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                self.assertTrue({'figure.png','figure.svg','report.pdf','process.json','processed/processed.csv'} <= set(archive.namelist()))
        v=1.1234567890123457
        self.assertIn(repr(v),spectrum_csv(dict(wavenumber=[v],intensity=[v])).decode('utf-8-sig'))

    def test_history_resources_rollback(self):
        with backend.db_connect() as conn:
            count=conn.execute('SELECT COUNT(*) AS n FROM analysis_runs').fetchone()['n']
        with patch.object(backend,'store_project_file',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.resource_cube()
        with backend.db_connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM analysis_runs').fetchone()['n'],count)

    def test_history_resources_reference_guard_and_candidates(self):
        import csv
        from history_resources import result_file
        for kind in ('library_matching','structure_generation'):
            run={'analysis_type':kind,'result':{'candidates':[dict(rank=1,class_id=7,name='saved candidate',smiles='C',formula='CH4',inchikey='saved-key',model_score=0.12345678901234567)]}}
            name,body=result_file(vars(backend),run)
            rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
            self.assertEqual(rows[0]['inchikey'],'saved-key')
            self.assertEqual(float(rows[0]['model_score']),0.12345678901234567)
        pid=self.project()
        rid=self.collab_run(pid)
        base='/api/analysis-runs/'+rid
        did=self.call(base+'/warehouse',dict(project_id=pid,confirm_sharing=True))[1]['dataset_id']
        other=backend.save_analysis_run(current_user=self.auth['user'],analysis_type='spectrum',source_name='derived.csv',steps=[],input_payload={'wavenumber':[1,2],'intensity':[3,4]},result_payload={'wavenumber':[1,2],'intensity':[3,4]},history=[],project_id=pid,source_dataset_id=did)
        self.assertEqual(self.call(base+'/warehouse',method='DELETE')[0],200)
        with backend.db_connect() as conn:
            self.assertIsNone(conn.execute('SELECT result_dataset_id FROM analysis_runs WHERE id=?',(rid,)).fetchone()['result_dataset_id'])
            self.assertIsNotNone(conn.execute('SELECT id FROM data_assets WHERE id=?',(did,)).fetchone())
            conn.execute('UPDATE analysis_runs SET source_dataset_id=NULL WHERE id=?',(other['id'],))
        code,task=self.call('/api/ai-workflows/source',dict(dataset_id=did))
        self.assertEqual(code,200,task)
        new_did=self.call(base+'/warehouse',dict(project_id=pid,confirm_sharing=True))[1]['dataset_id']
        code,task=self.call('/api/ai-workflows/source',dict(dataset_id=new_did))
        self.assertEqual(code,200,task)
        self.assertEqual(self.call(base+'/warehouse',method='DELETE')[0],200)
        self.assertEqual(self.call('/api/ai-workflows/'+task['id'])[0],200)
        listed=self.call('/api/projects/'+pid+'/datasets')[1]['data']['datasets']
        self.assertNotIn(new_did,[item['id'] for item in listed])
        self.assertEqual(self.call(base,method='DELETE')[0],200)
        self.assertEqual(self.call('/api/ai-workflows/'+task['id'])[0],200)

    def test_history_resources_cache_scope_and_missing_file(self):
        rid,cube=self.resource_cube()
        base='/api/analysis-runs/'+rid
        with backend.db_connect() as conn:
            run=backend.row_to_analysis_run(backend.get_analysis_run_row(conn,rid,self.auth['user']))
            path=conn.execute("SELECT storage_path FROM analysis_array_files WHERE run_id=? AND role='processed'",(rid,)).fetchone()['storage_path']
        key=run['result']['processed_dataset_id']
        backend.DATASETS[key]['owner_id']=self.other['user']['id']
        self.assertEqual(self.call(base+'/visualization')[0],409)
        backend.DATASETS.clear()
        backend.remove_stored_file(path)
        self.assertEqual(self.call(base+'/visualization')[0],409)
        self.assertEqual(self.call(base+'/resources/data')[0],409)
