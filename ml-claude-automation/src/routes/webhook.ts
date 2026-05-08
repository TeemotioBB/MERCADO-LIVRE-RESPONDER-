import { Router } from 'express';
import { query } from '../lib/db';
import { processQuestion } from '../services/orchestrator';

const router = Router();

/**
 * Webhook do ML.
 * IMPORTANTE: tem que responder 200 RAPIDAMENTE (em poucos segundos),
 * senão o ML reenvia. Por isso a gente só registra e processa em background.
 */
router.post('/webhooks', async (req, res) => {
  const body = req.body;
  console.log('[webhook]', JSON.stringify(body));

  // Resposta IMEDIATA pro ML
  res.status(200).send('ok');

  // Processamento em background (fire and forget)
  setImmediate(async () => {
    try {
      // Idempotência: só processa cada notification_id uma vez
      const existing = await query(
        `SELECT id FROM webhook_log WHERE notification_id=$1`,
        [body._id || body.id || `${body.topic}-${body.resource}-${body.sent}`],
      );
      if (existing.length > 0) return;

      await query(
        `INSERT INTO webhook_log (notification_id, topic, resource, user_id, raw_body)
         VALUES ($1, $2, $3, $4, $5)
         ON CONFLICT (notification_id) DO NOTHING`,
        [
          body._id || body.id || `${body.topic}-${body.resource}-${body.sent}`,
          body.topic,
          body.resource,
          body.user_id,
          body,
        ],
      );

      // Tópico de pergunta: resource = "/questions/{id}"
      if (body.topic === 'questions' && body.resource) {
        const match = String(body.resource).match(/\/questions\/(\d+)/);
        if (match) {
          await processQuestion(Number(match[1]));
        }
      }
    } catch (err: any) {
      console.error('[webhook] processamento falhou:', err.message);
    }
  });
});

export default router;
