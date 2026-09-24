-- R4.2 Phase 5 (T028): analyst_turn needs an entities jsonb column so a follow-up
-- turn can read back the prior turn's resolved IntentEntities (supplier_id, product_id,
-- date_range_start, date_range_end) for context resolution (FR-008).
-- Nullable: existing turns and unsupported-category turns have no entities to store.

alter table analyst_turn add column entities jsonb;
