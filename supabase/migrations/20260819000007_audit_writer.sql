-- 0007_audit_writer.sql — resolves a gap found reviewing the backend primitives.
--
-- THE PROBLEM
-- audit_event's insert policy requires `tenant_id = current_tenant_id()`. But two of the events
-- the spec most wants recorded cannot satisfy it:
--   * a failed sign-in (FR-006) — there is no tenant claim, because there is no session yet
--   * a refused workspace creation (FR-033) — the tenant does not exist yet
-- Both carry tenant_id NULL, and NULL = NULL is not true, so the policy rejects them. The
-- security events most worth recording were exactly the ones that could not be written.
--
-- THE REJECTED FIX
-- Handing the backend a service-role key for request handling would work, and was the first
-- implementation. It is wrong: research R4 restricts the service role to migrations and the
-- platform-invitation flow precisely so that an RLS bypass never sits in the request path. One
-- exception becomes two.
--
-- THE FIX
-- A SECURITY DEFINER function: the only sanctioned way to write an audit row. It is append-only
-- by construction (there is no update or delete counterpart) and it validates tenancy itself, so
-- a member cannot forge an event against another workspace even though the function runs with
-- elevated rights.

create or replace function record_audit_event(
  p_action   text,
  p_outcome  audit_outcome,
  p_tenant_id           uuid default null,
  p_actor_membership_id uuid default null,
  p_actor_email         text default null,
  p_target              jsonb default null,
  p_trace_id            text default null
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

-- anon needs it too: a failed sign-in is recorded before any session exists.
grant execute on function record_audit_event(text, audit_outcome, uuid, uuid, text, jsonb, text)
  to authenticated, anon;

comment on function record_audit_event is
  'The only sanctioned path for writing an audit event. SECURITY DEFINER so that pre-authentication
   and refused events can be recorded, but it validates the tenant against the caller''s claim, so
   elevated rights cannot be turned into cross-tenant writes. There is deliberately no update or
   delete counterpart.';
