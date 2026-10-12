"""Identity, token validation/revocation and database-backed login throttling."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
import jwt
from app.db import get_connection
from app.common import audit
from app.security import TOKEN_MINUTES, create_access_token, decode_access_token, verify_password

router = APIRouter(prefix='/auth', tags=['Autenticação'])
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise HTTPException(401, 'Autenticação necessária.', headers={'WWW-Authenticate': 'Bearer'})
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload['sub'])
    except (jwt.InvalidTokenError, OSError, ValueError, KeyError):
        raise HTTPException(401, 'Token inválido ou expirado.', headers={'WWW-Authenticate': 'Bearer'})
    with get_connection() as conn:
        revoked = conn.execute('SELECT 1 FROM revoked_tokens WHERE jti=%s AND expires_at>NOW()', (payload['jti'],)).fetchone()
        row = conn.execute('''
          SELECT u.id, u.username, u.role, u.is_active, u.department_id, d.name
          FROM users u LEFT JOIN departments d ON d.id=u.department_id WHERE u.id=%s
        ''', (user_id,)).fetchone()
    if revoked or not row or not row[3]:
        raise HTTPException(401, 'Sessão revogada ou conta indisponível.')
    return {'id': row[0], 'username': row[1], 'role': row[2], 'department_id': row[4],
            'department': row[5], 'jti': payload['jti'], 'exp': payload['exp']}


@router.post('/login')
def login(data: LoginRequest, request: Request):
    # A client cannot override this with a spoofed X-Forwarded-For header.
    ip = request.client.host if request.client else 'unknown'
    identity_key = (data.username.casefold() + '|' + ip)[:200]
    with get_connection() as conn:
        conn.execute('''INSERT INTO login_limits(identity_key) VALUES(%s)
                        ON CONFLICT(identity_key) DO NOTHING''', (identity_key,))
        limit = conn.execute('''
          SELECT failures, window_start, locked_until FROM login_limits
          WHERE identity_key=%s FOR UPDATE
        ''', (identity_key,)).fetchone()
        now = datetime.now(timezone.utc)
        if limit[2] and limit[2] > now:
            raise HTTPException(429, 'Muitas tentativas. Aguarde e tente novamente.')
        row = conn.execute('SELECT id, username, password_hash, is_active FROM users WHERE username=%s',
                           (data.username,)).fetchone()
        valid = bool(row and row[3] and verify_password(row[2], data.password))
        if not valid:
            conn.execute('''
              UPDATE login_limits SET
                failures = CASE WHEN window_start < NOW()-INTERVAL '10 minutes' THEN 1 ELSE failures+1 END,
                window_start = CASE WHEN window_start < NOW()-INTERVAL '10 minutes' THEN NOW() ELSE window_start END,
                locked_until = CASE WHEN window_start >= NOW()-INTERVAL '10 minutes' AND failures+1 >= 5
                                THEN NOW()+INTERVAL '10 minutes' ELSE NULL END
              WHERE identity_key=%s
            ''', (identity_key,))
        else:
            conn.execute('UPDATE login_limits SET failures=0, locked_until=NULL, window_start=NOW() WHERE identity_key=%s', (identity_key,))
    audit(row[0] if valid else None, 'login', None, 'success' if valid else 'denied',
          {'username': data.username}, resource_type='auth')
    if not valid:
        raise HTTPException(401, 'Credenciais inválidas.', headers={'WWW-Authenticate': 'Bearer'})
    return {'access_token': create_access_token(row[0], row[1]), 'token_type': 'bearer',
            'expires_in': TOKEN_MINUTES * 60}


@router.get('/me')
def me(user=Depends(get_current_user)):
    return {k: user[k] for k in ('id', 'username', 'role', 'department_id', 'department')}


@router.post('/logout')
def logout(user=Depends(get_current_user)):
    with get_connection() as conn:
        conn.execute('INSERT INTO revoked_tokens(jti, expires_at) VALUES(%s,%s) ON CONFLICT DO NOTHING',
                     (user['jti'], datetime.fromtimestamp(user['exp'], tz=timezone.utc)))
    audit(user['id'], 'logout', None, 'success', resource_type='auth')
    return {'message': 'Sessão terminada.'}
