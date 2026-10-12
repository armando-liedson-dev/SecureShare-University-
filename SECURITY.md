# Segurança e ameaças — protótipo académico

**Objetivo de segurança:** impedir acesso não autorizado a documentos privados, limitar a exposição de segredos, identificar modificações de ficheiros e impedir entrega de cópias adulteradas.

| Ameaça da ficha do docente | Mitigação existente | Limitação |
|---|---|---|
| Leakage / Eavesdropping | JWT, ACL, HTTPS, sem acesso direto ao armazenamento | Conteúdo dos volumes não é cifrado em repouso |
| Masquerading | Argon2, autenticação por token, segredos distintos por nó | MFA ainda não implementado |
| Replaying | JWT com expiração/jti, logout com lista de revogação | Token roubado pode ser usado antes da revogação |
| Message tampering | HTTPS + SHA-256 do documento recuperado | SHA-256 sozinho não autentica o emissor; TLS e controlo de acesso são necessários |
| Tampering | Escrita imutável por UUID; reparação com conteúdo validado por hash | Credencial interna comprometida é ameaça de elevado impacto |
| Vandalism / DoS | Limite de upload, controlo de tentativa de login | Não há WAF, proteção DDoS nem cluster de API |
| Resource stealing | API interna protegida; nós não divulgam ficheiros sem segredo | Quotas por utilizador ainda não existem |
| Falha por omissão/crash | Replicação em dois nós e fallback de leitura | API e PostgreSQL continuam pontos únicos de falha |

## Regras obrigatórias de configuração

1. Nunca copiar `.env`, `keys/jwt_private.pem`, `certs/ca.key`, `certs/server.key` ou `storage/` para um ZIP público.
2. Substituir **todos os segredos da versão original**, porque foram incluídos no ZIP entregue à análise.
3. Usar apenas documentos e identidades fictícias em testes.
4. Nunca expor diretamente os nós e o PostgreSQL à internet.
5. O certificado autoassinado é apenas para laboratório, não para produção.
6. Tratar backups, gestão de certificados, varrimento antivírus, retenção, monitorização e legislação aplicável antes de qualquer implantação institucional real.

A validação das credenciais não garante autorização: a consulta do documento aplica uma política por recurso e por departamento, e a API nunca confia num ID isolado como prova de acesso.
