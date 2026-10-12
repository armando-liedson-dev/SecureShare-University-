"""Generate fresh local secrets and a development-only TLS certificate authority.

Usage: python scripts/bootstrap.py  (requires cryptography)
Never send generated .env, private keys, CA key or documents to anyone.
"""
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
import os
import secrets
import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT=Path(__file__).resolve().parent.parent


def private_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(data)
    try:
        os.chmod(path,0o600)
    except OSError:
        pass


def key_bytes(key):
    return key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,
                             serialization.NoEncryption())


def create():
    targets=[ROOT/'.env',ROOT/'keys/jwt_private.pem',ROOT/'keys/jwt_public.pem',
             ROOT/'certs/ca.key',ROOT/'certs/ca.pem',ROOT/'certs/server.key',ROOT/'certs/server.pem']
    if any(p.exists() for p in targets):
        print('Já existem ficheiros de segurança locais. Para evitar substituição acidental, nada foi alterado.')
        print('Para rodar as chaves, faça backup da base de dados e remova os ficheiros locais conscientemente.')
        return 1
    env = '\n'.join([
        'PGDATABASE=secureshare',
        'PGUSER=secureshare',
        'PGPASSWORD='+secrets.token_urlsafe(40),
        'PGHOST=postgres',
        'PGPORT=5432',
        'NODE_A_URL=https://node_a:8001',
        'NODE_B_URL=https://node_b:8002',
        'NODE_A_SECRET='+secrets.token_urlsafe(48),
        'NODE_B_SECRET='+secrets.token_urlsafe(48),
        'JWT_PRIVATE_KEY_PATH=keys/jwt_private.pem',
        'JWT_PUBLIC_KEY_PATH=keys/jwt_public.pem',
        'JWT_ISSUER=secureshare-auth',
        'JWT_AUDIENCE=secureshare-api',
        'JWT_EXPIRE_MINUTES=20',
        'SECURESHARE_CA_BUNDLE=certs/ca.pem',
        'RECONCILE_INTERVAL_SECONDS=90',
        'CORS_ORIGINS=',
    ])+'\n'
    private_file(ROOT/'.env',env.encode())
    jwt_key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    private_file(ROOT/'keys/jwt_private.pem',key_bytes(jwt_key))
    private_file(ROOT/'keys/jwt_public.pem',jwt_key.public_key().public_bytes(
        serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    now=datetime.now(timezone.utc)
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SecureShare Local Development CA')])
    ca_cert=(x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
             .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365))
             .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
             .add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=False,
                 key_cert_sign=True,crl_sign=True,content_commitment=False,data_encipherment=False,
                 key_agreement=False,encipher_only=False,decipher_only=False),critical=True)
             .sign(ca_key,hashes.SHA256()))
    private_file(ROOT/'certs/ca.key',key_bytes(ca_key))
    private_file(ROOT/'certs/ca.pem',ca_cert.public_bytes(serialization.Encoding.PEM))
    server_key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'secureshare-local')])
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(ca_name)
          .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=90))
          .add_extension(x509.SubjectAlternativeName([
              x509.DNSName(n) for n in ('localhost','api','node_a','node_b')
          ]+[x509.IPAddress(ip_address('127.0.0.1'))]),critical=False)
          .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
          .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
          .sign(ca_key,hashes.SHA256()))
    private_file(ROOT/'certs/server.key',key_bytes(server_key))
    private_file(ROOT/'certs/server.pem',cert.public_bytes(serialization.Encoding.PEM))
    print('Credenciais e certificados locais criados com sucesso. Não incluir no ZIP nem no Git.')
    print('O certificado é somente para DESENVOLVIMENTO; não instalar a CA em máquinas de terceiros.')
    return 0


if __name__=='__main__':
    sys.exit(create())
