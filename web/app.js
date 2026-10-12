'use strict';
// Access tokens are only in memory: neither localStorage nor cookies receive JWTs.
let token = null;
let me = null;
const $ = (id) => document.getElementById(id);
function notice(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(notice.handle);
  notice.handle = setTimeout(() => $('toast').hidden = true, 5000);
}
async function request(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(path, {...options, headers, cache:'no-store'});
  if (!r.ok) {
    let detail;
    try { detail = (await r.json()).detail; } catch { detail = `HTTP ${r.status}`; }
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail);
    throw new Error(msg);
  }
  return r;
}
async function json(path, options = {}) {
  const opts = {...options};
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.body = JSON.stringify(opts.body);
    opts.headers = {...(opts.headers||{}), 'Content-Type':'application/json'};
  }
  const res = await request(path, opts);
  return res.json();
}
function wrap(formId, fn) {
  $(formId).addEventListener('submit', async e => {
    e.preventDefault();
    const btn = e.currentTarget.querySelector('button[type=submit]');
    btn.disabled = true;
    try { await fn(new FormData(e.currentTarget)); } catch(ex) { notice('Erro: ' + ex.message); }
    finally { btn.disabled = false; }
  });
}
function signout() {
  token = null; me = null;
  $('dashboard').hidden = true; $('identity').hidden = true; $('login-screen').hidden = false;
  $('login-pass').value = '';
}
wrap('login-form', async fd => {
  const body = {username:fd.get('username'),password:fd.get('password')};
  const data=await json('/auth/login',{method:'POST',body});
  token=data.access_token;
  me=await json('/auth/me');
  $('who').textContent = `${me.username} · ${me.department || me.role}`;
  $('login-screen').hidden=true; $('dashboard').hidden=false; $('identity').hidden=false;
  $('admin-panel').hidden=me.role!=='admin';
  await refresh(); notice('Sessão iniciada com sucesso.');
});
$('signout').addEventListener('click',async()=>{
  try {await json('/auth/logout',{method:'POST'});} catch { /* UI revokes local token anyway */ }
  signout();
});
async function refreshDepartments() {
  const depts=await json('/departments');
  for(const id of ['share-dept','user-dept','revoke-dept']) {
    const sel=$(id); sel.replaceChildren();
    if(id==='user-dept') {const empty=document.createElement('option');empty.value='';empty.textContent='Sem departamento';sel.append(empty);}
    for(const dept of depts.filter(d=>d.is_active)){
      const opt=document.createElement('option');opt.value=dept.id;opt.textContent=dept.name;sel.append(opt);
    }
  }
}
function cell(text){const td=document.createElement('td');td.textContent=text==null?'—':String(text);return td;}
async function refreshDocuments() {
  const documents=await json('/documents');
  $('document-count').textContent=`${documents.length} documento(s)`;
  const rows=$('document-rows');rows.replaceChildren();
  for(const d of documents) {
    const tr=document.createElement('tr');
    for(const x of [`#${d.id} · ${d.filename}`,d.owner_username,d.department,(d.size_bytes/1024).toFixed(1)+' KB']) tr.append(cell(x));
    const actions=document.createElement('td');
    const download=document.createElement('button');download.textContent='Descarregar';download.onclick=()=>downloadDocument(d);
    actions.append(download);
    if(d.owner_id===me.id){
      const remove=document.createElement('button');remove.textContent='Eliminar';remove.className='subtle';
      remove.onclick=async()=>{if(confirm('Eliminar este documento e todas as réplicas?')){
        try {const response=await request(`/documents/${d.id}`,{method:'DELETE'});
          notice(response.status===202?'Eliminação em processamento.':'Documento eliminado.');await refreshDocuments();
        } catch(e){notice('Erro: '+e.message);}
      }};
      actions.append(remove);
    }
    tr.append(actions); rows.append(tr);
  }
  if(!documents.length){const tr=document.createElement('tr');const td=cell('Ainda não existem documentos autorizados.');td.colSpan=5;tr.append(td);rows.append(tr);}
}
async function refresh(){ await Promise.all([refreshDepartments(),refreshDocuments()]); }
$('refresh').addEventListener('click',async()=>{try{await refresh();notice('Atualizado.');}catch(e){notice('Erro: '+e.message)}});
async function downloadDocument(doc){
  try{
    const r=await request(`/documents/${doc.id}/download`);const blob=await r.blob();const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download=doc.filename;document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(e){notice('Erro: '+e.message);}
}
wrap('upload-form',async fd=>{
  const r=await json('/documents',{method:'POST',body:fd});
  notice(`Documento #${r.id} replicado nos dois nós.`);
  $('upload-form').reset();await refreshDocuments();
});
wrap('share-user-form',async fd=>{
  const id=Number(fd.get('document'));
  await json(`/documents/${id}/share`,{method:'POST',body:{username:fd.get('username'),can_read:true,can_delete:false}});
  notice('Acesso concedido ao utilizador.');
});
wrap('share-dept-form',async fd=>{
  const id=Number(fd.get('document'));
  await json(`/documents/${id}/share-department`,{method:'POST',body:{department_id:Number(fd.get('department'))}});
  notice('Acesso concedido ao departamento.');
});
wrap('department-form',async fd=>{
  await json('/admin/departments',{method:'POST',body:{name:fd.get('name')}});
  notice('Departamento criado.');$('department-form').reset();await refreshDepartments();
});
wrap('user-form',async fd=>{
  await json('/admin/users',{method:'POST',body:{username:fd.get('username'),password:fd.get('password'),
    department_id:fd.get('department')?Number(fd.get('department')):null,role:fd.get('role')}});
  notice('Utilizador criado.');$('user-form').reset();
});
$('reconcile').onclick=async()=>{try{$('admin-output').textContent=JSON.stringify(await json('/admin/reconcile',{method:'POST'}),null,2);notice('Verificação concluída.');}catch(e){notice('Erro: '+e.message)}};
$('audit').onclick=async()=>{try{$('admin-output').textContent=JSON.stringify(await json('/audit?limit=30'),null,2);}catch(e){notice('Erro: '+e.message)}};

wrap('revoke-user-form',async fd=>{
  await json(`/documents/${Number(fd.get('document'))}/share/${encodeURIComponent(fd.get('username'))}`,{method:'DELETE'});
  notice('Acesso individual revogado.');
});
wrap('revoke-dept-form',async fd=>{
  await json(`/documents/${Number(fd.get('document'))}/share-department/${Number(fd.get('department'))}`,{method:'DELETE'});
  notice('Acesso departamental revogado.');
});
$('replica-status').onclick=async()=>{try{$('admin-output').textContent=JSON.stringify(await json('/admin/replicas'),null,2);}catch(e){notice('Erro: '+e.message)}};
