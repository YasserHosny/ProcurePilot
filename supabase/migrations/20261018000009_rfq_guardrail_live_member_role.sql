-- 20261018000009_rfq_guardrail_live_member_role.sql — follow-up to 20261018000003 and 20261018000007
-- (Codex review of #154, 2026-10-18).
--
-- 20261018000003 and 20261018000007 limited RFQ writes to an owner or buyer with
-- current_member_role(), which reads the member_role claim from the JWT. That claim is fixed when
-- the token is issued, so a member demoted from owner/buyer kept write access until the token
-- expired (up to an hour). current_member_role() itself is documented as never being the source
-- of truth for authorization (20260822000037_branch.sql).
--
-- current_membership_role() (20260927000000) reads the role from the member's active membership
-- row, the same live lookup current_membership_id() uses, so a role change applies on the next
-- request. The RFQ and guardrail write policies now use it. rfq_delete also gains the owner/buyer check: it still admitted
-- any creator, and deleting an RFQ cascades to its lines and recipients.
--
-- rfq_response is written only by the ingestion worker as service_role, so `authenticated` loses
-- write access to it entirely (its insert/update policies admitted any member of the workspace).
--
-- Scope: the RFQ, rfq_response and guardrail policies from 20260924203650, 20261018000003 and
-- 20261018000007. Other policies that read current_member_role() are unchanged here; the API's own
-- live-lookup consistency check already rejects a token whose role no longer matches.
--
-- Writers checked: RfqService (create, update_draft, send, prepare) sets claims with sub from the
-- member's own session; the ingestion orchestrator writes rfq/rfq_response as service_role.

-- rfq --------------------------------------------------------------------------------------------

drop policy rfq_insert on rfq;
create policy rfq_insert on rfq
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_membership_role() in ('owner', 'buyer')
  );

drop policy rfq_update on rfq;
create policy rfq_update on rfq
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_membership_role() in ('owner', 'buyer')
  )
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_membership_role() in ('owner', 'buyer')
  );

drop policy rfq_delete on rfq;
create policy rfq_delete on rfq
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_membership_role() in ('owner', 'buyer')
  );

-- rfq_line ---------------------------------------------------------------------------------------

drop policy rfq_line_insert on rfq_line;
create policy rfq_line_insert on rfq_line
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
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
    and current_membership_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  )
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
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
    and current_membership_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

-- rfq_recipient ----------------------------------------------------------------------------------

drop policy rfq_recipient_insert on rfq_recipient;
create policy rfq_recipient_insert on rfq_recipient
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
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
    and current_membership_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  )
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() in ('owner', 'buyer')
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
    and current_membership_role() in ('owner', 'buyer')
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

-- rfq_response -----------------------------------------------------------------------------------

drop policy rfq_response_insert on rfq_response;
drop policy rfq_response_update on rfq_response;
drop policy rfq_response_delete on rfq_response;
revoke insert, update, delete on rfq_response from authenticated;

-- auto_preparation_guardrail -----------------------------------------------------------------------

drop policy guardrail_select on auto_preparation_guardrail;
create policy guardrail_select on auto_preparation_guardrail
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      created_by_membership_id = current_membership_id()
      or current_membership_role() in ('owner', 'buyer')
    )
  );

drop policy guardrail_insert on auto_preparation_guardrail;
create policy guardrail_insert on auto_preparation_guardrail
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_membership_role() = 'owner'
  );

drop policy guardrail_update on auto_preparation_guardrail;
create policy guardrail_update on auto_preparation_guardrail
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_membership_role() = 'owner'
  )
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() = 'owner'
  );

drop policy guardrail_delete on auto_preparation_guardrail;
create policy guardrail_delete on auto_preparation_guardrail
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_membership_role() = 'owner'
  );
