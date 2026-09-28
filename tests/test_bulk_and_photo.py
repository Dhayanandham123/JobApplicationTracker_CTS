"""Regression tests for bulk status update and profile photo management."""
import io
import json

import pytest

from app import create_app
from database.db import init_db


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_bulk_photo.db"
    test_config = {
        'TESTING': True,
        'DATABASE': str(db_file),
        'SECRET_KEY': 'test-bulk-key',
    }
    app = create_app(test_config)
    with app.test_client() as c:
        with app.app_context():
            init_db()
        yield c


def _register(client, username='bulkuser', email='bulk@example.com'):
    client.post('/signup', data={
        'username': username,
        'email': email,
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)


def _seed(client, n=3):
    ids = []
    for i in range(n):
        res = client.post('/applications', json={
            'company_name': f'Company{i}',
            'job_title': f'Role{i}',
            'status': 'Applied',
            'date_applied': '2026-09-01'
        })
        assert res.status_code == 201
        ids.append(res.get_json()['id'])
    return ids


def test_bulk_status_update(client):
    _register(client)
    ids = _seed(client)
    res = client.post('/api/applications/bulk', json={
        'action': 'status', 'ids': ids[:2], 'status': 'Interviewing'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert sorted(data['updated']) == sorted(ids[:2])
    assert data['failed'] == []
    assert '2 applications updated to Interviewing.' == data['message']


def test_bulk_partial_failure_reported(client):
    _register(client)
    ids = _seed(client, n=1)
    res = client.post('/api/applications/bulk', json={
        'action': 'status', 'ids': [ids[0], 999999], 'status': 'Offered'})
    data = res.get_json()
    assert data['success'] is False
    assert data['updated'] == [ids[0]]
    assert len(data['failed']) == 1 and data['failed'][0]['id'] == 999999


def test_bulk_rejects_invalid_status(client):
    _register(client)
    ids = _seed(client, n=1)
    res = client.post('/api/applications/bulk', json={
        'action': 'status', 'ids': ids, 'status': 'Assessment'})
    assert res.status_code == 400


def test_bulk_archive_and_unarchive(client):
    _register(client)
    ids = _seed(client, n=2)
    res = client.post('/api/applications/bulk', json={'action': 'archive', 'ids': [ids[0]]})
    assert res.get_json()['success'] is True

    visible = [a['id'] for a in client.get('/applications').get_json()]
    assert ids[0] not in visible and ids[1] in visible

    all_apps = [a['id'] for a in client.get('/applications?include_archived=1').get_json()]
    assert ids[0] in all_apps

    res = client.post('/api/applications/bulk', json={'action': 'unarchive', 'ids': [ids[0]]})
    assert res.get_json()['success'] is True
    visible = [a['id'] for a in client.get('/applications').get_json()]
    assert ids[0] in visible


def test_bulk_delete(client):
    _register(client)
    ids = _seed(client, n=2)
    res = client.post('/api/applications/bulk', json={'action': 'delete', 'ids': [ids[0]]})
    assert res.get_json()['success'] is True
    visible = [a['id'] for a in client.get('/applications').get_json()]
    assert ids[0] not in visible


def _png_bytes(extra=64):
    return b'\x89PNG\r\n\x1a\n' + b'\x00' * extra


def test_photo_upload_serve_remove(client):
    _register(client)
    raw = _png_bytes()
    res = client.post('/api/profile/photo',
                      data={'photo': (io.BytesIO(raw), 'me.png')},
                      content_type='multipart/form-data')
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    got = client.get('/api/profile/photo/file')
    assert got.status_code == 200
    assert got.content_type == 'image/png'
    assert got.data == raw

    res = client.delete('/api/profile/photo')
    assert res.get_json()['success'] is True
    assert client.get('/api/profile/photo/file').status_code == 404


def test_photo_rejects_bad_files(client):
    _register(client)
    res = client.post('/api/profile/photo',
                      data={'photo': (io.BytesIO(b'not an image at all'), 'x.png')},
                      content_type='multipart/form-data')
    assert res.status_code == 400

    res = client.post('/api/profile/photo',
                      data={'photo': (io.BytesIO(b'gifstuff'), 'x.gif')},
                      content_type='multipart/form-data')
    assert res.status_code == 400

    big = b'\x89PNG\r\n\x1a\n' + b'\x00' * (2 * 1024 * 1024 + 1)
    res = client.post('/api/profile/photo',
                      data={'photo': (io.BytesIO(big), 'big.png')},
                      content_type='multipart/form-data')
    assert res.status_code == 400
