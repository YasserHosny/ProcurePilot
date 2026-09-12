-- 20260912000005_purchase_request_idempotency_key.sql
--
-- POST /requests already accepts an `Idempotency-Key` header (see the contract), but until now
-- the router discarded it — a real, systemic gap flagged during 009-mobile-app-mvp review
-- (PR #12, chatgpt-codex-connector): when a response to a create-request call is lost, a client
-- retry with the same key created a SECOND draft instead of returning the original, violating
-- FR-011 and blocking any future offline-queue replay guarantee for purchase requests. This is
-- the exact fix `low_stock_report` already has for the same class of problem
-- (20260912000002_low_stock_report.sql) — a nullable idempotency_key column plus a partial
-- unique index, so the guarantee is enforced by the database, not merely assumed by the client.

alter table purchase_request add column if not exists idempotency_key uuid;

-- Partial: two genuinely separate drafts with no key (today's normal case, and every existing
-- caller) never collide; a replayed create with the SAME key is rejected here, and the service
-- layer reads the existing row back instead of inserting a duplicate — exactly the low_stock_report
-- idiom, applied to the table that originally needed it first.
create unique index if not exists purchase_request_idempotency_key_idx
  on purchase_request (tenant_id, idempotency_key)
  where idempotency_key is not null;
