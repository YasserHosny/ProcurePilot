-- 20260819000022_matching_reference.sql — task T005
--
-- Reference enums for matching and landed cost. No tenant data — just the vocabulary the next
-- migrations build on.

do $$ begin
  create type match_task_status as enum ('open', 'in_progress', 'resolved');
exception when duplicate_object then null; end $$;

do $$ begin
  create type match_task_priority as enum ('low', 'normal', 'high');
exception when duplicate_object then null; end $$;

do $$ begin
  create type match_task_reason as enum (
    'low_confidence', 'close_candidates', 'no_candidate', 'alias_conflict'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type match_decision_outcome as enum (
    'same_product', 'different_pack', 'different_variant', 'compatible_alternative',
    'no_match_new_product'
  );
exception when duplicate_object then null; end $$;

comment on type match_decision_outcome is
  'The outcome vocabulary a reviewer chooses from (spec.md FR-008) — never a bare accept/reject.';
