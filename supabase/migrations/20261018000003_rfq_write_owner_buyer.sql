-- 20261018000003_rfq_write_owner_buyer.sql — security review 2026-10-18 (issue #122).
--
-- Spec 021 FR-001/FR-003: only an owner or buyer creates or sends an RFQ. The API routes now
-- require those roles; these policies hold the same line in the database, so a viewer,
-- approver or branch manager cannot create or update (and so send) an RFQ by any path.
-- Creator-only stays: an owner or buyer still edits only the RFQs they created.

drop policy rfq_insert on rfq;
create policy rfq_insert on rfq
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_member_role() in ('owner', 'buyer')
  );

drop policy rfq_update on rfq;
create policy rfq_update on rfq
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_member_role() in ('owner', 'buyer')
  )
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_member_role() in ('owner', 'buyer')
  );
