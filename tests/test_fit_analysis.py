"""Tests for the FIT Score structured analysis pipeline."""
import io
import json
from unittest.mock import patch

import pytest

from app import create_app
from database.db import init_db
from services.groq_service import validate_fit_analysis
from services.resume_context import get_active_resume


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_fit.db"
    test_config = {
        'TESTING': True,
        'DATABASE': str(db_file),
        'SECRET_KEY': 'test-fit-key',
        'GROQ_API_KEY': '',
    }
    app = create_app(test_config)
    with app.test_client() as c:
        with app.app_context():
            init_db()
        yield c


def _register(client, username='fituser', email='fit@example.com'):
    client.post('/signup', data={
        'username': username,
        'email': email,
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)


def test_validate_fit_analysis_accepts_good_payload():
    payload = {
        'fit_score': 92,
        'summary': 'Strong match overall.',
        'strengths': [{'title': 'Python experience', 'detail': 'Used daily', 'status': 'PRESENT'}],
        'improvements': [{'priority': 'HIGH', 'title': 'SQL visibility', 'detail': 'Not present',
                          'status': 'MISSING', 'evidence': 'JD lists SQL'}],
        'keywords_present': [{'keyword': 'Python', 'status': 'PRESENT'}],
        'keywords_missing': [{'keyword': 'SQL', 'status': 'MISSING'}],
        'final_advice': 'Highlight SQL-adjacent work.'
    }
    cleaned, err = validate_fit_analysis(payload)
    assert err is None
    assert cleaned['fit_score'] == 92
    assert cleaned['strengths'][0]['status'] == 'PRESENT'
    assert cleaned['improvements'][0]['priority'] == 'HIGH'


def test_validate_fit_analysis_rejects_garbage():
    assert validate_fit_analysis('not a dict')[0] is None
    assert validate_fit_analysis({'summary': 'x'})[0] is None
    assert validate_fit_analysis({'fit_score': 'high', 'summary': 'x'})[0] is None
    # Unknown status labels are coerced, not fatal
    cleaned, err = validate_fit_analysis({
        'fit_score': 50, 'summary': 'ok',
        'strengths': [{'title': 'T', 'status': 'BOGUS'}],
    })
    assert err is None
    assert cleaned['strengths'][0]['status'] == 'NEEDS_VERIFICATION'


def test_analyze_requires_application_id(client):
    _register(client)
    res = client.post('/api/fit-score/analyze', json={})
    assert res.status_code == 400


def test_analyze_requires_existing_job(client):
    _register(client)
    res = client.post('/api/fit-score/analyze', json={'application_id': 424242})
    assert res.status_code == 404


def test_analyze_requires_resume(client):
    _register(client)
    res = client.post('/applications', json={
        'company_name': 'Zenithbyte', 'job_title': 'Data Science Intern',
        'status': 'Applied', 'date_applied': '2026-09-01'})
    app_id = res.get_json()['id']
    res = client.post('/api/fit-score/analyze', json={'application_id': app_id})
    assert res.status_code == 400
    assert res.get_json()['error_type'] == 'NO_RESUME'


def _groq_ok_response(reply_text):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                'choices': [{'message': {'content': reply_text}, 'finish_reason': 'stop'}]
            }).encode('utf-8')
    return FakeResp()


