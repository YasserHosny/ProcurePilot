-- 022-home-currency-readiness: change the tenant's home currency and audit it in ONE transaction.
--
-- Doing the UPDATE and the audit RPC as two PostgREST calls could commit the new currency and
-- then lose the audit event (and a retry would then see old == new and skip it for good).
-- SECURITY INVOKER: the caller's RLS still applies, so a member can only ever touch their own
-- tenant row (tenant_isolation policy). Owner-only is enforced by the API layer, as for PATCH /tenant.

create or replace function set_tenant_currency(
  p_currency             text,
  p_actor_membership_id  uuid,
  p_actor_email          text
)
returns text
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_tenant uuid := current_tenant_id();
  v_old    text;
begin
  if not exists (
    select 1 from supported_currency where code = p_currency and is_enabled
  ) then
    raise exception 'unsupported currency' using errcode = '22023';
  end if;

  select currency into v_old from tenant where id = v_tenant for update;
  if not found then
    raise exception 'tenant not found' using errcode = 'P0002';
  end if;

  if v_old is distinct from p_currency then
    update tenant set currency = p_currency where id = v_tenant;
    perform record_audit_event(
      'tenant.currency_changed',
      'success'::audit_outcome,
      v_tenant,
      p_actor_membership_id,
      p_actor_email,
      jsonb_build_object('from', v_old, 'to', p_currency),
      null
    );
  end if;

  return v_old;
end;
$$;

grant execute on function set_tenant_currency(text, uuid, text) to authenticated;

comment on function set_tenant_currency is
  'Atomically sets tenant.currency (validated against supported_currency) and records the tenant.currency_changed audit event.';
