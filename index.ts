import 'dotenv/config';
import express from 'express';
import oauthRoutes from './routes/oauth';
import webhookRoutes from './routes/webhook';
import adminRoutes from './routes/admin';
import { pollUnanswered } from './services/orchestrator';

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.get('/', (_req, res) => {
  res.send(`<h1>ML × Claude Automation</h1>
    <ul>
      <li><a href="/ml/connect">🔗 Conectar conta do Mercado Livre</a></li>
      <li><a href="/admin">📨 Painel de aprovação</a></li>
      <li>Healthcheck: /health</li>
    </ul>`);
});

app.get('/health', (_req, res) => res.json({ ok: true }));

app.use('/ml', oauthRoutes);
app.use('/ml', webhookRoutes); // POST /ml/webhooks
app.use('/admin', adminRoutes);

const port = Number(process.env.PORT || 3000);
app.listen(port, () => {
  console.log(`🚀 Server na porta ${port}`);
});

// Polling de segurança a cada 10 minutos (caso webhook falhe)
setInterval(() => {
  pollUnanswered().catch((e) => console.error('[poll-cron]', e.message));
}, 10 * 60 * 1000);
