-- 20261018000004_definer_caller_tenant_guard.sql — security review 2026-10-18 (issue #122),
-- finding 1.
--
-- The R2.5 reporting readers (20260915000005) are SECURITY DEFINER and pinned to p_tenant_id on
-- every table reference, but nothing checked that p_tenant_id is the CALLER's tenant. That
-- migration revoked EXECUTE from PUBLIC only; Supabase grants EXECUTE on public functions to
-- anon and authenticated directly, so both kept it. Through PostgREST
-- (/rest/v1/rpc/reporting_purchases_for_period) the public anon key alone read another
-- workspace's purchases, savings, offers and suppliers given its tenant id.
--
-- record_audit_event had the same gap for writes: a caller with NO tenant claim (the anon key)
-- could file an event under any tenant id, forging another workspace's history.
--
-- The rule enforced below: a caller arriving as anon or authenticated (PostgREST, or a worker
-- that has SET ROLE authenticated with claims) may only name its own claimed tenant. Callers
-- with neither role — the workers and operator CLIs connecting as postgres through
-- DATABASE_URL, and service_role — are trusted server-side code and keep their access.
-- current_setting('role') still reports the caller's role inside a SECURITY DEFINER body
-- (current_user is the owner there), which is what makes the check possible.

create or replace function assert_caller_tenant(p_tenant_id uuid)
returns void
language plpgsql
stable
set search_path = pg_catalog, public
as $$
begin
  if coalesce(current_setting('role', true), 'none') in ('anon', 'authenticated')
     or current_tenant_id() is not null then
    if p_tenant_id is null or p_tenant_id is distinct from current_tenant_id() then
      raise exception 'tenant-pinned call for a workspace other than the caller''s'
        using errcode = 'insufficient_privilege';
    end if;
  end if;
end;
$$;

comment on function assert_caller_tenant(uuid) is
  'Refuses a SECURITY DEFINER call naming a tenant other than the caller''s claim when the
   caller is anon or authenticated (or holds any tenant claim). Server-side callers with no
   claim and no anon/authenticated role (postgres via DATABASE_URL, service_role) pass.';

revoke execute on function assert_caller_tenant(uuid) from public, anon;
grant execute on function assert_caller_tenant(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Reporting readers: keep the tenant-pinned bodies under *_unguarded (callable only by the
-- owner and service_role) and put a guarded wrapper under the original name, so every caller
-- keeps working unchanged.
-- ---------------------------------------------------------------------------

alter function reporting_savings_for_period(uuid, date, date, uuid, uuid)
  rename to reporting_savings_for_period_unguarded;
alter function reporting_purchases_for_period(uuid, date, date, uuid, uuid)
  rename to reporting_purchases_for_period_unguarded;
alter function reporting_alert_snapshot(uuid, date, date, uuid)
  rename to reporting_alert_snapshot_unguarded;
alter function reporting_validity_expiring(uuid, timestamptz, integer, uuid)
  rename to reporting_validity_expiring_unguarded;

revoke execute on function reporting_savings_for_period_unguarded(uuid, date, date, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function reporting_purchases_for_period_unguarded(uuid, date, date, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function reporting_alert_snapshot_unguarded(uuid, date, date, uuid)
  from public, anon, authenticated;
revoke execute on function reporting_validity_expiring_unguarded(uuid, timestamptz, integer, uuid)
  from public, anon, authenticated;

create function reporting_savings_for_period(
  p_tenant_id     uuid,
  p_period_start  date,
  p_period_end    date,
  p_supplier_id   uuid default null,
  p_branch_id     uuid default null
)
returns table (
  saving_id                    uuid,
  purchase_record_id           uuid,
  purchase_request_id          uuid,
  recorded_at                  timestamptz,
  supplier_id                  uuid,
  supplier_name                text,
  product_id                   uuid,
  product_name                 text,
  canonical_brand              text,
  canonical_name               text,
  canonical_gtin               text,
  base_unit                    text,
  quantity                     numeric,
  attributed_branch_id         uuid,
  attributed_branch_name       text,
  baseline_unit_price_amount   numeric,
  baseline_unit_price_currency text,
  baseline_value_amount        numeric,
  baseline_value_currency      text,
  actual_unit_price_amount     numeric,
  actual_unit_price_currency   text,
  actual_total_paid_amount     numeric,
  actual_total_paid_currency   text,
  verified_saving_amount       numeric,
  verified_saving_currency     text
)
language plpgsql
stable
security definer
set search_path = pg_catalog, public
as $$
begin
  perform assert_caller_tenant(p_tenant_id);
  return query select * from reporting_savings_for_period_unguarded(
    p_tenant_id, p_period_start, p_period_end, p_supplier_id, p_branch_id);
end;
$$;

create function reporting_purchases_for_period(
  p_tenant_id     uuid,
  p_period_start  date,
  p_period_end    date,
  p_supplier_id   uuid default null,
  p_branch_id     uuid default null
)
returns table (
  purchase_record_id          uuid,
  purchase_request_id         uuid,
  recorded_at                 timestamptz,
  ordered_at                  timestamptz,
  delivered_at                timestamptz,
  supplier_id                 uuid,
  supplier_name               text,
  product_id                  uuid,
  product_name                text,
  base_unit                   text,
  quantity                    numeric,
  attributed_branch_id        uuid,
  attributed_branch_name      text,
  unit_price_amount           numeric,
  unit_price_currency         text,
  total_paid_amount           numeric,
  total_paid_currency         text,
  saving_id                   uuid,
  saving_status               text,
  saving_delta_amount         numeric,
  saving_delta_currency       text
)
language plpgsql
stable
security definer
set search_path = pg_catalog, public
as $$
begin
  perform assert_caller_tenant(p_tenant_id);
  return query select * from reporting_purchases_for_period_unguarded(
    p_tenant_id, p_period_start, p_period_end, p_supplier_id, p_branch_id);
end;
$$;

create function reporting_alert_snapshot(
  p_tenant_id     uuid,
  p_period_start  date,
  p_period_end    date,
  p_branch_id     uuid default null
)
returns table (
  landed_cost_id           uuid,
  workspace_product_id     uuid,
  product_name             text,
  canonical_brand          text,
  canonical_name           text,
  canonical_gtin           text,
  supplier_id              uuid,
  supplier_name            text,
  quotation_line_id        uuid,
  match_confidence         numeric,
  rule_version             text,
  recorded_at              timestamptz,
  valid_from               timestamptz,
  valid_to                 timestamptz,
  total_amount             numeric,
  total_currency           text,
  normalised_base_quantity numeric,
  quantity                 numeric,
  base_unit                text,
  pack_base_quantity       numeric,
  lead_time_days           integer,
  reliability_score        numeric,
  is_latest_offer          boolean
)
language plpgsql
stable
security definer
set search_path = pg_catalog, public
as $$
begin
  perform assert_caller_tenant(p_tenant_id);
  return query select * from reporting_alert_snapshot_unguarded(
    p_tenant_id, p_period_start, p_period_end, p_branch_id);
end;
$$;

create function reporting_validity_expiring(
  p_tenant_id    uuid,
  p_now          timestamptz,
  p_horizon_days integer,
  p_branch_id    uuid default null
)
returns table (
  landed_cost_id           uuid,
  workspace_product_id     uuid,
  product_name             text,
  supplier_id              uuid,
  supplier_name            text,
  recorded_at              timestamptz,
  valid_from               timestamptz,
  valid_to                 timestamptz,
  total_amount             numeric,
  total_currency           text,
  normalised_base_quantity numeric,
  base_unit                text
)
language plpgsql
stable
security definer
set search_path = pg_catalog, public
as $$
begin
  perform assert_caller_tenant(p_tenant_id);
  return query select * from reporting_validity_expiring_unguarded(
    p_tenant_id, p_now, p_horizon_days, p_branch_id);
end;
$$;

create or replace function reporting_assert_branch_visible(
  p_tenant_id uuid,
  p_branch_id uuid
)
returns void
language plpgsql
stable
security definer
set search_path = pg_catalog, public
as $$
begin
  perform assert_caller_tenant(p_tenant_id);
  if p_branch_id is not null and not exists (
    select 1 from branch b
    where b.tenant_id = p_tenant_id
      and b.id = p_branch_id
      and b.is_active
  ) then
    raise exception 'reporting reader: branch % is not an active branch of the pinned tenant',
      p_branch_id
      using errcode = '22023';
  end if;
end;
$$;

revoke execute on function reporting_savings_for_period(uuid, date, date, uuid, uuid)
  from public, anon;
revoke execute on function reporting_purchases_for_period(uuid, date, date, uuid, uuid)
  from public, anon;
revoke execute on function reporting_alert_snapshot(uuid, date, date, uuid)
  from public, anon;
revoke execute on function reporting_validity_expiring(uuid, timestamptz, integer, uuid)
  from public, anon;
revoke execute on function reporting_assert_branch_visible(uuid, uuid)
  from public, anon;

grant execute on function reporting_savings_for_period(uuid, date, date, uuid, uuid)
  to authenticated, service_role;
grant execute on function reporting_purchases_for_period(uuid, date, date, uuid, uuid)
  to authenticated, service_role;
grant execute on function reporting_alert_snapshot(uuid, date, date, uuid)
  to authenticated, service_role;
grant execute on function reporting_validity_expiring(uuid, timestamptz, integer, uuid)
  to authenticated, service_role;
grant execute on function reporting_assert_branch_visible(uuid, uuid)
  to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- record_audit_event: a caller without a tenant claim may still record a pre-authentication
-- event (p_tenant_id null, e.g. a failed sign-in), but may no longer name a workspace. Server-
-- side writers with no claim (workers via DATABASE_URL) keep naming the tenant, as before.
-- ---------------------------------------------------------------------------

create or replace function record_audit_event(
  p_action              text,
  p_outcome             audit_outcome,
  p_tenant_id           uuid  default null,
  p_actor_membership_id uuid  default null,
  p_actor_email         text  default null,
  p_target              jsonb default null,
  p_trace_id            text  default null
)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  claim_tenant uuid := current_tenant_id();
  new_id bigint;
begin
  -- A caller holding a tenant claim may only write events for THAT tenant. Passing NULL is
  -- allowed and means a system or pre-authentication event. Anything else is an attempt to
  -- write into another workspace's history and is refused outright.
  if p_tenant_id is not null and claim_tenant is not null and p_tenant_id <> claim_tenant then
    raise exception 'cannot record an audit event for another workspace'
      using errcode = 'insufficient_privilege';
  end if;

  -- An anon or authenticated caller with no tenant claim cannot name a workspace either: that
  -- is the public anon key, and it must not be able to file events under any tenant id.
  if p_tenant_id is not null and claim_tenant is null
     and coalesce(current_setting('role', true), 'none') in ('anon', 'authenticated') then
    raise exception 'cannot record an audit event for a workspace without its claim'
      using errcode = 'insufficient_privilege';
  end if;

  insert into audit_event (
    tenant_id, actor_membership_id, actor_email, action, target, outcome, trace_id
  )
  values (
    coalesce(p_tenant_id, claim_tenant),
    p_actor_membership_id,
    p_actor_email,
    p_action,
    p_target,
    p_outcome,
    p_trace_id
  )
  returning id into new_id;

  return new_id;
end;
$$;

-- ---------------------------------------------------------------------------
-- Invitation RPCs (finding 2). accept_member_invitation takes the user id and address from
-- its arguments, and the address is shown on the accept page, so through /rest/v1/rpc anyone
-- holding an invitation link could redeem it for their own account. The API already proves the
-- invitee owns the address (sign-up or password check) and now calls it over DATABASE_URL.
-- member_invitation_for_token has no caller left (the API reads invitations server-side).
-- ---------------------------------------------------------------------------

revoke execute on function accept_member_invitation(text, uuid, text)
  from public, anon, authenticated;
revoke execute on function member_invitation_for_token(text)
  from public, anon, authenticated;
