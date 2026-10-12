"""Document workflow: authorization, durable upload intent, replication, and tombstone deletion."""
import hashlib
import asyncio
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.common import audit
from app.config import ALLOWED_SUFFIXES, MAX_FILE_SIZE, NODE_IDS
from app.db import get_connection
from app.storage_client import node_request, storage_key, verified_copy, write_replica

router = APIRouter(prefix='/documents', tags=['Documentos'])

# An administrative user does NOT automatically receive access to confidential documents.
VISIBLE = '''(
  d.owner_id=%s OR EXISTS(SELECT 1 FROM document_shares s
      WHERE s.document_id=d.id AND s.user_id=%s AND s.can_read=TRUE)
  OR EXISTS(SELECT 1 FROM department_shares ds JOIN users u ON u.department_id=ds.department_id
      WHERE ds.document_id=d.id AND u.id=%s AND ds.can_read=TRUE)
)'''
DELETABLE = '''(
  d.owner_id=%s OR EXISTS(SELECT 1 FROM document_shares s
      WHERE s.document_id=d.id AND s.user_id=%s AND s.can_delete=TRUE)
)'''


def row_to_document(r):
    return dict(zip(('id','owner_id','filename','content_type','size_bytes','sha256','node_id','storage_key','status','created_at'),r))


def fetch_document(conn, document_id):
    row = conn.execute('''
      SELECT id, owner_id, filename, content_type, size_bytes, sha256,
             node_id, storage_key, status, created_at FROM documents WHERE id=%s
    ''', (document_id,)).fetchone()
    return row_to_document(row) if row else None


def _access(conn, document_id, user, permission='read', allow_deleting=False):
    expr = VISIBLE if permission=='read' else DELETABLE
    rows = conn.execute(f'''SELECT d.id FROM documents d WHERE d.id=%s
      AND d.status IN ({"'available','deleting'" if allow_deleting else "'available'"})
      AND {expr}''', (document_id, user['id'], user['id'], *([user['id']] if permission=='read' else []))).fetchone()
    return bool(rows)


def _owner(conn, doc_id, user_id):
    row=conn.execute('SELECT owner_id FROM documents WHERE id=%s AND status=%s', (doc_id,'available')).fetchone()
    if not row:
        raise HTTPException(404, 'Documento não encontrado ou indisponível')
    if row[0] != user_id:
        raise HTTPException(403, 'Só o proprietário pode modificar partilhas')


@router.post('', status_code=201)
async def upload_document(file: UploadFile=File(...), user=Depends(get_current_user)):
    filename = Path((file.filename or '').replace('\\','/')).name.strip()
    if not filename or filename in ('.','..') or len(filename)>180:
        raise HTTPException(400, 'Nome inválido')
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, 'Formato não permitido: PDF, TXT, CSV, DOCX, XLSX ou PPTX')
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content)>MAX_FILE_SIZE:
        raise HTTPException(413, 'Limite de 20 MiB excedido')
    if not content:
        raise HTTPException(400, 'Ficheiro vazio')
    if suffix=='.pdf' and not content.startswith(b'%PDF-'):
        raise HTTPException(415, 'O conteúdo não corresponde a um PDF')
    if suffix in ('.docx','.xlsx','.pptx') and not content.startswith(b'PK'):
        raise HTTPException(415, 'Formato Office inválido')
    digest=hashlib.sha256(content).hexdigest()
    key=uuid.uuid4().hex
    with get_connection() as conn:
        row=conn.execute('''
          INSERT INTO documents(owner_id,filename,content_type,size_bytes,sha256,node_id,storage_key,status)
          VALUES(%s,%s,%s,%s,%s,%s,%s,'uploading') RETURNING id
        ''',(user['id'],filename,mimetypes.guess_type(filename)[0] or 'application/octet-stream',
             len(content),digest,'node_a',key)).fetchone()
        doc_id=row[0]
        for node in NODE_IDS:
            conn.execute('''INSERT INTO document_replicas(document_id,node_id,status,sha256,size_bytes)
                          VALUES(%s,%s,'pending',%s,%s)''',(doc_id,node,digest,len(content)))
    document={'id': doc_id,'storage_key':key,'sha256':digest,'size_bytes':len(content)}
    # Two independent HTTPS uploads run concurrently; release metadata only after BOTH confirmations.
    async def attempt_copy(node):
        try:
            await write_replica(document,node,content)
            return True
        except HTTPException:
            return False

    outcomes=await asyncio.gather(*(attempt_copy(node) for node in NODE_IDS))
    failures=[node for node,ok in zip(NODE_IDS,outcomes) if not ok]
    with get_connection() as conn:
        for node,ok in zip(NODE_IDS,outcomes):
            conn.execute("""UPDATE document_replicas SET status=%s,updated_at=NOW()
                            WHERE document_id=%s AND node_id=%s""",
                         ('available' if ok else 'failed',doc_id,node))
    if failures:
        audit(user['id'],'upload',doc_id,'error',{'pending_repair': True,'failed_nodes': failures})
        # No attempted blind rollback: durable 'uploading' state allows safe reconciliation.
        raise HTTPException(503,detail={'message':'Upload pendente; requer reconciliação.', 'document_id':doc_id,
                                        'failed_nodes':failures})
    with get_connection() as conn:
        committed = conn.execute("UPDATE documents SET status='available' WHERE id=%s AND status='uploading' RETURNING id",
                                 (doc_id,)).fetchone()
    if not committed:
        # Administrator may have cancelled this incomplete upload while nodes were writing.
        for node in NODE_IDS:
            try:
                await node_request(node,'DELETE',key)
            except HTTPException:
                pass  # The tombstone/reconciliation still controls access and cleanup.
        audit(user['id'],'upload',doc_id,'error',{'reason':'cancelled_during_upload'})
        raise HTTPException(409,'Envio cancelado durante a operação')
    audit(user['id'],'upload',doc_id,'success',{'replicas':list(NODE_IDS)})
    return {'id':doc_id,'filename':filename,'size_bytes':len(content),'sha256':digest,
            'replicas':list(NODE_IDS),'status':'available'}


