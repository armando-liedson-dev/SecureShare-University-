from fastapi.testclient import TestClient


def test_documentation_contains_university_routes():
    from app.main import app
    r=TestClient(app).get('/openapi.json')
    assert r.status_code==200
    paths=r.json()['paths']
    for expected in ['/documents','/documents/{document_id}/download','/documents/{document_id}/share-department',
                     '/admin/reconcile','/admin/departments','/admin/users','/auth/login']:
        assert expected in paths


def test_security_headers():
    from app.main import app
    r=TestClient(app).get('/openapi.json')
    assert r.headers['X-Content-Type-Options']=='nosniff'
    assert r.headers['X-Frame-Options']=='DENY'


def test_browser_index():
    from app.main import app
    r=TestClient(app).get('/')
    assert r.status_code==200
    assert 'SecureShare' in r.text
