-- 20261030000000_membership_display_name.sql — members have a name, not just an email (PPS-125).
--
-- The Approval Queue showed the requester's email: membership had no name column, so
-- PurchaseRequest.requester_name and ApprovalStep.assigned_name were always empty.
--
--   * membership.display_name: set at sign-up (the owner) or from the invitation on acceptance;
--     editable in Team Management. Nullable: existing members have none until someone sets it.
--   * member_invitation.display_name: the name an owner gives when inviting, copied onto the
--     membership when the invitation is accepted (server-side, after accept_member_invitation).
--   * `authenticated` may update membership.display_name. The existing membership_update policy
--     (20261018000010) already limits that to the caller's own row or, for an owner, any row in
--     the workspace; membership_owner_only_changes does not need to know about the column.
--
-- No RLS change: both tables keep their policies. member_invitation is already writable by
-- `authenticated` under its tenant policy (0004).

alter table membership
  add column display_name text
  constraint membership_display_name_check
    check (display_name is null or (display_name = btrim(display_name)
                                     and char_length(display_name) between 1 and 100));

alter table member_invitation
  add column display_name text
  constraint member_invitation_display_name_check
    check (display_name is null or (display_name = btrim(display_name)
                                     and char_length(display_name) between 1 and 100));

grant update (display_name) on membership to authenticated;

comment on column membership.display_name is
  'The member''s name as shown to colleagues (Approval Queue, Team Management). Trimmed, 1-100
   characters, or null when nobody has set one. 20261030000000.';
comment on column member_invitation.display_name is
  'Name the inviting owner gave; copied to membership.display_name on acceptance. 20261030000000.';
