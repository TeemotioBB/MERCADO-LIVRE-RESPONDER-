# ML × Claude Automation

Recebe perguntas do Mercado Livre via webhook, gera rascunhos de resposta com Claude e mostra um painel pra você aprovar antes de publicar.

## Stack
- Node.js 20 + TypeScript + Express
- PostgreSQL (Railway)
- Anthropic SDK (Claude)
- API do Mercado Livre

## Deploy no Railway — passo a passo

### 1. Suba o código pro GitHub
```bash
cd ml-claude-automation
git init
git add .
git commit -m "first commit"
git remote add origin git@github.com:seu_usuario/ml-claude-automation.git
git push -u origin main
```

### 2. Crie o projeto no Railway
- Acesse https://railway.app → New Project → Deploy from GitHub repo
- Selecione esse repo
- O Railway detecta Node automaticamente (Nixpacks)

### 3. Adicione um Postgres
- Dentro do projeto: `+ New` → `Database` → `Add PostgreSQL`
- O Railway cria a variável `DATABASE_URL` e linka automaticamente ao seu serviço web

### 4. Configure as variáveis de ambiente
No serviço web, aba **Variables**, adicione:

```
ML_CLIENT_ID=...                      (do app no painel do ML)
ML_CLIENT_SECRET=...                  (do app no painel do ML)
ML_REDIRECT_URI=https://SEU-DOMINIO.up.railway.app/ml/callback
ANTHROPIC_API_KEY=sk-ant-...          (de console.anthropic.com)
APP_BASE_URL=https://SEU-DOMINIO.up.railway.app
ADMIN_PASSWORD=alguma_senha_forte
```

> Para descobrir seu domínio: aba **Settings** do serviço web → **Networking** → **Generate Domain**.

### 5. Configure o app no Mercado Livre
Na tela de criação do app (https://developers.mercadolivre.com.br/devcenter):

| Campo | Valor |
|---|---|
| URI de redirect | `https://SEU-DOMINIO.up.railway.app/ml/callback` |
| Fluxos OAuth | ✅ Authorization Code, ✅ Refresh Token |
| PKCE | desativado (a app é confidencial, server-side) |
| Negócios | Mercado Livre |
| Permissões → Usuários | Leitura e escrita |
| Permissões → Comunicações pré e pós-vendas | Leitura e escrita |
| Permissões → Publicação e sincronização | Leitura (opcional, melhora contexto do anúncio) |
| URL de notificações | `https://SEU-DOMINIO.up.railway.app/ml/webhooks` |
| Tópicos | ✅ `questions` |

### 6. Conecte sua conta do ML
- Acesse `https://SEU-DOMINIO.up.railway.app/`
- Clique em **Conectar conta do Mercado Livre**
- Autorize o app
- Tokens ficam salvos no banco

### 7. Use o painel de aprovação
- Acesse `https://SEU-DOMINIO.up.railway.app/admin`
- Login: `admin` / sua `ADMIN_PASSWORD`
- Cada pergunta nova aparece com o rascunho do Claude
- Você edita se quiser, clica **Aprovar e enviar**

## Como rodar localmente

```bash
npm install
cp .env.example .env       # edita com seus valores
# precisa de um postgres rodando local ou apontar pro do Railway
npm run db:migrate
npm run dev
```

Para receber webhooks localmente, use ngrok: `ngrok http 3000`. Aí o ML_REDIRECT_URI e a URL de webhook viram o domínio do ngrok.

## Estrutura

```
src/
  index.ts                    entry point
  db/
    schema.sql                schema do banco
    migrate.ts                roda o schema
  lib/
    db.ts                     pool do pg
  services/
    mercadolivre.ts           OAuth + chamadas de API + refresh automático
    claude.ts                 prompt + geração de rascunhos
    orchestrator.ts           cola tudo
  routes/
    oauth.ts                  /ml/connect e /ml/callback
    webhook.ts                /ml/webhooks
    admin.ts                  /admin (painel)
```

## Próximos passos

- **Modo automático para confiança alta**: depois de validar uns 50 rascunhos, dá pra mudar `processQuestion` pra postar direto quando `confidence === 'high' && !needs_human`.
- **Notificação por e-mail/Telegram quando chegar pergunta nova** pra você não precisar ficar olhando o painel.
- **Fine-tuning do prompt** com FAQs específicas do seu negócio (prazo de envio padrão, política de troca, etc) — adicionar no `SYSTEM_PROMPT` em `services/claude.ts`.
- **Multi-conta**: o schema já suporta vários `seller_id`, só ajustar a UI.