def test_analyze_returns_structured_result_with_authoritative_score(client):
    _register(client)
    with client.session_transaction() as sess:
        user_id = sess['user_id']
    # Seed an active resume directly
    with client.application.app_context():
        from database.db import get_db
        db = get_db()
        db.execute('UPDATE users SET resume_text = ?, resume_filename = ? WHERE id = ?',
                   ('Python developer with ML projects using scikit-learn.', 'resume.pdf', user_id))
        db.commit()
    res = client.post('/applications', json={
        'company_name': 'Zenithbyte', 'job_title': 'Data Science Intern',
        'status': 'Applied', 'date_applied': '2026-09-01',
        'notes': 'Requires Python, SQL, TensorFlow.'})
    app_id = res.get_json()['id']

    # Force a deterministic authoritative score on the application row
    with client.application.app_context():
        from database.db import get_db
        db = get_db()
        db.execute('UPDATE applications SET fit_score = ? WHERE id = ?', (92, app_id))
        db.commit()

    analysis_json = json.dumps({
        'fit_score': 1,  # wrong on purpose: server must enforce 92
        'summary': 'Good match.',
        'strengths': [{'title': 'Python', 'detail': 'In resume', 'status': 'PRESENT'}],
        'improvements': [{'priority': 'HIGH', 'title': 'SQL', 'detail': 'Missing',
                          'status': 'MISSING', 'evidence': 'JD requires SQL'}],
        'keywords_present': [{'keyword': 'Python', 'status': 'PRESENT'}],
        'keywords_missing': [{'keyword': 'SQL', 'status': 'MISSING'}],
        'final_advice': 'Add SQL context.'
    })
    with patch('services.groq_service.urllib.request.urlopen',
               return_value=_groq_ok_response(analysis_json)):
        with patch.object(client.application.config, 'get', wraps=client.application.config.get):
            pass
        # Provide API key via config for this test
        client.application.config['GROQ_API_KEY'] = 'gsk_test_key'
        res = client.post('/api/fit-score/analyze', json={'application_id': app_id})

    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert data['success'] is True
    assert data['authoritative_fit_score'] == 92
    assert data['analysis']['fit_score'] == 92  # enforced, not the model's 1
    assert data['analysis']['improvements'][0]['status'] == 'MISSING'
    assert data['resume_filename'] == 'resume.pdf'
    # No raw model text leaks through
    assert 'analysis' in data and isinstance(data['analysis'], dict)


def test_analyze_without_api_key_returns_clean_error(client):
    _register(client)
    with client.session_transaction() as sess:
        user_id = sess['user_id']
    with client.application.app_context():
        from database.db import get_db
        db = get_db()
        db.execute('UPDATE users SET resume_text = ?, resume_filename = ? WHERE id = ?',
                   ('Some resume text here.', 'r.pdf', user_id))
        db.commit()
    res = client.post('/applications', json={
        'company_name': 'C', 'job_title': 'R', 'status': 'Applied', 'date_applied': '2026-09-01'})
    app_id = res.get_json()['id']
    client.application.config['GROQ_API_KEY'] = ''
    res = client.post('/api/fit-score/analyze', json={'application_id': app_id})
    assert res.status_code == 502
    data = res.get_json()
    assert data['success'] is False
    assert data['retryable'] is True


def test_resume_resolver_returns_empty_without_resume(client):
    _register(client)
    with client.session_transaction() as sess:
        user_id = sess['user_id']
    with client.application.app_context():
        resume = get_active_resume(user_id)
    assert resume['has_resume'] is False


def test_chatbot_includes_resume_context(client):
    _register(client)
    with client.session_transaction() as sess:
        user_id = sess['user_id']
    with client.application.app_context():
        from database.db import get_db
        db = get_db()
        db.execute('UPDATE users SET resume_text = ?, resume_filename = ? WHERE id = ?',
                   ('UNIQUE_RESUME_MARKER scikit-learn pipelines', 'r.pdf', user_id))
        db.commit()

    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                'choices': [{'message': {'content': 'Hello! How can I help?'}, 'finish_reason': 'stop'}]
            }).encode('utf-8')

    orig_request = __import__('urllib.request', fromlist=['Request']).Request

    def fake_urlopen(req, timeout=None):
        import json as j
        captured['payload'] = j.loads(req.data.decode('utf-8'))
        return FakeResp()

    client.application.config['GROQ_API_KEY'] = 'gsk_test_key'
    with patch('routes.chatbot.urllib.request.urlopen', side_effect=fake_urlopen):
        res = client.post('/api/chat', json={'message': 'Review my resume', 'history': []})
    assert res.status_code == 200
    system_text = captured['payload']['messages'][0]['content']
    assert 'UNIQUE_RESUME_MARKER' in system_text
    assert 'NEVER ask the user to paste' in system_text or 'paste' in system_text
