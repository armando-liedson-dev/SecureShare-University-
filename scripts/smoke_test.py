"""Full end-to-end live test; needs running Docker Compose + a seeded admin.

Inside container: docker compose exec api python scripts/smoke_test.py --base https://api:8000
"""
import argparse
from getpass import getpass
from pathlib import Path
import secrets
import httpx

ROOT=Path(__file__).resolve().parent.parent


def run(base,ca,admin,password):
    with httpx.Client(base_url=base,verify=str(ca),timeout=60.0,trust_env=False) as http:
        def check(r,codes=(200,)):
            if r.status_code not in codes:
                raise RuntimeError(f'{r.request.method} {r.request.url.path}: HTTP {r.status_code} {r.text[:500]}')
            return r
        check(http.get('/health'))
        token=check(http.post('/auth/login',json={'username':admin,'password':password})).json()['access_token']
        admin_headers={'Authorization':'Bearer '+token}
        suffix=secrets.token_hex(4)
        department=check(http.post('/admin/departments',headers=admin_headers,
               json={'name':'Direcção Demonstrativa '+suffix}), (201,)).json()['id']
        people=[]
        for label,dep in [('emissor',None),('destinatario',department),('externo',None)]:
            username=f'{label}_{suffix}'; pwd=secrets.token_urlsafe(18)
            check(http.post('/admin/users',headers=admin_headers,json={
                'username':username,'password':pwd,'role':'user','department_id':dep}), (201,))
            tok=check(http.post('/auth/login',json={'username':username,'password':pwd})).json()['access_token']
            people.append({'username':username,'headers':{'Authorization':'Bearer '+tok}})
        owner,recipient,outsider=people
        contents=b'%PDF-1.4\nSecureShare academic fake document\n%%EOF\n'
        uploaded=check(http.post('/documents',headers=owner['headers'],
              files={'file':('pauta-ficticia.pdf',contents,'application/pdf')}), (201,)).json()
        doc=uploaded['id']
        assert uploaded['replicas']==['node_a','node_b']
        assert check(http.get('/documents',headers=outsider['headers'])).json()==[]
        check(http.get(f'/documents/{doc}/download',headers=outsider['headers']), (404,))
        check(http.post(f'/documents/{doc}/share-department',headers=owner['headers'],json={'department_id':department}))
        assert check(http.get(f'/documents/{doc}/download',headers=recipient['headers'])).content==contents
        check(http.delete(f'/documents/{doc}/share-department/{department}',headers=owner['headers']))
        check(http.get(f'/documents/{doc}/download',headers=recipient['headers']), (404,))
        check(http.post(f'/documents/{doc}/share',headers=owner['headers'],json={'username':recipient['username']}))
        assert check(http.get(f'/documents/{doc}/download',headers=recipient['headers'])).content==contents
        check(http.delete(f'/documents/{doc}/share/{recipient["username"]}',headers=owner['headers']))
        check(http.get(f'/documents/{doc}/download',headers=recipient['headers']), (404,))
        assert len(check(http.get('/audit',headers=admin_headers)).json())>=1
        check(http.delete(f'/documents/{doc}',headers=owner['headers']))
        check(http.get(f'/documents/{doc}/download',headers=owner['headers']), (404,))
        print('PASSOU: login, departamentos, contas, upload, 2 réplicas, acessos negados, partilha, revogação, auditoria, eliminação.')
        print('NOTA: teste de failover exige parar um nó manualmente; ver README.')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',default='https://api:8000')
    ap.add_argument('--ca',default=str(ROOT/'certs/ca.pem'))
    ap.add_argument('--admin',default=None)
    args=ap.parse_args()
    admin=args.admin or input('Utilizador administrador: ')
    passwd=getpass('Palavra-passe do administrador: ')
    run(args.base,Path(args.ca),admin,passwd)

if __name__=='__main__':
    main()
