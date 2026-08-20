-- 20260819000010_invitation_lookup.sql — the fourth and last instance of one pattern.
--
-- THE PROBLEM
-- Accepting an invitation begins by resolving it: the server needs the invited address and role
-- before it can create the account. But the invitee is unauthenticated at that moment — they have
-- no session, no tenant claim, and `member_invitation` is tenant-scoped. The lookup returns
-- nothing and acceptance fails with a bare 503.
--
-- Migration 0009 solved the *write* half (accept_member_invitation) and left the *read* half
-- still going through RLS, which was an incomplete fix on my part rather than a new problem.
--
-- THE PATTERN, STATED ONCE
-- This is the fourth operation that legitimately crosses or precedes the tenancy boundary:
--   0007  writing an audit event for a pre-authentication or refused action
--   0008  listing the workspaces a person belongs to
--   0009  accepting an invitation into a workspace you are not yet in
--   0010  resolving that invitation in order to accept it
-- Every one needs a SECURITY DEFINER function that re-derives authority from something the caller
-- must already hold, rather than an RLS bypass in application code. If a fifth appears, it almost
-- certainly wants this shape too.
--
-- WHY THIS IS SAFE
-- The token hash is the authority. Only the holder of the plaintext token can produce it, the
-- plaintext is never stored, and the function returns nothing that is not already known to
-- whoever received the invitation. It deliberately does NOT return the tenant's other data.

create or replace function member_invitation_for_token(p_token_hash text)
returns table (
  id         uuid,
  tenant_id  uuid,
  email      text,
  role       member_role,
  status     member_invitation_status,
  expires_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select i.id, i.tenant_id, i.email, i.role, i.status, i.expires_at
    from member_invitation i
   where i.token_hash = p_token_hash;
$$;

-- anon as well as authenticated: an invitee accepting a first invitation has no session yet.
grant execute on function member_invitation_for_token(text) to anon, authenticated;

comment on function member_invitation_for_token(text) is
  'Resolves an invitation from its token hash so an unauthenticated invitee can accept it.
   SECURITY DEFINER because member_invitation is tenant-scoped and the invitee is, by definition,
   not yet in that tenant. The hash is the authority: it cannot be derived from stored data.';

-- ---------------------------------------------------------------------------
-- service_role privileges
--
-- Migration 0004 granted table privileges to `authenticated` and stopped there. service_role
-- BYPASSES RLS but still needs ordinary privileges, and it had none — so the back-office paths
-- (invitation lookup, marking an invitation expired or accepted) failed with
-- 'permission denied for table member_invitation', which reads like an RLS problem and is not.
--
-- Bypassing row-level security and being allowed to touch the table at all are two different
-- things. Granting one without the other produces a role that can see everything and read nothing.
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on tenant              to service_role;
grant select, insert, update, delete on membership          to service_role;
grant select, insert, update, delete on member_invitation   to service_role;
grant select, insert, update, delete on platform_invitation to service_role;
grant select, insert                 on audit_event         to service_role;
grant select                         on supported_region    to service_role;
grant select                         on supported_currency  to service_role;
grant select                         on supported_tax_model to service_role;
grant usage, select on all sequences in schema public to service_role;

-- ---------------------------------------------------------------------------
-- accept_member_invitation must be callable by anon.
--
-- 0009 granted it to `authenticated` only, which assumed the invitee already had a session. They
-- cannot: signing in builds a session that requires a tenant_id claim, and the auth hook only
-- injects that claim once a membership exists — which is precisely what acceptance creates.
-- Requiring a session first makes acceptance depend on its own outcome.
--
-- The function does not read the caller's claims; it takes the user id explicitly and proves
-- authority from the token hash and the addressee's email. So anon is the correct grant, and the
-- route signs the invitee in AFTER acceptance, when there is something to scope a session to.
-- ---------------------------------------------------------------------------
grant execute on function accept_member_invitation(text, uuid, text) to anon;

-- ---------------------------------------------------------------------------
-- Acceptance must also make the new membership ACTIVE when it is the person's first.
--
-- The custom access token hook injects tenant_id only from a membership flagged
-- is_active_workspace. 0009 inserted the membership without setting it, so a brand-new invitee
-- accepted successfully and then could not sign in: their token carried no tenant_id, and
-- verification rejects a token without one. Acceptance appeared to work and left the person
-- locked out — the worst kind of half-success.
--
-- Only when they have no other active workspace: someone already working in a workspace should
-- not be yanked into a new one just because they accepted an invitation.
-- ---------------------------------------------------------------------------
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
  has_active   boolean;
begin
  select * into invitation
    from member_invitation
   where token_hash = p_token_hash
   for update;

  if not found then
    return null;
  end if;

  if invitation.status in ('revoked', 'expired') or invitation.expires_at <= now() then
    return null;
  end if;

  if lower(invitation.email) <> lower(p_email) then
    raise exception 'invitation was issued to a different address'
      using errcode = 'insufficient_privilege';
  end if;

  select exists (
    select 1 from membership
     where user_id = p_user_id and is_active_workspace and status = 'active'
  ) into has_active;

  select id into existing_id
    from membership
   where tenant_id = invitation.tenant_id and user_id = p_user_id;

  if existing_id is not null then
    update member_invitation set status = 'accepted' where id = invitation.id;
    return existing_id;
  end if;

  if invitation.status = 'accepted' then
    return null;
  end if;

  insert into membership (tenant_id, user_id, email, role, is_active_workspace)
  values (invitation.tenant_id, p_user_id, p_email, invitation.role, not has_active)
  on conflict (tenant_id, user_id) do update set status = 'active'
  returning id into new_id;

  update member_invitation set status = 'accepted' where id = invitation.id;

  return new_id;
end;
$$;

grant execute on function accept_member_invitation(text, uuid, text) to anon, authenticated;
