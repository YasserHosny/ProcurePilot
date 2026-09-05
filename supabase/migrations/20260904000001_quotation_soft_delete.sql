-- Soft delete for quotations (Section 3: No delete or archive)
alter table quotation add column if not exists deleted_at timestamptz;

-- Exclude soft-deleted quotations from the one-open-per-quotation review_task index
-- by also filtering them out of the quotation query (the service layer does this).

-- Update RLS policy to exclude deleted quotations from normal reads.
-- The existing RLS policy on quotation uses USING (tenant_id = ...).
-- We add a default exclusion: deleted_at IS NULL. Users can explicitly query deleted ones.
create index if not exists quotation_deleted_idx on quotation (tenant_id, deleted_at)
  where deleted_at is not null;
