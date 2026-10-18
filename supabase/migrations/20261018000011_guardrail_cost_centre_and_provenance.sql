-- 20261018000011_guardrail_cost_centre_and_provenance.sql — hosted demo-tenant findings 37/38
-- (docs/gtm/demo-tenant/rtl-walkthrough-2026-10-18.md), spec 021-rfq-sourcing-autonomy.
--
-- 38b. auto_preparation_guardrail.default_cost_centre_id (optional). Composite FK on
--      (tenant_id, default_cost_centre_id), so a guardrail can never name another workspace's
--      cost centre. That it belongs to the guardrail's default branch is checked by the API
--      (RfqService) when the guardrail is written and again by the worker when it prepares.
--      ON DELETE SET NULL (column only): cost centres are archived, not deleted, in practice.
--      No new table, so RLS is unchanged: the column inherits the table's existing policies.
--
-- 38a. A guardrail-prepared request has to be recognisable on the request itself, for anyone
--      who can see that request -- including the approver it is later routed to, who is not an
--      owner/buyer and cannot read rfq_response/rfq_recipient. So:
--      - auto_preparation_event gains rfq_id and supplier_id (same composite tenant FKs), filled
--        by the worker at preparation time and backfilled here for existing rows;
--      - event_select also admits a member who can see the prepared purchase_request. The
--        subquery runs under the caller's own purchase_request RLS, so this grants nothing
--        beyond "you can see the request, so you can see how it was prepared". The role check
--        uses the live current_membership_role(), not the JWT claim, as 20261018000009 does.
--
-- 37.  set_tenant_default_locale(): change tenant.default_locale (the language RFQ emails go
--      out in) and record tenant.default_locale_changed in one transaction. Unlike
--      set_tenant_currency (20261014000001) it enforces owner-only itself (authenticated can
--      call it directly through PostgREST) and takes no actor arguments: the audit event
--      names the caller's own live membership.

-- 38b ----------------------------------------------------------------------------------------
alter table auto_preparation_guardrail add column default_cost_centre_id uuid;
alter table auto_preparation_guardrail add constraint
  auto_preparation_guardrail_default_cost_centre_id_fkey
  foreign key (tenant_id, default_cost_centre_id) references cost_centre (tenant_id, id)
  on delete set null (default_cost_centre_id);

-- 38a ----------------------------------------------------------------------------------------
alter table auto_preparation_event add column rfq_id uuid;
alter table auto_preparation_event add column supplier_id uuid;
alter table auto_preparation_event add constraint auto_preparation_event_rfq_fkey
  foreign key (tenant_id, rfq_id) references rfq (tenant_id, id);
alter table auto_preparation_event add constraint auto_preparation_event_supplier_fkey
  foreign key (tenant_id, supplier_id) references supplier (tenant_id, id);

-- auto_preparation_event is append-only for clients (UPDATE revoked from authenticated and
-- service_role); this one-off backfill runs as the migrating role.
update auto_preparation_event e
set rfq_id = rec.rfq_id,
    supplier_id = rec.supplier_id
from rfq_response r
join rfq_recipient rec on rec.tenant_id = r.tenant_id and rec.id = r.rfq_recipient_id
where r.tenant_id = e.tenant_id
  and r.id = e.rfq_response_id
  and (e.rfq_id is null or e.supplier_id is null);

create index if not exists auto_preparation_event_purchase_request_idx
  on auto_preparation_event (tenant_id, purchase_request_id);

drop policy event_select on auto_preparation_event;
create policy event_select on auto_preparation_event
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_membership_role() in ('owner', 'buyer')
      or exists (
        select 1 from auto_preparation_guardrail g
        where g.tenant_id = auto_preparation_event.tenant_id
          and g.id = auto_preparation_event.guardrail_id
          and g.created_by_membership_id = current_membership_id()
      )
      or exists (
        select 1 from purchase_request pr
        where pr.tenant_id = auto_preparation_event.tenant_id
          and pr.id = auto_preparation_event.purchase_request_id
      )
    )
  );

-- 37 -----------------------------------------------------------------------------------------
-- SECURITY INVOKER: the caller's RLS still applies, so a member only ever touches their own
-- tenant row. Owner-only is checked here with the live role, not only by the API.
create or replace function set_tenant_default_locale(p_locale text)
returns text
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_tenant     uuid := current_tenant_id();
  v_membership uuid := current_membership_id();
  v_email      text;
  v_old        text;
begin
  if v_membership is null or current_membership_role() is distinct from 'owner' then
    raise exception 'only the workspace owner can change the workspace language'
      using errcode = '42501';
  end if;

  if p_locale is null or p_locale not in ('en', 'ar') then
    raise exception 'unsupported locale' using errcode = '22023';
  end if;

  select email into v_email from membership where id = v_membership;

  select default_locale into v_old from tenant where id = v_tenant for update;
  if not found then
    raise exception 'tenant not found' using errcode = 'P0002';
  end if;

  if v_old is distinct from p_locale then
    update tenant set default_locale = p_locale where id = v_tenant;
    perform record_audit_event(
      'tenant.default_locale_changed',
      'success'::audit_outcome,
      v_tenant,
      v_membership,
      v_email,
      jsonb_build_object('from', v_old, 'to', p_locale),
      null
    );
  end if;

  return v_old;
end;
$$;

revoke execute on function set_tenant_default_locale(text) from public, anon;
grant execute on function set_tenant_default_locale(text) to authenticated;

comment on function set_tenant_default_locale is
  'Owner only (live role). Atomically sets tenant.default_locale (en or ar; RFQ emails use it) and records tenant.default_locale_changed naming the calling membership.';
