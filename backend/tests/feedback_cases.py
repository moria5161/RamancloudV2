"""Real HTTP feedback checks on the workflow suite's isolated database."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import app as backend


class FeedbackCases:
    def feedback_account(self, admin=False):
        code, result = self.request('/api/auth/register', dict(username='fb_' + uuid.uuid4().hex[:18], password='feedback-test-password'))
        self.assertEqual(code, 200, result)
        account = result['data']
        if admin:
            with backend.db_connect() as conn:
                conn.execute("UPDATE users SET role='admin' WHERE id=?", (account['user']['id'],))
        return account

    def feedback_payload(self, **overrides):
        return dict(request_id=str(uuid.uuid4()), category='bug', title='上传文件出现报错',
                    body='在智能处理上传实验文件后，出现了无法识别提示，请协助检查。', page_path='/tutorial', **overrides)

    def submit_feedback(self, account, payload=None):
        code, result = self.request('/api/feedback', payload or self.feedback_payload(), token=account['token'])
        self.assertEqual(code, 201, result)
        return result

    def test_feedback_authorization_private_records_and_spoofing(self):
        owner, other = self.feedback_account(), self.feedback_account()
        payload = self.feedback_payload()
        self.assertEqual(self.request('/api/feedback', payload)[0], 401)
        self.assertEqual(self.request('/api/feedback')[0], 401)
        item = self.submit_feedback(owner, payload)
        self.assertEqual(item['user_id'], owner['user']['id'])
        self.assertEqual(self.request('/api/feedback/' + item['id'], token=other['token'])[0], 404)
        self.assertEqual(self.request('/api/feedback?scope=all', token=other['token'])[0], 403)
        self.assertEqual(self.request('/api/feedback', token=other['token'])[1]['total'], 0)
        patch = dict(status='resolved', reply='无权处理', expected_updated_at=item['updated_at'])
        self.assertEqual(self.request('/api/feedback/' + item['id'], patch, method='PATCH', token=other['token'])[0], 403)
        self.assertEqual(self.request('/api/feedback', dict(payload, user_id=other['user']['id']), token=owner['token'])[0], 422)
        self.assertEqual(self.request('/api/feedback/' + item['id'], token=owner['token'])[1]['status'], 'new')

    def test_feedback_platform_admin_handles_feedback_without_submitting(self):
        owner, admin = self.feedback_account(), self.feedback_account(admin=True)
        self.assertEqual(self.request('/api/feedback', self.feedback_payload(), token=admin['token'])[0], 403)
        self.assertEqual(self.request('/api/feedback', token=admin['token'])[1]['total'], 0)
        item = self.submit_feedback(owner)
        self.assertEqual(self.request('/api/feedback/' + item['id'], token=admin['token'])[0], 200)
        code, updated = self.request('/api/feedback/' + item['id'], dict(status='resolved', reply='已处理这条用户反馈。', expected_updated_at=item['updated_at']), method='PATCH', token=admin['token'])
        self.assertEqual(code, 200, updated)
        self.assertEqual(self.request('/api/feedback/' + item['id'], token=owner['token'])[1]['reply'], updated['reply'])

    def test_feedback_persistent_plaintext_and_idempotent_retry(self):
        owner = self.feedback_account()
        payload = self.feedback_payload()
        payload.update(title='  SQL 与 HTML 原样记录  ', body='<script>alert("text")</script>\n含引号 \' 与 % 和 _ 的用户意见。')
        item = self.submit_feedback(owner, payload)
        self.assertEqual(item['title'], payload['title'].strip())
        self.assertEqual(item['body'], payload['body'])
        with backend.db_connect() as conn:
            stored = conn.execute('SELECT body FROM user_feedback WHERE id=?', (item['id'],)).fetchone()
        self.assertEqual(stored['body'], payload['body'])
        code, retry = self.request('/api/feedback', payload, token=owner['token'])
        self.assertEqual(code, 200)
        self.assertEqual(retry['id'], item['id'])
        self.assertEqual(self.request('/api/feedback', token=owner['token'])[1]['total'], 1)
        self.assertEqual(self.request('/api/feedback', dict(payload, body='同一提交编号下改变了原来的反馈正文。'), token=owner['token'])[0], 409)

    def test_feedback_concurrent_retries_create_one_record(self):
        owner, payload = self.feedback_account(), self.feedback_payload()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.request('/api/feedback', payload, token=owner['token']), range(4)))
        self.assertEqual(sorted(code for code, _ in responses), [200, 200, 200, 201])
        self.assertEqual(len({item['id'] for _, item in responses}), 1)

    def test_feedback_rate_limit_is_per_user_and_allows_retries(self):
        owner = self.feedback_account()
        payloads = [self.feedback_payload() for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda payload: self.request('/api/feedback', payload, token=owner['token']), payloads))
        self.assertEqual(sorted(code for code, _ in results), [201] * 5 + [429] * 3)
        index = next(i for i, (code, _) in enumerate(results) if code == 201)
        self.assertEqual(self.request('/api/feedback', payloads[index], token=owner['token'])[0], 200)
        self.submit_feedback(self.feedback_account())
        with backend.db_connect() as conn:
            conn.execute("UPDATE user_feedback SET created_at='2020-01-01T00:00:00+00:00' WHERE user_id=?", (owner['user']['id'],))
        self.submit_feedback(owner)

    def test_feedback_admin_reply_status_and_concurrent_update(self):
        owner, admin = self.feedback_account(), self.feedback_account(admin=True)
        item = self.submit_feedback(owner)
        payload = dict(status='in_progress', reply='已收到，正在核对这份仪器格式。', expected_updated_at=item['updated_at'])
        code, updated = self.request('/api/feedback/' + item['id'], payload, method='PATCH', token=admin['token'])
        self.assertEqual(code, 200, updated)
        self.assertEqual(updated['status'], 'in_progress')
        self.assertIsNotNone(updated['replied_at'])
        self.assertEqual(self.request('/api/feedback/' + item['id'], token=owner['token'])[1]['reply'], payload['reply'])
        self.assertEqual(self.request('/api/feedback/' + item['id'], dict(payload, reply='过时编辑不得覆盖'), method='PATCH', token=admin['token'])[0], 409)
        code, resolved = self.request('/api/feedback/' + item['id'], dict(status='resolved', expected_updated_at=updated['updated_at']), method='PATCH', token=admin['token'])
        self.assertEqual(code, 200, resolved)
        self.assertEqual(resolved['reply'], payload['reply'], 'Status-only updates preserve replies')
        self.assertEqual(self.request('/api/feedback/missing', dict(payload), method='PATCH', token=admin['token'])[0], 404)

    def test_feedback_pagination_filters_counts_and_minimal_list(self):
        owner, other, admin = self.feedback_account(), self.feedback_account(), self.feedback_account(admin=True)
        first = self.submit_feedback(owner)
        second_payload = self.feedback_payload()
        second_payload['category'] = 'suggestion'
        second = self.submit_feedback(owner, second_payload)
        self.submit_feedback(other)
        self.request('/api/feedback/' + first['id'], dict(status='resolved', expected_updated_at=first['updated_at']), method='PATCH', token=admin['token'])
        page = self.request('/api/feedback?page_size=1', token=owner['token'])[1]
        self.assertEqual(page['total'], 2)
        self.assertEqual(page['counts'], dict(new=1, in_progress=0, resolved=1))
        self.assertEqual(page['items'][0]['id'], second['id'])
        self.assertNotIn('body', page['items'][0])
        self.assertNotIn('request_id', page['items'][0])
        self.assertEqual(self.request('/api/feedback?page_size=1&page=2', token=owner['token'])[1]['items'][0]['id'], first['id'])
        filtered = self.request('/api/feedback?status=new&category=suggestion', token=owner['token'])[1]
        self.assertEqual([i['id'] for i in filtered['items']], [second['id']])
        all_feedback = self.request('/api/feedback?scope=all', token=admin['token'])[1]
        self.assertTrue({first['id'], second['id']} <= {i['id'] for i in all_feedback['items']} or all_feedback['total'] > 20)
        self.assertEqual(self.request('/api/feedback?page_size=51', token=owner['token'])[0], 422)
        self.assertEqual(self.request('/api/feedback?page=0', token=owner['token'])[0], 422)

    def test_feedback_input_validation_and_safe_source_links(self):
        owner = self.feedback_account()
        invalid = [('title', '  '), ('body', 'too short'), ('category', 'anything'),
                   ('title', 'x' * 121), ('body', 'x' * 5001), ('request_id', 'not-a-uuid')]
        for key, value in invalid:
            self.assertEqual(self.request('/api/feedback', dict(self.feedback_payload(), **{key: value}), token=owner['token'])[0], 422, key)
        for path in ['https://evil.example', '//evil.example', 'javascript:alert(1)', '/tutorial?token=private', '/unknown']:
            self.assertEqual(self.request('/api/feedback', dict(self.feedback_payload(), page_path=path), token=owner['token'])[0], 400)
        self.assertEqual(self.request('/api/feedback', dict(self.feedback_payload(), body='正文带空字符\x00需要被服务端明确拒绝。'), token=owner['token'])[0], 400)
        self.assertEqual(self.request('/api/feedback', dict(self.feedback_payload(), status='resolved'), token=owner['token'])[0], 422)

    def test_feedback_project_admin_and_revoked_platform_admin(self):
        owner, admin = self.feedback_account(), self.feedback_account(admin=True)
        item = self.submit_feedback(owner)
        code, project = self.request('/api/projects', dict(name='Feedback role check'), token=owner['token'])
        self.assertEqual(code, 200, project)
        self.assertEqual(self.request('/api/feedback?scope=all', token=owner['token'])[0], 403, 'Project ownership is not platform administration')
        with backend.db_connect() as conn:
            conn.execute("UPDATE users SET role='user' WHERE id=?", (admin['user']['id'],))
        patch = dict(status='resolved', expected_updated_at=item['updated_at'])
        self.assertEqual(self.request('/api/feedback/' + item['id'], patch, method='PATCH', token=admin['token'])[0], 403)
        self.assertEqual(self.request('/api/feedback/' + item['id'], token=admin['token'])[0], 404)
        with backend.db_connect() as conn:
            conn.execute('UPDATE users SET is_active=0 WHERE id=?', (owner['user']['id'],))
        self.assertEqual(self.request('/api/feedback', token=owner['token'])[0], 401)