@router.get('')
def list_documents(user=Depends(get_current_user)):
    with get_connection() as conn:
        rows=conn.execute(f'''
          SELECT DISTINCT d.id,d.filename,d.content_type,d.size_bytes,d.sha256,d.node_id,
                 d.created_at,d.owner_id,u.username,dep.name
          FROM documents d JOIN users u ON u.id=d.owner_id
          LEFT JOIN departments dep ON dep.id=u.department_id
          WHERE d.status='available' AND {VISIBLE}
          ORDER BY d.created_at DESC LIMIT 200
        ''',(user['id'],user['id'],user['id'])).fetchall()
    return [dict(zip(('id','filename','content_type','size_bytes','sha256','node_id','created_at',
                      'owner_id','owner_username','department'),r)) for r in rows]


@router.get('/{document_id}/download')
async def download_document(document_id:int,user=Depends(get_current_user)):
    with get_connection() as conn:
        allowed=_access(conn, document_id,user)
        document=fetch_document(conn,document_id) if allowed else None
    if not document:
        audit(user['id'],'download',document_id,'denied')
        raise HTTPException(404,'Documento não encontrado ou sem permissão de leitura')
    preferred=document['node_id']
    failure=[]
    for node in [preferred] + [n for n in NODE_IDS if n!=preferred]:
        try:
            content=await verified_copy(document,node)
        except HTTPException:
            failure.append(node)
            with get_connection() as conn:
                conn.execute('''UPDATE document_replicas SET status='failed',updated_at=NOW()
                                WHERE document_id=%s AND node_id=%s''',(document_id,node))
            continue
        with get_connection() as conn:
            conn.execute('''UPDATE document_replicas SET status='available',updated_at=NOW()
                            WHERE document_id=%s AND node_id=%s''',(document_id,node))
        # Recheck ACL immediately before delivering the content (revocation could occur during I/O).
        with get_connection() as conn:
            if not _access(conn,document_id,user):
                audit(user['id'],'download',document_id,'denied')
                raise HTTPException(403,'Permissão revogada durante o pedido')
        audit(user['id'],'download',document_id,'success',{'served_by':node,'fallback':node!=preferred,
                                                           'degraded_nodes':failure})
        return Response(content=content,media_type='application/octet-stream',
                        headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(document['filename']),
                                 'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    audit(user['id'],'download',document_id,'error',{'unavailable_nodes': failure})
    raise HTTPException(503,'Nenhuma réplica íntegra está disponível')


class ShareRequest(BaseModel):
    username: str=Field(min_length=1,max_length=64)
    can_read: bool=True
    can_delete: bool=False


@router.post('/{document_id}/share')
def share_user(document_id:int,data:ShareRequest,user=Depends(get_current_user)):
    if not data.can_read and not data.can_delete:
        raise HTTPException(400,'Conceda ao menos uma permissão')
    with get_connection() as conn:
        _owner(conn,document_id,user['id'])
        recipient=conn.execute('SELECT id FROM users WHERE username=%s AND is_active=TRUE',(data.username,)).fetchone()
        if not recipient:
            raise HTTPException(404,'Destinatário não encontrado')
        if recipient[0]==user['id']:
            raise HTTPException(400,'O proprietário já tem acesso')
        conn.execute('''INSERT INTO document_shares(document_id,user_id,can_read,can_delete)
          VALUES(%s,%s,%s,%s) ON CONFLICT(document_id,user_id)
          DO UPDATE SET can_read=EXCLUDED.can_read,can_delete=EXCLUDED.can_delete,shared_at=NOW()''',
          (document_id,recipient[0],data.can_read,data.can_delete))
    audit(user['id'],'share_user',document_id,'success',{'username':data.username})
    return {'message':'Partilha individual actualizada'}


@router.delete('/{document_id}/share/{username}')
def revoke_user_share(document_id:int,username:str,user=Depends(get_current_user)):
    with get_connection() as conn:
        _owner(conn,document_id,user['id'])
        deleted=conn.execute('''DELETE FROM document_shares WHERE document_id=%s AND
          user_id=(SELECT id FROM users WHERE username=%s) RETURNING user_id''',(document_id,username)).fetchone()
        if not deleted:
            raise HTTPException(404,'Partilha inexistente')
    audit(user['id'],'revoke_user',document_id,'success',{'username':username})
    return {'message':'Partilha revogada'}


class DepartmentShare(BaseModel):
    department_id: int=Field(gt=0)


@router.post('/{document_id}/share-department')
def share_department(document_id:int,data:DepartmentShare,user=Depends(get_current_user)):
    with get_connection() as conn:
        _owner(conn,document_id,user['id'])
        dep=conn.execute('SELECT id FROM departments WHERE id=%s AND is_active=TRUE',(data.department_id,)).fetchone()
        if not dep:
            raise HTTPException(404,'Departamento inexistente')
        conn.execute('''INSERT INTO department_shares(document_id,department_id)
          VALUES(%s,%s) ON CONFLICT(document_id,department_id)
          DO UPDATE SET can_read=TRUE,shared_at=NOW()''',(document_id,data.department_id))
    audit(user['id'],'share_department',document_id,'success',{'department_id':data.department_id})
    return {'message':'Departamento autorizado'}


@router.delete('/{document_id}/share-department/{department_id}')
def revoke_department(document_id:int,department_id:int,user=Depends(get_current_user)):
    with get_connection() as conn:
        _owner(conn,document_id,user['id'])
        row=conn.execute('DELETE FROM department_shares WHERE document_id=%s AND department_id=%s RETURNING department_id',
                         (document_id,department_id)).fetchone()
        if not row:
            raise HTTPException(404,'Partilha inexistente')
    audit(user['id'],'revoke_department',document_id,'success',{'department_id':department_id})
    return {'message':'Partilha departamental revogada'}


async def purge_document(document):
    """Idempotent delete with durable tombstone; metadata remains for audit and retries."""
    failures=[]
    for node in NODE_IDS:
        try:
            response=await node_request(node,'DELETE',storage_key(document))
            if response.status_code not in (200,204,404):
                failures.append(node)
        except HTTPException:
            failures.append(node)
        with get_connection() as conn:
            conn.execute('''UPDATE document_replicas SET status=%s,updated_at=NOW()
                           WHERE document_id=%s AND node_id=%s''',
                         ('failed' if node in failures else 'pending',document['id'],node))
    if not failures:
        with get_connection() as conn:
            conn.execute("UPDATE documents SET status='deleted',deleted_at=NOW() WHERE id=%s AND status='deleting'",
                         (document['id'],))
    return failures


@router.delete('/{document_id}')
async def delete_document(document_id:int,user=Depends(get_current_user)):
    with get_connection() as conn:
        if not _access(conn,document_id,user,'delete',allow_deleting=True):
            raise HTTPException(404,'Documento inexistente ou sem permissão para eliminar')
        # Lock stops concurrent transitions between deletion and new download authorizations.
        current=conn.execute('SELECT status FROM documents WHERE id=%s FOR UPDATE',(document_id,)).fetchone()
        if not current or current[0] not in ('available','deleting'):
            raise HTTPException(409,'Documento ainda não disponível para eliminação')
        conn.execute("UPDATE documents SET status='deleting' WHERE id=%s",(document_id,))
        document=fetch_document(conn,document_id)
    failed=await purge_document(document)
    audit(user['id'],'delete',document_id,'error' if failed else 'success',{'pending_nodes':failed})
    if failed:
        return Response(content='{"message":"Eliminação pendente; a reconciliação concluirá a operação."}',
                        status_code=202,media_type='application/json')
    return {'message':'Documento eliminado dos dois nós (metadados mantidos para auditoria).'}
