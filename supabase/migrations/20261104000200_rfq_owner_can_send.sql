-- 20261104000200_rfq_owner_can_send.sql — an owner can send, retry and cancel any RFQ in the
-- workspace (PPS-179).
--
-- rfq_update and rfq_recipient_update only matched the RFQ's creator (20261018000009), so an owner
-- could not send or retry a buyer's draft. Both policies now also admit an active owner of the same
-- workspace (live lookup through current_membership_role). A buyer is unchanged: only their own RFQs.
-- Editing a draft stays creator-only in the API (RfqService.update_draft); delete, insert and the
-- line and recipient insert/delete policies are not touched. rfq_response stays service_role only.
--
-- Cancel already works for owners through cancel_rfq (20261103120000).
--
-- Forward-only.

drop policy rfq_update on rfq;
create policy rfq_update on rfq
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
    and (created_by_membership_id = current_membership_id() or current_membership_role() = 'owner')
  )
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
    and (created_by_membership_id = current_membership_id() or current_membership_role() = 'owner')
  );

drop policy rfq_recipient_update on rfq_recipient;
create policy rfq_recipient_update on rfq_recipient
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and (r.created_by_membership_id = current_membership_id()
             or current_membership_role() = 'owner')
    )
  )
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and (r.created_by_membership_id = current_membership_id()
             or current_membership_role() = 'owner')
    )
  );
