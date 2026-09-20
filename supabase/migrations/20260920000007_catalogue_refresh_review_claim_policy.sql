-- Permit the owner/buyer claim transition while keeping final decisions attributed.

drop policy if exists catalogue_refresh_review_owner_buyer_update on catalogue_refresh_review;

create policy catalogue_refresh_review_owner_buyer_update on catalogue_refresh_review
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and (
      (status = 'processing' and reviewed_by is null and reviewed_at is null)
      or (
        status in ('approved', 'rejected')
        and reviewed_by = current_membership_id()
        and reviewed_at is not null
      )
    )
  );
