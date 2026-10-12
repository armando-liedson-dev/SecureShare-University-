# Alterações verificáveis em relação ao ZIP original

| Área | Antes | Nesta versão |
|---|---|---|
| Empacotamento | ZIP com `.venv`, `.env`, chave privada, dados e `.bak` | Fontes limpas + `.gitignore`/`.dockerignore`; segredos gerados localmente |
| Segurança do login | Argon2 e JWT | Argon2 e JWT mantidos + controlo de tentativas e auditoria de login |
| Transportes | HTTP interno sem TLS demonstrado | TLS local entre API e nós + TLS na entrada web; segredos independentes por nó |
| Organização | Uma API grande `main.py` | Rotas `auth`, `documents`, `admin`; serviços e configuração separados |
| Instituição | `admin`, `user` sem departamento | Departamentos, vínculo de funcionários, ACL por utilizador e departamento |
| IDs de armazenamento | Inteiros correspondentes a documentos | UUID hex de 128 bits, com compatibilidade para ficheiros legados |
| Upload | Escreve réplicas antes da inserção em BD, rollback perigoso | Regista intent `uploading` na BD, envia as duas cópias concorrentemente e confirma ambas, sem eliminação cega |
| Falhas parciais no upload | Órfãos possíveis sem estado | Upload pendente/visibilidade bloqueada; reconciliação com cópia íntegra |
| Eliminação | Apaga cópias antes de alterar BD | Tombstone `deleting` antes do pedido e apagamento idempotente |
| Réplica corrompida | Detecta hash mas não repara | Endpoint autenticado de reparação, bytes validados contra o hash esperado |
| Réplica ausente | Download alternativo apenas | Reparação periódica e manual com estados de réplica |
| Auditabilidade | Registos básicos | Falhas de login, partilhas por departamentos, reparação e paginação |
| Interface | Apenas API | Portal responsivo com login, documentos, ACL, administração e auditoria |
| Testes | Não havia testes incluídos | Pytest isolado + teste integrado executável no ambiente Docker |
| Execução | Configuração local manual | Docker Compose com PostgreSQL, API e dois nós; certificado gerado no bootstrap |
| Documentação | Não havia README | Guia de execução, endpoints, roteiro de defesa, limitações |

## Evidência da execução nesta sessão

- O código Python passou em `compileall`.
- O JavaScript da interface passou em `node --check`.
- O gerador de chaves e certificados TLS foi testado em diretório temporário (não foram incluídos segredos na entrega).
- Os testes isolados do `pytest` passaram: **19 verificações** na última execução.
- O ambiente usado para preparar a entrega **não dispõe de Docker nem de servidor PostgreSQL**. Portanto, os testes integrados e a demonstração real de failover ficam preparados para execução no computador do grupo, mas **não foram executados nesta sessão**.

## Questões em aberto antes da apresentação

1. Executar Docker Desktop e confirmar arranque real, sem erros, das quatro aplicações.
2. Executar `scripts/smoke_test.py`, registar saídas, tempos e capturas.
3. Testar falha e recuperação de um nó físico ou container e recolher evidências.
4. Rever com o docente se a demonstração em containers é suficiente ou se exige máquinas físicas separadas.
5. Caso exista base de dados original com documentos legítimos, fazer backup, testar migração num ambiente de ensaio e **não** instalar por cima sem validação.
6. Para utilização real, realizar auditoria externa e acrescentar backups, cifra em repouso, antivírus, gestão de certificados e políticas institucionais.
