import { readFileSync } from 'fs';
import { join } from 'path';
import { pool } from '../lib/db';
import 'dotenv/config';

async function migrate() {
  const schemaPath = join(__dirname, 'schema.sql');
  const sql = readFileSync(schemaPath, 'utf-8');
  await pool.query(sql);
  console.log('✅ Migração concluída');
  await pool.end();
}

migrate().catch((err) => {
  console.error('❌ Erro na migração:', err);
  process.exit(1);
});
