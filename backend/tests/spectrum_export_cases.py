"""Read-only batch export of complete saved arrays and completed workflow traces."""


class SpectrumExportCases:
    def export(self, spectra, **options):
        return self.call('/api/spectra/export-data',dict(spectra=spectra,**options))

    def test_spectrum_export_full_arrays_precision_versions_and_no_mutation(self):
        task = self.task()
        version = self.plan(task)
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/execute",{})
        done = self.wait_version(task,version['id'])
        original_versions = self.call('/api/ai-workflows/'+task['id'])[1]['versions']
        original_runs = self.call('/api/analysis-runs')[1]
        for reference in [dict(workflow_id=task['id']),dict(workflow_id=task['id'],version_id=version['id']),dict(run_id=done['analysis_run_id'])]:
            code, data = self.export([reference],original=True,processed=True)
            self.assertEqual(code,200,data)
            self.assertEqual(data['items'][0]['original'],task['original'])
            self.assertEqual(data['items'][0]['processed'],{key:done['trace'][-1]['after'][key] for key in ('wavenumber','intensity')})
            self.assertEqual(data['items'][0]['version'],1)
            self.assertEqual(data['skipped'],[])
        self.assertEqual(self.call('/api/ai-workflows/'+task['id'])[1]['versions'],original_versions)
        self.assertEqual(self.call('/api/analysis-runs')[1],original_runs)
        self.call('/api/analysis-runs/'+done['analysis_run_id'],method='DELETE')
        data = self.export([dict(workflow_id=task['id'],version_id=version['id'])])[1]
        self.assertEqual(data['items'][0]['processed'],{key:done['trace'][-1]['after'][key] for key in ('wavenumber','intensity')})
        self.assertNotIn(done['analysis_run_id'],[item['id'] for item in self.call('/api/analysis-runs')[1]['data']['runs']])

    def test_spectrum_export_incomplete_versions_are_never_final_results(self):
        task = self.task()
        version = self.plan(task)
        refs = [dict(workflow_id=task['id'],version_id=version['id'])]
        code, data = self.export(refs)
        self.assertEqual(code,200,data)
        self.assertEqual(data['items'],[])
        self.assertEqual(data['skipped'][0]['role'],'processed')
        data = self.export(refs,original=True)[1]
        self.assertEqual(data['items'][0]['original'],task['original'])
        self.assertNotIn('processed',data['items'][0])
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/execute",{})
        done = self.wait_version(task,version['id'])
        newer = self.plan(task)
        auto = self.export([dict(workflow_id=task['id'])])[1]['items'][0]
        self.assertEqual(auto['version_id'],done['id'])
        self.assertEqual(self.export([dict(workflow_id=task['id'],version_id=newer['id'])])[1]['items'],[])

    def test_spectrum_export_auth_boundaries_and_all_or_nothing_reads(self):
        task = self.task()
        payload = dict(spectra=[dict(workflow_id=task['id'])],original=True,processed=False)
        self.assertEqual(self.request('/api/spectra/export-data',payload)[0],401)
        self.assertEqual(self.request('/api/spectra/export-data',payload,token=self.other['token'])[0],404)
        self.assertEqual(self.export([dict(workflow_id=task['id']),dict(workflow_id='missing')],original=True)[0],404)
        foreign = self.task()
        version = self.plan(foreign)
        self.assertEqual(self.export([dict(workflow_id=task['id'],version_id=version['id'])])[0],404)

    def test_spectrum_export_saved_shared_run_respects_project_revocation(self):
        pid = self.project()
        self.join(pid)
        rid = self.collab_run(pid)
        payload = dict(spectra=[dict(run_id=rid)],original=True,processed=True)
        route = '/api/spectra/export-data'
        self.assertEqual(self.request(route,payload,token=self.other['token'])[0],404)
        self.call('/api/analysis-runs/'+rid+'/warehouse',dict(project_id=pid,confirm_sharing=True))
        code, data = self.request(route,payload,token=self.other['token'])
        self.assertEqual(code,200,data)
        self.assertTrue(data['items'][0]['processed']['intensity'])
        self.call('/api/projects/'+pid+'/members/'+self.other['user']['id'],method='DELETE')
        self.assertEqual(self.request(route,payload,token=self.other['token'])[0],404)

    def test_spectrum_export_input_limits(self):
        task = self.task()
        self.assertEqual(self.export([])[0],422)
        self.assertEqual(self.export([dict(workflow_id=task['id'])]*101)[0],422)
        self.assertEqual(self.export([dict(workflow_id=task['id'])],original=False,processed=False)[0],422)
        self.assertEqual(self.export([dict(workflow_id=task['id'],run_id='both')])[0],422)
        data = self.export([dict(workflow_id=task['id'])]*2,original=True,processed=False)[1]
        self.assertEqual(len(data['items']),1)
