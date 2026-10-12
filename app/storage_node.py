"""Isolated HTTPS storage service. File IDs are opaque UUIDs, legacy numeric IDs remain readable.

Atomic creation avoids overwriting unrelated files; retries with identical bytes are safe.
"""
import hashlib
import hmac
import os
import re
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse

load_dotenv()
NODE_ID = os.getenv('NODE_ID', 'node_a')
if NODE_ID not in ('node_a', 'node_b'):
    raise RuntimeError('NODE_ID inválido')
SERVICE_SECRET = os.getenv('NODE_A_SECRET' if NODE_ID == 'node_a' else 'NODE_B_SECRET') or os.getenv('STORAGE_SERVICE_SECRET')
if not SERVICE_SECRET or len(SERVICE_SECRET) < 32:
    raise RuntimeError(f'Segredo de {NODE_ID} em falta: execute scripts/bootstrap.py')
STORAGE_DIR = Path(os.getenv('STORAGE_DIR', f'storage/{NODE_ID}')).resolve()
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 20 * 1024 * 1024
app = FastAPI(title=f'SecureShare Storage {NODE_ID}', docs_url=None, redoc_url=None)


def authenticate_service(token):
    if not token or not hmac.compare_digest(token, SERVICE_SECRET):
        raise HTTPException(401, 'Serviço não autenticado')


def safe_path(file_id):
    if not re.fullmatch(r'(?:[1-9][0-9]*|[a-f0-9]{32})', file_id):
        raise HTTPException(400, 'Identificador inválido')
    p = (STORAGE_DIR / file_id).resolve()
    if p.parent != STORAGE_DIR:
        raise HTTPException(400, 'Caminho inválido')
    return p


@app.get('/health')
def health():
    return {'status': 'ok', 'node': NODE_ID}


@app.put('/internal/files/{file_id}')
async def store_file(file_id: str, request: Request, x_service_secret: str | None = Header(None)):
    authenticate_service(x_service_secret)
    path = safe_path(file_id)
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > MAX_FILE_SIZE:
            raise HTTPException(413, 'Ficheiro demasiado grande')
    content = bytes(body)
    digest = hashlib.sha256(content).hexdigest()
    if path.exists():
        # Immutable file: same bytes are an idempotent retry; different bytes MUST NOT overwrite.
        if path.is_file() and path.stat().st_size == len(content) and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            return {'stored': True, 'idempotent': True, 'node': NODE_ID,
                    'file_id': file_id, 'sha256': digest, 'size_bytes': len(content)}
        raise HTTPException(409, 'Identificador já utilizado por outro conteúdo')
    # Unique temporary file + exclusive hard-link: atomic publication; concurrent PUT cannot overwrite.
    fd, temporary_name = tempfile.mkstemp(prefix='.upload-', dir=STORAGE_DIR)
    try:
        with os.fdopen(fd, 'wb') as writer:
            writer.write(content)
            writer.flush()
            os.fsync(writer.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                pass
            else:
                raise HTTPException(409, 'Identificador em conflito')
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return {'stored': True, 'node': NODE_ID, 'file_id': file_id, 'sha256': digest, 'size_bytes': len(content)}


@app.get('/internal/files/{file_id}')
def retrieve_file(file_id: str, x_service_secret: str | None = Header(None)):
    authenticate_service(x_service_secret)
    path = safe_path(file_id)
    if not path.is_file():
        raise HTTPException(404, 'Ficheiro não encontrado')
    return FileResponse(path, filename=file_id)


@app.delete('/internal/files/{file_id}')
def delete_file(file_id: str, x_service_secret: str | None = Header(None)):
    authenticate_service(x_service_secret)
    path = safe_path(file_id)
    path.unlink(missing_ok=True)
    return {'deleted': True, 'node': NODE_ID}


@app.post('/internal/files/{file_id}/repair')
async def repair_file(file_id: str, request: Request, x_service_secret: str | None = Header(None),
                      x_expected_sha256: str | None = Header(None)):
    """Authorized, hash-verified replacement of a corrupt replica. No arbitrary content accepted."""
    authenticate_service(x_service_secret)
    path = safe_path(file_id)
    if not x_expected_sha256 or not re.fullmatch(r'[a-f0-9]{64}', x_expected_sha256):
        raise HTTPException(400, 'Hash de reparação obrigatório')
    content = bytearray()
    async for part in request.stream():
        content.extend(part)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(413, 'Ficheiro demasiado grande')
    if hashlib.sha256(content).hexdigest() != x_expected_sha256:
        raise HTTPException(422, 'Conteúdo de reparação não corresponde ao hash esperado')
    fd, temporary_name = tempfile.mkstemp(prefix='.repair-', dir=STORAGE_DIR)
    try:
        with os.fdopen(fd, 'wb') as writer:
            writer.write(content)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return {'stored': True, 'repaired': True, 'file_id': file_id, 'node': NODE_ID,
            'sha256': x_expected_sha256, 'size_bytes': len(content)}
