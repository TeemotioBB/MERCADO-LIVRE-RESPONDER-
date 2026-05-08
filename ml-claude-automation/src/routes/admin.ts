import { Router } from 'express';
import { query } from '../lib/db';
import { approveAnswer, pollUnanswered } from '../services/orchestrator';

const router = Router();

// Auth básica de uma senha só
router.use((req, res, next) => {
  const auth = req.headers.authorization;
  const expected = 'Basic ' + Buffer.from(`admin:${process.env.ADMIN_PASSWORD}`).toString('base64');
  if (auth !== expected) {
    res.set('WWW-Authenticate', 'Basic realm="ml-admin"');
    return res.status(401).send('Auth requerida');
  }
  next();
});

router.get('/', async (_req, res) => {
  const pending = await query<any>(
    `SELECT id, item_id, item_title, item_price, question_text,
            draft_answer, draft_reasoning, status, error, created_at
     FROM questions
     WHERE status IN ('pending', 'drafted', 'failed')
     ORDER BY created_at DESC LIMIT 50`,
  );
  const recent = await query<any>(
    `SELECT id, item_title, question_text, final_answer, updated_at
     FROM questions WHERE status='sent'
     ORDER BY updated_at DESC LIMIT 10`,
  );

  res.send(renderPage(pending, recent));
});

router.post('/approve/:id', async (req, res) => {
  const id = Number(req.params.id);
  const edited = req.body.text as string | undefined;
  try {
    await approveAnswer(id, edited);
    res.redirect('/admin');
  } catch (err: any) {
    res.status(500).send(`Erro: ${err.message}<br><a href="/admin">voltar</a>`);
  }
});

router.post('/skip/:id', async (req, res) => {
  await query(`UPDATE questions SET status='skipped', updated_at=NOW() WHERE id=$1`, [Number(req.params.id)]);
  res.redirect('/admin');
});

router.post('/poll', async (_req, res) => {
  await pollUnanswered();
  res.redirect('/admin');
});

function escapeHtml(s: string | null | undefined): string {
  if (!s) return '';
  return s.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!,
  );
}

function renderPage(pending: any[], recent: any[]): string {
  return `<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Painel ML</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:1rem;background:#f7f7f7}
  h1{margin-top:0}
  .card{background:#fff;padding:1rem 1.25rem;margin-bottom:1rem;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  .meta{color:#666;font-size:.85rem;margin-bottom:.5rem}
  .question{background:#f0f4ff;padding:.75rem;border-radius:4px;margin:.5rem 0}
  textarea{width:100%;min-height:80px;font-family:inherit;font-size:1rem;padding:.5rem;border:1px solid #ccc;border-radius:4px;box-sizing:border-box}
  button{padding:.5rem 1rem;border:0;border-radius:4px;cursor:pointer;font-size:.9rem;margin-right:.5rem}
  .btn-approve{background:#00a650;color:#fff}
  .btn-skip{background:#aaa;color:#fff}
  .btn-poll{background:#3483fa;color:#fff;margin-bottom:1rem}
  .reasoning{font-size:.8rem;color:#888;margin-top:.25rem}
  .error{background:#fee;border-left:3px solid #c33;padding:.5rem;margin:.5rem 0}
  .status-failed{border-left:4px solid #c33}
  .status-pending{border-left:4px solid #fa3}
  .status-drafted{border-left:4px solid #00a650}
  details{margin-top:1.5rem}
  .recent{font-size:.85rem;color:#555}
</style></head><body>
<h1>📨 Perguntas do Mercado Livre</h1>

<form method="POST" action="/admin/poll" style="display:inline">
  <button class="btn-poll" type="submit">🔄 Buscar perguntas pendentes agora</button>
</form>

${pending.length === 0 ? '<p>Nenhuma pergunta pendente. ✅</p>' : ''}

${pending.map((q) => `
  <div class="card status-${q.status}">
    <div class="meta">
      <b>${escapeHtml(q.item_title)}</b> · R$ ${q.item_price} ·
      <a href="https://www.mercadolivre.com.br/anuncio/${q.item_id}" target="_blank">${q.item_id}</a> ·
      ${new Date(q.created_at).toLocaleString('pt-BR')} · status: ${q.status}
    </div>
    <div class="question">❓ ${escapeHtml(q.question_text)}</div>

    ${q.error ? `<div class="error">⚠️ ${escapeHtml(q.error)}</div>` : ''}

    ${q.draft_answer ? `
      <form method="POST" action="/admin/approve/${q.id}">
        <textarea name="text">${escapeHtml(q.draft_answer)}</textarea>
        <div class="reasoning">🤖 ${escapeHtml(q.draft_reasoning)}</div>
        <div style="margin-top:.5rem">
          <button class="btn-approve" type="submit">✓ Aprovar e enviar</button>
        </div>
      </form>
      <form method="POST" action="/admin/skip/${q.id}" style="display:inline">
        <button class="btn-skip" type="submit">Pular</button>
      </form>
    ` : `<p><i>Rascunho ainda não gerado.</i></p>`}
  </div>
`).join('')}

<details>
  <summary>Últimas respondidas (${recent.length})</summary>
  <div class="recent">
  ${recent.map((q) => `
    <div class="card">
      <div class="meta">${escapeHtml(q.item_title)} · ${new Date(q.updated_at).toLocaleString('pt-BR')}</div>
      <div>❓ ${escapeHtml(q.question_text)}</div>
      <div>✅ ${escapeHtml(q.final_answer)}</div>
    </div>
  `).join('')}
  </div>
</details>
</body></html>`;
}

export default router;
