-- 20261018000007_rfq_child_write_owner_buyer.sql — follow-up to 20261018000003 (issue #122).
--
-- 20261018000003 limited rfq INSERT/UPDATE to an owner or buyer who created the RFQ. The child
-- tables' write policies (20260924203650) still admitted the creator without a role check, so a
-- member who created an RFQ and was later given another role could still change its lines and
-- recipients. These policies now hold the same line as rfq itself: tenant, creator, and role
-- owner/buyer, on USING and WITH CHECK.
--
-- rfq_recipient_update previously admitted any owner/buyer (not only the creator) and had no
-- WITH CHECK. The only server write to rfq_recipient (send marks recipients sent) already
-- requires the creator, so it now matches rfq_update: creator AND owner/buyer.
--
-- Read policies are unchanged. No worker writes rfq_line or rfq_recipient; the API writes them
-- only through RfqService.create / update_draft / send, which run as the member's own
-- authenticated session behind owner/buyer-only routes.

drop policy rfq_line_insert on rfq_line;
create policy rfq_line_insert on rfq_line
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

drop policy rfq_line_update on rfq_line;
create policy rfq_line_update on rfq_line
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

drop policy rfq_line_delete on rfq_line;
create policy rfq_line_delete on rfq_line
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

drop policy rfq_recipient_insert on rfq_recipient;
create policy rfq_recipient_insert on rfq_recipient
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

drop policy rfq_recipient_update on rfq_recipient;
create policy rfq_recipient_update on rfq_recipient
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

drop policy rfq_recipient_delete on rfq_recipient;
create policy rfq_recipient_delete on rfq_recipient
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );
