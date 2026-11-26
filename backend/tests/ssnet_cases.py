"""SSnet HTTP permissions, grid alignment, persistence and cancellation."""
import copy
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import qa_assistant
import qa_stream
import ssnet
import app as backend
from model_history import enrich_model_history
from ssnet_contract import align, prepare_standards


class SSnetCases:
    def ssnet_training(self):
        task = self.task()
        return task, dict(name='QA reference', standards=[dict(workflow_id=task['id'])], unit_confirmed=True,
                          epochs=1,samples_per_epoch=32,rf_samples=32,trees=10,points=512)

    def wait_ssnet(self, job_id, token=None):
        for _ in range(150):
            code, value = self.request('/api/ssnet/jobs/'+job_id,token=token or self.auth['token'])
            self.assertEqual(code,200,value)
            if value['status'] not in ('queued','running'):
                return value
            time.sleep(.03)
        self.fail('SSnet did not finish')

    def test_ssnet_physical_grid_and_permissions(self):
        task, payload = self.ssnet_training()
        path='/api/ssnet/train/validate'
        self.assertEqual(self.request('/api/ssnet/config')[0],401)
        self.assertEqual(self.request(path,payload,token=self.other['token'])[0],404)
        self.assertEqual(self.call(path,dict(payload,unit_confirmed=False))[0],400)
        self.assertEqual(self.call(path,dict(payload,start=3000,end=4000))[0],400)
        self.assertEqual(self.call(path,dict(payload,name='   '))[0],400)
        code,value=self.call(path,payload)
        self.assertEqual(code,200,value)
        axis = task['original']['wavenumber']
        self.assertEqual(value['grid'], dict(start=min(axis), end=max(axis), points=512))
        grid=dict(start=200.,end=800.,points=128)
        spectrum=dict(wavenumber=[100,200,300,400,500,600,700,900],intensity=[-2,0,2,4,3,1,0,-1])
        original=copy.deepcopy(spectrum)
        desc={key:list(reversed(values)) for key,values in spectrum.items()}
        self.assertEqual(align(spectrum,grid),align(desc,grid))
        self.assertEqual(spectrum,original)
        with self.assertRaises(ValueError):
            align(spectrum,dict(grid,start=50))

    def test_ssnet_model_reuse_history_exports_and_failed_worker(self):
        task,payload=self.ssnet_training()
        fixture=dict(artifacts={'unet.pth':'hash','forest.joblib':'hash'},network_sha256='network',loss_history=[.1],duration_seconds=.1)
        with patch.object(ssnet,'execute_local',return_value=fixture):
            code,created=self.call('/api/ssnet/train',payload)
            self.assertEqual(code,200,created)
            model=self.wait_ssnet(created['id'])
            self.assertEqual(model['status'],'completed',model['error'])
            self.assertEqual(self.request('/api/ssnet/jobs/'+model['id'],token=self.other['token'])[0],404)
            self.assertEqual(self.request('/api/ssnet/jobs/'+model['id']+'/download',token=self.other['token'])[0],404)
            self.assertEqual(self.call('/api/ssnet/jobs/'+model['id']+'/cancel',{})[0],409)
        mixture=self.task()
        self.call('/api/ai-workflows/'+task['id'],method='DELETE')
        predict=dict(workflow_id=mixture['id'],model_id=model['id'],unit_confirmed=True)
        self.assertEqual(self.call('/api/ssnet/predict/validate',predict)[0],200)
        self.assertEqual(self.call('/api/ssnet/predict/validate',dict(predict,model_id='foreign'))[0],404)
        output=dict(wavenumber=[131,2653],mixture=[1,2],extracted=[.2,.4],background=[.8,1.6],rf_score=.5,inference_performed=True)
        with patch.object(ssnet,'execute_local',return_value=output):
            code,job=self.call('/api/ssnet/predict',predict)
            self.assertEqual(code,200,job)
            result=self.wait_ssnet(job['id'])
            self.assertEqual(result['status'],'completed',result['error'])
            run=self.call('/api/analysis-runs/'+result['analysis_run_id'])[1]['data']['run']
            processing=run['result'].pop('processing')
            self.assertEqual(processing['training_parameters']['trees'],10)
            self.assertEqual(processing['grid'],model['input']['prepared']['grid'])
            self.assertGreater(processing['normalization_scale'],0)
            with backend.db_connect() as conn:
                restored=enrich_model_history(conn,run)
            self.assertEqual(restored['result']['processing'],processing)
            for fmt in ['json','csv']:
                self.assertEqual(self.call('/api/ssnet/jobs/'+job['id']+'/download?format='+fmt)[0],200)
        with patch.object(ssnet,'execute_local',side_effect=RuntimeError('QA worker failure')):
            code,job=self.call('/api/ssnet/predict',predict)
            self.assertEqual(code,200,job)
            failed=self.wait_ssnet(job['id'])
            self.assertEqual(failed['status'],'failed')
            self.assertIn('QA worker failure',failed['error'])

    def test_only_ssnet_jobs_wait_in_submission_order(self):
        _, payload = self.ssnet_training()
        first_started, release_first = threading.Event(), threading.Event()
        started_jobs = []
        training = dict(artifacts={'unet.pth':'hash','forest.joblib':'hash'}, network_sha256='network',
                        loss_history=[.1], duration_seconds=.1)

        def train(directory, request, update, cancelled):
            started_jobs.append(directory.name)
            if len(started_jobs) == 1:
                first_started.set()
                release_first.wait(12)
            return training

        def reply():
            return self.format_upload('/api/qa-assistant/reply', 'example.csv',
                                      b'400,1\n500,2\n600,3', fields=dict(message='介绍拉曼光谱', allow_ai='true', stream='true'),
                                      file_field='spectrum')

        wave = list(range(400, 432))
        cube = dict(wavenumber=wave, spectra=[wave, wave], shape=[2, len(wave)], mode='series', steps=[])
        model = dict(provider='ollama', model='qwen3:test', base_url='http://127.0.0.1:11434')
        answer = io.BytesIO(b'{"message":{"content":"Complete answer"},"done":true,"done_reason":"stop"}\n')
        with patch.object(ssnet, 'execute_local', side_effect=train), \
             patch.object(qa_assistant.workflow, 'config', return_value=model), \
             patch.object(qa_stream, 'urlopen', return_value=answer), ThreadPoolExecutor(2) as requests:
            try:
                first_code, first = self.call('/api/ssnet/train', payload)
                self.assertEqual(first_code, 200, first)
                self.assertTrue(first_started.wait(5))
                second_code, second = self.call('/api/ssnet/train', dict(payload, name='Second reference'))
                self.assertEqual(second_code, 200, second)
                self.assertEqual(second['status'], 'queued')
                hyper = requests.submit(self.call, '/api/process-hyperspectral?stream=true', cube)
                chat = requests.submit(reply)
                for future, end in ((hyper, 'result'), (chat, 'done')):
                    code, body = future.result(timeout=5)
                    self.assertEqual(code, 200, body)
                    events = [json.loads(line) for line in body.decode().splitlines()]
                    self.assertEqual(events[-1]['type'], end, events)
                    self.assertFalse(any(item['type'] == 'queued' for item in events))
                self.assertEqual(started_jobs, [first['id']])
            finally:
                release_first.set()
            self.assertEqual(self.wait_ssnet(first['id'])['status'], 'completed')
            self.assertEqual(self.wait_ssnet(second['id'])['status'], 'completed')
            self.assertEqual(started_jobs, [first['id'], second['id']])

    def test_ssnet_cancellation_does_not_publish_an_unfinished_model(self):
        task,payload=self.ssnet_training()
        started=threading.Event()
        def work(directory,request,update,cancelled):
            update(dict(percent=12,stage='unet'))
            started.set()
            cancelled.wait(4)
            return dict(artifacts={},loss_history=[])
        with patch.object(ssnet,'execute_local',side_effect=work):
            code,job=self.call('/api/ssnet/train',payload)
            self.assertEqual(code,200,job)
            self.assertTrue(started.wait(3))
            self.assertEqual(self.request('/api/ssnet/jobs/'+job['id']+'/cancel',{},token=self.other['token'])[0],404)
            self.assertEqual(self.call('/api/ssnet/jobs/'+job['id']+'/cancel',{})[1]['status'],'cancelled')
            time.sleep(.1)
            value=self.call('/api/ssnet/jobs/'+job['id'])[1]
            self.assertEqual(value['status'],'cancelled')
            self.assertEqual(value['result'],{})

    def test_ssnet_project_revocation_hides_trained_model(self):
        import app as backend
        project=self.project()
        self.join(project)
        task,payload=self.ssnet_training()
        with backend.db_connect() as conn:
            conn.execute('UPDATE ai_workflows SET project_id=?,user_id=? WHERE id=?',(project,self.other['user']['id'],task['id']))
        token=self.other['token']
        with patch.object(ssnet,'execute_local',return_value=dict(artifacts={},loss_history=[])):
            code,job=self.request('/api/ssnet/train',payload,token=token)
            self.assertEqual(code,200,job)
            self.assertEqual(self.wait_ssnet(job['id'],token)['status'],'completed')
        output=dict(wavenumber=[131,2653],mixture=[1,2],extracted=[.2,.4],background=[.8,1.6],rf_score=.5,inference_performed=True)
        with patch.object(ssnet,'execute_local',return_value=output):
            code,prediction=self.request('/api/ssnet/predict',dict(workflow_id=task['id'],model_id=job['id'],unit_confirmed=True),token=token)
            self.assertEqual(code,200,prediction)
            prediction=self.wait_ssnet(prediction['id'],token)
            self.assertEqual(prediction['status'],'completed',prediction['error'])
        run_id=prediction['analysis_run_id']
        self.assertEqual(self.request('/api/analysis-runs/'+run_id,token=token)[0],200)
        self.assertEqual(self.call(f"/api/projects/{project}/members/{self.other['user']['id']}",method='DELETE')[0],200)
        self.assertEqual(self.request('/api/analysis-runs/'+run_id,token=token)[0],404)
        self.assertEqual(self.request('/api/ssnet/jobs/'+job['id'],token=token)[0],404)
        self.assertEqual(self.request('/api/ssnet/jobs/'+job['id']+'/download',token=token)[0],404)
        self.assertNotIn(job['id'],[j['id'] for j in self.request('/api/ssnet/jobs',token=token)[1]])
