-- Allow an approval request to claim a preview before the synchronous import begins.

alter table catalogue_refresh_review
  drop constraint catalogue_refresh_review_status_check;

alter table catalogue_refresh_review
  add constraint catalogue_refresh_review_status_check
  check (status in ('pending_review', 'processing', 'approved', 'rejected'));

alter table catalogue_refresh_review
  drop constraint catalogue_refresh_review_reviewed_state;

alter table catalogue_refresh_review
  add constraint catalogue_refresh_review_reviewed_state
  check (
    (status in ('pending_review', 'processing'))
      = (reviewed_at is null and reviewed_by is null)
  );
