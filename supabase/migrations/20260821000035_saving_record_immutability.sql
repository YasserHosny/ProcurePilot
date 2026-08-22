-- 20260821000035_saving_record_immutability.sql
--
-- FR-004: a verified saving_record MUST be immutable — no UPDATE or DELETE, for any role. This is
-- a Principle-critical guarantee (Constitution Principle III: verification is a deliberate human
-- act; Principle I: evidence over assertion means the evidence chain cannot drift after the claim
-- is made), so — same reasoning as 20260819000005_owner_guard.sql's membership trigger — it
-- belongs in the database, not in application code that every future call site must remember to
-- respect.
--
-- Two triggers: one directly on saving_record, one on purchase_record (its evidence source) so
-- editing the purchase after its saving is verified cannot quietly undermine an already-verified
-- claim. See research.md R7 and data-model.md's "Additional Design Decisions".

create or replace function refuse_verified_saving_record_mutation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.status = 'verified' then
    raise exception 'verified saving records are immutable'
      using errcode = 'restrict_violation',
            hint = 'A verified saving record cannot be changed or removed by any role.';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

drop trigger if exists saving_record_verified_immutability on saving_record;

create trigger saving_record_verified_immutability
  before update or delete on saving_record
  for each row
  execute function refuse_verified_saving_record_mutation();

comment on function refuse_verified_saving_record_mutation() is
  'FR-004. Refuses any update or delete once status = ''verified''. Verification itself is the one
   allowed transition into this state and is expected to change only status/verified_at/verified_by
   (application-enforced boundary; this trigger is the constitutional guarantee underneath it).';

create or replace function refuse_purchase_record_mutation_when_saving_verified()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  target_id uuid;
  saving_status saving_record_status;
begin
  target_id := coalesce(old.id, new.id);

  select status into saving_status
  from saving_record
  where purchase_record_id = target_id;

  if saving_status = 'verified' then
    raise exception 'the purchase record behind a verified saving is immutable'
      using errcode = 'restrict_violation',
            hint = 'Its saving_record has already been verified and cannot be undermined.';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

drop trigger if exists purchase_record_locked_by_verified_saving on purchase_record;

create trigger purchase_record_locked_by_verified_saving
  before update or delete on purchase_record
  for each row
  execute function refuse_purchase_record_mutation_when_saving_verified();

comment on function refuse_purchase_record_mutation_when_saving_verified() is
  'Closes the same gap 20260819000005_owner_guard.sql closes for membership: a verified
   saving_record''s evidence must not be able to drift via an edit to the purchase_record it
   points at. See data-model.md''s "Additional Design Decisions".';
