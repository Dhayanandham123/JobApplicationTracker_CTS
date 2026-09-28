import unittest
import tempfile
import os
from datetime import date, timedelta
from unittest.mock import patch

from app import create_app
from database.db import get_db, update_user_settings
from services.email_service import process_upcoming_event_reminders

class EventRemindersTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.app = create_app({
            'TESTING': True,
            'DATABASE': self.db_path,
            'SECRET_KEY': 'test-secret-key',
            'MAIL_USERNAME': 'test@example.com',
            'MAIL_PASSWORD': 'testpassword'
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

    def test_24h_interview_and_assessment_email_reminders(self):
        self.register_and_login('alice_event', 'alice_event@example.com', 'password123')

        tomorrow = date.today() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%Y-%m-%d')

        # Create application with interview and assessment scheduled for tomorrow
        res = self.client.post('/applications', json={
            'company_name': 'NVIDIA',
            'job_title': 'Deep Learning Engineer',
            'status': 'Interviewing',
            'interview_date': tomorrow_str,
            'assessment_date': tomorrow_str
        })
        self.assertEqual(res.status_code, 201)

        # Run 24h event reminder processing with mocked SMTP
        with patch('services.email_service.smtplib.SMTP_SSL') as mock_smtp:
            with self.app.app_context():
                sent_count = process_upcoming_event_reminders()
                self.assertEqual(sent_count, 2) # 1 Interview + 1 Assessment email

        # Run process again on same day -> duplicate check should suppress emails
        with patch('services.email_service.smtplib.SMTP_SSL') as mock_smtp:
            with self.app.app_context():
                second_run_count = process_upcoming_event_reminders()
                self.assertEqual(second_run_count, 0)

    def test_disabled_settings_suppress_event_reminders(self):
        self.register_and_login('bob_event', 'bob_event@example.com', 'password123')

        tomorrow_str = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        res = self.client.post('/applications', json={
            'company_name': 'Intel',
            'job_title': 'Hardware Engineer',
            'status': 'Interviewing',
            'interview_date': tomorrow_str
        })
        self.assertEqual(res.status_code, 201)

        # Disable email_notifications in user_settings
        with self.app.app_context():
            update_user_settings(1, {'email_notifications': False})

        with patch('services.email_service.smtplib.SMTP_SSL') as mock_smtp:
            with self.app.app_context():
                sent_count = process_upcoming_event_reminders()
                self.assertEqual(sent_count, 0)

if __name__ == '__main__':
    unittest.main()
