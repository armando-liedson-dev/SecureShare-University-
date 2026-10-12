"""PostgreSQL persistence and additive migrations for the academic prototype.

Existing SecureShare databases are preserved: schema changes use ADD COLUMN IF NOT EXISTS.
Use a tested backup before running migrations against real data.
"""
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    params = {
        'dbname': os.getenv('PGDATABASE', 'secureshare'),
        'user': os.getenv('PGUSER', 'secureshare'),
        'connect_timeout': 8,
    }
    for env, key in [('PGHOST', 'host'), ('PGPORT', 'port'), ('PGPASSWORD', 'password')]:
        if os.getenv(env):
            params[key] = os.getenv(env)
    return psycopg.connect(**params)


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS departments (
        id BIGSERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE,
        description TEXT NOT NULL DEFAULT '',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        username VARCHAR(64) UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS department_id BIGINT REFERENCES departments(id)",
    """CREATE TABLE IF NOT EXISTS revoked_tokens (
        jti TEXT PRIMARY KEY, expires_at TIMESTAMPTZ NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_revoked_tokens_exp ON revoked_tokens(expires_at)",
    """CREATE TABLE IF NOT EXISTS documents (
        id BIGSERIAL PRIMARY KEY,
        owner_id BIGINT NOT NULL REFERENCES users(id),
        filename TEXT NOT NULL,
        content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
        size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
        sha256 CHAR(64) NOT NULL,
        node_id VARCHAR(20) NOT NULL CHECK (node_id IN ('node_a', 'node_b')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_key VARCHAR(40)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'available'",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status)",
    "CREATE INDEX IF NOT EXISTS idx_docs_owner ON documents(owner_id)",
    """CREATE TABLE IF NOT EXISTS document_replicas (
        document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        node_id VARCHAR(20) NOT NULL CHECK (node_id IN ('node_a', 'node_b')),
        status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('available', 'failed', 'pending')),
        sha256 CHAR(64) NOT NULL,
        size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY(document_id, node_id)
    )""",
    """CREATE TABLE IF NOT EXISTS document_shares (
        document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        can_read BOOLEAN NOT NULL DEFAULT TRUE,
        can_delete BOOLEAN NOT NULL DEFAULT FALSE,
        shared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY(document_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS department_shares (
        document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        department_id BIGINT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
        can_read BOOLEAN NOT NULL DEFAULT TRUE,
        shared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY(document_id, department_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_department_shares ON department_shares(department_id, document_id)",
    """CREATE TABLE IF NOT EXISTS audit_logs (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
        action VARCHAR(64) NOT NULL,
        resource_type VARCHAR(32) NOT NULL,
        resource_id TEXT,
        outcome VARCHAR(16) NOT NULL CHECK(outcome IN ('success', 'denied', 'error')),
        details JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC)",
    """CREATE TABLE IF NOT EXISTS login_limits (
        identity_key VARCHAR(200) PRIMARY KEY,
        failures INTEGER NOT NULL DEFAULT 0,
        window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        locked_until TIMESTAMPTZ
    )""",
]


def init_db():
    with get_connection() as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.execute('DELETE FROM revoked_tokens WHERE expires_at <= NOW()')
