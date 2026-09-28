import unittest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from app import create_app

class ChatbotTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        
        class TestConfig:
            TESTING = True
            DATABASE = self.db_path
            SECRET_KEY = 'test-secret-key'
            GROQ_API_KEY = 'gsk_test_mock_key_12345'
            GROQ_MODEL = 'openai/gpt-oss-120b'

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def register_and_login(self):
        self.client.post('/signup', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)

    def test_chat_endpoint_missing_api_key(self):
        self.app.config['GROQ_API_KEY'] = ''
        self.register_and_login()

        res = self.client.post('/api/chat', json={'message': 'Hello AI'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('api_key_missing'))
        self.assertIn('Groq API Key Required', data.get('reply', ''))

    def test_chat_endpoint_mock_success(self):
        self.register_and_login()

        mock_groq_res = {
            'choices': [
                {
                    'message': {
                        'content': 'Hello! I am your AI Assistant. I can help you prepare for your Salesforce interview.'
                    }
                }
            ]
        }

        with patch('routes.chatbot.urllib.request.urlopen') as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.read.return_value = json.dumps(mock_groq_res).encode('utf-8')

            res = self.client.post('/api/chat', json={
                'message': 'Help me prepare for my Salesforce interview'
            })

            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn('Salesforce', data.get('reply', ''))
            self.assertEqual(data.get('model'), 'openai/gpt-oss-120b')

    def test_chat_endpoint_network_error_fallback(self):
        self.register_and_login()
        # Add a sample application to user portfolio
        self.client.post('/applications', json={
            'company_name': 'Salesforce',
            'job_title': 'Software Engineer Intern',
            'status': 'Applied'
        })

        import urllib.error
        with patch('routes.chatbot.urllib.request.urlopen', side_effect=urllib.error.URLError('getaddrinfo failed')):
            res = self.client.post('/api/chat', json={
                'message': 'How many job have i applied'
            })

            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get('offline_fallback'))
            self.assertIn('Salesforce', data.get('reply', ''))
            self.assertIn('1', data.get('reply', ''))

if __name__ == '__main__':
    unittest.main()
