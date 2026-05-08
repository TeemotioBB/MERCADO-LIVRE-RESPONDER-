import { query, queryOne } from '../lib/db';
import * as ML from './mercadolivre';
import { generateDraft } from './claude';

/** Processa uma pergunta nova: busca item, gera rascunho e salva. */
export async function processQuestion(question_id: number): Promise<void> {
  console.log(`[process] Q${question_id} iniciando...`);

  // Pega o seller_id de qualquer token cadastrado.
  // Para multi-seller você precisaria descobrir o seller pela pergunta primeiro
  // (mas a API /questions/{id} já volta o seller_id, então usamos isso).
  const anyToken = await queryOne<{ seller_id: number }>(
    `SELECT seller_id FROM ml_tokens LIMIT 1`,
  );
  if (!anyToken) {
    console.warn('[process] Nenhum token cadastrado, pulando');
    return;
  }

  // Busca a pergunta no ML
  const q = await ML.getQuestion(anyToken.seller_id, question_id);

  // Se não for UNANSWERED (já foi respondida ou foi deletada), só atualiza status
  if (q.status !== 'UNANSWERED') {
    await query(
      `UPDATE questions SET ml_status=$1, status='skipped', updated_at=NOW() WHERE id=$2`,
      [q.status, question_id],
    );
    console.log(`[process] Q${question_id} status=${q.status}, pulando`);
    return;
  }

  // Busca dados do item
  const item = await ML.getItem(q.seller_id, q.item_id);
  const description = await ML.getItemDescription(q.seller_id, q.item_id);

  // Insere/atualiza pergunta
  await query(
    `INSERT INTO questions (id, seller_id, item_id, item_title, item_price,
                            question_text, question_date, ml_status, status)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending')
     ON CONFLICT (id) DO UPDATE SET
       item_title=EXCLUDED.item_title, item_price=EXCLUDED.item_price,
       ml_status=EXCLUDED.ml_status, updated_at=NOW()`,
    [q.id, q.seller_id, q.item_id, item.title, item.price,
     q.text, q.date_created, q.status],
  );

  // Gera rascunho com Claude
  try {
    const draft = await generateDraft(q.text, item, description);
    await query(
      `UPDATE questions SET draft_answer=$1, draft_reasoning=$2, status='drafted', updated_at=NOW()
       WHERE id=$3`,
      [draft.answer, `${draft.confidence} | needs_human=${draft.needs_human} | ${draft.reasoning}`, q.id],
    );
    console.log(`[process] Q${question_id} rascunho gerado (${draft.confidence})`);
  } catch (err: any) {
    await query(
      `UPDATE questions SET status='failed', error=$1, updated_at=NOW() WHERE id=$2`,
      [err.message, q.id],
    );
    console.error(`[process] Q${question_id} falhou:`, err.message);
  }
}

/** Aprova um rascunho: posta no ML e marca como enviado. */
export async function approveAnswer(question_id: number, edited_text?: string): Promise<void> {
  const q = await queryOne<{
    seller_id: number;
    draft_answer: string;
    status: string;
  }>(`SELECT seller_id, draft_answer, status FROM questions WHERE id=$1`, [question_id]);

  if (!q) throw new Error('Pergunta não encontrada');
  if (q.status === 'sent') throw new Error('Já foi respondida');

  const finalText = (edited_text ?? q.draft_answer).trim();
  if (!finalText) throw new Error('Resposta vazia');

  try {
    await ML.postAnswer(q.seller_id, question_id, finalText);
    await query(
      `UPDATE questions SET final_answer=$1, status='sent', updated_at=NOW() WHERE id=$2`,
      [finalText, question_id],
    );
  } catch (err: any) {
    await query(
      `UPDATE questions SET status='failed', error=$1, updated_at=NOW() WHERE id=$2`,
      [err.message, question_id],
    );
    throw err;
  }
}

/** Polling: busca perguntas não respondidas direto na API (backup do webhook). */
export async function pollUnanswered(): Promise<void> {
  const tokens = await query<{ seller_id: number }>(`SELECT seller_id FROM ml_tokens`);
  for (const { seller_id } of tokens) {
    try {
      const questions = await ML.listUnansweredQuestions(seller_id);
      for (const q of questions) {
        const exists = await queryOne(`SELECT id FROM questions WHERE id=$1`, [q.id]);
        if (!exists) {
          await processQuestion(q.id);
        }
      }
    } catch (err: any) {
      console.error(`[poll] Erro no seller ${seller_id}:`, err.message);
    }
  }
}
