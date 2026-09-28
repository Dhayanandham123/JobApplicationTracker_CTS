import unittest
import tempfile
import os
import json
from unittest.mock import patch

from app import create_app
from database.db import get_db

class FitScoreAndResumeVersionsTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.app = create_app({
            'TESTING': True,
            'DATABASE': self.db_path,
            'SECRET_KEY': 'test-secret-key'
        })
        self.client = self.app.test_client()
        self.register_and_login('test_user', 'test_user@example.com', 'password123')

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

    def test_resume_text_api(self):
        # 1. GET initial empty resume
        res = self.client.get('/api/resume')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['resume_text'], '')
        self.assertEqual(res.get_json()['resume_filename'], '')

    def test_resume_upload_api(self):
        import io
        # 1. Upload TXT File
        data = {
            'resume_file': (io.BytesIO(b'Python Flask Specialist with 5 years experience'), 'my_resume.txt')
        }
        res = self.client.post('/api/resume/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        self.assertEqual(res.get_json()['filename'], 'my_resume.txt')

        # 2. Check GET /api/resume
        res_get = self.client.get('/api/resume')
        self.assertEqual(res_get.get_json()['resume_filename'], 'my_resume.txt')
        self.assertEqual(res_get.get_json()['resume_text'], 'Python Flask Specialist with 5 years experience')

        # 3. DELETE /api/resume
        res_del = self.client.delete('/api/resume')
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(self.client.get('/api/resume').get_json()['resume_text'], '')

    def test_resume_versions_crud_and_analytics(self):
        # 1. Create Resume Versions
        res1 = self.client.post('/api/resume-versions', json={'version_name': 'Version A - Backend'})
        self.assertEqual(res1.status_code, 201)
        ver1_id = res1.get_json()['id']

        res2 = self.client.post('/api/resume-versions', json={'version_name': 'Version B - AI Focus'})
        self.assertEqual(res2.status_code, 201)

        # 2. List Resume Versions
        res_list = self.client.get('/api/resume-versions')
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.get_json()), 2)

        # 3. Create Applications linked to Resume Versions
        app1 = self.client.post('/applications', json={
            'company_name': 'Stripe',
            'job_title': 'Backend Engineer',
            'status': 'Interviewing',
            'resume_version': 'Version A - Backend'
        }).get_json()

        app2 = self.client.post('/applications', json={
            'company_name': 'OpenAI',
            'job_title': 'AI Researcher',
            'status': 'Offered',
            'resume_version': 'Version B - AI Focus'
        }).get_json()

        # 4. Fetch Resume Versions Analytics
        res_analytics = self.client.get('/api/analytics/resume-versions')
        self.assertEqual(res_analytics.status_code, 200)
        stats = res_analytics.get_json()
        self.assertTrue(any(s['version_name'] == 'Version A - Backend' and s['total'] == 1 for s in stats))
        self.assertTrue(any(s['version_name'] == 'Version B - AI Focus' and s['total'] == 1 for s in stats))

        # 5. Delete Resume Version
        res_del = self.client.delete(f'/api/resume-versions/{ver1_id}')
        self.assertEqual(res_del.status_code, 200)

    @patch('services.groq_service.urllib.request.urlopen')
    def test_fit_score_calculation_with_mocked_groq(self, mock_urlopen):
        # Mock Groq API JSON response
        mock_response = unittest.mock.MagicMock()
        mock_response.read.return_value = json.dumps({
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'fit_score': 85,
                        'missing_skills': ['Kubernetes', 'GraphQL']
                    })
                }
            }]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        import io
        # Save resume text via upload
        data = {
            'resume_file': (io.BytesIO(b'Python Flask Engineer'), 'resume.txt')
        }
        self.client.post('/api/resume/upload', data=data, content_type='multipart/form-data')

        # Create application -> triggers compute_fit_score
        res = self.client.post('/applications', json={
            'company_name': 'Datadog',
            'job_title': 'Software Engineer',
            'notes': 'Looking for Python, Flask, Kubernetes, and GraphQL.'
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()

        self.assertEqual(data['fit_score'], 85)
        self.assertIn('Kubernetes', data['missing_skills_list'])

    def test_version_file_upload_and_fit_score_selection(self):
        import io
        # 1. Create a version with attached document file
        data = {
            'version_name': 'Version C - Fullstack',
            'resume_file': (io.BytesIO(b'React TypeScript Node.js Specialist'), 'fullstack_resume.txt')
        }
        res = self.client.post('/api/resume-versions', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 201)
        ver_data = res.get_json()
        self.assertEqual(ver_data['filename'], 'fullstack_resume.txt')
        ver_id = ver_data['id']

        # 2. Select version for fit score
        res_sel = self.client.post('/api/fit-score/select-version', json={'version_id': ver_id})
        self.assertEqual(res_sel.status_code, 200)
        self.assertTrue(res_sel.get_json()['success'])
        self.assertIn('React TypeScript', res_sel.get_json()['resume_text'])

if __name__ == '__main__':
    unittest.main()
