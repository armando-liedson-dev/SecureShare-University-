import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerifyMismatchError,
)
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def read_key(env_name, default_name):
    path = Path(os.getenv(env_name, default_name))

    if not path.is_absolute():
        path = BASE_DIR / path

    return path.read_text(encoding="utf-8")


password_hasher = PasswordHasher()

ISSUER = os.getenv("JWT_ISSUER", "secureshare-auth")
AUDIENCE = os.getenv("JWT_AUDIENCE", "secureshare-api")
TOKEN_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "20"))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "username": username,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_MINUTES),
        "jti": str(uuid.uuid4()),
    }

    private_key = read_key(
        "JWT_PRIVATE_KEY_PATH",
        "keys/jwt_private.pem",
    )

    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
    )


def decode_access_token(token: str) -> dict:
    public_key = read_key(
        "JWT_PUBLIC_KEY_PATH",
        "keys/jwt_public.pem",
    )

    return jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        issuer=ISSUER,
        audience=AUDIENCE,
        options={
            "require": [
                "sub",
                "iss",
                "aud",
                "iat",
                "exp",
                "jti",
            ]
        },
    )
