-- 20260913000001_purchase_request_delivery_status.sql — task T001, chunk R2.3 (Mobile Approvals
-- and Delivery Receipt)
--
-- Extends purchase_request_status with the delivery half of the request lifecycle
-- (specs/010-mobile-approvals-receipt/research.md R1): an approved request is implicitly
-- "ordered" the moment a human approved it (this chunk adds no separate "place the order"
-- action), and a branch member later confirms it "delivered".
--
-- This file adds ONLY the new enum values and nothing else. PostgreSQL does not allow a newly
-- added enum value to be referenced by any statement in the same transaction block it was added
-- in (a standing PostgreSQL restriction, not specific to this project) — the columns and logic
-- that use 'ordered'/'delivered' live in the next migration, deliberately split out.

alter type purchase_request_status add value if not exists 'ordered' after 'approved';
alter type purchase_request_status add value if not exists 'delivered' after 'ordered';
