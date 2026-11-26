"""Authorization tests use the workflow suite's temporary database, never live data."""
import uuid
import app as backend


class CollaborationCases:
    def test_login_dates_follow_successful_session_creation(self):
        username = 'login_test_' + uuid.uuid4().hex[:10]
        password = 'test-password'
        code, registration = self.request('/api/auth/register', dict(username=username, password=password))
        self.assertEqual(code, 200, registration)
        auth = registration['data']
        user_id = auth['user']['id']
        with backend.db_connect() as conn:
            original_session = conn.execute('SELECT created_at FROM sessions WHERE user_id=?', (user_id,)).fetchone()['created_at']
            self.assertEqual(auth['user']['last_login'], original_session)
            conn.execute('UPDATE users SET last_login=NULL WHERE id=?', (user_id,))

        backend.init_auth_db()
        self.assertEqual(self.request('/api/auth/me', token=auth['token'])[1]['data']['user']['last_login'], original_session)
        self.assertEqual(self.request('/api/auth/login', dict(identifier=username, password='wrong-password'))[0], 401)
        self.assertEqual(self.request('/api/auth/me', token=auth['token'])[1]['data']['user']['last_login'], original_session)

        code, login = self.request('/api/auth/login', dict(identifier=username, password=password))
        self.assertEqual(code, 200, login)
        last_login = login['data']['user']['last_login']
        self.assertGreater(last_login, original_session)
        self.assertEqual(self.request('/api/auth/me', token=auth['token'])[1]['data']['user']['last_login'], last_login)

    def project(self):
        code, result = self.call('/api/projects', dict(name='Collaboration test'))
        self.assertEqual(code, 200, result)
        return result['data']['project']['id']

    def invite_other(self, pid, role='member'):
        code, invitation = self.call(f'/api/projects/{pid}/invitations', dict(username=self.other['user']['username'], role=role))
        self.assertEqual(code, 200, invitation)
        return invitation['id']

    def join(self, pid, role='member'):
        iid = self.invite_other(pid, role)
        self.assertEqual(self.request(f'/api/project-invitations/{iid}/respond', dict(decision='accept'), token=self.other['token'])[0], 200)

    def collab_run(self, pid, token=None):
        code, result = self.request('/api/process', dict(wavenumber=list(range(40)), intensity=[i * i for i in range(40)],
            steps=[], save_history=True, project_id=pid, source_name='shared.csv'), token=token or self.auth['token'])
        self.assertEqual(code, 200, result)
        return result['data']['analysis_run']['id']

    def test_collaboration_invitation_acceptance_and_scoped_roles(self):
        pid = self.project()
        iid = self.invite_other(pid)
        self.assertEqual(self.request(f'/api/projects/{pid}', token=self.other['token'])[0], 404)
        self.assertEqual(self.call(f'/api/project-invitations/{iid}/respond', dict(decision='accept'))[0], 404)
        self.assertEqual(self.request(f'/api/project-invitations/{iid}/respond', dict(decision='accept'), token=self.other['token'])[0], 200)
        self.assertEqual(self.request(f'/api/project-invitations/{iid}/respond', dict(decision='accept'), token=self.other['token'])[0], 409)
        self.assertEqual(self.request(f'/api/projects/{pid}', token=self.other['token'])[1]['data']['project']['my_role'], 'member')
        self.assertEqual(self.request(f'/api/projects/{pid}', dict(name='Forbidden'), method='PATCH', token=self.other['token'])[0], 403)
        uid = self.other['user']['id']
        self.assertEqual(self.call(f'/api/projects/{pid}/members/{uid}', dict(role='admin'), method='PATCH')[0], 200)
        self.assertEqual(self.request(f'/api/projects/{pid}', dict(name='Team changed'), method='PATCH', token=self.other['token'])[0], 200)
        self.assertEqual(self.request('/api/users', token=self.other['token'])[0], 403)
        self.assertEqual(self.request(f'/api/projects/{pid}', method='DELETE', token=self.other['token'])[0], 403)

    def test_collaboration_expired_revoked_and_declined_invitations(self):
        pid = self.project()
        iid = self.invite_other(pid)
        self.assertEqual(self.call(f'/api/projects/{pid}/invitations/{iid}', method='DELETE')[0], 200)
        self.assertEqual(self.request(f'/api/project-invitations/{iid}/respond', dict(decision='accept'), token=self.other['token'])[0], 409)
        iid = self.invite_other(pid)
        with backend.db_connect() as conn:
            conn.execute('UPDATE project_invitations SET expires_at=? WHERE id=?', ('2000-01-01T00:00:00+00:00', iid))
        self.assertEqual(self.request(f'/api/project-invitations/{iid}/respond', dict(decision='accept'), token=self.other['token'])[0], 409)
        iid = self.invite_other(pid)
        self.assertEqual(self.request(f'/api/project-invitations/{iid}/respond', dict(decision='decline'), token=self.other['token'])[0], 200)
        self.assertEqual(self.request(f'/api/projects/{pid}', token=self.other['token'])[0], 404)

    def test_collaboration_private_tasks_published_results_and_revocation(self):
        pid = self.project()
        self.join(pid)
        rid = self.collab_run(pid)
        base = f'/api/analysis-runs/{rid}'
        self.assertEqual(self.request(base, token=self.other['token'])[0], 404)
        self.assertEqual(self.call(base + '/publish', {})[0], 200)
        self.assertEqual(self.request(base, token=self.other['token'])[0], 200)
        self.assertEqual(self.request(base + '/download', token=self.other['token'])[0], 200)
        self.assertEqual(self.request(base, method='DELETE', token=self.other['token'])[0], 403)
        self.assertEqual(self.call(base, method='DELETE')[0], 409)
        code, task = self.format_upload('/api/ai-workflows/upload', 'personal.csv', self.spectrum_bytes(), dict(project_id=pid))
        self.assertEqual(code, 200, task)
        self.assertEqual(self.request(f"/api/ai-workflows/{task['id']}", token=self.other['token'])[0], 404)
        other_run = self.collab_run(pid, self.other['token'])
        uid = self.other['user']['id']
        self.assertEqual(self.call(f'/api/projects/{pid}/members/{uid}', method='DELETE')[0], 200)
        for path in [f'/api/projects/{pid}', base, base + '/download', f'/api/analysis-runs/{other_run}']:
            self.assertEqual(self.request(path, token=self.other['token'])[0], 404)
        self.assertNotIn(other_run, [r['id'] for r in self.request('/api/analysis-runs', token=self.other['token'])[1]['data']['runs']])
        self.assertEqual(self.call(f'/api/projects/{pid}/collaboration')[1]['results'][0]['id'], rid)

    def test_collaboration_owner_transfer_preserves_project_and_contributions(self):
        pid = self.project()
        self.join(pid)
        own = self.auth['user']['id']
        self.assertEqual(self.call(f'/api/projects/{pid}/members/{own}', method='DELETE')[0], 409)
        self.assertEqual(self.call(f'/api/projects/{pid}/members/{own}', dict(role='member'), method='PATCH')[0], 409)
        uid = self.other['user']['id']
        self.assertEqual(self.call(f'/api/projects/{pid}/transfer', dict(user_id=uid))[0], 200)
        data = self.request(f'/api/projects/{pid}/collaboration', token=self.other['token'])[1]
        self.assertEqual(data['owner_id'], uid)
        self.assertEqual(self.call(f'/api/projects/{pid}/transfer', dict(user_id=own))[0], 403)
        self.assertEqual(self.call(f'/api/projects/{pid}/members/{own}', method='DELETE')[0], 200)
        self.assertEqual(self.call(f'/api/projects/{pid}')[0], 404)

    def test_collaboration_platform_admin_has_no_project_or_task_bypass(self):
        username = 'admin_test_' + uuid.uuid4().hex[:10]
        self.assertEqual(self.request('/api/auth/register', dict(username=username, password='test-password', role='admin'))[0], 403)
        admin = self.request('/api/auth/register', dict(username=username, password='test-password'))[1]['data']
        with backend.db_connect() as conn:
            conn.execute("UPDATE users SET role='admin' WHERE id=?", (admin['user']['id'],))
        self.assertEqual(self.request('/api/users', token=admin['token'])[0], 200)
        pid = self.project()
        rid = self.collab_run(pid)
        task = self.task()
        for path in [f'/api/projects/{pid}', f'/api/analysis-runs/{rid}', f"/api/ai-workflows/{task['id']}"]:
            self.assertEqual(self.request(path, token=admin['token'])[0], 404)
        projects = self.request('/api/projects', token=admin['token'])[1]['data']['projects']
        self.assertNotIn(pid, [p['id'] for p in projects])

    def test_collaboration_shared_data_independent_work_and_referenced_delete_guard(self):
        pid = self.project()
        self.join(pid)
        code, uploaded = self.format_upload(f'/api/projects/{pid}/datasets/upload', 'shared.csv', self.spectrum_bytes(), file_field='files')
        self.assertEqual(code, 200, uploaded)
        asset = uploaded['data']['datasets'][0]['id']
        self.assertEqual(self.request(f'/api/datasets/{asset}/download', token=self.other['token'])[0], 200)
        self.assertEqual(self.request(f'/api/datasets/{asset}', dict(display_name='No'), method='PATCH', token=self.other['token'])[0], 403)
        self.assertEqual(self.request(f'/api/datasets/{asset}', method='DELETE', token=self.other['token'])[0], 403)
        code, task = self.request('/api/ai-workflows/source', dict(dataset_id=asset), token=self.other['token'])
        self.assertEqual(code, 200, task)
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}")[0], 404)
        self.assertEqual(self.call(f'/api/projects/{pid}/members/{self.other["user"]["id"]}', method='DELETE')[0], 200)
        self.assertEqual(self.request(f"/api/ai-workflows/{task['id']}", token=self.other['token'])[0], 404)
        self.assertEqual(self.call(f'/api/datasets/{asset}/download')[0], 200)
        self.assertEqual(self.call(f'/api/datasets/{asset}', method='DELETE')[0], 409)

    def test_collaboration_cached_hyperspectral_data_requires_owner_and_active_membership(self):
        import numpy as np
        pid = self.project()
        self.join(pid)
        with backend.db_connect() as conn:
            other = backend.row_to_user(conn.execute('SELECT * FROM users WHERE id=?', (self.other['user']['id'],)).fetchone())
        cached = backend.register_dataset(np.arange(8), np.ones((3, 3, 8)), 'imaging', 'private.mat', other, pid)
        endpoint = f'/api/hyperspectral-pixel/{cached}'
        self.assertEqual(self.request(endpoint)[0], 404)
        self.assertEqual(self.call(endpoint)[0], 404)
        self.assertEqual(self.request(endpoint, token=self.other['token'])[0], 200)
        self.assertEqual(self.call(f'/api/projects/{pid}/members/{other["id"]}', method='DELETE')[0], 200)
        self.assertEqual(self.request(endpoint, token=self.other['token'])[0], 404)
        self.assertEqual(self.request('/api/download', dict(dataset_id=cached, wavenumber=list(range(8)), format='mat'), token=self.other['token'])[0], 404)
