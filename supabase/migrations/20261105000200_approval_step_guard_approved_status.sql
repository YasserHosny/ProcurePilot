-- 20261105000200_approval_step_guard_approved_status.sql -- approval_step guard follows P-174
--
-- P-174 (ADR-025): an approval leaves the request `approved`, not `ordered`; `ordered` is set only
-- while a live purchase order exists. The guard from 20261105000100 required the request to read
-- `ordered` before an `approved` step could be recorded, so every client-session approval would
-- be refused once the API moves to `approved`. The comparison now accepts either value.

create or replace function approval_step_guard_client_write()
returns trigger
language plpgsql
set search_path = pg_catalog, public, pg_temp
as $$
declare
  is_owner boolean;
  acting_membership uuid;
  request_row record;
  sole_owner boolean;
begin
  if current_user not in ('authenticated', 'anon') then
    return coalesce(new, old);
  end if;

  if tg_op = 'DELETE' then
    raise exception 'approval steps cannot be deleted by a client session'
      using errcode = '42501';
  end if;

  -- Owner authority and identity are read live (current_membership_role / _id), never from the
  -- token's member_role claim, so a demoted owner loses it on their next statement.
  is_owner := coalesce(current_membership_role() = 'owner', false);
  acting_membership := current_membership_id();

  if acting_membership is null then
    raise exception 'no active membership for this session'
      using errcode = '42501';
  end if;

  if tg_op = 'INSERT' then
    if new.status <> 'pending' then
      raise exception 'an approval step is created pending'
        using errcode = '42501';
    end if;
    -- Routing runs when the requester submits: the request is submitted and theirs, and it is not
    -- routed to themselves unless they are the workspace's only active owner (ADR-024).
    select pr.status, pr.requested_by_membership_id into request_row
      from purchase_request pr
      where pr.tenant_id = new.tenant_id and pr.id = new.purchase_request_id;
    if request_row.status::text is distinct from 'submitted'
       or request_row.requested_by_membership_id is distinct from acting_membership then
      raise exception 'an approval step is created when its requester submits the request'
        using errcode = '42501';
    end if;
    if new.assigned_membership_id = acting_membership and not (
         is_owner and not exists (
           select 1 from membership m
           where m.tenant_id = new.tenant_id and m.role = 'owner' and m.status = 'active'
             and m.id <> acting_membership)
       ) then
      raise exception 'a request is not routed to its own requester'
        using errcode = '42501';
    end if;
    return new;
  end if;

  -- UPDATE

  if old.status <> 'pending' then
    raise exception 'a decided approval step cannot be changed'
      using errcode = '42501';
  end if;

  if new.id is distinct from old.id
     or new.tenant_id is distinct from old.tenant_id
     or new.purchase_request_id is distinct from old.purchase_request_id
     or new.created_at is distinct from old.created_at then
    raise exception 'an approval step cannot be moved'
      using errcode = '42501';
  end if;

  if new.status = 'pending' then
    -- Only an owner reassigning to an owner (escalation when the approver is removed).
    if is_owner
       and new.assigned_membership_id is distinct from old.assigned_membership_id
       and new.source = 'owner_fallback'
       and new.comment is not distinct from old.comment
       and new.decided_by_membership_id is null
       and new.decided_at is null
       and exists (
         select 1 from membership m
         where m.tenant_id = new.tenant_id
           and m.id = new.assigned_membership_id
           and m.role = 'owner'
           and m.status = 'active'
       ) then
      return new;
    end if;
    raise exception 'a pending approval step changes only by a decision or an owner reassignment'
      using errcode = '42501';
  end if;

  -- A decision: approved or rejected, by the assignee or an owner, recorded as themselves.
  if new.assigned_membership_id is distinct from old.assigned_membership_id
     or new.source is distinct from old.source then
    raise exception 'a decision cannot change who the step is assigned to'
      using errcode = '42501';
  end if;

  if new.decided_by_membership_id is distinct from acting_membership then
    raise exception 'a decision is recorded as the member who makes it'
      using errcode = '42501';
  end if;

  if not (is_owner or old.assigned_membership_id = acting_membership) then
    raise exception 'only the assigned approver or an owner can decide this step'
      using errcode = '42501';
  end if;

  -- The API moves the request first (approved -> approved, rejected -> rejected) and then records
  -- the step, so the request must already carry the same outcome.
  select pr.status, pr.requested_by_membership_id into request_row
    from purchase_request pr
    where pr.tenant_id = old.tenant_id and pr.id = old.purchase_request_id;
  -- An approval leaves the request `approved` (P-174); `ordered` is still accepted so the
  -- migration is safe to apply before or after the API that stopped writing it.
  if request_row.status::text is distinct from new.status::text
     and not (new.status::text = 'approved' and request_row.status::text = 'ordered') then
    raise exception 'a step is decided together with its request'
      using errcode = '42501';
  end if;

  -- ADR-024: nobody decides a request they submitted unless they are the only active owner.
  if request_row.requested_by_membership_id = acting_membership then
    sole_owner := is_owner and not exists (
      select 1 from membership m
      where m.tenant_id = old.tenant_id and m.role = 'owner' and m.status = 'active'
        and m.id <> acting_membership);
    if not sole_owner then
      raise exception 'a request cannot be decided by the member who submitted it'
        using errcode = '42501';
    end if;
  end if;

  -- The decision time is the database's, not whatever the session wrote.
  new.decided_at := now();

  return new;
end;
$$;

comment on function approval_step_guard_client_write() is
  'Limits a client session (authenticated, anon) to the writes the API makes on approval_step:
   insert pending, decide a pending step as its assignee or an owner, owner reassignment to an
   owner. Server-side roles are not restricted. (PPS-166)';
