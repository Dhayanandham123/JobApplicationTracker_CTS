import unittest
import sys
import os
from datetime import date, timedelta
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from database.db import init_db
from routes.applications import calculate_days_since

class AuthAndApplicationsTestCase(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        
        class TestConfig:
            TESTING = True
            DATABASE = self.db_path
            SECRET_KEY = 'test-secret-key'
            MAIL_USERNAME = 'test@example.com'
            MAIL_PASSWORD = 'testpassword'

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def register(self, username, email, password):
        return self.client.post('/signup', data={
            'username': username,
            'email': email,
            'password': password,
            'confirm_password': password
        }, follow_redirects=True)

    def login(self, login_input, password):
        return self.client.post('/login', data={
            'login_input': login_input,
            'password': password
        }, follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_unauthenticated_redirect(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/welcome' in response.headers['Location'] or '/login' in response.headers['Location'])

    def test_signup_and_login(self):
        # Register user
        res = self.register('alice', 'alice@example.com', 'password123')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(b'Job & Internship Tracker' in res.data or b'Job &amp; Internship Tracker' in res.data)

        # Logout
        self.logout()

        # Login with bad password
        res_bad = self.login('alice', 'wrongpassword')
        self.assertIn(b'Invalid username/email or password', res_bad.data)

        # Login with correct password
        res_good = self.login('alice', 'password123')
        self.assertEqual(res_good.status_code, 200)
        self.assertTrue(b'Job & Internship Tracker' in res_good.data or b'Job &amp; Internship Tracker' in res_good.data)

    def test_create_and_get_application_for_user(self):
        self.register('bob', 'bob@example.com', 'password123')

        # Test POST creation
        post_data = {
            'company_name': 'Acme Corp',
            'job_title': 'Software Engineer Intern',
            'status': 'Applied',
            'date_applied': '2026-08-01',
            'notes': 'Referred by John'
        }
        res = self.client.post('/applications', json=post_data)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data['company_name'], 'Acme Corp')
        app_id = data['id']

        # Test GET list
        res_get = self.client.get('/applications')
        self.assertEqual(res_get.status_code, 200)
        list_data = res_get.get_json()
        self.assertEqual(len(list_data), 1)
        self.assertEqual(list_data[0]['id'], app_id)

    def test_multi_user_data_isolation(self):
        # Register User A and create an application
        self.register('user_a', 'usera@example.com', 'password123')
        res_a = self.client.post('/applications', json={
            'company_name': 'Company A',
            'job_title': 'Developer A',
            'status': 'Applied'
        })
        app_a_id = res_a.get_json()['id']
        self.logout()

        # Register User B
        self.register('user_b', 'userb@example.com', 'password123')
        
        # User B should see 0 applications
        res_b_get = self.client.get('/applications')
        self.assertEqual(len(res_b_get.get_json()), 0)

        # User B cannot update User A's application
        res_b_put = self.client.put(f'/applications/{app_a_id}', json={'status': 'Offered'})
        self.assertEqual(res_b_put.status_code, 404)

        # User B cannot delete User A's application
        res_b_del = self.client.delete(f'/applications/{app_a_id}')
        self.assertEqual(res_b_del.status_code, 404)

    def test_followup_days_calculation(self):
        today = date.today()
        eight_days_ago = (today - timedelta(days=8)).strftime('%Y-%m-%d')
        three_days_ago = (today - timedelta(days=3)).strftime('%Y-%m-%d')

        self.assertEqual(calculate_days_since(eight_days_ago), 8)
        self.assertEqual(calculate_days_since(three_days_ago), 3)
        self.assertEqual(calculate_days_since(today.strftime('%Y-%m-%d')), 0)

    def test_automated_stale_reminder_scheduler(self):
        from unittest.mock import patch
        from services.email_service import process_automated_stale_reminders
        from database.db import get_db

        self.register('carol', 'carol@example.com', 'password123')

        ten_days_ago = (date.today() - timedelta(days=10)).strftime('%Y-%m-%d')
        res = self.client.post('/applications', json={
            'company_name': 'Meta',
            'job_title': 'Production Engineer',
            'status': 'Applied',
            'date_applied': ten_days_ago
        })
        app_id = res.get_json()['id']

        with self.app.app_context():
            db = get_db()
            db.execute('UPDATE applications SET last_updated = ? WHERE id = ?', (ten_days_ago, app_id))
            db.commit()

        with patch('services.email_service.smtplib.SMTP_SSL') as mock_smtp:
            with self.app.app_context():
                sent_count = process_automated_stale_reminders()
                self.assertEqual(sent_count, 1)

    def test_upcoming_interview_date(self):
        self.register('dave', 'dave@example.com', 'password123')

        res_create = self.client.post('/applications', json={
            'company_name': 'Microsoft',
            'job_title': 'Data Analyst Intern',
            'status': 'Interviewing',
            'interview_date': '2026-08-29'
        })
        self.assertEqual(res_create.status_code, 201)
        data = res_create.get_json()
        self.assertEqual(data['interview_date'], '2026-08-29')
        self.assertEqual(data['formatted_interview_date'], 'Aug 29, 2026')

    def test_get_calendar_events(self):
        self.register('eve', 'eve@example.com', 'password123')

        self.client.post('/applications', json={
            'company_name': 'Microsoft',
            'job_title': 'Cloud Engineer',
            'status': 'Interviewing',
            'interview_date': '2026-08-28',
            'assessment_date': '2026-08-29'
        })

        res = self.client.get('/api/calendar-events')
        self.assertEqual(res.status_code, 200)
        events = res.get_json()
        self.assertGreaterEqual(len(events), 2)

        event_types = [e['event_type'] for e in events]
        self.assertIn('interviewing', event_types)

    def test_get_analytics(self):
        self.register('frank', 'frank@example.com', 'password123')

        self.client.post('/applications', json={
            'company_name': 'Google',
            'job_title': 'Software Engineer',
            'status': 'Interviewing'
        })
        self.client.post('/applications', json={
            'company_name': 'Apple',
            'job_title': 'iOS Developer',
            'status': 'Offered'
        })

        res = self.client.get('/api/analytics')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['interviewing'], 1)
        self.assertEqual(data['offered'], 1)
        self.assertEqual(data['interview_rate'], 100.0)
        self.assertEqual(data['offer_rate'], 50.0)

    def test_get_single_application_details(self):
        self.register('grace', 'grace@example.com', 'password123')

        res_create = self.client.post('/applications', json={
            'company_name': 'Netflix',
            'job_title': 'Backend Developer',
            'status': 'Applied',
            'interview_date': '2026-09-01',
            'notes': 'Refers by John'
        })
        app_id = res_create.get_json()['id']

        res_details = self.client.get(f'/applications/{app_id}')
        self.assertEqual(res_details.status_code, 200)
        data = res_details.get_json()
        self.assertEqual(data['company_name'], 'Netflix')
        self.assertEqual(data['job_title'], 'Backend Developer')
        self.assertEqual(data['interview_date'], '2026-09-01')
        self.assertEqual(data['notes'], 'Refers by John')

    def test_autofill_url_endpoint(self):
        self.register('helen', 'helen@example.com', 'password123')

        from unittest.mock import patch
        mock_html = '''
        <html>
          <head>
            <meta property="og:title" content="Software Engineer at Google" />
            <meta property="og:site_name" content="Google Careers" />
            <meta property="og:description" content="Join our engineering team to build web-scale software applications." />
          </head>
          <body>
            <div>Location: San Francisco, CA</div>
            <div>Salary: $140,000 / yr</div>
          </body>
        </html>
        '''
        with patch('routes.applications.urllib.request.urlopen') as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.read.return_value = mock_html.encode('utf-8')

            res = self.client.post('/api/autofill-url', json={'url': 'https://google.com/jobs/123'})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data['success'])
            # og:title "Software Engineer at Google" names the true employer;
            # og:site_name ("Google Careers") is only a site label fallback.
            self.assertEqual(data['company_name'], 'Google')
            self.assertEqual(data['job_title'], 'Software Engineer')
            self.assertEqual(data['job_description'], 'Join our engineering team to build web-scale software applications.')

    def test_application_url_salary_location_fields(self):
        self.register('ian', 'ian@example.com', 'password123')

        res_create = self.client.post('/applications', json={
            'company_name': 'Stripe',
            'job_title': 'Frontend Engineer',
            'status': 'Applied',
            'job_url': 'https://stripe.com/jobs/frontend',
            'salary': '$150,000/yr',
            'location': 'Remote',
            'job_type': 'Full-time'
        })
        self.assertEqual(res_create.status_code, 201)
        data = res_create.get_json()
        self.assertEqual(data['job_url'], 'https://stripe.com/jobs/frontend')
        self.assertEqual(data['salary'], '$150,000/yr')
        self.assertEqual(data['location'], 'Remote')
        self.assertEqual(data['job_type'], 'Full-time')

    def test_autofill_salesforce_location_and_title(self):
        self.register('jack', 'jack@example.com', 'password123')

        from unittest.mock import patch
        mock_salesforce_html = '''
        <html>
          <head>
            <title>Salesforce Jobs</title>
            <meta property="og:site_name" content="Salesforce" />
            <meta name="description" content="Salesforce internship opportunity for Software Engineering students." />
          </head>
          <body>
            <h1>Intern - Software Engineer AMTS</h1>
            <p>Location: Hyderabad/Bangalore, India</p>
          </body>
        </html>
        '''
        with patch('routes.applications.urllib.request.urlopen') as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.read.return_value = mock_salesforce_html.encode('utf-8')

            res = self.client.post('/api/autofill-url', json={'url': 'https://salesforce.com/careers/jobs/JR337715'})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data['success'])
            self.assertEqual(data['company_name'], 'Salesforce')
            self.assertEqual(data['job_title'], 'Intern - Software Engineer AMTS')
            self.assertEqual(data['location'], 'Hyderabad/Bangalore, India')
            self.assertEqual(data['job_type'], 'Internship')
            self.assertEqual(data['job_description'], 'Salesforce internship opportunity for Software Engineering students.')

if __name__ == '__main__':
    unittest.main()
