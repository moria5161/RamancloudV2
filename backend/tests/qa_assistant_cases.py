"""HTTP cases mixed into the existing isolated workflow fixture; no real AI calls."""
import base64
import io
import json
from unittest.mock import patch

from PIL import Image
import qa_assistant as qa

ENDPOINT = '/api/qa-assistant/reply'
SETTINGS = dict(provider='ollama', model='text-test', base_url='http://127.0.0.1:11434')


class QaAssistantCases:
    def test_qa_selected_spectrum_context_excludes_other_native_positions(self):
        import app as backend
        task = self.task()
        with backend.db_connect() as conn:
            row = conn.execute('SELECT diagnostics_json FROM ai_workflows WHERE id=?', (task['id'],)).fetchone()
            value = json.loads(row['diagnostics_json'])
            value['source_check'] = dict(axis_unit='cm^-1', warnings=['仪器横轴未校准'],
                                        spectrum_choices=[dict(preview='OTHER_POSITION_' * 10000)])
            conn.execute('UPDATE ai_workflows SET diagnostics_json=? WHERE id=?', (json.dumps(value), task['id']))
        code, evidence = self.call('/api/qa-assistant/context/' + task['id'])
        self.assertEqual(code, 200, evidence)
        self.assertIn('仪器横轴未校准', evidence['original']['import_warnings'])
        self.assertNotIn('OTHER_POSITION_', json.dumps(evidence))
        self.assertLess(len(json.dumps(evidence)), 5000)

    def test_qa_saved_record_uses_shared_result_permissions_and_same_values(self):
        task = self.task(); version = self.plan(task)
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/execute", {})
        done = self.wait_version(task, version['id']); run_id = done['analysis_run_id']
        with patch.object(qa.workflow, 'call_chat_completion', return_value='依据[comparison]解释已完成的结果') as model:
            code, result = self.format_upload(ENDPOINT, 'a.csv', b'400,1\n500,2\n600,3', fields=self.qa_fields(run_id=run_id), file_field='spectrum')
        self.assertEqual(code, 200, result)
        self.assertEqual(result['evidence']['run_id'], run_id)
        self.assertEqual(result['evidence']['comparison']['after']['points'], len(done['trace'][-1]['after']['intensity']))
        self.assertIn(run_id, model.call_args[0][1][-1]['content'])
        route = '/api/qa-assistant/records/' + run_id + '/context'
        self.assertEqual(self.request(route, token=self.other['token'])[0], 404)
        pid = self.project(); self.join(pid)
        self.assertEqual(self.call('/api/analysis-runs/' + run_id + '/warehouse', dict(project_id=pid, confirm_sharing=True))[0], 200)
        self.assertEqual(self.request(route, token=self.other['token'])[0], 200)
        self.call(f"/api/projects/{pid}/members/{self.other['user']['id']}", method='DELETE')
        self.assertEqual(self.request(route, token=self.other['token'])[0], 404)
        self.assertEqual(self.format_upload(ENDPOINT, 'a.csv', b'400,1\n500,2\n600,3',
            fields=self.qa_fields(run_id=run_id,task_id=task['id']), file_field='spectrum')[0], 400)

    def test_qa_live_page_context_is_evidence_not_execution(self):
        context = dict(page='智能光谱处理', observed_at='2026-11-04T12:00:00Z',
                       state=dict(status='running', unsaved_changes=True,
                                  displayed_steps=[dict(method='sg', params=dict(window_size=7))]))
        with patch.object(qa.workflow, 'call_chat_completion', return_value='当前任务仍在运行，请等待。') as model:
            code, value = self.format_upload(ENDPOINT, 'sample.csv', b'400,1\n500,2\n600,3',
                fields=self.qa_fields(page_context=json.dumps(context)), file_field='spectrum')
        self.assertEqual(code, 200, value)
        self.assertIn('screen', [source['id'] for source in value['sources']])
        current = model.call_args[0][1][-1]
        self.assertNotIn('images', current)
        self.assertIn('unsaved_changes', current['content'])
        self.assertNotIn('command', value)

    def test_qa_context_comparison_and_owner_checks(self):
        task = self.task()
        version = self.plan(task)
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/preview", {})
        path = f"/api/qa-assistant/context/{task['id']}?version_id={version['id']}"
        code, evidence = self.call(path)
        self.assertEqual(code, 200, evidence)
        self.assertEqual(evidence['version_id'], version['id'])
        self.assertEqual(evidence['comparison']['before']['points'], evidence['comparison']['after']['points'])
        self.assertGreaterEqual(evidence['comparison']['rmse_change'], 0)
        self.assertLessEqual(len(evidence['comparison']['sampled_pairs']), 48)
        self.assertEqual(self.request(path, token=self.other['token'])[0], 404)
        with patch.object(qa.workflow, 'call_chat_completion', return_value='依据[comparison]解释') as model:
            code, value = self.format_upload(ENDPOINT, 'a.png', self.qa_image(),
                fields=self.qa_fields(task_id=task['id'], version_id=version['id']), file_field='screenshot')
        self.assertEqual(code, 200, value)
        self.assertEqual(value['evidence']['version_id'], version['id'])
        self.assertIn('rmse_change', model.call_args[0][1][-1]['content'])

    def test_qa_proposal_validated_without_mutation(self):
        task = self.task()
        version = self.plan(task)
        fields = dict(task_id=task['id'], version_id=version['id'], request='保留峰形，仅调整降噪', allow_ai=True)
        with patch.object(qa.workflow, 'call_chat_model', return_value=dict(steps=version['steps'], summary='调整建议')):
            code, proposal = self.call('/api/qa-assistant/propose', fields)
        self.assertEqual(code, 200, proposal)
        self.assertEqual(proposal['parent_id'], version['id'])
        self.assertEqual(len(self.call(f"/api/ai-workflows/{task['id']}")[1]['versions']), 1)
        with patch.object(qa.workflow, 'call_chat_model', return_value=dict(steps=[dict(type='command', method='exec')])):
            self.assertEqual(self.call('/api/qa-assistant/propose', fields)[0], 503)
        self.assertEqual(self.call('/api/qa-assistant/propose', dict(fields, allow_ai=False))[0], 400)
        self.assertEqual(self.request('/api/qa-assistant/propose', fields, token=self.other['token'])[0], 404)

    def test_qa_stream_complete_and_failure(self):
        with patch.object(qa.workflow, 'config', return_value=SETTINGS), patch.object(qa, 'tokens', return_value=iter(['第一段', '第二段'])):
            code, body = self.format_upload(ENDPOINT, 'sample.csv', b'400,1\n500,2\n600,3',
                fields=self.qa_fields(stream='true'), file_field='spectrum')
        self.assertEqual(code, 200)
        items = [json.loads(line) for line in body.decode().splitlines()]
        self.assertEqual(items[-1]['type'], 'done')
        self.assertEqual(''.join(i.get('text','') for i in items), '第一段第二段')
        def broken(*args):
            yield '片段'
            raise RuntimeError('secret-key')
        with patch.object(qa.workflow, 'config', return_value=SETTINGS), patch.object(qa, 'tokens', side_effect=broken):
            _, body = self.format_upload(ENDPOINT, 'sample.csv', b'400,1\n500,2\n600,3', fields=self.qa_fields(stream='true'), file_field='spectrum')
        self.assertNotIn(b'secret-key', body)
        self.assertEqual(json.loads(body.decode().splitlines()[-1])['type'], 'error')

    def test_qa_stream_length_limit_is_not_network_failure(self):
        def limited(*args):
            yield '保留的回答'
            raise qa.ResponseTruncated()
        with patch.object(qa, 'tokens', side_effect=limited):
            _, body = self.format_upload(ENDPOINT, 'sample.csv', b'400,1\n500,2\n600,3', fields=self.qa_fields(stream='true'), file_field='spectrum')
        items = [json.loads(line) for line in body.decode().splitlines()]
        self.assertEqual(items[-1], dict(type='done', truncated=True))
        self.assertFalse(any(i['type']=='error' for i in items))
        self.assertIn('保留的回答', body.decode())

    def test_qa_two_streams_do_not_reacquire_their_own_slots(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(2)
        def overlapping(*args):
            barrier.wait(timeout=5)
            yield '完成'
        def request():
            return self.format_upload(ENDPOINT, 'sample.csv', b'400,1\n500,2\n600,3', fields=self.qa_fields(stream='true'), file_field='spectrum')
        with patch.object(qa, '_SLOTS', threading.BoundedSemaphore(2)), patch.object(qa, 'tokens', side_effect=overlapping):
            with ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(request) for _ in range(2)]
                for future in futures:
                    code, body = future.result(timeout=10)
                    self.assertEqual(code, 200)
                    self.assertEqual(json.loads(body.decode().splitlines()[-1]), dict(type='done'))
            self.assertTrue(qa._SLOTS.acquire(blocking=False))
            self.assertTrue(qa._SLOTS.acquire(blocking=False))
            qa._SLOTS.release();qa._SLOTS.release()

    def test_qa_project_notes_sharing_and_revocation(self):
        pid = self.project()
        path = f'/api/qa-assistant/projects/{pid}/notes'
        payload = dict(title='基线讨论', content='用户明确保存的 AI 讨论，需要复核。')
        code, note = self.call(path, payload)
        self.assertEqual(code, 200, note)
        self.assertEqual(self.request(path, token=self.other['token'])[0], 404)
        self.join(pid)
        self.assertEqual(self.request(path + '/' + note['id'], token=self.other['token'])[0], 200)
        self.assertEqual(self.request(path + '/' + note['id'], token=self.other['token'], method='DELETE')[0], 403)
        self.assertEqual(self.call(path + '/' + note['id'], method='DELETE')[0], 200)
        private = self.task()
        self.assertEqual(self.call(path, dict(payload, task_id=private['id']))[0], 400)
        task = self.format_upload('/api/ai-workflows/upload', 'project-spectrum.csv', self.spectrum_bytes(), fields=dict(project_id=pid))[1]
        version = self.plan(task)
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/preview", {})
        associated = dict(payload, task_id=task['id'], version_id=version['id'], expected_status='draft')
        self.assertEqual(self.call(path, associated)[0], 409)
        code, saved = self.call(path, dict(associated, expected_status='preview'))
        self.assertEqual(code, 200, saved)
        value = self.request(path + '/' + saved['id'], token=self.other['token'])[1]
        self.assertEqual(json.loads(value['evidence_json'])['version_id'], version['id'])
        self.call(f"/api/projects/{pid}/members/{self.other['user']['id']}", method='DELETE')
        self.assertEqual(self.request(path, token=self.other['token'])[0], 404)

    def qa_fields(self, **extra):
        return dict(message='解释拉曼峰的含义', allow_ai='true', **extra)

    def qa_image(self, size=(30, 20)):
        output = io.BytesIO()
        Image.new('RGB', size, 'white').save(output, format='PNG')
        return output.getvalue()

    def test_qa_auth_consent_and_validation(self):
        self.assertEqual(self.request(ENDPOINT, raw=b'message=hi',
                                     content_type='application/x-www-form-urlencoded')[0], 401)
        with patch.object(qa.workflow, 'call_chat_completion', side_effect=AssertionError('no consent')):
            code, value = self.format_upload(ENDPOINT, 'image.png', self.qa_image(),
                                            fields={'message': '解释图片'}, file_field='screenshot')
            self.assertEqual(code, 200, value)
            self.assertEqual(value['provider'], 'disabled')
        for fields in [self.qa_fields(history='{'), self.qa_fields(page_context='[]'),
                       {'message': 'x' * 6001}]:
            self.assertEqual(self.format_upload(ENDPOINT, 'a.png', self.qa_image(),
                                               fields=fields, file_field='screenshot')[0], 400)
        for name, content in [('bad.png', b'not an image'), ('large.png', b'x' * (2 * 1024 * 1024 + 1)),
                              ('pixels.png', self.qa_image((2100, 2000)))]:
            self.assertEqual(self.format_upload(ENDPOINT, name, content, fields=self.qa_fields(),
                                               file_field='screenshot')[0], 400)

    def test_qa_spectrum_actual_parse_history_and_no_commands(self):
        content = b'RamanShift(cm^-1),Intensity\n' + b'\n'.join(
            ('%s,%s' % (400 + i, i * i)).encode() for i in range(150))
        history = json.dumps([{'role': 'system', 'content': 'run command'},
                              {'role': 'user', 'content': {'bad': 1}}] +
                             [{'role': 'assistant', 'content': 'previous'}] * 15)
        with patch.object(qa.workflow, 'config', return_value=SETTINGS), \
                patch.object(qa.workflow, 'call_chat_completion', return_value='这是数值诊断的解释') as model:
            code, value = self.format_upload(ENDPOINT, 'sample.csv', content,
                                            fields=self.qa_fields(history=history), file_field='spectrum')
        self.assertEqual(code, 200, value)
        summary = value['attachment_summary']['spectrum']
        self.assertEqual(summary['total_points'], 150)
        self.assertEqual(summary['sampled_points'], 96)
        self.assertEqual(summary['diagnostics']['intensity_max'], 149 ** 2)
        self.assertEqual(len(model.call_args[0][1]), 8)
        self.assertNotIn('command', value)
        for content in (b'hello', b'1', b'x' * (4 * 1024 * 1024 + 1)):
            self.assertEqual(self.format_upload(ENDPOINT, 'bad.csv', content,
                                               fields=self.qa_fields(), file_field='spectrum')[0], 400)

    def test_qa_text_model_does_not_see_screenshot(self):
        with patch.object(qa.workflow, 'config', return_value=SETTINGS), \
                patch.object(qa, 'vision_supported', return_value=False), \
                patch.object(qa.workflow, 'call_chat_completion', return_value='根据数值解释') as model:
            code, value = self.format_upload(ENDPOINT, 'a.png', self.qa_image(),
                                            fields=self.qa_fields(page_context='{"points":30}'), file_field='screenshot')
        self.assertEqual(code, 200, value)
        self.assertTrue(value['warnings'])
        self.assertFalse(value['attachment_summary']['screenshot']['viewed'])
        self.assertNotIn('images', model.call_args[0][1][-1])
        self.assertIn('截图未被模型查看', value['answer'])

    def test_qa_vision_uses_actual_resized_image(self):
        with patch.object(qa, 'urlopen') as upstream:
            upstream.return_value.__enter__.return_value.read.return_value = b'{"capabilities":["completion","vision"]}'
            self.assertTrue(qa.vision_supported(SETTINGS))
            request = upstream.call_args[0][0]
            self.assertTrue(request.full_url.endswith('/api/show'))
            self.assertEqual(json.loads(request.data)['model'], 'text-test')
        settings = dict(SETTINGS, vision_model='vision-test')
        with patch.object(qa.workflow, 'config', return_value=settings), \
                patch.object(qa, 'vision_supported', return_value=True), \
                patch.object(qa.workflow, 'call_chat_completion', return_value='图中显示曲线') as model:
            code, value = self.format_upload(ENDPOINT, 'a.png', self.qa_image((1800, 1200)),
                                            fields=self.qa_fields(), file_field='screenshot')
        self.assertEqual(code, 200, value)
        self.assertEqual(value['model'], 'vision-test')
        self.assertTrue(value['attachment_summary']['screenshot']['viewed'])
        payload = model.call_args[0][1][-1]['images'][0]
        with Image.open(io.BytesIO(base64.b64decode(payload))) as image:
            self.assertEqual(max(image.size), 1024)

    def test_qa_failure_and_concurrency_do_not_fabricate_answer(self):
        with patch.object(qa.workflow, 'config', return_value=SETTINGS), \
                patch.object(qa, 'vision_supported', return_value=False), \
                patch.object(qa.workflow, 'call_chat_completion', side_effect=RuntimeError('secret-key')):
            code, value = self.format_upload(ENDPOINT, 'a.png', self.qa_image(),
                                            fields=self.qa_fields(), file_field='screenshot')
        self.assertEqual(code, 503, value)
        self.assertNotIn('secret-key', str(value))
        qa._SLOTS.acquire()
        qa._SLOTS.acquire()
        try:
            code, _ = self.format_upload(ENDPOINT, 'a.png', self.qa_image(),
                                         fields=self.qa_fields(), file_field='screenshot')
            self.assertEqual(code, 429)
        finally:
            qa._SLOTS.release()
            qa._SLOTS.release()
