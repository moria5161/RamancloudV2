import copy
import json
from unittest.mock import patch
import app as backend
import structure_generation as sg


class ModelHistoryCases:
    def test_model_history_library_freezes_curves_and_restores_legacy_without_writes(self):
        source,_=self.module_input('library-matching')
        with self.library_runtime():
            code,created=self.call('/api/library-matching/jobs',dict(source_id=source['id'],unit_confirmed=True,preprocessing_mode='prepared'))
            self.assertEqual(code,200,created)
            job=self.wait_match(created['id'])
        rid=job['analysis_run_id']
        with backend.db_connect() as conn:
            original=conn.execute('SELECT result_json FROM analysis_runs WHERE id=?',(rid,)).fetchone()['result_json']
            conn.execute('UPDATE library_match_jobs SET result_json=? WHERE id=?',(json.dumps(dict(candidates=[])),job['id']))
        frozen=self.call('/api/analysis-runs/'+rid)[1]['data']['run']['result']
        self.assertEqual(frozen['model_input'],job['result']['model_input'])
        with backend.db_connect() as conn:
            conn.execute('UPDATE library_match_jobs SET result_json=? WHERE id=?',(json.dumps(job['result']),job['id']))
            thin=json.loads(original)
            for key in ('model_input','input_preview','preprocessing'):
                thin.pop(key,None)
            for candidate in thin['candidates']:
                candidate.pop('reference',None)
            encoded=json.dumps(thin)
            conn.execute('UPDATE analysis_runs SET result_json=? WHERE id=?',(encoded,rid))
        restored=self.call('/api/analysis-runs/'+rid)[1]['data']['run']['result']
        self.assertEqual(restored['model_input'],job['result']['model_input'])
        self.assertEqual(restored['candidates'][0]['reference'],job['result']['candidates'][0]['reference'])
        with backend.db_connect() as conn:
            self.assertEqual(conn.execute('SELECT result_json FROM analysis_runs WHERE id=?',(rid,)).fetchone()['result_json'],encoded)
        pid=self.project();self.join(pid)
        self.call('/api/analysis-runs/'+rid+'/warehouse',dict(project_id=pid,confirm_sharing=True))
        self.assertEqual(self.request('/api/library-matching/jobs/'+job['id'],token=self.other['token'])[0],404)
        shared=self.request('/api/analysis-runs/'+rid,token=self.other['token'])[1]['data']['run']['result']
        self.assertEqual(shared['candidates'],restored['candidates'])
        self.call('/api/projects/'+pid+'/members/'+self.other['user']['id'],method='DELETE')
        self.assertEqual(self.request('/api/analysis-runs/'+rid,token=self.other['token'])[0],404)

    def test_model_history_structure_images_survive_and_legacy_job_link_is_exact(self):
        source,_=self.module_input('structure-generation')
        fixture=dict(inference_performed=True,duration_seconds=.01,dropped={},ranking='matching_score',candidates=[dict(id='1',rank=1,smiles='CCO',formula='C2H6O',image_png='saved-image',matching_score=.2,generation_score=-5,sdf='mol')])
        with patch.object(sg,'public_configuration',return_value={'ready':True}),patch.object(sg.RUNTIME,'infer',side_effect=lambda *args:copy.deepcopy(fixture)):
            _,created=self.call('/api/structure-generation/jobs',dict(source_id=source['id'],unit_confirmed=True))
            job=self.wait_structure(created['id'])
        rid=job['analysis_run_id']
        run=self.call('/api/analysis-runs/'+rid)[1]['data']['run']
        self.assertEqual(run['result']['candidates'][0]['image_png'],'saved-image')
        thin=copy.deepcopy(run['result']);thin['candidates'][0].pop('image_png')
        with backend.db_connect() as conn:
            conn.execute('UPDATE analysis_runs SET result_json=? WHERE id=?',(json.dumps(thin),rid))
        self.assertEqual(self.call('/api/analysis-runs/'+rid)[1]['data']['run']['result']['candidates'][0]['image_png'],'saved-image')
        with backend.db_connect() as conn:
            conn.execute('UPDATE structure_jobs SET analysis_run_id=NULL WHERE id=?',(job['id'],))
        self.assertNotIn('image_png',self.call('/api/analysis-runs/'+rid)[1]['data']['run']['result']['candidates'][0])
