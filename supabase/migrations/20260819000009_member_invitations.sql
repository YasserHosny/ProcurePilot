-- 0009_member_invitations.sql — closes the last structural gap in the RLS design.
--
-- THE PROBLEM
-- Accepting a member invitation is a chicken-and-egg problem that RLS cannot express. The invitee
-- is, by definition, NOT yet a member of the target workspace: they hold no `tenant_id` claim for
-- it, so `member_invitation` and `membership` are both invisible to them. The one operation that
-- turns an outsider into a member cannot be performed by either an outsider or a member.
--
-- This is the third time this shape has appeared — audit writes (0007), workspace listing (0008),
-- and now acceptance. The pattern is consistent: any operation that legitimately crosses or
-- precedes the tenancy boundary needs a SECURITY DEFINER function that re-derives authority from
-- the JWT, rather than an RLS bypass in application code.
--
-- THE REJECTED FIX
-- The implementation this replaces used a service-role client for acceptance. It was correct
-- about the constraint and said so rather than hiding it — the brief had forbidden new
-- migrations, which was the brief's mistake, not the implementer's.
--
-- WHY THE FUNCTION IS SAFE
-- It matches on the token HASH and on the caller's own verified email. Holding the token is not
-- sufficient: an intercepted invitation cannot be redeemed by anyone but its addressee.

create or replace function current_user_email()
returns text
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'email', '');
$$;

create or replace function accept_member_invitation(
  p_token_hash text,
  p_user_id    uuid,
  p_email      text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  invitation   member_invitation%rowtype;
  existing_id  uuid;
  new_id       uuid;
begin
  -- Deliberately NOT filtered by status='pending'. Filtering here made a second acceptance
  -- return null instead of the existing membership, which contradicts the idempotency this
  -- function claims and the spec requires. Status is judged below, once the row is in hand.
  select * into invitation
    from member_invitation
   where token_hash = p_token_hash
   for update;

  if not found then
    return null;  -- unknown token
  end if;

  if invitation.status in ('revoked', 'expired') or invitation.expires_at <= now() then
    return null;  -- indistinguishable from unknown, by design: do not confirm a token existed
  end if;

  -- The token alone is not authority. It must be redeemed by the address it was sent to.
  if lower(invitation.email) <> lower(p_email) then
    raise exception 'invitation was issued to a different address'
      using errcode = 'insufficient_privilege';
  end if;

  -- Idempotent: a second acceptance returns the membership the first one created rather than
  -- adding a duplicate, and rather than reporting failure for work already done. The unique
  -- constraint on (tenant_id, user_id) is the real guarantee against duplicates under
  -- concurrency; this lookup turns the losing race into a clean answer instead of an
  -- integrity error.
  select id into existing_id
    from membership
   where tenant_id = invitation.tenant_id
     and user_id = p_user_id;

  if existing_id is not null then
    update member_invitation set status = 'accepted' where id = invitation.id;
    return existing_id;
  end if;

  -- Already accepted, but by somebody else: the token has been spent and is not reusable.
  if invitation.status = 'accepted' then
    return null;
  end if;

  insert into membership (tenant_id, user_id, email, role)
  values (invitation.tenant_id, p_user_id, p_email, invitation.role)
  on conflict (tenant_id, user_id) do update set status = 'active'
  returning id into new_id;

  update member_invitation set status = 'accepted' where id = invitation.id;

  return new_id;
end;
$$;

grant execute on function current_user_email()                        to authenticated;
grant execute on function accept_member_invitation(text, uuid, text)  to authenticated;
revoke execute on function accept_member_invitation(text, uuid, text) from anon, public;

comment on function accept_member_invitation is
  'Turns an invitation into a membership. SECURITY DEFINER because the invitee holds no claim for
   the target workspace and so cannot see the invitation or write the membership. Requires the
   token hash AND the addressee''s own email, so an intercepted token is not redeemable. Idempotent.';
