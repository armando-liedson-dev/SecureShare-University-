"""University administration, audit trails and controlled repair of distributed replicas."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from app.auth import get_current_user
from app.common import audit, require_admin
from app.db import get_connection
from app.config import NODE_IDS
from app.security import hash_password
from app.storage_client import verified_copy, write_replica
from app.documents import fetch_document, purge_document

router = APIRouter(tags=['Administração'])


class DepartmentCreate(BaseModel):
    name: str=Field(min_length=2,max_length=100)
    description: str=Field(default='',max_length=500)


class UserCreate(BaseModel):
    username: str=Field(min_length=3,max_length=64,pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str=Field(min_length=12,max_length=256)
    role: str=Field(default='user',pattern=r'^(admin|user)$')
    department_id: int | None=None


class UserDepartmentUpdate(BaseModel):
    department_id: int | None=None


@router.get('/departments')
def departments(user=Depends(get_current_user)):
    with get_connection() as conn:
        rows=conn.execute('SELECT id,name,description,is_active FROM departments ORDER BY name').fetchall()
    return [dict(zip(('id','name','description','is_active'),r)) for r in rows]


@router.post('/admin/departments',status_code=201)
def create_department(data:DepartmentCreate,user=Depends(get_current_user)):
    require_admin(user)
    with get_connection() as conn:
        if conn.execute('SELECT 1 FROM departments WHERE lower(name)=lower(%s)',(data.name,)).fetchone():
            raise HTTPException(409,'Departamento já existe')
        row=conn.execute('INSERT INTO departments(name,description) VALUES(%s,%s) RETURNING id',
                         (data.name.strip(),data.description)).fetchone()
    audit(user['id'],'create_department',row[0],'success',{'name':data.name},'department')
    return {'id':row[0],'name':data.name}


@router.post('/admin/users',status_code=201)
def create_user(data:UserCreate,user=Depends(get_current_user)):
    require_admin(user)
    if data.department_id is not None:
        with get_connection() as conn:
            if not conn.execute('SELECT 1 FROM departments WHERE id=%s AND is_active=TRUE',(data.department_id,)).fetchone():
                raise HTTPException(404,'Departamento inválido')
    with get_connection() as conn:
        if conn.execute('SELECT 1 FROM users WHERE username=%s',(data.username,)).fetchone():
            raise HTTPException(409,'Nome já utilizado')
        row=conn.execute('''INSERT INTO users(username,password_hash,role,department_id)
          VALUES(%s,%s,%s,%s) RETURNING id''',
          (data.username,hash_password(data.password),data.role,data.department_id)).fetchone()
    audit(user['id'],'create_user',row[0],'success',{'username':data.username,'role':data.role},'user')
    return {'id':row[0],'username':data.username,'role':data.role,'department_id':data.department_id}


@router.get('/admin/users')
def list_users(user=Depends(get_current_user)):
    require_admin(user)
    with get_connection() as conn:
        rows=conn.execute('''SELECT u.id,u.username,u.role,u.is_active,u.department_id,d.name
                             FROM users u LEFT JOIN departments d ON u.department_id=d.id ORDER BY u.id''').fetchall()
    return [dict(zip(('id','username','role','is_active','department_id','department'),r)) for r in rows]


@router.patch('/admin/users/{user_id}/department')
def move_user(user_id:int,data:UserDepartmentUpdate,user=Depends(get_current_user)):
    require_admin(user)
    with get_connection() as conn:
        if data.department_id is not None and not conn.execute('SELECT 1 FROM departments WHERE id=%s AND is_active=TRUE',
                                                               (data.department_id,)).fetchone():
            raise HTTPException(404,'Departamento inexistente')
        row=conn.execute('UPDATE users SET department_id=%s WHERE id=%s RETURNING id',
                         (data.department_id,user_id)).fetchone()
        if not row:
            raise HTTPException(404,'Utilizador inexistente')
    audit(user['id'],'move_department',user_id,'success',{'department_id':data.department_id},'user')
    return {'message':'Departamento actualizado'}


@router.get('/audit')
def audit_logs(user=Depends(get_current_user),limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    require_admin(user)
    with get_connection() as conn:
        rows=conn.execute('''SELECT id,user_id,action,resource_type,resource_id,outcome,details,created_at
                             FROM audit_logs ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s''',
                          (limit,offset)).fetchall()
    return [dict(zip(('id','user_id','action','resource_type','resource_id','outcome','details','created_at'),r)) for r in rows]


async def reconcile_documents(limit=20):
    """Reconcile a small batch. Safe to retry; source must match hash before any new copy."""
    with get_connection() as conn:
        rows=conn.execute('''SELECT id FROM documents WHERE status IN ('uploading','deleting','available')
          ORDER BY CASE WHEN status='deleting' THEN 0 WHEN status='uploading' THEN 1 ELSE 2 END, last_verified_at ASC NULLS FIRST, id
          LIMIT %s''',(limit,)).fetchall()
    result={'checked':0,'repaired':0,'completed_deletions':0,'still_degraded':[]}
    for (doc_id,) in rows:
        with get_connection() as conn:
            doc=fetch_document(conn,doc_id)
        if not doc:
            continue
        result['checked']+=1
        if doc['status']=='deleting':
            failures=await purge_document(doc)
            if not failures:
                result['completed_deletions']+=1
            else:
                result['still_degraded'].append(doc_id)
            with get_connection() as conn:
                conn.execute('UPDATE documents SET last_verified_at=NOW() WHERE id=%s',(doc_id,))
            continue
        source=None
        healthy=[]
        for node in NODE_IDS:
            try:
                content=await verified_copy(doc,node)
                if source is None:
                    source=content
                healthy.append(node)
            except HTTPException:
                pass
        if source is None:
            with get_connection() as conn:
                for node in NODE_IDS:
                    conn.execute("UPDATE document_replicas SET status='failed',updated_at=NOW() WHERE document_id=%s AND node_id=%s",
                                 (doc_id,node))
            result['still_degraded'].append(doc_id)
            with get_connection() as conn:
                conn.execute('UPDATE documents SET last_verified_at=NOW() WHERE id=%s',(doc_id,))
            continue
        for node in NODE_IDS:
            if node not in healthy:
                try:
                    await write_replica(doc,node,source)
                    healthy.append(node)
                    result['repaired']+=1
                except HTTPException:
                    pass
        cleanup_after_delete=False
        with get_connection() as conn:
            # Serialize state update with deletion, which may have started during network I/O.
            row=conn.execute('SELECT status FROM documents WHERE id=%s FOR UPDATE',(doc_id,)).fetchone()
            if row and row[0] in ('uploading','available'):
                for node in NODE_IDS:
                    conn.execute('''INSERT INTO document_replicas(document_id,node_id,status,sha256,size_bytes)
                         VALUES(%s,%s,%s,%s,%s)
                         ON CONFLICT(document_id,node_id) DO UPDATE
                         SET status=EXCLUDED.status,updated_at=NOW()''',
                         (doc_id,node,'available' if node in healthy else 'failed',doc['sha256'],doc['size_bytes']))
                if len(healthy)==len(NODE_IDS):
                    conn.execute("UPDATE documents SET status='available' WHERE id=%s",(doc_id,))
                else:
                    result['still_degraded'].append(doc_id)
            elif row and row[0] in ('deleting','deleted'):
                # A concurrent deletion superseded this repair; remove copies that may have
                # been reintroduced during remote I/O, after releasing the database row lock.
                cleanup_after_delete=True
                result['still_degraded'].append(doc_id)
            conn.execute('UPDATE documents SET last_verified_at=NOW() WHERE id=%s',(doc_id,))
        if cleanup_after_delete:
            await purge_document(doc)
    return result


@router.post('/admin/reconcile')
async def reconcile(user=Depends(get_current_user),limit:int=Query(20,ge=1,le=100)):
    require_admin(user)
    result=await reconcile_documents(limit)
    audit(user['id'],'reconcile',None,'success',result,'system')
    return result


@router.get('/admin/replicas')
def replica_health(user=Depends(get_current_user)):
    require_admin(user)
    with get_connection() as conn:
        rows=conn.execute('''SELECT d.id,d.filename,d.status,r.node_id,r.status
          FROM documents d LEFT JOIN document_replicas r ON r.document_id=d.id
          WHERE d.status<>'deleted' ORDER BY d.id DESC,r.node_id LIMIT 300''').fetchall()
    return [dict(zip(('document_id','filename','document_status','node_id','replica_status'),r)) for r in rows]

@router.post('/admin/documents/{document_id}/cancel-pending')
async def cancel_stuck_upload(document_id:int,user=Depends(get_current_user)):
    """Administrator may safely cancel a permanently pending upload (without losing audit history)."""
    require_admin(user)
    with get_connection() as conn:
        row=conn.execute('SELECT status FROM documents WHERE id=%s FOR UPDATE',(document_id,)).fetchone()
        if not row or row[0]!='uploading':
            raise HTTPException(409,'Somente uploads pendentes podem ser cancelados')
        conn.execute("UPDATE documents SET status='deleting' WHERE id=%s",(document_id,))
        doc=fetch_document(conn,document_id)
    failed=await purge_document(doc)
    audit(user['id'],'cancel_upload',document_id,'error' if failed else 'success',
          {'pending_nodes':failed},'document')
    return {'document_id':document_id,'cleanup_pending':bool(failed),'failed_nodes':failed}
