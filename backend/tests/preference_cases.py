"""Language preferences are private account data, not shared browser state."""


class PreferenceCases:
    def test_language_preferences_require_auth_and_reject_invalid_input(self):
        self.assertEqual(self.request('/api/account/preferences')[0], 401)
        self.assertEqual(self.request('/api/account/preferences', {'language': 'zh'}, method='PUT')[0], 401)
        for payload in ({'language': 'fr'}, {'language': 'ZH'}, {'language': 'zh', 'user_id': self.other['user']['id']}):
            self.assertEqual(self.call('/api/account/preferences', payload, method='PUT')[0], 422)

    def test_language_preferences_are_private_and_survive_new_login(self):
        account = self.feedback_account()
        token = account['token']
        self.assertEqual(self.request('/api/account/preferences', token=token)[1], {'language': None})
        self.assertEqual(self.request('/api/account/preferences', {'language': 'zh'}, token=token, method='PUT')[1], {'language': 'zh'})
        self.assertEqual(self.request('/api/account/preferences', token=self.other['token'])[1], {'language': None})
        code, logged_in = self.request('/api/auth/login', {'identifier': account['user']['username'], 'password': 'feedback-test-password'})
        self.assertEqual(code, 200)
        next_token = logged_in['data']['token']
        self.assertEqual(self.request('/api/account/preferences', token=next_token)[1], {'language': 'zh'})
        self.assertEqual(self.request('/api/account/preferences', {'language': 'en'}, token=next_token, method='PUT')[1], {'language': 'en'})
        self.assertEqual(self.request('/api/account/preferences', token=token)[1], {'language': 'en'})
