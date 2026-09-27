-- 20260927000000_saving_record_rls_hardening.sql
--
-- PR2 follow-up finding #5: `saving_record`'s tenant_isolation policy (20260821000034) is a
-- single `for all` policy granting select/insert/update/delete uniformly to every `authenticated`
-- tenant member, with no role distinction. The app layer restricts recording a purchase and
-- verifying a saving to WRITE_ROLES = (owner, buyer) (savings/router.py's `require_role`), but
-- that is an application-layer check only -- Non-negotiable #1 requires tenant isolation (and, by
-- the same evidence-over-assertion logic, this table's write shape) be enforced in the database,
-- not relied on at the application layer alone. A direct PostgREST/Supabase-client call with any
-- tenant member's own valid JWT -- any role, including `viewer` -- can currently INSERT a
-- saving_record already at status='verified' with verified_by/verified_at and arbitrary
-- baseline/actual/delta amounts, bypassing require_role() entirely. The immutability trigger
-- (20260821000035) only fires on UPDATE/DELETE, never INSERT, so it does not catch this.
--
-- Fix: replace the single policy with four operation-specific ones.
--   SELECT   unchanged -- every authenticated tenant member can already read savings via the
--            app's list_savings endpoint (no role restriction there), so this is not tightened.
--   INSERT   requires owner/buyer AND requires the inserted row to start at status='pending' with
--            no verified_by/verified_at -- exactly what record_purchase() always sends today
--            (service.py hard-codes 'pending' at insert time), so no legitimate write changes.
--   UPDATE   requires owner/buyer, and only the OLD row being 'pending' + the NEW row being
--            'verified' with verified_by = the caller's own membership -- exactly the pending ->
--            verified transition verify_saving() performs, and nothing else (no other endpoint
--            updates saving_record; research.md: "verification changes only status metadata").
--   DELETE   no policy for `authenticated` at all -- absence of a policy is the denial, same
--            convention as `plan_read` (20260821000034). Nothing in the app ever deletes a
--            saving_record through the authenticated path; the only DELETE in the codebase is
--            test cleanup, which runs as a role with BYPASSRLS.
--
-- Codex review of this PR caught two further gaps, both fixed below rather than shipped and
-- revisited:
--
-- (1) current_member_role() reads the JWT's `member_role` claim, which can be momentarily stale
--     relative to the live `membership` row -- a member demoted from owner/buyer to viewer keeps
--     write access on this table until their token is refreshed, the exact bug
--     current_membership_id()'s own comment (20260822000037) warns current_member_role() must
--     never be used for an authorization decision. The auto_preparation_guardrail write policies
--     (20260924203650) already made this same mistake; not fixed here (out of this PR's scope),
--     but this table does not repeat it. current_membership_role() below is the same live,
--     non-cached lookup current_membership_id() already performs, just selecting role instead of
--     id -- so a role change takes effect on the member's very next statement, no token refresh
--     required, matching the rest of this codebase's stated live-lookup convention.
--
-- (2) The UPDATE policy only constrained status/verified_by/verified_at -- nothing stopped the
--     SAME statement also rewriting baseline_value_amount, actual_value_amount, delta_amount,
--     calculation_inputs, or any other evidence column in the very statement that makes the row
--     permanently immutable, letting a "verifier" freeze fabricated evidence into the ledger.
--     research.md/data-model.md are explicit that verification changes only status metadata; RLS
--     alone cannot express "these other columns are unchanged" as cleanly as a trigger can, so
--     saving_record_verification_is_metadata_only below is the enforcement, mirroring
--     refuse_verified_saving_record_mutation's (20260821000035) existing trigger-based style for
--     this exact table.

create or replace function current_membership_role()
returns text
language sql
stable
as $$
  select role from membership
  where tenant_id = current_tenant_id()
    and user_id = current_user_id()
    and status = 'active'
  limit 1;
$$;

comment on function current_membership_role() is
  'The signed-in member''s role via a live lookup, not the JWT claim -- mirrors
   current_membership_id() (20260822000037) exactly, so a role change (e.g. a demotion) takes
   effect on the member''s very next statement. Use this, not current_member_role(), for any
   actual write-authorization decision -- see PR2 follow-up finding 5.';

drop policy if exists tenant_isolation on saving_record;

create policy saving_record_select on saving_record
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy saving_record_insert on saving_record
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
    and status = 'pending'
    and verified_by is null
    and verified_at is null
  );

create policy saving_record_update on saving_record
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
    and status = 'pending'
  )
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
    and status = 'verified'
    and verified_by = current_membership_id()
    and verified_at is not null
  );

revoke delete on saving_record from authenticated;

comment on policy saving_record_insert on saving_record is
  'FR-002-FR-006 + Non-negotiable #1. Only owner/buyer, and only a fresh pending row with no
   verification metadata -- closes the direct-insert-as-verified gap. See PR2 follow-up finding 5.';

comment on policy saving_record_update on saving_record is
  'Only the single legitimate transition (pending -> verified, by the caller''s own membership) is
   permitted; the immutability trigger (20260821000035) then makes it permanent, and
   saving_record_verification_is_metadata_only below stops that same transition from smuggling in
   evidence changes. See PR2 follow-up finding 5.';

create or replace function enforce_saving_record_verification_is_metadata_only()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.status = 'pending' and new.status = 'verified' then
    if old.tenant_id is distinct from new.tenant_id
      or old.purchase_record_id is distinct from new.purchase_record_id
      or old.workspace_product_id is distinct from new.workspace_product_id
      or old.supplier_id is distinct from new.supplier_id
      or old.baseline_policy is distinct from new.baseline_policy
      or old.baseline_source_landed_cost_ids is distinct from new.baseline_source_landed_cost_ids
      or old.baseline_unit_price_amount is distinct from new.baseline_unit_price_amount
      or old.baseline_unit_price_currency is distinct from new.baseline_unit_price_currency
      or old.baseline_value_amount is distinct from new.baseline_value_amount
      or old.baseline_value_currency is distinct from new.baseline_value_currency
      or old.actual_value_amount is distinct from new.actual_value_amount
      or old.actual_value_currency is distinct from new.actual_value_currency
      or old.delta_amount is distinct from new.delta_amount
      or old.delta_currency is distinct from new.delta_currency
      or old.calculation_version is distinct from new.calculation_version
      or old.calculation_inputs is distinct from new.calculation_inputs
      or old.recorded_by is distinct from new.recorded_by
      or old.recorded_at is distinct from new.recorded_at
      or old.created_at is distinct from new.created_at
    then
      raise exception 'verification may only change status, verified_at, and verified_by'
        using errcode = 'restrict_violation',
              hint = 'Every other saving_record field is fixed at record time (research.md R1).';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists saving_record_verification_is_metadata_only on saving_record;

create trigger saving_record_verification_is_metadata_only
  before update on saving_record
  for each row
  execute function enforce_saving_record_verification_is_metadata_only();

comment on function enforce_saving_record_verification_is_metadata_only() is
  'The pending -> verified transition may only touch status/verified_at/verified_by -- every other
   column must be byte-identical between OLD and NEW. Independent of, and a companion to,
   refuse_verified_saving_record_mutation (20260821000035), which guards the row AFTER it is
   verified; this guards the one statement that gets it there. See PR2 follow-up finding 5.';
