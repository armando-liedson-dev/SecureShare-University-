# Guia de defesa académica — SecureShare

## Questão central e tese

**Pergunta:** Como desenvolver um sistema distribuído que permita partilhar documentos entre departamentos universitários de forma segura, rastreável e com recuperação perante a falha de um nó de armazenamento?

**Tese testável:** Uma arquitectura que combina APIs autenticadas, permissões por utilizador/departamento, duas réplicas independentes e verificação SHA-256 pode continuar a disponibilizar um documento se um nó estiver indisponível, desde que o outro nó e a infraestrutura de coordenação continuem operacionais.

## Conteúdo recomendado da apresentação (12 slides)

1. **Título, equipa e tema** — SecureShare, cenário de universidade.
2. **Contexto** — Registo Académico, Direcção, RH e Finanças; circulação de pautas e relatórios.
3. **Problema** — documentos dispersos, acessos inadequados, ausência de rastreabilidade, dependência de um nó.
4. **Questão de investigação e objetivos** — resultado a alcançar e testar.
5. **Fundamentação de Sistemas Distribuídos** — nós, mensagens, client-server, transparência e falhas.
6. **Arquitectura** — portal, API, PostgreSQL, Node A, Node B; portas, TLS e ACL.
7. **Modelo de dados** — users, departments, documents, shares, replicas, audit.
8. **Segurança** — Argon2, JWT RS256, autenticação por nó, HTTPS, controlo por recurso, hash.
9. **Replicação e consistência** — estados uploading/available/deleting/deleted, escrita idempotente, reparação.
10. **Demonstração** — partilha de pauta, acesso autorizado e acesso negado, revogação.
11. **Demonstração de falha** — parar Node A, download via Node B, voltar e re-replicar.
12. **Resultados dos testes, limitações e conclusão** — tabelar o que passou/fracassou e responder à pergunta.

## Matriz de rastreabilidade

| Requisito | Onde está no código | Como demonstrar | Evidência a guardar |
|---|---|---|---|
| Autenticação | `app/auth.py`, `app/security.py` | Login válido/inválido | Captura + HTTP 200/401 |
| Perfil institucional | `app/admin.py`, `app/db.py` | Consultar `/auth/me` | Departamento devolvido |
| ACL individual | `app/documents.py` | Partilhar e revogar | 200 após partilha / 404 após revogação |
| ACL departamental | `app/documents.py` | Autorizar Direcção | Conta de Direcção acessa; RH não |
| Distribuição real | `app/storage_client.py` | Ver serviços separados | `docker compose ps` + logs |
| Replicação | `app/documents.py` | Upload com nós A e B | `/admin/replicas` |
| Integridade | `app/storage_client.py` | Alterar cópia de teste | Hash rejeitado + fallback |
| Tolerância a falhas | `app/documents.py` | Parar Node A | Download via Node B |
| Reparação | `app/admin.py` | Reiniciar A e reconciliar | Dois estados `available` |
| Auditoria | `app/common.py` | Consultar `/audit` | Eventos de acesso e partilha |
| Consistência | `app/documents.py` | Eliminação com nó falhado | `202`, documento oculto e conclusão posterior |

## Roteiro de demonstração

**Preparação:** iniciar os quatro containers. Criar administrador, quatro departamentos e utilizadores fictícios. Preparar um PDF fictício e um terminal Docker aberto. Confirmar que os nós A/B respondem via HTTPS.

1. Entrar como `registo`. Enviar `pauta-ficticia.pdf` e anotar ID/hash.
2. Entrar como `rh`. Confirmar documento não visível, download devolve 404.
3. Entrar como `registo`. Partilhar com `Direcção Pedagógica`.
4. Entrar como `direccao`. Descarregar e mostrar ficheiro idêntico.
5. Voltar a `registo`. Revogar a partilha. Nova tentativa de `direccao` devolve 404.
6. Partilhar novamente; parar `node_a` (`docker compose stop node_a`) e demonstrar fallback de download.
7. Reiniciar `node_a`, invocar reconciliação e consultar o estado das duas réplicas.
8. Mostrar o registo de auditoria com um administrador.

## Resultados que devem ser medidos (não inventar)

| Métrica | Medição sugerida |
|---|---|
| Tempo de upload | Medir do pedido até à resposta HTTP 201 |
| Tempo de download sem falha | Medir 10 downloads do mesmo ficheiro e calcular média |
| Tempo de download com Node A inativo | Medir 10 downloads com fallback para B |
| Disponibilidade na falha isolada | N.º downloads concluídos / total de tentativas durante teste |
| Tempo de recuperação da redundância | Reinício do Node A até ambos os estados `available` |
| Integridade | Comparar SHA-256 antes/depois e contar adulterações detectadas |
| Eficácia da autorização | Nº tentativas negadas correctamente / total de tentativas indevidas |

**Importante:** o controlo de confidencialidade não implica que os dados de estudantes reais possam ser colocados no sistema. O protótipo utiliza conteúdo fictício.

## Estrutura recomendada do relatório científico

Título, autores, resumo, palavras-chave, introdução, problema, objetivos, fundamentação teórica, metodologia, arquitectura, implementação, resultados de testes, discussão, limitações, conclusão e referências bibliográficas. Utilizar os slides do docente como enquadramento teórico e referenciar bibliografia científica devidamente consultada. Não apresentar capturas ou métricas não obtidas.

## Limitações a assumir na defesa

O projeto resiste à falha de um nó de armazenamento, **não** à falha da API ou da base de dados. O protótipo não inclui cifra em repouso, verificação antivírus, backups externos nem implantação multi-site. Uma falha simultânea nos dois nós impede recuperar um documento. Um certificado de CA local não equivale a um certificado válido para implantação pública.
