# Publicação do SecureShare no GitHub (Windows / VS Code)

> **Antes de qualquer `git push`**: mantenha `.env`, `keys/`, `certs/` gerados, `storage/` e credenciais fora do repositório. **Não publique ficheiros pessoais** de estudantes ou funcionários.

## 1. Criar o repositório

Na página **New repository** do GitHub:

- **Owner:** `armando-liedson-dev` (ou a organização/equipa acordada);
- **Repository name:** `secureshare-universitario`;
- **Description:** `Sistema distribuído para partilha segura de documentos universitários | FastAPI, PostgreSQL, Docker e replicação.`;
- **Visibility:** **Public**;
- **Add README:** **Off**;
- **Add .gitignore:** **None**;
- **Choose a license:** **None** por enquanto; discutir a licença com os colegas.

Clique em **Create repository**. Uma vez criado, copie a URL HTTPS do repositório.

## 2. Preparar a pasta certa no VS Code

Abra **Terminal → New Terminal**, na raiz que contém `app/`, `web/`, `scripts/`, `README.md`, `.gitignore` e `compose.yaml`.

> Se já tiver uma pasta do projecto com dados locais, **copie apenas os ficheiros públicos actualizados para essa pasta**; não substitua `.env`, chaves ou volumes. Pode também trabalhar numa pasta separada a partir do ZIP público preparado.

Verifique:

```powershell
git --version
Test-Path .\README.md
Test-Path .\.gitignore
Test-Path .\compose.yaml
```

## 3. Iniciar o Git e verificar se já existe um repositório

```powershell
git status
git remote -v
```

Se `git status` indicar **not a git repository**, prossiga com:

```powershell
git init
git branch -M main
```

Se a pasta já tiver Git, **não** repita `git init` ou altere a origem antes de confirmar onde aponta.

## 4. Rever o que vai ficar público

```powershell
git add .
git status --short
git diff --cached --name-only
```

**Interrompa o processo** se aparecerem quaisquer destes ficheiros (ou equivalentes):

- `.env` e outros ficheiros com segredos;
- `keys/jwt_private.pem`, `certs/ca.key`, `certs/server.key`, ou quaisquer chaves privadas;
- `storage/` com documentos carregados;
- documentos reais de estudantes e funcionários, logs privados, bases de dados exportadas ou passwords.

Também verifique os conteúdos dos ficheiros preparados para publicação, incluindo documentos Word e apresentações. O `.gitignore` não detecta senhas coladas dentro de ficheiros `.md`, `.py`, `.docx` ou `.pptx`.

Para ver se o Git está a ignorar os caminhos críticos:

```powershell
git check-ignore .env keys/jwt_private.pem certs/ca.key certs/server.key
```

**Se algum segredo já foi incluído num commit anterior**, removê-lo de um commit novo **não elimina o histórico**. É necessário revogar o segredo e limpar o histórico antes de publicar.

## 5. Fazer o primeiro commit e push

Só avance se a lista de ficheiros em `git diff --cached --name-only` estiver limpa.

```powershell
git commit -m "feat: publicar prototipo academico SecureShare"
git remote add origin https://github.com/armando-liedson-dev/secureshare-universitario.git
git push -u origin main
```

> Se o Git disser `remote origin already exists`, execute `git remote -v` e confirme antes de alterar a configuração. Se o username ou o nome do repositório forem diferentes, utilize a URL real que o GitHub mostrar no botão **Code**.

A autenticação do push é normalmente realizada através do navegador/Git Credential Manager ou de um token, conforme a configuração. **Não coloque passwords ou tokens directamente no URL remoto.**

## 6. Atualizações seguintes

```powershell
git status
git add .
git diff --cached --name-only
git commit -m "docs: actualizar relatorio e testes"
git push
```

## 7. Protecção adicional para um repositório público

- Defina quem da equipa pode fazer `push` directo na branch `main`;
- Considere activar regras de branch e revisões por pull request;
- Adicione uma licença **após** decisão da equipa (repositório público não concede automaticamente autorização de reutilização);
- Não publique credenciais de demonstração, tokens, chaves, dados pessoais, capturas com passwords nem ficheiros de certificados locais;
- Use **issues** e o ficheiro `TEST_RESULTS.md` para acompanhar os testes pendentes;
- A URL `https://localhost:8000` funciona apenas no computador com a aplicação em execução: **publicar no GitHub não coloca automaticamente o SecureShare online**.
