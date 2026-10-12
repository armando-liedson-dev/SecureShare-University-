# Verificação técnica nesta entrega (11/10/2026)

## Testes executados nesta sessão

| Verificação | Resultado | Natureza |
|---|---|---|
| Análise sintática dos ficheiros Python | Aprovada | Estática |
| Validação sintática do JavaScript (`node --check`) | Aprovada | Estática |
| Geração de segredos e certificado TLS em ambiente temporário | Aprovada | Execução de bootstrap |
| API `/openapi.json`: verificação dos endpoints | Aprovada | TestClient isolado |
| Respostas da API: cabeçalhos de segurança | Aprovada | TestClient isolado |
| Portal HTML servido pela aplicação | Aprovada | TestClient isolado |
| Argon2: hash e verificação de password | Aprovada | Unitário |
| JWT RS256: criação, leitura e deteção de adulteração | Aprovada | Unitário |
| Nó de armazenamento: saúde, autenticação negativa e positiva | Aprovada | TestClient isolado |
| Nó: escrita, leitura, idempotência, conflito e eliminação | Aprovada | TestClient isolado |
| Nó: bloqueio de nomes de ficheiro inválidos | Aprovada | TestClient isolado |
| Nó: limite de upload | Aprovada | TestClient isolado |
| Nó: reparação de réplica corrompida sob hash esperado | Aprovada | TestClient isolado |
| Reconciliação: reparar um nó a partir de outro íntegro | Aprovada | Simulação controlada |
| Reconciliação: não reproduzir dados sem uma cópia verificada | Aprovada | Simulação controlada |

**Total de casos pytest:** 19 aprovados.

## Testes ainda não executados

**Não houve servidor PostgreSQL nem Docker disponíveis nesta sessão.** Por isso, **não estão comprovados**: arranque de `docker compose`, integração real API/PostgreSQL, login em base de dados, execução conjunta dos nós HTTPS, integridade real sob failover, operação do portal num navegador real nem fluxo de upload/delete distribuído sob concorrência real.

Para validar estes aspetos, iniciar a infraestrutura no computador do grupo e executar:

```text
docker compose up --build -d
docker compose exec api python -m app.create_admin
docker compose exec api python scripts/seed_demo.py
docker compose exec api python scripts/smoke_test.py --base https://api:8000
```

Guardar log de resultados, capturas de ecrã e métricas de desempenho antes de afirmar que a solução foi demonstrada integralmente.
