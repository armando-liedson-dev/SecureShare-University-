"""Private node-to-node HTTP client with TLS CA validation and per-node credentials."""
import hashlib

_SHARED_CLIENT = None
import httpx
from fastapi import HTTPException
from app.config import NODE_SECRETS, NODE_URLS, VERIFY_TLS


def storage_key(document):
    """Legacy data used numeric IDs; new uploads use an unguessable UUID storage key."""
    return str(document['storage_key'] or document['id'])


async def open_node_client():
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = httpx.AsyncClient(timeout=20.0, verify=VERIFY_TLS, trust_env=False)


async def close_node_client():
    global _SHARED_CLIENT
    if _SHARED_CLIENT is not None:
        await _SHARED_CLIENT.aclose()
        _SHARED_CLIENT = None


async def node_request(node_id, method, key, *, content=None, extra_headers=None, path_suffix=""):
    secret = NODE_SECRETS.get(node_id)
    if not secret or len(secret) < 32:
        raise HTTPException(500, f'Credencial de {node_id} não configurada')
    url = NODE_URLS[node_id].rstrip('/') + '/internal/files/' + key + path_suffix
    try:
        if _SHARED_CLIENT is not None:
            return await _SHARED_CLIENT.request(method, url, content=content,
                                                headers={'X-Service-Secret': secret, **(extra_headers or {})})
        async with httpx.AsyncClient(timeout=20.0, verify=VERIFY_TLS, trust_env=False) as client:
            return await client.request(method, url, content=content,
                                        headers={'X-Service-Secret': secret, **(extra_headers or {})})
    except (httpx.HTTPError, ValueError, OSError) as exc:
        raise HTTPException(503, f'Nó {node_id} indisponível ou ligação TLS inválida') from exc


async def verified_copy(document, node_id):
    """Only return complete, cryptographically verified bytes; never trust the node blindly."""
    result = await node_request(node_id, 'GET', storage_key(document))
    if result.status_code != 200:
        raise HTTPException(503, f'Nó {node_id} não devolveu o ficheiro')
    content = result.content
    if len(content) != document['size_bytes'] or hashlib.sha256(content).hexdigest() != document['sha256'].strip():
        raise HTTPException(502, f'Integridade comprometida no nó {node_id}')
    return content


async def write_replica(document, node_id, content):
    if hashlib.sha256(content).hexdigest() != document['sha256'].strip():
        raise HTTPException(500, 'Origem do documento não corresponde ao hash registado')
    result = await node_request(node_id, 'PUT', storage_key(document), content=content)
    if result.status_code == 409:
        # Explicit hash-verified repair, not a blind rollback or overwrite of arbitrary data.
        result = await node_request(node_id, 'POST', storage_key(document), content=content,
                                    path_suffix='/repair',
                                    extra_headers={'X-Expected-Sha256': document['sha256'].strip()})
    if result.status_code not in (200, 201):
        raise HTTPException(503, f'Falha ao escrever cópia no nó {node_id} (HTTP {result.status_code})')
    try:
        meta = result.json()
    except ValueError as exc:
        raise HTTPException(502, 'Resposta inválida do nó') from exc
    if meta.get('sha256') != document['sha256'].strip() or meta.get('size_bytes') != document['size_bytes']:
        raise HTTPException(502, 'Cópia armazenada não corresponde ao documento')
    return meta
