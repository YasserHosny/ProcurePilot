-- 20260821000030_value_proof_enums.sql
--
-- Reference enums for chunk 4.6 (006-value-proof-launch). No tenant data — just the vocabulary
-- the next migrations build on, same discipline as 20260819000022_matching_reference.sql.

do $$ begin
  create type saving_record_status as enum ('pending', 'verified');
exception when duplicate_object then null; end $$;

do $$ begin
  create type baseline_policy as enum ('last_paid', 'rolling_average_6m', 'none_available');
exception when duplicate_object then null; end $$;

do $$ begin
  create type purchase_delivery_result as enum (
    'ordered', 'partially_delivered', 'delivered', 'cancelled', 'disputed'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type export_job_status as enum ('queued', 'running', 'completed', 'failed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type export_format as enum ('xlsx', 'pdf');
exception when duplicate_object then null; end $$;

do $$ begin
  create type billing_account_status as enum ('active', 'past_due', 'cancelled');
exception when duplicate_object then null; end $$;

do $$ begin
  create type plan_status as enum ('active', 'archived');
exception when duplicate_object then null; end $$;

comment on type saving_record_status is
  'pending: recorded but not yet a defensible claim. verified: immutable from this point on
   (see 20260821000035_saving_record_immutability.sql). Never automatic — Constitution
   Principle III requires an explicit human transition. See research.md R1/R2.';
