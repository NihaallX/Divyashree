#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP_SQL="$ROOT_DIR/db/neon_setup.sql"

if [[ ! -f "$SETUP_SQL" ]]; then
  echo "ERROR: missing setup SQL at $SETUP_SQL"
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set"
  echo "Example: export DATABASE_URL='postgresql://USER:PASSWORD@HOST/DB?sslmode=require'"
  exit 1
fi

PSQL_BIN="${PSQL_BIN:-psql}"

echo "Applying Neon setup SQL..."
"$PSQL_BIN" "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$SETUP_SQL"

echo "Running verification checks..."
"$PSQL_BIN" "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'tables' AS check_name,
       CASE WHEN COUNT(*) = 11 THEN 'ok' ELSE 'fail' END AS status,
       COUNT(*) AS count
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'users','agents','calls','transcripts','call_analysis','templates',
    'knowledge_base','auth_tokens','contacts','bulk_campaigns','campaign_contacts'
  );

SELECT 'scheduled_events_table' AS check_name,
       CASE WHEN EXISTS (
         SELECT 1 FROM information_schema.tables
         WHERE table_schema='public' AND table_name='scheduled_events'
       ) THEN 'ok' ELSE 'fail' END AS status;

SELECT 'wow_columns' AS check_name,
       CASE WHEN COUNT(*) = 7 THEN 'ok' ELSE 'fail' END AS status,
       COUNT(*) AS count
FROM information_schema.columns
WHERE table_name = 'call_analysis'
  AND column_name IN (
    'intent_category','budget_fit','geography_fit','timeline_fit',
    'overall_grade','checkpoint_json','next_action'
  );

SELECT 'priya_seed' AS check_name,
       CASE WHEN EXISTS (
          SELECT 1 FROM agents WHERE name = 'Priya'
       ) THEN 'ok' ELSE 'fail' END AS status;
SQL

echo "Neon setup complete."
