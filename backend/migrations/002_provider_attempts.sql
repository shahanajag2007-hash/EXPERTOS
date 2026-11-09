-- Record every provider tried for one AI call, so fallback behaviour is
-- visible: JSON list of {"provider", "model", "category", "ms", "skipped"}
-- in the order they were tried. Contains no request or response text.
ALTER TABLE ai_calls ADD COLUMN provider_attempts TEXT;
