import { Router } from 'express';
import { randomBytes } from 'crypto';
import * as ML from '../services/mercadolivre';

const router = Router();
const stateStore = new Set<string>(); // simples, em memória

router.get('/connect', (_req, res) => {
  const state = randomBytes(16).toString('hex');
  stateStore.add(state);
  setTimeout(() => stateStore.delete(state), 10 * 60 * 1000);
  res.redirect(ML.getAuthUrl(state));
});

router.get('/callback', async (req, res) => {
  const { code, state, error } = req.query;
  if (error) return res.status(400).send(`Erro do ML: ${error}`);
  if (!code || typeof code !== 'string') return res.status(400).send('Sem code');
  if (!state || !stateStore.has(state as string)) return res.status(400).send('State inválido');
  stateStore.delete(state as string);

  try {
    const tokens = await ML.exchangeCodeForToken(code);
    const saved = await ML.saveToken(tokens);
    res.send(
      `<h2>✅ Conta conectada</h2>
       <p>Seller: <b>${saved.nickname || saved.seller_id}</b></p>
       <p><a href="/admin">Ir para o painel de aprovação</a></p>`,
    );
  } catch (err: any) {
    res.status(500).send(`Erro: ${err.message}`);
  }
});

export default router;
