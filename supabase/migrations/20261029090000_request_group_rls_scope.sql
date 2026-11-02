-- 20261029090000_request_group_rls_scope.sql — purchase_request_group gets the visibility and
-- the insert rule its siblings already have (spec 024 data-model.md; review of 20261029080000).
--
-- * Select: data-model.md asks for "same visibility as purchase_request". A RESTRICTIVE policy
--   narrows the tenant-wide permissive one exactly as purchase_request_scoped_visibility
--   (20260823000041) does: owners, members with no branch assignment, members assigned to the
--   group's branch, and the group's creator (the requester-sees-own clause).
-- * Insert: the creator must be the caller, with the live role lookup, as rfq_insert does since
--   20261018000009. A group is immutable evidence; a row filed under another member's name could
--   never be corrected.

create policy purchase_request_group_scoped_visibility on purchase_request_group
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_member_role() = 'owner'
      or created_by_membership_id = current_membership_id()
      or not exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = purchase_request_group.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
      )
      or exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = purchase_request_group.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
          and branch_role_assignment.branch_id = purchase_request_group.branch_id
      )
    )
  );

drop policy purchase_request_group_insert on purchase_request_group;
create policy purchase_request_group_insert on purchase_request_group
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_membership_role() in ('owner', 'buyer')
  );
