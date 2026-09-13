-- 20260913000002_purchase_request_delivery_columns.sql — task T002, chunk R2.3 (Mobile Approvals
-- and Delivery Receipt)
--
-- Delivery-fact columns for purchase_request and purchase_request_line
-- (specs/010-mobile-approvals-receipt/data-model.md). Must run after
-- 20260913000001_purchase_request_delivery_status.sql — this file is the first to reference the
-- 'ordered'/'delivered' enum values that migration added.
--
-- has_delivery_discrepancy is a derived summary flag (fast filtering/display); the per-line
-- quantity_received values on purchase_request_line are the source of truth for exactly which
-- line(s) fell short, the same "aggregate flag at the parent, detail at the line" split
-- has_incomplete_estimate/estimated_unit_price_* already established for R2.1.

alter table purchase_request
  add column if not exists delivered_at timestamptz,
  add column if not exists delivery_confirmed_by_membership_id uuid,
  add column if not exists has_delivery_discrepancy boolean not null default false;

alter table purchase_request
  add constraint purchase_request_delivery_confirmed_by_fkey
  foreign key (tenant_id, delivery_confirmed_by_membership_id)
  references membership (tenant_id, id);

-- Mirrors approval_step's own "decided fields populated iff decided" discipline: delivered_at is
-- set exactly when the request has actually reached the delivered status, never before, never
-- left stamped on a request that somehow regresses (this schema has no path backward out of
-- delivered, but the pairing check is cheap insurance regardless).
alter table purchase_request
  add constraint purchase_request_delivered_at_pairing
  check ((status = 'delivered') = (delivered_at is not null));

alter table purchase_request_line
  add column if not exists quantity_received numeric(18, 6);

alter table purchase_request_line
  add constraint purchase_request_line_quantity_received_check
  check (quantity_received is null or quantity_received >= 0);
