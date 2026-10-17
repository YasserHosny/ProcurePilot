-- PUT /rfq/{id} (draft edit) is idempotent: the last applied Idempotency-Key is stored on the
-- RFQ so a retry after a lost response replays the result instead of deleting and recreating
-- every line/recipient and appending another audit event. Existing rfq RLS (creator-only
-- update) already covers the column; no policy change.
alter table rfq add column if not exists last_update_idempotency_key uuid;
