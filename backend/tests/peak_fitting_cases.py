import copy
import io
import time
import zipfile
from unittest.mock import patch
import peak_fitting


class PeakFittingCases:
    def test_peak_fit_uses_completed_baseline_versions_without_an_external_attestation(self):
        task=self.task();version=self.plan(task)
        self.call('/api/ai-workflows/'+task['id']+'/versions/'+version['id']+'/execute',{})
        done=self.wait_version(task,version['id']);self.assertEqual(done['status'],'completed',done.get('error'))
        spectrum=done['trace'][-1]['after'];x,y=spectrum['wavenumber'],spectrum['intensity']
        center=x[max(range(len(y)),key=lambda i:y[i])];lo,hi=min(x),max(x);width=(hi-lo)/25
        p=peak_fitting.Peak(center=center,center_min=max(lo,center-1),center_max=min(hi,center+1),width=width,width_min=width*.9,width_max=width*1.1).dict()
        payload=dict(workflow_id=task['id'],version_id=version['id'],start=lo,end=hi,peaks=[p],unit_confirmed=True,baseline_confirmed=False)
        code,value=self.call('/api/peak-fitting/validate',payload);self.assertEqual(code,200,value)
        self.assertEqual(self.call('/api/peak-fitting/validate',dict(payload,version_id=None))[0],400)
        self.assertEqual(self.request('/api/peak-fitting/validate',payload,token=self.other['token'])[0],404)

    def fit_upload(self):
        code, example=self.call('/api/peak-fitting/example')
        self.assertEqual(code,200)
        content='\n'.join('%s\t%s'%pair for pair in zip(example['spectrum']['wavenumber'],example['spectrum']['intensity'])).encode()
        boundary='peak-fit-boundary'
        body=b'--'+boundary.encode()+b'\r\nContent-Disposition: form-data; name="file"; filename="peaks.txt"\r\nContent-Type: text/plain\r\n\r\n'+content+b'\r\n--'+boundary.encode()+b'--\r\n'
        code,source=self.call('/api/peak-fitting/sources/upload',raw=body,content_type='multipart/form-data; boundary='+boundary)
        self.assertEqual(code,200,source)
        return dict(source_id=source['id'],unit_confirmed=True,baseline_confirmed=True,**example['settings'])

    def wait_fit(self,jid):
        for _ in range(120):
            code,value=self.call('/api/peak-fitting/jobs/'+jid)
            self.assertEqual(code,200,value)
            if value['status'] not in ('queued','running'):return value
            time.sleep(.03)
        self.fail('Fitting did not finish')

    def test_peak_fitting_requires_auth_baseline_units_valid_bounds_and_owns_sources(self):
        self.assertEqual(self.request('/api/peak-fitting/example')[0],401)
        payload=self.fit_upload()
        endpoint='/api/peak-fitting/jobs'
        for key in ('unit_confirmed','baseline_confirmed'):
            self.assertEqual(self.call(endpoint,dict(payload,**{key:False}))[0],400)
        self.assertEqual(self.request(endpoint,payload,token=self.other['token'])[0],404)
        bad=copy.deepcopy(payload);bad['peaks'][0]['center_min']=1000
        self.assertEqual(self.call(endpoint,bad)[0],400)
        self.assertEqual(self.call(endpoint,dict(payload,unexpected='no'))[0],422)

    def test_peak_fit_persists_exact_curves_history_exports_and_owner_isolation(self):
        payload=self.fit_upload()
        code,created=self.call('/api/peak-fitting/jobs',payload);self.assertEqual(code,200,created)
        job=self.wait_fit(created['id']);self.assertEqual(job['status'],'completed',job['error'])
        self.assertGreater(job['result']['r_squared'],.99999999)
        for suffix in ('','/download?kind=bundle'):
            self.assertEqual(self.request('/api/peak-fitting/jobs/'+job['id']+suffix,token=self.other['token'])[0],404)
        run=self.call('/api/analysis-runs/'+job['analysis_run_id'])[1]['data']['run']
        self.assertEqual(run['analysis_type'],'peak_fitting');self.assertEqual(run['result']['components'],job['result']['components'])
        self.assertEqual(run['title'],job['source_name'])  # No hard-coded Chinese suffix in English record lists.
        self.assertEqual(run['steps'][0]['params']['peaks'],payload['peaks'])
        code,data=self.call('/api/peak-fitting/jobs/'+job['id']+'/download?kind=bundle');self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertTrue({'peak_parameters.csv','curves.tsv','peak_1.txt','peak_2.txt','peak_3.txt','residual.txt','settings.json','fit.png'}<=set(archive.namelist()))
            self.assertTrue(archive.read('fit.png').startswith(b'\x89PNG'))
        for kind in ('data','curves','png','bundle','json'):
            code,data=self.call('/api/analysis-runs/'+run['id']+'/resources/'+kind)
            self.assertEqual(code,200,(kind,data))
        replay=dict(payload);replay.pop('source_id');replay['reuse_job_id']=job['id']
        code,again=self.call('/api/peak-fitting/jobs',replay);self.assertEqual(code,200,again)
        self.assertEqual(self.wait_fit(again['id'])['input'],job['input'])

    def test_peak_fit_failure_is_recorded_without_fabricating_a_result(self):
        payload=self.fit_upload()
        with patch.object(peak_fitting,'fit',side_effect=ValueError('injected failure')):
            code,job=self.call('/api/peak-fitting/jobs',payload);self.assertEqual(code,200)
            done=self.wait_fit(job['id'])
        self.assertEqual(done['status'],'failed');self.assertFalse(done['result']);self.assertIsNone(done['analysis_run_id'])
        items=self.call('/api/analysis-records/tasks')[1]['items']
        self.assertIn(done['id'],[i.get('job_id') for i in items if i['analysis_type']=='peak_fitting'])
