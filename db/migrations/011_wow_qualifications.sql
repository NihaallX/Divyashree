-- 011_wow_qualifications.sql
-- Divyasree WOW lead qualification fields

ALTER TABLE call_analysis
  ADD COLUMN IF NOT EXISTS intent_category   VARCHAR(20),
  ADD COLUMN IF NOT EXISTS budget_fit        VARCHAR(10),
  ADD COLUMN IF NOT EXISTS geography_fit     VARCHAR(10),
  ADD COLUMN IF NOT EXISTS timeline_fit      VARCHAR(10),
  ADD COLUMN IF NOT EXISTS overall_grade     VARCHAR(10),
  ADD COLUMN IF NOT EXISTS checkpoint_json   JSONB,
  ADD COLUMN IF NOT EXISTS next_action       VARCHAR(30);

CREATE INDEX IF NOT EXISTS idx_call_analysis_grade
  ON call_analysis(overall_grade);

CREATE INDEX IF NOT EXISTS idx_call_analysis_intent
  ON call_analysis(intent_category);
