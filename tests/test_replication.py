"""Isolated reconciliation behaviour; verifies the algorithms, not a live PostgreSQL cluster."""
import asyncio
import hashlib
from fastapi import HTTPException


def test_repair_missing_replica(monkeypatch):
    from app import admin
    body=b'%PDF-1.4 test\n'
    doc={'id':42,'storage_key':'a'*32,'sha256':hashlib.sha256(body).hexdigest(),
         'size_bytes':len(body),'status':'available','node_id':'node_a'}
    events=[]

    class Result:
        def __init__(self,rows):self.rows=rows
        def fetchall(self):return self.rows
        def fetchone(self):return self.rows[0] if self.rows else None
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,args=None):
            events.append(('sql',sql.strip().split()[0],args))
            if 'SELECT id FROM documents' in sql:return Result([(42,)])
            if 'SELECT status FROM documents' in sql:return Result([('available',)])
            return Result([])

    monkeypatch.setattr(admin,'get_connection',lambda:Connection())
    monkeypatch.setattr(admin,'fetch_document',lambda c,i:doc)
    async def fake_read(document,node):
        if node=='node_a':raise HTTPException(503,'Node A down')
        return body
    async def fake_write(document,node,content):
        assert content==body
        events.append(('repaired',node))
        return {'stored':True}
    monkeypatch.setattr(admin,'verified_copy',fake_read)
    monkeypatch.setattr(admin,'write_replica',fake_write)
    results=asyncio.run(admin.reconcile_documents(limit=5))
    assert results['checked']==1
    assert results['repaired']==1
    assert ('repaired','node_a') in events
    assert not results['still_degraded']


def test_no_source_never_replicates_unverified_bytes(monkeypatch):
    from app import admin
    class Result:
        def __init__(self,rows):self.rows=rows
        def fetchall(self):return self.rows
        def fetchone(self):return self.rows[0] if self.rows else None
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,args=None):
            if 'SELECT id FROM documents' in sql:return Result([(10,)])
            return Result([])
    monkeypatch.setattr(admin,'get_connection',lambda:Connection())
    monkeypatch.setattr(admin,'fetch_document',lambda c,i:{'id':10,'status':'uploading'})
    async def bad_read(doc,node):raise HTTPException(502,'hash mismatch')
    async def must_never_write(doc,node,content):assert False,'uncorroborated bytes were copied'
    monkeypatch.setattr(admin,'verified_copy',bad_read)
    monkeypatch.setattr(admin,'write_replica',must_never_write)
    result=asyncio.run(admin.reconcile_documents())
    assert result['repaired']==0
    assert result['still_degraded']==[10]
