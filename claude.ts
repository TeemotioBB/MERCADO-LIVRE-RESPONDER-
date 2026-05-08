import Anthropic from '@anthropic-ai/sdk';
import type { MLItem } from './mercadolivre';

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const SYSTEM_PROMPT = `Você é um atendente experiente de uma loja no Mercado Livre.
Sua tarefa é responder perguntas de potenciais compradores sobre os anúncios.

REGRAS OBRIGATÓRIAS (políticas do Mercado Livre — violar dá punição na conta):
1. NUNCA inclua links externos, números de telefone, WhatsApp, e-mails ou qualquer canal fora do ML.
2. NUNCA direcione o comprador a comprar fora do Mercado Livre.
3. NUNCA prometa preços, descontos ou condições diferentes do que está no anúncio.
4. NUNCA invente informações que você não tem certeza. Se não souber, diga que vai verificar com a equipe.
5. NUNCA combine pagamento, envio ou retirada fora do fluxo do ML.

DIRETRIZES DE QUALIDADE:
- Tom: cordial, direto, profissional. Trate por "você". Sem firulas.
- Tamanho: o mais curto possível pra responder a pergunta. 1 a 3 frases idealmente.
- Use APENAS os dados do anúncio que eu te passar. Se a pergunta for sobre algo que não está nos dados, responda que vai verificar.
- Se a pergunta for absurda, ofensiva ou claramente não relacionada ao produto, responda educadamente pedindo mais detalhes.
- Não use emojis a não ser que combine com o tom do anúncio.
- Não comece com "Olá!" toda vez — varie ou vá direto à resposta.

FORMATO DE SAÍDA (JSON estrito, sem markdown, sem backticks):
{
  "answer": "texto da resposta que será publicada",
  "confidence": "high" | "medium" | "low",
  "reasoning": "breve explicação interna de como chegou na resposta (não vai pro comprador)",
  "needs_human": false | true
}

- confidence "high": resposta direta com base nos dados do anúncio
- confidence "medium": inferência razoável mas não 100% certa
- confidence "low" ou needs_human=true: pergunta exige info que você não tem (estoque em tempo real, prazo específico, foto adicional, customização). Nesses casos responda algo neutro como "Vou verificar com a equipe e te retorno em breve" e marque needs_human=true.`;

export interface DraftResult {
  answer: string;
  confidence: 'high' | 'medium' | 'low';
  reasoning: string;
  needs_human: boolean;
}

export async function generateDraft(
  question: string,
  item: MLItem,
  description: string,
): Promise<DraftResult> {
  // Atributos relevantes do produto em formato legível
  const attributes = (item.attributes || [])
    .filter((a) => a.value_name)
    .map((a) => `- ${a.name}: ${a.value_name}`)
    .join('\n');

  const userPrompt = `DADOS DO ANÚNCIO
Título: ${item.title}
Preço: R$ ${item.price}
Estoque disponível: ${item.available_quantity}
Condição: ${item.condition === 'new' ? 'Novo' : 'Usado'}
Frete grátis: ${item.shipping?.free_shipping ? 'Sim' : 'Não'}
Link: ${item.permalink}

ATRIBUTOS DO PRODUTO:
${attributes || '(nenhum atributo cadastrado)'}

DESCRIÇÃO DO ANÚNCIO:
${description.slice(0, 2000) || '(sem descrição)'}

PERGUNTA DO COMPRADOR:
"${question}"

Responda em JSON estrito conforme o formato definido.`;

  const response = await anthropic.messages.create({
    // Sonnet 4.6 é o sweet spot pra atendimento: rápido, barato e respostas com qualidade.
    // Se quiser respostas mais elaboradas, troque por 'claude-opus-4-7'.
    // Se quiser mais barato ainda pra muito volume, 'claude-haiku-4-5'.
    model: 'claude-sonnet-4-6',
    max_tokens: 1024,
    system: SYSTEM_PROMPT,
    messages: [{ role: 'user', content: userPrompt }],
  });

  const textBlock = response.content.find((b) => b.type === 'text');
  if (!textBlock || textBlock.type !== 'text') throw new Error('Resposta sem texto');

  // Tira possíveis backticks/markdown caso o modelo escorregue
  const cleaned = textBlock.text
    .replace(/^```json\s*/i, '')
    .replace(/^```\s*/i, '')
    .replace(/```\s*$/i, '')
    .trim();

  const parsed = JSON.parse(cleaned) as DraftResult;
  return parsed;
}
