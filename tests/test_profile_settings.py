import unittest
from app import create_app
from database.db import get_db, init_db

import tempfile
import os

class ProfileAndSettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.app = create_app({
            'TESTING': True,
            'DATABASE': self.db_path,
            'SECRET_KEY': 'test-secret-key'
        })
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def register_and_login(self, username, email, password):
        self.client.post('/signup', data={
            'username': username,
            'email': email,
            'password': password,
            'confirm_password': password
        }, follow_redirects=True)

    def test_get_and_update_profile(self):
        self.register_and_login('sam', 'sam@example.com', 'password123')

        # Test GET profile
        res_get = self.client.get('/api/profile')
        self.assertEqual(res_get.status_code, 200)
        profile_data = res_get.get_json()
        self.assertEqual(profile_data['username'], 'sam')

        # Test PUT update profile
        update_payload = {
            'full_name': 'Sam Student',
            'phone': '+1 555-0199',
            'location': 'Seattle, WA',
            'headline': 'CS Grad | AI Developer',
            'university': 'UW',
            'grad_year': '2026'
        }
        res_put = self.client.put('/api/profile', json=update_payload)
        self.assertEqual(res_put.status_code, 200)
        data = res_put.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['full_name'], 'Sam Student')
        self.assertEqual(data['user']['headline'], 'CS Grad | AI Developer')

    def test_get_and_update_settings(self):
        self.register_and_login('tina', 'tina@example.com', 'password123')

        # Test GET settings
        res_get = self.client.get('/api/settings')
        self.assertEqual(res_get.status_code, 200)
        settings = res_get.get_json()
        self.assertIn('notify_followup', settings)

        # Test PUT update settings
        settings_payload = {
            'notify_followup': False,
            'notify_interview': True,
            'reminder_time': '2 Hours Before',
            'email_notifications': False,
            'theme': 'dark',
            'card_density': 'compact'
        }
        res_put = self.client.put('/api/settings', json=settings_payload)
        self.assertEqual(res_put.status_code, 200)
        updated = res_put.get_json()['settings']
        self.assertEqual(updated['notify_followup'], 0)
        self.assertEqual(updated['theme'], 'dark')
        self.assertEqual(updated['card_density'], 'compact')

    def test_change_password(self):
        self.register_and_login('uma', 'uma@example.com', 'password123')

        # Test bad current password
        res_bad = self.client.post('/api/account/change-password', json={
            'current_password': 'wrongpassword',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        })
        self.assertEqual(res_bad.status_code, 400)
        self.assertIn('Incorrect current password', res_bad.get_json()['error'])

        # Test valid password change
        res_good = self.client.post('/api/account/change-password', json={
            'current_password': 'password123',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        })
        self.assertEqual(res_good.status_code, 200)
        self.assertTrue(res_good.get_json()['success'])

    def test_delete_account(self):
        self.register_and_login('victor', 'victor@example.com', 'password123')

        res_del = self.client.post('/api/account/delete')
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.get_json()['success'])

        # Verify profile can no longer be accessed (unauthenticated)
        res_check = self.client.get('/api/profile')
        self.assertIn(res_check.status_code, [401, 302])

if __name__ == '__main__':
    unittest.main()
