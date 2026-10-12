"""Isolated storage-node functional and negative/security tests (no PostgreSQL needed)."""
import importlib
import hashlib
import sys
from fastapi.testclient import TestClient
import pytest

@pytest.fixture()
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('NODE_ID','node_a')
    monkeypatch.setenv('NODE_A_SECRET','s'*50)
    monkeypatch.setenv('STORAGE_DIR',str(tmp_path))
    from app import storage_node
    importlib.reload(storage_node)
    return TestClient(storage_node.app)

HEADERS={'X-Service-Secret':'s'*50}
KEY='0123456789abcdef0123456789abcdef'


def test_health(client):
    assert client.get('/health').json()['status']=='ok'


def test_protected_storage(client):
    assert client.put('/internal/files/'+KEY,content=b'a').status_code==401
    assert client.get('/internal/files/'+KEY).status_code==401
    assert client.delete('/internal/files/'+KEY).status_code==401
    assert client.put('/internal/files/'+KEY,content=b'a',headers={'X-Service-Secret':'wrong'}).status_code==401


def test_round_trip_and_idempotency(client):
    data=b'%PDF-1.4\nFicheiro demonstrativo'
    out=client.put('/internal/files/'+KEY,content=data,headers=HEADERS)
    assert out.status_code==200
    assert out.json()['sha256']==hashlib.sha256(data).hexdigest()
    assert out.json()['size_bytes']==len(data)
    assert client.put('/internal/files/'+KEY,content=data,headers=HEADERS).json()['idempotent'] is True
    assert client.put('/internal/files/'+KEY,content=b'outro',headers=HEADERS).status_code==409
    assert client.get('/internal/files/'+KEY,headers=HEADERS).content==data
    assert client.delete('/internal/files/'+KEY,headers=HEADERS).status_code==200
    assert client.delete('/internal/files/'+KEY,headers=HEADERS).status_code==200
    assert client.get('/internal/files/'+KEY,headers=HEADERS).status_code==404


@pytest.mark.parametrize('path', ['..','foo','-1','1..2','abc','1%2Fsecret'])
def test_reject_invalid_ids(client,path):
    res=client.put('/internal/files/'+path,content=b'secret',headers=HEADERS)
    assert res.status_code in (400,404)


def test_legacy_numeric_ids_still_work(client):
    assert client.put('/internal/files/42',content=b'old',headers=HEADERS).status_code==200
    assert client.get('/internal/files/42',headers=HEADERS).content==b'old'


def test_oversized_upload(client):
    r=client.put('/internal/files/'+KEY,content=b'x'*(20*1024*1024+1),headers=HEADERS)
    assert r.status_code==413


def test_corruption_can_be_repaired_with_correct_hash(client, tmp_path):
    original=b'%PDF-1.4\ncorrect\n'
    assert client.put('/internal/files/'+KEY,content=original,headers=HEADERS).status_code==200
    (tmp_path/KEY).write_bytes(b'corrupt')
    assert client.put('/internal/files/'+KEY,content=original,headers=HEADERS).status_code==409
    wrong_headers={**HEADERS, 'X-Expected-Sha256':hashlib.sha256(original).hexdigest()}
    assert client.post('/internal/files/'+KEY+'/repair',content=b'wrong',headers=wrong_headers).status_code==422
    assert (tmp_path/KEY).read_bytes()==b'corrupt'
    assert client.post('/internal/files/'+KEY+'/repair',content=original,headers=wrong_headers).status_code==200
    assert client.get('/internal/files/'+KEY,headers=HEADERS).content==original
