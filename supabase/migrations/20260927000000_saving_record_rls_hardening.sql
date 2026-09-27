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
-- current_member_role() reads the (possibly momentarily stale) JWT role claim; using it for an
-- authorization decision, not just a visibility shortcut, mirrors the precedent already set by
-- guardrail_insert/update/delete (20260924203650) for the same tenant-role-gated-write shape.

drop policy if exists tenant_isolation on saving_record;

create policy saving_record_select on saving_record
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy saving_record_insert on saving_record
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and status = 'pending'
    and verified_by is null
    and verified_at is null
  );

create policy saving_record_update on saving_record
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and status = 'pending'
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
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
   permitted; the immutability trigger (20260821000035) then makes it permanent. See PR2 follow-up
   finding 5.';
