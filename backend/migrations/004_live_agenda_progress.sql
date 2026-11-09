-- Which agenda item an expert message was written for (NULL for answers to
-- the client and for client messages). An agenda item is complete only when
-- enough different experts have contributed to it (services/live_engine.py).
-- Existing transcripts keep NULL, and their stage counter is unchanged.
ALTER TABLE live_messages ADD COLUMN agenda_stage INTEGER;
