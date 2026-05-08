import { query, queryOne } from '../lib/db';

const ML_API = 'https://api.mercadolibre.com';

export interface MLToken {
  seller_id: number;
  access_token: string;
  refresh_token: string;
  expires_at: Date;
  nickname?: string;
}

export interface MLQuestion {
  id: number;
  seller_id: number;
  text: string;
  status: string;
  date_created: string;
  item_id: string;
  from: { id: number };
}

export interface MLItem {
  id: string;
  title: string;
  price: number;
  available_quantity: number;
  condition: string;
  permalink: string;
  attributes?: Array<{ id: string; name: string; value_name: string | null }>;
  description?: string;
  shipping?: { free_shipping?: boolean };
}

// ============================================================
// OAUTH
// ============================================================

export function getAuthUrl(state: string): string {
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: process.env.ML_CLIENT_ID!,
    redirect_uri: process.env.ML_REDIRECT_URI!,
    state,
  });
  return `https://auth.mercadolivre.com.br/authorization?${params}`;
}

export async function exchangeCodeForToken(code: string): Promise<{
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user_id: number;
}> {
  const res = await fetch(`${ML_API}/oauth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: process.env.ML_CLIENT_ID!,
      client_secret: process.env.ML_CLIENT_SECRET!,
      code,
      redirect_uri: process.env.ML_REDIRECT_URI!,
    }),
  });
  if (!res.ok) throw new Error(`OAuth exchange failed: ${res.status} ${await res.text()}`);
  return res.json() as any;
}

async function refreshToken(token: MLToken): Promise<MLToken> {
  const res = await fetch(`${ML_API}/oauth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: process.env.ML_CLIENT_ID!,
      client_secret: process.env.ML_CLIENT_SECRET!,
      refresh_token: token.refresh_token,
    }),
  });
  if (!res.ok) throw new Error(`Refresh failed: ${res.status} ${await res.text()}`);
  const data = (await res.json()) as any;

  const newToken: MLToken = {
    seller_id: token.seller_id,
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: new Date(Date.now() + data.expires_in * 1000),
    nickname: token.nickname,
  };

  await query(
    `UPDATE ml_tokens SET access_token=$1, refresh_token=$2, expires_at=$3, updated_at=NOW()
     WHERE seller_id=$4`,
    [newToken.access_token, newToken.refresh_token, newToken.expires_at, newToken.seller_id],
  );
  return newToken;
}

export async function saveToken(t: {
  user_id: number;
  access_token: string;
  refresh_token: string;
  expires_in: number;
}): Promise<MLToken> {
  const expires_at = new Date(Date.now() + t.expires_in * 1000);

  // Buscar nickname do usuário
  let nickname: string | undefined;
  try {
    const userRes = await fetch(`${ML_API}/users/me`, {
      headers: { Authorization: `Bearer ${t.access_token}` },
    });
    if (userRes.ok) nickname = ((await userRes.json()) as any).nickname;
  } catch {}

  await query(
    `INSERT INTO ml_tokens (seller_id, access_token, refresh_token, expires_at, nickname)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (seller_id) DO UPDATE SET
       access_token=EXCLUDED.access_token,
       refresh_token=EXCLUDED.refresh_token,
       expires_at=EXCLUDED.expires_at,
       nickname=EXCLUDED.nickname,
       updated_at=NOW()`,
    [t.user_id, t.access_token, t.refresh_token, expires_at, nickname],
  );

  return {
    seller_id: t.user_id,
    access_token: t.access_token,
    refresh_token: t.refresh_token,
    expires_at,
    nickname,
  };
}

export async function getValidToken(seller_id: number): Promise<MLToken> {
  const token = await queryOne<MLToken>(
    `SELECT seller_id, access_token, refresh_token, expires_at, nickname
     FROM ml_tokens WHERE seller_id=$1`,
    [seller_id],
  );
  if (!token) throw new Error(`Sem token para seller ${seller_id}`);

  // Refresh se faltar menos de 5 minutos pra expirar
  const willExpireSoon = new Date(token.expires_at).getTime() - Date.now() < 5 * 60 * 1000;
  return willExpireSoon ? await refreshToken(token) : token;
}

// ============================================================
// API CALLS
// ============================================================

async function mlFetch(seller_id: number, path: string, init: RequestInit = {}): Promise<any> {
  const token = await getValidToken(seller_id);
  const res = await fetch(`${ML_API}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${token.access_token}`,
      'Content-Type': 'application/json',
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`ML API ${path} failed: ${res.status} ${body}`);
  }
  return res.json();
}

export async function getQuestion(seller_id: number, question_id: number): Promise<MLQuestion> {
  return mlFetch(seller_id, `/questions/${question_id}`);
}

export async function getItem(seller_id: number, item_id: string): Promise<MLItem> {
  return mlFetch(seller_id, `/items/${item_id}`);
}

export async function getItemDescription(seller_id: number, item_id: string): Promise<string> {
  try {
    const data = await mlFetch(seller_id, `/items/${item_id}/description`);
    return data.plain_text || '';
  } catch {
    return '';
  }
}

export async function postAnswer(
  seller_id: number,
  question_id: number,
  text: string,
): Promise<any> {
  return mlFetch(seller_id, '/answers', {
    method: 'POST',
    body: JSON.stringify({ question_id, text }),
  });
}

export async function listUnansweredQuestions(seller_id: number): Promise<MLQuestion[]> {
  const data = await mlFetch(
    seller_id,
    `/questions/search?seller_id=${seller_id}&status=UNANSWERED&limit=50`,
  );
  return data.questions || [];
}
