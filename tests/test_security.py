"""JWT signing/validation and Argon2 password verification."""
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
import pytest


def test_password_hash():
    from app.security import hash_password,verify_password
    hash_value=hash_password('password-that-is-long')
    assert 'password-that-is-long' not in hash_value
    assert verify_password(hash_value,'password-that-is-long')
    assert not verify_password(hash_value,'incorrect')


def test_rs256_token_and_tamper(monkeypatch,tmp_path):
    from app import security
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    private=tmp_path/'private.pem';public=tmp_path/'public.pem'
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                     serialization.PublicFormat.SubjectPublicKeyInfo))
    monkeypatch.setenv('JWT_PRIVATE_KEY_PATH',str(private))
    monkeypatch.setenv('JWT_PUBLIC_KEY_PATH',str(public))
    token=security.create_access_token(7,'aluno')
    claims=security.decode_access_token(token)
    assert claims['sub']=='7'
    assert claims['aud']==security.AUDIENCE
    head,payload,sig=token.split('.')
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token(head+'.'+('A' if payload[0]!='A' else 'B')+payload[1:]+'.'+sig)
