-- Tokens OAuth do Mercado Livre (um por seller)
CREATE TABLE IF NOT EXISTS ml_tokens (
  seller_id BIGINT PRIMARY KEY,
  access_token TEXT NOT NULL,
  refresh_token TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  nickname TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Perguntas + rascunhos gerados pelo Claude
CREATE TABLE IF NOT EXISTS questions (
  id BIGINT PRIMARY KEY,                    -- question_id do ML
  seller_id BIGINT NOT NULL,
  item_id TEXT NOT NULL,
  item_title TEXT,
  item_price NUMERIC,
  question_text TEXT NOT NULL,
  question_date TIMESTAMPTZ NOT NULL,
  draft_answer TEXT,                        -- rascunho do Claude
  draft_reasoning TEXT,                     -- por que o Claude respondeu assim
  final_answer TEXT,                        -- o que foi efetivamente postado
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | drafted | approved | sent | failed | skipped
  ml_status TEXT,                           -- status no ML (UNANSWERED, ANSWERED, etc)
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
CREATE INDEX IF NOT EXISTS idx_questions_seller ON questions(seller_id);

-- Log dos webhooks recebidos (pra debug e idempotência)
CREATE TABLE IF NOT EXISTS webhook_log (
  id BIGSERIAL PRIMARY KEY,
  notification_id TEXT UNIQUE,
  topic TEXT NOT NULL,
  resource TEXT,
  user_id BIGINT,
  raw_body JSONB,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed BOOLEAN NOT NULL DEFAULT FALSE
);
