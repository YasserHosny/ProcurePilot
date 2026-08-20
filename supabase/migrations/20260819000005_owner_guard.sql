-- 0005_owner_guard.sql — task T016
--
-- FR-012: a workspace MUST always retain at least one active owner.
--
-- This is a cardinality-minimum rule. No unique constraint or check constraint can express it,
-- because it concerns the count of OTHER rows after the change. A trigger is the only correct
-- place: enforcing it in application code alone would leave the guarantee dependent on every
-- future code path remembering to call it, and the spec's edge cases (self-demotion,
-- self-removal, demoting the last owner) each arrive through a different path.

create or replace function assert_tenant_retains_owner()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  affected_tenant uuid;
  remaining_owners integer;
begin
  affected_tenant := coalesce(old.tenant_id, new.tenant_id);

  -- Only changes that could REMOVE an owner matter. A change that adds or leaves owners
  -- untouched skips the count entirely.
  if tg_op = 'UPDATE'
     and old.role = 'owner' and new.role = 'owner'
     and old.status = new.status then
    return new;
  end if;

  if tg_op = 'UPDATE' and old.role <> 'owner' and new.role <> 'owner' then
    return new;
  end if;

  if tg_op = 'DELETE' and old.role <> 'owner' then
    return old;
  end if;

  select count(*) into remaining_owners
  from membership m
  where m.tenant_id = affected_tenant
    and m.role = 'owner'
    and m.status = 'active'
    and m.id <> coalesce(old.id, new.id);

  -- The row being changed counts only if it REMAINS an active owner afterwards.
  if tg_op <> 'DELETE' and new.role = 'owner' and new.status = 'active' then
    remaining_owners := remaining_owners + 1;
  end if;

  if remaining_owners < 1 then
    raise exception 'a workspace must always retain at least one active owner'
      using errcode = 'restrict_violation',
            hint = 'Promote another member to owner before removing or demoting this one.';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

drop trigger if exists membership_owner_guard on membership;

create trigger membership_owner_guard
  before update or delete on membership
  for each row
  execute function assert_tenant_retains_owner();

comment on function assert_tenant_retains_owner() is
  'FR-012. Refuses any update or delete that would leave a workspace with no active owner.
   Covers demotion, removal, and self-service versions of both.';
