-- R4.2 Phase 3 (T013): analyst_turn needs three columns the turn service depends on that
-- 20260924000001 didn't anticipate — discovered during review, before this branch merges.
-- Purely additive: no existing column, data, or behaviour change.
--
-- idempotency_key: required on every insert (the API layer rejects a missing header before
-- calling the service), NOT NULL with a per-tenant uniqueness constraint so a replayed request
-- cannot create a second turn for the same key.
-- calculation: the stored CalculationDetail JSON (FR-004) — nullable, since the unsupported-
-- category refusal and the no-grounding-data answer both have no calculation to show.
-- is_unsupported: distinguishes an explicit "can't answer that yet" refusal (FR-002) from a
-- supported-but-ungrounded answer (FR-006) — both produce an answer_text but the two paths are
-- otherwise indistinguishable ex post without this flag.

alter table analyst_turn add column idempotency_key uuid not null;
alter table analyst_turn add column calculation jsonb;
alter table analyst_turn add column is_unsupported boolean not null default false;

alter table analyst_turn
  add constraint analyst_turn_idempotency_key_unique unique (tenant_id, idempotency_key);
