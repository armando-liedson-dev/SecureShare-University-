"""Shared database operations and error handling."""
from psycopg.types.json import Jsonb
from app.db import get_connection


def audit(user_id, action, resource_id, outcome, details=None, resource_type='document'):
    """Persist success, denial and error events; never log plaintext passwords or tokens."""
    with get_connection() as conn:
        conn.execute('''
          INSERT INTO audit_logs (user_id, action, resource_type, resource_id, outcome, details)
          VALUES (%s, %s, %s, %s, %s, %s)
        ''', (user_id, action, resource_type, str(resource_id) if resource_id is not None else None,
              outcome, Jsonb(details or {})))


def require_admin(user):
    from fastapi import HTTPException
    if user['role'] != 'admin':
        raise HTTPException(403, 'Acesso reservado ao administrador.')
