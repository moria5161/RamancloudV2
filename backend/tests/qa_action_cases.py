"""Isolated HTTP/numeric coverage for closed AI action adapters."""
import copy
import io
import json
import time
import threading
import zipfile
from unittest.mock import patch
from urllib.parse import urlencode
import qa_actions
import qa_assistant
from qa_preprocess_intent import interpret_preprocessing
import ssnet
import structure_generation as sg
import structure_profiles
from test_wxd_single import wxd_fixture

PIPE=[dict(type='denoise',method='sg',params=dict(window_size=5,order=2),enabled=True,reason='温和降噪')]


class QaActionCases:
    def test_clear_conversation_discards_only_the_owners_unrun_drafts(self):
        route = '/api/qa-assistant/plans'
        self.assertEqual(self.request(route+'/drafts', method='DELETE')[0], 401)
        draft = self.action_plan([dict(action='preprocess', params=dict(steps=PIPE))])
        completed = self.action_plan([dict(action='preprocess', params=dict(steps=PIPE))])
        self.run_action(completed)
        self.assertEqual(self.wait_action(completed)['status'], 'completed')

        code, other_source = self.request('/api/ai-workflows/source', dict(demo='tutorial'), token=self.other['token'])
        self.assertEqual(code, 200, other_source)
        payload = dict(module='ai-analysis', goal='仅降噪', history=[], allow_ai=True, context_key='other',
                       inputs=dict(source=dict(workflow_id=other_source['id'])))
        with patch.object(qa_actions, 'generate_plan', return_value=dict(steps=[dict(action='preprocess', params=dict(steps=PIPE))])):
            code, other_draft = self.request(route, token=self.other['token'],
                raw=urlencode(dict(payload=json.dumps(payload))).encode(), content_type='application/x-www-form-urlencoded')
        self.assertEqual(code, 200, other_draft)

        code, result = self.call(route+'/drafts', method='DELETE')
        self.assertEqual(code, 200, result)
        self.assertGreaterEqual(result['discarded'], 1)
        remaining = {plan['id']: plan['status'] for plan in self.call(route)[1]}
        self.assertNotIn(draft['id'], remaining)
        self.assertEqual(remaining[completed['id']], 'completed')
        self.assertEqual(self.run_action(draft)['status'], 'discarded')
        self.assertEqual(self.request(route+'/'+other_draft['id'], token=self.other['token'])[1]['status'], 'draft')
        self.assertEqual(self.call(route+'/drafts', method='DELETE')[1]['discarded'], 0)

    def test_clear_conversation_blocks_a_draft_that_finishes_generating_after_clear(self):
        route = '/api/qa-assistant/plans'
        task = self.task()
        payload = dict(module='ai-analysis', goal='仅降噪', history=[], allow_ai=True, context_key='clear-race',
                       inputs=dict(source=dict(workflow_id=task['id'])))
        entered, resume = threading.Event(), threading.Event()
        results = []

        def delayed_plan(*args):
            entered.set()
            if not resume.wait(8):
                raise RuntimeError('test did not release plan construction')
            return dict(steps=[dict(action='preprocess', params=dict(steps=PIPE))])

        def request_plan():
            results.append(self.call(route, raw=urlencode(dict(payload=json.dumps(payload))).encode(),
                                     content_type='application/x-www-form-urlencoded'))

        with patch.object(qa_actions, 'generate_plan', side_effect=delayed_plan):
            worker = threading.Thread(target=request_plan, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.call(route+'/drafts', method='DELETE')[0], 200)
            finally:
                resume.set()
                worker.join(10)
        self.assertEqual(results[0][0], 409, results[0])
        self.assertNotIn('clear-race', [plan['context_key'] for plan in self.call(route)[1]])
        self.assertEqual(self.action_plan([dict(action='preprocess', params=dict(steps=PIPE))])['status'], 'draft')

    def preprocessing_turn(self, goal, task=None, model=None, *, history=None, region=None, parent=None, file=None,
                           filename='direct-spectrum.txt', mode='custom', consent=True, displayed=None):
        inputs = dict(source=dict(workflow_id=task['id']), settings=dict(region=region, steps=displayed or [])) if task else {}
        payload = dict(module='ai-analysis', mode=mode, goal=goal, history=history or [], allow_ai=consent,
                       context_key='test-direct-key', inputs=inputs, parent_plan_id=parent)
        route = '/api/qa-assistant/preprocessing-turn'
        with patch.object(qa_actions.workflow, 'call_chat_completion', return_value=json.dumps(model or {}, ensure_ascii=False)):
            if file:
                return self.format_upload(route, filename, file,
                                          fields=dict(payload=json.dumps(payload)), file_field='spectrum')
            return self.call(route, raw=urlencode(dict(payload=json.dumps(payload))).encode(),
                             content_type='application/x-www-form-urlencoded')

    def test_streamed_preprocessing_keeps_its_uploaded_spectrum_open(self):
        payload = dict(module='ai-analysis', mode='custom', goal='使用 Savitzky-Golay 降噪', allow_ai=True,
                       context_key='stream-attachment', inputs={})
        code, body = self.format_upload('/api/qa-assistant/preprocessing-turn?stream=true', 'stream-spectrum.txt',
                                        self.spectrum_bytes(), fields=dict(payload=json.dumps(payload)), file_field='spectrum')
        self.assertEqual(code, 200)
        event = json.loads(body.decode().splitlines()[-1])
        self.assertEqual(event['type'], 'result', event)
        self.assertEqual(event['data']['kind'], 'plan', event)

    def test_streamed_hyperspectral_processing_reports_running_and_returns_result(self):
        wave = list(range(400, 432))
        payload = dict(wavenumber=wave, spectra=[wave, wave], shape=[2, len(wave)], mode='series', steps=[])
        code, body = self.call('/api/process-hyperspectral?stream=true', payload)
        self.assertEqual(code, 200)
        events = [json.loads(line) for line in body.decode().splitlines()]
        self.assertIn(dict(type='running'), events)
        self.assertFalse(any(item['type'] == 'queued' for item in events))
        self.assertEqual(events[-1]['type'], 'result', events)
        self.assertEqual(events[-1]['data']['code'], 0)

    def test_direct_turn_recognizes_attachment_reference_and_executes_all_after_confirmation(self):
        tasks_before = self.call('/api/ai-workflows')[1]
        model = dict(kind='plan', changes=[dict(type='despike')])
        legacy = qa_actions.workflow.legacy_algorithms
        availability = legacy.availability

        def without_weights(spec):
            if spec['method'] in ('f2p', 'airnet'):
                return False, '测试环境缺少权重'
            return availability(spec)

        with patch.object(legacy, 'availability', side_effect=without_weights):
            code, result = self.preprocessing_turn('对他去鬼峰、去噪、基线矫正', model=model, file=self.spectrum_bytes())
        self.assertEqual(code, 200, result)
        plan = result['plan']
        self.assertEqual(plan['status'], 'draft')
        self.assertEqual(plan['title'], '去鬼峰 → 降噪 → 基线校正')
        self.assertEqual(self.call('/api/ai-workflows')[1], tasks_before)
        steps = plan['steps'][0]['params']['steps']
        self.assertEqual([s['method'] for s in steps], ['despike', 'sg', 'airpls'])
        self.run_action(plan)
        result = self.wait_action(plan)
        self.assertEqual(result['status'], 'completed', result)
        trace = result['progress']['steps'][0]['result_summary']['processing_steps']
        self.assertEqual(trace, [dict(id=s['id'], status='done') for s in steps])

    def test_direct_turn_covers_every_step_combination_and_exclusions_without_model(self):
        cases = [
            ('请对它做去鬼峰、去噪和基线校正', 'plan', ['despike', 'denoise', 'baseline']),
            ('可以帮我把这条谱的尖刺去掉、平滑一下，再扣掉慢变背景吗？', 'plan', ['despike', 'denoise', 'baseline']),
            ('附件里的谱，先做去噪再校正基线，主要峰要保留', 'plan', ['denoise', 'baseline']),
            ('麻烦把数据降下噪，最后做背景扣除', 'plan', ['denoise', 'baseline']),
            ('Could you remove the spikes, reduce the noise and subtract the background?', 'plan', ['despike', 'denoise', 'baseline']),
            ('Denoise this spectrum but leave the baseline unchanged.', 'plan', ['denoise']),
            ('不要去鬼峰和降噪，只校正基线', 'plan', ['baseline']),
            ('去尖刺，别动基线，也别降噪', 'plan', ['despike']),
            ('不做基线校正，只去鬼峰并去噪', 'plan', ['despike', 'denoise']),
            ('只去鬼峰和校正基线', 'plan', ['despike', 'baseline']),
            ('背景校正，其他都不用处理', 'plan', ['baseline']),
            ('对附件不要降噪', 'clarification', []),
            ('先降噪，又不要降噪', 'clarification', []),
            ('好的', 'clarification', []),
        ]
        history = [dict(role='user', content='请去鬼峰、降噪并校正基线')]
        with patch.object(qa_actions.workflow, 'call_chat_completion') as model:
            for text, kind, types in cases:
                with self.subTest(text=text):
                    intent, _ = interpret_preprocessing(text, history, {})
                    self.assertEqual(intent.kind, kind)
                    self.assertEqual([s.type for s in intent.changes if s.enabled], types)
            model.assert_not_called()

    def test_direct_turn_protects_explicit_steps_in_mixed_semantic_requests(self):
        task = self.task()
        goal = '先去鬼峰，再减弱谱线里重复的短周期纹路；最后扣背景，不用裁剪'
        with patch.object(qa_actions.workflow.legacy_algorithms, 'availability', return_value=(True, '')):
            code, result = self.preprocessing_turn(goal, task, dict(kind='plan', changes=[
                dict(type='denoise', evidence='减弱谱线里重复的短周期纹路', method='wtd', params=dict(level=4)),
                dict(type='cut', evidence='不用裁剪', enabled=True),
            ]))
        self.assertEqual(code, 200, result)
        steps = result['plan']['steps'][0]['params']['steps']
        self.assertEqual([step['method'] for step in steps], ['despike', 'f2p', 'airnet'])
        code, response = self.preprocessing_turn(goal, task, dict(kind='clarification', changes=[]))
        self.assertEqual(code, 200, response)
        self.assertEqual(response['kind'], 'clarification')

    def test_direct_turn_prefers_model_algorithms_in_new_plans_and_honors_explicit_settings(self):
        task = self.task()
        displayed = PIPE + [dict(type='baseline', method='airpls', params=dict(lam=1000, diff_order=2))]
        with patch.object(qa_actions.workflow.legacy_algorithms, 'availability', return_value=(True, '')):
            code, result = self.preprocessing_turn('降噪和基线校正', task, displayed=displayed)
            self.assertEqual(code, 200, result)
            steps = result['plan']['steps'][0]['params']['steps']
            self.assertEqual([step['method'] for step in steps], ['f2p', 'airnet'])
            code, result = self.preprocessing_turn('降噪窗口调到9，校正基线', task, displayed=displayed)
            self.assertEqual(code, 200, result)
            steps = result['plan']['steps'][0]['params']['steps']
            self.assertEqual([step['method'] for step in steps], ['sg', 'airnet'])
            self.assertEqual(steps[0]['params']['window_size'], 9)

    def test_direct_turn_keeps_user_settings_and_only_changes_requested_steps(self):
        task = self.task()
        code, result = self.preprocessing_turn('用SG降噪，窗口取9，再用SNIP校正基线', task)
        self.assertEqual(code, 200, result)
        plan = result['plan']
        steps = plan['steps'][0]['params']['steps']
        self.assertEqual([step['method'] for step in steps], ['sg', 'snip'])
        self.assertEqual(steps[0]['params']['window_size'], 9)
        code, result = self.preprocessing_turn('先不做基线校正了，保留其余步骤', task, parent=plan['id'])
        self.assertEqual(code, 200, result)
        self.assertEqual(result['plan']['steps'][0]['params']['steps'], steps[:1])

    def test_direct_turn_uses_crop_range_in_request_or_as_clarification_reply(self):
        task = self.task()
        code, result = self.preprocessing_turn('先裁剪到800–1500 cm⁻¹再降噪', task)
        self.assertEqual(code, 200, result)
        steps = result['plan']['steps'][0]['params']['steps']
        self.assertEqual([step['type'] for step in steps], ['cut', 'denoise'])
        self.assertEqual(steps[0]['params'], dict(start=800, end=1500))
        code, response = self.preprocessing_turn('把光谱裁剪一下', task)
        self.assertEqual(code, 200, response)
        self.assertEqual(response['kind'], 'clarification')
        code, result = self.preprocessing_turn('800 到 1500', task, history=[
            dict(role='user', content='把光谱裁剪一下'), dict(role='assistant', content=response['answer'])])
        self.assertEqual(code, 200, result)
        self.assertEqual(result['plan']['steps'][0]['params']['steps'][0]['params'], steps[0]['params'])

    def test_direct_turn_needs_source_and_gives_preprocessing_clarification(self):
        code, response = self.preprocessing_turn('只降噪，别动基线', model=dict(kind='plan', changes=[dict(type='baseline')]))
        self.assertEqual(code, 200)
        self.assertEqual(response, dict(kind='clarification', answer='请先上传或选择要处理的光谱。'))
        with patch.object(qa_assistant, 'tokens') as reply:
            code, response = self.preprocessing_turn('好的', self.task())
        self.assertEqual(code, 200, response)
        self.assertEqual(response['kind'], 'clarification')
        reply.assert_not_called()

    def test_direct_turn_preset_is_fixed_and_independent_of_ai_consent(self):
        task = self.task()
        with patch.object(qa_actions.workflow, 'config') as config, patch.object(qa_actions.workflow.legacy_algorithms, 'availability',
                                                                                return_value=(True, '')):
            code, result = self.preprocessing_turn('一键预处理', task, mode='preset', consent=False,
                                                    region=dict(start=700, end=1450))
        self.assertEqual(code, 200, result)
        config.assert_not_called()
        self.assertEqual(result['plan']['status'], 'draft')
        steps = result['plan']['steps'][0]['params']['steps']
        self.assertEqual([step['method'] for step in steps], ['despike', 'f2p', 'airnet'])
        code, result = self.preprocessing_turn('只降噪', task, consent=False)
        self.assertEqual(code, 400, result)
        with patch.object(qa_actions.workflow.legacy_algorithms, 'availability', return_value=(False, '测试：缺少模型权重')):
            code, result = self.preprocessing_turn('一键预处理', task, mode='preset', consent=False)
        self.assertEqual(code, 200, result)
        self.assertEqual(result['kind'], 'clarification')
        self.assertIn('F2P', result['answer'])

    def test_direct_turn_preset_requires_confirmation_for_native_conversion(self):
        with patch.object(qa_actions.workflow.legacy_algorithms, 'availability', return_value=(True, '')):
            code, result = self.preprocessing_turn('一键预处理', mode='preset', consent=False,
                                                    file=wxd_fixture()[0], filename='measurement.wxd')
            self.assertEqual(code, 200, result)
            plan = result['plan']
            self.assertTrue(plan['needs_units'])
            code, response = self.call('/api/qa-assistant/plans/' + plan['id'] + '/execute',
                                       dict(revision=plan['revision'], context_key=plan['context_key']))
            self.assertEqual(code, 400, response)
            self.assertEqual(self.call('/api/qa-assistant/plans/' + plan['id'])[1]['status'], 'draft')

    def test_direct_turn_routes_free_form_and_revises_only_one_step(self):
        task = self.task()
        goal = '用SG把那些细小抖动压一压，再把缓慢起伏的底去掉'
        code, result = self.preprocessing_turn(goal, task, dict(kind='plan', changes=[
            dict(type='despike', evidence='细小抖动'), dict(type='denoise', evidence='细小抖动能压一压', params=dict(window_size=11)),
            dict(type='baseline', evidence='把缓慢起伏的底去掉')]),
                                              region=dict(start=400, end=1750))
        self.assertEqual(code, 200, result)
        plan = result['plan']; before = plan['steps'][0]['params']['steps']
        self.assertEqual([s['type'] for s in before], ['cut', 'denoise', 'baseline'])
        self.assertEqual(before[0]['params']['end'], 1750)
        self.assertEqual(before[1]['params']['window_size'], 7)
        code, result = self.preprocessing_turn('把刚才的降噪窗口改成 9，其他保留', task,
            dict(kind='revise', changes=[dict(type='denoise', params=dict(window_size=9), evidence='降噪窗口改成 9')]), parent=plan['id'], region=dict(start=400, end=1750))
        self.assertEqual(code, 200, result)
        after = result['plan']['steps'][0]['params']['steps']
        self.assertEqual(after[0], before[0]); self.assertEqual(after[2], before[2])
        self.assertEqual(after[1]['params']['window_size'], 9)
        self.assertEqual(self.call('/api/qa-assistant/plans/'+plan['id'])[1]['status'], 'superseded')

    def test_direct_turn_rejects_category_mismatch_and_asks_for_missing_cut_range(self):
        task = self.task()
        for message, changes, expected in [
            ('用SNIP降噪', [dict(type='denoise', method='sg', evidence='用SNIP降噪')], '不适用于这一步'),
            ('帮我裁剪这条光谱', [dict(type='cut', evidence='裁剪这条光谱')], '起止波数'),
        ]:
            code, result = self.preprocessing_turn(message, task, dict(kind='plan', changes=changes))
            self.assertEqual(code, 200, result)
            self.assertEqual(result['kind'], 'clarification')
            self.assertIn(expected, result['answer'])
        message = '只降噪，别动基线'
        code, result = self.preprocessing_turn(message, model=dict(kind='plan', changes=[dict(type='baseline')]), file=self.spectrum_bytes())
        self.assertEqual(code, 200, result)
        self.assertEqual([s['type'] for s in result['plan']['steps'][0]['params']['steps']], ['denoise'])

    def test_qa_action_retries_optional_quality_question_without_executing(self):
        task=self.task();goal='先去鬼峰，再降噪，最后扣除基线'
        data=dict(module='ai-analysis',goal=goal,history=[dict(role='user',content='是的')],allow_ai=True,context_key='discussion',inputs=dict(source=dict(workflow_id=task['id'])))
        draft=dict(title='预处理',summary='',clarification='',steps=[dict(action='preprocess',params=dict(steps=PIPE))])
        with patch.object(qa_actions.workflow,'config',return_value=dict(provider='ollama',model='fixture')),patch.object(qa_actions.workflow,'call_chat_completion',side_effect=[json.dumps(dict(clarification='是否需要每步质量检查？',steps=[])),json.dumps(draft)]) as model:
            code,value=self.request('/api/qa-assistant/plans',raw=urlencode(dict(payload=json.dumps(data))).encode(),token=self.auth['token'],content_type='application/x-www-form-urlencoded')
        self.assertEqual(code,200,value);self.assertEqual(value['status'],'draft');self.assertEqual(model.call_count,2)
        self.assertIn(goal,model.call_args[0][1][1]['content'])
        self.assertEqual(self.call('/api/ai-workflows/'+task['id'])[1]['versions'],[])
        with patch.object(qa_actions.workflow,'config',return_value=dict(provider='ollama',model='fixture')),patch.object(qa_actions.workflow,'call_chat_completion',return_value=json.dumps(dict(clarification='请指定目标物质。',steps=[]))) as model:
            code,value=self.request('/api/qa-assistant/plans',raw=urlencode(dict(payload=json.dumps(data))).encode(),token=self.auth['token'],content_type='application/x-www-form-urlencoded')
        self.assertEqual(code,200,value);self.assertIn('clarification',value);self.assertNotIn('id',value);self.assertEqual(model.call_count,2)

    def test_qa_action_valid_steps_are_not_hidden_by_optional_question(self):
        task=self.task()
        data=dict(module='ai-analysis',goal='温和降噪',history=[],allow_ai=True,context_key='discussion',inputs=dict(source=dict(workflow_id=task['id'])))
        draft=dict(title='降噪',summary='',clarification='是否每步检查质量？',steps=[dict(action='preprocess',params=dict(steps=PIPE))])
        with patch.object(qa_actions,'generate_plan',return_value=draft):
            code,value=self.request('/api/qa-assistant/plans',raw=urlencode(dict(payload=json.dumps(data))).encode(),token=self.auth['token'],content_type='application/x-www-form-urlencoded')
        self.assertEqual(code,200,value);self.assertEqual(value['status'],'draft');self.assertTrue(value['steps'])

    def test_qa_action_keeps_module_settings_when_plan_omits_them(self):
        task=self.structure_source()
        settings=dict(engine='agent',top_k=10,formula='C6H6',rerank=False)
        plan=self.action_plan([dict(action='structure_generate',params={})],
            inputs=dict(source=dict(workflow_id=task['id']),settings=settings),module='structure-generation')
        self.assertEqual(plan['steps'][0]['params'],settings)
        edited=self.action_plan([dict(action='structure_generate',params=dict(top_k=3,formula=''))],
            inputs=dict(source=dict(workflow_id=task['id']),settings=settings),module='structure-generation')
        self.assertEqual(edited['steps'][0]['params'],dict(settings,top_k=3,formula=''))
        train_settings=dict(mode='train',name='Selected standard',points=512,epochs=2,samples_per_epoch=64)
        trained=self.action_plan([dict(action='ssnet_train',params={})],
            inputs=dict(standards=[dict(workflow_id=task['id'])],settings=train_settings),module='spectral-unmixing')
        self.assertEqual({k:trained['steps'][0]['params'][k] for k in train_settings if k!='mode'},
            {k:v for k,v in train_settings.items() if k!='mode'})
        match=self.action_plan([dict(action='library_match',params={})],
            inputs=dict(source=dict(workflow_id=task['id']),settings=dict(top_k=7,preprocessing_mode='prepared')),module='library-matching')
        self.assertEqual(match['steps'][0]['params'],dict(top_k=7,preprocessing_mode='prepared'))

    def test_qa_action_matching_defaults_follow_baseline_correction(self):
        baseline=dict(type='baseline',method='airpls',params=dict(lam=1000,diff_order=2))
        for enabled in (False,True):
            plan=self.action_plan([dict(action='preprocess',params=dict(steps=PIPE+[dict(baseline,enabled=enabled)])),dict(action='library_match',params={})])
            self.assertEqual(plan['steps'][1]['params']['preprocessing_mode'],'prepared' if enabled else 'auto')
        explicit=self.action_plan([dict(action='preprocess',params=dict(steps=PIPE+[baseline])),dict(action='library_match',params=dict(preprocessing_mode='auto'))])
        self.assertEqual(explicit['steps'][1]['params']['preprocessing_mode'],'auto')

    def test_qa_action_train_predict_confirms_both_axes(self):
        task=self.task()
        inputs=dict(source=dict(workflow_id=task['id']),standards=[dict(workflow_id=task['id'])],unit_confirmed=True,
            settings=dict(mode='train',name='Target',standard_unit_confirmed=True,mixture_unit_confirmed=False))
        plan=self.action_plan([dict(action='ssnet_train',params={}),dict(action='ssnet_predict',params={})],inputs=inputs,module='spectral-unmixing')
        self.assertTrue(plan['needs_units'])
        self.assertEqual(self.call('/api/qa-assistant/plans/'+plan['id']+'/execute',dict(revision=1,context_key='fixture-key'))[0],400)

    def action_plan(self,steps,inputs=None,module='ai-analysis',task=None):
        if inputs is None:
            task=task or self.task();inputs=dict(source=dict(workflow_id=task['id']))
        data=dict(module=module,goal='处理当前光谱并分析结果：'+ '、'.join(qa_actions.LABELS.get(s['action'],s['action']) for s in steps),history=[],allow_ai=True,context_key='fixture-key',inputs=inputs)
        draft=dict(title='测试方案',summary='检查后运行',steps=copy.deepcopy(steps))
        with patch.object(qa_actions,'generate_plan',return_value=draft):
            code,value=self.request('/api/qa-assistant/plans',raw=urlencode(dict(payload=json.dumps(data))).encode(),token=self.auth['token'],content_type='application/x-www-form-urlencoded')
        self.assertEqual(code,200,value);return value

    def run_action(self,plan,**extra):
        code,value=self.call('/api/qa-assistant/plans/'+plan['id']+'/execute',dict(revision=plan['revision'],context_key=plan['context_key'],**extra))
        self.assertEqual(code,200,value);return value

    def wait_action(self,plan):
        for _ in range(600):
            code,value=self.call('/api/qa-assistant/plans/'+plan['id']);self.assertEqual(code,200,value)
            if value['status'] not in ('queued','running','stopping'):return value
            time.sleep(.04)
        self.fail('Action run timed out')

    def test_qa_action_single_edit_idempotence_export(self):
        task=self.task()
        plan=self.action_plan([dict(action='preprocess',params=dict(steps=PIPE)),dict(action='export',params=dict(format='txt',processed=True,original=True))],task=task)
        self.assertEqual(self.call('/api/ai-workflows/'+task['id'])[1]['versions'],[])
        route='/api/qa-assistant/plans/'+plan['id']
        self.assertEqual(self.request(route,token=self.other['token'])[0],404)
        self.assertEqual(self.call(route+'/execute',dict(revision=1,context_key='changed'))[0],409)
        steps=copy.deepcopy(plan['steps']);steps[0]['params']['steps'][0]['params']['window_size']=7
        code,plan=self.call(route,dict(revision=1,steps=[{k:v for k,v in s.items() if k in ('action','params')} for s in steps]),method='PUT')
        self.assertEqual(code,200,plan);self.assertEqual(plan['revision'],2)
        self.run_action(plan);self.run_action(plan);done=self.wait_action(plan)
        self.assertEqual(done['status'],'completed',done)
        self.assertEqual(len(self.call('/api/ai-workflows/'+task['id'])[1]['versions']),1)
        self.assertNotIn('_artifact_path',json.dumps(done))
        code,content=self.call(route+'/artifacts/1');self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:self.assertEqual(len(archive.namelist()),2)
        self.assertEqual(self.request(route+'/artifacts/1',token=self.other['token'])[0],404)
        with patch.object(qa_assistant.workflow,'call_chat_completion',return_value='已完成降噪和导出。') as model:
            code,reply=self.format_upload('/api/qa-assistant/reply','spectrum.csv',self.spectrum_bytes(),fields=dict(message='刚才的方案进展如何？',allow_ai='true',action_plan_id=plan['id']),file_field='spectrum')
        self.assertEqual(code,200,reply)
        self.assertIn('execution',[s['id'] for s in reply['sources']])
        self.assertIn('action_plan',model.call_args[0][1][-1]['content'])
        self.assertNotIn('_artifact_path',model.call_args[0][1][-1]['content'])

    def test_qa_action_cross_module_and_failure_stops_pipeline(self):
        task=self.task();steps=[dict(action='preprocess',params=dict(steps=PIPE)),dict(action='library_match',params=dict(top_k=3,preprocessing_mode='prepared'))]
        plan=self.action_plan(steps,task=task)
        self.assertTrue(plan['needs_units'])
        self.assertEqual(self.call('/api/qa-assistant/plans/'+plan['id']+'/execute',dict(revision=1,context_key='fixture-key'))[0],400)
        with self.library_runtime():
            self.run_action(plan,confirm_units=True);done=self.wait_action(plan)
        self.assertEqual(done['status'],'completed',done)
        job=self.call('/api/library-matching/jobs/'+done['progress']['steps'][1]['job_id'])[1]
        self.assertEqual(job['input']['source']['reference']['workflow_id'],task['id'])
        failed=self.action_plan(steps+[dict(action='export',params=dict(format='bundle'))],task=task)
        with self.library_runtime(fail=True):
            self.run_action(failed,confirm_units=True);done=self.wait_action(failed)
        self.assertEqual(done['status'],'failed',done)
        self.assertEqual(len(done['progress']['steps']),2)
        self.assertEqual(done['progress']['steps'][0]['status'],'completed')

    def test_qa_action_structure_and_module_source(self):
        task=self.structure_source()
        fixture=dict(duration_seconds=.01,inference_performed=True,candidates=[dict(id='1',rank=1,smiles='C',formula='CH4',matching_score=.2,generation_score=-1,sdf='',image_png='')])
        plan=self.action_plan([dict(action='structure_generate',params=dict(top_k=3))],task=task,module='structure-generation')
        with patch.object(structure_profiles,'public_configuration',return_value={'ready':True}), \
                patch.object(sg,'public_configuration',return_value={'ready':True}), \
                patch.object(sg.RUNTIME,'infer',return_value=fixture):
            self.run_action(plan,confirm_units=True);done=self.wait_action(plan)
        self.assertEqual(done['status'],'completed',done)
        source,_=self.module_input('library-matching')
        plan=self.action_plan([dict(action='library_match',params=dict(top_k=5))],inputs=dict(source=dict(source_id=source['id'],module='library-matching'),unit_confirmed=True),module='library-matching')
        with self.library_runtime():self.run_action(plan);done=self.wait_action(plan)
        self.assertEqual(done['status'],'completed',done)

    def test_qa_action_hyperspectral_tshi(self):
        code,value=self.upload_tshi();self.assertEqual(code,200,value);dataset=value['data']
        steps=[dict(type='denoise',method='tshi',params=dict(center_wavenumber=dataset['wavenumber'][7],half_width=4,windowsize=3,count=1,bm3d_enabled=False))]
        plan=self.action_plan([dict(action='hyperspectral',params=dict(steps=steps))],inputs=dict(dataset_id=dataset['dataset_id']),module='hyperspectral')
        self.run_action(plan);done=self.wait_action(plan);self.assertEqual(done['status'],'completed',done)
        rid=done['progress']['steps'][0]['run_ids'][0]
        self.assertEqual(self.call('/api/analysis-runs/'+rid)[1]['data']['run']['analysis_type'],'hyperspectral')

    def test_qa_action_train_and_predict(self):
        task=self.task()
        plan=self.action_plan([dict(action='ssnet_train',params=dict(name='QA model',epochs=1,samples_per_epoch=32,rf_samples=32,trees=10,points=512)),dict(action='ssnet_predict',params={})],inputs=dict(source=dict(workflow_id=task['id']),standards=[dict(workflow_id=task['id'])]),module='spectral-unmixing')
        def worker(directory,request,update,cancelled):
            if request['kind']=='train':return dict(artifacts={'unet.pth':'hash','forest.joblib':'hash'},network_sha256='hash',loss_history=[.1],duration_seconds=.01)
            return dict(wavenumber=[131,2653],mixture=[1,2],extracted=[.2,.4],background=[.8,1.6],rf_score=.5,inference_performed=True,duration_seconds=.01)
        with patch.object(ssnet,'runtime_ready',return_value=True),patch.object(ssnet,'execute_local',side_effect=worker):
            self.run_action(plan,confirm_units=True);done=self.wait_action(plan)
        self.assertEqual(done['status'],'completed',done)

    def test_qa_action_batch_and_project_share(self):
        _,batch=self.batch_upload();ids=[item['workflow_id'] for item in batch['items']]
        plan=self.action_plan([dict(action='preprocess',params=dict(steps=PIPE))],inputs=dict(source=dict(workflow_id=ids[0]),batch_id=batch['id'],workflow_ids=ids))
        self.run_action(plan);done=self.wait_action(plan);self.assertEqual(done['status'],'completed',done)
        self.assertEqual(self.call('/api/ai-workflow-batches/'+batch['id'])[1]['counts']['completed'],len(ids))
        pid=self.project();task=self.task()
        plan=self.action_plan([dict(action='preprocess',params=dict(steps=PIPE)),dict(action='share',params={})],inputs=dict(source=dict(workflow_id=task['id']),project_id=pid))
        self.assertEqual(self.call('/api/qa-assistant/plans/'+plan['id']+'/execute',dict(revision=1,context_key='fixture-key'))[0],400)
        self.run_action(plan,confirm_sharing=True);done=self.wait_action(plan);self.assertEqual(done['status'],'completed',done)

    def test_qa_action_standardize_file(self):
        data=dict(module='extra-tools',goal='转换为标准双列文件',history=[],allow_ai=True,context_key='fixture-key',inputs={})
        draft=dict(title='转换',summary='标准双列',steps=[dict(action='standardize',params={})])
        with patch.object(qa_actions,'generate_plan',return_value=draft):
            code,plan=self.format_upload('/api/qa-assistant/plans','sample.csv',self.spectrum_bytes(),dict(payload=json.dumps(data)),file_field='files')
        self.assertEqual(code,200,plan);self.run_action(plan);done=self.wait_action(plan);self.assertEqual(done['status'],'completed',done)
        code,body=self.call('/api/qa-assistant/plans/'+plan['id']+'/artifacts/0');self.assertEqual(code,200)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(body)))

    def test_qa_action_forbidden_operations_and_stale_inputs(self):
        task=self.task();data=dict(module='ai-analysis',goal='校验当前方案',history=[],allow_ai=True,context_key='x',inputs=dict(source=dict(workflow_id=task['id'])))
        for draft in [dict(steps=[dict(action='exec',params=dict(code='print(1)'))]),dict(steps=[dict(action='preprocess',params=dict(steps=PIPE,source_id='other'))])]:
            with patch.object(qa_actions,'generate_plan',return_value=draft):
                code,_=self.request('/api/qa-assistant/plans',raw=urlencode(dict(payload=json.dumps(data))).encode(),token=self.auth['token'],content_type='application/x-www-form-urlencoded')
            self.assertEqual(code,400)
        plan=self.action_plan([dict(action='preprocess',params=dict(steps=PIPE))],task=task)
        self.assertEqual(self.request('/api/qa-assistant/plans/'+plan['id']+'/execute',dict(revision=1,context_key='fixture-key'),token=self.other['token'])[0],404)
        self.call('/api/ai-workflows/'+task['id'],method='DELETE')
        self.assertEqual(self.call('/api/qa-assistant/plans/'+plan['id']+'/execute',dict(revision=1,context_key='fixture-key'))[0],404)

    def test_qa_action_cancellation_stops_followups(self):
        task=self.task();pid=self.project();entered=threading.Event();release=threading.Event()
        import library_matching as lm
        plan=self.action_plan([dict(action='library_match',params={}),dict(action='share',params={})],inputs=dict(source=dict(workflow_id=task['id']),project_id=pid,unit_confirmed=True))
        with self.library_runtime():
            original=lm.infer
            def slow(*args):entered.set();release.wait(5);return original(*args)
            with patch.object(lm,'infer',side_effect=slow):
                self.run_action(plan,confirm_sharing=True)
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.call('/api/qa-assistant/plans/'+plan['id']+'/cancel',{})[0],200)
                release.set();done=self.wait_action(plan)
        self.assertEqual(done['status'],'cancelled',done)
        self.assertEqual(len(done['progress']['steps']),1)

    def test_qa_action_model_record_export_and_png(self):
        import library_matching as lm
        task=self.task()
        with self.library_runtime():
            job=self.call('/api/library-matching/jobs',dict(workflow_id=task['id'],unit_confirmed=True))[1]
            job=self.wait_match(job['id'])
        rid=job['analysis_run_id']
        plan=self.action_plan([dict(action='export',params=dict(format='bundle'))],inputs=dict(source=dict(run_id=rid),run_ids=[rid]),module='analysis-history')
        self.run_action(plan);done=self.wait_action(plan);self.assertEqual(done['status'],'completed',done)
        version=self.plan(task);self.call('/api/ai-workflows/'+task['id']+'/versions/'+version['id']+'/execute',{})
        completed=self.wait_version(task,version['id'])
        png=self.action_plan([dict(action='export',params=dict(format='png'))],inputs=dict(run_ids=[completed['analysis_run_id']]),module='analysis-history')
        self.run_action(png);done=self.wait_action(png);self.assertEqual(done['status'],'completed',done)
        body=self.call('/api/qa-assistant/plans/'+png['id']+'/artifacts/0')[1]
        with zipfile.ZipFile(io.BytesIO(body)) as archive:self.assertTrue(archive.read(archive.namelist()[0]).startswith(b'\x89PNG'))

    def test_qa_action_export_checked_unfinished_and_project_files(self):
        first=self.task();second=self.task()
        refs=[dict(workflow_id=t['id']) for t in (first,second)]
        plan=self.action_plan([dict(action='export',params=dict(format='txt',original=True,processed=False))],inputs=dict(export_refs=refs),module='analysis-history')
        self.assertEqual(plan['file_count'],2)
        self.run_action(plan);done=self.wait_action(plan);self.assertEqual(done['status'],'completed',done)
        body=self.call('/api/qa-assistant/plans/'+plan['id']+'/artifacts/0')[1]
        with zipfile.ZipFile(io.BytesIO(body)) as archive:self.assertEqual(len(archive.namelist()),2)
        pid=self.project()
        code,value=self.format_upload('/api/projects/'+pid+'/datasets/upload','original.csv',self.spectrum_bytes(),dict(data_kind='raw'),file_field='files')
        self.assertEqual(code,200,value)
        aid=value['data']['datasets'][0]['id']
        plan=self.action_plan([dict(action='export',params=dict(format='bundle',original=True,processed=False))],inputs=dict(project_id=pid,asset_ids=[aid]),module='projects')
        self.run_action(plan);done=self.wait_action(plan);self.assertEqual(done['status'],'completed',done)
