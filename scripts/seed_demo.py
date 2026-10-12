"""Idempotent synthetic university data: run INSIDE the API container after migrations."""
import secrets
from app.db import get_connection
from app.security import hash_password

DEPTS=['Registo Académico','Direcção Pedagógica','Recursos Humanos','Finanças']
USERS=[('registo','Registo Académico'),('direccao','Direcção Pedagógica'),('rh','Recursos Humanos'),('financas','Finanças')]


def main():
    with get_connection() as conn:
        for name in DEPTS:
            conn.execute('INSERT INTO departments(name) VALUES (%s) ON CONFLICT(name) DO NOTHING',(name,))
        for name,dep in USERS:
            if conn.execute('SELECT 1 FROM users WHERE username=%s',(name,)).fetchone():
                print(f'{name}: já existe (password não alterada)')
                continue
            password=secrets.token_urlsafe(18)
            conn.execute('''INSERT INTO users(username,password_hash,role,department_id)
              VALUES(%s,%s,'user',(SELECT id FROM departments WHERE name=%s))''',
                         (name,hash_password(password),dep))
            print(f'{name}: {password}  [guarde esta credencial de demonstração em local seguro]')
    print('Os dados são fictícios. Não utilize dados reais de estudantes.')

if __name__=='__main__':
    main()
